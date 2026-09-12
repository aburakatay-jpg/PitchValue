import type {
  PredictionStateContract,
  PredictionSurface,
  PredictionViewState,
} from '@/types/prediction-state';

const surfaces: PredictionSurface[] = [
  'TODAY',
  'EXPLORE',
  'MATCH_DETAIL',
  'MY_BETS',
  'PREMIUM',
];

const states: PredictionViewState[] = [
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
];

// Contract fixtures only: no provider data and no client-side prediction math.
export const mockPredictionStates: PredictionStateContract[] = states.map(
  (state, index) => ({
    surface: surfaces[index % surfaces.length]!,
    state,
    modelReadinessGate: state === 'PICK' ? 'PASS' : 'PENDING',
    publicDecision:
      state === 'PICK' ? 'PICK' : state === 'NO_BET' ? 'NO_BET' : null,
    internalShadowDecision: state === 'PICK' ? 'PICK' : null,
    blockerCodes: state === 'PICK' ? [] : ['MODEL_READINESS_PENDING'],
    premiumLocked: index % 2 === 1,
  }),
);
