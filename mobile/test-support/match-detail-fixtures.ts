import type {
  FinalCheckState,
  MatchDetailResponse,
  PublicMarketAvailability,
  PublicMarketState,
  PublicPrediction,
} from '@/types/public-api';

export const v1MarketNames = [
  '1X2',
  'O/U 1.5',
  'O/U 2.5',
  'BTTS',
  'Double Chance',
  'Home Team Goals O/U 0.5',
  'Home Team Goals O/U 1.5',
  'Away Team Goals O/U 0.5',
  'Away Team Goals O/U 1.5',
] as const;

export function makePrediction(
  overrides: Partial<PublicPrediction> = {},
): PublicPrediction {
  return {
    match_id: 321,
    market: 'match_result',
    selection: 'HOME',
    model_probability: '0.51',
    probability_source: 'RAW ML',
    prediction_as_of: '2026-09-14T08:00:00Z',
    generated_at: '2026-09-14T08:01:00Z',
    decimal_odds: '2.10',
    no_vig_market_probability: '0.47',
    edge: '0.04',
    policy_decision: 'PICK',
    score_class: 'PICK',
    bet_score: '76',
    bet_score_completeness: 'COMPLETE',
    blockers: [],
    ...overrides,
  };
}

export function makeMarket(
  market: string,
  state: PublicMarketState = 'NOT_PUBLISHED',
  overrides: Partial<PublicMarketAvailability> = {},
): PublicMarketAvailability {
  return {
    market,
    line: null,
    state,
    score: null,
    score_completeness: 'UNAVAILABLE',
    ...overrides,
  };
}

export function makeMatchDetail(
  overrides: Partial<MatchDetailResponse> = {},
): MatchDetailResponse {
  return {
    match_id: 321,
    competition: 'Premier League',
    kickoff: '2026-09-14T17:00:00Z',
    home_team: { name: 'Very Long Canonical Home United' },
    away_team: { name: 'Canonical Away Athletic' },
    fixture_status: 'SCHEDULED',
    data_availability: 'AVAILABLE',
    public_analysis: 'AVAILABLE_PUBLIC',
    publication_state: 'PICK',
    final_check: 'FINAL_CHECK_UNAVAILABLE',
    freshness: {
      state: 'FRESH',
      source_last_seen_at: '2026-09-14T07:00:00Z',
      fixture_refresh_at: '2026-09-14T07:00:00Z',
      evidence_source: 'fixture_refresh_event',
    },
    score: null,
    statistics: null,
    statistics_state: 'DATA_INSUFFICIENT',
    markets: v1MarketNames.map((name) => makeMarket(name)),
    public_predictions: [makePrediction()],
    ...overrides,
  };
}

export function withFinalCheck(state: FinalCheckState): MatchDetailResponse {
  return makeMatchDetail({ final_check: state });
}
