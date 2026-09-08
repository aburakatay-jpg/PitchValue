import { render } from '@testing-library/react-native';

jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  useRouter: () => ({ replace: jest.fn() }),
}));

import { AiScreen } from '@/app/(tabs)/ai';
import { BetsScreen } from '@/app/(tabs)/bets';
import { TodayScreen } from '@/app/(tabs)/today';
import { RootLanding } from '@/app/index';
import { aiActions, mockMatches } from '@/dev/mock-data';

describe('screen foundations', () => {
  it('renders the app root loading state', async () => {
    const view = await render(<RootLanding loading onComplete={jest.fn()} />);
    expect(view.getByLabelText('Loading PitchValue')).toBeTruthy();
  });

  it('renders Today no-value state', async () => {
    const view = await render(<TodayScreen />);
    expect(view.getByText('No strong value found')).toBeTruthy();
  });

  it('renders all four AI actions', async () => {
    const view = await render(<AiScreen />);
    for (const action of aiActions) expect(view.getByText(action)).toBeTruthy();
  });

  it('renders My Bets as locked for the default guest', async () => {
    const view = await render(<BetsScreen />);
    expect(view.getByLabelText('Premium content locked')).toBeTruthy();
  });

  it('keeps mock fixtures clearly synthetic', () => {
    expect(mockMatches.length).toBeGreaterThan(0);
    expect(
      mockMatches.every((match) => /Development|Mock/.test(match.competition)),
    ).toBe(true);
  });
});
