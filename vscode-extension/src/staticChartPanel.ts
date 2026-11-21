import * as vscode from 'vscode';

let currentPanel: vscode.WebviewPanel | undefined;

function escapeHtml(value: string): string {
  return value.replace(/[<>&"']/g, (character) => {
    switch (character) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case '"': return '&quot;';
      case "'": return '&#39;';
      default: return character;
    }
  });
}

const classifications = [
  ['blocker', 1, '#f85149'],
  ['critical', 2, '#ff7b72'],
  ['major', 5, '#d29922'],
  ['minor', 2, '#58a6ff'],
  ['normal', 2, '#3fb950'],
  ['trivial', 12, '#8b949e'],
] as const;

const files = [
  ['bubble_sort/function-bubbleSort.cpp', 3, '1 blocker, 1 critical, 1 major'],
  ['bubble_sort/funtion-main-bubbleSort.cpp', 3, '1 critical, 2 major'],
  ['vscode-extension/fixtures/cpp/bubble_sort/main.cpp', 3, '1 minor, 2 normal'],
  ['vscode-extension/fixtures/cpp/dead_code.cpp', 4, '1 major, 1 minor, 2 trivial'],
  ['vscode-extension/fixtures/cpp/malloc_free.cpp', 2, '1 major, 1 trivial'],
  ['vscode-extension/fixtures/cpp/polarity.cpp', 2, '2 trivial'],
  ['vscode-extension/fixtures/cpp/swap_test.cpp', 7, '7 trivial'],
] as const;

export function showStaticChart(context: vscode.ExtensionContext): void {
  const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;

  if (!currentPanel) {
    currentPanel = vscode.window.createWebviewPanel(
      'ruleEngineChartV2',
      'Rule Engine: Findings v2',
      { viewColumn: column, preserveFocus: false },
      { enableScripts: false, retainContextWhenHidden: true, localResourceRoots: [] }
    );
    currentPanel.onDidDispose(() => {
      currentPanel = undefined;
    });
  } else {
    currentPanel.reveal(column);
  }

  currentPanel.title = 'Rule Engine: Findings v2';
  currentPanel.webview.html = buildHtml();
}

function buildHtml(): string {
  const classificationCards = classifications.map(([name, count, color], index) => `
    <div class="class-card">
      <div class="class-number">${index}</div>
      <div class="class-color" style="background:${color}"></div>
      <div class="class-name">${name}</div>
      <div class="class-count">${count}</div>
    </div>`).join('');

  const fileRows = files.map(([file, count, detail]) => `
    <div class="file-row">
      <span class="file-name">${escapeHtml(file)}</span>
      <span class="file-bar"><span style="width:${count * 20}%"></span></span>
      <strong>${count}</strong>
      <span class="muted">${detail}</span>
    </div>`).join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground);
    background: var(--vscode-editor-background); margin: 0; padding: 28px; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 14px; margin: 28px 0 12px; color: var(--vscode-descriptionForeground); }
  .subtitle, .muted { color: var(--vscode-descriptionForeground); }
  .summary { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr));
    gap: 10px; margin-top: 22px; }
  .metric, .class-card { border: 1px solid var(--vscode-panel-border);
    background: var(--vscode-sideBar-background); border-radius: 8px; padding: 14px; }
  .metric-label { color: var(--vscode-descriptionForeground); font-size: 12px; }
  .metric-value { font-size: 24px; font-weight: 700; margin-top: 5px; }
  .classification { display: grid; grid-template-columns: repeat(6, minmax(90px, 1fr)); gap: 10px; }
  .class-card { position: relative; min-height: 74px; }
  .class-number { position: absolute; right: 10px; top: 8px; color: var(--vscode-descriptionForeground); }
  .class-color { width: 10px; height: 10px; border-radius: 50%; margin-bottom: 12px; }
  .class-name { font-weight: 600; text-transform: capitalize; }
  .class-count { font-size: 20px; font-weight: 700; margin-top: 8px; }
  .panel { border: 1px solid var(--vscode-panel-border); border-radius: 8px; overflow: hidden; }
  .file-row { display: grid; grid-template-columns: minmax(260px, 2fr) minmax(100px, 1fr) 35px minmax(130px, 1fr);
    gap: 14px; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--vscode-panel-border); }
  .file-row:last-child { border-bottom: 0; }
  .file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-bar { height: 8px; background: var(--vscode-editor-lineHighlightBackground); border-radius: 5px; overflow: hidden; }
  .file-bar span { display: block; height: 100%; background: #58a6ff; border-radius: 5px; }
  .legend { margin-top: 18px; font-size: 12px; color: var(--vscode-descriptionForeground); }
  @media (max-width: 760px) { .summary, .classification { grid-template-columns: repeat(2, 1fr); }
    .file-row { grid-template-columns: 1fr 70px 25px; } .file-row .muted { display: none; } }
</style>
</head>
<body>
  <h1>Findings Chart <span class="muted">v2</span></h1>
  <div class="subtitle">Static preview · /home/brad/Desktop/Practice/pbl</div>
  <div class="summary">
    <div class="metric"><div class="metric-label">Files scanned</div><div class="metric-value">12</div></div>
    <div class="metric"><div class="metric-label">Files with findings</div><div class="metric-value">7</div></div>
    <div class="metric"><div class="metric-label">Total findings</div><div class="metric-value">24</div></div>
    <div class="metric"><div class="metric-label">Rules triggered</div><div class="metric-value">3</div></div>
  </div>
  <h2>Severity classification</h2>
  <div class="classification">${classificationCards}</div>
  <div class="legend">Classes are static UI data for preview only. No scan or classification logic is connected.</div>
  <h2>Findings by file</h2>
  <div class="panel">${fileRows}</div>
</body>
</html>`;
}
