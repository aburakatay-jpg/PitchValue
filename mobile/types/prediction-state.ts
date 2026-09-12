export const predictionViewStates = [
  'LOADING',
  'API_UNAVAILABLE',
  'EMPTY',
  'DATA_INSUFFICIENT',
  'NO_BET',
  'WATCHLIST',
  'PICK',
  'SCORE_INCOMPLETE',
  'CHANGED',
  'HISTORICAL',
  'STALE',
] as const;

export type PredictionViewState = (typeof predictionViewStates)[number];
export type PredictionSurface =
  'TODAY' | 'EXPLORE' | 'MATCH_DETAIL' | 'MY_BETS' | 'PREMIUM';
export type ModelReadinessGate = 'PASS' | 'PENDING' | 'FAIL';

export type PredictionStateContract = Readonly<{
  surface: PredictionSurface;
  state: PredictionViewState;
  modelReadinessGate: ModelReadinessGate;
  publicDecision: 'NO_BET' | 'WATCHLIST' | 'PICK' | null;
  internalShadowDecision: 'NO_BET' | 'WATCHLIST' | 'PICK' | null;
  blockerCodes: readonly string[];
  premiumLocked: boolean;
}>;

export function canExposePublicPick(
  contract: PredictionStateContract,
): boolean {
  return (
    contract.publicDecision === 'PICK' && contract.modelReadinessGate === 'PASS'
  );
}

export function validatePredictionState(
  contract: PredictionStateContract,
): void {
  if (
    contract.publicDecision === 'PICK' &&
    contract.modelReadinessGate !== 'PASS'
  ) {
    throw new Error('public PICK requires MODEL_READINESS_GATE PASS');
  }
  if (contract.state === 'PICK' && !canExposePublicPick(contract)) {
    throw new Error('PICK view state requires an eligible public decision');
  }
  if (contract.blockerCodes.some((code) => code.trim().length === 0)) {
    throw new Error('blocker codes must be stable nonblank values');
  }
}
