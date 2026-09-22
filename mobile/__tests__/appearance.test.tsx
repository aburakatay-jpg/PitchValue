import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Text, View } from 'react-native';
import { StyleSheet } from 'react-native';

import { ProfileView } from '@/app/profile';
import { Screen, sharedStyles } from '@/components/ui';
import {
  APPEARANCE_STORAGE_KEY,
  AppearanceProvider,
  resolveAppearance,
  useAppearance,
} from '@/features/appearance/AppearanceContext';
import { LanguageProvider } from '@/features/language/LanguageContext';
import {
  ProductSessionProvider,
  useProductSession,
} from '@/features/session/ProductSessionContext';
import { darkColors, lightColors, setActiveAppearance } from '@/theme/tokens';

function AppearanceProbe() {
  const { colors, preference, resolvedAppearance, setPreference } =
    useAppearance();
  return (
    <View>
      <Text testID="preference">{preference}</Text>
      <Text testID="resolved">{resolvedAppearance}</Text>
      <Text testID="background">{colors.background}</Text>
      <Text onPress={() => setPreference('system')}>choose-system</Text>
      <Text onPress={() => setPreference('dark')}>choose-dark</Text>
      <Text onPress={() => setPreference('light')}>choose-light</Text>
    </View>
  );
}

function BareWrapper({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

function SignOutProbe() {
  const session = useProductSession();
  return <Text onPress={() => void session.signOut()}>sign-out</Text>;
}

function contrastRatio(foreground: string, background: string) {
  const luminance = (hex: string) => {
    const channels = [1, 3, 5].map(
      (start) => parseInt(hex.slice(start, start + 2), 16) / 255,
    );
    const linear = channels.map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );
    return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722;
  };
  const values = [luminance(foreground), luminance(background)].sort(
    (a, b) => b - a,
  );
  return (values[0]! + 0.05) / (values[1]! + 0.05);
}

describe('appearance foundation', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  afterEach(async () => {
    setActiveAppearance('dark');
    await AsyncStorage.clear();
  });

  it('uses system by default and resolves both device schemes', () => {
    expect(resolveAppearance('system', 'dark')).toBe('dark');
    expect(resolveAppearance('system', 'light')).toBe('light');
    expect(resolveAppearance('dark', 'light')).toBe('dark');
    expect(resolveAppearance('light', 'dark')).toBe('light');
  });

  it('defines distinct semantic palettes for content and navigation surfaces', () => {
    expect(lightColors.background).toBe('#F3F1EB');
    expect(lightColors.surface).toBe('#EAE8E2');
    expect(lightColors.surface).not.toBe('#DAD8D3');
    expect(darkColors.background).toBe('#08111F');
    expect(darkColors.surface).toBe('#111D2E');
    expect(lightColors.background).not.toBe(darkColors.background);
    expect(lightColors.surface).not.toBe(darkColors.surface);
    expect(lightColors.textPrimary).not.toBe(darkColors.textPrimary);
    expect(lightColors.border).not.toBe(darkColors.border);
    expect(lightColors.headerBackground).toBe(lightColors.surface);
    expect(lightColors.tabBarBackground).toBe(lightColors.surface);
    expect(darkColors.headerBackground).toBe(darkColors.surface);
    expect(darkColors.tabBarBackground).toBe(darkColors.surface);
    expect(lightColors.controlSelected).not.toBe(lightColors.brandPrimary);
    expect(lightColors.controlSelectedText).toBe(lightColors.textPrimary);
    expect(lightColors.controlSelectedAccent).toBe('#F2B84B');
    expect(darkColors.controlSelectedAccent).toBe('rgba(65, 105, 225, 1)');
    expect(lightColors.segmentedSelectedBackground).toBe('#F2B84B');
    expect(lightColors.segmentedSelectedText).toBe(lightColors.textPrimary);
    expect(lightColors.appearanceSelectedBackground).toBe('#F2B84B');
    expect(lightColors.appearanceSelectedText).toBe(lightColors.textPrimary);
    expect(lightColors.authPrimaryBackground).toBe('#F2B84B');
    expect(lightColors.authPrimaryText).toBe(lightColors.textPrimary);
    expect(lightColors.interactiveTextAccent).toBe('#835500');
    expect(lightColors.interactiveTextAccent).not.toBe(
      lightColors.brandPrimary,
    );
    expect(darkColors.segmentedSelectedBackground).toBe(
      'rgba(65, 105, 225, 1)',
    );
    expect(darkColors.appearanceSelectedBackground).toBe(
      'rgba(65, 105, 225, 1)',
    );
    expect(darkColors.authPrimaryBackground).toBe('rgba(65, 105, 225, 1)');
    expect(darkColors.controlSelected).toBe(darkColors.brandPrimary);
    expect(darkColors.interactiveTextAccent).toBe('rgba(118, 150, 245, 1)');
  });

  it('keeps Light normal text accessible on both warm surfaces', () => {
    for (const surface of [lightColors.background, lightColors.surface]) {
      expect(
        contrastRatio(lightColors.textPrimary, surface),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrastRatio(lightColors.textSecondary, surface),
      ).toBeGreaterThanOrEqual(4.5);
      expect(
        contrastRatio(lightColors.interactiveTextAccent, surface),
      ).toBeGreaterThanOrEqual(4.5);
    }
    expect(
      contrastRatio(
        lightColors.authPrimaryText,
        lightColors.authPrimaryBackground,
      ),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it('resolves the shared Light canvas and card while retaining Dark surfaces', async () => {
    setActiveAppearance('light');
    const lightView = await render(
      <Screen>
        <View testID="sample-card" style={sharedStyles.card} />
      </Screen>,
    );
    expect(
      StyleSheet.flatten(lightView.getByTestId('screen-safe-area').props.style)
        .backgroundColor,
    ).toBe(lightColors.background);
    expect(
      StyleSheet.flatten(lightView.getByTestId('sample-card').props.style)
        .backgroundColor,
    ).toBe(lightColors.surface);
    setActiveAppearance('dark');
    await lightView.rerender(
      <Screen>
        <View testID="sample-card" style={sharedStyles.card} />
      </Screen>,
    );
    expect(
      StyleSheet.flatten(lightView.getByTestId('screen-safe-area').props.style)
        .backgroundColor,
    ).toBe(darkColors.background);
    expect(
      StyleSheet.flatten(lightView.getByTestId('sample-card').props.style)
        .backgroundColor,
    ).toBe(darkColors.surface);
  });

  it('holds the app at a theme-safe bootstrap surface until storage resolves', async () => {
    (AsyncStorage.getItem as jest.Mock).mockImplementationOnce(
      () =>
        new Promise(() => {
          // Deliberately unresolved so the bootstrap state can be asserted.
        }),
    );
    const view = await render(
      <AppearanceProvider systemSchemeOverride="dark">
        <AppearanceProbe />
      </AppearanceProvider>,
      { wrapper: BareWrapper },
    );
    expect(
      view.getByTestId('appearance-bootstrap', { includeHiddenElements: true }),
    ).toBeTruthy();
    expect(view.queryByTestId('preference')).toBeNull();
  });

  it('falls back to system for malformed persistence', async () => {
    await AsyncStorage.setItem(APPEARANCE_STORAGE_KEY, 'sepia');
    const view = await render(
      <AppearanceProvider systemSchemeOverride="dark">
        <AppearanceProbe />
      </AppearanceProvider>,
      { wrapper: BareWrapper },
    );
    expect(await view.findByTestId('preference')).toHaveTextContent('system');
    expect(view.getByTestId('resolved')).toHaveTextContent('dark');
  });

  it('persists explicit choices and keeps them independent of device changes', async () => {
    const view = await render(
      <AppearanceProvider systemSchemeOverride="dark">
        <AppearanceProbe />
      </AppearanceProvider>,
      { wrapper: BareWrapper },
    );
    await view.findByTestId('preference');
    await fireEvent.press(view.getByText('choose-light'));
    expect(view.getByTestId('resolved')).toHaveTextContent('light');
    expect(view.getByTestId('background')).toHaveTextContent(
      lightColors.background,
    );
    await waitFor(() =>
      expect(AsyncStorage.getItem(APPEARANCE_STORAGE_KEY)).resolves.toBe(
        'light',
      ),
    );

    await view.rerender(
      <AppearanceProvider systemSchemeOverride="dark">
        <AppearanceProbe />
      </AppearanceProvider>,
    );
    expect(view.getByTestId('resolved')).toHaveTextContent('light');
  });

  it('keeps the device-local appearance preference across sign-out', async () => {
    await AsyncStorage.setItem(APPEARANCE_STORAGE_KEY, 'light');
    const view = await render(
      <ProductSessionProvider>
        <AppearanceProvider systemSchemeOverride="dark">
          <SignOutProbe />
        </AppearanceProvider>
      </ProductSessionProvider>,
      { wrapper: BareWrapper },
    );
    await fireEvent.press(await view.findByText('sign-out'));
    await waitFor(() =>
      expect(AsyncStorage.getItem(APPEARANCE_STORAGE_KEY)).resolves.toBe(
        'light',
      ),
    );
  });

  it('tracks live device changes while System is selected', async () => {
    const view = await render(
      <AppearanceProvider systemSchemeOverride="dark">
        <AppearanceProbe />
      </AppearanceProvider>,
      { wrapper: BareWrapper },
    );
    await view.findByTestId('preference');
    expect(view.getByTestId('background')).toHaveTextContent(
      darkColors.background,
    );

    await view.rerender(
      <AppearanceProvider systemSchemeOverride="light">
        <AppearanceProbe />
      </AppearanceProvider>,
    );
    expect(view.getByTestId('resolved')).toHaveTextContent('light');
    expect(view.getByTestId('background')).toHaveTextContent(
      lightColors.background,
    );
  });

  it('renders the localized three-option Profile selector and stores selection', async () => {
    const view = await render(
      <AppearanceProvider systemSchemeOverride="dark">
        <LanguageProvider>
          <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
        </LanguageProvider>
      </AppearanceProvider>,
      { wrapper: BareWrapper },
    );
    expect(await view.findByText('Appearance')).toBeTruthy();
    for (const label of ['System', 'Dark', 'Light']) {
      expect(view.getByRole('radio', { name: label })).toBeTruthy();
    }
    await fireEvent.press(view.getByRole('radio', { name: 'Light' }));
    expect(
      view.getByRole('radio', { name: 'Light' }).props.accessibilityState,
    ).toMatchObject({ checked: true });
    await waitFor(() =>
      expect(AsyncStorage.getItem(APPEARANCE_STORAGE_KEY)).resolves.toBe(
        'light',
      ),
    );
    const lightOption = view.getByTestId('appearance-light');
    expect(StyleSheet.flatten(lightOption.props.style)).toMatchObject({
      backgroundColor: lightColors.appearanceSelectedBackground,
      borderColor: lightColors.appearanceSelectedBackground,
    });
    expect(
      StyleSheet.flatten(view.getByTestId('language-en').props.style),
    ).toMatchObject({
      backgroundColor: lightColors.appearanceSelectedBackground,
      borderColor: lightColors.appearanceSelectedBackground,
    });
  });
});
