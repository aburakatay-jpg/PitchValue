import { useCallback, useState } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { createThemedStyleSheet, colors, typography } from '@/theme/tokens';
import { Text, View } from 'react-native';
import { useLanguage } from '@/features/language/LanguageContext';

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
import { useProductSession } from '@/features/session/ProductSessionContext';
import { saveSelection } from '@/lib/product-api';
import { getMatchDetail, type PublicApiError } from '@/lib/public-api';
import type { MatchDetailResponse, PublicPrediction } from '@/types/public-api';

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
  onSavePrediction,
  saveMessage,
}: {
  data: MatchDetailResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  onSavePrediction?: ((prediction: PublicPrediction) => void) | undefined;
  saveMessage?: string | null;
}) {
  const { t } = useLanguage();

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
              ? t('Match not found')
              : t('Match data is temporarily unavailable')
          }
          detail={
            missing
              ? t('This match is not available.')
              : t('Please try again shortly.')
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
          title={t('Could not refresh match detail')}
          detail={t('Showing the last available public match data.')}
          tone="negative"
        />
      ) : null}
      {saveMessage ? (
        <InlineNotice
          title={saveMessage}
          tone={saveMessage === 'Saved to My Bets' ? 'positive' : 'negative'}
        />
      ) : null}
      <MatchHeader detail={data} />
      <PublicAnalysisSection detail={data} onSave={onSavePrediction} />
      <AllMarkets markets={data.markets} />
      <FinalCheckSection state={data.final_check} />
      <StatisticsSection detail={data} />
      <FreshnessSection detail={data} />
    </Screen>
  );
}

function InvalidMatchState() {
  const { t } = useLanguage();
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <UnavailableState
        title={t('Match not found')}
        detail={t('A valid match is required.')}
      />
    </Screen>
  );
}

function ProductionMatchDetail({ matchId }: { matchId: number }) {
  const session = useProductSession();
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const loader = useCallback(
    (signal: AbortSignal) => getMatchDetail(matchId, signal),
    [matchId],
  );
  const resource = usePublicResource(loader);
  const save = async (prediction: PublicPrediction) => {
    if (!session.accessToken) return;
    try {
      await saveSelection(
        session.accessToken,
        {
          match_id: prediction.match_id,
          market: prediction.market,
          selection: prediction.selection,
        },
        new AbortController().signal,
      );
      setSaveMessage('Saved to My Bets');
    } catch {
      setSaveMessage('Unable to save this selection');
    }
  };
  return (
    <MatchDetailView
      {...resource}
      onRefresh={() => void resource.refresh()}
      onSavePrediction={
        session.accessToken ? (prediction) => void save(prediction) : undefined
      }
      saveMessage={saveMessage}
    />
  );
}

function DevelopmentMatchDetail({ id }: { id: string }) {
  const match = mockMatches.find((item) => item.id === id);
  const { t } = useLanguage();
  if (!match) return <InvalidMatchState />;
  return (
    <Screen safeAreaEdges={stackScreenEdges}>
      <View style={sharedStyles.card}>
        <SectionHeader
          title={`${match.homeTeam} vs ${match.awayTeam}`}
          detail={`${t('Development preview')} · ${match.competition} · ${match.kickoff}`}
        />
        <Text style={styles.preview}>
          {t('Synthetic fixture preview. No public analysis is attached.')}
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

const styles = createThemedStyleSheet({
  preview: { color: colors.textSecondary, ...typography.body },
});
