import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { StyleSheet, Text } from 'react-native';

import {
  PaywallPresentation,
  PaywallShell,
  annualPlanDetail,
} from '@/components/Paywall';
import { LockedPremiumSection, PremiumGuard } from '@/components/PremiumGuard';
import * as CommerceContext from '@/features/entitlement/CommerceContext';
import { useLanguage } from '@/features/language/LanguageContext';
import * as SessionContext from '@/features/session/ProductSessionContext';
import { defaultCommerceAdapter } from '@/lib/commerce';
import { darkColors, lightColors, setActiveAppearance } from '@/theme/tokens';

jest.mock('@/features/entitlement/CommerceContext', () => ({
  useCommerce: jest.fn(),
  CommerceProvider: ({ children }: any) => children,
}));

jest.mock('@/features/session/ProductSessionContext', () => ({
  useProductSession: jest.fn(),
}));

function TurkishSwitch() {
  const { setLanguage } = useLanguage();
  return <Text onPress={() => setLanguage('tr')}>switch-to-turkish</Text>;
}

describe('premium UI foundation', () => {
  const mockProducts = [
    {
      id: 'monthly' as const,
      externalId: 'a',
      provider: 'UNCONFIGURED' as const,
      localizedPrice: null,
      currencyCode: null,
      isTrialAvailable: false,
    },
    {
      id: 'quarterly' as const,
      externalId: 'b',
      provider: 'UNCONFIGURED' as const,
      localizedPrice: null,
      currencyCode: null,
      isTrialAvailable: false,
    },
    {
      id: 'annual' as const,
      externalId: 'c',
      provider: 'UNCONFIGURED' as const,
      localizedPrice: null,
      currencyCode: null,
      isTrialAvailable: false,
    },
  ];

  beforeEach(() => {
    (SessionContext.useProductSession as jest.Mock).mockReturnValue({
      state: 'GUEST',
    });
    (CommerceContext.useCommerce as jest.Mock).mockReturnValue({
      isConfigured: false,
      products: mockProducts,
      isFetchingProducts: false,
      isPurchasing: false,
      isRestoring: false,
      error: null,
      purchase: jest.fn(),
      restore: jest.fn(),
    });
  });

  afterEach(() => setActiveAppearance('dark'));

  it('uses a contextual, accessible premium boundary for guests', async () => {
    const onUnlock = jest.fn();
    const view = await render(
      <LockedPremiumSection
        detail="See the complete evidence behind this analysis."
        onUnlock={onUnlock}
        title="Unlock analysis details"
      />,
    );
    expect(view.getByLabelText('Premium content locked')).toBeTruthy();
    await fireEvent.press(view.getByText('View Premium'));
    expect(onUnlock).toHaveBeenCalledTimes(1);
  });

  it('locks premium content for a guest', async () => {
    const view = await render(
      <PremiumGuard state="GUEST">
        <Text>Unlocked insight</Text>
      </PremiumGuard>,
    );
    expect(view.getByLabelText('Premium content locked')).toBeTruthy();
    expect(view.queryByText('Unlocked insight')).toBeNull();
  });

  it.each(['PREMIUM_ACTIVE', 'PREMIUM_TRIAL'] as const)(
    'unlocks premium content for %s',
    async (state) => {
      const view = await render(
        <PremiumGuard state={state}>
          <Text>Unlocked insight</Text>
        </PremiumGuard>,
      );
      expect(view.getByText('Unlocked insight')).toBeTruthy();
    },
  );

  it('locks expired premium', async () => {
    const view = await render(
      <PremiumGuard state="PREMIUM_EXPIRED">
        <Text>Unlocked insight</Text>
      </PremiumGuard>,
    );
    expect(view.getByLabelText('Premium content locked')).toBeTruthy();
  });

  it('keeps three disabled plan concepts without treating placeholders as products', async () => {
    const view = await render(<PaywallShell />);
    expect(
      (await defaultCommerceAdapter.queryProducts()).every(
        (product) => product.provider === 'UNCONFIGURED',
      ),
    ).toBe(true);
    expect(view.getByTestId('paywall-plan-group')).toBeTruthy();
    for (const plan of ['monthly', 'quarterly', 'annual']) {
      const row = view.getByTestId(`paywall-plan-${plan}`);
      expect(row).toBeDisabled();
      expect(row.props.accessibilityState.checked).toBe(false);
    }
    expect(view.getByText('Monthly')).toBeTruthy();
    expect(view.getByText('3 Months')).toBeTruthy();
    expect(view.getByText('Annual')).toBeTruthy();
    expect(view.getAllByText('—')).toHaveLength(3);
    expect(
      view.getByTestId('paywall-plan-monthly').props.accessibilityLabel,
    ).toBe('Monthly, Price unavailable');
    expect(
      view.queryByText('Plans and prices are currently unavailable.'),
    ).toBeNull();
    expect(view.queryByText(/TL|\$|€|£/)).toBeNull();
    expect(view.getByTestId('paywall-primary')).toBeDisabled();
  });

  it('does not promise a trial without store eligibility', async () => {
    const view = await render(<PaywallShell trialEligibility="unknown" />);
    expect(view.queryByText(/3-day|free trial/i)).toBeNull();
    expect(annualPlanDetail('unknown', (k) => k)).toMatch(
      /require the App Store/i,
    );
  });

  it('does not claim even eligible presentation has verified a trial', () => {
    expect(annualPlanDetail('eligible', (k) => k)).toMatch(/may be offered/i);
  });

  it('keeps purchase and restore actions honestly disabled', async () => {
    const view = await render(<PaywallShell />);
    expect(view.getByLabelText('Go Premium')).toBeDisabled();
    expect(view.getByLabelText('Restore purchases')).toBeDisabled();
  });

  it('renders only authoritative catalog rows with accessible selection and store price', async () => {
    const purchase = jest.fn();
    (CommerceContext.useCommerce as jest.Mock).mockReturnValue({
      isConfigured: true,
      products: [
        { ...mockProducts[0], provider: 'APPLE', localizedPrice: '£4.99' },
        mockProducts[1],
      ],
      isFetchingProducts: false,
      isPurchasing: false,
      isRestoring: false,
      purchase,
      restore: jest.fn(),
    });
    setActiveAppearance('light');
    const view = await render(<PaywallShell />);
    const monthly = view.getByRole('radio', { name: 'Monthly, £4.99' });
    expect(view.getByText('3 Months')).toBeTruthy();
    expect(view.getByTestId('paywall-plan-quarterly')).toBeDisabled();
    expect(monthly.props.accessibilityState.checked).toBe(false);
    await fireEvent.press(monthly);
    expect(monthly.props.accessibilityState.checked).toBe(true);
    expect(StyleSheet.flatten(monthly.props.style).backgroundColor).toBe(
      lightColors.segmentedSelectedBackground,
    );
    expect(view.getByLabelText('Go Premium')).toBeDisabled();
    expect(purchase).not.toHaveBeenCalled();
  });

  it('retains the established Dark selected-plan treatment', async () => {
    (CommerceContext.useCommerce as jest.Mock).mockReturnValue({
      isConfigured: true,
      products: [
        { ...mockProducts[0], provider: 'APPLE', localizedPrice: '£4.99' },
      ],
      isFetchingProducts: false,
      isPurchasing: false,
      isRestoring: false,
      purchase: jest.fn(),
      restore: jest.fn(),
    });
    setActiveAppearance('dark');
    const darkView = await render(<PaywallShell />);
    await fireEvent.press(await darkView.findByTestId('paywall-plan-monthly'));
    await waitFor(() =>
      expect(
        StyleSheet.flatten(
          darkView.getByTestId('paywall-plan-monthly').props.style,
        ).backgroundColor,
      ).toBe(darkColors.segmentedSelectedBackground),
    );
  });

  it('uses the Light auth CTA only for a selected priced product and authenticated session', async () => {
    const purchase = jest.fn().mockResolvedValue(undefined);
    (CommerceContext.useCommerce as jest.Mock).mockReturnValue({
      isConfigured: true,
      products: [
        { ...mockProducts[0], provider: 'APPLE', localizedPrice: '£4.99' },
      ],
      isFetchingProducts: false,
      isPurchasing: false,
      isRestoring: false,
      purchase,
      restore: jest.fn(),
    });
    (SessionContext.useProductSession as jest.Mock).mockReturnValue({
      state: 'AUTHENTICATED',
    });
    setActiveAppearance('light');
    const view = await render(<PaywallShell />);
    const cta = await view.findByTestId('paywall-primary');
    expect(cta).toBeDisabled();
    await fireEvent.press(view.getByTestId('paywall-plan-monthly'));
    expect(cta).toBeEnabled();
    expect(StyleSheet.flatten(cta.props.style).backgroundColor).toBe(
      lightColors.authPrimaryBackground,
    );
    await fireEvent.press(cta);
    expect(purchase).toHaveBeenCalledWith('monthly');
  });

  it('uses a reduced headline and renders the six approved V1 benefits in order', async () => {
    setActiveAppearance('light');
    const view = await render(<PaywallShell />);
    const headline = await view.findByText(
      'Not more predictions.\nBetter filtering.',
    );
    expect(headline).toHaveProp('accessibilityRole', 'header');
    expect(StyleSheet.flatten(headline.props.style)).toMatchObject({
      fontSize: 28,
      lineHeight: 34,
      fontWeight: '800',
    });
    expect(view.getByText('With Premium')).toBeTruthy();
    expect(
      StyleSheet.flatten(view.getByTestId('paywall-plan-group').props.style)
        .backgroundColor,
    ).toBe(lightColors.surface);
    const benefits = [
      'More powerful analysis with PV Engine',
      'Discover value opportunities faster',
      'Edge and Bet Score visibility',
      'Deeper insights across supported markets',
      'A final review with Final Check',
      'Premium filtering experience',
    ];
    for (const [index, benefit] of benefits.entries()) {
      expect(view.getByTestId(`paywall-benefit-${index + 1}`)).toBeTruthy();
      expect(view.getByText(benefit)).toBeTruthy();
    }
    expect(
      view.queryByText('Premium feature details are not available yet.'),
    ).toBeNull();
    expect(view.queryByText(/Model Agreement/i)).toBeNull();
    expect(
      view.queryByText(/Payment, restoration, trial confirmation/),
    ).toBeNull();
    expect(view.getByTestId('paywall-restore')).toBeDisabled();
    expect(view.getByTestId('paywall-restore').props.style).toBeTruthy();
    expect(view.queryByText(/Restore Purchases · Unavailable/)).toBeNull();
    const tree = JSON.stringify(view.toJSON());
    expect(tree.indexOf('paywall-primary')).toBeLessThan(
      tree.indexOf('paywall-benefits'),
    );
    expect(tree.indexOf('paywall-benefit-6')).toBeLessThan(
      tree.indexOf('paywall-restore'),
    );
    expect(
      StyleSheet.flatten(view.getByTestId('paywall-primary').props.style)
        .backgroundColor,
    ).toBe(lightColors.surface);
  });

  it('contains no casino or urgency copy', async () => {
    const view = await render(<PaywallShell />);
    const output = JSON.stringify(view.toJSON());
    expect(output).not.toMatch(
      /WIN MORE|BOOST PROFITS|LIMITED TIME|countdown/i,
    );
  });

  it('keeps an accessible close control available', async () => {
    const onClose = jest.fn();
    const view = await render(<PaywallPresentation onClose={onClose} />);
    expect(view.queryByText('Close')).toBeNull();
    await fireEvent.press(await view.findByLabelText('Close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('localizes all app-owned Paywall controls in Turkish', async () => {
    const view = await render(
      <>
        <TurkishSwitch />
        <PaywallShell />
      </>,
    );
    await view.findByText('Not more predictions.\nBetter filtering.');
    await fireEvent.press(view.getByText('switch-to-turkish'));
    expect(
      await view.findByText('Daha fazla tahmin değil.\nDaha iyi filtreleme.'),
    ).toBeTruthy();
    expect(view.getByText('Aylık')).toBeTruthy();
    expect(view.getByText('3 Aylık')).toBeTruthy();
    expect(view.getByText('Yıllık')).toBeTruthy();
    expect(view.getByLabelText("Premium'a Geç")).toBeDisabled();
    expect(view.getByText('Premium ile')).toBeTruthy();
    for (const benefit of [
      'PV Engine ile daha güçlü analizler',
      'Değer fırsatlarını daha hızlı keşfet',
      'Edge ve Bet Score görünümü',
      'Desteklenen marketlerde daha derin içgörüler',
      'Final Check ile son kontrol',
      'Premium filtreleme deneyimi',
    ]) {
      expect(view.getByText(benefit)).toBeTruthy();
    }
    expect(view.getByLabelText('Satın alımları geri yükle')).toBeTruthy();
  });

  it('localizes the compact close control in Turkish', async () => {
    const view = await render(
      <>
        <TurkishSwitch />
        <PaywallPresentation onClose={jest.fn()} />
      </>,
    );
    await fireEvent.press(view.getByText('switch-to-turkish'));
    expect(view.getByLabelText('Kapat')).toBeTruthy();
    expect(view.queryByText('Kapat')).toBeNull();
  });
});
