import { useEffect, useState } from 'react';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { useProductSession } from './ProductSessionContext';
import { registerPushToken } from '@/lib/product-api';

export function usePushRegistration() {
  const { state, accessToken } = useProductSession();
  const [isPushDisabled, setIsPushDisabled] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;

    async function registerForPushNotificationsAsync() {
      if (Platform.OS === 'web') {
        return;
      }

      try {
        const { status: existingStatus } =
          await Notifications.getPermissionsAsync();
        const finalStatus =
          existingStatus === 'undetermined'
            ? (await Notifications.requestPermissionsAsync()).status
            : existingStatus;
        if (mounted) setIsPushDisabled(finalStatus !== 'granted');
        if (finalStatus !== 'granted') return;

        const projectId =
          Constants?.expoConfig?.extra?.eas?.projectId ??
          Constants?.easConfig?.projectId;
        if (!projectId) return;

        const pushTokenData = await Notifications.getExpoPushTokenAsync({
          projectId,
        });

        if (mounted && accessToken) {
          // Do not log the full token unnecessarily
          await registerPushToken(pushTokenData.data, 'EXPO', accessToken);
        }
      } catch {
        // Permission, token and registration failures are non-fatal to navigation.
      }
    }

    if (state === 'AUTHENTICATED' && accessToken) {
      void registerForPushNotificationsAsync();
    }

    return () => {
      mounted = false;
    };
  }, [state, accessToken]);

  return { isPushDisabled, dismissWarning: () => setIsPushDisabled(false) };
}
