import { execFile } from 'child_process';
import { EngineError } from './engineRunner';
import { ModelSeverity } from './types';

export interface ScanFinding {
  rule: string;
  line: number;
  col: number;
  message: string;
  severity: 'error' | 'warning' | 'info' | 'hint';
  modelSeverity?: ModelSeverity;
  modelConfidence?: number;
}

export interface ScanFileEntry {
  path: string;
  error: string | null;
  findings: ScanFinding[];
  counts: Record<string, number>;
}

export interface ScanResult {
  root: string;
  files_scanned: number;
  files_with_findings: number;
  totals: { error: number; warning: number; info: number; hint: number; total: number };
  by_rule: Record<string, number>;
  by_file: ScanFileEntry[];
}

export function runScan(
  pythonPath: string,
  scanScriptAbsPath: string,
  directory: string,
  cwd: string
): Promise<ScanResult> {
  return new Promise((resolve, reject) => {
    execFile(
      pythonPath,
      [scanScriptAbsPath, directory, '--json'],
      { cwd, timeout: 120000, maxBuffer: 50 * 1024 * 1024 },
      (err, stdout, stderr) => {
        const execErr = err as (NodeJS.ErrnoException & { code?: number }) | null;
        const exitOk = !execErr || execErr.code === 0 || execErr.code === 1;
        if (!exitOk) {
          reject(new EngineError(
            `scan failed: ${execErr?.message ?? 'unknown'}${stderr ? ' — ' + stderr.trim() : ''}`
          ));
          return;
        }
        try {
          if (!stdout || !stdout.trim()) {
            throw new Error('empty output');
          }
          resolve(JSON.parse(stdout) as ScanResult);
        } catch {
          const errDetail = stderr && stderr.trim() ? ` — stderr: ${stderr.trim()}` : '';
          reject(new EngineError(
            `scan output was not valid JSON. First 200 chars: ${stdout.slice(0, 200)}${errDetail}`
          ));
        }
      }
    );
  });
}
