import { useEffect, useState } from 'react';
import { useRouter } from 'expo-router';

import { OnboardingFlow } from '@/components/OnboardingFlow';
import { LoadingState, Screen } from '@/components/ui';
import {
  isOnboardingComplete,
  markOnboardingComplete,
} from '@/lib/onboarding-storage';

export function RootLanding({
  loading,
  onComplete,
}: {
  loading: boolean;
  onComplete: () => void;
}) {
  if (loading)
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  return <OnboardingFlow onComplete={onComplete} />;
}

export default function IndexScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    isOnboardingComplete()
      .then((complete) => complete && router.replace('/(tabs)/today'))
      .finally(() => setLoading(false));
  }, [router]);

  const complete = async () => {
    await markOnboardingComplete();
    router.replace('/(tabs)/today');
  };

  return <RootLanding loading={loading} onComplete={complete} />;
}
