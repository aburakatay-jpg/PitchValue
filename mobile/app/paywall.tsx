import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { PaywallShell } from '@/components/Paywall';
import {
  AppHeader,
  Chip,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import type { TrialEligibility } from '@/types/entitlement';

export default function PaywallScreen() {
  const [eligibility, setEligibility] = useState<TrialEligibility>('unknown');
  return (
    <Screen>
      <AppHeader eyebrow="Preview only" title="PitchValue Premium" />
      <SectionHeader
        title="One product, three durations"
        detail="All paid plans unlock the same future product features."
      />
      {__DEV__ ? (
        <View style={sharedStyles.row}>
          {(['unknown', 'eligible', 'ineligible'] as const).map((value) => (
            <Pressable
              accessibilityRole="button"
              key={value}
              onPress={() => setEligibility(value)}
            >
              <Chip label={value} selected={eligibility === value} />
            </Pressable>
          ))}
        </View>
      ) : null}
      <PaywallShell trialEligibility={eligibility} />
    </Screen>
  );
}
