import pytest

from app.services.strategy_runner import GuardrailError, check_guardrails

ALLOWED = """import backtrader as bt


class GeneratedStrategy(bt.Strategy):
    params = (("rsi_period", 14),)

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

    def next(self):
        if not self.position and self.rsi < 30:
            self.buy()
        elif self.position and self.rsi > 70:
            self.sell()
"""


def test_accepts_clean_strategy_code():
    check_guardrails(ALLOWED)  # must not raise


@pytest.mark.parametrize(
    "code",
    [
        "import os\nprint(os.getcwd())",
        "from subprocess import run",
        "from app.services.llm_service import chat_completion",
        "exec('print(1)')",
        "eval('1+1')",
        "open('enemy.txt')",
        "input('password?')",
        "compile('x', '<s>', 'exec')",
        "__import__('os')",
        "class A:\n    def f(self):\n        return self.__class__",
        "print(__globals__)",
        "object().__getattribute__",
    ],
)
def test_rejects_escape_hatches(code):
    with pytest.raises(GuardrailError):
        check_guardrails(code)


def test_rejects_malformed_python():
    with pytest.raises(GuardrailError):
        check_guardrails("def broken(:")


def test_rejects_without_strategy_executing():
    # Guardrail fires statically before any of the code can run.
    with pytest.raises(GuardrailError):
        check_guardrails("import backtrader as bt\nexec('import os')")