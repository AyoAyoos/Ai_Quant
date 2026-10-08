import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CHAT_TIMEOUT_MS, postChat } from '../lib/api.js'
import { clearThread, readThread, registerStrategy, writeThread } from '../lib/storage.js'
import { formatElapsed } from '../lib/format.js'
import { useElapsedTimer } from '../lib/useElapsedTimer.js'
import Markdown from '../components/Markdown.jsx'
import Note from '../components/Note.jsx'
import StrategyMiniCard from '../components/StrategyMiniCard.jsx'

const EXAMPLES = [
  {
    title: 'Vague idea — the assistant should ask',
    text: 'Starts with a bare indicator mention so the assistant asks about timeframe, thresholds and sizing instead of writing code.',
    content: 'I want to build a mean reversion strategy using the RSI indicator.',
  },
  {
    title: 'Fully specified — should finalize immediately',
    text: 'Names the indicator, the period, the deviation, the exit rule and the position size, then says finalize.',
    content:
      'Write a complete Backtrader strategy using a Bollinger Bands breakout. Go long when the price closes above the upper band, and exit when it crosses below the middle band. Use a 20-day period and 2 standard deviations for the bands, and invest 10% of portfolio cash per trade. I have no more requirements, please finalize the code.',
  },
  {
    title: 'Two indicators combined',
    text: 'Checks the strategy handles multi-indicator conditions without breaking the output format.',
    content:
      'I need a trend-following Backtrader script. The rules are: only take long trades if the current close is above the 200-day SMA AND the 14-period RSI drops below 30. Exit the position when the RSI crosses above 70. Please finalize the code.',
  },
  {
    title: 'Start a conversation, refine later',
    text: 'Opens a thread. Answer the follow-up questions to finish the strategy inside the same conversation.',
    content: "Let's build a MACD crossover strategy.",
  },
]

function AssistantAvatar() {
  return (
    <span className="row-avatar" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
        <path
          d="M12 2.5 13.8 8.6 20 10.4 13.8 12.2 12 18.3 10.2 12.2 4 10.4 10.2 8.6 12 2.5Z"
          fill="#8B639B"
        />
        <path
          d="M18.6 15.2l.9 2.5 2.5.9-2.5.9-.9 2.5-.9-2.5-2.5-.9 2.5-.9.9-2.5Z"
          fill="#AF719D"
        />
      </svg>
    </span>
  )
}

