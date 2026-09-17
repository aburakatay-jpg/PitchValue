import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, sharedStyles } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
import { colors, spacing, touchTarget, typography } from '@/theme/tokens';
import type {
  PublicFixtureSummary,
  PublicPrediction,
} from '@/types/public-api';

function fixtureAnalysisLabel(fixture: PublicFixtureSummary): string {
  if (fixture.public_analysis === 'AVAILABLE_PUBLIC') {
    return fixture.publication_state.replaceAll('_', ' ');
  }
  if (
    fixture.public_analysis === 'DATA_INSUFFICIENT' ||
    fixture.publication_state === 'DATA_INSUFFICIENT' ||
    fixture.data_availability === 'DATA_INSUFFICIENT'
  ) {
    return 'Not enough reliable data';
  }
  return 'No analysis published';
}

export function lifecycleLabel(value: string): string {
  return value
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
}

export function lifecycleTone(
  value: string,
): 'primary' | 'positive' | 'warning' | 'negative' {
  const normalized = value.toUpperCase();
  if (normalized === 'FINISHED' || normalized === 'AWARDED') return 'positive';
  if (normalized === 'POSTPONED' || normalized === 'ABANDONED')
    return 'warning';
  if (normalized === 'CANCELLED') return 'negative';
  return 'primary';
}

export function formatKickoff(value: string, timezone: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Kickoff unavailable';
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: timezone,
  }).format(parsed);
}

export function TodayFixtureCard({
  fixture,
  timezone,
}: {
  fixture: PublicFixtureSummary;
  timezone: string;
}) {
  const label = `${fixture.home_team.name} versus ${fixture.away_team.name}, ${formatKickoff(fixture.kickoff, timezone)}`;
  return (
    <Link
      href={{
        pathname: '/match/[id]',
        params: { id: String(fixture.match_id) },
      }}
      asChild
    >
      <Pressable
        accessibilityLabel={label}
        accessibilityRole="button"
        style={styles.card}
      >
        <View style={sharedStyles.rowBetween}>
          <Text style={styles.competition}>{fixture.competition}</Text>
          <Text style={styles.kickoff}>
            {formatKickoff(fixture.kickoff, timezone)}
          </Text>
        </View>
        <View
          accessibilityLabel={`${fixture.home_team.name}, ${fixture.away_team.name}`}
        >
          <Text style={styles.team}>{fixture.home_team.name}</Text>
          <Text style={styles.team}>{fixture.away_team.name}</Text>
        </View>
        <View style={sharedStyles.rowBetween}>
          <Badge
            label={lifecycleLabel(fixture.fixture_status)}
            tone={lifecycleTone(fixture.fixture_status)}
          />
          <Text style={styles.analysis}>{fixtureAnalysisLabel(fixture)}</Text>
        </View>
      </Pressable>
    </Link>
  );
}

export function ExplorePredictionCard({
  prediction,
}: {
  prediction: PublicPrediction;
}) {
  const { t } = useLanguage();
  const score = prediction.bet_score;
  return (
    <Link
      href={{
        pathname: '/match/[id]',
        params: { id: String(prediction.match_id) },
      }}
      asChild
    >
      <Pressable
        accessibilityLabel={`${prediction.selection} published analysis`}
        accessibilityRole="button"
        style={styles.card}
      >
        <View style={sharedStyles.rowBetween}>
          <Text style={styles.competition}>{t('Published analysis')}</Text>
          <Badge
            label={prediction.policy_decision.replaceAll('_', ' ')}
            tone="accent"
          />
        </View>
        <Text style={styles.featured}>
          {prediction.selection.replaceAll('_', ' ')}
        </Text>
        <Text style={styles.market}>
          {prediction.market.replaceAll('_', ' ')}
        </Text>
        <View style={styles.metrics}>
          <View style={styles.metricBlock}>
            <Text style={styles.meta}>BET SCORE</Text>
            <Text style={styles.metric}>{score ?? 'Score unavailable'}</Text>
          </View>
          <View style={styles.metricBlock}>
            <Text style={styles.meta}>EDGE</Text>
            <Text style={styles.metric}>{prediction.edge}</Text>
          </View>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  card: {
    ...sharedStyles.card,
    minHeight: touchTarget,
  },
  competition: {
    color: colors.textSecondary,
    flexShrink: 1,
    ...typography.competition,
  },
  kickoff: { color: colors.secondary, ...typography.metric },
  team: { color: colors.text, flexShrink: 1, ...typography.teamName },
  analysis: {
    color: colors.textSecondary,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.metadata,
  },
  featured: { color: colors.text, ...typography.featured },
  market: { color: colors.textSecondary, ...typography.body },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.lg },
  metricBlock: { flexGrow: 1, gap: spacing.xs, minWidth: 120 },
  meta: { color: colors.textSecondary, ...typography.caption },
  metric: { color: colors.text, ...typography.metric },
});
