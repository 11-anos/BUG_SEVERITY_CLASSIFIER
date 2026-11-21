import * as vscode from 'vscode';
import { EngineViolation, Severity } from './types';

const SEVERITY_MAP: Record<Severity, vscode.DiagnosticSeverity> = {
  error: vscode.DiagnosticSeverity.Error,
  warning: vscode.DiagnosticSeverity.Warning,
  info: vscode.DiagnosticSeverity.Information,
  hint: vscode.DiagnosticSeverity.Hint,
};

export function buildDiagnostics(
  violations: EngineViolation[]
): vscode.Diagnostic[] {
  return violations.map((v) => {
    // Engine line is 1-indexed; VSCode is 0-indexed. Engine col is already 0-indexed.
    const line0 = Math.max(0, v.line - 1);
    const col0 = Math.max(0, v.col);
    const range = new vscode.Range(line0, col0, line0, col0);
    const d = new vscode.Diagnostic(
      range,
      v.message,
      SEVERITY_MAP[v.severity] ?? vscode.DiagnosticSeverity.Warning
    );
    d.source = 'rule-engine';
    d.code = v.rule;
    return d;
  });
}
