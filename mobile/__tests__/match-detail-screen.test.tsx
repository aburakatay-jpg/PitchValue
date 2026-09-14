import { render, waitFor } from '@testing-library/react-native';

let mockRouteId: string | string[] | undefined = '321';

jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ id: mockRouteId }),
}));

import MatchDetailScreen from '@/app/match/[id]';
import { mockMatches } from '@/dev/mock-data';

import { makeMatchDetail } from '../test-support/match-detail-fixtures';

const originalFetch = globalThis.fetch;

afterEach(() => {
  mockRouteId = '321';
  globalThis.fetch = originalFetch;
  jest.restoreAllMocks();
});

describe('production Match Detail screen', () => {
  it('uses the canonical route ID and real public endpoint', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => makeMatchDetail(),
    });
    const view = await render(<MatchDetailScreen />);
    await waitFor(() =>
      expect(view.getByText('Very Long Canonical Home United')).toBeTruthy(),
    );
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/matches\/321$/),
      expect.any(Object),
    );
  });

  it('does not request or substitute a mock for an invalid route ID', async () => {
    mockRouteId = 'invalid';
    globalThis.fetch = jest.fn();
    const view = await render(<MatchDetailScreen />);
    expect(view.getByText('Match not found')).toBeTruthy();
    expect(view.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('does not activate a mock after an API failure', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('network failed'));
    const view = await render(<MatchDetailScreen />);
    await waitFor(() =>
      expect(
        view.getByText('Match data is temporarily unavailable'),
      ).toBeTruthy(),
    );
    expect(view.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
  });

  it('does not activate a mock after a 404', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 404 });
    const view = await render(<MatchDetailScreen />);
    await waitFor(() => expect(view.getByText('Match not found')).toBeTruthy());
    expect(view.queryByText(mockMatches[0]!.homeTeam)).toBeNull();
  });
});
