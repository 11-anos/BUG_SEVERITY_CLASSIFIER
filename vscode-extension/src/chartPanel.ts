import * as vscode from 'vscode';
import { ScanResult } from './projectScan';
import { renderChartSvg } from './chartSvg';

let currentPanel: vscode.WebviewPanel | undefined;
let latestResult: ScanResult | undefined;

function escapeHtml(s: string): string {
  return s.replace(/[<>&"']/g, (c) => {
    switch (c) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case '"': return '&quot;';
      case "'": return '&#39;';
      default:  return c;
    }
  });
}

export function showChart(context: vscode.ExtensionContext, result: ScanResult): void {
  latestResult = result;

  const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;

  if (currentPanel) {
    currentPanel.reveal(column);
  } else {
    currentPanel = vscode.window.createWebviewPanel(
      'ruleEngineChart',
      'Rule Engine: Findings',
      { viewColumn: column, preserveFocus: false },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [],
      }
    );

    currentPanel.onDidDispose(() => {
      currentPanel = undefined;
    });

    currentPanel.webview.onDidReceiveMessage(async (msg: unknown) => {
      if (!latestResult) return;
      const m = msg as { type?: string; path?: string; line?: number };
      if (m?.type !== 'openFile' || typeof m.path !== 'string') return;

      const rootUri = vscode.Uri.file(latestResult.root);
      const fileUri = vscode.Uri.joinPath(rootUri, m.path);
      try {
        const doc = await vscode.workspace.openTextDocument(fileUri);
        const editor = await vscode.window.showTextDocument(doc, { preview: false });
        const line0 = Math.max(0, (m.line ?? 1) - 1);
        const pos = new vscode.Position(line0, 0);
        editor.selection = new vscode.Selection(pos, pos);
        editor.revealRange(
          new vscode.Range(pos, pos),
          vscode.TextEditorRevealType.InCenter
        );
      } catch (e) {
        const msg2 = e instanceof Error ? e.message : String(e);
        vscode.window.showErrorMessage(`Rule Engine: cannot open ${m.path}: ${msg2}`);
      }
    });
  }

  currentPanel.title = `Rule Engine: ${result.totals.total} findings`;
  currentPanel.webview.html = buildHtml(result);
}

function buildHtml(result: ScanResult): string {
  const { svg } = renderChartSvg(result);

  const csp = [
    `default-src 'none'`,
    `style-src 'unsafe-inline'`,
    `script-src 'unsafe-inline'`,
    `img-src data:`,
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>
  body {
    font-family: var(--vscode-font-family);
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    padding: 16px;
    margin: 0;
  }
  .summary {
    margin-bottom: 16px;
    font-size: 13px;
    line-height: 1.6;
    border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,0.2));
    padding-bottom: 12px;
  }
  .summary strong { color: var(--vscode-descriptionForeground); font-weight: 600; }
  svg { display: block; }
  .hdr { fill: var(--vscode-descriptionForeground); font-size: 12px; font-weight: 600; }
  .lbl { fill: var(--vscode-foreground); font-size: 12px; }
  .cnt { fill: #ffffff; font-size: 11px; font-weight: 600; pointer-events: none; }
  .rowAlt { fill: var(--vscode-editor-lineHighlightBackground, rgba(128,128,128,0.06)); }
  .bubble { cursor: pointer; }
  .bubble:hover { stroke: var(--vscode-focusBorder); stroke-width: 2; }
</style>
</head>
<body>
  <div class="summary">
    <div><strong>Root:</strong> ${escapeHtml(result.root)}</div>
    <div><strong>Files:</strong> ${result.files_scanned} scanned, ${result.files_with_findings} with findings</div>
    <div><strong>Totals:</strong> ${result.totals.error} error · ${result.totals.warning} warning · ${result.totals.info} info · ${result.totals.hint} hint</div>
  </div>
  ${svg}
  <script>
    const vscode = acquireVsCodeApi();
    document.addEventListener('click', (e) => {
      const c = e.target && e.target.closest ? e.target.closest('circle.bubble') : null;
      if (!c) return;
      const p = c.getAttribute('data-path');
      const l = parseInt(c.getAttribute('data-line'), 10) || 1;
      vscode.postMessage({ type: 'openFile', path: p, line: l });
    });
  </script>
</body>
</html>`;
}
