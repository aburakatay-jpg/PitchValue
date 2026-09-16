import { render } from '@testing-library/react-native';
import { Text } from 'react-native';

jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  Stack: { Screen: () => null },
}));

import NotFoundScreen from '@/app/+not-found';
import { TodayFixtureCard } from '@/components/discovery';
import {
  Button,
  Screen,
  SectionHeader,
  stackScreenEdges,
} from '@/components/ui';
import type { PublicFixtureSummary } from '@/types/public-api';

const longFixture: PublicFixtureSummary = {
  match_id: 942,
  competition: 'A Very Long International Competition Name',
  kickoff: '2026-09-16T18:00:00Z',
  home_team: { name: 'Very Long Canonical Home Football Club United' },
  away_team: { name: 'Very Long Canonical Away Athletic Association' },
  fixture_status: 'SCHEDULED',
  data_availability: 'AVAILABLE',
  public_analysis: 'NO_PUBLIC_ANALYSIS',
  publication_state: 'NO_PUBLIC_ANALYSIS',
  final_check: 'FINAL_CHECK_UNAVAILABLE',
  freshness: {
    state: 'FRESH',
    source_last_seen_at: null,
    fixture_refresh_at: '2026-09-16T08:00:00Z',
    evidence_source: 'fixture_refresh_event',
  },
};

describe('cross-surface release hardening', () => {
  it('announces shared section titles as headings', async () => {
    const view = await render(
      <SectionHeader title="Published analysis" detail="Current state" />,
    );
    expect(
      view.getByRole('header', { name: 'Published analysis' }),
    ).toBeTruthy();
  });

  it('exposes disabled controls semantically without hiding their text', async () => {
    const view = await render(<Button disabled>Unavailable action</Button>);
    const button = view.getByRole('button', { name: 'Unavailable action' });
    expect(button).toBeDisabled();
    expect(button.props.accessibilityState).toEqual({ disabled: true });
  });

  it('supports stack safe areas and keyboard-adjusted scrolling', async () => {
    const view = await render(
      <Screen keyboardAware safeAreaEdges={stackScreenEdges}>
        <Text>Form content</Text>
      </Screen>,
    );
    expect(view.getByTestId('screen-safe-area').props.edges).toMatchObject({
      bottom: 'additive',
      left: 'additive',
      right: 'additive',
      top: 'off',
    });
    expect(view.getByTestId('screen-scroll-view')).toHaveProp(
      'automaticallyAdjustKeyboardInsets',
      true,
    );
  });

  it('does not truncate primary fixture identity in code', async () => {
    const view = await render(
      <TodayFixtureCard fixture={longFixture} timezone="Europe/Istanbul" />,
    );
    for (const value of [
      longFixture.competition,
      longFixture.home_team.name,
      longFixture.away_team.name,
    ]) {
      expect(view.getByText(value)).not.toHaveProp('numberOfLines');
    }
  });

  it('uses an accessible dark-safe unknown-route recovery surface', async () => {
    const view = await render(<NotFoundScreen />);
    expect(
      view.getByRole('header', { name: 'This screen is unavailable' }),
    ).toBeTruthy();
    expect(view.getByRole('button', { name: 'Return to Today' })).toBeTruthy();
    expect(view.queryByText(/route|debug|stack|URL/i)).toBeNull();
  });
});
