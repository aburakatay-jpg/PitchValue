import { fireEvent, render } from '@testing-library/react-native';

import {
  MyBetsSkeleton,
  MyBetsView,
  myBetsTabs,
  productionMyBetsStates,
} from '@/components/MyBets';
import {
  personalTrackingContract,
  productionTrackingAvailable,
} from '@/lib/personal-tracking';

describe('personal tracking contract safety', () => {
  it('records that no production saved-user contract exists', () => {
    expect(productionTrackingAvailable).toBe(false);
    expect(personalTrackingContract.saveMatch).toBe('MISSING');
    expect(personalTrackingContract.savePrediction).toBe('MISSING');
    expect(personalTrackingContract.userOwnership).toBe('BLOCKED_BY_AUTH');
    expect(personalTrackingContract.guestPersistence).toBe(
      'BLOCKED_BY_PRODUCT_DECISION',
    );
    expect(personalTrackingContract.settlement).toBe('MISSING');
    expect(personalTrackingContract.stake).toBe('MISSING');
    expect(personalTrackingContract.oddsAtSave).toBe('MISSING');
    expect(personalTrackingContract.roiInputs).toBe('MISSING');
  });

  it('keeps every production section explicitly unavailable', () => {
    expect(productionMyBetsStates).toEqual({
      Active: 'UNAVAILABLE',
      History: 'UNAVAILABLE',
      Performance: 'UNAVAILABLE',
    });
  });
});

describe('My Bets top-level presentation', () => {
  it('uses the three canonical accessible tabs with Active selected', async () => {
    const view = await render(<MyBetsView />);
    expect(myBetsTabs).toEqual(['Active', 'History', 'Performance']);
    expect(
      view.getByRole('tab', { name: 'Active' }).props.accessibilityState,
    ).toEqual({ selected: true });
    expect(view.getByText('Tracked selections unavailable')).toBeTruthy();
  });

  it('switches independently to honest History and Performance states', async () => {
    const view = await render(<MyBetsView />);
    await fireEvent.press(view.getByRole('tab', { name: 'History' }));
    expect(view.getByText('History unavailable')).toBeTruthy();
    await fireEvent.press(view.getByRole('tab', { name: 'Performance' }));
    expect(view.getByText('Performance unavailable')).toBeTruthy();
    expect(view.getByText(/ROI is not calculated/)).toBeTruthy();
    expect(view.queryByText(/0% ROI|0\.00%/i)).toBeNull();
  });

  it('supports honest empty states only when a future authority supplies them', async () => {
    const view = await render(
      <MyBetsView
        sectionStates={{
          Active: 'EMPTY',
          History: 'EMPTY',
          Performance: 'EMPTY',
        }}
      />,
    );
    expect(view.getByText('No tracked selections yet')).toBeTruthy();
    await fireEvent.press(view.getByRole('tab', { name: 'History' }));
    expect(view.getByText('No settled records yet')).toBeTruthy();
    await fireEvent.press(view.getByRole('tab', { name: 'Performance' }));
    expect(view.getByText('No performance record yet')).toBeTruthy();
  });

  it('keeps section errors specific and does not expose implementation detail', async () => {
    const view = await render(
      <MyBetsView
        sectionStates={{
          Active: 'ERROR',
          History: 'ERROR',
          Performance: 'ERROR',
        }}
      />,
    );
    expect(view.getByText('Unable to load tracked selections')).toBeTruthy();
    expect(JSON.stringify(view.toJSON())).not.toMatch(
      /SQL|stack trace|provider exception/i,
    );
  });

  it('hides structural loading content from accessibility', async () => {
    const view = await render(<MyBetsSkeleton tab="Active" />);
    expect(
      view.getByTestId('my-bets-active-skeleton', {
        includeHiddenElements: true,
      }),
    ).toHaveProp('importantForAccessibility', 'no-hide-descendants');
  });

  it('introduces no sportsbook or compulsive-product actions', async () => {
    const view = await render(<MyBetsView />);
    expect(JSON.stringify(view.toJSON())).not.toMatch(
      /Bet Now|Place Bet|Deposit|Cash Out|Bonus|recover your losses|on fire/i,
    );
  });
});
