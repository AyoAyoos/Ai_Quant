"""
Deterministic Backtrader Strategy Generator.

The LLM produces a validated StrategySpec.
This module converts that specification into controlled
Backtrader code.

The LLM does NOT directly determine Python order handling.
"""

from app.services.strategy_schema import StrategySpec


def generate_backtrader_code(strategy: StrategySpec) -> str:

    # =========================================================
    # Extract indicator configuration
    # =========================================================

    sma_periods = []
    rsi_period = None
    volume_period = None

    for indicator in strategy.indicators:

        if indicator.type == "SMA":
            if indicator.period is not None:
                sma_periods.append(indicator.period)

        elif indicator.type == "RSI":
            rsi_period = indicator.period

        elif indicator.type == "VolumeSMA":
            volume_period = indicator.period

    sma_periods = sorted(sma_periods)

    if len(sma_periods) < 2:
        raise ValueError(
            "Strategy requires at least two SMA indicators."
        )

    fast_sma = sma_periods[0]
    slow_sma = sma_periods[1]

    if rsi_period is None:
        raise ValueError(
            "Strategy requires an RSI indicator."
        )

    if volume_period is None:
        raise ValueError(
            "Strategy requires a VolumeSMA indicator."
        )

    # =========================================================
    # Risk configuration
    # =========================================================

    risk_per_trade = strategy.risk_management.risk_per_trade
    stop_loss_pct = strategy.risk_management.stop_loss_pct
    take_profit_pct = strategy.risk_management.take_profit_pct

    if stop_loss_pct is None:
        raise ValueError(
            "A stop-loss is required for risk-based position sizing."
        )

    # =========================================================
    # Generate controlled Backtrader strategy
    # =========================================================

    code = f'''import backtrader as bt


class GeneratedStrategy(bt.Strategy):

    params = (
        ("fast_sma_period", {fast_sma}),
        ("slow_sma_period", {slow_sma}),
        ("rsi_period", {rsi_period}),
        ("volume_period", {volume_period}),
        ("risk_per_trade", {risk_per_trade}),
        ("stop_loss_pct", {stop_loss_pct}),
        ("take_profit_pct", {take_profit_pct}),
    )

    def __init__(self):

        # =====================================================
        # Indicators
        # =====================================================

        self.fast_sma = bt.indicators.SMA(
            self.data.close,
            period=self.p.fast_sma_period
        )

        self.slow_sma = bt.indicators.SMA(
            self.data.close,
            period=self.p.slow_sma_period
        )

        self.rsi = bt.indicators.RSI(
            self.data.close,
            period=self.p.rsi_period
        )

        self.volume_sma = bt.indicators.SMA(
            self.data.volume,
            period=self.p.volume_period
        )

        # Detect actual SMA crossover events.
        self.sma_crossover = bt.indicators.CrossOver(
            self.fast_sma,
            self.slow_sma
        )

        # =====================================================
        # Order tracking
        # =====================================================

        self.entry_order = None
        self.stop_order = None
        self.take_profit_order = None

        # Actual filled entry price.
        self.entry_price = None

    # =========================================================
    # Cancel protective orders
    # =========================================================

    def _cancel_exit_orders(self):

        if self.stop_order is not None:
            if self.stop_order.alive():
                self.cancel(self.stop_order)

        if self.take_profit_order is not None:
            if self.take_profit_order.alive():
                self.cancel(self.take_profit_order)

        self.stop_order = None
        self.take_profit_order = None

    # =========================================================
    # Create stop-loss and take-profit orders
    # =========================================================

    def _place_exit_orders(self):

        if self.entry_price is None:
            return

        if not self.position:
            return

        stop_price = (
            self.entry_price
            * (1.0 - self.p.stop_loss_pct)
        )

        # -----------------------------------------------------
        # Stop-loss order
        # -----------------------------------------------------

        self.stop_order = self.sell(
            exectype=bt.Order.Stop,
            price=stop_price,
            size=self.position.size,
        )

        # -----------------------------------------------------
        # Take-profit order
        #
        # OCO links the two orders so that when one executes,
        # the other is automatically cancelled.
        # -----------------------------------------------------

        if self.p.take_profit_pct is not None:

            target_price = (
                self.entry_price
                * (1.0 + self.p.take_profit_pct)
            )

            self.take_profit_order = self.sell(
                exectype=bt.Order.Limit,
                price=target_price,
                size=self.position.size,
                oco=self.stop_order,
            )

    # =========================================================
    # Order notifications
    # =========================================================

    def notify_order(self, order):

        # -----------------------------------------------------
        # Ignore submitted/accepted states.
        # -----------------------------------------------------

        if order.status in [
            order.Submitted,
            order.Accepted
        ]:
            return

        # -----------------------------------------------------
        # Entry completed
        # -----------------------------------------------------

        if order.status == order.Completed:

            if order.isbuy():

                # IMPORTANT:
                # Use the actual filled price rather than the
                # signal-bar close.
                self.entry_price = order.executed.price
                self.entry_order = None

                # Now that the position exists, place the
                # protective orders using the actual fill.
                self._place_exit_orders()

            elif order.issell():

                # A sell may have come from:
                # - stop-loss
                # - take-profit
                # - SMA/RSI market exit
                #
                # Clear position-related state.

                self.entry_price = None
                self.stop_order = None
                self.take_profit_order = None

                self.entry_order = None

            return

        # -----------------------------------------------------
        # Failed/cancelled orders
        # -----------------------------------------------------

        if order.status in [
            order.Canceled,
            order.Margin,
            order.Rejected
        ]:

            if (
                self.entry_order is not None
                and order.ref == self.entry_order.ref
            ):
                self.entry_order = None

            if (
                self.stop_order is not None
                and order.ref == self.stop_order.ref
            ):
                self.stop_order = None

            if (
                self.take_profit_order is not None
                and order.ref == self.take_profit_order.ref
            ):
                self.take_profit_order = None

    # =========================================================
    # Main strategy logic
    # =========================================================

    def next(self):

        # -----------------------------------------------------
        # Do not submit another entry while one is pending.
        # -----------------------------------------------------

        if self.entry_order is not None:
            return

        # =====================================================
        # EXIT LOGIC
        # =====================================================

        if self.position:

            # Stop-loss and take-profit are already active
            # Backtrader orders.
            #
            # We only need to handle the indicator-based exits
            # here.

            exit_crossover = self.sma_crossover < 0

            exit_rsi = self.rsi[0] > 70

            if exit_crossover or exit_rsi:

                # Cancel protective orders before manually
                # closing the position.
                self._cancel_exit_orders()

                self.close()

                return

            return

        # =====================================================
        # ENTRY LOGIC
        # =====================================================

        entry_crossover = self.sma_crossover > 0

        entry_rsi = (
            self.rsi[0] >= 50
            and self.rsi[0] <= 70
        )

        entry_volume = (
            self.data.volume[0]
            > self.volume_sma[0]
        )

        if not (
            entry_crossover
            and entry_rsi
            and entry_volume
        ):
            return

        # =====================================================
        # POSITION SIZING
        # =====================================================

        # Use current portfolio value rather than a fixed
        # initial capital amount.

        portfolio_value = self.broker.getvalue()

        risk_amount = (
            portfolio_value
            * self.p.risk_per_trade
        )

        current_price = self.data.close[0]

        stop_distance = (
            current_price
            * self.p.stop_loss_pct
        )

        if stop_distance <= 0:
            return

        # Number of shares whose theoretical stop-loss loss
        # is approximately equal to the allowed risk.
        risk_based_size = int(
            risk_amount / stop_distance
        )

        # Never purchase more than available cash allows.
        affordable_size = int(
            self.broker.getcash()
            / current_price
        )

        size = min(
            risk_based_size,
            affordable_size
        )

        if size <= 0:
            return

        # =====================================================
        # MARKET ENTRY
        # =====================================================

        self.entry_order = self.buy(
            size=size
        )
'''

    return code