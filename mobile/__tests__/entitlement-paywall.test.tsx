import { render } from '@testing-library/react-native';
import { Text } from 'react-native';

import { PaywallShell } from '@/components/Paywall';
import { PremiumGuard } from '@/components/PremiumGuard';

describe('premium UI foundation', () => {
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

  it('does not promise a free trial when eligibility is unknown', async () => {
    const view = await render(<PaywallShell trialEligibility="unknown" />);
    expect(view.queryByText(/3-day trial/i)).toBeNull();
    expect(view.getByLabelText('Review annual option')).toBeTruthy();
  });

  it('shows trial CTA only for an eligible annual preview', async () => {
    const view = await render(<PaywallShell trialEligibility="eligible" />);
    expect(view.getByLabelText('Preview 3-day trial')).toBeTruthy();
  });

  it('shows continuation CTA when annual trial is ineligible', async () => {
    const view = await render(<PaywallShell trialEligibility="ineligible" />);
    expect(view.getByLabelText('Continue with annual')).toBeTruthy();
  });
});
