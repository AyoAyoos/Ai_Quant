"""
Sandboxed strategy runner (worker process).

This is the ONLY place AI-generated strategy code executes. It is designed to
be spawned as a subprocess by the orchestrator (``backtest_service``) and run
standalone during development:

    python -m app.services.strategy_runner --data data.csv [--cash 100000] [--commission 0.1] [--sizer-percents 95] < strategy.py

Input protocol:
  * strategy code  -> stdin (avoids Windows argv length/quoting limits)
  * data + config  -> argv (paths, numeric knobs)

Output protocol:
  * one sentinel-prefixed JSON line on stdout: ``__BT_RESULT__ <json>``
    {"ok": true, "metrics": {...}}  or  {"ok": false, "error": "..."}
  * anything the strategy prints goes to stdout/stderr BEFORE the sentinel
    (the parent caps captured bytes); the sentinel is the last line.
  * non-zero exit code on failure.

Security note: this is a GUARDRAIL, not a sandbox. The real boundary is the
isolated subprocess + timeout (hard memory/process sandboxing is a Phase 5
item). The ``ast`` pre-check only refuses the obvious escape hatches so
accidental/dumb malicious code fails fast and cheap.
"""
import argparse
import ast
import json
import math
import sys
import types
import uuid
from datetime import datetime

import backtrader as bt
import pandas as pd

RESULT_MARKER = "__BT_RESULT__"

# backtrader annualises daily Sharpe with 252 periods (see
# ``backtrader.analyzers.sharpe.RATEFACTORS``). Sortino is annualised with the
# same factor so the two ratios in a report are directly comparable.
ANNUALISATION_FACTOR = 252

# Caps on the per-trade / equity-curve payloads. The worker serialises metrics
# to stdout and the parent caps captured bytes at 256KB, so a strategy that
# trades every single bar would otherwise blow that budget.
MAX_TRADE_RECORDS = 500
MAX_EQUITY_POINTS = 400

# Imports beyond these fail the guardrail.
ALLOWED_IMPORTS = {"backtrader", "pandas", "numpy", "math", "datetime"}

# Builtin/attribute names that are escape/capability hatches. Calls are
# refused; dunder attribute access (and the escape-y dunder classes) too.
BLOCKED_CALLS = {
    "exec", "eval", "open", "input", "compile", "globals", "locals",
    "vars", "breakpoint", "getattr", "setattr", "delattr", "__import__",
}
BLOCKED_DUNDER_ATTRS = {
    "__class__", "__subclasses__", "__base__", "__bases__", "__mro__",
    "__globals__", "__builtins__", "__import__", "__getattribute__",
    "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__",
    "__subclasshook__",
}
# Referencing these module-level dunders as bare names is refused too.
BLOCKED_DUNDER_NAMES = BLOCKED_DUNDER_ATTRS

TIMEOUT_DEFAULT_SECONDS = 120


# --------------------------------------------------------------------------- #
# Guardrail (ast static analysis)
# --------------------------------------------------------------------------- #
class GuardrailError(Exception):
    pass


