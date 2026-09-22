import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import {
  MyBetsSkeleton,
  MyBetsView,
  myBetsTabs,
  productionMyBetsStates,
} from '@/components/MyBets';
import {
  personalTrackingContract,
  productTrackingContractReady,
  productionTrackingAvailable,
} from '@/lib/personal-tracking';
import { lightColors, setActiveAppearance } from '@/theme/tokens';

describe('personal tracking contract safety', () => {
  it('records that no production saved-user contract exists', () => {
    expect(productionTrackingAvailable).toBe(false);
    expect(productTrackingContractReady).toBe(true);
    expect(personalTrackingContract.saveMatch).toBe('MISSING');
    expect(personalTrackingContract.savePrediction).toBe('SUPPORTED');
    expect(personalTrackingContract.userOwnership).toBe('SUPPORTED');
    expect(personalTrackingContract.guestPersistence).toBe(
      'PARTIALLY_SUPPORTED',
    );
    expect(personalTrackingContract.settlement).toBe('SUPPORTED');
    expect(personalTrackingContract.stake).toBe('SUPPORTED');
    expect(personalTrackingContract.oddsAtSave).toBe('SUPPORTED');
    expect(personalTrackingContract.roiInputs).toBe('SUPPORTED');
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
  afterEach(() => setActiveAppearance('dark'));

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

  it('uses the semantic yellow selected segment in Light Mode', async () => {
    setActiveAppearance('light');
    const view = await render(<MyBetsView />);
    const active = view.getByTestId('my-bets-tab-active');
    const style = active.props.style;
    expect(StyleSheet.flatten(style)).toMatchObject({
      backgroundColor: lightColors.segmentedSelectedBackground,
      borderColor: lightColors.segmentedSelectedBackground,
    });
    expect(active.props.accessibilityState).toEqual({ selected: true });
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
