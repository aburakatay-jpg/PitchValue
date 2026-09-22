import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { SymbolView, type SFSymbol } from 'expo-symbols';
import {
  createThemedStyleSheet,
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

import { InlineNotice, PredictionCardSkeleton } from '@/components/feedback';
import {
  AppHeader,
  Badge,
  Button,
  EmptyState,
  Screen,
  SectionHeader,
  sharedStyles,
  UnavailableState,
} from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import {
  assistantFeatures,
  couponRiskOptions,
  type AssistantFeature,
  type CouponRisk,
} from '@/lib/assistant-contract';
import type { PublicApiError } from '@/lib/public-api';
import type {
  PredictionListResponse,
  PublicPrediction,
} from '@/types/public-api';

const featureDetails: Readonly<Record<AssistantFeature, string>> = {
  'Coupon Builder': 'Organize eligible published analyses into 1–4 selections.',
  'Today’s Best Value':
    'Review the current public analysis pool in published order.',
  'Explain a Pick': 'Choose a published analysis as authoritative context.',
  'Ask PitchValue':
    'Ask grounded questions when the assistant service is available.',
};

const featureIcons: Readonly<Record<AssistantFeature, SFSymbol>> = {
  'Coupon Builder': 'square.stack.3d.up',
  'Today’s Best Value': 'chart.line.uptrend.xyaxis',
  'Explain a Pick': 'text.magnifyingglass',
  'Ask PitchValue': 'bubble.left.and.bubble.right',
};

function featureAvailability(
  feature: AssistantFeature,
  t: (k: string) => string,
): string {
  return feature === 'Today’s Best Value'
    ? t('Public signals available when published')
    : t('Currently unavailable');
}

export function AssistantSkeleton() {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.stack}
      testID="assistant-skeleton"
    >
      <PredictionCardSkeleton />
      <PredictionCardSkeleton />
    </View>
  );
}

function FeatureCards({
  onSelect,
}: {
  onSelect: (value: AssistantFeature) => void;
}) {
  const { t } = useLanguage();
  return (
    <View style={styles.stack}>
      {assistantFeatures.map((feature) => (
        <Pressable
          accessibilityHint={t(featureDetails[feature])}
          accessibilityLabel={t(feature)}
          accessibilityRole="button"
          key={feature}
          onPress={() => onSelect(feature)}
          style={({ pressed }) => [
            styles.featureCard,
            pressed && styles.pressed,
          ]}
        >
          <View accessible={false} style={styles.featureIcon}>
            <SymbolView
              name={featureIcons[feature]}
              size={21}
              tintColor={colors.secondary}
            />
          </View>
          <View style={styles.flex}>
            <Text style={styles.featureTitle}>{t(feature)}</Text>
            <Text style={styles.secondary}>{t(featureDetails[feature])}</Text>
            <Text style={styles.availability}>
              {featureAvailability(feature, t)}
            </Text>
          </View>
        </Pressable>
      ))}
    </View>
  );
}

function PublicSignalRow({
  prediction,
  onSelect,
}: {
  prediction: PublicPrediction;
  onSelect?: (() => void) | undefined;
}) {
  const { t } = useLanguage();
  const content = (
    <>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.meta}>{t('PUBLISHED ANALYSIS')}</Text>
        <Badge
          label={t(prediction.policy_decision.replaceAll('_', ' '))}
          tone="accent"
        />
      </View>
      <Text style={styles.featureTitle}>
        {t(prediction.selection.replaceAll('_', ' '))}
      </Text>
      <Text style={styles.secondary}>
        {t(prediction.market.replaceAll('_', ' '))}
      </Text>
      <View style={styles.metrics}>
        <Text style={styles.metric}>
          {t('Bet Score')}: {prediction.bet_score ?? t('Score unavailable')}
        </Text>
        <Text style={styles.metric}>
          {t('Edge')}: {prediction.edge}
        </Text>
      </View>
    </>
  );
  if (!onSelect) return <View style={styles.signalCard}>{content}</View>;
  return (
    <Pressable
      accessibilityLabel={`${t('Use')} ${t(prediction.selection)} ${t('as explanation context')}`}
      accessibilityRole="button"
      onPress={onSelect}
      style={({ pressed }) => [styles.signalCard, pressed && styles.pressed]}
    >
      {content}
    </Pressable>
  );
}

