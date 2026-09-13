import {
  finalCheckStates,
  freshnessStates,
  predictionStates,
  publicMarketStates,
  type PublicMarketAvailability,
} from '@/types/public-api';

describe('public API contract foundation', () => {
  it('preserves canonical prediction and Final Check states', () => {
    expect(predictionStates).toEqual([
      'PICK',
      'WATCHLIST',
      'NO_BET',
      'DATA_INSUFFICIENT',
      'SCORE_INCOMPLETE',
    ]);
    expect(finalCheckStates).toEqual([
      'CONFIRMED',
      'CHANGED',
      'WITHDRAWN',
      'FINAL_CHECK_UNAVAILABLE',
    ]);
  });

  it('keeps backend freshness and market states distinct', () => {
    expect(freshnessStates).toEqual([
      'FRESH',
      'STALE',
      'UNAVAILABLE',
      'FAILED',
    ]);
    expect(publicMarketStates).toContain('DATA_INSUFFICIENT');
    expect(publicMarketStates).toContain('SCORE_INCOMPLETE');
    expect(publicMarketStates).toContain('NOT_PUBLISHED');
  });

  it('represents an incomplete score as null rather than zero', () => {
    const market: PublicMarketAvailability = {
      market: '1X2',
      line: null,
      state: 'SCORE_INCOMPLETE',
      score: null,
      score_completeness: 'PARTIAL',
    };
    expect(market.score).toBeNull();
    expect(market.state).toBe('SCORE_INCOMPLETE');
  });
});
