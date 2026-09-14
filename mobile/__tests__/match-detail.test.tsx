import { fireEvent, render } from '@testing-library/react-native';

import { MatchDetailView, parseCanonicalMatchId } from '@/app/match/[id]';
import { MatchDetailSkeleton } from '@/components/feedback';
import {
  AllMarkets,
  FinalCheckSection,
  MarketRow,
  StatisticsSection,
  marketGroups,
  marketStateCopy,
} from '@/components/match-detail';
import { PublicApiError } from '@/lib/public-api';
import { publicMarketStates } from '@/types/public-api';

import {
  makeMarket,
  makeMatchDetail,
  makePrediction,
  v1MarketNames,
  withFinalCheck,
} from '../test-support/match-detail-fixtures';

describe('Match Detail resource and fixture identity', () => {
  it('renders a structural loading skeleton hidden from accessibility', async () => {
    const view = await render(<MatchDetailSkeleton />);
    const skeleton = view.getByTestId('match-detail-skeleton', {
      includeHiddenElements: true,
    });
    expect(skeleton).toHaveProp(
      'importantForAccessibility',
      'no-hide-descendants',
    );
  });

  it('renders scheduled fixture identity without requiring score', async () => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail()}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
    expect(view.getByText('Scheduled')).toBeTruthy();
    expect(view.queryByText(/0 – 0/)).toBeNull();
    expect(view.queryByText(/^Save$/)).toBeNull();
    expect(view.queryByText(/^Saved$/)).toBeNull();
  });

  it('shows an authoritative finished score only when present', async () => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail({
          fixture_status: 'FINISHED',
          score: { home: 2, away: 1, result: 'H' },
        })}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByLabelText('Final score 2 to 1')).toBeTruthy();
    expect(view.getByText('Finished')).toBeTruthy();
  });

  it('uses a full-screen safe error only without retained fixture data', async () => {
    const view = await render(
      <MatchDetailView
        data={null}
        error={new PublicApiError('API_UNAVAILABLE')}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(
      view.getByText('Match data is temporarily unavailable'),
    ).toBeTruthy();
    expect(
      view.getByLabelText('Retry: Match data is temporarily unavailable'),
    ).toBeTruthy();
  });

  it('keeps retained fixture data after refresh failure', async () => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail()}
        error={new PublicApiError('API_UNAVAILABLE')}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
    expect(view.getByText('Could not refresh match detail')).toBeTruthy();
  });

  it.each([
    [undefined, null],
    ['', null],
    ['abc', null],
    ['0', null],
    ['-1', null],
    [['42', '43'], 42],
    ['42', 42],
  ] as const)('parses route ID %p safely', (value, expected) => {
    expect(parseCanonicalMatchId(value)).toBe(expected);
  });
});

describe('public analysis integrity', () => {
  it('shows every public prediction neutrally without ranking', async () => {
    const detail = makeMatchDetail({
      public_predictions: [
        makePrediction({ selection: 'HOME' }),
        makePrediction({ selection: 'DRAW', edge: '0.031' }),
      ],
    });
    const view = await render(
      <MatchDetailView
        data={detail}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('2 published selections')).toBeTruthy();
    expect(view.getByText('0.031')).toBeTruthy();
    expect(view.getAllByText('76 / 100').length).toBeGreaterThan(0);
    expect(view.queryByText(/agree/i)).toBeNull();
  });

  it('preserves null Bet Score and authoritative probability values', async () => {
    const detail = makeMatchDetail({
      public_predictions: [
        makePrediction({
          bet_score: null,
          bet_score_completeness: 'PARTIAL',
          edge: '0.071',
          model_probability: '0.541',
          no_vig_market_probability: '0.470',
        }),
      ],
    });
    const view = await render(
      <MatchDetailView
        data={detail}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getAllByText('Score unavailable').length).toBeGreaterThan(0);
    expect(view.queryByText('0 / 100')).toBeNull();
    expect(view.getByText('0.071')).toBeTruthy();
    expect(view.getByText('Model probability 0.541')).toBeTruthy();
    expect(view.getByText('Market probability 0.470')).toBeTruthy();
  });

  it.each([
    ['NO_PUBLIC_ANALYSIS', 'NO_PUBLIC_ANALYSIS', 'No analysis published'],
    ['DATA_INSUFFICIENT', 'DATA_INSUFFICIENT', 'Not enough reliable data'],
  ] as const)(
    'preserves analysis state %s',
    async (publicAnalysis, publicationState, expected) => {
      const view = await render(
        <MatchDetailView
          data={makeMatchDetail({
            public_analysis: publicAnalysis,
            publication_state: publicationState,
            public_predictions: [],
          })}
          error={null}
          initialLoading={false}
          onRefresh={jest.fn()}
          refreshing={false}
        />,
      );
      expect(view.getByText(expected)).toBeTruthy();
    },
  );
});

