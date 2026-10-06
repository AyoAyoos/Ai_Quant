"""
Market-bar selection for paper trading (Phase 2, part A of the tick).

This module answers exactly one question: *which bar is next?* It knows nothing
about orders, positions or P&L — that is :mod:`app.services.paper_engine`'s
job. Keeping the split here is what lets the Phase 2 tests drive the execution
engine from synthetic bars with no network and no live market data.

Bars come from the same cached CSV the backtester reads
(``backend/data/{MARKET}.csv``, written by :mod:`app.services.market_data`), so
paper trading and backtesting consume an identical price history and an
identical OHLCV shape. Nothing here downloads anything: a missing cache is an
error, not a trigger for a Yahoo fetch. That keeps a tick reproducible.
"""
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from app.services.market_data import MarketDataError, market_data_path


# Columns the strategy runner's CSV loader requires, reused so a paper bar and
# a backtest bar are validated against the same contract.
_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

# Guard against a pathological cache; 10 years of daily bars is far beyond any
# MVP horizon and stops a bad file from exhausting memory.
MAX_BARS = 5000


class PaperBarError(ValueError):
    """A bar is missing, malformed, or fails price sanity checks."""


class PaperBarDuplicate(PaperBarError):
    """The requested bar was already consumed by an earlier tick.

    Distinct from a plain :class:`PaperBarError` so a repeat call is
    idempotent without hiding a real problem: "you asked for a date that has
    already been processed" is a no-op, whereas "no such bar exists" and "the
    cache is malformed" are errors.
    """


@dataclass(frozen=True)
class PaperBar:
    """One validated daily OHLCV bar.

    ``close`` is the price paper trading fills at and marks positions with (see
    :func:`app.services.paper_engine.run_tick` for why).
    """

    symbol: str
    bar_date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def date_str(self) -> str:
        return self.bar_date.strftime("%Y-%m-%d")


def _as_float(value, field: str, bar_label: str) -> float:
    """Coerce to float, rejecting None/NaN/inf and non-numeric junk."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PaperBarError(f"{bar_label}: {field} is not a number ({value!r})") from None
    if math.isnan(number):
        raise PaperBarError(f"{bar_label}: {field} is NaN")
    if math.isinf(number):
        raise PaperBarError(f"{bar_label}: {field} is infinite")
    if number <= 0.0:
        raise PaperBarError(f"{bar_label}: {field} must be > 0 (got {number})")
    return number


def _as_datetime(value, bar_label: str) -> datetime:
    """Coerce a bar's date to a naive datetime.

    Naive on purpose: ``PaperDeployment.last_bar_date`` and every other datetime
    column in this project is naive UTC, and mixing aware/naive values raises
    ``TypeError`` deep inside a comparison.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        try:
            parsed = pd.to_datetime(value).to_pydatetime()
        except (TypeError, ValueError):
            raise PaperBarError(f"{bar_label}: unparseable bar date ({value!r})") from None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def validate_bar(symbol: str, bar_date, open_, high, low, close, volume=0.0) -> PaperBar:
    """Validate one raw bar and return a :class:`PaperBar`.

    Raises :class:`PaperBarError` for a missing/malformed date, a non-positive
    or non-finite OHLC price, or internally inconsistent highs/lows. ``volume``
    only has to be non-negative — a zero-volume bar is legal (a holiday), a
    negative one is not.
    """
    label = f"bar {bar_date!r}"
    dt = _as_datetime(bar_date, label)

    o = _as_float(open_, "open", label)
    h = _as_float(high, "high", label)
    l = _as_float(low, "low", label)
    c = _as_float(close, "close", label)

    if h < l:
        raise PaperBarError(f"{label}: high {h} < low {l}")
    if h < max(o, c) or l > min(o, c):
        raise PaperBarError(
            f"{label}: inconsistent OHLC (open={o} high={h} low={l} close={c})"
        )

    try:
        vol = float(volume if volume is not None else 0.0)
    except (TypeError, ValueError):
        raise PaperBarError(f"{label}: volume is not a number ({volume!r})") from None
    if math.isnan(vol) or math.isinf(vol) or vol < 0.0:
        raise PaperBarError(f"{label}: volume must be finite and >= 0 (got {volume!r})")

    return PaperBar(
        symbol=symbol.strip().upper(),
        bar_date=dt,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
    )