class _Guardrails(ast.NodeVisitor):
    def visit_Import(self, node):
        for alias in node.names:
            self._check_root(alias.name, node)
            self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self._check_root(node.module or "", node)
        self.generic_visit(node)

    def _check_root(self, name: str, node) -> None:
        root = name.split(".")[0]
        if root not in ALLOWED_IMPORTS:
            raise GuardrailError(f"refused import: {name}")

    def visit_Attribute(self, node):
        if node.attr in BLOCKED_DUNDER_ATTRS:
            raise GuardrailError(f"refused attribute access: .{node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in BLOCKED_DUNDER_NAMES:
            raise GuardrailError(f"refused name reference: {node.id}")
        self.generic_visit(node)

    def _walk_call_names(self, node):
        """Yield every name used in a call function position."""
        func = node.func
        if isinstance(func, ast.Name):
            yield func.id
        elif isinstance(func, ast.Attribute):
            yield func.attr

    def visit_Call(self, node):
        for name in self._walk_call_names(node):
            if name in BLOCKED_CALLS:
                raise GuardrailError(f"refused call to: {name}()")
        self.generic_visit(node)


def check_guardrails(code: str) -> None:
    """Raise GuardrailError if the code trips a static rule. No execution."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise GuardrailError(f"strategy code does not parse: {exc.args[0]}")

    visitor = _Guardrails()
    try:
        visitor.visit(tree)
    except GuardrailError:
        raise
    except Exception as exc:  # defensively treat any ast hiccup as a reject
        raise GuardrailError(f"guardrail analysis failed: {exc}")


# --------------------------------------------------------------------------- #
# Metrics helpers
# --------------------------------------------------------------------------- #
def _sanitize(value):
    """Coerce NaN/inf floats to None so JSON/Postgres stay happy."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def _safe_get(analysis: dict, *path, default=None, key=None):
    """Lazily walk a nested bt analyzer dict; return default on any miss."""
    node = analysis
    for part in path:
        if not hasattr(node, "get"):
            return default
        node = node.get(part)
    if node is None:
        return default
    if key is not None:
        return _safe_get(node, key, default=default)
    return node


def _extract_trade_metrics(analysis: dict) -> dict:
    total_closed = _safe_get(analysis, "total", "closed", default=0)
    won = _safe_get(analysis, "won", "total", default=0)
    lost = _safe_get(analysis, "lost", "total", default=0)

    closed_pnl = _safe_get(analysis, "pnl", "net", "total", default=0.0)
    won_pnl_sum = _safe_get(analysis, "won", "pnl", "total", default=0.0)
    lost_pnl_sum = _safe_get(analysis, "lost", "pnl", "total", default=0.0)

    profit_factor = None
    if lost_pnl_sum < 0:
        profit_factor = _sanitize(round(abs(won_pnl_sum / lost_pnl_sum), 4))

    return {
        "num_trades": int(total_closed),
        "win_rate_pct": _sanitize(
            round(won / total_closed * 100.0, 2) if total_closed else None
        ),
        "profit_factor": profit_factor,
        "avg_win": _sanitize(
            round(_safe_get(analysis, "won", "pnl", "average", default=0.0), 2)
        ),
        "avg_loss": _sanitize(
            round(_safe_get(analysis, "lost", "pnl", "average", default=0.0), 2)
        ),
        "closed_pnl": _sanitize(round(closed_pnl, 2)),
    }


def _extract_drawdown(analysis: dict) -> dict:
    return {
        "max_drawdown_pct": _sanitize(
            _safe_get(analysis, "max", "drawdown", default=None)
        ),
        "max_drawdown_duration_bars": _sanitize(
            _safe_get(analysis, "max", "len", default=None)
        ),
    }


def _compute_sortino(time_return_analysis: dict):
    """Sortino ratio from backtrader's ``TimeReturn`` analyzer output.

    ``TimeReturn.get_analysis()`` maps each bar's date to that period's simple
    return. Only *negative* returns feed the downside deviation, so upside
    volatility is not punished the way it is in Sharpe.

    The per-period mean and downside deviation are annualised separately
    (mean x 252, deviation x sqrt(252)) — the usual definition for daily data.
    Compounding each period instead would let a single good day dominate the
    ratio and produce absurd values like 69 for a 0.38 Sharpe.

    Returns ``None`` when there is not enough data to form a ratio.
    """
    values = list((time_return_analysis or {}).values())
    returns = [float(v) for v in values if isinstance(v, (int, float))]
    if len(returns) < 2:
        return None

    mean = sum(returns) / len(returns)
    downside = [min(0.0, r) for r in returns]
    deviation = math.sqrt(sum(d * d for d in downside) / len(downside))
    if deviation <= 0:
        return None
    annualised_mean = mean * ANNUALISATION_FACTOR
    annualised_deviation = deviation * math.sqrt(ANNUALISATION_FACTOR)
    return round(annualised_mean / annualised_deviation, 4)


def _build_equity_curve(time_return_analysis: dict, value_start: float):
    """Portfolio value per bar, reconstructed from ``TimeReturn``'s daily series.

    ``TimeReturn`` reports simple per-period returns, so compounding them from
    the starting cash reproduces the broker's value path exactly without
    attaching a second value-tracking analyzer. Downsampled to
    ``MAX_EQUITY_POINTS`` (keeping the first and last bar) so a multi-year run
    does not produce an unwieldy payload.
    """
    items = sorted(
        (dt, r)
        for dt, r in (time_return_analysis or {}).items()
        if isinstance(r, (int, float))
    )
    if not items:
        return []

    points = []
    value = float(value_start)
    for dt, ret in items:
        if ret > -1.0:  # a -100% return would zero the account; skip past it
            value *= 1.0 + float(ret)
        points.append([_format_date(dt), round(value, 2)])

    if len(points) > MAX_EQUITY_POINTS:
        step = len(points) / MAX_EQUITY_POINTS
        sampled = [points[min(len(points) - 1, int(i * step))] for i in range(MAX_EQUITY_POINTS)]
        if sampled[-1] != points[-1]:
            sampled[-1] = points[-1]
        points = sampled
    return points


def _format_date(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


class ClosedTradeCollector(bt.analyzers.Analyzer):
    """Records one dict per closed trade for the trade dashboard.

    ``TradeAnalyzer`` only ever accumulates aggregates — it increments counters
    and never keeps the individual trades — so anything wanting a per-trade
    breakdown has to collect them separately. Entry details are captured when
    the trade opens because ``Trade`` only exposes the exit price once closed.
    """

    params = (("max_records", MAX_TRADE_RECORDS),)

    def start(self):
        super(ClosedTradeCollector, self).start()
        self.records = []
        self._pending = {}
        self.dropped = 0

    def notify_trade(self, trade):
        # Entries are paired by ``trade.ref``: backtrader delivers a *different*
        # Trade object on open and on close, so object identity (id()) can
        # never match them — verified empirically. ``ref`` is a global counter
        # and is stable for the logical trade's whole lifetime.
        if trade.justopened:
            self._pending[trade.ref] = {
                "date": self.strategy.datetime.datetime(0),
                "price": float(trade.price),
                "size": int(trade.size),
            }
            return

        if trade.status != trade.Closed:
            return

        entry = self._pending.pop(trade.ref, None)
        if entry is None:
            return

        if len(self.records) >= self.p.max_records:
            self.dropped += 1
            return

        # ``trade.price`` and ``trade.size`` are stale once closed (price keeps
        # the entry value, size is zeroed). The entry details were captured at
        # open time; the exit price is the current bar's open, because market
        # orders execute there — verified against implied pnl/size math.
        exit_price = float(self.strategy.data.open[0])
        self.records.append(
            {
                "entry_date": _format_date(entry["date"]),
                "exit_date": _format_date(self.strategy.datetime.datetime(0)),
                "entry_price": round(entry["price"], 2),
                "exit_price": round(exit_price, 2),
                "size": entry["size"],
                "direction": "long" if trade.long else "short",
                "bars_held": int(trade.barlen),
                "pnl": _sanitize(round(float(trade.pnl), 2)),
                "pnl_net": _sanitize(round(float(trade.pnlcomm), 2)),
                "won": bool(trade.pnlcomm >= 0.0),
            }
        )

    def get_analysis(self):
        return self.records


# --------------------------------------------------------------------------- #
# Data loading (worker side; the parent normally pre-writes the CSV)
# --------------------------------------------------------------------------- #
def load_dataframe(path: str):
    import pandas as pd

    df = pd.read_csv(path)
    if df.empty or len(df) < 2:
        raise ValueError("insufficient data: empty or single-row dataset")

    # Flatten any accidental MultiIndex columns into plain names.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    # Locate the datetime column / index and normalize to a naive UTC index.
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], utc=True)
        df = df.set_index("Date")
    elif not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("data must have a 'Date' column or a DatetimeIndex")
    df = df.sort_index()
    df.index = df.index.tz_localize(None)

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"data missing columns: {sorted(missing)}")

    for col in ("Open", "High", "Low", "Close", "Volume"):
        if not df[col].notna().all():
            raise ValueError(f"data column '{col}' contains nulls")
    if (df["Volume"] == 0).all():
        raise ValueError("data has zero volume throughout; refusing to run")

    return df


