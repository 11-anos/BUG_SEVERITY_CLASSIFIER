export type Severity = 'error' | 'warning' | 'info' | 'hint';

export type ModelSeverity =
  | 'blocker'
  | 'critical'
  | 'major'
  | 'minor'
  | 'normal'
  | 'trivial';

export interface EngineViolation {
  rule: string;
  line: number;
  col: number;
  message: string;
  severity: Severity;
  modelSeverity?: ModelSeverity;
  modelConfidence?: number;
}

export interface EngineResult {
  file: string;
  violations: EngineViolation[];
}
