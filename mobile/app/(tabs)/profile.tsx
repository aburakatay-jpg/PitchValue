import Constants from 'expo-constants';
import { useRouter, type Href } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import {
  AppHeader,
  Button,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { colors, spacing, typography } from '@/theme/tokens';
import type { EntitlementState } from '@/types/entitlement';

export const profileGroups = [
  'Account',
  'Subscription',
  'Preferences',
  'Track Record',
  'Responsible Gaming',
  'App',
] as const;

const entitlementLabels: Readonly<Record<EntitlementState, string>> = {
  GUEST: 'Guest',
  PREMIUM_ACTIVE: 'Premium Active',
  PREMIUM_TRIAL: 'Premium Trial',
  PREMIUM_EXPIRED: 'Premium Inactive',
};

function ProfileGroup({
  title,
  children,
}: {
  title: (typeof profileGroups)[number];
  children: React.ReactNode;
}) {
  return (
    <View style={styles.group}>
      <SectionHeader title={title} />
      <View style={sharedStyles.card}>{children}</View>
    </View>
  );
}

function InformationRow({ label, value }: { label: string; value: string }) {
  return (
    <View
      accessibilityLabel={`${label}: ${value}`}
      style={sharedStyles.rowBetween}
    >
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

export function ProfileView({
  entitlement,
  onSignIn,
  onOpenTrackRecord,
  onViewPremium,
}: {
  entitlement: EntitlementState;
  onSignIn: () => void;
  onOpenTrackRecord: () => void;
  onViewPremium: () => void;
}) {
  const guest = entitlement === 'GUEST';
  return (
    <Screen>
      <AppHeader eyebrow={entitlementLabels[entitlement]} title="Profile" />
      <ProfileGroup title="Account">
        <InformationRow
          label="Account status"
          value={entitlementLabels[entitlement]}
        />
        {guest ? (
          <>
            <Text style={styles.detail}>
              Guest access includes public Today, Explore, and Match Detail
              discovery.
            </Text>
            <Button onPress={onSignIn} variant="secondary">
              Sign in
            </Button>
          </>
        ) : null}
      </ProfileGroup>
      <ProfileGroup title="Subscription">
        <InformationRow label="Access" value={entitlementLabels[entitlement]} />
        <Button onPress={onViewPremium} variant="secondary">
          View Premium
        </Button>
        <Text style={styles.detail}>
          Management and restoration remain unavailable until store integration
          exists.
        </Text>
      </ProfileGroup>
      <ProfileGroup title="Preferences">
        <Text style={styles.detail}>
          No configurable preferences are currently available.
        </Text>
      </ProfileGroup>
      <ProfileGroup title="Track Record">
        <Text style={styles.detail}>
          No verified performance record is available. PitchValue never
          fabricates ROI.
        </Text>
        <Button onPress={onOpenTrackRecord} variant="secondary">
          Open My Bets
        </Button>
      </ProfileGroup>
      <ProfileGroup title="Responsible Gaming">
        <Text style={styles.detail}>
          18+ · Betting can involve financial loss.
        </Text>
        <Text style={styles.detail}>
          Full Responsible Gambling content and destinations require Legal
          approval.
        </Text>
      </ProfileGroup>
      <ProfileGroup title="App">
        <InformationRow
          label="Version"
          value={Constants.expoConfig?.version ?? 'Unavailable'}
        />
        <Text style={styles.detail}>
          Terms, Privacy, Responsible Gambling, and Support routes require
          approved content or service destinations.
        </Text>
      </ProfileGroup>
    </Screen>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const { state } = useEntitlement();
  return (
    <ProfileView
      entitlement={state}
      onOpenTrackRecord={() => router.push('/(tabs)/bets')}
      onSignIn={() => router.push('/auth/index' as Href)}
      onViewPremium={() => router.push('/paywall')}
    />
  );
}

const styles = StyleSheet.create({
  group: { gap: spacing.sm },
  label: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  value: {
    color: colors.secondary,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.body,
  },
  detail: { color: colors.textSecondary, ...typography.body },
});
