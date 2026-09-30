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
    """Collectors of blocking reasons for backtested -> approved."""
    reasons = []
    if strategy.status.value != "backtested":
        reasons.append(
            f"strategy status is {strategy.status.value!r}, must be 'backtested'"
        )

    result = latest_backtest(strategy)
    if result is None:
        reasons.append("no backtest yet — run a backtest first")
        return reasons

    num_trades = result.num_trades or 0
    if num_trades < settings.approval_min_trades:
        reasons.append(
            f"only {num_trades} trade(s), need at least {settings.approval_min_trades}"
        )

    drawdown = result.max_drawdown_pct
    if drawdown is not None and drawdown > settings.approval_max_drawdown_pct:
        reasons.append(
            f"max drawdown {drawdown:.1f}% exceeds the "
            f"{settings.approval_max_drawdown_pct:.1f}% cap"
        )
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
