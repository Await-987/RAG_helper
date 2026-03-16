import { isValidKnowledgeBaseAssetPath } from './utils';

function normalizeLineEndings(content: string): string {
  return content.replace(/\r\n/g, '\n');
}

function stripInvisibleMathCharacters(content: string): string {
  return content.replace(/[\u200B-\u200D\u2060\uFEFF]/g, '');
}

function normalizeLatexDelimiters(content: string): string {
  return content
    .replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_match, expr: string) => `$$\n${expr.trim()}\n$$`)
    .replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_match, expr: string) => `$${expr.trim()}$`);
}

/**
 * Fix LaTeX formulas that were broken by newlines (LLM output issue).
 * Merges split formulas back into single-line format.
 */
function fixBrokenLatexNewlines(content: string): string {
  // Fix inline formulas broken by newline(s): $\frac{a}\nb$ -> $\frac{a}b$
  // This handles cases where LLM outputs formula with line break in the middle
  let result = content;

  // Repeatedly apply until no more matches (handles 3+ parts split by newlines)
  let prevResult = '';
  while (prevResult !== result) {
    prevResult = result;
    // Match: $opening part\nrest part$
    result = result.replace(/\$([^$\n]+)\n([^$\n]+)\$/g, (_match, p1, p2) => {
      return `$${p1.trim()}${p2.trim()}$`;
    });
  }

  return result;
}

/**
 * Protect unclosed LaTeX inline formulas from being rendered as errors.
 * Converts unclosed $...$ or $$...$$ to plain text to avoid KaTeX errors.
 */
function protectUnclosedLatex(content: string): string {
  // Count single $ delimiters (ignoring escaped \$ and $$)
  const singleDollarPositions: number[] = [];
  let i = 0;
  while (i < content.length) {
    // Skip escaped \$
    if (content[i] === '\\' && content[i + 1] === '$') {
      i += 2;
      continue;
    }
    // Skip $$ (block math)
    if (content[i] === '$' && content[i + 1] === '$') {
      i += 2;
      // Find closing $$
      const closePos = content.indexOf('$$', i);
      if (closePos === -1) {
        // Unclosed $$ - escape the opening
        // Just leave it as is, will be handled as incomplete
      } else {
        i = closePos + 2;
      }
      continue;
    }
    if (content[i] === '$') {
      singleDollarPositions.push(i);
    }
    i += 1;
  }

  // If odd number of single $, the last one is unclosed
  if (singleDollarPositions.length % 2 === 1) {
    const lastUnclosedPos = singleDollarPositions[singleDollarPositions.length - 1];
    // Find the matching opening $ before it
    const openingPos = singleDollarPositions[singleDollarPositions.length - 2];

    if (openingPos !== undefined) {
      // Extract the incomplete formula content
      const beforeFormula = content.slice(0, openingPos);
      const formulaContent = content.slice(openingPos + 1);

      // Escape the unclosed formula by replacing $ with \$
      const escapedContent = beforeFormula + '\\$' + formulaContent.replace(/\$/g, '\\$');
      return escapedContent;
    } else {
      // Only one $, escape it
      return content.slice(0, lastUnclosedPos) + '\\$' + content.slice(lastUnclosedPos + 1);
    }
  }

  return content;
}

function normalizeBareLatexBlocks(content: string): string {
  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.includes('$$') || trimmed.includes('$')) {
        return line;
      }

      const looksLikeLatexFormula =
        /\\(?:text|frac|sum|sqrt|times|cdot|left|right|mathrm|operatorname)\b/.test(trimmed) &&
        /[=+\-*/]/.test(trimmed);

      if (!looksLikeLatexFormula) {
        return line;
      }

      const leadingSpaces = line.match(/^\s*/)?.[0] ?? '';
      return `${leadingSpaces}$$\n${trimmed}\n$$`;
    })
    .join('\n');
}

function hasLatexCommand(value: string): boolean {
  return /\\(?:text|frac|sum|sqrt|times|cdot|left|right|mathrm|operatorname|sin|cos|tan|theta|phi|delta|alpha|beta|gamma|lambda|omega|sigma|pi)\b/.test(value);
}

function hasMathOperator(value: string): boolean {
  return /[=+\-*/^]|√|∑|∫|≈|≤|≥/.test(value);
}

