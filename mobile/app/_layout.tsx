import { DarkTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { EntitlementProvider } from '@/features/entitlement/EntitlementContext';
import {
  ProductSessionProvider,
  useProductSession,
} from '@/features/session/ProductSessionContext';
import { LanguageProvider } from '@/features/language/LanguageContext';
import { colors } from '@/theme/tokens';

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
  return (
    <ThemeProvider value={pitchValueNavigationTheme}>
      <EntitlementProvider
        state={session.entitlement}
        openPaywall={() => router.push('/paywall')}
      >
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            contentStyle: { backgroundColor: colors.background },
            headerStyle: { backgroundColor: colors.surface },
            headerTintColor: colors.text,
          }}
        >
          <Stack.Screen name="index" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen
            name="profile"
            options={{ title: 'Profile', headerBackTitle: '' }}
          />
          <Stack.Screen name="match/[id]" options={{ title: 'Match detail' }} />
          <Stack.Screen name="auth/index" options={{ title: 'Account' }} />
          <Stack.Screen name="auth/email" options={{ title: 'Email' }} />
          <Stack.Screen
            name="paywall"
            options={{ presentation: 'modal', title: 'PitchValue Premium' }}
          />
        </Stack>
      </EntitlementProvider>
    </ThemeProvider>
  );
}
