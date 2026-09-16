import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { lifecycleLabel, lifecycleTone } from '@/components/discovery';
import { InlineNotice, StaleIndicator } from '@/components/feedback';
import { Badge, Button, SectionHeader, sharedStyles } from '@/components/ui';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';
import type {
  FinalCheckState,
  MatchDetailResponse,
  PublicMarketAvailability,
  PublicMarketState,
  PublicPrediction,
} from '@/types/public-api';

const DISPLAY_TIMEZONE = 'Europe/Istanbul';

type MarketGroupDefinition = Readonly<{
  key: string;
  title: string;
  names: readonly string[];
}>;

export const marketGroups: readonly MarketGroupDefinition[] = [
  { key: 'result', title: 'Match result', names: ['1X2', 'Double Chance'] },
  { key: 'goals', title: 'Match goals', names: ['O/U 1.5', 'O/U 2.5'] },
  { key: 'btts', title: 'Both teams to score', names: ['BTTS'] },
  {
    key: 'home-goals',
    title: 'Home team goals',
    names: ['Home Team Goals O/U 0.5', 'Home Team Goals O/U 1.5'],
  },
  {
    key: 'away-goals',
    title: 'Away team goals',
    names: ['Away Team Goals O/U 0.5', 'Away Team Goals O/U 1.5'],
  },
] as const;

export const marketStateCopy: Readonly<Record<PublicMarketState, string>> = {
  AVAILABLE_PUBLIC: 'Analysis available',
  ANALYSIS_UNAVAILABLE: 'Analysis unavailable',
  DATA_INSUFFICIENT: 'Not enough reliable data',
  SCORE_INCOMPLETE: 'Score unavailable',
  NOT_SUPPORTED: 'Not supported',
  NOT_PUBLISHED: 'Not published',
};

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time unavailable';
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
    timeZone: DISPLAY_TIMEZONE,
    year: 'numeric',
  }).format(date);
}

export function MatchHeader({ detail }: { detail: MatchDetailResponse }) {
  return (
    <View style={styles.headerCard}>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.competition}>{detail.competition}</Text>
        <Badge
          label={lifecycleLabel(detail.fixture_status)}
          tone={lifecycleTone(detail.fixture_status)}
        />
      </View>
      <Text style={styles.kickoff}>{formatDateTime(detail.kickoff)}</Text>
      <View
        accessibilityLabel={`${detail.home_team.name} versus ${detail.away_team.name}`}
        style={styles.teams}
      >
        <Text style={styles.team}>{detail.home_team.name}</Text>
        {detail.score ? (
          <Text
            accessibilityLabel={`Final score ${detail.score.home} to ${detail.score.away}`}
            style={styles.score}
          >
            {detail.score.home} – {detail.score.away}
          </Text>
        ) : null}
        <Text style={styles.team}>{detail.away_team.name}</Text>
      </View>
    </View>
  );
}

function AnalysisMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricBlock}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function PublicPredictionRow({
  prediction,
  onSave,
}: {
  prediction: PublicPrediction;
  onSave?: ((prediction: PublicPrediction) => void) | undefined;
}) {
  return (
    <View style={styles.analysisRow}>
      <View style={sharedStyles.rowBetween}>
        <View style={styles.flexible}>
          <Text style={styles.selection}>
            {prediction.selection.replaceAll('_', ' ')}
          </Text>
          <Text style={styles.metadata}>
            {prediction.market.replaceAll('_', ' ')}
          </Text>
        </View>
        <Badge
          label={prediction.policy_decision.replaceAll('_', ' ')}
          tone="accent"
        />
      </View>
      <View style={styles.metrics}>
        <AnalysisMetric
          label="BET SCORE"
          value={
            prediction.bet_score === null
              ? 'Score unavailable'
              : `${prediction.bet_score} / 100`
          }
        />
        <AnalysisMetric label="PROBABILITY EDGE" value={prediction.edge} />
      </View>
      <Text style={styles.explainer}>
        Bet Score is a PitchValue quality score, not win probability.
      </Text>
      <View style={styles.probabilities}>
        <Text style={styles.metadata}>
          Model probability {prediction.model_probability}
        </Text>
        <Text style={styles.metadata}>
          Market probability {prediction.no_vig_market_probability}
        </Text>
      </View>
      <Text style={styles.explainer}>
        Edge is the server-provided probability difference, not expected profit.
      </Text>
      {onSave ? (
        <Button onPress={() => onSave(prediction)} variant="secondary">
          Save to My Bets
        </Button>
      ) : null}
    </View>
  );
}