describe('all markets and canonical state semantics', () => {
  it('represents all nine V1 market families in five accessible groups', async () => {
    expect(new Set(marketGroups.flatMap((group) => group.names))).toEqual(
      new Set(v1MarketNames),
    );
    const view = await render(
      <AllMarkets markets={v1MarketNames.map((name) => makeMarket(name))} />,
    );
    for (const group of marketGroups) {
      const control = view.getByLabelText(`${group.title} markets`);
      expect(control.props.accessibilityState).toEqual({
        expanded: group.key === 'result',
      });
      if (group.key !== 'result') await fireEvent.press(control);
    }
    for (const market of v1MarketNames)
      expect(view.getByText(market)).toBeTruthy();
  });

  it.each(publicMarketStates)('keeps %s distinct', async (state) => {
    const view = await render(<MarketRow market={makeMarket('1X2', state)} />);
    expect(view.getAllByText(marketStateCopy[state]).length).toBeGreaterThan(0);
  });

  it('does not turn a null incomplete market score into zero', async () => {
    const view = await render(
      <MarketRow market={makeMarket('1X2', 'SCORE_INCOMPLETE')} />,
    );
    expect(view.getAllByText('Score unavailable')).toHaveLength(2);
    expect(view.queryByText('0')).toBeNull();
  });
});

describe('Final Check, freshness, and partial sections', () => {
  it.each([
    ['CONFIRMED', 'Analysis confirmed'],
    ['CHANGED', 'Analysis changed'],
    ['WITHDRAWN', 'Analysis withdrawn'],
    ['FINAL_CHECK_UNAVAILABLE', 'Final Check unavailable'],
  ] as const)('renders %s without synthesis', async (state, expected) => {
    const detail = withFinalCheck(state);
    const view = await render(<FinalCheckSection state={detail.final_check} />);
    expect(view.getAllByText(expected).length).toBeGreaterThan(0);
  });

  it('treats Final Check unavailable as normal and retains base analysis', async () => {
    const view = await render(
      <MatchDetailView
        data={withFinalCheck('FINAL_CHECK_UNAVAILABLE')}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('Current public analysis')).toBeTruthy();
    expect(view.getAllByText('Final Check unavailable').length).toBeGreaterThan(
      0,
    );
  });

  it('shows stale backend evidence without replacing fixture identity', async () => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail({
          freshness: {
            state: 'STALE',
            source_last_seen_at: '2026-09-10T07:00:00Z',
            fixture_refresh_at: null,
            evidence_source: 'fixture_source_last_seen',
          },
        })}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText('Data may be outdated')).toBeTruthy();
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
    expect(view.getByText(/Source evidence:/)).toBeTruthy();
  });

  it.each([
    ['UNAVAILABLE', 'Freshness information unavailable'],
    ['FAILED', 'Fixture refresh failed'],
  ] as const)('preserves %s freshness', async (state, expected) => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail({
          freshness: {
            state,
            source_last_seen_at: null,
            fixture_refresh_at: null,
            evidence_source: 'fixture_refresh_event',
          },
        })}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText(expected)).toBeTruthy();
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
  });

  it('uses only the backend evidence time for fresh metadata', async () => {
    const view = await render(
      <MatchDetailView
        data={makeMatchDetail()}
        error={null}
        initialLoading={false}
        onRefresh={jest.fn()}
        refreshing={false}
      />,
    );
    expect(view.getByText(/Source evidence:/)).toBeTruthy();
    expect(view.queryByText(/just now/i)).toBeNull();
  });

  it('omits unavailable statistics without blanking analysis', async () => {
    const detail = makeMatchDetail({ statistics: null });
    const view = await render(<StatisticsSection detail={detail} />);
    expect(view.toJSON()).toBeNull();
  });

  it('renders only persisted statistics and labels one-sided nulls unavailable', async () => {
    const detail = makeMatchDetail({
      statistics_state: 'AVAILABLE',
      statistics: {
        home_shots: 12,
        away_shots: null,
        home_shots_on_target: 5,
        away_shots_on_target: 3,
        home_possession: null,
        away_possession: null,
        home_corners: 4,
        away_corners: 2,
      },
    });
    const view = await render(<StatisticsSection detail={detail} />);
    expect(view.getByText('12')).toBeTruthy();
    expect(view.getByText('Unavailable')).toBeTruthy();
    expect(view.queryByText('0')).toBeNull();
  });
});
