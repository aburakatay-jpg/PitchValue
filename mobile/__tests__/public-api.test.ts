import {
  getExplorePredictions,
  getMatchDetail,
  getTodayFixtures,
  PublicApiError,
} from '@/lib/public-api';

import { makeMatchDetail } from '../test-support/match-detail-fixtures';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  jest.restoreAllMocks();
});

describe('public API client', () => {
  it('loads Today through the canonical read-only endpoint', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        fixture_date: '2026-09-14',
        timezone: 'Europe/Istanbul',
        state: 'NO_FIXTURES',
        fixtures: [],
        count: 0,
      }),
    });
    await expect(
      getTodayFixtures(new AbortController().signal),
    ).resolves.toMatchObject({
      count: 0,
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/fixtures\/today$/),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('loads Explore only through the publication endpoint', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ predictions: [], count: 0 }),
    });
    await expect(
      getExplorePredictions(new AbortController().signal),
    ).resolves.toEqual({ predictions: [], count: 0 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/predictions$/),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('loads Match Detail through the canonical match endpoint', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => makeMatchDetail(),
    });
    await expect(
      getMatchDetail(321, new AbortController().signal),
    ).resolves.toMatchObject({ match_id: 321 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/matches\/321$/),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('maps missing matches to a public-safe not-found error', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 404 });
    await expect(
      getMatchDetail(321, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'NOT_FOUND' });
  });

  it('rejects invalid IDs before a request is issued', async () => {
    globalThis.fetch = jest.fn();
    await expect(
      getMatchDetail(0, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'NOT_FOUND' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('normalizes network and server failures without leaking raw details', async () => {
    globalThis.fetch = jest
      .fn()
      .mockRejectedValue(new Error('SQL password secret'));
    const failure = getTodayFixtures(new AbortController().signal);
    await expect(failure).rejects.toBeInstanceOf(PublicApiError);
    await expect(failure).rejects.not.toThrow(/SQL|password|secret/);

    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });
    await expect(
      getExplorePredictions(new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'API_UNAVAILABLE' });
  });

  it('rejects malformed successful payloads explicitly', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ predictions: 'not-an-array', count: 1 }),
    });
    await expect(
      getExplorePredictions(new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'INVALID_RESPONSE' });
  });

  it('rejects a malformed Match Detail response', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...makeMatchDetail(), markets: 'not-an-array' }),
    });
    await expect(
      getMatchDetail(321, new AbortController().signal),
    ).rejects.toMatchObject({ kind: 'INVALID_RESPONSE' });
  });
});
