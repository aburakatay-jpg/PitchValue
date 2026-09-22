import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { useCommerce } from '@/features/entitlement/CommerceContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import type { CanonicalPlan, CommerceProduct } from '@/lib/commerce';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
  createThemedStyleSheet,
} from '@/theme/tokens';
import type { TrialEligibility } from '@/types/entitlement';

const planNames: Readonly<Record<CanonicalPlan, string>> = {
  monthly: 'Monthly',
  quarterly: '3 Months',
  annual: 'Annual',
};

export function annualPlanDetail(
  eligibility: TrialEligibility,
  t: (k: string) => string,
): string {
  if (eligibility === 'eligible') {
    return t('A trial may be offered after App Store eligibility is verified.');
  }
  return t('Trial eligibility and localized pricing require the App Store.');
}

function PaywallPlanRow({
  product,
  selected,
  onSelect,
  last,
}: {
  product: CommerceProduct;
  selected: boolean;
  onSelect: () => void;
  last: boolean;
}) {
  const { t } = useLanguage();
  const name = t(planNames[product.id]);
  const price = product.localizedPrice ?? t('Localized price unavailable');
  return (
    <Pressable
      accessibilityLabel={`${name}, ${price}`}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onSelect}
      style={({ pressed }) => [
        styles.planRow,
        selected && styles.planRowSelected,
        !last && styles.planDivider,
        pressed && styles.pressed,
      ]}
      testID={`paywall-plan-${product.id}`}
    >
      <View style={[styles.radio, selected && styles.radioSelected]}>
        {selected ? <View style={styles.radioCenter} /> : null}
      </View>
      <Text style={styles.planName}>{name}</Text>
      <Text style={styles.planPrice}>{price}</Text>
    </Pressable>
  );
}

export function PaywallShell({
  trialEligibility = 'unknown',
}: {
  trialEligibility?: TrialEligibility;
}) {
  const { t } = useLanguage();
  const commerce = useCommerce();
  const session = useProductSession();
  const [selectedPlan, setSelectedPlan] = useState<CanonicalPlan | null>(null);
  // The default adapter exposes unconfigured placeholders for diagnostics.
  // They are not purchasable store products and must not appear as plans.
  const products = commerce.isConfigured
    ? commerce.products.filter((product) => product.provider !== 'UNCONFIGURED')
    : [];
  const selectedProduct = products.find(
    (product) => product.id === selectedPlan,
  );
  const canPurchase =
    session.state === 'AUTHENTICATED' &&
    Boolean(selectedProduct?.localizedPrice) &&
    !commerce.isFetchingProducts &&
    !commerce.isPurchasing;

  return (
    <View style={styles.stack}>
      <Text style={styles.context}>{t('PitchValue Premium')}</Text>
      <Text accessibilityRole="header" style={styles.headline}>
        {t('Not more predictions.\nBetter filtering.')}
      </Text>

      {products.length > 0 ? (
        <View
          accessibilityLabel={t('Premium plans')}
          accessibilityRole="radiogroup"
          style={styles.planGroup}
          testID="paywall-plan-group"
        >
          {products.map((product, index) => (
            <PaywallPlanRow
              key={product.id}
              product={product}
              selected={selectedPlan === product.id}
              onSelect={() => setSelectedPlan(product.id)}
              last={index === products.length - 1}
            />
          ))}
        </View>
      ) : (
        <Text style={styles.unavailable} testID="paywall-plans-unavailable">
          {commerce.isFetchingProducts
            ? t('Loading plans')
            : t('Plans and prices are currently unavailable.')}
        </Text>
      )}

      <Button
        accessibilityLabel={t('Go Premium')}
        disabled={!canPurchase}
        onPress={() => {
          if (selectedProduct && canPurchase) {
            void commerce.purchase(selectedProduct.id).catch(() => undefined);
          }
        }}
        testID="paywall-primary"
        variant="auth"
      >
        {commerce.isPurchasing ? t('Please wait') : t('Go Premium')}
      </Button>
      {commerce.error ? (
        <Text accessibilityLiveRegion="polite" style={styles.unavailable}>
          {t('Purchase is temporarily unavailable.')}
        </Text>
      ) : null}

      <View style={styles.benefits} testID="paywall-benefits">
        <Text accessibilityRole="header" style={styles.benefitTitle}>
          {t('With Premium')}
        </Text>
        <Text style={styles.unavailable}>
          {t('Premium feature details are not available yet.')}
        </Text>
      </View>

      <Button
        accessibilityLabel={t('Restore purchases')}
        disabled={!commerce.isConfigured || commerce.isRestoring}
        onPress={commerce.restore}
        variant="quiet"
      >
        {t('Restore Purchases')}{' '}
        {!commerce.isConfigured ? `· ${t('Unavailable')}` : ''}
      </Button>
      <Text style={styles.footnote}>
        {commerce.isConfigured
          ? t(
              'Payment, restoration, and trial confirmation will use the App Store.',
            )
          : t(
              'Payment, restoration, trial confirmation, and entitlement changes are currently unavailable.',
            )}
      </Text>
      {trialEligibility === 'eligible' ? (
        <Text style={styles.footnote}>
          {annualPlanDetail(trialEligibility, t)}
        </Text>
      ) : null}
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

const styles = createThemedStyleSheet({
  stack: { gap: spacing.lg },
  context: { color: colors.textSecondary, ...typography.caption },
  headline: { color: colors.text, ...typography.pageTitle },
  planGroup: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    overflow: 'hidden',
  },
  planRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  planRowSelected: { backgroundColor: colors.segmentedSelectedBackground },
  planDivider: {
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  radio: {
    alignItems: 'center',
    borderColor: colors.textSecondary,
    borderRadius: radii.pill,
    borderWidth: 2,
    height: 20,
    justifyContent: 'center',
    width: 20,
  },
  radioSelected: { borderColor: colors.text },
  radioCenter: {
    backgroundColor: colors.text,
    borderRadius: radii.pill,
    height: 10,
    width: 10,
  },
  planName: {
    color: colors.text,
    flexGrow: 1,
    flexShrink: 1,
    ...typography.body,
  },
  planPrice: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  benefits: { gap: spacing.sm },
  benefitTitle: { color: colors.text, ...typography.sectionTitle },
  unavailable: { color: colors.textSecondary, ...typography.body },
  footnote: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
  pressed: { opacity: 0.8 },
});
