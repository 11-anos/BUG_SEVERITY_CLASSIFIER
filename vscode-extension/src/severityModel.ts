import { spawn } from 'child_process';
import { ModelSeverity, Severity } from './types';

export interface ModelPrediction {
  description: string;
  predicted_severity: string;
  highest_probability: number;
  probabilities: Record<string, number>;
}

export interface ClassifiableFinding {
  rule: string;
  message: string;
  severity: Severity;
  modelSeverity?: ModelSeverity;
  modelConfidence?: number;
}

const MODEL_TO_DIAGNOSTIC: Record<ModelSeverity, Severity> = {
  blocker: 'error',
  critical: 'error',
  major: 'warning',
  minor: 'warning',
  normal: 'info',
  trivial: 'hint',
};

export function descriptionsFor(findings: ClassifiableFinding[]): string[] {
  return findings.map((finding) => `${finding.rule}: ${finding.message}`);
}

export function applyPredictions(
  findings: ClassifiableFinding[],
  predictions: ModelPrediction[]
): void {
  findings.forEach((finding, index) => {
    const prediction = predictions[index];
    if (!prediction) return;

    const label = prediction.predicted_severity as ModelSeverity;
    const severity = MODEL_TO_DIAGNOSTIC[label];
    if (!severity) return;

    finding.modelSeverity = label;
    finding.modelConfidence = prediction.highest_probability;
    finding.severity = severity;

    if (!finding.message.includes('[model:')) {
      const percent = (prediction.highest_probability * 100).toFixed(0);
      finding.message = `${finding.message} [model: ${label} ${percent}%]`;
    }
  });
}

export function predictSeverities(
  pythonPath: string,
  scriptAbsPath: string,
  descriptions: string[],
  cwd: string
): Promise<ModelPrediction[]> {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonPath, ['-u', scriptAbsPath], { cwd });
    let stdout = '';
    let stderr = '';
    let settled = false;
    let timer: NodeJS.Timeout;

    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn();
    };

    timer = setTimeout(() => {
      proc.kill();
      finish(() => reject(new Error('model timed out')));
    }, 180_000);

    proc.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    proc.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on('error', (err) => {
      finish(() => reject(new Error(`cannot start model: ${err.message}`)));
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        finish(() =>
          reject(
            new Error(
              `model exited with code ${code}${stderr ? ': ' + stderr.trim() : ''}`
            )
          )
        );
        return;
      }

      try {
        const parsed: unknown = JSON.parse(stdout);
        if (!Array.isArray(parsed)) {
          throw new Error('expected a JSON array');
        }
        finish(() => resolve(parsed as ModelPrediction[]));
      } catch (e) {
        finish(() =>
          reject(new Error(`model output was not valid JSON: ${String(e)}`))
        );
      }
    });

    proc.stdin.end(JSON.stringify({ descriptions }));
  });
}