export function PublicAnalysisSection({
  detail,
  onSave,
}: {
  detail: MatchDetailResponse;
  onSave?: ((prediction: PublicPrediction) => void) | undefined;
}) {
  if (
    detail.public_analysis === 'DATA_INSUFFICIENT' ||
    detail.publication_state === 'DATA_INSUFFICIENT'
  ) {
    return (
      <View style={sharedStyles.card}>
        <SectionHeader
          title="Not enough reliable data"
          detail="PitchValue does not publish analysis when the available evidence is insufficient."
        />
      </View>
    );
  }
  if (detail.public_predictions.length === 0) {
    return (
      <View style={sharedStyles.card}>
        <SectionHeader
          title="No analysis published"
          detail="This fixture remains available even when no analysis meets publication criteria."
        />
      </View>
    );
  }
  return (
    <View style={styles.sectionCard}>
      <SectionHeader
        title="Current public analysis"
        detail={`${detail.public_predictions.length} published selection${detail.public_predictions.length === 1 ? '' : 's'}`}
      />
      {detail.public_predictions.map((prediction, index) => (
        <PublicPredictionRow
          key={`${prediction.market}-${prediction.selection}-${index}`}
          onSave={onSave}
          prediction={prediction}
        />
      ))}
    </View>
  );
}

export function MarketRow({ market }: { market: PublicMarketAvailability }) {
  const score = market.score;
  return (
    <View
      accessibilityLabel={`${market.market}: ${marketStateCopy[market.state]}`}
      style={styles.marketRow}
    >
      <View style={styles.flexible}>
        <Text style={styles.marketName}>{market.market}</Text>
        <Text style={styles.marketState}>{marketStateCopy[market.state]}</Text>
      </View>
      {score !== null ? (
        <View style={styles.marketScore}>
          <Text style={styles.metricLabel}>SCORE</Text>
          <Text style={styles.metricValue}>{score}</Text>
        </View>
      ) : market.state === 'SCORE_INCOMPLETE' ? (
        <Text style={styles.marketUnavailable}>Score unavailable</Text>
      ) : null}
    </View>
  );
}

function MarketGroup({
  definition,
  markets,
  initiallyExpanded,
}: {
  definition: MarketGroupDefinition;
  markets: readonly PublicMarketAvailability[];
  initiallyExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  return (
    <View style={styles.marketGroup}>
      <Pressable
        accessibilityLabel={`${definition.title} markets`}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((value) => !value)}
        style={styles.marketGroupButton}
      >
        <Text style={styles.marketGroupTitle}>{definition.title}</Text>
        <Text
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={styles.disclosure}
        >
          {expanded ? '−' : '+'}
        </Text>
      </Pressable>
      {expanded
        ? markets.map((market) => (
            <MarketRow key={market.market} market={market} />
          ))
        : null}
    </View>
  );
}

export function AllMarkets({
  markets,
}: {
  markets: readonly PublicMarketAvailability[];
}) {
  return (
    <View style={styles.sectionCard}>
      <SectionHeader
        title="All markets"
        detail="Availability reflects the current public analysis state."
      />
      {marketGroups.map((definition, index) => {
        const grouped = markets.filter((market) =>
          definition.names.includes(market.market),
        );
        return (
          <MarketGroup
            definition={definition}
            initiallyExpanded={index === 0}
            key={definition.key}
            markets={grouped}
          />
        );
      })}
    </View>
  );
}

const finalCheckContent: Readonly<
  Record<
    FinalCheckState,
    {
      title: string;
      detail: string;
      tone: 'positive' | 'warning' | 'negative' | 'primary';
    }
  >
> = {
  CONFIRMED: {
    title: 'Analysis confirmed',
    detail: 'Latest available data still supports the published analysis.',
    tone: 'positive',
  },
  CHANGED: {
    title: 'Analysis changed',
    detail: 'The latest data now supports a different view.',
    tone: 'warning',
  },
  WITHDRAWN: {
    title: 'Analysis withdrawn',
    detail: 'The previous recommendation no longer meets publication criteria.',
    tone: 'negative',
  },
  FINAL_CHECK_UNAVAILABLE: {
    title: 'Final Check unavailable',
    detail: 'The pre-match verification could not be completed.',
    tone: 'primary',
  },
};

export function FinalCheckSection({ state }: { state: FinalCheckState }) {
  const content = finalCheckContent[state];
  return (
    <View
      accessibilityLabel={content.title}
      accessibilityLiveRegion="polite"
      style={sharedStyles.card}
    >
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.sectionTitle}>Final Check</Text>
        <Badge label={content.title} tone={content.tone} />
      </View>
      <Text style={styles.body}>{content.detail}</Text>
    </View>
  );
}

