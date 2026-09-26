import { config } from '@/lib/config';
import type {
  MatchDetailResponse,
  PredictionListResponse,
  TodayFixturesResponse,
} from '@/types/public-api';
import {
  finalCheckStates,
  freshnessStates,
  publicMarketStates,
} from '@/types/public-api';

export type PublicApiErrorKind =
  'API_UNAVAILABLE' | 'INVALID_RESPONSE' | 'NOT_FOUND' | 'CANCELLED';

export class PublicApiError extends Error {
  readonly kind: PublicApiErrorKind;

  constructor(kind: PublicApiErrorKind) {
    super(
      kind === 'CANCELLED'
        ? 'Request cancelled'
        : kind === 'NOT_FOUND'
          ? 'Public resource not found'
          : 'Public data unavailable',
    );
    this.name = 'PublicApiError';
    this.kind = kind;
  }
}

type Validator<T> = (value: unknown) => value is T;

async function request<T>(
  path: string,
  signal: AbortSignal,
  validator: Validator<T>,
): Promise<T> {
  if (config.apiBaseUrl === null) {
    if (__DEV__)
      console.log(`[API] ${path} blocked: API_UNAVAILABLE (No valid base URL)`);
    throw new PublicApiError('API_UNAVAILABLE');
  }
  let response: Response;
  const fullUrl = `${config.apiBaseUrl.replace(/\/$/, '')}${path}`;
  if (__DEV__) console.log(`[API] Fetching ${fullUrl}`);
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    signal.addEventListener('abort', () => {
      clearTimeout(timeout);
      controller.abort();
    });

    response = await fetch(fullUrl, {
      headers: { Accept: 'application/json' },
      method: 'GET',
      signal: controller.signal,
    });
    clearTimeout(timeout);
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      if (signal.aborted) {
        if (__DEV__) console.log(`[API] ${path} CANCELLED`);
        throw new PublicApiError('CANCELLED');
      } else {
        if (__DEV__) console.log(`[API] ${path} NETWORK TIMEOUT`);
        throw new PublicApiError('API_UNAVAILABLE');
      }
    }
    if (__DEV__)
      console.log(
        `[API] ${path} NETWORK FAILURE: ${error instanceof Error ? error.message : 'Unknown'}`,
      );
    throw new PublicApiError('API_UNAVAILABLE');
  }
  if (!response.ok) {
    if (__DEV__) console.log(`[API] ${path} HTTP ${response.status}`);
    throw new PublicApiError(
      response.status === 404 ? 'NOT_FOUND' : 'API_UNAVAILABLE',
    );
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    if (__DEV__)
      console.log(`[API] ${path} INVALID_RESPONSE (JSON parse failed)`);
    throw new PublicApiError('INVALID_RESPONSE');
  }
  if (!validator(payload)) {
    if (__DEV__)
      console.log(`[API] ${path} INVALID_RESPONSE (Schema validation failed)`);
    throw new PublicApiError('INVALID_RESPONSE');
  }
  return payload;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === 'string' || value === null;
}

function isNullableNumber(value: unknown): value is number | null {
  return typeof value === 'number' || value === null;
}

function isAllowedString(
  value: unknown,
  allowed: readonly string[],
): value is string {
  return typeof value === 'string' && allowed.includes(value);
}

function isFixtureSummary(
  value: unknown,
): value is TodayFixturesResponse['fixtures'][number] {
  return (
    isObject(value) &&
    typeof value.match_id === 'number' &&
    typeof value.kickoff === 'string' &&
    !Number.isNaN(Date.parse(value.kickoff)) &&
    typeof value.competition === 'string' &&
    isObject(value.home_team) &&
    typeof value.home_team.name === 'string' &&
    isObject(value.away_team) &&
    typeof value.away_team.name === 'string' &&
    typeof value.fixture_status === 'string' &&
    isAllowedString(value.data_availability, [
      'AVAILABLE',
      'DATA_INSUFFICIENT',
      'STALE',
      'PROVIDER_UNAVAILABLE',
    ]) &&
    isAllowedString(value.public_analysis, [
      'AVAILABLE_PUBLIC',
      'NO_PUBLIC_ANALYSIS',
      'DATA_INSUFFICIENT',
    ]) &&
    isAllowedString(value.publication_state, [
      'PICK',
      'WATCHLIST',
      'NO_BET',
      'DATA_INSUFFICIENT',
      'NO_PUBLIC_ANALYSIS',
    ]) &&
    isAllowedString(value.final_check, finalCheckStates) &&
    isObject(value.freshness) &&
    isAllowedString(value.freshness.state, freshnessStates) &&
    isNullableString(value.freshness.source_last_seen_at) &&
    isNullableString(value.freshness.fixture_refresh_at) &&
    typeof value.freshness.evidence_source === 'string'
  );
}

