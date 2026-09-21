import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { View, useColorScheme, type ColorSchemeName } from 'react-native';

import {
  getThemeColors,
  setActiveAppearance,
  type ResolvedAppearance,
  type ThemeColors,
} from '@/theme/tokens';

export type AppearancePreference = 'system' | 'dark' | 'light';

export const APPEARANCE_STORAGE_KEY = 'pitchvalue_appearance';
export const appearancePreferences: readonly AppearancePreference[] = [
  'system',
  'dark',
  'light',
];

interface AppearanceContextValue {
  preference: AppearancePreference;
  resolvedAppearance: ResolvedAppearance;
  colors: ThemeColors;
  setPreference: (preference: AppearancePreference) => void;
}

const AppearanceContext = createContext<AppearanceContextValue | null>(null);

export function isAppearancePreference(
  value: string | null,
): value is AppearancePreference {
  return (
    value !== null &&
    appearancePreferences.includes(value as AppearancePreference)
  );
}

export function resolveAppearance(
  preference: AppearancePreference,
  systemScheme: ColorSchemeName,
): ResolvedAppearance {
  if (preference === 'dark' || preference === 'light') return preference;
  return systemScheme === 'light' ? 'light' : 'dark';
}

export function AppearanceProvider({
  children,
  systemSchemeOverride,
}: {
  children: React.ReactNode;
  systemSchemeOverride?: ColorSchemeName;
}) {
  if (systemSchemeOverride !== undefined) {
    return (
      <AppearanceProviderCore systemScheme={systemSchemeOverride}>
        {children}
      </AppearanceProviderCore>
    );
  }
  return <SystemAppearanceProvider>{children}</SystemAppearanceProvider>;
}

function SystemAppearanceProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  return (
    <AppearanceProviderCore systemScheme={systemScheme}>
      {children}
    </AppearanceProviderCore>
  );
}

function AppearanceProviderCore({
  children,
  systemScheme,
}: {
  children: React.ReactNode;
  systemScheme: ColorSchemeName;
}) {
  const [preference, setStoredPreference] =
    useState<AppearancePreference>('system');
  const [isReady, setIsReady] = useState(false);
  const resolvedAppearance = resolveAppearance(preference, systemScheme);
  const themeColors = getThemeColors(resolvedAppearance);

  // Style proxies must resolve against the active palette during child render.
  setActiveAppearance(resolvedAppearance);

  useEffect(() => {
    AsyncStorage.getItem(APPEARANCE_STORAGE_KEY)
      .then((value) => {
        setStoredPreference(isAppearancePreference(value) ? value : 'system');
      })
      .catch(() => setStoredPreference('system'))
      .finally(() => setIsReady(true));
  }, []);

  const value = useMemo<AppearanceContextValue>(
    () => ({
      preference,
      resolvedAppearance,
      colors: themeColors,
      setPreference: (nextPreference) => {
        setStoredPreference(nextPreference);
        void AsyncStorage.setItem(APPEARANCE_STORAGE_KEY, nextPreference);
      },
    }),
    [preference, resolvedAppearance, themeColors],
  );

  if (!isReady) {
    return (
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={{ flex: 1, backgroundColor: themeColors.background }}
        testID="appearance-bootstrap"
      />
    );
  }

  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  );
}

export function useAppearance() {
  const context = useContext(AppearanceContext);
  if (!context) {
    throw new Error('useAppearance must be used within AppearanceProvider');
  }
  return context;
}
