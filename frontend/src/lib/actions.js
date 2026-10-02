/**
 * Status → allowed-actions matrix, mirroring the backend's gate rules in
 * app/services/deployment_gate.py. The UI drives every button from this, and
 * every page uses `explainUnavailable` to say *why* an action does not apply
 * instead of hiding it.
 */
export const ACTION_MATRIX = {
  draft: { backtest: true, approve: false, reject: true, deploy: false, stop: false },
  backtested: { backtest: true, approve: true, reject: true, deploy: false, stop: false },
  approved: { backtest: false, approve: false, reject: false, deploy: true, stop: false },
  paper_trading: { backtest: false, approve: false, reject: false, deploy: false, stop: true },
  rejected: { backtest: false, approve: false, reject: false, deploy: false, stop: false },
}

export function canPerform(status, action) {
  return ACTION_MATRIX[status]?.[action] === true
}

const REASONS = {
  backtest: {
    approved: 'Re-running the backtest is only offered while the strategy is a draft or freshly backtested. Deploy or stop the current deployment first, then the strategy returns to approved and the backtest can be repeated.',
    paper_trading: 'A backtest cannot run while a deployment is active. Stop the deployment to return the strategy to approved, then re-run it.',
    rejected: 'A rejected strategy is read-only. Create a new strategy in chat instead.',
  },
  approve: {
    draft: 'Approval requires a backtest. Run one first so the gate has metrics to read.',
    approved: 'This strategy is already approved.',
    paper_trading: 'An active deployment already exists. Stop it before approving again.',
    rejected: 'A rejected strategy cannot be approved.',
  },
  reject: {
    approved: 'Rejection is only possible from draft or backtested. An approved strategy can only be rejected by removing it from deployment first — and the API has no such transition.',
    paper_trading: 'Stop the active deployment before rejecting.',
    rejected: 'This strategy is already rejected.',
  },
  deploy: {
    draft: 'Deployment requires approval, which requires a backtest that passes the quality gate.',
    backtested: 'Run the approval gate first. The backend refuses to deploy a strategy that is not approved.',
    paper_trading: 'A deployment is already active for this strategy. Only one is allowed at a time.',
    rejected: 'A rejected strategy cannot be deployed.',
  },
  stop: {
    draft: 'There is no deployment to stop at this stage.',
    backtested: 'There is no deployment to stop at this stage.',
    approved: 'No deployment is active, so there is nothing to stop.',
    rejected: 'A rejected strategy was never deployed.',
  },
}

/** Human-readable reason an action is unavailable, or null when it is allowed. */
export function explainUnavailable(status, action) {
  if (canPerform(status, action)) return null
  const byStatus = REASONS[action] ?? {}
  return byStatus[status] ?? `This action does not apply while the strategy is ${status}.`
}