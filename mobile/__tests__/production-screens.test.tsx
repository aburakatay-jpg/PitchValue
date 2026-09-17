import { render, waitFor } from '@testing-library/react-native';

jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
}));

import ExploreScreen from '@/app/(tabs)/explore';
import AiScreen from '@/app/(tabs)/ai';
import { TodayScreen } from '@/app/(tabs)/today';
import { mockMatches } from '@/dev/mock-data';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  jest.restoreAllMocks();
});

describe('production-connected discovery screens', () => {
  it('renders Today from /api/v1/fixtures/today without requiring analysis', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        fixture_date: '2026-09-14',
        timezone: 'Europe/Istanbul',
        state: 'FIXTURES_AVAILABLE',
        count: 1,
        fixtures: [
          {
            match_id: 77,
            competition: 'Premier League',
            kickoff: '2026-09-14T17:00:00Z',
            home_team: { name: 'Canonical Home' },
            away_team: { name: 'Canonical Away' },
            fixture_status: 'SCHEDULED',
            data_availability: 'AVAILABLE',
            public_analysis: 'NO_PUBLIC_ANALYSIS',
            publication_state: 'NO_PUBLIC_ANALYSIS',
            final_check: 'FINAL_CHECK_UNAVAILABLE',
            freshness: {
              state: 'FRESH',
              source_last_seen_at: null,
              fixture_refresh_at: '2026-09-14T07:00:00Z',
              evidence_source: 'fixture_refresh_event',
            },
          },
        ],
      }),
    });
    const view = await render(<TodayScreen />);
    await waitFor(() => expect(view.getByText('Canonical Home')).toBeTruthy());
    expect(view.getByText('No analysis published')).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/fixtures\/today$/),
      expect.any(Object),
    );
  });

  it('does not activate Today or Explore mocks after API failure', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('network failed'));
    const today = await render(<TodayScreen />);
    await waitFor(() =>
      expect(
        today.getByText('Match data is temporarily unavailable'),
      ).toBeTruthy(),
    );
    expect(today.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
    await today.unmount();

    const explore = await render(<ExploreScreen />);
    await waitFor(() =>
      expect(explore.getByText('Unable to load value signals')).toBeTruthy(),
    );
    expect(explore.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
  });

  it('uses only the public prediction endpoint as AI context', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ predictions: [], count: 0 }),
    });
    const view = await render(<AiScreen />);
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/predictions$/),
        expect.objectContaining({ method: 'GET' }),
      ),
    );
    expect(view.getByText('Premium AI foundation')).toBeTruthy();
  });

  it('never activates mocks or generates selections when AI context fails', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('network failed'));
    const view = await render(<AiScreen />);
    await waitFor(() =>
      expect(view.getByText('Public analysis unavailable')).toBeTruthy(),
    );
    expect(view.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
    expect(view.queryByText(/generated pick|winning pick/i)).toBeNull();
  });
});
