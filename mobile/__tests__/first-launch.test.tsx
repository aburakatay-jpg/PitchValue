import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockReplace = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

import IndexScreen, { RootLanding, landingStageFromState } from '@/app/index';
import { onboardingPages } from '@/components/OnboardingFlow';
import {
  firstLaunchStorageKeys,
  loadFirstLaunchState,
} from '@/lib/onboarding-storage';

beforeEach(async () => {
  mockReplace.mockClear();
  await AsyncStorage.clear();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('first-launch state and persistence', () => {
  it('fails closed to 18+ when storage is empty or malformed', async () => {
    expect(await loadFirstLaunchState()).toEqual({
      ageConfirmed: false,
      tutorialComplete: false,
    });
    await AsyncStorage.multiSet([
      [firstLaunchStorageKeys.ageConfirmed, 'yes-ish'],
      [firstLaunchStorageKeys.tutorialComplete, 'true'],
      [firstLaunchStorageKeys.legacyComplete, 'corrupt'],
    ]);
    expect(await loadFirstLaunchState()).toEqual({
      ageConfirmed: false,
      tutorialComplete: false,
    });
  });

  it('safely honors the exact legacy completion written by the prior flow', async () => {
    await AsyncStorage.setItem(firstLaunchStorageKeys.legacyComplete, 'true');
    expect(await loadFirstLaunchState()).toEqual({
      ageConfirmed: true,
      tutorialComplete: true,
    });
  });

  it('derives age confirmation before onboarding', () => {
    expect(
      landingStageFromState({ ageConfirmed: false, tutorialComplete: false }),
    ).toBe('AGE_CONFIRMATION');
    expect(
      landingStageFromState({ ageConfirmed: true, tutorialComplete: false }),
    ).toBe('ONBOARDING');
  });

  it('does not render age or tutorial content while storage is unresolved', async () => {
    const view = await render(
      <RootLanding
        onAgeAccepted={jest.fn()}
        onComplete={jest.fn()}
        stage="LOADING"
      />,
    );
    expect(view.getByLabelText('Loading PitchValue')).toBeTruthy();
    expect(view.queryByText('For adults 18+')).toBeNull();
  });

  it('keeps Exit visible and does not enter the product', async () => {
    const onAgeAccepted = jest.fn();
    const view = await render(
      <RootLanding
        onAgeAccepted={onAgeAccepted}
        onComplete={jest.fn()}
        stage="AGE_CONFIRMATION"
      />,
    );
    expect(view.getByText('For adults 18+')).toBeTruthy();
    await fireEvent.press(view.getByLabelText('Exit PitchValue'));
    expect(view.getByText('PitchValue remains locked')).toBeTruthy();
    expect(onAgeAccepted).not.toHaveBeenCalled();
  });

  it('persists age and tutorial before routing a first-time guest to Today', async () => {
    const view = await render(<IndexScreen />);
    await waitFor(() => expect(view.getByText('For adults 18+')).toBeTruthy());
    await fireEvent.press(view.getByLabelText('Confirm I am 18 or older'));
    await waitFor(() =>
      expect(view.getByText(onboardingPages[0].title)).toBeTruthy(),
    );
    await fireEvent.press(
      view.getByLabelText('Skip onboarding and open Today'),
    );
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith('/(tabs)/today'),
    );
    expect(await loadFirstLaunchState()).toEqual({
      ageConfirmed: true,
      tutorialComplete: true,
    });
  });

  it('does not bypass the age gate when confirmation cannot be persisted', async () => {
    const view = await render(<IndexScreen />);
    await waitFor(() => expect(view.getByText('For adults 18+')).toBeTruthy());
    jest
      .spyOn(AsyncStorage, 'setItem')
      .mockRejectedValueOnce(new Error('storage'));
    await fireEvent.press(view.getByLabelText('Confirm I am 18 or older'));
    await waitFor(() =>
      expect(
        view.getByText(
          'First-launch progress could not be saved. Please try again.',
        ),
      ).toBeTruthy(),
    );
    expect(view.getByText('For adults 18+')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('routes a returning completed user directly to Today', async () => {
    await AsyncStorage.multiSet([
      [firstLaunchStorageKeys.ageConfirmed, 'confirmed'],
      [firstLaunchStorageKeys.tutorialComplete, 'complete'],
    ]);
    const view = await render(<IndexScreen />);
    expect(view.getByLabelText('Loading PitchValue')).toBeTruthy();
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith('/(tabs)/today'),
    );
    expect(view.queryByText('For adults 18+')).toBeNull();
  });
});

describe('three-page onboarding', () => {
  it('contains exactly the three canonical concepts with Back, Next, and final CTA', async () => {
    expect(onboardingPages).toHaveLength(3);
    const onComplete = jest.fn();
    const view = await render(
      <RootLanding
        onAgeAccepted={jest.fn()}
        onComplete={onComplete}
        stage="ONBOARDING"
      />,
    );
    expect(view.getByText(onboardingPages[0].title)).toBeTruthy();
    await fireEvent.press(view.getByText('Next'));
    expect(view.getByText(onboardingPages[1].title)).toBeTruthy();
    await fireEvent.press(view.getByText('Back'));
    expect(view.getByText(onboardingPages[0].title)).toBeTruthy();
    await fireEvent.press(view.getByText('Next'));
    await fireEvent.press(view.getByText('Next'));
    expect(view.getByText(onboardingPages[2].title)).toBeTruthy();
    await fireEvent.press(view.getByText('Explore PitchValue'));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });
});
