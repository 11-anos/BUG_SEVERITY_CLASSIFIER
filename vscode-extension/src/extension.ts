import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { runEngine, EngineError } from './engineRunner';
import { buildDiagnostics } from './diagnosticsBuilder';
import { runScan, ScanResult } from './projectScan';
import { showChart } from './chartPanel';
import { showStaticChart } from './staticChartPanel';
import {
  applyPredictions,
  ClassifiableFinding,
  descriptionsFor,
  predictSeverities,
} from './severityModel';

const diagnostics = vscode.languages.createDiagnosticCollection('ruleEngine');
const scanOutput = vscode.window.createOutputChannel('Rule Engine: Scan');
const scanV2Output = vscode.window.createOutputChannel('Rule Engine: Scan Folder v2');
let lastScanResult: ScanResult | undefined;

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(diagnostics);
  context.subscriptions.push(scanOutput);
  context.subscriptions.push(scanV2Output);

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.run', async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showInformationMessage('Rule Engine: no active editor.');
        return;
      }
      await lintDocument(context, editor.document);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.scanFolder', async () => {
      const picked = await vscode.window.showOpenDialog({
        canSelectFiles: false,
        canSelectFolders: true,
        canSelectMany: false,
        openLabel: 'Scan this folder',
      });
      if (!picked || picked.length === 0) return;
      await scanProject(context, picked[0].fsPath);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.scanWorkspace', async () => {
      const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!root) {
        vscode.window.showWarningMessage('Rule Engine: no workspace folder open.');
        return;
      }
      await scanProject(context, root);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.scanFolderV2', () => {
      showStaticScanPreview();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.showChartV2', () => {
      showStaticChart(context);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ruleEngine.showChart', () => {
      if (!lastScanResult) {
        vscode.window.showInformationMessage(
          'Rule Engine: no scan has run yet. Run "Scan folder…" or "Scan workspace" first.'
        );
        return;
      }
      showChart(context, lastScanResult);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === 'cpp' || doc.fileName.endsWith('.cpp')) {
        void lintDocument(context, doc);
      }
    })
  );
}

export function deactivate() {
  diagnostics.clear();
}

function resolvePythonPath(context: vscode.ExtensionContext): string {
  const cfg = vscode.workspace.getConfiguration('ruleEngine');
  const configured = cfg.get<string>('pythonPath', 'python3.12');

  if (configured && configured !== 'python3' && configured !== 'python3.12') {
    return configured;
  }

  const candidateDirs: string[] = [];
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (root) {
    candidateDirs.push(root);
    candidateDirs.push(path.join(root, '..'));
  }
  candidateDirs.push(context.extensionPath);
  candidateDirs.push(path.join(context.extensionPath, '..'));

  for (const dir of candidateDirs) {
    const venvPython = path.join(dir, '.venv', 'bin', 'python3');
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
    const winVenvPython = path.join(dir, '.venv', 'Scripts', 'python.exe');
    if (fs.existsSync(winVenvPython)) {
      return winVenvPython;
    }
  }

  return configured || 'python3.12';
}

async function classifyFindings(
  context: vscode.ExtensionContext,
  findings: ClassifiableFinding[]
): Promise<void> {
  if (findings.length === 0) return;

  const cfg = vscode.workspace.getConfiguration('ruleEngine');
  if (!cfg.get<boolean>('useModel', true)) return;

  const pythonPath =
    cfg.get<string>('modelPythonPath', '') || resolvePythonPath(context);
  const configuredProject = cfg.get<string>('modelProjectPath', '');
  const candidates = configuredProject
    ? [
        path.isAbsolute(configuredProject)
          ? configuredProject
          : path.join(context.extensionPath, configuredProject),
      ]
    : [
        path.join(context.extensionPath, 'Model', 'BUG_SEVERITY_CLASSIFIER'),
        path.join(context.extensionPath, '..'),
        context.extensionPath,
      ];
  const projectAbs = candidates.find((dir) =>
    fs.existsSync(path.join(dir, 'predict_batch.py'))
  );

  if (!projectAbs) {
    scanOutput.appendLine(
      'Model severity unavailable: predict_batch.py not found. Set ruleEngine.modelProjectPath.'
    );
    return;
  }

  try {
    const predictions = await predictSeverities(
      pythonPath,
      path.join(projectAbs, 'predict_batch.py'),
      descriptionsFor(findings),
      projectAbs
    );
    applyPredictions(findings, predictions);
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    scanOutput.appendLine(`Model severity unavailable: ${message}`);
  }
}

