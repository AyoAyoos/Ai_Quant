import traceback

import backtrader as bt


class GeneratedStrategy(bt.Strategy):
    def next(self):
        print(
            "next bar len=", len(self),
            "pos_size=", (self.position.size if self.position else 0),
            "close=", self.data.close[0],
            flush=True,
        )
        if not self.position:
            print("  -> buy", flush=True)
            self.buy()
        else:
            print("  -> sell", flush=True)
            self.sell()
