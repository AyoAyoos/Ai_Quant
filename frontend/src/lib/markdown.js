/**
 * Markdown-lite parser for assistant prose.
 *
 * Deliberately tiny and deliberately pure: it returns a plain AST that
 * components render with real React elements. There is no
 * dangerouslySetInnerHTML anywhere, so LLM output can never inject markup.
 *
 * Supported: blank-line separated blocks, "## / ###" headings, "- / * / +"
 * bullet lists, "1." ordered lists, **bold**, and `inline code`.
 */

const INLINE_SPLIT = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g

/** Returns [{type:'text'|'strong'|'code', value}] for one line of prose. */
export function parseInline(text) {
  if (typeof text !== 'string' || text === '') return []
  const tokens = []
  let lastIndex = 0
  for (const match of text.matchAll(INLINE_SPLIT)) {
    const [raw, group] = match
    const start = match.index ?? 0
    if (start > lastIndex) {
      tokens.push({ type: 'text', value: text.slice(lastIndex, start) })
    }
    if (group.startsWith('**')) {
      tokens.push({ type: 'strong', value: group.slice(2, -2) })
    } else {
      tokens.push({ type: 'code', value: group.slice(1, -1) })
    }
    lastIndex = start + raw.length
  }
  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }
  return tokens
}

const BULLET = /^[-*+]\s+(.*)$/
const ORDERED = /^\d+[.)]\s+(.*)$/
const HEADING = /^(#{1,6})\s+(.*)$/
const FENCE = /^```(\w*)\s*$/
const TABLE_SEP = /^\|?[\s:|-]+\|?[\s:|.-]*$/

function isTableSeparator(line) {
  if (!TABLE_SEP.test(line.trim())) return false
  // A separator row must contain at least three dashes/colons/pipes.
  return /---/.test(line) || /:--/.test(line)
}

function splitRow(line) {
  let cells = line.trim()
  if (cells.startsWith('|')) cells = cells.slice(1)
  if (cells.endsWith('|')) cells = cells.slice(0, -1)
  return cells.split('|').map((cell) => cell.trim())
}

/**
 * Returns a block list:
 *   {type:'heading', level, tokens}
 *   {type:'paragraph', tokens}
 *   {type:'list', ordered:boolean, items:Array<Array<token>>}
 *   {type:'code', language, value}
 *   {type:'table', head:Array<Array<token>>, rows:Array<Array<Array<token>>>}
 */
export function parseBlocks(text) {
  if (typeof text !== 'string' || text.trim() === '') return []

  const normalized = text.replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  const blocks = []
  let i = 0

  while (i < lines.length) {
    // Fenced code block: ```lang ... ```
    const fence = lines[i].trim().match(FENCE)
    if (fence) {
      const language = fence[1] || ''
      i += 1
      const codeLines = []
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
        codeLines.push(lines[i])
        i += 1
      }
      i += 1 // consume closing fence (or run off the end)
      blocks.push({ type: 'code', language, value: codeLines.join('\n') })
      continue
    }

    // Pipe table: header row + separator row + body rows.
    if (
      lines[i].includes('|') &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const head = splitRow(lines[i])
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim() !== '' && lines[i].includes('|')) {
        rows.push(splitRow(lines[i]))
        i += 1
      }
      blocks.push({
        type: 'table',
        head: head.map((cell) => parseInline(cell)),
        rows: rows.map((row) => row.map((cell) => parseInline(cell))),
      })
      continue
    }

    // Blank line: block boundary.
    if (lines[i].trim() === '') {
      i += 1
      continue
    }

    // Gather a blank-line-delimited chunk for heading / list / paragraph.
    const chunkLines = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].trim().match(FENCE)
    ) {
      // Stop before a table header so the table branch above can claim it.
      if (
        lines[i].includes('|') &&
        i + 1 < lines.length &&
        isTableSeparator(lines[i + 1])
      ) {
        break
      }
      chunkLines.push(lines[i])
      i += 1
    }

    const trimmed = chunkLines.map((line) => line.trim()).filter((line) => line !== '')
    if (trimmed.length === 0) continue

    const heading = trimmed[0].match(HEADING)
    if (heading && trimmed.length === 1) {
      blocks.push({
        type: 'heading',
        level: Math.min(heading[1].length, 4),
        tokens: parseInline(heading[2]),
      })
      continue
    }

    const bulletLines = trimmed.map((line) => line.match(BULLET))
    if (bulletLines.every((m) => m !== null)) {
      blocks.push({
        type: 'list',
        ordered: false,
        items: bulletLines.map((m) => parseInline(m[1])),
      })
      continue
    }

    const orderedLines = trimmed.map((line) => line.match(ORDERED))
    if (orderedLines.every((m) => m !== null)) {
      blocks.push({
        type: 'list',
        ordered: true,
        items: orderedLines.map((m) => parseInline(m[1])),
      })
      continue
    }

    blocks.push({ type: 'paragraph', tokens: parseInline(trimmed.join(' ')) })
  }

  return blocks
}