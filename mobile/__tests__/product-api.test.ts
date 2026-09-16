import {
  ProductServiceError,
  createGuestSession,
  getCurrentUser,
  getSavedSelections,
  logoutProductSession,
} from '@/lib/product-api';

const signal = new AbortController().signal;

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe('product service client', () => {
  afterEach(() => jest.restoreAllMocks());

  it('creates a guest session without inventing client identity', async () => {
    const payload = {
      user: { user_id: 'user-1', account_kind: 'GUEST', email: null },
      access_token: 'access',
      refresh_token: 'refresh',
      token_type: 'bearer',
      access_expires_at: '2026-09-16T12:30:00Z',
      refresh_expires_at: '2026-10-16T12:00:00Z',
    };
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(response(payload));
    await expect(createGuestSession(signal)).resolves.toEqual(payload);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/guest'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('rejects malformed session responses', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ access_token: 'only' }));
    await expect(createGuestSession(signal)).rejects.toMatchObject({
      kind: 'INVALID_RESPONSE',
    });
  });

  it('passes bearer authority explicitly without persisting it', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(
      response({
        user_id: 'user-1',
        account_kind: 'AUTHENTICATED',
        email: 'a@example.com',
      }),
    );
    await getCurrentUser('opaque-token', signal);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/me'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer opaque-token',
        }),
      }),
    );
  });

  it('keeps active and history server-scoped', async () => {
    jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ records: [], count: 0 }));
    await getSavedSelections('token', 'history', signal);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/me/bets?section=history'),
      expect.anything(),
    );
  });

  it('normalizes authorization failure and supports real logout', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValueOnce(response({}, 401));
    await expect(getCurrentUser('expired', signal)).rejects.toMatchObject({
      kind: 'UNAUTHORIZED',
    } satisfies Partial<ProductServiceError>);
    jest
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(undefined, 204));
    await expect(
      logoutProductSession('token', signal),
    ).resolves.toBeUndefined();
  });
});