function BestValueSurface({ data }: { data: PredictionListResponse | null }) {
  const { t } = useLanguage();
  if (!data || data.predictions.length === 0) {
    return (
      <EmptyState
        title={t('No eligible value signals available right now')}
        detail={t(
          'PitchValue will not create alternatives when the public publication pool is empty.',
        )}
      />
    );
  }
  return (
    <View style={styles.stack}>
      <SectionHeader
        title={t('Current published signals')}
        detail={t(
          'Shown in published order. No additional ranking is applied.',
        )}
      />
      {data.predictions.map((prediction, index) => (
        <PublicSignalRow
          key={`${prediction.match_id}-${prediction.market}-${prediction.selection}-${index}`}
          prediction={prediction}
        />
      ))}
    </View>
  );
}

function ExplainSurface({ data }: { data: PredictionListResponse | null }) {
  const { t } = useLanguage();
  const [selected, setSelected] = useState<PublicPrediction | null>(null);
  if (!data || data.predictions.length === 0) {
    return (
      <EmptyState
        title={t('No pick selected')}
        detail={t(
          'An explanation must start from an authoritative published PitchValue analysis.',
        )}
      />
    );
  }
  return (
    <View style={styles.stack}>
      <SectionHeader
        title={t('Choose published context')}
        detail={t(
          'Only public analysis is offered. Choosing it does not generate a new prediction.',
        )}
      />
      {data.predictions.map((prediction, index) => (
        <PublicSignalRow
          key={`${prediction.match_id}-${prediction.market}-${prediction.selection}-${index}`}
          onSelect={() => setSelected(prediction)}
          prediction={prediction}
        />
      ))}
      {selected ? (
        <UnavailableState
          title={t('Explanation unavailable')}
          detail={`${t('The published')} ${t(selected.market.replaceAll('_', ' '))} / ${t(selected.selection.replaceAll('_', ' '))} ${t('analysis is selected, but a detailed explanation is not available.')}`}
        />
      ) : null}
    </View>
  );
}

function AskSurface() {
  const { t } = useLanguage();
  const [question, setQuestion] = useState('');
  return (
    <View style={styles.stack}>
      <UnavailableState
        title={t('Ask PitchValue unavailable')}
        detail={t(
          'The assistant is currently unavailable. No answer or prediction will be generated.',
        )}
      />
      <View style={styles.form}>
        <Text style={styles.label}>{t('Question')}</Text>
        <TextInput
          accessibilityLabel={t('Question for PitchValue')}
          multiline
          onChangeText={setQuestion}
          placeholder={t('Ask about a published PitchValue analysis')}
          placeholderTextColor={colors.textSecondary}
          returnKeyType="send"
          style={styles.input}
          value={question}
        />
        <Button accessibilityLabel={t('Send question unavailable')} disabled>
          {t('Send unavailable')}
        </Button>
      </View>
    </View>
  );
}

