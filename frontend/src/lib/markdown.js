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

/**
 * Returns a block list:
 *   {type:'heading', level, tokens}
 *   {type:'paragraph', tokens}
 *   {type:'list', ordered:boolean, items:Array<Array<token>>}
 */
export function parseBlocks(text) {
  if (typeof text !== 'string' || text.trim() === '') return []

  const chunks = text.replace(/\r\n/g, '\n').split(/\n{2,}/)
  const blocks = []

  for (const chunk of chunks) {
    const lines = chunk
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line !== '')

    if (lines.length === 0) continue

    const heading = lines[0].match(HEADING)
    if (heading && lines.length === 1) {
      blocks.push({
        type: 'heading',
        level: Math.min(heading[1].length, 4),
        tokens: parseInline(heading[2]),
      })
      continue
    }

    const bulletLines = lines.map((line) => line.match(BULLET))
    if (bulletLines.every((m) => m !== null)) {
      blocks.push({
        type: 'list',
        ordered: false,
        items: bulletLines.map((m) => parseInline(m[1])),
      })
      continue
    }

    const orderedLines = lines.map((line) => line.match(ORDERED))
    if (orderedLines.every((m) => m !== null)) {
      blocks.push({
        type: 'list',
        ordered: true,
        items: orderedLines.map((m) => parseInline(m[1])),
      })
      continue
    }

    blocks.push({ type: 'paragraph', tokens: parseInline(lines.join(' ')) })
  }

  return blocks
}