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

RESULT_MARKER = "__BT_RESULT__"

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
    cerebro.broker.setcommission(commission=pct_to_fraction(commission_pct))

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
    )
    available = {}
    for _name, _cls_name, _kwargs in _ANALYZERS:
        cls = getattr(bt.analyzers, _cls_name, None)
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

    first_close = float(df["Close"].iloc[0])
    last_close = float(df["Close"].iloc[-1])

    metrics = {
        "start_date": str(df.index[0].date()),
        "end_date": str(df.index[-1].date()),
        "value_start": _sanitize(round(value_start, 2)),
        "value_end": _sanitize(round(value_end, 2)),
        "total_return_pct": _sanitize(round((value_end / value_start - 1.0) * 100.0, 2)),
        "benchmark_return_pct": _sanitize(round((last_close / first_close - 1.0) * 100.0, 2)),
        "sharpe": _sanitize(_safe_get(sharpe, "sharperatio")),
        "sortino": _sanitize(_safe_get(sortino, "sortinoratio")),
        "cagr_pct": None,  # computed in the parent from value + date span
        "warnings": [],
    }
    metrics.update(_extract_trade_metrics(trades))
    metrics.update(_extract_drawdown(drawdown))

    if metrics["num_trades"] == 0:
        metrics["warnings"].append("no_trades")

    return metrics


def pct_to_fraction(pct: float) -> float:
    return float(pct) / 100.0
