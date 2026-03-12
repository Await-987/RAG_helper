function normalizeLineEndings(content: string): string {
  return content.replace(/\r\n/g, '\n');
}

function trimTrailingSpaces(content: string): string {
  return content
    .split('\n')
    .map((line) => line.replace(/[ \t]+$/g, ''))
    .join('\n');
}

function removeCommonIndentation(content: string): string {
  const lines = content.split('\n');
  const indents = lines
    .filter((line) => line.trim().length > 0)
    .map((line) => (line.match(/^ +/)?.[0].length ?? 0));

  const commonIndent = indents.length > 0 ? Math.min(...indents) : 0;
  if (commonIndent === 0) {
    return content;
  }

  return lines.map((line) => line.slice(commonIndent)).join('\n');
}

function normalizeMarkdownTables(content: string): string {
  return content
    .split('\n')
    .map((line) =>
      line
        .replace(/｜/g, '|')
        .replace(/\\\|/g, '|')
        .replace(/\u00a0/g, ' ')
    )
    .join('\n');
}

function isTableRow(line: string): boolean {
  return /^\|.*\|$/.test(line) || /^[^|\n]+(\|[^|\n]+){2,}$/.test(line);
}

function isTableSeparator(line: string): boolean {
  const normalized = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  const cells = normalized.split('|').map((cell) => cell.trim()).filter(Boolean);

  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isMarkdownImageLine(line: string): boolean {
  return /^!\[[^\]]*]\([^)]+\)$/.test(line);
}

function normalizeLooseTableBlocks(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];
  let buffer: string[] = [];

  const flushBuffer = () => {
    if (buffer.length > 0) {
      output.push('');
      output.push(...buffer);
      output.push('');
      buffer = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const isPipeLikeRow = isTableRow(line);

    if (isPipeLikeRow) {
      const normalizedRow = line.startsWith('|') ? line : `| ${line} |`;
      buffer.push(normalizedRow);
      continue;
    }

    flushBuffer();
    output.push(rawLine);
  }

  flushBuffer();
  return output.join('\n');
}

function collapseBlankLinesInsideTables(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    const current = lines[i]?.trim() ?? '';
    const prev = output.length > 0 ? output[output.length - 1].trim() : '';
    const next = lines[i + 1]?.trim() ?? '';

    const prevIsTableRow = isTableRow(prev);
    const nextIsTableRow = isTableRow(next);

    if (current === '' && prevIsTableRow && nextIsTableRow) {
      continue;
    }

    output.push(lines[i]);
  }

  return output.join('\n');
}

function normalizeInterruptedTables(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];

  let i = 0;
  while (i < lines.length) {
    const headerLine = lines[i]?.trim() ?? '';
    const separatorLine = lines[i + 1]?.trim() ?? '';

    if (!isTableRow(headerLine) || !isTableSeparator(separatorLine)) {
      output.push(lines[i]);
      i += 1;
      continue;
    }

    const tableLines = [lines[i], lines[i + 1]];
    const trailingArtifacts: string[] = [];
    let j = i + 2;

    while (j < lines.length) {
      const rawLine = lines[j];
      const line = rawLine?.trim() ?? '';

      if (line === '') {
        j += 1;
        continue;
      }

      if (isTableRow(line)) {
        tableLines.push(line.startsWith('|') ? rawLine : `| ${line} |`);
        j += 1;
        continue;
      }

      if (isMarkdownImageLine(line)) {
        trailingArtifacts.push(rawLine);
        j += 1;
        continue;
      }

      break;
    }

    output.push(...tableLines);

    if (trailingArtifacts.length > 0) {
      output.push('', ...trailingArtifacts);
    }

    i = j;
  }

  return output.join('\n');
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function convertPipeTablesToHtml(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];

  const parseRow = (row: string) =>
    row
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim());

  let i = 0;
  while (i < lines.length) {
    const headerLine = lines[i]?.trim() ?? '';
    const separatorLine = lines[i + 1]?.trim() ?? '';

    const isHeader = isTableRow(headerLine);
    const isSeparator = isTableSeparator(separatorLine);

    if (!isHeader || !isSeparator) {
      output.push(lines[i]);
      i += 1;
      continue;
    }

    const headerCells = parseRow(headerLine);
    const bodyRows: string[][] = [];
    const deferredArtifacts: string[] = [];
    let j = i + 2;

    while (j < lines.length) {
      const row = lines[j]?.trim() ?? '';

      if (row === '') {
        j += 1;
        continue;
      }

      if (isMarkdownImageLine(row)) {
        deferredArtifacts.push(lines[j]);
        j += 1;
        continue;
      }

      if (!isTableRow(row)) {
        break;
      }

      bodyRows.push(parseRow(row));
      j += 1;
    }

    const thead = `<thead><tr>${headerCells
      .map((cell) => `<th>${escapeHtml(cell)}</th>`)
      .join('')}</tr></thead>`;
    const tbody = `<tbody>${bodyRows
      .map(
        (row) =>
          `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`
      )
      .join('')}</tbody>`;

    output.push(`<table>${thead}${tbody}</table>`);
    if (deferredArtifacts.length > 0) {
      output.push('', ...deferredArtifacts);
    }
    i = j;
  }

  return output.join('\n');
}

