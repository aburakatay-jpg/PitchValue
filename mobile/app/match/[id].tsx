import { useCallback } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { InlineNotice, MatchDetailSkeleton } from '@/components/feedback';
import {
  AllMarkets,
  FinalCheckSection,
  FreshnessSection,
  MatchHeader,
  PublicAnalysisSection,
  StatisticsSection,
} from '@/components/match-detail';
import {
  Screen,
  SectionHeader,
  UnavailableState,
  sharedStyles,
  stackScreenEdges,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { usePublicResource } from '@/hooks/use-public-resource';
import { config } from '@/lib/config';
import { getMatchDetail, type PublicApiError } from '@/lib/public-api';
import { colors, typography } from '@/theme/tokens';
import type { MatchDetailResponse } from '@/types/public-api';

export function parseCanonicalMatchId(
  value: string | readonly string[] | undefined,
): number | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (typeof candidate !== 'string' || !/^[1-9]\d*$/.test(candidate)) {
    return null;
  }
  const parsed = Number(candidate);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

export function MatchDetailView({
  data,
  error,
  initialLoading,
  onRefresh,
  refreshing,
}: {
  data: MatchDetailResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (initialLoading && data === null) {
    return (
      <Screen safeAreaEdges={stackScreenEdges}>
        <MatchDetailSkeleton />
      </Screen>
    );
  }
  if (!data && error) {
    const missing = error.kind === 'NOT_FOUND';
    return (
      <Screen safeAreaEdges={stackScreenEdges}>
        <UnavailableState
          title={
            missing
              ? 'Match not found'
              : 'Match data is temporarily unavailable'
          }
          detail={
            missing
              ? 'This match is not available.'
              : 'Please try again shortly.'
          }
          retry={missing ? undefined : onRefresh}
        />
      </Screen>
    );
  }
  if (!data) return <InvalidMatchState />;
  return (
    <Screen
      onRefresh={onRefresh}
      refreshing={refreshing}
      safeAreaEdges={stackScreenEdges}
    >
      {error ? (
        <InlineNotice
          title="Could not refresh match detail"
          detail="Showing the last available public match data."
          tone="negative"
        />
      ) : null}
      <MatchHeader detail={data} />
      <PublicAnalysisSection detail={data} />
      <AllMarkets markets={data.markets} />
      <FinalCheckSection state={data.final_check} />
      <StatisticsSection detail={data} />
      <FreshnessSection detail={data} />
    </Screen>
  );
}

function InvalidMatchState() {
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <UnavailableState
        title="Match not found"
        detail="A valid match is required."
      />
    </Screen>
  );
}

function ProductionMatchDetail({ matchId }: { matchId: number }) {
  const loader = useCallback(
    (signal: AbortSignal) => getMatchDetail(matchId, signal),
    [matchId],
  );
  const resource = usePublicResource(loader);
  return (
    <MatchDetailView {...resource} onRefresh={() => void resource.refresh()} />
  );
}

function DevelopmentMatchDetail({ id }: { id: string }) {
  const match = mockMatches.find((item) => item.id === id);
  if (!match) return <InvalidMatchState />;
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <View style={sharedStyles.card}>
        <SectionHeader
          title={`${match.homeTeam} vs ${match.awayTeam}`}
          detail={`Development preview · ${match.competition} · ${match.kickoff}`}
        />
        <Text style={styles.preview}>
          Synthetic fixture preview. No public analysis is attached.
        </Text>
      </View>
    </Screen>
  );
}

export default function MatchDetailScreen() {
  const { id } = useLocalSearchParams<{ id?: string | string[] }>();
  const matchId = parseCanonicalMatchId(id);
  if (config.developmentPreviewEnabled && typeof id === 'string') {
    return <DevelopmentMatchDetail id={id} />;
  }
  if (matchId === null) return <InvalidMatchState />;
  return <ProductionMatchDetail matchId={matchId} />;
}

const styles = StyleSheet.create({
  preview: { color: colors.textSecondary, ...typography.body },
});
