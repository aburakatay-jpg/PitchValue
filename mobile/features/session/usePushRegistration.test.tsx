import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  fireEvent,
  render,
  renderHook,
  waitFor,
} from '@testing-library/react-native';
import * as Notifications from 'expo-notifications';
import { Pressable, Text, View } from 'react-native';

import { PushDisabledNotice } from './PushDisabledNotice';
import { usePushRegistration } from './usePushRegistration';
import { registerPushToken } from '@/lib/product-api';

jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
}));
jest.mock('expo-constants', () => ({
  expoConfig: { extra: { eas: { projectId: 'test-project' } } },
}));
jest.mock('@/features/session/ProductSessionContext', () => ({
  useProductSession: () => ({
    state: 'AUTHENTICATED',
    accessToken: 'session-token',
  }),
}));
jest.mock('@/lib/product-api', () => ({ registerPushToken: jest.fn() }));

const permissions = Notifications.getPermissionsAsync as jest.Mock;
const request = Notifications.requestPermissionsAsync as jest.Mock;
const getToken = Notifications.getExpoPushTokenAsync as jest.Mock;
const register = registerPushToken as jest.Mock;

describe('push permission warning', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    permissions.mockResolvedValue({ status: 'granted' });
    request.mockResolvedValue({ status: 'granted' });
    getToken.mockResolvedValue({ data: 'test-token' });
    register.mockResolvedValue(undefined);
  });

  it('does not warn when permission is granted', async () => {
    const hook = await renderHook(usePushRegistration);
    await waitFor(() => expect(register).toHaveBeenCalledTimes(1));
    expect(hook.result.current.isPushDisabled).toBe(false);
    expect(request).not.toHaveBeenCalled();
  });

  it('warns on denied permission without requesting in a loop', async () => {
    permissions.mockResolvedValue({ status: 'denied' });
    const hook = await renderHook(usePushRegistration);
    await waitFor(() => expect(hook.result.current.isPushDisabled).toBe(true));
    expect(request).not.toHaveBeenCalled();
    expect(getToken).not.toHaveBeenCalled();
  });

  it('requests undetermined permission only once', async () => {
    permissions.mockResolvedValue({ status: 'undetermined' });
    request.mockResolvedValue({ status: 'denied' });
    const hook = await renderHook(usePushRegistration);
    await waitFor(() => expect(hook.result.current.isPushDisabled).toBe(true));
    await hook.rerender(undefined);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      'permission/network',
      () => permissions.mockRejectedValue(new Error('network')),
    ],
    ['token', () => getToken.mockRejectedValue(new Error('token'))],
    [
      'backend registration',
      () => register.mockRejectedValue(new Error('server')),
    ],
  ])('keeps the app usable on %s failure', async (_label, fail) => {
    fail();
    const hook = await renderHook(usePushRegistration);
    await waitFor(() => expect(permissions).toHaveBeenCalledTimes(1));
    expect(hook.result.current.isPushDisabled).toBe(false);
    expect(hook.result.current.dismissWarning).toBeInstanceOf(Function);
  });

  it('keeps navigation interactive while the warning is visible', async () => {
    const navigate = jest.fn();
    const view = await render(
      <View>
        <PushDisabledNotice />
        <Pressable accessibilityRole="button" onPress={navigate}>
          <Text>Open Today</Text>
        </Pressable>
      </View>,
    );
    await fireEvent.press(view.getByRole('button', { name: 'Open Today' }));
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['en', 'Notifications are disabled'],
    ['tr', 'Bildirimler kapalı'],
  ])('localizes the warning in %s', async (language, title) => {
    await AsyncStorage.setItem('pitchvalue_language', language);
    const view = await render(<PushDisabledNotice />);
    await waitFor(() => expect(view.getByText(title)).toBeTruthy());
  });
});
