// Indicator catalog shared by the builder UI and the payload mapper.
// `id` is the key used in component state; `name` is the literal display
// string the backend schema accepts ('EMA', 'SMA', 'RSI', 'MACD',
// 'Bollinger Bands', 'Volume').
export const INDICATORS = [
  {
    id: 'EMA',
    name: 'EMA',
    description: 'Exponential Moving Average',
    params: [
      { key: 'fast', label: 'Fast Period', type: 'number', min: 1, max: 200, default: 20 },
      { key: 'slow', label: 'Slow Period', type: 'number', min: 1, max: 200, default: 50 },
    ],
  },
  {
    id: 'SMA',
    name: 'SMA',
    description: 'Simple Moving Average',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 200, default: 20 },
    ],
  },
  {
    id: 'RSI',
    name: 'RSI',
    description: 'Relative Strength Index',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 100, default: 14 },
      { key: 'oversold', label: 'Oversold', type: 'number', min: 1, max: 50, default: 30 },
      { key: 'overbought', label: 'Overbought', type: 'number', min: 50, max: 100, default: 70 },
    ],
  },
  {
    id: 'MACD',
    name: 'MACD',
    description: 'Moving Average Convergence Divergence',
    params: [
      { key: 'fast', label: 'Fast Period', type: 'number', min: 1, max: 50, default: 12 },
      { key: 'slow', label: 'Slow Period', type: 'number', min: 1, max: 50, default: 26 },
      { key: 'signal', label: 'Signal Period', type: 'number', min: 1, max: 50, default: 9 },
    ],
  },
  {
    id: 'BOLLINGER_BANDS',
    name: 'Bollinger Bands',
    description: 'Volatility Bands',
    params: [
      { key: 'period', label: 'Period', type: 'number', min: 1, max: 100, default: 20 },
      { key: 'devfactor', label: 'Deviation Factor', type: 'number', min: 0.1, max: 5, step: 0.1, default: 2.0 },
    ],
  },
  {
    id: 'VOLUME',
    name: 'Volume',
    description: 'Volume Indicator',
    params: [],
  },
]