function CouponSurface({ data }: { data: PredictionListResponse | null }) {
  const { t } = useLanguage();
  const [risk, setRisk] = useState<CouponRisk>('BALANCED');
  const eligible = data?.predictions.length ?? 0;
  return (
    <View style={styles.stack}>
      <SectionHeader
        title={t('Coupon Builder')}
        detail={t(
          'Choose a preference to preview the intended experience. No coupon will be generated.',
        )}
      />
      <View accessibilityRole="radiogroup" style={styles.riskGroup}>
        {couponRiskOptions.map((option) => {
          const selected = risk === option.key;
          return (
            <Pressable
              accessibilityLabel={`${t(option.label)}. ${t(option.detail)}`}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              key={option.key}
              onPress={() => setRisk(option.key)}
              style={[styles.riskOption, selected && styles.riskSelected]}
            >
              <Text style={styles.featureTitle}>{t(option.label)}</Text>
              <Text style={styles.secondary}>{t(option.detail)}</Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.secondary}>
        {t(
          'A future coupon may contain 1–4 selections and only one selection from each match.',
        )}
      </Text>
      {eligible === 0 ? (
        <EmptyState
          title={t('No publishable signals')}
          detail={t(
            'Coupon Builder will not use unpublished or internal analysis to fill the pool.',
          )}
        />
      ) : (
        <InlineNotice
          title={`${eligible} ${eligible === 1 ? t('eligible signal') : t('eligible signals')} ${t('available')}`}
          detail={
            eligible < 4
              ? `${t('Only')} ${eligible} ${eligible === 1 ? t('eligible signal is') : t('eligible signals are')} ${t('available right now. A future builder must not force four selections.')}`
              : t(
                  'A future builder may use 1–4 selections and must keep one selection per canonical match.',
                )
          }
        />
      )}
      <UnavailableState
        title={t('Coupon Builder unavailable')}
        detail={t(
          'Coupon generation is not available. Eligible public analyses are not combined automatically.',
        )}
      />
    </View>
  );
}

function FeatureSurface({
  data,
  feature,
}: {
  data: PredictionListResponse | null;
  feature: AssistantFeature;
}) {
  if (feature === 'Today’s Best Value') return <BestValueSurface data={data} />;
  if (feature === 'Explain a Pick') return <ExplainSurface data={data} />;
  if (feature === 'Ask PitchValue') return <AskSurface />;
  return <CouponSurface data={data} />;
}

export function AiView({
  data,
  error,
  initialLoading,
  onRefresh,
  refreshing,
}: {
  data: PredictionListResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const { t } = useLanguage();
  const [activeFeature, setActiveFeature] = useState<AssistantFeature | null>(
    null,
  );
  return (
    <Screen keyboardAware onRefresh={onRefresh} refreshing={refreshing}>
      <AppHeader title={t('PV Engine')} />
      <FeatureCards onSelect={setActiveFeature} />
      {initialLoading && data === null ? <AssistantSkeleton /> : null}
      {error && data === null ? (
        <UnavailableState
          detail={t(
            'Published analysis context could not be loaded. Please try again shortly.',
          )}
          retry={onRefresh}
          title={t('Public analysis unavailable')}
        />
      ) : null}
      {error && data !== null ? (
        <InlineNotice
          detail={t('Showing the last available public analysis context.')}
          title={t('Could not refresh public analysis')}
          tone="negative"
        />
      ) : null}
      {activeFeature &&
      !(initialLoading && data === null) &&
      !(error && data === null) ? (
        <FeatureSurface data={data} feature={activeFeature} />
      ) : null}
    </Screen>
  );
}

const styles = createThemedStyleSheet({
  stack: { gap: spacing.md },
  featureCard: {
    ...sharedStyles.card,
    flexDirection: 'row',
    minHeight: touchTarget,
  },
  signalCard: { ...sharedStyles.card, minHeight: touchTarget },
  featureIcon: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
    width: touchTarget,
  },
  flex: { flex: 1, gap: spacing.xs },
  featureTitle: {
    color: colors.text,
    flexShrink: 1,
    ...typography.sectionTitle,
  },
  principle: { color: colors.textSecondary, ...typography.body },
  secondary: { color: colors.textSecondary, flexShrink: 1, ...typography.body },
  availability: { color: colors.warning, ...typography.caption },
  meta: { color: colors.textSecondary, ...typography.caption },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  metric: { color: colors.text, ...typography.metadata },
  pressed: { opacity: 0.82 },
  form: { ...sharedStyles.card, gap: spacing.sm },
  label: { color: colors.text, ...typography.caption },
  input: {
    backgroundColor: colors.inputBackground,
    borderColor: colors.border,
    borderRadius: radii.sm,
    borderWidth: 1,
    color: colors.text,
    minHeight: 112,
    padding: spacing.md,
    textAlignVertical: 'top',
    ...typography.body,
  },
  riskGroup: { gap: spacing.sm },
  riskOption: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    gap: spacing.xs,
    minHeight: touchTarget,
    padding: spacing.md,
  },
  riskSelected: { borderColor: colors.controlSelectedAccent },
});