# --------------------------------------------------------------------------- #
# Cerebro orchestration
# --------------------------------------------------------------------------- #
def run_backtest(code: str, data_path: str, cash: float, commission_pct: float,
                 sizer_percents: float) -> dict:
    check_guardrails(code)

    # Run in a fresh namespace with real builtins. The guardrail (not builtin
    # stripping) is the boundary here; keeping real builtins is what makes
    # class-definition machinery (__build_class__) and ordinary helpers
    # (range/len/min/max/super/print) work without special casing.
    # backtrader's metaclass machinery (MetaParams.donew) does
    # `sys.modules[cls.__module__]` every time a strategy is instantiated, so
    # the exec'd class's module needs a real, unique entry in sys.modules
    # rather than a bare dict passed as the exec namespace.
    module_name = f"__strategy_{uuid.uuid4().hex}__"
    module = types.ModuleType(module_name)
    module.__file__ = "<generated>"
    sys.modules[module_name] = module
    try:
        exec(compile(code, "<strategy>", "exec"), module.__dict__)

        strategy_cls = None
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, bt.Strategy):
                if name == "GeneratedStrategy":
                    strategy_cls = obj
                    break
                strategy_cls = obj  # accept differently-named subclasses too
        if strategy_cls is None:
            raise ValueError("no bt.Strategy subclass found in the generated code")

        return _run_cerebro(strategy_cls, data_path, cash, commission_pct, sizer_percents)
    finally:
        del sys.modules[module_name]


