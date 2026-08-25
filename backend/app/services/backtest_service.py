import math

import backtrader as bt
import pandas as pd


# =============================================================
# EQUITY CURVE ANALYZER
# =============================================================

class EquityCurveAnalyzer(bt.Analyzer):
    """
    Records the portfolio value for every processed trading bar.

    This data will later be sent to the React frontend and
    displayed using Recharts.
    """

    def start(self):
        self.dates = []
        self.values = []

    def next(self):
        # Current portfolio value
        portfolio_value = self.strategy.broker.getvalue()

        # Current market date
        current_date = self.strategy.datetime.datetime(0)

        self.dates.append(
            current_date.isoformat()
        )

        self.values.append(
            float(portfolio_value)
        )

    def get_analysis(self):
        return {
            "dates": self.dates,
            "values": self.values,
        }


# =============================================================
# LOAD NIFTY50 DATA
# =============================================================

def load_nifty50_data(csv_path: str):
    """
    Load daily NIFTY50 OHLCV data from CSV.

    Expected columns:

        Date
        Open
        High
        Low
        Close
        Volume

    Additional columns such as Dividends and Stock Splits
    are ignored.
    """

    # =========================================================
    # 1. Read CSV
    # =========================================================

    df = pd.read_csv(csv_path)

    # =========================================================
    # 2. Normalize column names
    # =========================================================

    df.columns = [
        str(column).strip().lower()
        for column in df.columns
    ]

    required_columns = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    # =========================================================
    # 3. Parse dates
    # =========================================================

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        utc=True,
    )

    # Remove invalid dates
    df = df.dropna(
        subset=["date"]
    )

    # Remove timezone information
    df["date"] = (
        df["date"]
        .dt
        .tz_localize(None)
    )

    # =========================================================
    # 4. Convert OHLCV columns to numeric
    # =========================================================

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # =========================================================
    # 5. Remove invalid numerical rows
    # =========================================================

    df = df.dropna(
        subset=numeric_columns
    )

    # =========================================================
    # 6. Remove zero / negative volume rows
    # =========================================================

    df = df[
        df["volume"] > 0
    ]

    # =========================================================
    # 7. Sort chronologically
    # =========================================================

    df = df.sort_values(
        "date"
    )

    # =========================================================
    # 8. Remove duplicate dates
    # =========================================================

    df = df.drop_duplicates(
        subset=["date"],
        keep="first",
    )

    # =========================================================
    # 9. Set date as index
    # =========================================================

    df.set_index(
        "date",
        inplace=True,
    )

    # =========================================================
    # 10. Keep only OHLCV columns
    # =========================================================

    df = df[
        [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    ]

    # =========================================================
    # 11. Final validation
    # =========================================================

    if df.empty:
        raise ValueError(
            "No valid OHLCV data remains after cleaning."
        )

    if len(df) < 50:
        raise ValueError(
            f"Not enough historical data. "
            f"Only {len(df)} valid rows remain."
        )

    return df


# =============================================================
# TRADE METRICS
# =============================================================

def calculate_trade_metrics(analyzer):
    """
    Extract trade statistics from Backtrader's TradeAnalyzer.
    """

    analysis = analyzer.get_analysis()

    # =========================================================
    # Total closed trades
    # =========================================================

    total_closed = (
        analysis
        .get("total", {})
        .get("closed", 0)
    )

    # =========================================================
    # Winning trades
    # =========================================================

    won = (
        analysis
        .get("won", {})
        .get("total", 0)
    )

    # =========================================================
    # Losing trades
    # =========================================================

    lost = (
        analysis
        .get("lost", {})
        .get("total", 0)
    )

    # =========================================================
    # Win rate
    # =========================================================

    if total_closed > 0:
        win_rate = (
            won / total_closed
        ) * 100
    else:
        win_rate = 0.0

    # =========================================================
    # Gross profit
    # =========================================================

    gross_profit = (
        analysis
        .get("won", {})
        .get("pnl", {})
        .get("total", 0.0)
    )

    # =========================================================
    # Gross loss
    # =========================================================

    gross_loss = abs(
        analysis
        .get("lost", {})
        .get("pnl", {})
        .get("total", 0.0)
    )

    # =========================================================
    # Profit factor
    # =========================================================

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            / gross_loss
        )

    elif gross_profit > 0:

        profit_factor = math.inf

    else:

        profit_factor = 0.0

    # =========================================================
    # Total trade P&L
    # =========================================================

    total_pnl = (
        analysis
        .get("pnl", {})
        .get("net", {})
        .get("total", 0.0)
    )

    # =========================================================
    # Average trade P&L
    # =========================================================

    if total_closed > 0:

        average_trade_pnl = (
            total_pnl
            / total_closed
        )

    else:

        average_trade_pnl = 0.0

    return {
        "num_trades": total_closed,
        "winning_trades": won,
        "losing_trades": lost,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "average_trade_pnl": average_trade_pnl,
    }


