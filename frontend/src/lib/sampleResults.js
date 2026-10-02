/*
 * Sample dataset for the landing page metrics preview.
 *
 * These are NOT invented numbers. They are one real run of this repository's own
 * sandbox worker (`python -m app.services.strategy_runner`) against the checked-in
 * fixture `backend/tests/fixtures/nifty50.csv`, using the strategy in
 * SAMPLE_STRATEGY below, with the worker's own default parameters
 * (cash 100000, commission 0.1%, PercentSizer 95%).
 *
 * Reproduce from the backend/ directory with:
 *   cat sample.py | python -m app.services.strategy_runner \
 *     --data tests/fixtures/nifty50.csv
 *
 * The sample edges out a naive buy & hold on this window (20.25% vs 15.96%),
 * which is exactly why it needs the caveat below: one window, no out-of-sample
 * split, 9 trades and a 44% hit rate. The point of the section is what the
 * engine measures, not that the strategy is good. Past performance does not
 * predict future returns.
 */

export const SAMPLE_STRATEGY = {
  name: 'NiftyTrendMomentum',
  file: 'generated_strategy.py',
  params: "('fast_len', 15), ('slow_len', 40)",
  dataset: 'nifty50.csv',
  startDate: '2023-09-18',
  endDate: '2026-09-18',
  bars: 740,
}

export const SAMPLE_METRICS = {
  total_return_pct: 20.25,
  benchmark_return_pct: 15.96,
  cagr_pct: 6.34,
  max_drawdown_pct: 13.32,
  max_drawdown_duration_bars: 314,
  sharpe: 0.59,
  sortino: 0.99,
  win_rate_pct: 44.44,
  num_trades: 9,
  profit_factor: 2.57,
  avg_win: 8294.26,
  avg_loss: -2584.98,
  value_start: 100000,
  value_end: 120252.15,
}

/** Winner / loser split, straight off the closed-trade table. */
export const SAMPLE_TRADES = { wins: 4, losses: 5 }

/** 46 sampled dates shared by both curves. */
export const SAMPLE_DATES = [
  '2023-09-18', '2023-10-12', '2023-11-07', '2023-12-01', '2023-12-27', '2024-01-19',
  '2024-02-14', '2024-03-11', '2024-04-05', '2024-05-02', '2024-05-28', '2024-06-21',
  '2024-07-15', '2024-08-08', '2024-09-03', '2024-09-25', '2024-10-21', '2024-11-13',
  '2024-12-09', '2025-01-02', '2025-01-27', '2025-02-17', '2025-03-13', '2025-04-08',
  '2025-05-07', '2025-05-30', '2025-06-23', '2025-07-16', '2025-08-08', '2025-09-03',
  '2025-09-26', '2025-10-23', '2025-11-17', '2025-12-10', '2026-01-05', '2026-01-29',
  '2026-02-23', '2026-03-19', '2026-04-16', '2026-05-12', '2026-06-05', '2026-06-30',
  '2026-07-23', '2026-08-14', '2026-09-08', '2026-09-18',
]

/** Strategy NAV, compounded by the worker from starting cash. */
export const SAMPLE_EQUITY = [
  100000, 100000, 100000, 102104, 108757, 108602, 109646, 112009, 112878, 113523, 114752,
  117680, 122865, 120621, 125328, 128746, 122310, 122310, 122310, 118208, 118208, 118208,
  118208, 114252, 123222, 124827, 125884, 127030, 125376, 125376, 122322, 128158, 128734,
  127528, 129851, 127115, 127115, 122264, 122264, 118916, 121320, 120404, 120423, 122812,
  120252, 120252,
]

/** NIFTY 50 buy & hold over the same bars — the benchmark the gate compares to. */
export const SAMPLE_BENCHMARK = [
  100000, 98315, 96391, 100669, 107557, 107396, 108477, 110924, 111823, 112491, 113683,
  116728, 122120, 119787, 125562, 129160, 123085, 117015, 122280, 120142, 113390, 114037,
  111245, 111933, 121264, 122934, 124033, 125226, 121010, 122757, 122457, 128600, 129206,
  127937, 130382, 126253, 127714, 114249, 120183, 116124, 116060, 118539, 118558, 121023,
  117393, 115959,
]