import { DarkTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

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
import { colors } from '@/theme/tokens';
import { signInScreenOptions } from '@/lib/navigation-options';

const pitchValueNavigationTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    primary: colors.primary,
    background: colors.background,
    card: colors.surface,
    text: colors.text,
    border: colors.border,
  },
};

export default function RootLayout() {
  return (
    <ProductSessionProvider>
      <LanguageProvider>
        <RootNavigation />
      </LanguageProvider>
    </ProductSessionProvider>
  );
}

function RootNavigation() {
  const router = useRouter();
  const session = useProductSession();
  const { t } = useLanguage();
  return (
    <ThemeProvider value={pitchValueNavigationTheme}>
      <EntitlementProvider
        state={session.entitlement}
        openPaywall={() => router.push('/paywall')}
      >
        <CommerceProvider>
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              contentStyle: { backgroundColor: colors.background },
              headerStyle: { backgroundColor: colors.surface },
              headerTintColor: colors.text,
            }}
          >
            <Stack.Screen name="index" options={{ headerShown: false }} />
            <Stack.Screen
              name="(tabs)"
              options={{ headerShown: false, title: '' }}
            />
            <Stack.Screen
              name="profile"
              options={{ title: t('Profile'), headerBackTitle: '' }}
            />
            <Stack.Screen
              name="match/[id]"
              options={{ title: t('Match detail') }}
            />
            <Stack.Screen name="auth/index" options={signInScreenOptions} />
            <Stack.Screen name="auth/email" options={{ title: t('Email') }} />
            <Stack.Screen
              name="paywall"
              options={{
                presentation: 'modal',
                title: t('PitchValue Premium'),
              }}
            />
          </Stack>
        </CommerceProvider>
      </EntitlementProvider>
    </ThemeProvider>
  );
}
