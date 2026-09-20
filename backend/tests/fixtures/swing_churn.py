import backtrader as bt


class GeneratedStrategy(bt.Strategy):
    params = (("hold_bars", 5),)

    def start(self):
        self.held = 0

    def next(self):
        if not self.position:
            self.buy()
        else:
            self.held += 1
            if self.held >= self.p.hold_bars:
                self.sell()
                self.held = 0
