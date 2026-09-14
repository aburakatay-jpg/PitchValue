import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { PremiumGuard } from '@/components/PremiumGuard';
import {
  AppHeader,
  Badge,
  Button,
  EmptyState,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { config } from '@/lib/config';
import { colors, spacing, typeScale } from '@/theme/tokens';

const analysisFields = [
  ['Selected market', 'Development-only market'],
  ['Odds', '1.95 mock'],
  ['PitchValue Score', '74 mock'],
  ['Edge', '+4.2% mock'],
  ['Probability / confidence', '55% / illustrative'],
] as const;

export default function MatchDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const match = config.developmentPreviewEnabled
    ? mockMatches.find((item) => item.id === id)
    : undefined;
  if (!match) {
    return (
      <Screen>
        <AppHeader title="Match detail" />
        <EmptyState
          title="Public match data unavailable"
          detail="Internal or synthetic analysis is never used as a public fallback."
        />
      </Screen>
    );
  }
  return (
    <Screen>
      <AppHeader
        eyebrow={`${match.competition} · ${match.kickoff}`}
        title={`${match.homeTeam} vs ${match.awayTeam}`}
      />
      <Badge label="Development-only analysis" tone="accent" />
      <View style={styles.metrics}>
        {analysisFields.map(([label, value]) => (
          <View key={label} style={sharedStyles.rowBetween}>
            <Text style={sharedStyles.label}>{label}</Text>
            <Text style={styles.metric}>{value}</Text>
          </View>
        ))}
      </View>
      <PremiumGuard onLocked={() => router.push('/paywall')}>
        <View style={sharedStyles.card}>
          <SectionHeader
            title="Short reasoning"
            detail="No real analysis is produced in this foundation build."
          />
          <Text style={sharedStyles.body}>
            Alternative pick: development placeholder only.
          </Text>
        </View>
      </PremiumGuard>
      <View style={styles.actions}>
        <Button disabled>Save Pick</Button>
        <Button disabled>Final Check</Button>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  metrics: { ...sharedStyles.card, gap: spacing.md },
  metric: {
    color: colors.text,
    fontSize: typeScale.body,
    fontWeight: '800',
    flexShrink: 1,
    textAlign: 'right',
  },
  actions: { gap: spacing.sm },
});
