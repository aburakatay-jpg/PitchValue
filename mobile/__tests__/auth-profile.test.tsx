import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { Linking, StyleSheet } from 'react-native';

import AsyncStorage from '@react-native-async-storage/async-storage';

import AuthEntryScreen from '@/app/auth';
import { ProfileView, profileGroups } from '@/app/profile';
import { SignInShell } from '@/components/AuthShell';
import { signInScreenOptions } from '@/lib/navigation-options';
import { ProductServiceError } from '@/lib/product-api';
import { entitlementStates } from '@/types/entitlement';
import {
  darkColors,
  lightColors,
  setActiveAppearance,
  spacing,
  touchTarget,
} from '@/theme/tokens';

jest.mock('@/features/appearance/AppearanceContext', () => ({
  appearancePreferences: ['system', 'dark', 'light'],
  useAppearance: () => ({
    preference: 'system',
    resolvedAppearance: 'dark',
    setPreference: jest.fn(),
  }),
}));

const englishStatusLabels = {
  GUEST: 'Inactive',
  PREMIUM_ACTIVE: 'Active',
  PREMIUM_TRIAL: 'Trial',
  PREMIUM_EXPIRED: 'Expired',
  PREMIUM_INACTIVE: 'Inactive',
} as const;

const turkishStatusLabels = {
  GUEST: 'Pasif',
  PREMIUM_ACTIVE: 'Aktif',
  PREMIUM_TRIAL: 'Deneme',
  PREMIUM_EXPIRED: 'Süresi Doldu',
  PREMIUM_INACTIVE: 'Pasif',
} as const;

