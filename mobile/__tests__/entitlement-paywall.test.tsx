import { fireEvent, render } from '@testing-library/react-native';
import { Text } from 'react-native';

import {
  PaywallPresentation,
  PaywallShell,
  annualPlanDetail,
  plans,
} from '@/components/Paywall';
import { LockedPremiumSection, PremiumGuard } from '@/components/PremiumGuard';

describe('premium UI foundation', () => {
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

  it('presents all three plan concepts without hardcoded store prices', async () => {
    expect(plans.map((plan) => plan.name)).toEqual([
      'Monthly',
      '3 Months',
      'Annual',
    ]);
    const view = await render(<PaywallShell />);
    expect(view.getAllByText('Localized price unavailable')).toHaveLength(3);
    expect(view.queryByText(/TL|\$|€|£/)).toBeNull();
    expect(view.getAllByText('Purchase unavailable')).toHaveLength(3);
  });

  it('does not promise a trial without store eligibility', async () => {
    const view = await render(<PaywallShell trialEligibility="unknown" />);
    expect(view.queryByText(/3-day|free trial/i)).toBeNull();
    expect(annualPlanDetail('unknown')).toMatch(/require the App Store/i);
  });

  it('does not claim even eligible presentation has verified a trial', () => {
    expect(annualPlanDetail('eligible')).toMatch(/may be offered/i);
  });

  it('keeps purchase and restore actions honestly disabled', async () => {
    const view = await render(<PaywallShell />);
    for (const plan of plans) {
      expect(
        view.getByLabelText(`${plan.name} purchase unavailable`),
      ).toBeDisabled();
    }
    expect(view.getByLabelText('Restore purchases unavailable')).toBeDisabled();
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
    await fireEvent.press(view.getByLabelText('Close Premium options'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
