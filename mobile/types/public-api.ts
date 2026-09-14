export const predictionStates = [
  'PICK',
  'WATCHLIST',
  'NO_BET',
  'DATA_INSUFFICIENT',
  'SCORE_INCOMPLETE',
] as const;

export const finalCheckStates = [
  'CONFIRMED',
  'CHANGED',
  'WITHDRAWN',
  'FINAL_CHECK_UNAVAILABLE',
] as const;

export const freshnessStates = [
  'FRESH',
  'STALE',
  'UNAVAILABLE',
  'FAILED',
] as const;

export const publicMarketStates = [
  'AVAILABLE_PUBLIC',
  'ANALYSIS_UNAVAILABLE',
  'DATA_INSUFFICIENT',
  'SCORE_INCOMPLETE',
  'NOT_SUPPORTED',
  'NOT_PUBLISHED',
] as const;

export type PredictionState = (typeof predictionStates)[number];
export type FinalCheckState = (typeof finalCheckStates)[number];
export type FreshnessState = (typeof freshnessStates)[number];
export type PublicMarketState = (typeof publicMarketStates)[number];

export type PublicFixtureSummary = Readonly<{
  match_id: number;
  competition: string;
  kickoff: string;
  home_team: Readonly<{ name: string }>;
  away_team: Readonly<{ name: string }>;
  fixture_status: string;
  data_availability:
    'AVAILABLE' | 'DATA_INSUFFICIENT' | 'STALE' | 'PROVIDER_UNAVAILABLE';
  public_analysis:
    'AVAILABLE_PUBLIC' | 'NO_PUBLIC_ANALYSIS' | 'DATA_INSUFFICIENT';
  publication_state:
    | 'PICK'
    | 'WATCHLIST'
    | 'NO_BET'
    | 'DATA_INSUFFICIENT'
    | 'NO_PUBLIC_ANALYSIS';
  final_check: FinalCheckState;
  freshness: Readonly<{
    state: FreshnessState;
    source_last_seen_at: string | null;
    fixture_refresh_at: string | null;
    evidence_source: string;
  }>;
}>;

export type PublicMarketAvailability = Readonly<{
  market: string;
  line: string | null;
  state: PublicMarketState;
  score: string | null;
  score_completeness: string;
}>;

export type PublicPrediction = Readonly<{
  match_id: number;
  market: string;
  selection: string;
  model_probability: string;
  probability_source: string;
  prediction_as_of: string;
  generated_at: string;
  decimal_odds: string;
  no_vig_market_probability: string;
  edge: string;
  policy_decision: string;
  score_class: string | null;
  bet_score: string | null;
  bet_score_completeness: string;
  blockers: readonly string[];
}>;

export type PredictionListResponse = Readonly<{
  predictions: readonly PublicPrediction[];
  count: number;
}>;

export type PublicApiErrorResponse = Readonly<{
  error: Readonly<{
    code:
      | 'VALIDATION_ERROR'
      | 'NOT_FOUND'
      | 'SERVICE_UNAVAILABLE'
      | 'INTERNAL_ERROR';
    message: string;
    request_id: string;
  }>;
}>;

export type TodayFixturesResponse = Readonly<{
  fixture_date: string;
  timezone: string;
  state:
    | 'FIXTURES_AVAILABLE'
    | 'NO_FIXTURES'
    | 'STALE_FIXTURE_DATA'
    | 'PROVIDER_UNAVAILABLE';
  fixtures: readonly PublicFixtureSummary[];
  count: number;
}>;

export type MatchDetailResponse = PublicFixtureSummary &
  Readonly<{
    score: Readonly<{
      home: number;
      away: number;
      result: string | null;
    }> | null;
    statistics: Readonly<{
      home_shots: number | null;
      away_shots: number | null;
      home_shots_on_target: number | null;
      away_shots_on_target: number | null;
      home_possession: string | null;
      away_possession: string | null;
      home_corners: number | null;
      away_corners: number | null;
    }> | null;
    statistics_state:
      'AVAILABLE' | 'DATA_INSUFFICIENT' | 'STALE' | 'PROVIDER_UNAVAILABLE';
    markets: readonly PublicMarketAvailability[];
    public_predictions: readonly PublicPrediction[];
  }>;