def _run_cerebro(strategy_cls, data_path: str, cash: float, commission_pct: float,
                  sizer_percents: float) -> dict:
    df = load_dataframe(data_path)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cash)
    # Equity-style percentage commission. `stocklike=True` keeps the position
    # marked as a cash trade (not futures margin); COMM_PERC makes the
    # commission a percentage of notional. Both must match or the broker's
    # margin check can reject every order.
    cerebro.broker.setcommission(
        commission=pct_to_fraction(commission_pct),
        stocklike=True,
        commtype=bt.CommInfoBase.COMM_PERC,
    )

    data = bt.feeds.PandasData(
        dataname=df,
        open="Open", high="High", low="Low", close="Close",
        volume="Volume", openinterest=None,
    )
    cerebro.adddata(data)
    cerebro.addstrategy(strategy_cls)

    # PercentSizer so a bare buy() uses ~sizer_percents% of cash instead of
    # backtrader's default "1 unit" (which makes index-level strategies look
    # like ~0% returns). Single-position assumption, noted for Phase >3.
    cerebro.addsizer(bt.sizers.PercentSizer, percents=sizer_percents)

    # Attach analyzers by name so the runner survives backtrader version drift
    # (e.g. SortinoRatio_A is absent in 1.9.78.123 but present in later builds).
    _ANALYZERS = (
        ("sharpe", "SharpeRatio_A", dict(timeframe=bt.TimeFrame.Days, annualize=True)),
        ("sortino", "SortinoRatio_A", dict(timeframe=bt.TimeFrame.Days, annualize=True)),
        ("drawdown", "DrawDown", {}),
        ("trades", "TradeAnalyzer", {}),
        ("returns", "Returns", {}),
        ("timereturn", "TimeReturn", dict(timeframe=bt.TimeFrame.Days)),
        ("closedtrades", ClosedTradeCollector, {}),
    )
    available = {}
    for _name, _cls_name, _kwargs in _ANALYZERS:
        cls = _cls_name if isinstance(_cls_name, type) else getattr(bt.analyzers, _cls_name, None)
        if cls is None:
            available[_name] = False
            continue
        cerebro.addanalyzer(cls, _name=_name, **_kwargs)
        available[_name] = True

    results = cerebro.run()
    strat = results[0]

    value_start = cash
    value_end = cerebro.broker.getvalue()
    if not value_end or value_end <= 0:
        raise ValueError("portfolio ended with a non-positive value")

    def analysis(name, default=None):
        analyzer = getattr(strat.analyzers, name, None)
        if analyzer is None:
            return default
        return _safe_get(analyzer.get_analysis(), default=default)

    sharpe = analysis("sharpe", default={})
    sortino = analysis("sortino", default={})
    drawdown = analysis("drawdown", default={})
    trades = analysis("trades", default={})
    time_return = analysis("timereturn", default={})
    closed_trades = analysis("closedtrades", default=[])

    # SortinoRatio_A does not exist in backtrader 1.9.78.123, so the analyzer
    # above is always skipped and we derive Sortino from the daily return series.
    sortino_value = _safe_get(sortino, "sortinoratio")
    if sortino_value is None:
        sortino_value = _compute_sortino(time_return)

    first_close = float(df["Close"].iloc[0])
    last_close = float(df["Close"].iloc[-1])

    trade_collector = getattr(strat.analyzers, "closedtrades", None)
    dropped_trades = int(getattr(trade_collector, "dropped", 0) or 0)

    metrics = {
        "start_date": str(df.index[0].date()),
        "end_date": str(df.index[-1].date()),
        "value_start": _sanitize(round(value_start, 2)),
        "value_end": _sanitize(round(value_end, 2)),
        "total_return_pct": _sanitize(round((value_end / value_start - 1.0) * 100.0, 2)),
        "benchmark_return_pct": _sanitize(round((last_close / first_close - 1.0) * 100.0, 2)),
        "sharpe": _sanitize(_safe_get(sharpe, "sharperatio")),
        "sortino": _sanitize(sortino_value),
        "cagr_pct": None,  # computed in the parent from value + date span
        "trades": closed_trades if isinstance(closed_trades, list) else [],
        "trades_truncated": dropped_trades,
        "equity_curve": _build_equity_curve(time_return, value_start),
        "warnings": [],
    }
    metrics.update(_extract_trade_metrics(trades))
    metrics.update(_extract_drawdown(drawdown))

    if metrics["num_trades"] == 0:
        metrics["warnings"].append("no_trades")
    elif dropped_trades:
        metrics["warnings"].append(f"trades_truncated:{dropped_trades}")

    return metrics


