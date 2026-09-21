import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { Linking } from 'react-native';

import AsyncStorage from '@react-native-async-storage/async-storage';

import AuthEntryScreen from '@/app/auth';
import { ProfileView, profileGroups } from '@/app/profile';
import { SignInShell } from '@/components/AuthShell';
import { signInScreenOptions } from '@/lib/navigation-options';
import { ProductServiceError } from '@/lib/product-api';
import { entitlementStates } from '@/types/entitlement';

const englishEntitlementLabels = {
  GUEST: 'Premium Inactive',
  PREMIUM_ACTIVE: 'Premium Active',
  PREMIUM_TRIAL: 'Premium Trial',
  PREMIUM_EXPIRED: 'Premium Expired',
  PREMIUM_INACTIVE: 'Premium Inactive',
} as const;

const turkishEntitlementLabels = {
  GUEST: 'Premium Pasif',
  PREMIUM_ACTIVE: 'Premium Aktif',
  PREMIUM_TRIAL: 'Premium Deneme',
  PREMIUM_EXPIRED: 'Premium Süresi Doldu',
  PREMIUM_INACTIVE: 'Premium Pasif',
} as const;

describe('auth-safe presentation', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  afterEach(async () => {
    await AsyncStorage.clear();
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
    expect(view.getByText('Premium Inactive')).toBeTruthy();
    expect(view.queryByText(/Guest access includes/i)).toBeNull();
    expect(
      view.queryByText(/Subscription management and restoration/i),
    ).toBeNull();
    await fireEvent.press(view.getByText('Sign In'));
    expect(onSignIn).toHaveBeenCalledTimes(1);

    // Verify track record / My Bets is removed from Profile
    expect(view.queryByText(/Open My Bets/i)).toBeNull();
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
      expect(view.getByText(englishEntitlementLabels[state])).toBeTruthy();
      expect(view.queryByText(/Free|Basic|Standard/)).toBeNull();
    },
  );

  it('keeps authenticated identity and sign-out inside the merged Account card', async () => {
    const onSignOut = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="PREMIUM_ACTIVE"
          email="person@example.com"
          onSignIn={jest.fn()}
          onSignOut={onSignOut}
        />
      </LanguageProvider>,
    );
    await view.findByText('Account');
    expect(view.getByText('person@example.com')).toBeTruthy();
    expect(view.getByText('Premium Active')).toBeTruthy();
    expect(view.queryByText('Subscription')).toBeNull();
    await fireEvent.press(view.getByText('Sign out'));
    expect(onSignOut).toHaveBeenCalledTimes(1);
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
      const turkishControl = view.queryByText('TR');
      if (turkishControl) {
        await fireEvent.press(turkishControl);
      }
      expect(await view.findByText('Hesap')).toBeTruthy();
      expect(view.getByText(turkishEntitlementLabels[state])).toBeTruthy();
      if (state === 'GUEST') {
        expect(view.getByText('Giriş Yap')).toBeTruthy();
      }
      expect(view.queryByText('Abonelik')).toBeNull();
    },
  );
});