function stripFormulaContinuationMarker(value: string): string {
  return value.replace(/^[•·●▪◦‣\-*]+\s*/, '').trim();
}

function stripMarkdownEmphasis(value: string): string {
  return value
    .replace(/^\*{1,3}\s*/, '')
    .replace(/\s*\*{1,3}$/, '')
    .replace(/^_{1,3}\s*/, '')
    .replace(/\s*_{1,3}$/, '')
    .trim();
}

function normalizeFormulaCandidate(value: string): string {
  return stripMarkdownEmphasis(stripFormulaContinuationMarker(value.trim()));
}

function looksLikeFormulaTail(value: string): boolean {
  return /^[)}\]}]+$/.test(value) ||
    /^(?:[)}\]}]+|\\(?:right|left)\b|[_^}{\\])/i.test(value) ||
    /(?:\\right[)\]}]|[)\]}])$/.test(value);
}

function hasLatexStructure(value: string): boolean {
  return /\\(?:frac|sqrt|left|right|mathrm|mathbf|mathcal|text|alpha|beta|gamma|delta|theta|phi|rho|mu|sigma|lambda|omega|sin|cos|tan|log|ln|quad|cdot|times)\b/.test(value) ||
    /[_^]\{[^}]+\}/.test(value) ||
    /[_^][A-Za-z0-9]/.test(value);
}

function hasBalancedDelimiters(value: string): boolean {
  const pairs: Record<string, string> = { '{': '}', '(': ')', '[': ']' };
  const closing = new Set(Object.values(pairs));
  const stack: string[] = [];

  for (let index = 0; index < value.length; index += 1) {
    const current = value[index];
    if (current === '\\') {
      index += 1;
      continue;
    }

    if (pairs[current]) {
      stack.push(pairs[current]);
      continue;
    }

    if (closing.has(current) && stack.length > 0 && stack[stack.length - 1] === current) {
      stack.pop();
    }
  }

  return stack.length === 0;
}

function hasSuspiciousLatexPattern(value: string): boolean {
  return /\\(?:mathrm|mathbf|mathcal|mathfrak|text)\{[^}]+\}\{[^}]+\}/.test(value) ||
    /\|\s+\|/.test(value) ||
    /\\left(?!.*\\right)|\\right(?!.*\\left)/.test(value);
}

function isRenderableLatexBlock(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }

  const strongSignals = /\\(?:frac|sqrt|left|right|mathrm|mathbf|mathcal|text|alpha|beta|gamma|delta|theta|phi|rho|mu|sigma|lambda|omega|sin|cos|tan|log|ln|quad|cdot|times)\b/.test(trimmed);
  if (!strongSignals) {
    return false;
  }

  if (!hasBalancedDelimiters(trimmed)) {
    return false;
  }

  if (hasSuspiciousLatexPattern(trimmed)) {
    return false;
  }

  return true;
}

function looksLikeStandaloneFormulaLine(line: string): boolean {
  const trimmed = normalizeFormulaCandidate(line);
  if (!trimmed || trimmed.includes('$$') || trimmed.includes('$')) {
    return false;
  }

  if (/^(其中|说明|注[:：]?|例如|比如|如下|定义|可得|因此|所以|来源[:：]?|应用场景[:：]?|参数说明[:：]?)/.test(trimmed)) {
    return false;
  }

  if (trimmed.length > 160) {
    return false;
  }

  if (/[，。；！？]/.test(trimmed) && !/\\text\{.*\}/.test(trimmed)) {
    return false;
  }

  return hasLatexStructure(trimmed) && (hasLatexCommand(trimmed) || hasMathOperator(trimmed));
}

