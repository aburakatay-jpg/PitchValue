import {
  getExplorePredictions,
  getTodayFixtures,
  PublicApiError,
} from '@/lib/public-api';

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
});
