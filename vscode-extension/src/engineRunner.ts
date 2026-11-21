import { execFile } from 'child_process';
import { EngineResult } from './types';

export class EngineError extends Error {}

export function runEngine(
  pythonPath: string,
  scriptAbsPath: string,
  fileAbsPath: string,
  cwd: string
): Promise<EngineResult> {
  return new Promise((resolve, reject) => {
    execFile(
      pythonPath,
      [scriptAbsPath, fileAbsPath, '--json'],
      { cwd, timeout: 30000, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        // Exit code 1 = violations found. That is success for our purposes.
        const execErr = err as (NodeJS.ErrnoException & { code?: number }) | null;
        const exitOk = !execErr || execErr.code === 1;

        if (!exitOk) {
          const msg = execErr?.message ?? 'unknown error';
          reject(new EngineError(
            `engine invocation failed: ${msg}${stderr ? ' — ' + stderr.trim() : ''}`
          ));
          return;
        }

        let parsed: EngineResult;
        try {
          if (!stdout || !stdout.trim()) {
            throw new Error('empty output');
          }
          parsed = JSON.parse(stdout) as EngineResult;
        } catch {
          const errDetail = stderr && stderr.trim() ? ` — stderr: ${stderr.trim()}` : '';
          reject(new EngineError(
            `engine output was not valid JSON. First 200 chars: ${stdout.slice(0, 200)}${errDetail}`
          ));
          return;
        }

        if (!parsed || !Array.isArray(parsed.violations)) {
          reject(new EngineError('engine JSON missing violations array'));
          return;
        }

        resolve(parsed);
      }
    );
  });
}