function isFormulaFragmentLine(line: string): boolean {
  const trimmed = normalizeFormulaCandidate(line);
  if (!trimmed || trimmed.includes('$$') || trimmed.includes('$')) {
    return false;
  }

  if (/^(#{1,6}\s+|-{3,}|\d+\.\s+|- )/.test(trimmed)) {
    return false;
  }

  if (/^(其中|说明|注[:：]?|例如|比如|如下|定义|可得|因此|所以)/.test(trimmed)) {
    return false;
  }

  if (trimmed.length > 80) {
    return false;
  }

  if (/[，。；！？]/.test(trimmed) && !hasLatexCommand(trimmed)) {
    return false;
  }

  const symbolOnly = /^[A-Za-z0-9_'.(){}\[\]\\|,:%<>+\-*/=^~\s\u00B2\u00B3\u00B9\u2070-\u209F\u03B1-\u03C9\u0391-\u03A9\u4E00-\u9FFF]+$/.test(trimmed);
  const shortSymbolToken = symbolOnly && trimmed.length <= 16;

  return hasLatexCommand(trimmed) || hasMathOperator(trimmed) || shortSymbolToken || looksLikeFormulaTail(trimmed) || looksLikeStandaloneFormulaLine(trimmed);
}

function normalizeFormulaComparisonKey(value: string): string {
  return value.replace(/\s+/g, '').replace(/[(){}\[\]]/g, '').toLowerCase();
}

function mergeFormulaFragmentBlock(lines: string[]): string | null {
  const trimmedLines = lines
    .map((line) => normalizeFormulaCandidate(line))
    .filter(Boolean);
  if (trimmedLines.length < 2) {
    return null;
  }

  const hasStrongFormulaSignal = trimmedLines.some((line) => hasLatexCommand(line) || hasMathOperator(line));
  if (!hasStrongFormulaSignal && trimmedLines.length < 3) {
    return null;
  }

  const comparisonKeys = trimmedLines.map(normalizeFormulaComparisonKey);
  const deduped = trimmedLines.filter((line, index) => {
    const key = comparisonKeys[index];
    if (!key) {
      return false;
    }

    return !comparisonKeys.some((otherKey, otherIndex) => {
      if (otherIndex === index || otherKey.length <= key.length) {
        return false;
      }

      return otherKey.includes(key);
    });
  });

  const merged = deduped
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .join(' ')
    .replace(/\s*([=+\-*/^])\s*/g, ' $1 ')
    .replace(/\s+([)\]}])/g, '$1')
    .replace(/([({\[])\s+/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();

  return merged.length > 0 && isRenderableLatexBlock(merged) ? merged : null;
}

function normalizeStandaloneFormulaParagraphs(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];
  let buffer: string[] = [];

  const flushBuffer = () => {
    if (buffer.length === 0) {
      return;
    }

    const merged = mergeFormulaFragmentBlock(buffer);
    if (merged && buffer.some((line) => looksLikeStandaloneFormulaLine(line))) {
      output.push('$$', merged, '$$');
    } else {
      output.push(...buffer);
    }
    buffer = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed === '') {
      if (buffer.length > 0) {
        const nextNonEmpty = lines.slice(index + 1).find((candidate) => candidate.trim().length > 0);
        if (nextNonEmpty && looksLikeStandaloneFormulaLine(nextNonEmpty)) {
          continue;
        }
      }
      flushBuffer();
      output.push(line);
      continue;
    }

    if (looksLikeStandaloneFormulaLine(line) || (buffer.length > 0 && isFormulaFragmentLine(line))) {
      buffer.push(line);
      continue;
    }

    flushBuffer();
    output.push(line);
  }

  flushBuffer();
  return output.join('\n');
}

function normalizeFragmentedFormulaBlocks(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];
  let buffer: string[] = [];
  let pendingBlankLines = 0;

  const flushBuffer = () => {
    if (buffer.length === 0) {
      pendingBlankLines = 0;
      return;
    }

    const merged = mergeFormulaFragmentBlock(buffer);
    if (merged) {
      output.push('$$', merged, '$$');
    } else {
      output.push(...buffer);
    }

    buffer = [];
    pendingBlankLines = 0;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (isFormulaFragmentLine(line)) {
      if (pendingBlankLines > 0 && buffer.length > 0) {
        pendingBlankLines = 0;
      }
      buffer.push(line);
      continue;
    }

    if (line.trim() === '' && buffer.length > 0) {
      const nextNonEmptyLine = lines
        .slice(index + 1)
        .find((candidate) => candidate.trim().length > 0);

      if (nextNonEmptyLine && isFormulaFragmentLine(nextNonEmptyLine) && pendingBlankLines < 1) {
        pendingBlankLines += 1;
        continue;
      }
    }

    flushBuffer();
    output.push(line);
  }

  flushBuffer();
  return output.join('\n');
}

