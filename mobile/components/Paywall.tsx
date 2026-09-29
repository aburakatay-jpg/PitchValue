import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SymbolView, type SFSymbol } from 'expo-symbols';

import { Button } from '@/components/ui';
import { LegalModal, LegalTextLink } from '@/components/LegalModal';
import { useCommerce } from '@/features/entitlement/CommerceContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { useOptionalAppearanceResolution } from '@/features/appearance/AppearanceContext';
import type { CanonicalPlan, CommerceProduct } from '@/lib/commerce';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
  createThemedStyleSheet,
  getActiveAppearance,
} from '@/theme/tokens';
import type { TrialEligibility } from '@/types/entitlement';
import type { LegalDocumentId } from '@/legal/content';

const planNames: Readonly<Record<CanonicalPlan, string>> = {
  monthly: 'Monthly',
  quarterly: '3 Months',
  annual: 'Annual',
};
const planOrder: readonly CanonicalPlan[] = ['monthly', 'quarterly', 'annual'];
const closeCircleSize = 36;
const premiumBenefits = [
  'More powerful analysis with PV Engine',
  'Discover value opportunities faster',
  'Edge and Bet Score visibility',
  'Deeper insights across supported markets',
  'A final review with Final Check',
  'Premium filtering experience',
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

function PaywallPlanRow({
  plan,
  product,
  selected,
  onSelect,
  last,
}: {
  plan: CanonicalPlan;
  product: CommerceProduct | undefined;
  selected: boolean;
  onSelect: () => void;
  last: boolean;
}) {
  const { t } = useLanguage();
  const name = t(planNames[plan]);
  const available = Boolean(product?.localizedPrice);
  const price = product?.localizedPrice || '—';
  return (
    <Pressable
      accessibilityLabel={`${name}, ${available ? price : t('Price unavailable')}`}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected, disabled: !available }}
      disabled={!available}
      onPress={onSelect}
      style={({ pressed }) => [
        styles.planRow,
        selected && styles.planRowSelected,
        !last && styles.planDivider,
        pressed && styles.pressed,
      ]}
      testID={`paywall-plan-${plan}`}
    >
      <View style={[styles.radio, selected && styles.radioSelected]}>
        {selected ? <View style={styles.radioCenter} /> : null}
      </View>
      <Text style={styles.planName}>{name}</Text>
      <Text style={[styles.planPrice, !available && styles.placeholderPrice]}>
        {price}
      </Text>
    </Pressable>
  );
}

export function PaywallShell({
  trialEligibility: _trialEligibility,
}: {
  trialEligibility?: TrialEligibility;
}) {
  const { t } = useLanguage();
  const resolvedAppearance = useOptionalAppearanceResolution();
  const isLight = (resolvedAppearance ?? getActiveAppearance()) === 'light';
  const commerce = useCommerce();
  const session = useProductSession();
  const [selectedPlan, setSelectedPlan] = useState<CanonicalPlan | null>(null);
  const [legalDocument, setLegalDocument] = useState<LegalDocumentId | null>(
    null,
  );
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
      <Text accessibilityRole="header" style={styles.headline}>
        {t('Not more predictions.\nBetter filtering.')}
      </Text>

      <View
        accessibilityLabel={t('Premium plans')}
        accessibilityRole="radiogroup"
        style={styles.planGroup}
        testID="paywall-plan-group"
      >
        {planOrder.map((plan, index) => {
          const product = products.find((candidate) => candidate.id === plan);
          return (
            <PaywallPlanRow
              key={plan}
              plan={plan}
              product={product}
              selected={
                Boolean(product?.localizedPrice) && selectedPlan === plan
              }
              onSelect={() => setSelectedPlan(plan)}
              last={index === planOrder.length - 1}
            />
          );
        })}
      </View>

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
        style={isLight ? styles.lightPrimary : undefined}
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
        <View style={styles.benefitList}>
          {premiumBenefits.map((benefit, index) => (
            <View
              key={benefit}
              style={styles.benefitRow}
              testID={`paywall-benefit-${index + 1}`}
            >
              <View style={styles.benefitIcon}>
                <SymbolView
                  accessibilityElementsHidden
                  importantForAccessibility="no"
                  name={'circle.fill' as SFSymbol}
                  size={7}
                  tintColor={colors.interactiveTextAccent}
                />
              </View>
              <Text style={styles.benefitText}>{t(benefit)}</Text>
            </View>
          ))}
        </View>
      </View>

      <Pressable
        accessibilityLabel={t('Restore purchases')}
        accessibilityRole="button"
        accessibilityState={{ disabled: true }}
        disabled
        style={({ pressed }) => [
          styles.restoreAction,
          pressed && styles.pressed,
        ]}
        testID="paywall-restore"
      >
        <Text style={styles.restoreText}>{t('Restore Purchases')}</Text>
      </Pressable>
      <Text style={styles.unavailable} testID="paywall-restore-unavailable">
        {t('Restore Purchases is currently unavailable.')}
      </Text>

      <View style={styles.legalLinks} testID="paywall-legal-links">
        <LegalTextLink
          label={t('Subscription Explanation')}
          onPress={() => setLegalDocument('subscription')}
          testID="paywall-legal-subscription"
        />
        <LegalTextLink
          label={t('Terms of Use')}
          onPress={() => setLegalDocument('terms')}
          testID="paywall-legal-terms"
        />
        <LegalTextLink
          label={t('Privacy Policy')}
          onPress={() => setLegalDocument('privacy')}
          testID="paywall-legal-privacy"
        />
      </View>
      <LegalModal
        documentId={legalDocument}
        onClose={() => setLegalDocument(null)}
      />
    </View>
  );
}

export function PaywallPresentation() {
  return <PaywallShell />;
}

export function PaywallHeaderClose({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  useOptionalAppearanceResolution();
  return (
    <Pressable
      accessibilityLabel={t('Close')}
      accessibilityRole="button"
      onPress={onClose}
      style={({ pressed }) => [styles.closeControl, pressed && styles.pressed]}
      testID="paywall-close"
    >
      <View style={styles.closeCircle} testID="paywall-close-circle">
        <SymbolView
          accessibilityElementsHidden
          importantForAccessibility="no"
          name={'xmark' as SFSymbol}
          size={18}
          tintColor={colors.text}
        />
      </View>
    </Pressable>
  );
}

const styles = createThemedStyleSheet({
  stack: { gap: spacing.lg },
  closeControl: {
    alignItems: 'center',
    height: touchTarget,
    justifyContent: 'center',
    width: touchTarget,
  },
  closeCircle: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: closeCircleSize / 2,
    height: closeCircleSize,
    justifyContent: 'center',
    width: closeCircleSize,
  },
  lightPrimary: {
    backgroundColor: colors.authPrimaryBackground,
    borderWidth: 0,
  },
  headline: {
    color: colors.text,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
  },
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
  placeholderPrice: { color: colors.textSecondary },
  benefits: { gap: spacing.sm },
  benefitTitle: { color: colors.text, ...typography.sectionTitle },
  benefitList: { gap: spacing.sm },
  benefitRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: spacing.sm,
  },
  benefitIcon: { paddingTop: spacing.sm },
  benefitText: { color: colors.text, flex: 1, ...typography.body },
  unavailable: { color: colors.textSecondary, ...typography.body },
  restoreAction: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
  },
  restoreText: { color: colors.textSecondary, ...typography.body },
  legalLinks: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    justifyContent: 'center',
  },
  pressed: { opacity: 0.8 },
});
