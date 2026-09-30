"""Unit tests for reply display cleaning.

The stored message keeps the raw LLM reply (finalize + conversation memory
need it). These cover only the client-facing copy: no STRATEGY_READY marker,
no Name/Description headers, no code dumps.
"""
from app.services.strategy_extractor import clean_reply_for_display

STRICT = """STRATEGY_READY
Name: Bollinger Breakout
Description: Buys NIFTY 50 on upper-band breaks.
```python
import backtrader as bt
class GeneratedStrategy(bt.Strategy):
    def next(self):
        self.buy()
```
"""

STRICT_WITH_PROSE = f"""Here is your strategy:

{STRICT}
Let me know if you want different parameters."""

FREEFORM = """Sounds good! Here is the implementation:

```python
import backtrader as bt
class RSI(bt.Strategy):
    def next(self):
        self.buy()
```

This buys on RSI dips."""


class TestCleanReplyForDisplay:
    def test_strict_format_collapses_to_confirmation(self):
        out = clean_reply_for_display(STRICT, "Bollinger Breakout")
        assert "STRATEGY_READY" not in out
        assert "Name:" not in out
        assert "Description:" not in out
        assert "```python" not in out
        assert "GeneratedStrategy" not in out
        assert "Bollinger Breakout" in out

    def test_strict_format_keeps_surrounding_prose(self):
        out = clean_reply_for_display(STRICT_WITH_PROSE, "Bollinger Breakout")
        assert "Here is your strategy" in out
        assert "different parameters" in out
        assert "STRATEGY_READY" not in out
        assert "```python" not in out

    def test_freeform_code_becomes_placeholder(self):
        out = clean_reply_for_display(FREEFORM, "RSI Dip Buyer")
        assert "Sounds good" in out
        assert "buys on RSI dips" in out
        assert "```python" not in out
        assert "self.buy()" not in out
        assert "RSI Dip Buyer" in out

    def test_plain_prose_passes_through(self):
        reply = "What risk level are you comfortable with?"
        assert clean_reply_for_display(reply, "X") == reply

    def test_empty_after_cleaning_falls_back_to_confirmation(self):
        out = clean_reply_for_display("STRATEGY_READY", "Lonely Strategy")
        assert "Lonely Strategy" in out
