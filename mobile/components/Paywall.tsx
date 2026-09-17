import { StyleSheet, Text, View } from 'react-native';

import { Badge, Button, SectionHeader, sharedStyles } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { colors, spacing, typography } from '@/theme/tokens';
import type { TrialEligibility } from '@/types/entitlement';

export const premiumBenefits = [
  'Full market analysis',
  'Bet Score details',
  'Model agreement when authoritative data is available',
  'Final Check',
  'AI explanations',
  'Coupon Builder',
] as const;

export const plans = [
  { id: 'monthly', name: 'Monthly' },
  { id: 'quarterly', name: '3 Months' },
  { id: 'annual', name: 'Annual' },
] as const;

export function annualPlanDetail(
  eligibility: TrialEligibility,
  t: (k: string) => string,
): string {
  if (eligibility === 'eligible') {
    return t('A trial may be offered after App Store eligibility is verified.');
  }
  return t('Trial eligibility and localized pricing require the App Store.');
}

function PaywallPlanCard({
  name,
  annual,
  trialEligibility,
}: {
  name: string;
  annual: boolean;
  trialEligibility: TrialEligibility;
}) {
  const { t } = useLanguage();
  return (
    <View style={[sharedStyles.card, annual && styles.highlighted]}>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.name}>{t(name)}</Text>
        {annual ? <Badge label={t('Annual option')} tone="accent" /> : null}
      </View>
      <Text style={styles.price}>{t('Localized price unavailable')}</Text>
      <Text style={styles.detail}>
        {annual
          ? annualPlanDetail(trialEligibility, t)
          : t('Pricing will be supplied by the App Store.')}
      </Text>
      <Button
        accessibilityLabel={`${t(name)} ${t('purchase unavailable')}`}
        disabled
      >
        {t('Purchase unavailable')}
      </Button>
    </View>
  );
}

export function PaywallShell({
  trialEligibility = 'unknown',
}: {
  trialEligibility?: TrialEligibility;
}) {
  const { t } = useLanguage();
  return (
    <View style={styles.stack}>
      <SectionHeader
        title={t('Unlock full PitchValue analysis')}
        detail={t(
          'Review the planned Premium experience. Store purchases are not available yet.',
        )}
      />
      <View style={sharedStyles.card}>
        {premiumBenefits.map((benefit) => (
          <Text key={benefit} style={styles.benefit}>
            • {t(benefit)}
          </Text>
        ))}
      </View>
      {plans.map((plan) => (
        <PaywallPlanCard
          annual={plan.id === 'annual'}
          key={plan.id}
          name={plan.name}
          trialEligibility={trialEligibility}
        />
      ))}
      <Button
        accessibilityLabel={t('Restore purchases unavailable')}
        disabled
        variant="quiet"
      >
        {t('Restore Purchases')} · {t('Unavailable')}
      </Button>
      <Text style={styles.footnote}>
        {t(
          'Payment, restoration, trial confirmation, and entitlement changes are currently unavailable.',
        )}
      </Text>
    </View>
  );
}

export function PaywallPresentation({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  return (
    <View style={styles.stack}>
      <Button
        accessibilityLabel={t('Close Premium options')}
        onPress={onClose}
        variant="quiet"
      >
        {t('Close')}
      </Button>
      <PaywallShell trialEligibility="unknown" />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  highlighted: { borderColor: colors.accent },
  name: { color: colors.text, ...typography.sectionTitle },
  price: { color: colors.text, ...typography.featured },
  detail: { color: colors.textSecondary, ...typography.body },
  benefit: { color: colors.text, ...typography.body },
  footnote: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
});
