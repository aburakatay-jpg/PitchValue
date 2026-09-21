import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Text, View } from 'react-native';

import { ProfileView } from '@/app/profile';
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
    expect(lightColors.background).not.toBe(darkColors.background);
    expect(lightColors.surface).not.toBe(darkColors.surface);
    expect(lightColors.textPrimary).not.toBe(darkColors.textPrimary);
    expect(lightColors.border).not.toBe(darkColors.border);
    expect(lightColors.headerBackground).toBe(lightColors.surface);
    expect(lightColors.tabBarBackground).toBe(lightColors.surface);
    expect(darkColors.headerBackground).toBe(darkColors.surface);
    expect(darkColors.tabBarBackground).toBe(darkColors.surface);
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
  });
});
