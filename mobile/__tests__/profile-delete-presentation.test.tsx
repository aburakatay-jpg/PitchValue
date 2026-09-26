import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render } from '@testing-library/react-native';
import { useRouter } from 'expo-router';
import { StyleSheet } from 'react-native';

import DeleteAccountScreen from '@/app/account/delete';
import { ProfileView } from '@/app/profile';
import { LanguageProvider } from '@/features/language/LanguageContext';
import {
  darkColors,
  lightColors,
  setActiveAppearance,
  touchTarget,
} from '@/theme/tokens';

jest.mock('expo-router', () => ({ useRouter: jest.fn() }));
jest.mock('@/features/appearance/AppearanceContext', () => ({
  appearancePreferences: ['system', 'dark', 'light'],
  useAppearance: () => ({
    preference: 'system',
    setPreference: jest.fn(),
  }),
}));

describe('Profile account actions and delete presentation', () => {
  const push = jest.fn();

  beforeEach(async () => {
    await AsyncStorage.clear();
    jest.mocked(useRouter).mockReturnValue({ push } as never);
  });

  afterEach(async () => {
    setActiveAppearance('dark');
    jest.clearAllMocks();
    await AsyncStorage.clear();
  });

  it('opens the existing deletion route only from the authenticated lower action', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView
          authenticated
          entitlement="PREMIUM_INACTIVE"
          email="person@example.com"
          onSignIn={jest.fn()}
          onSignOut={jest.fn()}
        />
      </LanguageProvider>,
    );
    await view.findByText('Delete Account');
    await fireEvent.press(view.getByTestId('profile-delete-account'));
    expect(push).toHaveBeenCalledWith('/account/delete');
  });

  it('uses the semantic destructive color and touch target in both appearances', async () => {
    for (const [appearance, negative] of [
      ['dark', darkColors.negative],
      ['light', lightColors.negative],
    ] as const) {
      setActiveAppearance(appearance);
      const view = await render(
        <LanguageProvider>
          <ProfileView
            authenticated
            entitlement="PREMIUM_INACTIVE"
            onSignIn={jest.fn()}
            onSignOut={jest.fn()}
          />
        </LanguageProvider>,
      );
      await view.findByText('Delete Account');
      expect(
        StyleSheet.flatten(view.getByText('Delete Account').props.style).color,
      ).toBe(negative);
      expect(
        StyleSheet.flatten(
          view.getByTestId('profile-delete-account').props.style,
        ).minHeight,
      ).toBe(touchTarget);
      await view.unmount();
    }
  });

  it('localizes the existing delete screen without changing its initial flow', async () => {
    setActiveAppearance('light');
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <LanguageProvider>
        <DeleteAccountScreen />
      </LanguageProvider>,
    );
    expect(await view.findByText('Hesabı Sil')).toBeTruthy();
    expect(view.getByText('Devam Et')).toBeTruthy();
    expect(view.getByText('İptal')).toBeTruthy();
    expect(view.queryByText('Delete Account')).toBeNull();
    expect(view.getByTestId('screen-scroll-view')).toHaveProp(
      'automaticallyAdjustKeyboardInsets',
      true,
    );
    await fireEvent.press(view.getByText('Devam Et'));
    expect(view.getByText('Son Onay')).toBeTruthy();
    expect(
      StyleSheet.flatten(
        view.getByTestId('delete-account-confirm-action').props.style,
      ).backgroundColor,
    ).toBe(lightColors.negative);
  });
});
