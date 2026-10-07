export default function ExitRiskSection({ value: rawValue, onChange, error }) {
  // value: { exitOnOpposite: boolean, customExits: [], stopLoss: { enabled: boolean, value: number }, takeProfit: { enabled: boolean, value: number }, trailingStop: { enabled: boolean, value: number }, maxTradesPerDay: number }
  //
  // Defensive normalization: every render reads `value.stopLoss.enabled` etc,
  // so a missing/partial object (fresh state, API payload) must not crash the
  // tree — default the whole shape instead.
  const value = {
    exitOnOpposite: rawValue?.exitOnOpposite ?? false,
    customExits: Array.isArray(rawValue?.customExits) ? rawValue.customExits : [],
    stopLoss: { enabled: false, value: 1, ...rawValue?.stopLoss },
    takeProfit: { enabled: false, value: 2, ...rawValue?.takeProfit },
    trailingStop: { enabled: false, value: 0.5, ...rawValue?.trailingStop },
    maxTradesPerDay: rawValue?.maxTradesPerDay ?? 3,
  }

  const updateField = (section, field, newValue) => {
    onChange({ ...value, [section]: { ...value[section], [field]: newValue } })
  }

  const updateNested = (section, field, subField, newValue) => {
    onChange({
      ...value,
      [section]: {
        ...value[section],
        [field]: subField
          ? { ...value[section][field], [subField]: newValue }
          : newValue,
      },
    })
  }

  const addCustomExit = () => {
    onChange({ ...value, customExits: [...value.customExits, { left: '', operator: 'crosses below', right: '' }] })
  }

  const removeCustomExit = (index) => {
    onChange({ ...value, customExits: value.customExits.filter((_, i) => i !== index) })
  }

  const updateCustomExit = (index, field, newValue) => {
    const updated = [...value.customExits]
    updated[index] = { ...updated[index], [field]: newValue }
    onChange({ ...value, customExits: updated })
  }

  return (
    <section className="strategy-section" aria-labelledby="exit-risk-heading">
      <div className="strategy-section__head">
        <h2 id="exit-risk-heading" className="strategy-section__title">Exit & Risk Management</h2>
      </div>

      <div className="exit-risk-grid">
        {/* Exit Conditions */}
        <div className="exit-risk-panel">
          <h3 className="exit-risk-panel__title">Exit Conditions</h3>

          <label className="exit-risk__checkbox">
            <input
              type="checkbox"
              checked={value.exitOnOpposite}
              onChange={(e) => updateField('exitOnOpposite', '', e.target.checked)}
            />
            <span>Exit when opposite signal occurs</span>
          </label>

          <div className="exit-risk__divider" />

          <div className="exit-risk__custom">
            <div className="exit-risk__custom-head">
              <span>Custom Exit Conditions</span>
              <button type="button" className="btn btn--ghost btn--sm" onClick={addCustomExit}>
                + Add Exit
              </button>
            </div>

            {value.customExits.length === 0 ? (
              <p className="exit-risk__empty">No custom exits defined</p>
            ) : (
              value.customExits.map((exit, index) => (
                <div key={index} className="exit-condition-row">
                  <select
                    className="field__input"
                    value={exit.left}
                    onChange={(e) => updateCustomExit(index, 'left', e.target.value)}
                  >
                    <option value="">Select indicator</option>
                    <option value="EMA 20">EMA 20</option>
                    <option value="EMA 50">EMA 50</option>
                    <option value="RSI">RSI</option>
                    <option value="MACD">MACD</option>
                    <option value="Price">Price</option>
                  </select>

                  <select
                    className="field__input"
                    value={exit.operator}
                    onChange={(e) => updateCustomExit(index, 'operator', e.target.value)}
                  >
                    <option value="crosses below">crosses below</option>
                    <option value="crosses above">crosses above</option>
                    <option value="is below">is below</option>
                    <option value="is above">is above</option>
                  </select>

                  <select
                    className="field__input"
                    value={exit.right}
                    onChange={(e) => updateCustomExit(index, 'right', e.target.value)}
                  >
                    <option value="">Select value</option>
                    <option value="EMA 50">EMA 50</option>
                    <option value="EMA 20">EMA 20</option>
                    <option value="70">70</option>
                    <option value="30">30</option>
                  </select>

                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => removeCustomExit(index)}
                    aria-label={`Remove exit ${index + 1}`}
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Risk Management */}
        <div className="exit-risk-panel">
          <h3 className="exit-risk-panel__title">Risk Management</h3>

          <div className="risk-row">
            <label className="exit-risk__checkbox">
              <input
                type="checkbox"
                checked={value.stopLoss.enabled}
                onChange={(e) => updateNested('stopLoss', 'enabled', '', e.target.checked)}
              />
              <span>Stop Loss</span>
            </label>
            {value.stopLoss.enabled && (
              <div className="field risk-field">
                <label className="field__label">%</label>
                <div className="field__control">
                  <input
                    type="number"
                    className="field__input"
                    min="0.1"
                    max="100"
                    step="0.1"
                    value={value.stopLoss.value}
                    onChange={(e) => updateNested('stopLoss', 'value', '', Number(e.target.value))}
                  />
                  <span className="field__suffix">%</span>
                </div>
              </div>
            )}
          </div>

          <div className="risk-row">
            <label className="exit-risk__checkbox">
              <input
                type="checkbox"
                checked={value.takeProfit.enabled}
                onChange={(e) => updateNested('takeProfit', 'enabled', '', e.target.checked)}
              />
              <span>Take Profit</span>
            </label>
            {value.takeProfit.enabled && (
              <div className="field risk-field">
                <label className="field__label">%</label>
                <div className="field__control">
                  <input
                    type="number"
                    className="field__input"
                    min="0.1"
                    max="100"
                    step="0.1"
                    value={value.takeProfit.value}
                    onChange={(e) => updateNested('takeProfit', 'value', '', Number(e.target.value))}
                  />
                  <span className="field__suffix">%</span>
                </div>
              </div>
            )}
          </div>

          <div className="risk-row">
            <label className="exit-risk__checkbox">
              <input
                type="checkbox"
                checked={value.trailingStop.enabled}
                onChange={(e) => updateNested('trailingStop', 'enabled', '', e.target.checked)}
              />
              <span>Trailing Stop</span>
            </label>
            {value.trailingStop.enabled && (
              <div className="field risk-field">
                <label className="field__label">%</label>
                <div className="field__control">
                  <input
                    type="number"
                    className="field__input"
                    min="0.1"
                    max="100"
                    step="0.1"
                    value={value.trailingStop.value}
                    onChange={(e) => updateNested('trailingStop', 'value', '', Number(e.target.value))}
                  />
                  <span className="field__suffix">%</span>
                </div>
              </div>
            )}
          </div>

          <div className="field risk-field risk-field--full">
            <label htmlFor="max-trades" className="field__label">Maximum Trades / Day</label>
            <div className="field__control">
              <input
                type="number"
                id="max-trades"
                className="field__input"
                min="1"
                max="100"
                value={value.maxTradesPerDay}
                onChange={(e) => updateField('maxTradesPerDay', '', Number(e.target.value))}
              />
            </div>
          </div>
        </div>
      </div>

      {error && <p className="field__error" role="alert">{error}</p>}
    </section>
  )
}