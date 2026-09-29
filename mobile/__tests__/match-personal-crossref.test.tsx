import AsyncStorage from '@react-native-async-storage/async-storage';
import { render, waitFor } from '@testing-library/react-native';

import { MatchDetailView, ProductionMatchDetail } from '@/app/match/[id]';
import { getSavedSelections } from '@/lib/product-api';
import type { SavedSelection } from '@/types/product-services';

import { makeMatchDetail } from '../test-support/match-detail-fixtures';

let mockSessionState = 'AUTHENTICATED';
jest.mock('@/features/session/ProductSessionContext', () => ({
  useProductSession: () => ({
    state: mockSessionState,
    accessToken: 'session-token',
  }),
}));
jest.mock('@/features/session/useFollow', () => ({
  useFollow: () => ({
    isFollowed: false,
    isLoading: false,
    error: null,
    toggleFollow: jest.fn(),
    isAuthenticated: false,
  }),
}));
jest.mock('@/lib/product-api', () => ({
  getSavedSelections: jest.fn(),
  saveSelection: jest.fn(),
}));
jest.mock('@/hooks/use-public-resource', () => ({
  usePublicResource: () => ({
    data: jest
      .requireActual('../test-support/match-detail-fixtures')
      .makeMatchDetail(),
    error: null,
    initialLoading: false,
    refreshing: false,
    refresh: jest.fn(),
  }),
}));

const saved = (status: SavedSelection['tracking_status']): SavedSelection => ({
  saved_selection_id: 'saved-1',
  prediction_snapshot_id: 1001,
  saved_bet_score: '80',
  saved_policy_decision: 'PICK',
  match_id: 321,
  market: 'match_result',
  selection: 'home',
  line: null,
  saved_decimal_odds: null,
  stake: null,
  currency: null,
  tracking_status: status,
  outcome: null,
  created_at: '2026-09-29T00:00:00Z',
});

const viewProps = {
  data: makeMatchDetail(),
  error: null,
  initialLoading: false,
  onRefresh: jest.fn(),
  refreshing: false,
};

describe('Match Detail personal cross-reference', () => {
  beforeEach(async () => {
    mockSessionState = 'AUTHENTICATED';
    (getSavedSelections as jest.Mock).mockReset();
    await AsyncStorage.setItem('pitchvalue_language', 'en');
  });
  it('shows no saved selection without removing canonical fixture', async () => {
    const view = await render(
      <MatchDetailView {...viewProps} personalSelections={[]} />,
    );
    expect(view.getByText('No saved selection')).toBeTruthy();
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
  });

  it.each([
    ['ACTIVE', 'Active'],
    ['SETTLED', 'Settled'],
    ['REMOVED', 'Removed'],
    ['REVIEW_REQUIRED', 'Review required'],
  ] as const)(
    'shows %s without changing public detail',
    async (status, label) => {
      const view = await render(
        <MatchDetailView {...viewProps} personalSelections={[saved(status)]} />,
      );
      expect(view.getByText(/Very Long Canonical Home United/)).toBeTruthy();
      expect(view.getByText(new RegExp(`^${label} ·`))).toBeTruthy();
    },
  );

  it('keeps canonical fixture visible when personal API fails', async () => {
    (getSavedSelections as jest.Mock).mockRejectedValue(
      new Error('private service unavailable'),
    );
    const view = await render(<ProductionMatchDetail matchId={321} />);
    await waitFor(() =>
      expect(
        view.getByText('Your saved selection is temporarily unavailable'),
      ).toBeTruthy(),
    );
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
    expect(view.queryByText('private service unavailable')).toBeNull();
  });

  it('joins only matching personal records from active and history reads', async () => {
    (getSavedSelections as jest.Mock).mockImplementation((_token, section) => {
      const records =
        section === 'active'
          ? [
              saved('ACTIVE'),
              {
                ...saved('ACTIVE'),
                saved_selection_id: 'other',
                match_id: 999,
              },
            ]
          : [{ ...saved('REMOVED'), saved_selection_id: 'removed' }];
      return Promise.resolve({ records, count: records.length });
    });
    const view = await render(<ProductionMatchDetail matchId={321} />);
    await waitFor(() => expect(view.getByText(/^Active ·/)).toBeTruthy());
    expect(view.getByText(/^Removed ·/)).toBeTruthy();
    expect(view.queryByText('No saved selection')).toBeNull();
    expect(getSavedSelections).toHaveBeenCalledWith(
      'session-token',
      'active',
      expect.anything(),
    );
    expect(getSavedSelections).toHaveBeenCalledWith(
      'session-token',
      'history',
      expect.anything(),
    );
  });

  it('localizes the personal relation in Turkish', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <MatchDetailView
        {...viewProps}
        personalSelections={[saved('REVIEW_REQUIRED')]}
      />,
    );
    expect(view.getByText('Kaydedilen seçim')).toBeTruthy();
    expect(view.getByText(/^İnceleme gerekli ·/)).toBeTruthy();
  });

  it('does not request authenticated personal records for a guest', async () => {
    mockSessionState = 'GUEST';
    const view = await render(<ProductionMatchDetail matchId={321} />);
    expect(view.getByText('Very Long Canonical Home United')).toBeTruthy();
    expect(getSavedSelections).not.toHaveBeenCalled();
    expect(view.queryByText('No saved selection')).toBeNull();
  });
});
