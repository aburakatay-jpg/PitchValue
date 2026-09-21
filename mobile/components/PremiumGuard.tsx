import type { PropsWithChildren } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { useEntitlement } from '@/features/entitlement/EntitlementContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { hasPremiumAccess } from '@/lib/entitlement';
import {
  colors,
  radii,
  spacing,
  typography,
  createThemedStyleSheet,
} from '@/theme/tokens';
import type { EntitlementState } from '@/types/entitlement';

export function LockedPremiumSection({
  onUnlock,
  title = 'Unlock more analysis',
  detail = 'See the Premium options available for this part of PitchValue.',
  cta = 'View Premium',
}: {
  onUnlock: () => void;
  title?: string;
  detail?: string;
  cta?: string;
}) {
  const { t } = useLanguage();
  return (
    <View
      accessibilityLabel={t('Premium content locked')}
      style={styles.locked}
    >
      <Text style={styles.title}>{t(title)}</Text>
      <Text style={styles.detail}>{t(detail)}</Text>
      <Button
        accessibilityLabel={t(cta)}
        onPress={onUnlock}
        variant="secondary"
      >
        {t(cta)}
      </Button>
    </View>
  );
}

export function PremiumGuard({
  children,
  state,
  onLocked,
  title,
  detail,
}: PropsWithChildren<{
  state?: EntitlementState;
  onLocked?: () => void;
  title?: string;
  detail?: string;
}>) {
  const entitlement = useEntitlement();
  const effectiveState = state ?? entitlement.state;
  if (!hasPremiumAccess(effectiveState)) {
    return (
      <LockedPremiumSection
        {...(detail === undefined ? {} : { detail })}
        onUnlock={onLocked ?? entitlement.openPaywall}
        {...(title === undefined ? {} : { title })}
      />
    );
  }
  return <>{children}</>;
}

const styles = createThemedStyleSheet({
  locked: {
    backgroundColor: colors.surface,
    borderColor: colors.accent,
    borderRadius: radii.md,
    borderWidth: 1,
    gap: spacing.sm,
    padding: spacing.lg,
  },
  title: { color: colors.text, ...typography.sectionTitle },
  detail: { color: colors.textSecondary, ...typography.body },
});