# =============================================================
# RUN BACKTEST
# =============================================================

def run_backtest(
    strategy_code: str,
    csv_path: str,
    initial_cash: float = 100000.0,
    commission: float = 0.0003,
    slippage: float = 0.0005,
):
    """
    Run a Backtrader backtest.

    Parameters
    ----------
    strategy_code:
        Generated Python code containing GeneratedStrategy.

    csv_path:
        Path to the NIFTY50 daily OHLCV CSV.

    initial_cash:
        Starting portfolio capital.

    commission:
        Commission as a decimal.
        Example:
            0.0003 = 0.03%

    slippage:
        Percentage-based slippage.
        Example:
            0.0005 = 0.05%
    """

    # =========================================================
    # 1. Load historical data
    # =========================================================

    df = load_nifty50_data(
        csv_path
    )

    print()
    print(
        "========== DATA LOADED =========="
    )
    print(
        f"Rows: {len(df)}"
    )
    print(
        f"Start: {df.index.min()}"
    )
    print(
        f"End:   {df.index.max()}"
    )
    print(
        f"Columns: {list(df.columns)}"
    )
    print(
        "================================="
    )
    print()

    # =========================================================
    # 2. Create Backtrader data feed
    # =========================================================

    data = bt.feeds.PandasData(
        dataname=df
    )

    # =========================================================
    # 3. Create Cerebro
    # =========================================================

    cerebro = bt.Cerebro()

    # =========================================================
    # 4. Add historical data
    # =========================================================

    cerebro.adddata(
        data
    )

    # =========================================================
    # 5. Load generated strategy
    # =========================================================

    namespace = {}

    exec(
        strategy_code,
        {
            "__builtins__": __builtins__,
            "bt": bt,
        },
        namespace,
    )

    GeneratedStrategy = namespace.get(
        "GeneratedStrategy"
    )

    if GeneratedStrategy is None:
        raise ValueError(
            "GeneratedStrategy class was not found."
        )

    cerebro.addstrategy(
        GeneratedStrategy
    )

    # =========================================================
    # 6. Configure broker
    # =========================================================

    cerebro.broker.setcash(
        initial_cash
    )

    cerebro.broker.setcommission(
        commission=commission
    )

    cerebro.broker.set_slippage_perc(
        perc=slippage
    )

    # =========================================================
    # 7. Add analyzers
    # =========================================================

    # Trade statistics
    cerebro.addanalyzer(
        bt.analyzers.TradeAnalyzer,
        _name="trades",
    )

    # Maximum drawdown
    cerebro.addanalyzer(
        bt.analyzers.DrawDown,
        _name="drawdown",
    )

    # Sharpe ratio
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        annualize=True,
    )

    # Returns
    cerebro.addanalyzer(
        bt.analyzers.Returns,
        _name="returns",
    )

    # Equity curve
    cerebro.addanalyzer(
        EquityCurveAnalyzer,
        _name="equity_curve",
    )

    # =========================================================
    # 8. Run backtest
    # =========================================================

    print(
        "========== RUNNING BACKTEST =========="
    )

    start_value = (
        cerebro.broker.getvalue()
    )

    results = cerebro.run()

    end_value = (
        cerebro.broker.getvalue()
    )

    strategy_instance = results[0]

    print(
        "========== BACKTEST FINISHED =========="
    )
    print()

    # =========================================================
    # 9. Total return
    # =========================================================

    total_return_pct = (
        (
            end_value
            - start_value
        )
        / start_value
    ) * 100

    # =========================================================
    # 10. Maximum drawdown
    # =========================================================

    drawdown_analysis = (
        strategy_instance
        .analyzers
        .drawdown
        .get_analysis()
    )

    max_drawdown_pct = (
        drawdown_analysis
        .get("max", {})
        .get("drawdown", 0.0)
    )

    # =========================================================
    # 11. Sharpe ratio
    # =========================================================

    sharpe_analysis = (
        strategy_instance
        .analyzers
        .sharpe
        .get_analysis()
    )

    sharpe_ratio = (
        sharpe_analysis
        .get("sharperatio")
    )

    # =========================================================
    # 12. Trade statistics
    # =========================================================

    trade_metrics = (
        calculate_trade_metrics(
            strategy_instance
            .analyzers
            .trades
        )
    )

    # =========================================================
    # 13. Date range
    # =========================================================

    start_date = df.index.min()
    end_date = df.index.max()

    # =========================================================
    # 14. CAGR
    # =========================================================

    days = (
        end_date
        - start_date
    ).days

    if (
        days > 0
        and start_value > 0
        and end_value > 0
    ):

        years = (
            days / 365.25
        )

        cagr_pct = (
            (
                (
                    end_value
                    / start_value
                )
                ** (1 / years)
            )
            - 1
        ) * 100

    else:

        cagr_pct = 0.0

    # =========================================================
    # 15. Extract equity curve
    # =========================================================

    equity_analysis = (
        strategy_instance
        .analyzers
        .equity_curve
        .get_analysis()
    )

    equity_curve = []

    for date, value in zip(
        equity_analysis.get(
            "dates",
            []
        ),
        equity_analysis.get(
            "values",
            []
        ),
    ):

        equity_curve.append(
            {
                "date": date,
                "value": float(value),
            }
        )

    # =========================================================
    # 16. Print equity curve information
    # =========================================================

    print(
        "========== EQUITY CURVE =========="
    )

    print(
        f"Equity curve points: "
        f"{len(equity_curve)}"
    )

    if equity_curve:

        print(
            "First point:",
            equity_curve[0]
        )

        print(
            "Last point:",
            equity_curve[-1]
        )

    print(
        "=================================="
    )
    print()

    # =========================================================
    # 17. Final result
    # =========================================================

    return {
        "initial_capital": float(
            start_value
        ),

        "final_capital": float(
            end_value
        ),

        "total_return_pct": float(
            total_return_pct
        ),

        "cagr_pct": float(
            cagr_pct
        ),

        "sharpe_ratio": (
            float(sharpe_ratio)
            if sharpe_ratio is not None
            else None
        ),

        "max_drawdown_pct": float(
            max_drawdown_pct
        ),

        "num_trades": int(
            trade_metrics[
                "num_trades"
            ]
        ),

        "winning_trades": int(
            trade_metrics[
                "winning_trades"
            ]
        ),

        "losing_trades": int(
            trade_metrics[
                "losing_trades"
            ]
        ),

        "win_rate_pct": float(
            trade_metrics[
                "win_rate_pct"
            ]
        ),

        "profit_factor": (
            float(
                trade_metrics[
                    "profit_factor"
                ]
            )
            if math.isfinite(
                trade_metrics[
                    "profit_factor"
                ]
            )
            else None
        ),

        "average_trade_pnl": float(
            trade_metrics[
                "average_trade_pnl"
            ]
        ),

        "start_date": start_date.isoformat(),

        "end_date": end_date.isoformat(),

        # NEW:
        # Data used by the React equity curve chart.
        "equity_curve": equity_curve,
    }