function isPublicPrediction(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.match_id === 'number' &&
    typeof value.market === 'string' &&
    typeof value.selection === 'string' &&
    typeof value.model_probability === 'string' &&
    typeof value.probability_source === 'string' &&
    typeof value.prediction_as_of === 'string' &&
    typeof value.generated_at === 'string' &&
    typeof value.decimal_odds === 'string' &&
    typeof value.no_vig_market_probability === 'string' &&
    typeof value.edge === 'string' &&
    typeof value.policy_decision === 'string' &&
    isNullableString(value.score_class) &&
    isNullableString(value.bet_score) &&
    typeof value.bet_score_completeness === 'string' &&
    Array.isArray(value.blockers) &&
    value.blockers.every((blocker) => typeof blocker === 'string')
  );
}

export function isTodayFixturesResponse(
  value: unknown,
): value is TodayFixturesResponse {
  if (!isObject(value) || !Array.isArray(value.fixtures)) return false;
  return (
    typeof value.fixture_date === 'string' &&
    typeof value.timezone === 'string' &&
    typeof value.state === 'string' &&
    typeof value.count === 'number' &&
    value.fixtures.every(isFixtureSummary)
  );
}

export function isPredictionListResponse(
  value: unknown,
): value is PredictionListResponse {
  if (!isObject(value) || !Array.isArray(value.predictions)) return false;
  return (
    typeof value.count === 'number' &&
    value.predictions.every(isPublicPrediction)
  );
}

export function isMatchDetailResponse(
  value: unknown,
): value is MatchDetailResponse {
  if (!isFixtureSummary(value)) return false;
  const candidate = value as unknown as Record<string, unknown>;
  return (
    (candidate.score === null ||
      (isObject(candidate.score) &&
        typeof candidate.score.home === 'number' &&
        typeof candidate.score.away === 'number' &&
        isNullableString(candidate.score.result))) &&
    (candidate.statistics === null ||
      (isObject(candidate.statistics) &&
        isNullableNumber(candidate.statistics.home_shots) &&
        isNullableNumber(candidate.statistics.away_shots) &&
        isNullableNumber(candidate.statistics.home_shots_on_target) &&
        isNullableNumber(candidate.statistics.away_shots_on_target) &&
        isNullableString(candidate.statistics.home_possession) &&
        isNullableString(candidate.statistics.away_possession) &&
        isNullableNumber(candidate.statistics.home_corners) &&
        isNullableNumber(candidate.statistics.away_corners))) &&
    isAllowedString(candidate.statistics_state, [
      'AVAILABLE',
      'DATA_INSUFFICIENT',
      'STALE',
      'PROVIDER_UNAVAILABLE',
    ]) &&
    Array.isArray(candidate.markets) &&
    candidate.markets.every(
      (market) =>
        isObject(market) &&
        typeof market.market === 'string' &&
        isNullableString(market.line) &&
        isAllowedString(market.state, publicMarketStates) &&
        isNullableString(market.score) &&
        typeof market.score_completeness === 'string',
    ) &&
    Array.isArray(candidate.public_predictions) &&
    candidate.public_predictions.every(isPublicPrediction)
  );
}

export function getTodayFixtures(
  signal: AbortSignal,
): Promise<TodayFixturesResponse> {
  return request('/api/v1/fixtures/today', signal, isTodayFixturesResponse);
}

export function getExplorePredictions(
  signal: AbortSignal,
): Promise<PredictionListResponse> {
  return request('/api/v1/predictions', signal, isPredictionListResponse);
}

export function getMatchDetail(
  matchId: number,
  signal: AbortSignal,
): Promise<MatchDetailResponse> {
  if (!Number.isSafeInteger(matchId) || matchId <= 0) {
    return Promise.reject(new PublicApiError('NOT_FOUND'));
  }
  return request(`/api/v1/matches/${matchId}`, signal, isMatchDetailResponse);
}
