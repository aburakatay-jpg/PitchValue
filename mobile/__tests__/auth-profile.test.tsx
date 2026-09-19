import { fireEvent, render } from '@testing-library/react-native';

import { ProfileView, profileGroups } from '@/app/profile';
import { AuthEntry, EmailAuthShell } from '@/components/AuthShell';
import { entitlementStates } from '@/types/entitlement';

describe('auth-safe presentation', () => {
  it('shows canonical auth methods without faking success and keeps Guest usable', async () => {
    const onGuest = jest.fn();
    const onEmail = jest.fn();
    const view = await render(
      <AuthEntry onEmail={onEmail} onGuest={onGuest} />,
    );
    for (const provider of ['Apple', 'Google']) {
      expect(
        view.getByLabelText(`Continue with ${provider}, unavailable`),
      ).toBeDisabled();
    }
    await fireEvent.press(view.getByLabelText('Continue with Email'));
    expect(onEmail).toHaveBeenCalledTimes(1);
    expect(view.queryByText(/continue with sms/i)).toBeNull();
    await fireEvent.press(view.getByText('Continue as Guest'));
    expect(onGuest).toHaveBeenCalledTimes(1);
  });

  it('provides labeled email/password semantics and honest disabled submission', async () => {
    const view = await render(<EmailAuthShell />);
    const email = view.getByLabelText('Email');
    const password = view.getByLabelText('Password');
    expect(email).toHaveProp('keyboardType', 'email-address');
    expect(password).toHaveProp('secureTextEntry', true);
    expect(view.getByLabelText('Sign in')).toBeDisabled();
    await fireEvent.changeText(email, 'invalid');
    await fireEvent(email, 'blur');
    expect(view.getByText('Enter a valid email address.')).toBeTruthy();
  });

  it('submits email authentication only through a real service callback', async () => {
    const onSignIn = jest.fn().mockResolvedValue(undefined);
    const view = await render(<EmailAuthShell onSignIn={onSignIn} />);
    await fireEvent.changeText(
      view.getByLabelText('Email'),
      'user@example.com',
    );
    await fireEvent.changeText(
      view.getByLabelText('Password'),
      'SecurePassword1!',
    );
    await fireEvent.press(view.getByLabelText('Sign in'));
    expect(onSignIn).toHaveBeenCalledWith(
      'user@example.com',
      'SecurePassword1!',
    );
  });
});

import { LanguageProvider } from '@/features/language/LanguageContext';

describe('Profile foundation', () => {
  it('renders all canonical groups and a truthful Guest state', async () => {
    const onSignIn = jest.fn();
    const view = await render(
      <LanguageProvider>
        <ProfileView
          entitlement="GUEST"
          onSignIn={onSignIn}
          onViewPremium={jest.fn()}
        />
      </LanguageProvider>,
    );
    // Wait for async storage LanguageProvider initialization
    await view.findByText('Account');

    for (const group of profileGroups) {
      expect(view.getByText(group)).toBeTruthy();
    }

    expect(view.getAllByText('Guest').length).toBeGreaterThan(0);
    await fireEvent.press(view.getByText('Sign in'));
    expect(onSignIn).toHaveBeenCalledTimes(1);

    // Verify track record / My Bets is removed from Profile
    expect(view.queryByText(/Open My Bets/i)).toBeNull();
  });

  it.each(entitlementStates)(
    'renders canonical entitlement %s',
    async (state) => {
      const view = await render(
        <LanguageProvider>
          <ProfileView
            entitlement={state}
            onSignIn={jest.fn()}
            onViewPremium={jest.fn()}
          />
        </LanguageProvider>,
      );
      await view.findByText('Subscription');
      expect(view.getByText('Subscription')).toBeTruthy();
      expect(view.queryByText(/Free|Basic|Standard/)).toBeNull();
    },
  );
});
