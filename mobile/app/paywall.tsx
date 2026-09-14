import { useRouter } from 'expo-router';

import { PaywallPresentation } from '@/components/Paywall';
import { Screen } from '@/components/ui';

export default function PaywallScreen() {
  const router = useRouter();
  return (
    <Screen>
      <PaywallPresentation onClose={() => router.back()} />
    </Screen>
  );
}
