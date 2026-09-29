import { useCallback, useEffect, useState } from 'react';
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
import { getSavedSelections, saveSelection } from '@/lib/product-api';
import type { SavedSelection } from '@/types/product-services';
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
  personalSelections,
  personalUnavailable,
}: {
  data: MatchDetailResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  onSavePrediction?: ((prediction: PublicPrediction) => void) | undefined;
  saveMessage?: string | null;
  personalSelections?: readonly SavedSelection[] | null | undefined;
  personalUnavailable?: boolean;
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
          title={t(saveMessage)}
          tone={saveMessage === 'Saved to My Bets' ? 'positive' : 'negative'}
        />
      ) : null}
      <MatchHeader detail={data} />
      {personalSelections != null || personalUnavailable ? (
        <View style={sharedStyles.card}>
          <SectionHeader title={t('Saved selection')} />
          {personalUnavailable ? (
            <Text style={styles.preview}>
              {t('Your saved selection is temporarily unavailable')}
            </Text>
          ) : personalSelections?.length ? (
            personalSelections.map((record) => (
              <Text key={record.saved_selection_id} style={styles.preview}>
                {t(record.tracking_status)} ·{' '}
                {t(record.market.replaceAll('_', ' '))} ·{' '}
                {t(record.selection.replaceAll('_', ' '))}
              </Text>
            ))
          ) : (
            <Text style={styles.preview}>{t('No saved selection')}</Text>
          )}
        </View>
      ) : null}
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

export function ProductionMatchDetail({ matchId }: { matchId: number }) {
  const session = useProductSession();
  const personalToken =
    session.state === 'AUTHENTICATED' ? session.accessToken : null;
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [personalResult, setPersonalResult] = useState<{
    token: string;
    matchId: number;
    records: readonly SavedSelection[];
  } | null>(null);
  const [personalUnavailable, setPersonalUnavailable] = useState(false);
  const [personalRevision, setPersonalRevision] = useState(0);
  useEffect(() => {
    if (!personalToken) return;
    const controller = new AbortController();
    const token = personalToken;
    void Promise.all([
      getSavedSelections(token, 'active', controller.signal),
      getSavedSelections(token, 'history', controller.signal),
    ])
      .then(([active, history]) => {
        if (controller.signal.aborted) return;
        setPersonalResult({
          token,
          matchId,
          records: [...active.records, ...history.records].filter(
            (record) => record.match_id === matchId,
          ),
        });
        setPersonalUnavailable(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setPersonalUnavailable(true);
      });
    return () => controller.abort();
  }, [matchId, personalToken, personalRevision]);
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
      setPersonalRevision((value) => value + 1);
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
      personalSelections={
        personalToken &&
        personalResult?.token === personalToken &&
        personalResult.matchId === matchId
          ? personalResult.records
          : null
      }
      personalUnavailable={personalToken ? personalUnavailable : false}
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
