import { config } from '@/lib/config';
import type {
  PredictionListResponse,
  TodayFixturesResponse,
} from '@/types/public-api';

export type PublicApiErrorKind =
  'API_UNAVAILABLE' | 'INVALID_RESPONSE' | 'CANCELLED';

export class PublicApiError extends Error {
  readonly kind: PublicApiErrorKind;

  constructor(kind: PublicApiErrorKind) {
    super(
      kind === 'CANCELLED' ? 'Request cancelled' : 'Public data unavailable',
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
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl.replace(/\/$/, '')}${path}`, {
      headers: { Accept: 'application/json' },
      method: 'GET',
      signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new PublicApiError('CANCELLED');
    }
    throw new PublicApiError('API_UNAVAILABLE');
  }
  if (!response.ok) throw new PublicApiError('API_UNAVAILABLE');
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new PublicApiError('INVALID_RESPONSE');
  }
  if (!validator(payload)) throw new PublicApiError('INVALID_RESPONSE');
  return payload;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
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
    value.fixtures.every(
      (fixture) =>
        isObject(fixture) &&
        typeof fixture.match_id === 'number' &&
        typeof fixture.kickoff === 'string' &&
        !Number.isNaN(Date.parse(fixture.kickoff)) &&
        typeof fixture.competition === 'string' &&
        isObject(fixture.home_team) &&
        typeof fixture.home_team.name === 'string' &&
        isObject(fixture.away_team) &&
        typeof fixture.away_team.name === 'string' &&
        typeof fixture.fixture_status === 'string' &&
        typeof fixture.public_analysis === 'string' &&
        typeof fixture.publication_state === 'string' &&
        isObject(fixture.freshness) &&
        typeof fixture.freshness.state === 'string',
    )
  );
}

export function isPredictionListResponse(
  value: unknown,
): value is PredictionListResponse {
  if (!isObject(value) || !Array.isArray(value.predictions)) return false;
  return (
    typeof value.count === 'number' &&
    value.predictions.every(
      (prediction) =>
        isObject(prediction) &&
        typeof prediction.match_id === 'number' &&
        typeof prediction.market === 'string' &&
        typeof prediction.selection === 'string' &&
        typeof prediction.edge === 'string' &&
        typeof prediction.policy_decision === 'string' &&
        (typeof prediction.bet_score === 'string' ||
          prediction.bet_score === null),
    )
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
