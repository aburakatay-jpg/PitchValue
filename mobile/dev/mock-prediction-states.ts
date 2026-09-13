import { predictionViewStates } from '@/types/prediction-state';
import type {
  PredictionStateContract,
  PredictionSurface,
} from '@/types/prediction-state';

const surfaces: PredictionSurface[] = [
  'TODAY',
  'EXPLORE',
  'MATCH_DETAIL',
  'MY_BETS',
  'PREMIUM',
];

// Contract fixtures only: no provider data and no client-side prediction math.
export const mockPredictionStates: PredictionStateContract[] =
  predictionViewStates.map((state, index) => ({
    surface: surfaces[index % surfaces.length]!,
    state,
    modelReadinessGate: state === 'PICK' ? 'PASS' : 'PENDING',
    publicDecision:
      state === 'PICK' ? 'PICK' : state === 'NO_BET' ? 'NO_BET' : null,
    blockerCodes: state === 'PICK' ? [] : ['MODEL_READINESS_PENDING'],
    premiumLocked: index % 2 === 1,
  }));
