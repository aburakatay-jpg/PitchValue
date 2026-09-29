import {
  DarkTheme,
  DefaultTheme,
  Stack,
  ThemeProvider,
  useRouter,
} from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { View } from 'react-native';
import { PushDisabledNotice } from '@/features/session/PushDisabledNotice';
import { usePushRegistration } from '@/features/session/usePushRegistration';
import { useNotificationDeepLink } from '@/features/session/useNotificationDeepLink';

import { BrandedLaunchSplash } from '@/components/BrandedLaunchSplash';
import { CommerceProvider } from '@/features/entitlement/CommerceContext';
import { EntitlementProvider } from '@/features/entitlement/EntitlementContext';
import {
  ProductSessionProvider,
  useProductSession,
} from '@/features/session/ProductSessionContext';
import {
  LanguageProvider,
  useLanguage,
} from '@/features/language/LanguageContext';
import {
  AppearanceProvider,
  useAppearance,
} from '@/features/appearance/AppearanceContext';
import {
  createNativeHeaderOptions,
  registrationScreenOptions,
  signInScreenOptions,
} from '@/lib/navigation-options';

void SplashScreen.preventAutoHideAsync().catch(() => {
  // Startup still remains safe if a development host controls splash behavior.
});

export default function RootLayout() {
  return (
    <ProductSessionProvider>
      <AppearanceProvider>
        <LanguageProvider>
          <RootNavigation />
        </LanguageProvider>
      </AppearanceProvider>
    </ProductSessionProvider>
  );
}

function RootNavigation() {
  const router = useRouter();
  const session = useProductSession();
  const { isPushDisabled } = usePushRegistration();
  useNotificationDeepLink();
  const { t } = useLanguage();
  const { resolvedAppearance, colors: themeColors } = useAppearance();
  const navigationBase =
    resolvedAppearance === 'dark' ? DarkTheme : DefaultTheme;
  const nativeHeaderOptions = createNativeHeaderOptions(themeColors);
  const navigationTheme = {
    ...navigationBase,
    colors: {
      ...navigationBase.colors,
      primary: themeColors.brandPrimary,
      background: themeColors.background,
      card: themeColors.headerBackground,
      text: themeColors.textPrimary,
      border: themeColors.border,
    },
  };
  return (
    <ThemeProvider value={navigationTheme}>
      <EntitlementProvider
        state={session.entitlement}
        openPaywall={() => router.push('/paywall')}
      >
        <CommerceProvider>
          <View style={{ flex: 1 }}>
            <StatusBar
              style={resolvedAppearance === 'dark' ? 'light' : 'dark'}
            />
            <Stack screenOptions={nativeHeaderOptions}>
              <Stack.Screen name="index" options={{ headerShown: false }} />
              <Stack.Screen
                name="(tabs)"
                options={{ headerShown: false, title: '' }}
              />
              <Stack.Screen
                name="profile"
                options={{
                  ...nativeHeaderOptions,
                  title: t('Profile'),
                  headerBackTitle: '',
                }}
              />
              <Stack.Screen
                name="match/[id]"
                options={{ ...nativeHeaderOptions, title: t('Match detail') }}
              />
              <Stack.Screen
                name="auth/index"
                options={{ ...nativeHeaderOptions, ...signInScreenOptions }}
              />
              <Stack.Screen
                name="auth/email"
                options={{
                  ...nativeHeaderOptions,
                  ...registrationScreenOptions,
                }}
              />
              <Stack.Screen
                name="paywall"
                options={{
                  ...nativeHeaderOptions,
                  presentation: 'modal',
                  headerBackVisible: false,
                  title: t('PitchValue Premium'),
                }}
              />
            </Stack>
            {isPushDisabled ? <PushDisabledNotice /> : null}
            <BrandedLaunchSplash ready />
          </View>
        </CommerceProvider>
      </EntitlementProvider>
    </ThemeProvider>
  );
}
