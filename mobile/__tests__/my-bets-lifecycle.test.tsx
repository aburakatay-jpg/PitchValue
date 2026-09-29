import AsyncStorage from '@react-native-async-storage/async-storage';
import { render, fireEvent, waitFor } from '@testing-library/react-native';

import { MyBetsView } from '@/components/MyBets';
import { getSavedSelections } from '@/lib/product-api';
import type { SavedSelection } from '@/types/product-services';

jest.mock('@/lib/product-api', () => ({
  getSavedSelections: jest.fn(),
  getTrackingPerformance: jest.fn(),
}));

const list = getSavedSelections as jest.Mock;
const record = (
  tracking_status: SavedSelection['tracking_status'],
  id: number,
): SavedSelection => ({
  saved_selection_id: `saved-${id}`,
  prediction_snapshot_id: id,
  saved_bet_score: '80',
  saved_policy_decision: 'PICK',
  match_id: id,
  market: 'match_result',
  selection: 'home',
  line: null,
  saved_decimal_odds: null,
  stake: null,
  currency: null,
  tracking_status,
  outcome: null,
  created_at: '2026-09-29T00:00:00Z',
});

describe('My Bets lifecycle and pinned evidence', () => {
  beforeEach(async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'en');
    list.mockReset();
    list.mockImplementation((_token, section) => {
      const records =
        section === 'active'
          ? [record('ACTIVE', 101)]
          : [
              record('SETTLED', 102),
              record('REMOVED', 103),
              record('REVIEW_REQUIRED', 104),
            ];
      return Promise.resolve({ records, count: records.length });
    });
  });

  it('keeps ACTIVE distinct and renders historical pinned score', async () => {
    const view = await render(<MyBetsView accessToken="session" />);
    await waitFor(() =>
      expect(
        view.getByText('Saved analysis · At save: PICK · Bet Score: 80'),
      ).toBeTruthy(),
    );
    expect(view.getAllByText('Active')).toHaveLength(2);
    expect(
      view.getByText('Saved analysis · At save: PICK · Bet Score: 80'),
    ).toBeTruthy();
    expect(JSON.stringify(view.toJSON())).not.toContain('#101');
  });

  it('renders SETTLED, REMOVED and REVIEW_REQUIRED separately in history', async () => {
    const view = await render(<MyBetsView accessToken="session" />);
    await fireEvent.press(view.getByRole('tab', { name: 'History' }));
    await waitFor(() => expect(view.getByText('Settled')).toBeTruthy());
    expect(view.getByText('Removed')).toBeTruthy();
    expect(view.getByText('Review required')).toBeTruthy();
  });

  it('localizes every history state in Turkish without collapsing them', async () => {
    await AsyncStorage.setItem('pitchvalue_language', 'tr');
    const view = await render(
      <MyBetsView accessToken="session" initialTab="History" />,
    );
    await waitFor(() => expect(view.getByText('Sonuçlandı')).toBeTruthy());
    expect(view.getByText('Kaldırıldı')).toBeTruthy();
    expect(view.getByText('İnceleme gerekli')).toBeTruthy();
  });
});
