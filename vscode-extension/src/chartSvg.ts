import { ScanFileEntry, ScanResult } from './projectScan';

const SEVERITIES = ['error', 'warning', 'info', 'hint'] as const;
type Sev = typeof SEVERITIES[number];

const SEV_COLOR: Record<Sev, string> = {
  error:   '#d73a49',
  warning: '#d29922',
  info:    '#1976d2',
  hint:    '#6a737d',
};

const PAD = 24;
const LEFT_W = 280;
const TOP_H = 44;
const ROW_H = 38;
const COL_W = 100;
const MIN_R = 5;
const MAX_R = 16;

export interface ChartData {
  svg: string;
  width: number;
  height: number;
}

function escapeXml(s: string): string {
  return s.replace(/[<>&"']/g, (c) => {
    switch (c) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case '"': return '&quot;';
      case "'": return '&apos;';
      default:  return c;
    }
  });
}

function truncatePath(p: string, maxChars: number): string {
  if (p.length <= maxChars) return p;
  return '…' + p.slice(-(maxChars - 1));
}

function firstLineForSeverity(entry: ScanFileEntry, sev: Sev): number | null {
  for (const f of entry.findings) {
    if (f.severity === sev) return f.line;
  }
  return null;
}

function radiusFor(count: number): number {
  return Math.min(MAX_R, MIN_R + Math.sqrt(count) * 4);
}

export function renderChartSvg(result: ScanResult): ChartData {
  const entries = [...result.by_file].sort((a, b) => {
    const ta = a.findings.length;
    const tb = b.findings.length;
    if (tb !== ta) return tb - ta;
    return a.path.localeCompare(b.path);
  });

  const rows = entries.length;
  const width = PAD * 2 + LEFT_W + SEVERITIES.length * COL_W;
  const height = PAD * 2 + TOP_H + rows * ROW_H + 8;

  const parts: string[] = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" ` +
    `width="${width}" height="${height}" role="img" ` +
    `aria-label="Findings per file by severity">`
  );

  // Column headers
  SEVERITIES.forEach((sev, i) => {
    const x = PAD + LEFT_W + i * COL_W + COL_W / 2;
    const y = PAD + TOP_H - 16;
    parts.push(
      `<text x="${x}" y="${y}" text-anchor="middle" class="hdr">${sev}</text>`
    );
  });

  // Rows
  entries.forEach((entry, ri) => {
    const rowY = PAD + TOP_H + ri * ROW_H + ROW_H / 2;

    if (ri % 2 === 0) {
      parts.push(
        `<rect x="${PAD}" y="${PAD + TOP_H + ri * ROW_H}" ` +
        `width="${LEFT_W + SEVERITIES.length * COL_W}" height="${ROW_H}" ` +
        `class="rowAlt"/>`
      );
    }

    const label = truncatePath(entry.path, 38);
    parts.push(
      `<text x="${PAD + LEFT_W - 12}" y="${rowY + 4}" ` +
      `text-anchor="end" class="lbl">${escapeXml(label)}` +
      `<title>${escapeXml(entry.path)}</title></text>`
    );

    SEVERITIES.forEach((sev, ci) => {
      const count = entry.counts[sev] ?? 0;
      if (count === 0) return;
      const x = PAD + LEFT_W + ci * COL_W + COL_W / 2;
      const r = radiusFor(count);
      const line = firstLineForSeverity(entry, sev) ?? 1;
      const tooltip = `${entry.path}\n${count} ${sev}\nfirst at line ${line}`;
      parts.push(
        `<circle cx="${x}" cy="${rowY}" r="${r}" fill="${SEV_COLOR[sev]}" ` +
        `data-path="${escapeXml(entry.path)}" ` +
        `data-line="${line}" data-sev="${sev}" class="bubble">` +
        `<title>${escapeXml(tooltip)}</title>` +
        `</circle>`
      );
      if (r >= 10) {
        parts.push(
          `<text x="${x}" y="${rowY + 4}" text-anchor="middle" class="cnt">${count}</text>`
        );
      }
    });
  });

  parts.push(`</svg>`);
  return { svg: parts.join(''), width, height };
}
