import type { PropsWithChildren } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { hasPremiumAccess } from '@/lib/entitlement';
import { colors, radii, spacing, typeScale } from '@/theme/tokens';
import type { EntitlementState } from '@/types/entitlement';

export function LockedPremiumSection({ onUnlock }: { onUnlock: () => void }) {
  return (
    <View accessibilityLabel="Premium content locked" style={styles.locked}>
      <Text style={styles.title}>Premium insight</Text>
      <Text style={styles.detail}>
        Upgrade access is presented here without starting a purchase.
      </Text>
      <Button onPress={onUnlock}>View premium options</Button>
    </View>
  );
}

export function PremiumGuard({
  children,
  state,
  onLocked,
}: PropsWithChildren<{ state?: EntitlementState; onLocked?: () => void }>) {
  const entitlement = useEntitlement();
  const effectiveState = state ?? entitlement.state;
  if (!hasPremiumAccess(effectiveState)) {
    return (
      <LockedPremiumSection onUnlock={onLocked ?? entitlement.openPaywall} />
    );
  }
  return <>{children}</>;
}

const styles = StyleSheet.create({
  locked: {
    backgroundColor: colors.surface,
    borderColor: colors.accent,
    borderRadius: radii.md,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  title: { color: colors.text, fontSize: typeScale.title, fontWeight: '700' },
  detail: {
    color: colors.textSecondary,
    fontSize: typeScale.body,
    lineHeight: 23,
  },
});
