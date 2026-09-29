import { fireEvent, render } from '@testing-library/react-native';

import EmailAuthScreen from '@/app/auth/email';
import DeleteAccountScreen from '@/app/account/delete';
import { ProfileView } from '@/app/profile';
import { LegalModal } from '@/components/LegalModal';
import { PaywallShell } from '@/components/Paywall';
import { LEGAL_DOCUMENTS } from '@/legal/content';

jest.mock('@/features/appearance/AppearanceContext', () => ({
  appearancePreferences: ['system', 'dark', 'light'],
  useAppearance: () => ({
    preference: 'system',
    resolvedAppearance: 'dark',
    setPreference: jest.fn(),
  }),
  useOptionalAppearanceResolution: () => 'dark',
}));

jest.mock('@/features/session/ProductSessionContext', () => ({
  useProductSession: () => ({
    state: 'GUEST',
    user: null,
    accessToken: null,
    signUpEmail: jest.fn(),
    refreshUser: jest.fn(),
    signOut: jest.fn(),
  }),
}));

jest.mock('@/features/entitlement/EntitlementContext', () => ({
  useEntitlement: () => ({ state: 'GUEST', openPaywall: jest.fn() }),
}));

jest.mock('@/features/entitlement/CommerceContext', () => ({
  useCommerce: () => ({
    isConfigured: false,
    products: [],
    isFetchingProducts: false,
    isPurchasing: false,
    isRestoring: false,
    error: null,
    purchase: jest.fn(),
    restore: jest.fn(),
  }),
}));

describe('in-app legal surfaces', () => {
  it('opens with the correct title and content and closes accessibly', async () => {
    const onClose = jest.fn();
    const view = await render(
      <LegalModal documentId="terms" onClose={onClose} />,
    );

    expect(view.getByTestId('legal-modal-title').props.children).toBe(
      'Kullanım Koşulları',
    );
    expect(view.getByTestId('legal-modal-content').props.children).toContain(
      'BURAK ATAY',
    );

    await fireEvent.press(view.getByTestId('legal-modal-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('opens registration Terms, Privacy and 18+ links inside the app', async () => {
    const view = await render(<EmailAuthScreen />);

    await fireEvent.press(view.getByRole('link', { name: 'Terms of Use' }));
    expect(view.getByTestId('legal-modal-title').props.children).toBe(
      'Kullanım Koşulları',
    );
    await fireEvent.press(view.getByTestId('legal-modal-close'));

    await fireEvent.press(view.getByRole('link', { name: 'Privacy Policy' }));
    expect(view.getByTestId('legal-modal-title').props.children).toBe(
      'Gizlilik Politikası',
    );
    await fireEvent.press(view.getByTestId('legal-modal-close'));

    await fireEvent.press(
      view.getByRole('link', { name: '18+ and Age Declaration' }),
    );
    expect(view.getByTestId('legal-modal-title').props.children).toBe(
      '18+ ve Yaş Beyanı',
    );
  });

  it('opens Profile legal rows in the shared modal', async () => {
    const view = await render(
      <ProfileView entitlement="GUEST" onSignIn={jest.fn()} />,
    );

    await fireEvent.press(view.getByRole('button', { name: 'Privacy Policy' }));
    expect(view.getByTestId('legal-modal-content').props.children).toContain(
      'push tokenlarını siler',
    );
  });

  it('opens Paywall legal links in the shared modal', async () => {
    const view = await render(<PaywallShell />);

    await fireEvent.press(view.getByTestId('paywall-legal-subscription'));
    expect(view.getByTestId('legal-modal-content').props.children).toContain(
      'güncel fiyatı',
    );
  });

  it('opens account-deletion Privacy and Terms without leaving the app', async () => {
    const view = await render(<DeleteAccountScreen />);

    await fireEvent.press(view.getByTestId('delete-legal-privacy'));
    expect(view.getByTestId('legal-modal-title').props.children).toBe(
      'Gizlilik Politikası',
    );
  });

  it('contains no unsupported fixed TRY prices or three-day trial claim', () => {
    const subscription = LEGAL_DOCUMENTS.subscription.content;
    expect(subscription).not.toMatch(/499[,.]99|999[,.]99|2[.]?999[,.]99/i);
    expect(subscription).not.toMatch(/3 günlük ücretsiz deneme/i);
    expect(subscription).toContain(
      '“Restore Purchases / Satın Almaları Geri Yükle” işlevi mevcut sürümde operasyonel değildir.',
    );
  });

  it('does not represent Restore Purchases as operational', async () => {
    const view = await render(<PaywallShell />);
    expect(view.getByTestId('paywall-restore')).toBeDisabled();
    expect(view.getByTestId('paywall-restore-unavailable')).toBeTruthy();
  });
});