function normalizeFormulaContinuationBlocks(content: string): string {
  const lines = content.split('\n');
  const output: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const current = lines[index];
    const trimmed = current.trim();

    if (!trimmed || trimmed.includes('$$')) {
      output.push(current);
      continue;
    }

    const isFormulaStart =
      /[=]/.test(trimmed) &&
      (hasLatexCommand(trimmed) || /\\frac\b/.test(trimmed) || /[_^]{/.test(trimmed));

    if (!isFormulaStart) {
      output.push(current);
      continue;
    }

    const block = [trimmed];
    let nextIndex = index + 1;

    while (nextIndex < lines.length) {
      const candidate = lines[nextIndex].trim();
      if (!candidate) {
        nextIndex += 1;
        continue;
      }

      if (/^(来源|说明|注[:：]?|同上文件|同上文档)/.test(candidate)) {
        break;
      }

      const normalizedCandidate = normalizeFormulaCandidate(candidate);
      if (!isFormulaFragmentLine(normalizedCandidate)) {
        break;
      }

      block.push(normalizedCandidate);
      nextIndex += 1;
    }

    if (block.length > 1) {
      const merged = mergeFormulaFragmentBlock(block);
      if (merged) {
        output.push('$$', merged, '$$');
        index = nextIndex - 1;
        continue;
      }
    }

    output.push(current);
  }

  return output.join('\n');
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

function normalizeHardSectionBreaks(content: string): string {
  return content
    .replace(/\s+---+\s+/g, '\n\n<hr />\n\n')
    .replace(/(<\/(?:div|table|blockquote|pre)>)\s*<hr \/>/gi, '$1\n\n<hr />')
    .replace(/<hr \/>\s*(#{1,6}\s+)/gi, '<hr />\n\n$1');
}

function normalizeInlineBlockMarkers(content: string): string {
  return content
    .replace(/([^\n])\s+(#{1,6}\s+)/g, '$1\n\n$2')
    .replace(/([^\n])\s+(-\s+\*\*[^*\n]+\*\*:)/g, '$1\n$2')
    .replace(/([^\n])\s+(\d+\.\s+\*\*[^*\n]+\*\*)/g, '$1\n\n$2')
    .replace(/([^\n])\s+(\d+\.\s+)/g, '$1\n$2')
    .replace(/([^\n])\s+(-\s+)/g, '$1\n$2')
    .replace(/([。；;：:）)])\s*(#{1,6}\s+)/g, '$1\n\n$2')
    .replace(/([。；;：:）)])\s*(\d+\.\s+)/g, '$1\n$2');
}

function cleanupEmptyImageLeadIns(content: string): string {
  return content
    .replace(/（([^（）\n]*?(?:图片链接|见图|见图片)[^（）\n]*?)：\s*）/g, '（$1）')
    .replace(/\(([^()\n]*?(?:image|图片链接)[^()\n]*?):\s*\)/gi, '($1)');
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

export type ChatContentBlock =
  | { type: 'markdown'; content: string }
  | { type: 'math'; content: string }
  | { type: 'table'; content: string }
  | { type: 'code'; content: string };

const bareKnowledgeBaseImagePattern =
  /(?:^|[\s(（\[:：,，])(mineru_output\/[^\s)）\]】>]+?\.(?:png|jpe?g|gif|webp)|data\/stored_files\/[^\s)）\]】>]+?\.(?:png|jpe?g|gif|webp))(?=$|[\s)）\]】>,.!?，。；;:：])/gim;
const inlineCodeImagePattern =
  /`(mineru_output\/[^`\s]+?\.(?:png|jpe?g|gif|webp)|data\/stored_files\/[^`\s]+?\.(?:png|jpe?g|gif|webp))`/gim;

export function extractImageReferences(content: string): ExtractedImageReference[] {
  const results: ExtractedImageReference[] = [];
  const seen = new Set<string>();

  const markdownImagePattern = /!\[([^\]]*)]\(([^)]+)\)/g;
  for (const match of content.matchAll(markdownImagePattern)) {
    const alt = match[1]?.trim() ?? '';
    const src = match[2]?.trim() ?? '';
    if (!isValidKnowledgeBaseAssetPath(src) || seen.has(src)) {
      continue;
    }
    seen.add(src);
    results.push({ alt, src });
  }

  const htmlImagePattern = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi;
  for (const match of content.matchAll(htmlImagePattern)) {
    const src = match[1]?.trim() ?? '';
    if (!isValidKnowledgeBaseAssetPath(src) || seen.has(src)) {
      continue;
    }
    seen.add(src);
    results.push({ alt: '', src });
  }

  for (const match of content.matchAll(bareKnowledgeBaseImagePattern)) {
    const src = match[1]?.trim() ?? '';
    if (!isValidKnowledgeBaseAssetPath(src) || seen.has(src)) {
      continue;
    }
    seen.add(src);
    results.push({ alt: '', src });
  }

  for (const match of content.matchAll(inlineCodeImagePattern)) {
    const src = match[1]?.trim() ?? '';
    if (!isValidKnowledgeBaseAssetPath(src) || seen.has(src)) {
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
    .replace(inlineCodeImagePattern, '')
    .replace(bareKnowledgeBaseImagePattern, (_match, src: string) => {
      return isValidKnowledgeBaseAssetPath(src) ? _match.replace(src, '').trimEnd() : '';
    })
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function normalizeChatMarkdown(content: string): string {
  let normalized = normalizeLineEndings(content);
  normalized = stripInvisibleMathCharacters(normalized);
  normalized = fixBrokenLatexNewlines(normalized);
  normalized = protectUnclosedLatex(normalized);
  normalized = normalizeLatexDelimiters(normalized);
  normalized = normalizeFormulaContinuationBlocks(normalized);
  normalized = normalizeStandaloneFormulaParagraphs(normalized);
  normalized = normalizeFragmentedFormulaBlocks(normalized);
  normalized = normalizeBareLatexBlocks(normalized);
  normalized = trimTrailingSpaces(normalized);
  normalized = removeCommonIndentation(normalized);
  normalized = cleanupEmptyImageLeadIns(normalized);
  normalized = normalizeHardSectionBreaks(normalized);
  normalized = collapseBlankLinesInsideTables(normalized);
  normalized = normalizeMarkdownImages(normalized);
  normalized = normalizeHtmlImages(normalized);
  normalized = normalizeMarkdownTables(normalized);
  normalized = normalizeHtmlTableBlocks(normalized);
  normalized = normalizeInlineBlockMarkers(normalized);
  normalized = normalizeBlockBoundaries(normalized);
  normalized = normalizeInterruptedTables(normalized);
  normalized = normalizeLooseTableBlocks(normalized);
  normalized = convertPipeTablesToHtml(normalized);
  return normalized.trim();
}

export function parseChatContentBlocks(content: string): ChatContentBlock[] {
  const normalized = normalizeChatMarkdown(content);
  if (!normalized) {
    return [];
  }

  const lines = normalized.split('\n');
  const blocks: ChatContentBlock[] = [];
  let markdownBuffer: string[] = [];

  const flushMarkdown = () => {
    const markdown = markdownBuffer.join('\n').trim();
    if (markdown) {
      blocks.push({ type: 'markdown', content: markdown });
    }
    markdownBuffer = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (/^```/.test(trimmed)) {
      flushMarkdown();
      const codeLines = [line];
      index += 1;

      while (index < lines.length) {
        codeLines.push(lines[index]);
        if (/^```/.test(lines[index].trim())) {
          break;
        }
        index += 1;
      }

      blocks.push({ type: 'code', content: codeLines.join('\n') });
      continue;
    }

    if (trimmed === '$$') {
      flushMarkdown();
      const mathLines: string[] = [];
      index += 1;

      while (index < lines.length && lines[index].trim() !== '$$') {
        mathLines.push(lines[index]);
        index += 1;
      }

      const mathContent = mathLines.join('\n').trim();
      if (mathContent) {
        blocks.push({ type: 'math', content: mathContent });
      }
      continue;
    }

    if (/^<table[\s>]/i.test(trimmed)) {
      flushMarkdown();
      const tableLines = [line];
      while (index + 1 < lines.length && !/<\/table>/i.test(tableLines[tableLines.length - 1])) {
        index += 1;
        tableLines.push(lines[index]);
      }
      blocks.push({ type: 'table', content: tableLines.join('\n') });
      continue;
    }

    markdownBuffer.push(line);
  }

  flushMarkdown();
  return blocks;
}
