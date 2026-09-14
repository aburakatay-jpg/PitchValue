import { useEffect, useState } from 'react';
import { useRouter } from 'expo-router';

import {
  AgeConfirmation,
  ExitConfirmation,
  OnboardingFlow,
} from '@/components/OnboardingFlow';
import { LoadingState, Screen } from '@/components/ui';
import {
  loadFirstLaunchState,
  markAgeConfirmed,
  markOnboardingComplete,
  type FirstLaunchState,
} from '@/lib/onboarding-storage';

export type LandingStage =
  'LOADING' | 'AGE_CONFIRMATION' | 'EXITED' | 'ONBOARDING';

export function landingStageFromState(state: FirstLaunchState): LandingStage {
  if (!state.ageConfirmed) return 'AGE_CONFIRMATION';
  return state.tutorialComplete ? 'LOADING' : 'ONBOARDING';
}

export function RootLanding({
  stage,
  onAgeAccepted,
  onComplete,
  storageError = false,
}: {
  stage: LandingStage;
  onAgeAccepted: () => void;
  onComplete: () => void;
  storageError?: boolean;
}) {
  const [exited, setExited] = useState(stage === 'EXITED');
  if (stage === 'LOADING')
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  if (exited) return <ExitConfirmation onReview={() => setExited(false)} />;
  if (stage === 'AGE_CONFIRMATION')
    return (
      <AgeConfirmation
        onAccept={onAgeAccepted}
        onExit={() => setExited(true)}
        storageError={storageError}
      />
    );
  return <OnboardingFlow onComplete={onComplete} storageError={storageError} />;
}

export default function IndexScreen() {
  const router = useRouter();
  const [stage, setStage] = useState<LandingStage>('LOADING');
  const [storageError, setStorageError] = useState(false);

  useEffect(() => {
    loadFirstLaunchState()
      .then((state) => {
        if (state.tutorialComplete) {
          router.replace('/(tabs)/today');
          return;
        }
        setStage(landingStageFromState(state));
      })
      .catch(() => {
        setStorageError(true);
        setStage('AGE_CONFIRMATION');
      });
  }, [router]);

  const acceptAge = async () => {
    try {
      await markAgeConfirmed();
      setStorageError(false);
      setStage('ONBOARDING');
    } catch {
      setStorageError(true);
    }
  };
  const complete = async () => {
    try {
      await markOnboardingComplete();
      setStorageError(false);
      router.replace('/(tabs)/today');
    } catch {
      setStorageError(true);
    }
  };
  return (
    <RootLanding
      onAgeAccepted={() => void acceptAge()}
      onComplete={() => void complete()}
      stage={stage}
      storageError={storageError}
    />
  );
}
