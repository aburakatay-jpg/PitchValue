import { useCallback, useEffect, useRef, useState } from 'react';

import { PublicApiError } from '@/lib/public-api';

export type PublicResource<T> = Readonly<{
  data: T | null;
  initialLoading: boolean;
  refreshing: boolean;
  error: PublicApiError | null;
  refresh: () => Promise<void>;
}>;

export function usePublicResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
): PublicResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<PublicApiError | null>(null);
  const activeController = useRef<AbortController | null>(null);

  const execute = useCallback(
    async (isRefresh: boolean) => {
      activeController.current?.abort();
      const controller = new AbortController();
      activeController.current = controller;
      if (isRefresh) setRefreshing(true);
      else setInitialLoading(true);
      try {
        const result = await loader(controller.signal);
        if (!controller.signal.aborted) {
          setData(result);
          setError(null);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          const normalized =
            caught instanceof PublicApiError
              ? caught
              : new PublicApiError('API_UNAVAILABLE');
          if (normalized.kind !== 'CANCELLED') setError(normalized);
        }
      } finally {
        if (!controller.signal.aborted) {
          setInitialLoading(false);
          setRefreshing(false);
        }
      }
    },
    [loader],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void execute(false);
    return () => activeController.current?.abort();
  }, [execute]);

  const refresh = useCallback(async () => execute(true), [execute]);
  return { data, initialLoading, refreshing, error, refresh };
}
