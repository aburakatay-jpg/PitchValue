import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { InlineNotice, PredictionCardSkeleton } from '@/components/feedback';
import { LockedPremiumSection } from '@/components/PremiumGuard';
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
import {
  assistantFeatures,
  couponRiskOptions,
  type AssistantFeature,
  type CouponRisk,
} from '@/lib/assistant-contract';
import type { PublicApiError } from '@/lib/public-api';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';
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

function featureAvailability(feature: AssistantFeature): string {
  return feature === 'Today’s Best Value'
    ? 'Public signals available when published'
    : 'Currently unavailable';
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
  return (
    <View style={styles.stack}>
      {assistantFeatures.map((feature, index) => (
        <Pressable
          accessibilityHint={featureDetails[feature]}
          accessibilityLabel={feature}
          accessibilityRole="button"
          key={feature}
          onPress={() => onSelect(feature)}
          style={({ pressed }) => [
            styles.featureCard,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.number}>0{index + 1}</Text>
          <View style={styles.flex}>
            <Text style={styles.featureTitle}>{feature}</Text>
            <Text style={styles.secondary}>{featureDetails[feature]}</Text>
            <Text style={styles.availability}>
              {featureAvailability(feature)}
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
  const content = (
    <>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.meta}>PUBLISHED ANALYSIS</Text>
        <Badge
          label={prediction.policy_decision.replaceAll('_', ' ')}
          tone="accent"
        />
      </View>
      <Text style={styles.featureTitle}>
        {prediction.selection.replaceAll('_', ' ')}
      </Text>
      <Text style={styles.secondary}>
        {prediction.market.replaceAll('_', ' ')}
      </Text>
      <View style={styles.metrics}>
        <Text style={styles.metric}>
          Bet Score: {prediction.bet_score ?? 'Score unavailable'}
        </Text>
        <Text style={styles.metric}>Edge: {prediction.edge}</Text>
      </View>
    </>
  );
  if (!onSelect) return <View style={styles.signalCard}>{content}</View>;
  return (
    <Pressable
      accessibilityLabel={`Use ${prediction.selection} as explanation context`}
      accessibilityRole="button"
      onPress={onSelect}
      style={({ pressed }) => [styles.signalCard, pressed && styles.pressed]}
    >
      {content}
    </Pressable>
  );
}

function BestValueSurface({ data }: { data: PredictionListResponse | null }) {
  if (!data || data.predictions.length === 0) {
    return (
      <EmptyState
        title="No eligible value signals available right now"
        detail="PitchValue will not create alternatives when the public publication pool is empty."
      />
    );
  }
  return (
    <View style={styles.stack}>
      <SectionHeader
        title="Current published signals"
        detail="Shown in published order. No additional ranking is applied."
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
  const [selected, setSelected] = useState<PublicPrediction | null>(null);
  if (!data || data.predictions.length === 0) {
    return (
      <EmptyState
        title="No pick selected"
        detail="An explanation must start from an authoritative published PitchValue analysis."
      />
    );
  }
  return (
    <View style={styles.stack}>
      <SectionHeader
        title="Choose published context"
        detail="Only public analysis is offered. Choosing it does not generate a new prediction."
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
          title="Explanation unavailable"
          detail={`The published ${selected.market.replaceAll('_', ' ')} / ${selected.selection.replaceAll('_', ' ')} analysis is selected, but a detailed explanation is not available.`}
        />
      ) : null}
    </View>
  );
}

function AskSurface() {
  const [question, setQuestion] = useState('');
  return (
    <View style={styles.stack}>
      <UnavailableState
        title="Ask PitchValue unavailable"
        detail="The assistant is currently unavailable. No answer or prediction will be generated."
      />
      <View style={styles.form}>
        <Text style={styles.label}>Question</Text>
        <TextInput
          accessibilityLabel="Question for PitchValue"
          multiline
          onChangeText={setQuestion}
          placeholder="Ask about a published PitchValue analysis"
          placeholderTextColor={colors.textSecondary}
          returnKeyType="send"
          style={styles.input}
          value={question}
        />
        <Button accessibilityLabel="Send question unavailable" disabled>
          Send unavailable
        </Button>
      </View>
    </View>
  );
}

function CouponSurface({ data }: { data: PredictionListResponse | null }) {
  const [risk, setRisk] = useState<CouponRisk>('BALANCED');
  const eligible = data?.predictions.length ?? 0;
  return (
    <View style={styles.stack}>
      <SectionHeader
        title="Coupon Builder"
        detail="Choose a preference to preview the intended experience. No coupon will be generated."
      />
      <View accessibilityRole="radiogroup" style={styles.riskGroup}>
        {couponRiskOptions.map((option) => {
          const selected = risk === option.key;
          return (
            <Pressable
              accessibilityLabel={`${option.label}. ${option.detail}`}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              key={option.key}
              onPress={() => setRisk(option.key)}
              style={[styles.riskOption, selected && styles.riskSelected]}
            >
              <Text style={styles.featureTitle}>{option.label}</Text>
              <Text style={styles.secondary}>{option.detail}</Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.secondary}>
        A future coupon may contain 1–4 selections and only one selection from
        each match.
      </Text>
      {eligible === 0 ? (
        <EmptyState
          title="No publishable signals"
          detail="Coupon Builder will not use unpublished or internal analysis to fill the pool."
        />
      ) : (
        <InlineNotice
          title={`${eligible} eligible signal${eligible === 1 ? '' : 's'} available`}
          detail={
            eligible < 4
              ? `Only ${eligible} eligible signal${eligible === 1 ? ' is' : 's are'} available right now. A future builder must not force four selections.`
              : 'A future builder may use 1–4 selections and must keep one selection per canonical match.'
          }
        />
      )}
      <UnavailableState
        title="Coupon Builder unavailable"
        detail="Coupon generation is not available. Eligible public analyses are not combined automatically."
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
  onOpenPremium,
  onRefresh,
  premiumAccess,
  refreshing,
}: {
  data: PredictionListResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onOpenPremium: () => void;
  onRefresh: () => void;
  premiumAccess: boolean;
  refreshing: boolean;
}) {
  const [activeFeature, setActiveFeature] = useState<AssistantFeature | null>(
    null,
  );
  return (
    <Screen keyboardAware onRefresh={onRefresh} refreshing={refreshing}>
      <AppHeader eyebrow="Grounded analysis tools" title="PitchValue AI" />
      <Text style={styles.principle}>
        AI explains PitchValue analysis. It does not create independent
        predictions.
      </Text>
      <FeatureCards onSelect={setActiveFeature} />
      {initialLoading && data === null ? <AssistantSkeleton /> : null}
      {error && data === null ? (
        <UnavailableState
          detail="Published analysis context could not be loaded. Please try again shortly."
          retry={onRefresh}
          title="Public analysis unavailable"
        />
      ) : null}
      {error && data !== null ? (
        <InlineNotice
          detail="Showing the last available public analysis context."
          title="Could not refresh public analysis"
          tone="negative"
        />
      ) : null}
      {activeFeature &&
      !(initialLoading && data === null) &&
      !(error && data === null) ? (
        <FeatureSurface data={data} feature={activeFeature} />
      ) : null}
      {!premiumAccess ? (
        <LockedPremiumSection
          detail="AI access is not available yet. Viewing Premium options will not change access."
          onUnlock={onOpenPremium}
          title="Premium AI foundation"
        />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  featureCard: {
    ...sharedStyles.card,
    flexDirection: 'row',
    minHeight: touchTarget,
  },
  signalCard: { ...sharedStyles.card, minHeight: touchTarget },
  number: { color: colors.secondary, ...typography.caption },
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
    backgroundColor: colors.background,
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
  riskSelected: { borderColor: colors.secondary },
});
