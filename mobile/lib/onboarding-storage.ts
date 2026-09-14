import AsyncStorage from '@react-native-async-storage/async-storage';

const AGE_CONFIRMED_KEY = 'pitchvalue.first-launch.age-confirmed.v1';
const TUTORIAL_COMPLETE_KEY = 'pitchvalue.first-launch.tutorial-complete.v1';
const LEGACY_ONBOARDING_KEY = 'pitchvalue.onboarding.complete.v1';
const CONFIRMED_VALUE = 'confirmed';
const COMPLETE_VALUE = 'complete';

export type FirstLaunchState = Readonly<{
  ageConfirmed: boolean;
  tutorialComplete: boolean;
}>;

export async function loadFirstLaunchState(): Promise<FirstLaunchState> {
  const [ageValue, tutorialValue, legacyValue] = await Promise.all([
    AsyncStorage.getItem(AGE_CONFIRMED_KEY),
    AsyncStorage.getItem(TUTORIAL_COMPLETE_KEY),
    AsyncStorage.getItem(LEGACY_ONBOARDING_KEY),
  ]);
  const legacyComplete = legacyValue === 'true';
  const ageConfirmed = ageValue === CONFIRMED_VALUE || legacyComplete;
  return {
    ageConfirmed,
    tutorialComplete:
      ageConfirmed && (tutorialValue === COMPLETE_VALUE || legacyComplete),
  };
}

export async function markAgeConfirmed(): Promise<void> {
  await AsyncStorage.setItem(AGE_CONFIRMED_KEY, CONFIRMED_VALUE);
}

export async function markOnboardingComplete(): Promise<void> {
  await AsyncStorage.setItem(TUTORIAL_COMPLETE_KEY, COMPLETE_VALUE);
}

export async function isOnboardingComplete(): Promise<boolean> {
  return (await loadFirstLaunchState()).tutorialComplete;
}

export async function resetFirstLaunchForDevelopment(): Promise<void> {
  if (!__DEV__) return;
  await AsyncStorage.multiRemove([
    AGE_CONFIRMED_KEY,
    TUTORIAL_COMPLETE_KEY,
    LEGACY_ONBOARDING_KEY,
  ]);
}

export const firstLaunchStorageKeys = {
  ageConfirmed: AGE_CONFIRMED_KEY,
  tutorialComplete: TUTORIAL_COMPLETE_KEY,
  legacyComplete: LEGACY_ONBOARDING_KEY,
} as const;
