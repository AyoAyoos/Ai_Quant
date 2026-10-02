import { Fragment } from 'react'
import { parseBlocks } from '../lib/markdown.js'

function InlineTokens({ tokens }) {
  return tokens.map((token, index) => {
    if (token.type === 'strong') return <strong key={index}>{token.value}</strong>
    if (token.type === 'code') return <code key={index}>{token.value}</code>
    return <Fragment key={index}>{token.value}</Fragment>
  })
}

/**
 * Markdown-lite renderer: paragraphs, headings, bullet/ordered lists, bold and
 * inline code. Every token becomes a real React node, so assistant output is
 * never interpreted as markup.
 */
export default function Markdown({ text, small = false }) {
  const blocks = parseBlocks(text)
  if (blocks.length === 0) return null

  return (
    <div className={`prose${small ? ' prose--sm' : ''}`}>
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const Tag = block.level <= 3 ? 'h3' : 'h4'
          return <Tag key={index}><InlineTokens tokens={block.tokens} /></Tag>
        }

        if (block.type === 'list') {
          const ListTag = block.ordered ? 'ol' : 'ul'
          return (
            <ListTag key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineTokens tokens={item} />
                </li>
              ))}
            </ListTag>
          )
        }

        return (
          <p key={index}>
            <InlineTokens tokens={block.tokens} />
          </p>
        )
      })}
    </div>
  )
}