describe('auth-safe presentation', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  afterEach(async () => {
    setActiveAppearance('dark');
    await AsyncStorage.clear();
  });

  it('uses the semantic yellow treatment for enabled Light Mode auth CTAs', async () => {
    setActiveAppearance('light');
    const signIn = await render(
      <SignInShell onCreateAccount={jest.fn()} onSignIn={jest.fn()} />,
    );
    expect(
      StyleSheet.flatten(signIn.getByTestId('auth-primary').props.style),
    ).toMatchObject({ backgroundColor: lightColors.authPrimaryBackground });
  });

  it('keeps disabled auth actions neutral and secondary auth links accessible amber in Light Mode', async () => {
    setActiveAppearance('light');
    const view = await render(<SignInShell onCreateAccount={jest.fn()} />);
    expect(
      StyleSheet.flatten(view.getByTestId('auth-primary').props.style),
    ).toMatchObject({ backgroundColor: lightColors.surface });
    expect(
      StyleSheet.flatten(view.getByText('Sign Up').props.style),
    ).toMatchObject({ color: lightColors.interactiveTextAccent });
  });

  it('opens the email/password sign-in form directly without chooser tabs or Guest CTA', async () => {
    const view = await render(<AuthEntryScreen />);
    expect(await view.findByText('Welcome back')).toBeTruthy();
    expect(view.getByLabelText('Email')).toBeTruthy();
    expect(view.getByLabelText('Password')).toBeTruthy();
    expect(view.queryByText('Continue as Guest')).toBeNull();
    expect(view.queryByText('Continue with Email')).toBeNull();
    expect(view.queryByText('Create an account')).toBeNull();
  });

  it('places honest Apple and Google options after the primary email flow', async () => {
    const view = await render(
      <SignInShell
        onCreateAccount={jest.fn()}
        onSignIn={jest.fn().mockResolvedValue(undefined)}
      />,
    );
    for (const provider of ['Apple', 'Google']) {
      expect(
        view.getByLabelText(`Continue with ${provider}, unavailable`),
      ).toBeDisabled();
    }
    expect(view.getByTestId('auth-apple-symbol')).toHaveProp(
      'name',
      'apple.logo',
    );
    expect(view.getByText('G')).toBeTruthy();
    const tree = JSON.stringify(view.toJSON());
    expect(tree.indexOf('auth-primary')).toBeLessThan(
      tree.indexOf('auth-apple'),
    );
    expect(tree.indexOf('auth-apple')).toBeLessThan(
      tree.indexOf('auth-google'),
    );
  });

  it('provides mobile email/password semantics and an inline eye toggle', async () => {
    const view = await render(
      <SignInShell onCreateAccount={jest.fn()} onSignIn={jest.fn()} />,
    );
    const email = view.getByLabelText('Email');
    const password = view.getByLabelText('Password');
    expect(email).toHaveProp('keyboardType', 'email-address');
    expect(email).toHaveProp('autoCapitalize', 'none');
    expect(email).toHaveProp('returnKeyType', 'next');
    expect(password).toHaveProp('secureTextEntry', true);
    expect(password).toHaveProp('returnKeyType', 'done');
    expect(view.queryByText('Show password')).toBeNull();
    await fireEvent.press(view.getByLabelText('Show password'));
    expect(password).toHaveProp('secureTextEntry', false);
    expect(view.getByLabelText('Hide password')).toBeTruthy();
    await fireEvent.changeText(email, 'invalid');
    await fireEvent(email, 'blur');
    expect(view.getByText('Enter a valid email address.')).toBeTruthy();
  });

  it('submits email authentication only through a real service callback', async () => {
    const onSignIn = jest.fn().mockResolvedValue(undefined);
    const view = await render(
      <SignInShell onCreateAccount={jest.fn()} onSignIn={onSignIn} />,
    );
    await fireEvent.changeText(
      view.getByLabelText('Email'),
      'user@example.com',
    );
    await fireEvent.changeText(
      view.getByLabelText('Password'),
      'SecurePassword1!',
    );
    await fireEvent.press(view.getByLabelText('Sign In'));
    expect(onSignIn).toHaveBeenCalledWith(
      'user@example.com',
      'SecurePassword1!',
    );
  });

  it('keeps authentication errors user-safe and localized', async () => {
    const view = await render(
      <SignInShell
        onCreateAccount={jest.fn()}
        onSignIn={jest
          .fn()
          .mockRejectedValue(new ProductServiceError('UNAVAILABLE'))}
      />,
    );
    await fireEvent.changeText(
      view.getByLabelText('Email'),
      'user@example.com',
    );
    await fireEvent.changeText(view.getByLabelText('Password'), 'password');
    await fireEvent.press(view.getByLabelText('Sign In'));
    expect(await view.findByText('Unable to sign in')).toBeTruthy();
  });

  it('uses a text link for Create Account and chevron-only stack navigation', async () => {
    const onCreateAccount = jest.fn();
    const view = await render(
      <SignInShell onCreateAccount={onCreateAccount} onSignIn={jest.fn()} />,
    );
    const link = view.getByRole('link', { name: 'Create an account' });
    await fireEvent.press(link);
    expect(onCreateAccount).toHaveBeenCalledTimes(1);
    expect(signInScreenOptions).toEqual({
      title: '',
      headerBackTitle: '',
      headerBackButtonDisplayMode: 'minimal',
    });
  });

  it('renders the complete sign-in flow in Turkish', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <SignInShell onCreateAccount={jest.fn()} onSignIn={jest.fn()} />,
    );
    for (const label of [
      'Tekrar hoş geldiniz',
      'E-posta',
      'Şifre',
      'Giriş Yap',
      'Hesabınız yok mu?',
      'Kayıt Ol',
      'Apple ile devam et',
      'Google ile devam et',
    ]) {
      expect(await view.findByText(label)).toBeTruthy();
    }
    expect(view.queryByText('Continue as Guest')).toBeNull();
  });
});

import { LanguageProvider } from '@/features/language/LanguageContext';

