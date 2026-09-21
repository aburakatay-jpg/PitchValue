import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import {
  createThemedStyleSheet,
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

import { lifecycleLabel, lifecycleTone } from '@/components/discovery';
import { InlineNotice, StaleIndicator } from '@/components/feedback';
import { Badge, Button, SectionHeader, sharedStyles } from '@/components/ui';
import { useLanguage } from '@/features/language/LanguageContext';
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

function formatDateTime(value: string, t: (k: string) => string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t('Time unavailable');
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
  const { t } = useLanguage();
  return (
    <View style={styles.headerCard}>
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.competition}>{detail.competition}</Text>
        <Badge
          label={t(lifecycleLabel(detail.fixture_status))}
          tone={lifecycleTone(detail.fixture_status)}
        />
      </View>
      <Text style={styles.kickoff}>{formatDateTime(detail.kickoff, t)}</Text>
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
  const { t } = useLanguage();
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
          label={t('BET SCORE')}
          value={
            prediction.bet_score === null
              ? t('Score unavailable')
              : `${prediction.bet_score} / 100`
          }
        />
        <AnalysisMetric label={t('PROBABILITY EDGE')} value={prediction.edge} />
      </View>
      <Text style={styles.explainer}>
        {t('Bet Score is a PitchValue quality score, not win probability.')}
      </Text>
      <View style={styles.probabilities}>
        <Text style={styles.metadata}>
          {t('Model probability')} {prediction.model_probability}
        </Text>
        <Text style={styles.metadata}>
          {t('Market probability')} {prediction.no_vig_market_probability}
        </Text>
      </View>
      <Text style={styles.explainer}>
        {t(
          'Edge is the server-provided probability difference, not expected profit.',
        )}
      </Text>
      {onSave ? (
        <Button onPress={() => onSave(prediction)} variant="secondary">
          {t('Save to My Bets')}
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
  const { t } = useLanguage();
  if (
    detail.public_analysis === 'DATA_INSUFFICIENT' ||
    detail.publication_state === 'DATA_INSUFFICIENT'
  ) {
    return (
      <View style={sharedStyles.card}>
        <SectionHeader
          title={t('Not enough reliable data')}
          detail={t(
            'PitchValue does not publish analysis when the available evidence is insufficient.',
          )}
        />
      </View>
    );
  }
  if (detail.public_predictions.length === 0) {
    return (
      <View style={sharedStyles.card}>
        <SectionHeader
          title={t('No analysis published')}
          detail={t(
            'This fixture remains available even when no analysis meets publication criteria.',
          )}
        />
      </View>
    );
  }
  return (
    <View style={styles.sectionCard}>
      <SectionHeader
        title={t('Current public analysis')}
        detail={`${detail.public_predictions.length} ${detail.public_predictions.length === 1 ? t('published selection') : t('published selections')}`}
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
  const { t } = useLanguage();
  const score = market.score;
  return (
    <View
      accessibilityLabel={`${market.market}: ${t(marketStateCopy[market.state])}`}
      style={styles.marketRow}
    >
      <View style={styles.flexible}>
        <Text style={styles.marketName}>{market.market}</Text>
        <Text style={styles.marketState}>
          {t(marketStateCopy[market.state])}
        </Text>
      </View>
      {score !== null ? (
        <View style={styles.marketScore}>
          <Text style={styles.metricLabel}>{t('SCORE')}</Text>
          <Text style={styles.metricValue}>{score}</Text>
        </View>
      ) : market.state === 'SCORE_INCOMPLETE' ? (
        <Text style={styles.marketUnavailable}>{t('Score unavailable')}</Text>
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
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(initiallyExpanded);
  return (
    <View style={styles.marketGroup}>
      <Pressable
        accessibilityLabel={`${t(definition.title)} markets`}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((value) => !value)}
        style={styles.marketGroupButton}
      >
        <Text style={styles.marketGroupTitle}>{t(definition.title)}</Text>
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
  const { t } = useLanguage();
  return (
    <View style={styles.sectionCard}>
      <SectionHeader
        title={t('All markets')}
        detail={t('Availability reflects the current public analysis state.')}
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
  const { t } = useLanguage();
  const content = finalCheckContent[state];
  return (
    <View
      accessibilityLabel={t(content.title)}
      accessibilityLiveRegion="polite"
      style={sharedStyles.card}
    >
      <View style={sharedStyles.rowBetween}>
        <Text style={styles.sectionTitle}>{t('Final Check')}</Text>
        <Badge label={t(content.title)} tone={content.tone} />
      </View>
      <Text style={styles.body}>{t(content.detail)}</Text>
    </View>
  );
}

type StatisticRow = Readonly<{
  label: string;
  home: number | string | null;
  away: number | string | null;
}>;

export function StatisticsSection({ detail }: { detail: MatchDetailResponse }) {
  const { t } = useLanguage();
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
        title={t('Match statistics')}
        detail={t('Persisted match evidence')}
      />
      {statistics.map((item) => (
        <View key={item.label} style={styles.statRow}>
          <Text style={styles.statValue}>{item.home ?? t('Unavailable')}</Text>
          <Text style={styles.statLabel}>{t(item.label)}</Text>
          <Text style={styles.statValue}>{item.away ?? t('Unavailable')}</Text>
        </View>
      ))}
    </View>
  );
}

export function FreshnessSection({ detail }: { detail: MatchDetailResponse }) {
  const { t } = useLanguage();
  const timestamp =
    detail.freshness.source_last_seen_at ?? detail.freshness.fixture_refresh_at;
  const timestampDetail = timestamp
    ? `${t('Source evidence')}: ${formatDateTime(timestamp, t)}`
    : undefined;
  if (detail.freshness.state === 'STALE')
    return <StaleIndicator detail={timestampDetail} />;
  if (detail.freshness.state === 'FAILED') {
    return (
      <InlineNotice
        title={t('Fixture refresh failed')}
        detail={timestampDetail}
        tone="warning"
      />
    );
  }
  if (detail.freshness.state === 'UNAVAILABLE') {
    return (
      <View style={sharedStyles.card}>
        <Text style={styles.metadata}>
          {t('Freshness information unavailable')}
        </Text>
      </View>
    );
  }
  return timestampDetail ? (
    <Text style={styles.freshness}>{timestampDetail}</Text>
  ) : null;
}

const styles = createThemedStyleSheet({
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
