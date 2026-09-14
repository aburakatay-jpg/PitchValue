import { act, renderHook, waitFor } from '@testing-library/react-native';

import { usePublicResource } from '@/hooks/use-public-resource';
import { PublicApiError } from '@/lib/public-api';

describe('retained public resource', () => {
  it('retains successful data when a refresh fails', async () => {
    const loader = jest
      .fn<Promise<string>, [AbortSignal]>()
      .mockResolvedValueOnce('persisted public data')
      .mockRejectedValueOnce(new PublicApiError('API_UNAVAILABLE'));
    const hook = await renderHook(() => usePublicResource(loader));
    await waitFor(() =>
      expect(hook.result.current.data).toBe('persisted public data'),
    );
    await act(async () => hook.result.current.refresh());
    expect(hook.result.current.data).toBe('persisted public data');
    expect(hook.result.current.error?.kind).toBe('API_UNAVAILABLE');
  });

  it('aborts the active request when the surface unmounts', async () => {
    let signal: AbortSignal | undefined;
    const loader = jest.fn((candidate: AbortSignal) => {
      signal = candidate;
      return new Promise<string>(() => undefined);
    });
    const hook = await renderHook(() => usePublicResource(loader));
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));
    await hook.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it('normalizes unexpected loader failures without exposing their message', async () => {
    const loader = jest
      .fn<Promise<string>, [AbortSignal]>()
      .mockRejectedValue(new Error('provider-token-and-stack'));
    const hook = await renderHook(() => usePublicResource(loader));
    await waitFor(() =>
      expect(hook.result.current.error?.kind).toBe('API_UNAVAILABLE'),
    );
    expect(hook.result.current.error?.message).not.toContain('provider-token');
  });
});
