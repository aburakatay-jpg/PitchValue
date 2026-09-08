import AsyncStorage from '@react-native-async-storage/async-storage';

const ONBOARDING_KEY = 'pitchvalue.onboarding.complete.v1';

export async function isOnboardingComplete(): Promise<boolean> {
  return (await AsyncStorage.getItem(ONBOARDING_KEY)) === 'true';
}

export async function markOnboardingComplete(): Promise<void> {
  await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
}
