import { Fragment, useState } from 'react'
import { parseBlocks } from '../lib/markdown.js'

function InlineTokens({ tokens }) {
  return tokens.map((token, index) => {
    if (token.type === 'strong') return <strong key={index}>{token.value}</strong>
    if (token.type === 'code') return <code key={index}>{token.value}</code>
    return <Fragment key={index}>{token.value}</Fragment>
  })
}

/**
 * Tiny dependency-free tokenizer for fenced code (Python-flavoured).
 * Runs on plain text and returns React nodes, so highlighted output can
 * never inject markup. Group order matters: comments and strings win over
 * keywords, keywords win over plain identifiers.
 */
const CODE_TOKEN_RE =
  /(#[^\n]*)|((?:[rRbBfFuU]{0,2})?(?:'''(?:[^\\]|\\[\s\S])*?'''|"""(?:[^\\]|\\[\s\S])*?"""|'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"))|\b(\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?j?)\b|\b(class|def|import|from|if|elif|else|return|for|while|with|as|try|except|finally|raise|pass|break|continue|lambda|yield|assert|del|global|nonlocal|in|is|not|and|or|None|True|False)\b|\b(print|len|range|str|int|float|bool|list|dict|set|tuple|super|isinstance|issubclass|enumerate|zip|map|filter|open|abs|min|max|sum|round|sorted|reversed|any|all|Exception|ValueError|TypeError|KeyError|IndexError)\b|([A-Za-z_]\w*)(?=\s*\()/g

function highlightCode(code) {
  if (!code) return null
  const nodes = []
  let lastIndex = 0
  let key = 0
  CODE_TOKEN_RE.lastIndex = 0
  let match
  while ((match = CODE_TOKEN_RE.exec(code)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        <Fragment key={key++}>{code.slice(lastIndex, match.index)}</Fragment>,
      )
    }
    const [full, comment, string, number, keyword, builtin, func] = match
    if (comment) {
      nodes.push(
        <span key={key++} className="tok-com">
          {full}
        </span>,
      )
    } else if (string || number) {
      nodes.push(
        <span key={key++} className="tok-str">
          {full}
        </span>,
      )
    } else if (keyword || builtin) {
      nodes.push(
        <span key={key++} className="tok-kw">
          {full}
        </span>,
      )
    } else if (func) {
      nodes.push(
        <span key={key++} className="tok-fn">
          {full}
        </span>,
      )
    } else {
      nodes.push(<Fragment key={key++}>{full}</Fragment>)
    }
    lastIndex = match.index + full.length
    // Guard against zero-length matches looping forever.
    if (CODE_TOKEN_RE.lastIndex === match.index) CODE_TOKEN_RE.lastIndex += 1
  }
  if (lastIndex < code.length) {
    nodes.push(<Fragment key={key++}>{code.slice(lastIndex)}</Fragment>)
  }
  return nodes
}

function CodeBlock({ code, language }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
    } catch {
      // Clipboard API needs a secure context: fall back to execCommand.
      const ta = document.createElement('textarea')
      ta.value = code
      ta.setAttribute('readonly', '')
      ta.style.position = 'absolute'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
      } catch {
        /* copying is best-effort; still show feedback */
      }
      ta.remove()
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="md-code">
      <div className="md-code__bar">
        <span className="md-code__lang">{language || 'code'}</span>
        <button
          type="button"
          className="md-code__copy"
          onClick={copy}
          aria-live="polite"
          aria-label={copied ? 'Code copied' : 'Copy code to clipboard'}
        >
          {copied ? (
            <Fragment>
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                <path
                  d="M4 12.5 9.5 18 20 6.5"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Copied!</span>
            </Fragment>
          ) : (
            <Fragment>
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" aria-hidden="true">
                <rect x="9" y="9" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="2" />
                <path
                  d="M5 15V5a2 2 0 0 1 2-2h10"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
              <span>Copy code</span>
            </Fragment>
          )}
        </button>
      </div>
      <pre className="md-code__pre">
        <code>{highlightCode(code)}</code>
      </pre>
    </div>
  )
}

/**
 * Markdown-lite renderer: paragraphs, headings, bullet/ordered lists, bold,
 * inline code, fenced code blocks and pipe tables. Every token becomes a real
 * React node, so assistant output is never interpreted as markup.
 *
 * Fenced code renders through CodeBlock: a lightweight Python-flavoured
 * tokenizer plus a copy-to-clipboard header. No external highlighter.
 */
export default function Markdown({ text, small = false }) {
  const blocks = parseBlocks(text)
  if (blocks.length === 0) return null

  return (
    <div className={`prose${small ? ' prose--sm' : ''}`}>
      {blocks.map((block, index) => {
        if (block.type === 'code') {
          return <CodeBlock key={index} code={block.value} language={block.language} />
        }

        if (block.type === 'table') {
          return (
            <div key={index} className="md-table-wrap">
              <table className="md-table">
                <thead>
                  <tr>
                    {block.head.map((cell, cellIndex) => (
                      <th key={cellIndex}>
                        <InlineTokens tokens={cell} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex}>
                          <InlineTokens tokens={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }

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