type StatisticRow = Readonly<{
  label: string;
  home: number | string | null;
  away: number | string | null;
}>;

export function StatisticsSection({ detail }: { detail: MatchDetailResponse }) {
  if (detail.statistics === null) return null;
  const statistics: readonly StatisticRow[] = [
    {
      label: 'Shots',
      home: detail.statistics.home_shots,
      away: detail.statistics.away_shots,
    },
    {
      label: 'Shots on target',
      home: detail.statistics.home_shots_on_target,
      away: detail.statistics.away_shots_on_target,
    },
    {
      label: 'Possession',
      home: detail.statistics.home_possession,
      away: detail.statistics.away_possession,
    },
    {
      label: 'Corners',
      home: detail.statistics.home_corners,
      away: detail.statistics.away_corners,
    },
  ].filter((item) => item.home !== null || item.away !== null);
  if (statistics.length === 0) return null;
  return (
    <View style={styles.sectionCard}>
      <SectionHeader
        title="Match statistics"
        detail="Persisted match evidence"
      />
      {statistics.map((item) => (
        <View key={item.label} style={styles.statRow}>
          <Text style={styles.statValue}>{item.home ?? 'Unavailable'}</Text>
          <Text style={styles.statLabel}>{item.label}</Text>
          <Text style={styles.statValue}>{item.away ?? 'Unavailable'}</Text>
        </View>
      ))}
    </View>
  );
}

export function FreshnessSection({ detail }: { detail: MatchDetailResponse }) {
  const timestamp =
    detail.freshness.source_last_seen_at ?? detail.freshness.fixture_refresh_at;
  const timestampDetail = timestamp
    ? `Source evidence: ${formatDateTime(timestamp)}`
    : undefined;
  if (detail.freshness.state === 'STALE')
    return <StaleIndicator detail={timestampDetail} />;
  if (detail.freshness.state === 'FAILED') {
    return (
      <InlineNotice
        title="Fixture refresh failed"
        detail={timestampDetail}
        tone="warning"
      />
    );
  }
  if (detail.freshness.state === 'UNAVAILABLE') {
    return (
      <View style={sharedStyles.card}>
        <Text style={styles.metadata}>Freshness information unavailable</Text>
      </View>
    );
  }
  return timestampDetail ? (
    <Text style={styles.freshness}>{timestampDetail}</Text>
  ) : null;
}

const styles = StyleSheet.create({
  headerCard: { ...sharedStyles.card, gap: spacing.md },
  sectionCard: { ...sharedStyles.card, gap: spacing.md },
  competition: {
    color: colors.textSecondary,
    flexShrink: 1,
    ...typography.competition,
  },
  kickoff: { color: colors.secondary, ...typography.metadata },
  teams: { gap: spacing.sm },
  team: { color: colors.text, flexShrink: 1, ...typography.teamName },
  score: { color: colors.text, ...typography.featured },
  analysisRow: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
    gap: spacing.md,
    paddingTop: spacing.md,
  },
  flexible: { flex: 1, minWidth: 0 },
  selection: { color: colors.text, ...typography.featured },
  metadata: { color: colors.textSecondary, ...typography.metadata },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.lg },
  metricBlock: { flexGrow: 1, gap: spacing.xs, minWidth: 120 },
  metricLabel: { color: colors.textSecondary, ...typography.caption },
  metricValue: { color: colors.text, flexShrink: 1, ...typography.metric },
  probabilities: { gap: spacing.xs },
  explainer: { color: colors.textSecondary, ...typography.caption },
  marketGroup: {
    borderColor: colors.border,
    borderRadius: radii.sm,
    borderWidth: 1,
  },
  marketGroupButton: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  marketGroupTitle: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  disclosure: { color: colors.secondary, ...typography.sectionTitle },
  marketRow: {
    alignItems: 'center',
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    minHeight: touchTarget,
    padding: spacing.md,
  },
  marketName: { color: colors.text, ...typography.body, fontWeight: '600' },
  marketState: { color: colors.textSecondary, ...typography.metadata },
  marketScore: { alignItems: 'flex-end', gap: spacing.xs },
  marketUnavailable: {
    color: colors.warning,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.caption,
  },
  sectionTitle: { color: colors.text, ...typography.sectionTitle },
  body: { color: colors.textSecondary, ...typography.body },
  statRow: { alignItems: 'center', flexDirection: 'row', gap: spacing.sm },
  statValue: {
    color: colors.text,
    flex: 1,
    textAlign: 'center',
    ...typography.metric,
  },
  statLabel: {
    color: colors.textSecondary,
    flex: 2,
    textAlign: 'center',
    ...typography.metadata,
  },
  freshness: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
});
