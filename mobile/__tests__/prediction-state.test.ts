import { mockPredictionStates } from '@/dev/mock-prediction-states';
import {
  canExposePublicPick,
  predictionViewStates,
  type PredictionStateContract,
  validatePredictionState,
} from '@/types/prediction-state';

describe('provider-independent prediction states', () => {
  it('covers every required state and all planned contract surfaces', () => {
    expect(mockPredictionStates.map((item) => item.state)).toEqual(
      predictionViewStates,
    );
    expect(new Set(mockPredictionStates.map((item) => item.surface))).toEqual(
      new Set(['TODAY', 'EXPLORE', 'MATCH_DETAIL', 'MY_BETS', 'PREMIUM']),
    );
  });

  it('blocks public PICK before model readiness passes while retaining shadow state', () => {
    const blocked: PredictionStateContract = {
      surface: 'MATCH_DETAIL',
      state: 'DATA_INSUFFICIENT',
      modelReadinessGate: 'PENDING',
      publicDecision: null,
      internalShadowDecision: 'PICK',
      blockerCodes: ['MODEL_READINESS_PENDING'],
      premiumLocked: false,
    };
    validatePredictionState(blocked);
    expect(canExposePublicPick(blocked)).toBe(false);
  });

  it('rejects a public PICK when model readiness is not PASS', () => {
    const invalid: PredictionStateContract = {
      surface: 'TODAY',
      state: 'PICK',
      modelReadinessGate: 'PENDING',
      publicDecision: 'PICK',
      internalShadowDecision: 'PICK',
      blockerCodes: [],
      premiumLocked: false,
    };
    expect(() => validatePredictionState(invalid)).toThrow(
      'public PICK requires MODEL_READINESS_GATE PASS',
    );
  });

  it('contains no client-side probability, edge, no-vig, or Bet Score fields', () => {
    const serialized = JSON.stringify(mockPredictionStates);
    expect(serialized).not.toMatch(
      /probability|noVig|edge|betScore|publicationEligible/,
    );
  });
});
