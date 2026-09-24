import { Stack, useRouter } from 'expo-router';

import { PaywallHeaderClose, PaywallPresentation } from '@/components/Paywall';
import { Screen, stackScreenEdges } from '@/components/ui';

export default function PaywallScreen() {
  const router = useRouter();
  return (
    <>
      <Stack.Screen
        options={{
          headerRight: () => (
            <PaywallHeaderClose onClose={() => router.back()} />
          ),
          unstable_headerRightItems: () => [
            {
              type: 'custom',
              element: <PaywallHeaderClose onClose={() => router.back()} />,
              hidesSharedBackground: true,
            },
          ],
        }}
      />
      <Screen safeAreaEdges={stackScreenEdges}>
        <PaywallPresentation />
      </Screen>
    </>
  );
}
