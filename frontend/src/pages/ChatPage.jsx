import { useCallback, useEffect, useRef, useState } from 'react'
import { CHAT_TIMEOUT_MS, postChat } from '../lib/api.js'
import { clearThread, readThread, registerStrategy, writeThread } from '../lib/storage.js'
import { formatElapsed } from '../lib/format.js'
import { useElapsedTimer } from '../lib/useElapsedTimer.js'
import Markdown from '../components/Markdown.jsx'
import Note from '../components/Note.jsx'
import ElapsedTimer from '../components/ElapsedTimer.jsx'
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

function Bubble({ message }) {
  const isUser = message.role === 'user'
  return (
    <div className={`turn${isUser ? ' turn--user' : ''}`}>
      <div className={`bubble bubble--${isUser ? 'user' : 'assistant'}`}>
        <div className="bubble__meta">
          <span>{isUser ? 'You' : 'Assistant'}</span>
        </div>
        {isUser ? <p>{message.content}</p> : <Markdown text={message.content} />}
      </div>
      {!isUser && message.strategy && <StrategyMiniCard strategy={message.strategy} />}
    </div>
  )
}

export default function ChatPage() {
  const [thread, setThread] = useState(() => readThread())
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const elapsed = useElapsedTimer(loading)

  const scrollRef = useRef(null)
  const abortRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [thread.messages.length, loading])

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
    }

    const base = { conversationId: thread.conversationId, messages: [...thread.messages, userMessage] }
    persist(base)
    setInput('')
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
    inputRef.current?.focus()
  }

  const isEmpty = thread.messages.length === 0

  return (
    <div className="chat-page">
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
          </div>
        ) : (
          <div className="thread">
            {thread.messages.map((message) => (
              <Bubble key={message.id} message={message} />
            ))}

            {loading && (
              <div className="thinking" role="status" aria-live="polite">
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
        <form
          className="composer__box"
          onSubmit={(event) => {
            event.preventDefault()
            sendMessage()
          }}
        >
          <textarea
            ref={inputRef}
            className="composer__input"
            rows={2}
            value={input}
            disabled={loading}
            placeholder="Describe your strategy idea…"
            aria-label="Message the strategy assistant"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                sendMessage()
              }
            }}
          />
          <button type="submit" className="btn btn--primary" disabled={loading || input.trim() === ''}>
            {loading ? <span className="btn__spinner" aria-hidden="true" /> : null}
            {loading ? 'Sending…' : 'Send'}
          </button>
        </form>

        <div className="composer__foot">
          <span>
            <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
          </span>
          <div className="row">
            {!isEmpty && <ElapsedTimer seconds={elapsed} />}
            {isEmpty ? null : (
              <button type="button" className="btn btn--ghost btn--sm" onClick={newConversation} disabled={loading}>
                New conversation
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}