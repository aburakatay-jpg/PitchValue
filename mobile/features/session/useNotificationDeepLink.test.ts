import { renderHook } from '@testing-library/react-native';
import * as Notifications from 'expo-notifications';
import { useRouter } from 'expo-router';

import { useNotificationDeepLink } from './useNotificationDeepLink';

jest.mock('expo-notifications', () => ({
  getLastNotificationResponseAsync: jest.fn(),
  addNotificationResponseReceivedListener: jest.fn(),
}));

jest.mock('expo-router', () => ({
  useRouter: jest.fn(),
}));

describe('useNotificationDeepLink', () => {
  let mockPush: jest.Mock;
  let mockRemoveSubscription: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();

    mockPush = jest.fn();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });

    mockRemoveSubscription = jest.fn();
    (
      Notifications.addNotificationResponseReceivedListener as jest.Mock
    ).mockReturnValue({
      remove: mockRemoveSubscription,
    });
    (
      Notifications.getLastNotificationResponseAsync as jest.Mock
    ).mockResolvedValue(null);
  });

  const triggerNotification = (data: any) => {
    const listener = (
      Notifications.addNotificationResponseReceivedListener as jest.Mock
    ).mock.calls[0][0];
    listener({
      notification: {
        request: {
          content: {
            data,
          },
        },
      },
    });
  };

  test('valid matchId navigates to Match Detail', async () => {
    await renderHook(() => useNotificationDeepLink());

    triggerNotification({ type: 'match_event', matchId: 1234 });

    expect(mockPush).toHaveBeenCalledWith('/match/1234');
  });

  test('missing matchId does not navigate', async () => {
    await renderHook(() => useNotificationDeepLink());

    triggerNotification({ type: 'match_event' });

    expect(mockPush).not.toHaveBeenCalled();
  });

  test('malformed matchId does not navigate', async () => {
    await renderHook(() => useNotificationDeepLink());

    triggerNotification({ type: 'match_event', matchId: '1234' }); // wrong type
    expect(mockPush).not.toHaveBeenCalled();

    triggerNotification({ type: 'match_event', matchId: null });
    expect(mockPush).not.toHaveBeenCalled();

    triggerNotification({ type: 'match_event', matchId: {} });
    expect(mockPush).not.toHaveBeenCalled();

    triggerNotification({ type: 'match_event', matchId: -1 });
    triggerNotification({ type: 'match_event', matchId: 1.5 });
    expect(mockPush).not.toHaveBeenCalled();
  });

  test('unrelated payload does not navigate', async () => {
    await renderHook(() => useNotificationDeepLink());

    triggerNotification({ foo: 'bar' });

    expect(mockPush).not.toHaveBeenCalled();
  });

  test('unsupported event safely ignored', async () => {
    await renderHook(() => useNotificationDeepLink());

    triggerNotification({ type: 'UNKNOWN_EVENT', matchId: 1234 });
    expect(mockPush).not.toHaveBeenCalled();
  });

  test('listener is registered once', async () => {
    const hook = await renderHook(() => useNotificationDeepLink());
    await hook.rerender(undefined);

    expect(
      Notifications.addNotificationResponseReceivedListener,
    ).toHaveBeenCalledTimes(1);
  });

  test('listener is removed during cleanup', async () => {
    const { unmount } = await renderHook(() => useNotificationDeepLink());

    await unmount();

    expect(mockRemoveSubscription).toHaveBeenCalledTimes(1);
  });
});
