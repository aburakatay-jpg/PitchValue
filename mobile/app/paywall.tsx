import { useRouter } from 'expo-router';

import { PaywallPresentation } from '@/components/Paywall';
import { Screen, stackScreenEdges } from '@/components/ui';

export default function PaywallScreen() {
  const router = useRouter();
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <PaywallPresentation onClose={() => router.back()} />
    </Screen>
  );
}