def pct_to_fraction(pct: float) -> float:
    return float(pct) / 100.0


# --------------------------------------------------------------------------- #
# Phase 2: paper-trading signal replay
# --------------------------------------------------------------------------- #
class FinalBarOrderCollector(bt.analyzers.Analyzer):
    """Records the orders a strategy *submitted* on the final bar of a replay.

    Paper trading must not re-interpret the generated strategy: this analyzer
    observes the real Backtrader broker and reports what the strategy's own
    ``next()`` decided for the last bar. Only ``Submitted`` events on the final
    bar count — those are the strategy's intent. Later ``Accepted``/``Completed``
    events are deliberately ignored: a market order submitted in ``next()`` of
    the final bar has no following bar to fill against, and paper trading fills
    the order itself (see ``paper_engine``).

    Submitting is also what distinguishes a signal from a no-op: a bar where the
    strategy did nothing yields no event and therefore a HOLD.
    """

    def start(self):
        super(FinalBarOrderCollector, self).start()
        self.submissions = []

    def notify_order(self, order):
        self.submissions.append(
            {
                "bar_date": _format_date(self.strategy.datetime.datetime(0)),
                "status": order.getstatusname(),
                "isbuy": bool(order.isbuy()),
                "ref": order.ref,
            }
        )

    def get_analysis(self):
        return self.submissions


ACTION_BUY = "buy"
ACTION_SELL = "sell"
ACTION_HOLD = "hold"


def run_signal(
    code: str,
    data_path: str,
    cash: float,
    commission_pct: float,
    sizer_percents: float,
    upto_date: str | None = None,
) -> dict:
    """Replay `code` over its own data and report the decision for one bar.

    Deterministic replay, not incremental execution: Backtrader's Cerebro is
    built to run a feed start-to-finish in one pass and cannot be fed a bar at a
    time with its indicator state carried across ticks. Rather than bolt a
    parallel indicator framework onto the paper account (a second RSI/SMA
    interpretation that could silently disagree with the backtest), the same
    strategy class is re-run over the real cached history up to and including
    ``upto_date``. Indicators warm up exactly as they do in a backtest, so the
    final bar's decision is the strategy's genuine output.

    Cost: one extra full replay per tick. For a daily MVP series that is
    seconds, and it is bounded by the same subprocess timeout as a backtest.

    Returns ``{"action": buy|sell|hold, "bar_date": ..., "close": ...}``.
    """
    check_guardrails(code)

    module_name = f"__strategy_{uuid.uuid4().hex}__"
    module = types.ModuleType(module_name)
    module.__file__ = "<generated>"
    sys.modules[module_name] = module
    try:
        exec(compile(code, "<strategy>", "exec"), module.__dict__)

        strategy_cls = None
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, bt.Strategy):
                if name == "GeneratedStrategy":
                    strategy_cls = obj
                    break
                strategy_cls = obj
        if strategy_cls is None:
            raise ValueError("no bt.Strategy subclass found in the generated code")

        return _replay_for_signal(
            strategy_cls, data_path, cash, commission_pct, sizer_percents, upto_date
        )
    finally:
        # Must stay in sys.modules until Cerebro has *instantiated* the class
        # (MetaParams.donew resolves sys.modules[cls.__module__]).
        del sys.modules[module_name]


