"""
Paper-trading market bars (read-only).

The paper execution engine AND the NIFTY paper-trading chart read the SAME
underlying data through this module: the cached ``backend/data/{MARKET}.csv``
written by ``market_data``. Nothing here downloads, refreshes, contacts a
broker, or mutates anything — when the cache is missing the caller gets a
``PaperBarsError`` it must surface, never a fabricated bar.
"""
import csv
from pathlib import Path

from app.services.market_data import market_data_path

_REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close")


class PaperBarsError(RuntimeError):
    pass


def load_bars(market: str) -> list[dict]:
    """Load cached OHLC bars for ``market``, oldest first.

    Each bar is ``{"date": "YYYY-MM-DD", "open": f, "high": f, "low": f,
    "close": f, "volume": f}``. Raises :class:`PaperBarsError` when the
    cache is missing or unusable.
    """
    market_key = (market or "").strip().upper()
    path: Path = market_data_path(market_key)
    if not path.exists():
        raise PaperBarsError(
            f"no cached market data for {market_key!r} "
            f"(expected {path.name}); run a backtest first to populate the cache"
        )

    try:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = [c for c in _REQUIRED_COLUMNS if c not in columns]
            if missing:
                raise PaperBarsError(
                    f"cached market data {path.name} is missing columns: {missing}"
                )
            bars: list[dict] = []
            for row in reader:
                try:
                    bars.append(
                        {
                            "date": str(row["Date"]).strip()[:10],
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": float(row.get("Volume") or 0),
                        }
                    )
                except (TypeError, ValueError):
                    # A corrupt row must not silently shift the watermark:
                    # fail loudly instead of skipping it.
                    raise PaperBarsError(
                        f"cached market data {path.name} has an unreadable row "
                        f"near date {row.get('Date')!r}"
                    )
    except PaperBarsError:
        raise
    except OSError as exc:
        raise PaperBarsError(
            f"could not read cached market data {path.name}: {exc}"
        ) from exc

    bars.sort(key=lambda b: b["date"])
    if not bars:
        raise PaperBarsError(f"cached market data {path.name} contains no bars")
    return bars


def select_next_bar(
    bars: list[dict],
    last_bar_date: str | None,
    requested_date: str | None = None,
) -> dict:
    """Pick the single bar the next paper tick must process.

    Strict chronological execution: without ``requested_date`` this is the
    oldest bar strictly after the ``last_bar_date`` watermark (or the very
    first bar when nothing was processed yet). With ``requested_date`` the
    bar must be EXACTLY that next bar — already-processed, earlier, missing,
    or future-skipping dates are rejected so intermediate bars (which may
    contain BUY/SELL decisions) can never be silently skipped. Raises
    :class:`PaperBarsError` when there is nothing left to process.
    """
    next_bar = None
    for bar in bars:
        if last_bar_date is None or bar["date"] > last_bar_date:
            next_bar = bar
            break
    if requested_date is not None:
        wanted = requested_date.strip()[:10]
        match = next((b for b in bars if b["date"] == wanted), None)
        if match is None:
            raise PaperBarsError(f"no cached market bar for date {wanted!r}")
        if last_bar_date is not None and match["date"] <= last_bar_date:
            raise PaperBarsError(
                f"bar {wanted!r} was already processed "
                f"(last processed bar is {last_bar_date!r})"
            )
        if next_bar is None:
            raise PaperBarsError(
                "all cached market bars have been processed — no new bar for a paper tick"
            )
        if match["date"] != next_bar["date"]:
            raise PaperBarsError(
                f"bar date must be the next unprocessed market bar "
                f"({next_bar['date']!r}); got {wanted!r}"
            )
        return match

    if next_bar is None:
        raise PaperBarsError(
            "all cached market bars have been processed — no new bar for a paper tick"
        )
    return next_bar


def processed_bars(bars: list[dict], last_bar_date: str | None) -> list[dict]:
    """Bars the engine has actually processed (watermark-inclusive), oldest first."""
    if last_bar_date is None:
        return []
    return [b for b in bars if b["date"] <= last_bar_date]