function normalizeMarkdownImages(content: string): string {
  return content.replace(/^[ \t]+(!\[[^\]]*]\([^)]+\))/gm, '$1');
}

function normalizeHtmlImages(content: string): string {
  return content.replace(/<img\b[\s\S]*?>/gi, (match) => `\n\n${match.trim()}\n\n`);
}

function normalizeHtmlTableBlocks(content: string): string {
  return content.replace(/<table[\s\S]*?<\/table>/gi, (match) => {
    const normalizedBlock = match
      .split('\n')
      .map((line) => line.trim())
      .join('\n');

    return `\n\n${normalizedBlock}\n\n`;
  });
}

function normalizeBlockBoundaries(content: string): string {
  return content
    .replace(/(<\/table>)\s*(#{1,6}\s+)/gi, '$1\n\n$2')
    .replace(/(<\/table>)\s*(\d+\.\s+)/gi, '$1\n\n$2')
    .replace(/(<\/table>)\s*([^\n<])/gi, '$1\n\n$2')
    .replace(/(#{1,6}\s[^\n]+)\n(?!\n)(\d+\.\s+)/g, '$1\n\n$2')
    .replace(/([^\n])\n(#{1,6}\s+)/g, '$1\n\n$2')
    .replace(/([^\n])\n(\d+\.\s+)/g, '$1\n\n$2');
}

export interface ExtractedImageReference {
  alt: string;
  src: string;
}

export function extractImageReferences(content: string): ExtractedImageReference[] {
  const results: ExtractedImageReference[] = [];
  const seen = new Set<string>();

  const markdownImagePattern = /!\[([^\]]*)]\(([^)]+)\)/g;
  for (const match of content.matchAll(markdownImagePattern)) {
    const alt = match[1]?.trim() ?? '';
    const src = match[2]?.trim() ?? '';
    if (!src || seen.has(src)) {
      continue;
    }
    seen.add(src);
    results.push({ alt, src });
  }

  const htmlImagePattern = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  for (const match of content.matchAll(htmlImagePattern)) {
    const src = match[1]?.trim() ?? '';
    if (!src || seen.has(src)) {
      continue;
    }
    seen.add(src);
    results.push({ alt: '', src });
  }

  return results;
}

export function stripImageReferences(content: string): string {
  return content
    .replace(/!\[[^\]]*]\([^)]+\)/g, '')
    .replace(/<img\b[^>]*\bsrc=["'][^"']+["'][^>]*>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function normalizeChatMarkdown(content: string): string {
  let normalized = normalizeLineEndings(content);
  normalized = trimTrailingSpaces(normalized);
  normalized = removeCommonIndentation(normalized);
  normalized = collapseBlankLinesInsideTables(normalized);
  normalized = normalizeMarkdownImages(normalized);
  normalized = normalizeHtmlImages(normalized);
  normalized = normalizeMarkdownTables(normalized);
  normalized = normalizeHtmlTableBlocks(normalized);
  normalized = normalizeBlockBoundaries(normalized);
  normalized = normalizeInterruptedTables(normalized);
  normalized = normalizeLooseTableBlocks(normalized);
  normalized = convertPipeTablesToHtml(normalized);
  return normalized.trim();
}
