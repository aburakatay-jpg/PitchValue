import { useEffect } from 'react';
import { useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';

function matchRoute(data: unknown): `/match/${number}` | null {
  if (!data || typeof data !== 'object') return null;
  const payload = data as Record<string, unknown>;
  if (payload.type !== 'match_event') {
    return null;
  }
  if (
    typeof payload.matchId !== 'number' ||
    !Number.isSafeInteger(payload.matchId) ||
    payload.matchId <= 0
  ) {
    return null;
  }
  return `/match/${payload.matchId}`;
}

export function useNotificationDeepLink() {
  const router = useRouter();

  useEffect(() => {
    let isMounted = true;

    // Handle cold start
    void Notifications.getLastNotificationResponseAsync()
      .then((response) => {
        if (!isMounted) return;
        const route = matchRoute(
          response?.notification?.request?.content?.data,
        );
        if (route) router.push(route);
      })
      .catch(() => {});

    // Handle background / foreground taps
    const subscription = Notifications.addNotificationResponseReceivedListener(
      (response) => {
        const route = matchRoute(response.notification.request.content.data);
        if (route) router.push(route);
      },
    );

    return () => {
      isMounted = false;
      subscription.remove();
    };
  }, [router]);
}
