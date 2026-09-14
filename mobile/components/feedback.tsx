import { StyleSheet, Text, View } from 'react-native';

import { colors, radii, spacing, typography } from '@/theme/tokens';

export function SkeletonBlock({
  height,
  width = '100%',
}: {
  height: number;
  width?: number | `${number}%`;
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.skeleton, { height, width }]}
    />
  );
}

export function FixtureCardSkeleton() {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.card}
      testID="fixture-card-skeleton"
    >
      <SkeletonBlock height={14} width="45%" />
      <SkeletonBlock height={22} width="78%" />
      <SkeletonBlock height={22} width="64%" />
      <SkeletonBlock height={18} width="38%" />
    </View>
  );
}

export function PredictionCardSkeleton() {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.card}
      testID="prediction-card-skeleton"
    >
      <SkeletonBlock height={14} width="38%" />
      <SkeletonBlock height={26} width="70%" />
      <View style={styles.row}>
        <SkeletonBlock height={36} width="30%" />
        <SkeletonBlock height={36} width="30%" />
      </View>
    </View>
  );
}

export function InlineNotice({
  title,
  detail,
  tone = 'warning',
}: {
  title: string;
  detail?: string | undefined;
  tone?: 'warning' | 'negative';
}) {
  return (
    <View
      accessibilityLiveRegion="polite"
      accessibilityRole={tone === 'negative' ? 'alert' : 'text'}
      style={[styles.notice, { borderColor: colors[tone] }]}
    >
      <Text style={[styles.noticeTitle, { color: colors[tone] }]}>{title}</Text>
      {detail ? <Text style={styles.noticeDetail}>{detail}</Text> : null}
    </View>
  );
}

export function StaleIndicator({ detail }: { detail?: string | undefined }) {
  return (
    <InlineNotice detail={detail} title="Data may be outdated" tone="warning" />
  );
}

const styles = StyleSheet.create({
  skeleton: {
    backgroundColor: colors.surfaceRaised,
    borderRadius: radii.sm,
  },
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    gap: spacing.md,
    padding: spacing.md,
  },
  row: { flexDirection: 'row', gap: spacing.sm },
  notice: {
    backgroundColor: colors.surface,
    borderLeftWidth: 3,
    borderRadius: radii.sm,
    gap: spacing.xs,
    padding: spacing.md,
  },
  noticeTitle: { ...typography.caption },
  noticeDetail: { color: colors.textSecondary, ...typography.metadata },
});
