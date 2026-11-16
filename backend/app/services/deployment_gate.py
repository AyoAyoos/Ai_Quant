"""
Paper-trading deployment gate.

Pure transition logic for the strategy lifecycle:

    draft -> backtested -> approved -> paper_trading
       \\         \\                      ^
        \\-> rejected                      \\-> approved (on stop)

Approval is a quality gate over the latest backtest (it must exist, show
real trading activity, and stay within a drawdown cap). Deployment
re-validates the guardrails on the current code and refuses when a
deployment is already active. Every function returns a list of blocking
reasons — empty means the transition is allowed — so routers stay thin
and the rules are unit-testable without a database.
"""
from app.config import settings
from app.models import DeploymentStatus
from app.services.strategy_runner import GuardrailError, check_guardrails


def latest_backtest(strategy):
    results = list(strategy.backtest_results or [])
    if not results:
        return None
    return max(results, key=lambda r: r.created_at)


def active_deployment(strategy):
    for dep in strategy.deployments or []:
        if dep.status == DeploymentStatus.active:
            return dep
    return None


def check_approval(strategy) -> list[str]:
    """Collectors of blocking reasons for backtested -> approved.

    Metrics that were never recorded (NULL columns, no backtest row) are read
    as "no evidence" rather than as a crash or a silent pass: `num_trades` and
    `max_drawdown_pct` may be None, and `latest_backtest` may be None entirely.
    Every reason is written for the human reading it on the approval page,
    since these strings are returned verbatim as `detail.reasons`.
    """
    reasons = []
    if strategy.status.value != "backtested":
        reasons.append(
            f"strategy status is {strategy.status.value!r}, must be 'backtested'"
        )

    result = latest_backtest(strategy)
    if result is None:
        reasons.append("no backtest yet — run a backtest first")
        return reasons

    # Minimum closed trades prerequisite
    num_trades = result.num_trades or 0
    if num_trades < 10:
        reasons.append(
            f"Approval requires at least 10 closed trades. Current closed trades: {num_trades}."
        )
        return reasons

    # Gather metrics for the four criteria
    max_drawdown = result.max_drawdown_pct
    win_rate = result.win_rate_pct
    raw = result.raw_metrics or {}
    sharpe = raw.get('sharpe')

    criteria = []
    # 1. Max drawdown under 25%
    c1_pass = max_drawdown is not None and max_drawdown < 25
    criteria.append(('Max drawdown under 25%', c1_pass, max_drawdown))

    # 2. At least 10 closed trades
    c2_pass = num_trades >= 10
    criteria.append(('At least 10 closed trades', c2_pass, num_trades))

    # 3. Sharpe ratio above 0.5
    c3_pass = sharpe is not None and sharpe > 0.5
    criteria.append(('Sharpe ratio above 0.5', c3_pass, sharpe))

    # 4. Win rate above 40%
    c4_pass = win_rate is not None and win_rate > 40
    criteria.append(('Win rate above 40%', c4_pass, win_rate))

    passed = sum(1 for _, p, _ in criteria if p)
    if passed < 2:
        failed = [name for name, p, _ in criteria if not p]
        reasons.append(
            f"Approval requires at least 2 of 4 criteria to pass. Passed {passed}/4. "
            f"Failed criteria: {', '.join(failed)}."
        )
        # Add details for each failed criterion for clarity
        if not c1_pass:
            if max_drawdown is None:
                reasons.append("Max drawdown under 25%: no drawdown was recorded.")
            else:
                reasons.append(f"Max drawdown under 25%: drawdown reached {max_drawdown:.2f}%, above the 25% ceiling.")
        if not c2_pass:
            reasons.append(f"At least 10 closed trades: only {num_trades} closed trade(s) — too thin to judge.")
        if not c3_pass:
            if sharpe is None:
                reasons.append("Sharpe ratio above 0.5: no Sharpe ratio was recorded.")
            else:
                reasons.append(f"Sharpe ratio above 0.5: Sharpe was {sharpe:.2f}.")
        if not c4_pass:
            if win_rate is None:
                reasons.append("Win rate above 40%: no win rate was recorded.")
            else:
                reasons.append(f"Win rate above 40%: win rate was {win_rate:.2f}%.")
    return reasons


def check_deploy(strategy) -> list[str]:
    """Collectors of blocking reasons for approved -> paper_trading."""
    reasons = []
    if strategy.status.value != "approved":
        reasons.append(
            f"strategy status is {strategy.status.value!r}, must be 'approved'"
        )

    if not strategy.generated_code:
        reasons.append("strategy has no generated code")
    else:
        try:
            check_guardrails(strategy.generated_code)
        except GuardrailError as exc:
            reasons.append(f"guardrail rejection: {exc}")

    if active_deployment(strategy) is not None:
        reasons.append("strategy already has an active deployment")
    return reasons
