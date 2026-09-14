import { render } from '@testing-library/react-native';

const capturedHrefs: unknown[] = [];
jest.mock('expo-router', () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: unknown }) => {
    capturedHrefs.push(href);
    return children;
  },
}));

import { ExploreView } from '@/app/(tabs)/explore';
import { chronologicalFixtures, TodayView } from '@/app/(tabs)/today';
import {
  ExplorePredictionCard,
  TodayFixtureCard,
} from '@/components/discovery';
import {
  FixtureCardSkeleton,
  PredictionCardSkeleton,
} from '@/components/feedback';
import { PublicApiError } from '@/lib/public-api';
import type {
  PredictionListResponse,
  PublicFixtureSummary,
  PublicPrediction,
  TodayFixturesResponse,
} from '@/types/public-api';

const fixture = (
  id: number,
  kickoff: string,
  overrides: Partial<PublicFixtureSummary> = {},
): PublicFixtureSummary => ({
  match_id: id,
  competition: 'Premier League',
  kickoff,
  home_team: { name: `Home ${id}` },
  away_team: { name: `Away ${id}` },
  fixture_status: 'SCHEDULED',
  data_availability: 'AVAILABLE',
  public_analysis: 'NO_PUBLIC_ANALYSIS',
  publication_state: 'NO_PUBLIC_ANALYSIS',
  final_check: 'FINAL_CHECK_UNAVAILABLE',
  freshness: {
    state: 'FRESH',
    source_last_seen_at: '2026-09-14T07:00:00Z',
    fixture_refresh_at: '2026-09-14T07:00:00Z',
    evidence_source: 'fixture_refresh_event',
  },
  ...overrides,
});

const today = (
  fixtures: readonly PublicFixtureSummary[],
  state: TodayFixturesResponse['state'] = 'FIXTURES_AVAILABLE',
): TodayFixturesResponse => ({
  fixture_date: '2026-09-14',
  timezone: 'Europe/Istanbul',
  state,
  fixtures,
  count: fixtures.length,
});

const prediction = (
  id: number,
  selection: string,
  betScore: string | null = '72.5',
): PublicPrediction => ({
  match_id: id,
  market: 'match_result',
  selection,
  model_probability: '0.51',
  probability_source: 'RAW ML',
  prediction_as_of: '2026-09-14T08:00:00Z',
  generated_at: '2026-09-14T08:01:00Z',
  decimal_odds: '2.10',
  no_vig_market_probability: '0.47',
  edge: '0.04',
  policy_decision: 'PICK',
  score_class: 'PICK',
  bet_score: betScore,
  bet_score_completeness: betScore === null ? 'PARTIAL' : 'COMPLETE',
  blockers: [],
});

beforeEach(() => capturedHrefs.splice(0));

describe('Today production states', () => {
  it('renders a structural loading skeleton hidden from accessibility', async () => {
    const view = await render(
      <TodayView
        data={null}
        error={null}
        initialLoading
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(
      view.getAllByTestId('fixture-card-skeleton', {
        includeHiddenElements: true,
      }),
    ).toHaveLength(3);
    expect(
      view.getAllByTestId('fixture-card-skeleton', {
        includeHiddenElements: true,
      })[0],
    ).toHaveProp('importantForAccessibility', 'no-hide-descendants');
  });

  it('orders fixtures only by authoritative kickoff', () => {
    const ordered = chronologicalFixtures([
      fixture(2, '2026-09-14T20:00:00Z'),
      fixture(1, '2026-09-14T17:00:00Z'),
    ]);
    expect(ordered.map((item) => item.match_id)).toEqual([1, 2]);
  });

  it('keeps fixtures visible without public analysis and preserves insufficient data', async () => {
    const view = await render(
      <TodayView
        data={today([
          fixture(1, '2026-09-14T17:00:00Z'),
          fixture(2, '2026-09-14T20:00:00Z', {
            public_analysis: 'DATA_INSUFFICIENT',
            publication_state: 'DATA_INSUFFICIENT',
          }),
        ])}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('No analysis published')).toBeTruthy();
    expect(view.getByText('Not enough reliable data')).toBeTruthy();
    expect(view.queryByText('NO BET')).toBeNull();
  });

  it('distinguishes successful empty, stale, and API unavailable states', async () => {
    const empty = await render(
      <TodayView
        data={today([], 'NO_FIXTURES')}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(empty.getByText('No matches scheduled')).toBeTruthy();
    await empty.unmount();

    const stale = await render(
      <TodayView
        data={today(
          [
            fixture(1, '2026-09-14T17:00:00Z', {
              data_availability: 'STALE',
              freshness: {
                state: 'STALE',
                source_last_seen_at: null,
                fixture_refresh_at: '2026-09-10T07:00:00Z',
                evidence_source: 'fixture_refresh_event',
              },
            }),
          ],
          'STALE_FIXTURE_DATA',
        )}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(stale.getByText('Data may be outdated')).toBeTruthy();
    await stale.unmount();

    const unavailable = await render(
      <TodayView
        data={null}
        error={new PublicApiError('API_UNAVAILABLE')}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(
      unavailable.getByText('Match data is temporarily unavailable'),
    ).toBeTruthy();
  });

  it('keeps retained fixtures visible after refresh failure', async () => {
    const view = await render(
      <TodayView
        data={today([fixture(1, '2026-09-14T17:00:00Z')])}
        error={new PublicApiError('API_UNAVAILABLE')}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('Home 1')).toBeTruthy();
    expect(view.getByText('Could not refresh match data')).toBeTruthy();
  });
});

describe('Explore production states', () => {
  it('treats an empty publication response as success', async () => {
    const view = await render(
      <ExploreView
        data={{ predictions: [], count: 0 }}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('No publishable signals right now')).toBeTruthy();
  });

  it('preserves server order, server edge, and null score semantics', async () => {
    const data: PredictionListResponse = {
      predictions: [prediction(2, 'AWAY', null), prediction(1, 'HOME')],
      count: 2,
    };
    const view = await render(
      <ExploreView
        data={data}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(
      view.getAllByText(/AWAY|HOME/).map((node) => node.props.children),
    ).toEqual(['AWAY', 'HOME']);
    expect(view.getByText('Score unavailable')).toBeTruthy();
    expect(view.queryByText('0')).toBeNull();
    expect(view.getAllByText('0.04')).toHaveLength(2);
    expect(view.queryByText(/agree/i)).toBeNull();
  });

  it('uses a distinct skeleton and sanitized unavailable state', async () => {
    const loading = await render(
      <ExploreView
        data={null}
        error={null}
        initialLoading
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(
      loading.getAllByTestId('prediction-card-skeleton', {
        includeHiddenElements: true,
      }),
    ).toHaveLength(2);
    await loading.unmount();
    const failed = await render(
      <ExploreView
        data={null}
        error={new PublicApiError('API_UNAVAILABLE')}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(failed.getByText('Unable to load value signals')).toBeTruthy();
  });
});

describe('canonical navigation', () => {
  it('uses canonical IDs for Today and Explore links', async () => {
    await render(
      <TodayFixtureCard
        fixture={fixture(42, '2026-09-14T17:00:00Z')}
        timezone="Europe/Istanbul"
      />,
    );
    await render(<ExplorePredictionCard prediction={prediction(84, 'HOME')} />);
    expect(capturedHrefs).toEqual([
      { pathname: '/match/[id]', params: { id: '42' } },
      { pathname: '/match/[id]', params: { id: '84' } },
    ]);
  });
});
