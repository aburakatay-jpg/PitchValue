import { render } from '@testing-library/react-native';

jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
}));

import { AiScreen } from '@/app/(tabs)/ai';
import { BetsScreen } from '@/app/(tabs)/bets';
import { TodayView } from '@/app/(tabs)/today';
import { RootLanding } from '@/app/index';
import { mockMatches } from '@/dev/mock-data';
import { assistantFeatures } from '@/lib/assistant-contract';

describe('screen foundations', () => {
  it('renders the app root loading state', async () => {
    const view = await render(
      <RootLanding
        onAgeAccepted={jest.fn()}
        onComplete={jest.fn()}
        stage="LOADING"
      />,
    );
    expect(view.getByLabelText('Loading PitchValue')).toBeTruthy();
  });

  it('renders Today as a safe fixture empty state without mock fallback', async () => {
    const view = await render(
      <TodayView
        data={{
          fixture_date: '2026-09-14',
          timezone: 'Europe/Istanbul',
          state: 'NO_FIXTURES',
          fixtures: [],
          count: 0,
        }}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('No matches scheduled')).toBeTruthy();
    expect(view.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
  });

  it('renders all four AI actions', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ predictions: [], count: 0 }),
    });
    const view = await render(<AiScreen />);
    for (const action of assistantFeatures)
      expect(view.getByText(action)).toBeTruthy();
  });

  it('renders My Bets as an honest unavailable tracking workspace', async () => {
    const view = await render(<BetsScreen />);
    expect(view.getByText('Tracked selections unavailable')).toBeTruthy();
    expect(view.queryByText('Premium bet workspace placeholder')).toBeNull();
  });

  it('keeps mock fixtures clearly synthetic', () => {
    expect(mockMatches.length).toBeGreaterThan(0);
    expect(
      mockMatches.every((match) => /Development|Mock/.test(match.competition)),
    ).toBe(true);
  });
});
