import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const INDICATORS_FOR_CONDITIONS = [
  { value: 'EMA 20', label: 'EMA 20' },
  { value: 'EMA 50', label: 'EMA 50' },
  { value: 'EMA 100', label: 'EMA 100' },
  { value: 'EMA 200', label: 'EMA 200' },
  { value: 'SMA 20', label: 'SMA 20' },
  { value: 'SMA 50', label: 'SMA 50' },
  { value: 'RSI', label: 'RSI' },
  { value: 'MACD', label: 'MACD' },
  { value: 'Bollinger Upper', label: 'Bollinger Upper' },
  { value: 'Bollinger Lower', label: 'Bollinger Lower' },
  { value: 'Price', label: 'Price' },
  { value: 'Volume', label: 'Volume' },
]

const OPERATORS = [
  { value: 'crosses above', label: 'crosses above' },
  { value: 'crosses below', label: 'crosses below' },
  { value: 'is above', label: 'is above' },
  { value: 'is below', label: 'is below' },
  { value: 'equals', label: 'equals' },
  { value: 'is greater than', label: 'is greater than' },
  { value: 'is less than', label: 'is less than' },
]

const LOGICAL_OPS = ['AND', 'OR']

export default function EntryConditionsSection({
  value,
  onChange,
  _availableIndicators,
  error,
  onAIInterpret,
  aiSuggestions,
}) {
  // value: array of condition objects { left, operator, right, logicalOp }
  // availableIndicators: array of selected indicator names from IndicatorsSection

  const navigate = useNavigate()
  // onAIInterpret is the legacy inline-suggestion hook; the button now hands
  // the description off to the Studio chat instead (see handleAIInterpret).
  void onAIInterpret
  const [aiInput, setAiInput] = useState('')

  const addCondition = () => {
    onChange([
      ...value,
      { left: '', operator: 'crosses above', right: '', logicalOp: 'AND' },
    ])
  }

  const removeCondition = (index) => {
    onChange(value.filter((_, i) => i !== index))
  }

  const updateCondition = (index, field, newValue) => {
    const updated = [...value]
    updated[index] = { ...updated[index], [field]: newValue }
    onChange(updated)
  }

  const handleAIInterpret = () => {
    const text = aiInput.trim()
    // Always route directly to Studio so the button is actionable via
    // mouse, touch, and keyboard. Carry the description when present so
    // the Studio composer can prefill it.
    if (text) {
      navigate('/studio', { state: { entryPrompt: text } })
    } else {
      navigate('/studio')
    }
  }

  const addAISuggestions = () => {
    if (aiSuggestions && aiSuggestions.length > 0) {
      onChange(aiSuggestions)
      setAiInput('')
    }
  }

  return (
    <section className="strategy-section entry-card" aria-labelledby="entry-heading">
      <div className="strategy-section__head">
        <h2 id="entry-heading" className="strategy-section__title entry-card__title">When should the strategy ENTER?</h2>
      </div>

      <div className="entry-conditions" role="group" aria-label="Entry conditions">
        <div className="entry-conditions__label entry-buy-label">BUY WHEN</div>

        {value.length === 0 ? (
          <div className="entry-conditions__empty">
            <p className="entry-conditions__hint">Add your first entry condition</p>
            <button type="button" className="btn btn--primary btn--sm" onClick={addCondition}>
              + Add Condition
            </button>
          </div>
        ) : (
          <>
            {value.map((condition, index) => (
              <div key={index} className="condition-row">
                {index > 0 && (
                  <div className="condition-logical">
                    <select
                      className="field__input condition-select"
                      value={condition.logicalOp}
                      onChange={(e) => updateCondition(index, 'logicalOp', e.target.value)}
                      aria-label={`Logical operator for condition ${index + 1}`}
                    >
                      {LOGICAL_OPS.map((op) => (
                        <option key={op} value={op}>{op}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="condition-fields">
                  <div className="field condition-field">
                    <select
                      className="field__input condition-select"
                      value={condition.left}
                      onChange={(e) => updateCondition(index, 'left', e.target.value)}
                      aria-label={`Left operand for condition ${index + 1}`}
                    >
                      <option value="">Select indicator</option>
                      {INDICATORS_FOR_CONDITIONS.map((ind) => (
                        <option key={ind.value} value={ind.value}>{ind.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field condition-field">
                    <select
                      className="field__input condition-select"
                      value={condition.operator}
                      onChange={(e) => updateCondition(index, 'operator', e.target.value)}
                      aria-label={`Operator for condition ${index + 1}`}
                    >
                      {OPERATORS.map((op) => (
                        <option key={op.value} value={op.value}>{op.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="field condition-field">
                    <select
                      className="field__input condition-select"
                      value={condition.right}
                      onChange={(e) => updateCondition(index, 'right', e.target.value)}
                      aria-label={`Right operand for condition ${index + 1}`}
                    >
                      <option value="">Select value</option>
                      {INDICATORS_FOR_CONDITIONS.map((ind) => (
                        <option key={ind.value} value={ind.value}>{ind.label}</option>
                      ))}
                      {['30', '70', '50', '20', '100', '0'].map((v) => (
                        <option key={v} value={v}>{v}</option>
                      ))}
                    </select>
                  </div>

                  <button
                    type="button"
                    className="btn btn--ghost btn--sm condition-remove"
                    onClick={() => removeCondition(index)}
                    aria-label={`Remove condition ${index + 1}`}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}

            <button type="button" className="btn entry-add-btn" onClick={addCondition}>
              + Add Condition
            </button>
          </>
        )}

        {/* AI Natural Language Input */}
        <div className="entry-ai-input">
          <div className="entry-ai-input__divider">Or describe your entry condition</div>
          <div className="entry-ai-input__field">
            <textarea
              className="field__input entry-describe"
              rows={2}
              value={aiInput}
              onChange={(e) => setAiInput(e.target.value)}
              placeholder="e.g., Buy when EMA 20 crosses above EMA 50 and RSI is below 30"
              aria-label="Describe entry condition in natural language"
            />
            <button
              type="button"
              className="btn btn--primary btn--sm entry-ai-input__btn"
              onClick={handleAIInterpret}
              aria-label="Understand strategy entry conditions with AI"
              title="Understand strategy entry conditions with AI"
            >
              <span>UNDERSTAND WITH AI</span>
            </button>
          </div>
        </div>

        {/* AI Suggestions */}
        {aiSuggestions && aiSuggestions.length > 0 && (
          <div className="ai-suggestions" role="status" aria-live="polite">
            <div className="ai-suggestions__header">
              <span>AI understood:</span>
              <button type="button" className="btn btn--ghost btn--sm" onClick={addAISuggestions}>
                Accept All
              </button>
            </div>
            <ul className="ai-suggestions__list">
              {aiSuggestions.map((s, i) => (
                <li key={i} className="ai-suggestions__item">
                  ✓ {s.left} {s.operator} {s.right}
                </li>
              ))}
            </ul>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => onChange([])}>
              Edit instead
            </button>
          </div>
        )}
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}