def _replay_for_signal(
    strategy_cls, data_path: str, cash: float, commission_pct: float,
    sizer_percents: float, upto_date: str | None,
) -> dict:
    df = load_dataframe(data_path)

    if not upto_date:
        return _replay_window(strategy_cls, df, cash, commission_pct, sizer_percents)

    cutoff = pd.Timestamp(upto_date)
    # Compare on the naive date only: the CSV loader localises the index to
    # naive UTC, and a tz-aware cutoff would silently select nothing.
    eligible = df.index <= (cutoff.tz_localize(None) if cutoff.tzinfo else cutoff)
    window = df[eligible]
    if window.empty:
        raise ValueError(f"no bars on or before {upto_date}")

    if len(window) >= len(df):
        return _replay_window(strategy_cls, window, cash, commission_pct, sizer_percents)

    try:
        return _replay_window(strategy_cls, window, cash, commission_pct, sizer_percents)
    except Exception as window_error:
        # The truncated window is shorter than the strategy's longest indicator
        # period, so indexing that indicator underflows. That is a warmup
        # condition, not a broken strategy — but the two are indistinguishable
        # from the exception alone. Distinguish them by re-running the FULL
        # history: a strategy that only fails on short windows is sound, and
        # the right answer for a not-yet-warm bar is HOLD, not an error.
        #
        # This costs a second replay, but only during warmup (the first few
        # bars of a deployment), so the common tick stays at one replay. A
        # strategy that fails on the full history too is genuinely broken and
        # its error surfaces to the caller.
        _replay_window(strategy_cls, df, cash, commission_pct, sizer_percents)
        return {
            "action": ACTION_HOLD,
            "bar_date": _format_date(window.index[-1]),
            "close": float(window["Close"].iloc[-1]),
            "warmup": True,
            "reason": (
                f"warming up: strategy needs more than {len(window)} bar(s) of "
                f"history; no signal for {upto_date}"
            ),
        }


def _replay_window(strategy_cls, df, cash: float, commission_pct: float,
                   sizer_percents: float) -> dict:
    """Run one Cerebro replay over ``df`` and report the final bar's decision."""
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cash)
    # Identical broker configuration to _run_cerebro, so sizing and margin
    # behaviour match the backtest this strategy was approved on.
    cerebro.broker.setcommission(
        commission=pct_to_fraction(commission_pct),
        stocklike=True,
        commtype=bt.CommInfoBase.COMM_PERC,
    )
    data = bt.feeds.PandasData(
        dataname=df,
        open="Open", high="High", low="Low", close="Close",
        volume="Volume", openinterest=None,
    )
    cerebro.adddata(data)
    cerebro.addstrategy(strategy_cls)
    cerebro.addsizer(bt.sizers.PercentSizer, percents=sizer_percents)
    cerebro.addanalyzer(FinalBarOrderCollector, _name="signal")

    results = cerebro.run()
    strat = results[0]

    last_date = _format_date(df.index[-1])
    last_close = float(df["Close"].iloc[-1])

    collector = getattr(strat.analyzers, "signal", None)
    submissions = list(collector.get_analysis()) if collector is not None else []
    final_bar = [
        s for s in submissions
        if s["status"] == "Submitted" and str(s["bar_date"]).startswith(last_date)
    ]

    action = ACTION_HOLD
    if final_bar:
        # Last submission wins; a strategy that both buys and sells on one bar
        # is pathological, and the most recent decision is the relevant one.
        action = ACTION_BUY if final_bar[-1]["isbuy"] else ACTION_SELL

    return {"action": action, "bar_date": last_date, "close": last_close}


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run an AI-generated bt strategy.")
    parser.add_argument("--data", required=True, help="path to OHLCV CSV")
    parser.add_argument("--cash", type=float, default=100000.0)
    parser.add_argument("--commission", type=float, default=0.1, help="commission %%")
    parser.add_argument("--sizer-percents", type=float, default=95.0)
    parser.add_argument(
        "--signal",
        action="store_true",
        help="paper-trading mode: report the strategy's decision for one bar",
    )
    parser.add_argument(
        "--upto-date",
        default=None,
        help="with --signal, replay only bars up to this YYYY-MM-DD",
    )
    args = parser.parse_args(argv)

    code = sys.stdin.read()
    try:
        if args.signal:
            signal = run_signal(
                code=code,
                data_path=args.data,
                cash=args.cash,
                commission_pct=args.commission,
                sizer_percents=args.sizer_percents,
                upto_date=args.upto_date,
            )
            print_result({"ok": True, "signal": signal})
            return 0

        metrics = run_backtest(
            code=code,
            data_path=args.data,
            cash=args.cash,
            commission_pct=args.commission,
            sizer_percents=args.sizer_percents,
        )
        print_result({"ok": True, "metrics": metrics})
        return 0
    except (GuardrailError, ValueError, SyntaxError) as exc:
        print_result({"ok": False, "error": str(exc)})
        return 1
    except Exception as exc:  # noqa: BLE001 - worker must never die silently
        print_result({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1


def print_result(payload: dict) -> None:
    print(f"{RESULT_MARKER} {json.dumps(payload, default=str)}", flush=True)


if __name__ == "__main__":
    sys.exit(main())