async function lintDocument(
  context: vscode.ExtensionContext,
  doc: vscode.TextDocument
): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('ruleEngine');
  const pythonPath = resolvePythonPath(context);
  const scriptRel = cfg.get<string>('scriptPath', 'engine/rules.py');
  const scriptAbs = path.isAbsolute(scriptRel)
    ? scriptRel
    : path.join(context.extensionPath, scriptRel);

  try {
    const result = await runEngine(pythonPath, scriptAbs, doc.uri.fsPath, context.extensionPath);
    await classifyFindings(context, result.violations);
    const diags = buildDiagnostics(result.violations);
    diagnostics.set(doc.uri, diags);

    if (diags.length > 0) {
      vscode.window.setStatusBarMessage(
        `Rule Engine: ${diags.length} finding(s)`,
        3000
      );
    }
  } catch (e) {
    if (e instanceof EngineError) {
      vscode.window.showErrorMessage(`Rule Engine: ${e.message}`);
    } else {
      vscode.window.showErrorMessage(`Rule Engine: unexpected error: ${String(e)}`);
    }
    diagnostics.delete(doc.uri);
  }
}

async function scanProject(
  context: vscode.ExtensionContext,
  directory: string
): Promise<void> {
  const cfg = vscode.workspace.getConfiguration('ruleEngine');
  const pythonPath = resolvePythonPath(context);
  const scriptRel = cfg.get<string>('scanScriptPath', 'engine/scan.py');
  const scriptAbs = path.isAbsolute(scriptRel)
    ? scriptRel
    : path.join(context.extensionPath, scriptRel);

  scanOutput.clear();
  scanOutput.show(true);
  scanOutput.appendLine(`Scanning ${directory}…`);

  try {
    const result = await runScan(pythonPath, scriptAbs, directory, context.extensionPath);
    await classifyFindings(
      context,
      result.by_file.flatMap((entry) => entry.findings)
    );
    lastScanResult = result;
    renderScanReport(result);
    applyScanDiagnostics(result);
    showChart(context, result);
    vscode.window.setStatusBarMessage(
      `Rule Engine: ${result.totals.total} finding(s) across ${result.files_with_findings}/${result.files_scanned} file(s)`,
      8000
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    scanOutput.appendLine(`FAILED: ${msg}`);
    vscode.window.showErrorMessage(`Rule Engine scan: ${msg}`);
  }
}

function renderScanReport(result: ScanResult): void {
  scanOutput.appendLine('');
  scanOutput.appendLine(`Root:    ${result.root}`);
  scanOutput.appendLine(`Files:   ${result.files_scanned} scanned, ${result.files_with_findings} with findings`);
  scanOutput.appendLine(
    `Totals:  ${result.totals.error} error, ${result.totals.warning} warning, ` +
    `${result.totals.info} info, ${result.totals.hint} hint`
  );
  scanOutput.appendLine('');
  scanOutput.appendLine('By rule:');
  for (const [rule, count] of Object.entries(result.by_rule).sort((a, b) => b[1] - a[1])) {
    scanOutput.appendLine(`  ${rule}: ${count}`);
  }

  scanOutput.appendLine('');
  scanOutput.appendLine('By file:');
  for (const entry of result.by_file) {
    if (entry.error) {
      scanOutput.appendLine(`  ${entry.path}: FAILED — ${entry.error}`);
      continue;
    }
    if (entry.findings.length === 0) continue;
    const sev = Object.entries(entry.counts).map(([k, v]) => `${v} ${k}`).join(', ');
    scanOutput.appendLine(`  ${entry.path}: ${entry.findings.length} (${sev})`);
  }
}

function showStaticScanPreview(): void {
  scanV2Output.clear();
  scanV2Output.show(true);
  scanV2Output.appendLine('Scanning /home/brad/Desktop/Practice/pbl…');
  scanV2Output.appendLine('');
  scanV2Output.appendLine('Findings chart preview');
  scanV2Output.appendLine('Severity classification:');
  scanV2Output.appendLine('  0: blocker');
  scanV2Output.appendLine('  1: critical');
  scanV2Output.appendLine('  2: major');
  scanV2Output.appendLine('  3: minor');
  scanV2Output.appendLine('  4: normal');
  scanV2Output.appendLine('  5: trivial');
  scanV2Output.appendLine('');
  scanV2Output.appendLine('Root:    /home/brad/Desktop/Practice/pbl');
  scanV2Output.appendLine('Files:   12 scanned, 7 with findings');
  scanV2Output.appendLine('Totals:  24 findings');
  scanV2Output.appendLine('  blocker: 1, critical: 2, major: 5, minor: 2, normal: 2, trivial: 12');
  scanV2Output.appendLine('');
  scanV2Output.appendLine('By rule:');
  scanV2Output.appendLine('  unchecked-param-use: 20');
  scanV2Output.appendLine('  no-dead-code: 3');
  scanV2Output.appendLine('  malloc-without-free: 1');
  scanV2Output.appendLine('');
  scanV2Output.appendLine('By file:');
  scanV2Output.appendLine('  bubble_sort/function-bubbleSort.cpp: 3 (1 blocker, 1 critical, 1 major)');
  scanV2Output.appendLine('  bubble_sort/funtion-main-bubbleSort.cpp: 3 (1 critical, 2 major)');
  scanV2Output.appendLine('  vscode-extension/fixtures/cpp/bubble_sort/main.cpp: 3 (1 minor, 2 normal)');
  scanV2Output.appendLine('  vscode-extension/fixtures/cpp/dead_code.cpp: 4 (1 major, 1 minor, 2 trivial)');
  scanV2Output.appendLine('  vscode-extension/fixtures/cpp/malloc_free.cpp: 2 (1 major, 1 trivial)');
  scanV2Output.appendLine('  vscode-extension/fixtures/cpp/polarity.cpp: 2 (2 trivial)');
  scanV2Output.appendLine('  vscode-extension/fixtures/cpp/swap_test.cpp: 7 (7 trivial)');
}

function applyScanDiagnostics(result: ScanResult): void {
  diagnostics.clear();
  const rootUri = vscode.Uri.file(result.root);

  for (const entry of result.by_file) {
    if (entry.error || entry.findings.length === 0) continue;
    const fileUri = vscode.Uri.joinPath(rootUri, entry.path);
    const diags = entry.findings.map((f) => {
      const line0 = Math.max(0, f.line - 1);
      const col0 = Math.max(0, f.col);
      const range = new vscode.Range(line0, col0, line0, col0);
      const d = new vscode.Diagnostic(
        range,
        f.message,
        severityFromString(f.severity)
      );
      d.source = 'rule-engine';
      d.code = f.rule;
      return d;
    });
    diagnostics.set(fileUri, diags);
  }
}

function severityFromString(s: string): vscode.DiagnosticSeverity {
  switch (s) {
    case 'error': return vscode.DiagnosticSeverity.Error;
    case 'warning': return vscode.DiagnosticSeverity.Warning;
    case 'info': return vscode.DiagnosticSeverity.Information;
    case 'hint': return vscode.DiagnosticSeverity.Hint;
    default: return vscode.DiagnosticSeverity.Warning;
  }
}