describe('Profile foundation', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
    jest.restoreAllMocks();
  });

  it('replaces inline language buttons with one accessible settings row and native-name options', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    const row = await view.findByTestId('profile-language-row');
    expect(row.props.accessibilityRole).toBe('button');
    expect(row.props.accessibilityLabel).toBe('Language: English');
    expect(StyleSheet.flatten(row.props.style).minHeight).toBe(touchTarget);
    expect(view.queryByTestId('language-en')).toBeNull();
    expect(view.queryByTestId('language-tr')).toBeNull();

    await fireEvent.press(row);
    expect(view.getByTestId('language-selector-modal')).toBeTruthy();
    expect(
      view.getByTestId('language-option-en').props.accessibilityLabel,
    ).toBe('English');
    expect(
      view.getByTestId('language-option-tr').props.accessibilityLabel,
    ).toBe('Türkçe');
    expect(
      view.getByTestId('language-option-en').props.accessibilityState,
    ).toMatchObject({ checked: true });
    expect(
      view.getByTestId('language-option-tr').props.accessibilityState,
    ).toMatchObject({ checked: false });
    expect(
      view.getByTestId('language-selected-en', { includeHiddenElements: true }),
    ).toBeTruthy();
    expect(
      view.queryByTestId('language-selected-tr', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
  });

  it('switches English and Turkish immediately through the existing persisted context', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    await view.findByTestId('profile-language-row');
    await fireEvent.press(view.getByTestId('profile-language-row'));
    await fireEvent.press(view.getByTestId('language-option-tr'));
    expect(view.queryByTestId('language-selector-modal')).toBeNull();
    expect(
      view.getByTestId('profile-language-row').props.accessibilityLabel,
    ).toBe('Dil: Türkçe');
    expect(view.getByText('Tercihler')).toBeTruthy();
    await waitFor(() =>
      expect(AsyncStorage.getItem('pitchvalue_language')).resolves.toBe('tr'),
    );

    await fireEvent.press(view.getByTestId('profile-language-row'));
    expect(
      view.getByTestId('language-option-tr').props.accessibilityState,
    ).toMatchObject({ checked: true });
    await fireEvent.press(view.getByTestId('language-option-en'));
    expect(view.queryByTestId('language-selector-modal')).toBeNull();
    expect(
      view.getByTestId('profile-language-row').props.accessibilityLabel,
    ).toBe('Language: English');
    expect(view.getByText('Preferences')).toBeTruthy();
    await waitFor(() =>
      expect(AsyncStorage.getItem('pitchvalue_language')).resolves.toBe('en'),
    );
  });

  it('loads the previously selected language without adding a second persistence path', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    const row = await view.findByTestId('profile-language-row');
    expect(row.props.accessibilityLabel).toBe('Dil: Türkçe');
    await fireEvent.press(row);
    expect(
      view.getByTestId('language-selected-tr', { includeHiddenElements: true }),
    ).toBeTruthy();
    expect(
      view.getByTestId('language-selector-close').props.accessibilityLabel,
    ).toBe('Dil seçiciyi kapat');
    await fireEvent.press(view.getByTestId('language-selector-close'));
    expect(view.queryByTestId('language-selector-modal')).toBeNull();
  });

  it('renders all canonical groups and a truthful Guest state', async () => {
    const onSignIn = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={onSignIn} />
      </LanguageProvider>,
    );
    // Wait for async storage LanguageProvider initialization
    await view.findByText('Account');
    expect(view.getByTestId('screen-safe-area').props.edges).toMatchObject({
      top: 'off',
      bottom: 'additive',
    });

    for (const group of profileGroups) {
      expect(view.getByText(group)).toBeTruthy();
    }

    expect(view.queryByText('Subscription')).toBeNull();
    expect(view.getByText('Premium')).toBeTruthy();
    expect(view.getByText('Inactive')).toBeTruthy();
    expect(view.getByTestId('profile-account-divider')).toBeTruthy();
    expect(view.queryByTestId('profile-account-identity')).toBeNull();
    expect(view.queryByTestId('profile-sign-out')).toBeNull();
    expect(view.queryByText(/Guest access includes/i)).toBeNull();
    expect(
      view.queryByText(/Subscription management and restoration/i),
    ).toBeNull();
    await fireEvent.press(view.getByText('Sign In'));
    expect(onSignIn).toHaveBeenCalledTimes(1);

    // Verify track record / My Bets is removed from Profile
    expect(view.queryByText(/Open My Bets/i)).toBeNull();
  });

  it('opens existing Premium options for Guest without forcing registration', async () => {
    setActiveAppearance('light');
    const onSignIn = jest.fn();
    const onOpenPremium = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="GUEST"
          onOpenPremium={onOpenPremium}
          onSignIn={onSignIn}
        />
      </LanguageProvider>,
    );
    const premiumRow = await view.findByTestId('profile-premium-row');
    expect(premiumRow.props.accessibilityLabel).toBe(
      'Premium: Premium Inactive. View Premium',
    );
    expect(StyleSheet.flatten(premiumRow.props.style).minHeight).toBe(
      touchTarget,
    );
    expect(
      StyleSheet.flatten(view.getByTestId('profile-premium-value').props.style),
    ).toMatchObject({ color: lightColors.interactiveTextAccent });
    await fireEvent.press(premiumRow);
    expect(onOpenPremium).toHaveBeenCalledTimes(1);
    expect(onSignIn).not.toHaveBeenCalled();
  });

  it.each(['PREMIUM_INACTIVE', 'PREMIUM_EXPIRED'] as const)(
    'opens existing Premium options for %s without changing entitlement semantics',
    async (entitlement) => {
      const onOpenPremium = jest.fn();
      const view = await render(
        <LanguageProvider>
          <ProfileView
            entitlement={entitlement}
            onOpenPremium={onOpenPremium}
            onSignIn={jest.fn()}
          />
        </LanguageProvider>,
      );
      await view.findByTestId('profile-premium-row');
      expect(view.getByTestId('profile-premium-value')).toHaveTextContent(
        englishStatusLabels[entitlement],
      );
      expect(
        view.getByTestId('profile-premium-chevron', {
          includeHiddenElements: true,
        }),
      ).toBeTruthy();
      await fireEvent.press(view.getByTestId('profile-premium-row'));
      expect(onOpenPremium).toHaveBeenCalledTimes(1);
    },
  );

  it.each(['PREMIUM_ACTIVE', 'PREMIUM_TRIAL'] as const)(
    'keeps %s informative without a purchase or subscription-management loop',
    async (entitlement) => {
      const onOpenPremium = jest.fn();
      const view = await render(
        <LanguageProvider>
          <ProfileView
            entitlement={entitlement}
            onOpenPremium={onOpenPremium}
            onSignIn={jest.fn()}
          />
        </LanguageProvider>,
      );
      await view.findByTestId('profile-premium-static-row');
      expect(view.getByTestId('profile-premium-value')).toHaveTextContent(
        englishStatusLabels[entitlement],
      );
      expect(view.queryByTestId('profile-premium-row')).toBeNull();
      expect(
        view.queryByTestId('profile-premium-chevron', {
          includeHiddenElements: true,
        }),
      ).toBeNull();
      expect(onOpenPremium).not.toHaveBeenCalled();
      expect(view.queryByText(/day|renew|billing/i)).toBeNull();
    },
  );

  it('localizes the interactive Premium row in Turkish', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const onOpenPremium = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="PREMIUM_INACTIVE"
          onOpenPremium={onOpenPremium}
          onSignIn={jest.fn()}
        />
      </LanguageProvider>,
    );
    const premiumRow = await view.findByTestId('profile-premium-row');
    expect(premiumRow.props.accessibilityLabel).toBe(
      "Premium: Premium Pasif. Premium'u Görüntüle",
    );
    await fireEvent.press(premiumRow);
    expect(onOpenPremium).toHaveBeenCalledTimes(1);
  });

  it('renders legal destinations, lightweight contacts, and the final footer without an App group', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    await view.findByText('Responsible Gaming');
    for (const label of [
      '18+ and Age Declaration',
      'Betting Risk and Responsible Gaming',
      'Terms of Use',
      'Privacy Policy',
      'Legal Information',
    ]) {
      expect(view.getByRole('button', { name: label })).toBeTruthy();
    }
    expect(view.queryByText('App')).toBeNull();
    expect(
      view.queryByText('Legal and support destinations are not yet available.'),
    ).toBeNull();
    expect(
      view.getByRole('link', { name: 'pitchvalue@outlook.com' }),
    ).toBeTruthy();
    expect(view.getByRole('link', { name: '@pitchvalueapp' })).toBeTruthy();
    expect(view.getByText(/^Version /)).toBeTruthy();
    expect(view.getByText('crtnapp © 2026')).toBeTruthy();
    const tree = JSON.stringify(view.toJSON());
    expect(tree.indexOf('profile-contact-area')).toBeLessThan(
      tree.indexOf('profile-footer'),
    );
    expect(tree.indexOf('Version')).toBeLessThan(
      tree.indexOf('crtnapp © 2026'),
    );
  });

  it('opens contact links only through supported platform URL handlers', async () => {
    const canOpenURL = jest
      .spyOn(Linking, 'canOpenURL')
      .mockResolvedValue(true);
    const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    await view.findByText('Responsible Gaming');
    await fireEvent.press(view.getByTestId('profile-email-link'));
    expect(canOpenURL).toHaveBeenCalledWith('mailto:pitchvalue@outlook.com');
    await waitFor(() =>
      expect(openURL).toHaveBeenCalledWith('mailto:pitchvalue@outlook.com'),
    );
    await fireEvent.press(view.getByTestId('profile-x-link'));
    expect(canOpenURL).toHaveBeenCalledWith('https://x.com/pitchvalueapp');
    await waitFor(() =>
      expect(openURL).toHaveBeenCalledWith('https://x.com/pitchvalueapp'),
    );
  });

  it('presents equal lightweight contact rows without trailing external-link indicators', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    await view.findByText('Responsible Gaming');
    const emailRow = view.getByTestId('profile-email-link');
    const xRow = view.getByTestId('profile-x-link');
    expect(StyleSheet.flatten(emailRow.props.style).minHeight).toBe(
      touchTarget,
    );
    expect(StyleSheet.flatten(xRow.props.style).minHeight).toBe(touchTarget);
    expect(
      StyleSheet.flatten(view.getByTestId('profile-contact-area').props.style)
        .backgroundColor,
    ).toBeUndefined();
    expect(view.queryByText(/^(Contact|Support)$/)).toBeNull();
    for (const testID of [
      'profile-email-link-external-icon',
      'profile-x-link-external-icon',
    ]) {
      expect(
        view.queryByTestId(testID, { includeHiddenElements: true }),
      ).toBeNull();
    }
  });

  it('keeps the footer inside a bottom safe-area boundary with breathing room', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    await view.findByText('Responsible Gaming');
    const footer = view.getByTestId('profile-footer');
    expect(footer.props.edges).toMatchObject({ bottom: 'additive' });
    expect(StyleSheet.flatten(footer.props.style).paddingBottom).toBe(
      spacing.md,
    );
  });

  it('localizes the complete legal and footer hierarchy in Turkish', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <LanguageProvider>
        <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />
      </LanguageProvider>,
    );
    for (const label of [
      'Sorumlu Oyun',
      '18+ ve Yaş Beyanı',
      'Bahis Riski ve Sorumlu Oyun',
      'Kullanım Koşulları',
      'Gizlilik Politikası',
      'Yasal Bilgiler',
      'pitchvalue@outlook.com',
      '@pitchvalueapp',
      'crtnapp © 2026',
    ]) {
      expect(await view.findByText(label)).toBeTruthy();
    }
    expect(view.getByText(/^Sürüm /)).toBeTruthy();
    expect(view.queryByText('Uygulama')).toBeNull();
  });

  it.each(entitlementStates)(
    'renders canonical entitlement %s',
    async (state) => {
      const view = await render(
        <LanguageProvider>
          <ProfileView entitlement={state} onSignIn={jest.fn()} />
        </LanguageProvider>,
      );
      await view.findByText('Account');
      expect(view.queryByText('Subscription')).toBeNull();
      expect(view.getByText('Premium')).toBeTruthy();
      expect(view.getByTestId('profile-premium-value')).toHaveTextContent(
        englishStatusLabels[state],
      );
      expect(view.queryByText(/Free|Basic|Standard/)).toBeNull();
    },
  );

  it('shows authoritative identity in Account and Sign Out below contacts', async () => {
    setActiveAppearance('dark');
    const onSignOut = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="PREMIUM_ACTIVE"
          authenticated
          email="person@example.com"
          onSignIn={jest.fn()}
          onSignOut={onSignOut}
        />
      </LanguageProvider>,
    );
    await view.findByText('Account');
    expect(view.getByText('person@example.com')).toBeTruthy();
    expect(view.getByText('Active')).toBeTruthy();
    expect(view.queryByText('Subscription')).toBeNull();
    const tree = JSON.stringify(view.toJSON());
    expect(tree.indexOf('profile-sign-out')).toBeGreaterThan(
      tree.indexOf('profile-x-link'),
    );
    expect(tree.indexOf('profile-sign-out')).toBeLessThan(
      tree.indexOf('profile-footer'),
    );
    expect(
      view.getByTestId('profile-account-identity').props.accessibilityLabel,
    ).toBe('person@example.com');
    const signOutText = view.getByText('Sign out');
    expect(StyleSheet.flatten(signOutText.props.style).color).toBe(
      darkColors.negative,
    );
    await fireEvent.press(view.getByTestId('profile-sign-out'));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('keeps Sign Out destructive in Light appearance', async () => {
    setActiveAppearance('light');
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="PREMIUM_ACTIVE"
          authenticated
          email="person@example.com"
          onSignIn={jest.fn()}
          onSignOut={jest.fn()}
        />
      </LanguageProvider>,
    );
    expect(
      StyleSheet.flatten(view.getByText('Sign out').props.style).color,
    ).toBe(lightColors.negative);
  });

  it('keeps authenticated identity separate from a non-Premium entitlement', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView
          authenticated
          entitlement="GUEST"
          email="member@example.com"
          onSignIn={jest.fn()}
          onSignOut={jest.fn()}
        />
      </LanguageProvider>,
    );
    expect(await view.findByText('member@example.com')).toBeTruthy();
    expect(view.getByTestId('profile-premium-value')).toHaveTextContent(
      'Inactive',
    );
    expect(view.queryByTestId('profile-account-sign-in')).toBeNull();
    expect(view.getByTestId('profile-sign-out')).toBeTruthy();
  });

  it('truncates a long authoritative email and has a truthful signed-in fallback', async () => {
    const view = await render(
      <LanguageProvider>
        <ProfileView
          authenticated
          entitlement="PREMIUM_INACTIVE"
          email="a-very-long-email-address@example-football-domain.com"
          onSignIn={jest.fn()}
        />
      </LanguageProvider>,
    );
    await view.findByTestId('profile-account-identity');
    expect(
      view.getByText('a-very-long-email-address@example-football-domain.com')
        .props.numberOfLines,
    ).toBe(1);
    view.rerender(
      <LanguageProvider>
        <ProfileView
          authenticated
          entitlement="PREMIUM_INACTIVE"
          onSignIn={jest.fn()}
        />
      </LanguageProvider>,
    );
    expect(await view.findByText('Signed in')).toBeTruthy();
    expect(view.queryByText('user@example.com')).toBeNull();
  });

  it.each(entitlementStates)(
    'renders canonical entitlement %s correctly in Turkish',
    async (state) => {
      const view = await render(
        <LanguageProvider>
          <ProfileView entitlement={state} onSignIn={jest.fn()} />
        </LanguageProvider>,
      );
      await view.findByText(/Account|Hesap/);
      await fireEvent.press(view.getByTestId('profile-language-row'));
      await fireEvent.press(view.getByTestId('language-option-tr'));
      expect(await view.findByText('Hesap')).toBeTruthy();
      expect(view.getByTestId('profile-premium-value')).toHaveTextContent(
        turkishStatusLabels[state],
      );
      if (state === 'GUEST') {
        expect(view.getByText('Giriş Yap')).toBeTruthy();
      }
      expect(view.queryByText('Abonelik')).toBeNull();
    },
  );
});