def load_bars(market: str, path: str | Path | None = None) -> list[PaperBar]:
    """Load and validate every bar in the cached CSV for ``market``.

    Raises :class:`PaperBarError` when the file is missing or unreadable; this
    never triggers a download.
    """
    symbol = market.strip().upper()
    csv_path = Path(path) if path else market_data_path(symbol)
    if not csv_path.exists():
        raise PaperBarError(
            f"no cached market data for {symbol!r} at {csv_path}; "
            f"run a backtest first to populate the cache"
        )

    try:
        frame = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001 - any read failure is a data problem
        raise PaperBarError(f"could not read market data {csv_path}: {exc}") from None

    if frame.empty:
        raise PaperBarError(f"market data {csv_path} is empty")
    if len(frame) > MAX_BARS:
        raise PaperBarError(f"market data {csv_path} has {len(frame)} bars (max {MAX_BARS})")

    if "Date" in frame.columns:
        dates = frame["Date"]
    else:
        dates = pd.Series(frame.index, index=frame.index)

    missing = set(_REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise PaperBarError(f"market data {csv_path} missing columns: {sorted(missing)}")

    bars = [
        validate_bar(
            symbol=symbol,
            bar_date=row_date,
            open_=row["Open"],
            high=row["High"],
            low=row["Low"],
            close=row["Close"],
            volume=row["Volume"],
        )
        for row_date, row in zip(dates, frame[list(_REQUIRED_COLUMNS)].to_dict("records"))
    ]
    bars.sort(key=lambda b: b.bar_date)
    return bars


def next_bar(
    market: str,
    after: datetime | None = None,
    on: datetime | None = None,
    path: str | Path | None = None,
) -> PaperBar:
    """Pick the single bar a tick should process.

    * ``on`` pins one specific bar (the demo/test "step to this day" control).
    * ``after`` is the account's ``last_bar_date`` watermark.

    With ``on`` alone the pinned bar is returned whatever the watermark, so the
    caller decides what to do about a repeat. With ``after`` the first bar
    strictly later than the watermark is returned. With both, a pinned date at
    or before the watermark raises :class:`PaperBarDuplicate` instead of
    handing back a bar that would be processed twice.
    """
    bars = load_bars(market, path=path)
    if not bars:
        raise PaperBarError(f"no bars available for {market!r}")

    if on is not None:
        wanted = _as_datetime(on, "requested bar")
        if after is not None and wanted <= _as_datetime(after, "watermark"):
            raise PaperBarDuplicate(
                f"bar {wanted.strftime('%Y-%m-%d')} was already processed "
                f"(watermark {_as_datetime(after, 'watermark').strftime('%Y-%m-%d')})"
            )
        for bar in bars:
            if bar.bar_date == wanted:
                return bar
        raise PaperBarError(
            f"no bar on {wanted.strftime('%Y-%m-%d')} for {market!r}"
        )

    if after is None:
        return bars[0]

    watermark = _as_datetime(after, "watermark")
    for bar in bars:
        if bar.bar_date > watermark:
            return bar
    raise PaperBarError(
        f"no bar after {watermark.strftime('%Y-%m-%d')} for {market!r}; "
        f"data ends {bars[-1].date_str}"
    )


__all__ = [
    "MAX_BARS",
    "MarketDataError",
    "PaperBar",
    "PaperBarDuplicate",
    "PaperBarError",
    "load_bars",
    "next_bar",
    "validate_bar",
]