function Bubble({ message }) {
  const isUser = message.role === 'user'
  if (isUser) {
    return (
      <div className="turn turn--user">
        <div className="row row--user">
          <span className="row-badge">You</span>
          <div className="row__body">
            {message.attachmentName && (
              <span className="row-attach" title={message.attachmentName}>
                &#128206; {message.attachmentName}
              </span>
            )}
            <p className="row__text">{message.content}</p>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="turn">
      <div className="row row--assistant">
        <AssistantAvatar />
        <div className="row__body">
          <Markdown text={message.content} />
        </div>
      </div>
      {message.strategy && <StrategyMiniCard strategy={message.strategy} />}
    </div>
  )
}

export default function ChatPage() {
  const [thread, setThread] = useState(() => readThread())
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [attachment, setAttachment] = useState(null)
  const elapsed = useElapsedTimer(loading)

  const scrollRef = useRef(null)
  const abortRef = useRef(null)
  const inputRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [thread.messages.length, loading])

  // Auto-resize the composer textarea as the user types.
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [input])

  const persist = useCallback((next) => {
    setThread(next)
    writeThread(next)
  }, [])

  async function sendMessage(content) {
    const text = typeof content === 'string' ? content : input
    if (loading || !text.trim()) return

    const userMessage = {
      id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: text.trim(),
      createdAt: new Date().toISOString(),
      attachmentName: attachment?.name ?? null,
    }

    const base = { conversationId: thread.conversationId, messages: [...thread.messages, userMessage] }
    persist(base)
    setInput('')
    setAttachment(null)
    if (fileRef.current) fileRef.current.value = ''
    setLoading(true)
    setError(null)
    setNotice(null)

    const controller = new AbortController()
    abortRef.current = controller
    const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)

    try {
      const data = await postChat({
        conversationId: base.conversationId,
        content: userMessage.content,
        signal: controller.signal,
      })

      const assistantMessage = {
        id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        role: 'assistant',
        content: data.reply,
        createdAt: new Date().toISOString(),
        strategy: data.strategy_id
          ? {
              strategy_id: data.strategy_id,
              strategy_name: data.strategy_name,
              strategy_description: data.strategy_description,
            }
          : null,
      }

      if (data.strategy_id) {
        registerStrategy({
          id: data.strategy_id,
          name: data.strategy_name,
          description: data.strategy_description,
        })
      }

      persist({
        conversationId: data.conversation_id,
        messages: [...base.messages, assistantMessage],
      })
    } catch (err) {
      // The user turn stays in the thread so nothing typed is lost.
      if (err?.name === 'AbortError') {
        setError('The assistant did not answer within 150 seconds and the request was cancelled.')
      } else if (err?.status === 404) {
        setNotice(
          'This conversation no longer exists on the backend. Start a new conversation to keep going.',
        )
      } else {
        setError(err?.message ?? 'Request failed.')
      }
    } finally {
      clearTimeout(timer)
      abortRef.current = null
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function newConversation() {
    abortRef.current?.abort()
    clearThread()
    setThread({ conversationId: null, messages: [] })
    setError(null)
    setNotice(null)
    setLoading(false)
    setAttachment(null)
    if (fileRef.current) fileRef.current.value = ''
    inputRef.current?.focus()
  }

  function handleFileChange(event) {
    const file = event.target.files?.[0]
    if (file) setAttachment({ name: file.name, size: file.size, type: file.type })
  }

  const canSend = !loading && input.trim() !== ''

  const isEmpty = thread.messages.length === 0

  return (
    <div className="chat-page">
      <div className="studio-head">
        <button
          type="button"
          className="new-chat-btn"
          onClick={newConversation}
          disabled={loading}
          title="New chat"
          aria-label="Start a new chat"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <path
              d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M18.375 2.625a2.828 2.828 0 1 1 3 3L11.5 15.5l-4 1 1-4Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
      <div className="chat-page__scroll">
        {isEmpty ? (
          <div className="chat-empty">
            <div className="chat-empty__hero">
              <h1 className="chat-empty__title">Design a NIFTY 50 strategy by conversation</h1>
              <p className="chat-empty__text">
                Describe the idea in plain language. The assistant asks for anything missing — timeframe,
                thresholds, holding period, risk — and only writes Backtrader code once the rules are
                complete. Nothing here places real orders.
              </p>
            </div>

            <div className="stack stack--tight">
              <span className="section-title">Try one of these</span>
              <div className="example-grid">
                {EXAMPLES.map((example, index) => (
                  <button
                    key={example.title}
                    type="button"
                    className="example-card"
                    onClick={() => sendMessage(example.content)}
                    disabled={loading}
                  >
                    <span className="example-card__index">0{index + 1}</span>
                    <span className="example-card__title">{example.title}</span>
                    <span className="example-card__text">{example.text}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="chat-empty__builder">
              <Link to="/studio/builder" className="btn btn--primary" disabled={loading}>
                ✨ Open Strategy Builder
              </Link>
              <p className="chat-empty__builder-text">
                Prefer a structured form? Build your strategy visually with the Strategy Builder.
              </p>
            </div>
          </div>
        ) : (
          <div className="thread">
            {thread.messages.map((message) => (
              <Bubble key={message.id} message={message} />
            ))}

            {loading && (
              <div className="thinking" role="status" aria-live="polite">
                <AssistantAvatar />
                <span className="spinner-inline" aria-hidden="true" />
                <span className="thinking__label">Thinking…</span>
                <span className="thinking__timer">{formatElapsed(elapsed)}</span>
              </div>
            )}
          </div>
        )}

        {notice && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Note tone="warning" title="Conversation expired">
              <span>{notice}</span>
              <span>
                <button type="button" className="btn btn--sm" onClick={newConversation}>
                  Start a new conversation
                </button>
              </span>
            </Note>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Note tone="danger" title="Request failed">
              <span>{error}</span>
            </Note>
          </div>
        )}

        <div ref={scrollRef} />
      </div>

      <div className="composer">
        <div className="composer__inner">
          {attachment && (
            <div className="composer__chip">
              <span className="composer__chip-icon" aria-hidden="true">&#128206;</span>
              <span className="composer__chip-name" title={attachment.name}>
                {attachment.name}
              </span>
              <button
                type="button"
                className="composer__chip-remove"
                aria-label={`Remove ${attachment.name}`}
                onClick={() => {
                  setAttachment(null)
                  if (fileRef.current) fileRef.current.value = ''
                  inputRef.current?.focus()
                }}
              >
                &times;
              </button>
            </div>
          )}
          <form
            className="composer__bar"
            onSubmit={(event) => {
              event.preventDefault()
              sendMessage()
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf,.csv,.txt"
              className="visually-hidden"
              aria-label="Attach a strategy screenshot or document"
              onChange={handleFileChange}
            />
            <button
              type="button"
              className="composer__attach"
              aria-label="Attach a file"
              title="Attach a screenshot or document (image, PDF, CSV, TXT)"
              disabled={loading}
              onClick={() => fileRef.current?.click()}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                <path
                  d="M12 5v14M5 12h14"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
            <textarea
              ref={inputRef}
              className="composer__input"
              rows={1}
              value={input}
              disabled={loading}
              placeholder="Describe your strategy idea..."
              aria-label="Message the strategy assistant"
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  sendMessage()
                }
              }}
            />
            <button
              type="submit"
              className={`composer__send${canSend ? ' composer__send--active' : ''}`}
              disabled={!canSend}
              aria-label={loading ? 'Sending message' : 'Send message'}
              title="Send"
            >
              {loading ? (
                <span className="btn__spinner" aria-hidden="true" />
              ) : (
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden="true">
                  <path
                    d="M12 19V5m-6 6 6-6 6 6"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}