import { ExplorePredictionCard } from '@/components/discovery';
import { InlineNotice, PredictionCardSkeleton } from '@/components/feedback';
import { MatchCard } from '@/components/MatchCard';
import {
  AppHeader,
  EmptyState,
  Screen,
  SectionHeader,
  UnavailableState,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { usePublicResource } from '@/hooks/use-public-resource';
import { config } from '@/lib/config';
import { getExplorePredictions, type PublicApiError } from '@/lib/public-api';
import type { PredictionListResponse } from '@/types/public-api';

import { useLanguage } from '@/features/language/LanguageContext';

export function ExploreView({
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

  if (initialLoading && data === null) {
    return (
      <Screen>
        <AppHeader title={t('Explore')} />
        <SectionHeader
          title={t('Published analysis')}
          detail={t('Loading value signals')}
        />
        <PredictionCardSkeleton />
        <PredictionCardSkeleton />
      </Screen>
    );
  }
  if (!data && error) {
    return (
      <Screen>
        <AppHeader title={t('Explore')} />
        <UnavailableState
          title={t('Unable to load value signals')}
          detail={t('Please try again shortly.')}
          retry={onRefresh}
        />
      </Screen>
    );
  }
  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <AppHeader title={t('Explore')} />
      <SectionHeader
        title={t('Published analysis')}
        detail={t(
          'Only analyses that meet PitchValue publication criteria appear here.',
        )}
      />
      {error ? (
        <InlineNotice
          title={t('Could not refresh value signals')}
          detail={t('Showing the last available published analyses.')}
          tone="negative"
        />
      ) : null}
      {(data?.predictions.length ?? 0) === 0 ? (
        <EmptyState
          title={t('No publishable signals right now')}
          detail={t(
            'PitchValue only surfaces analyses that meet its publication criteria.',
          )}
        />
      ) : (
        data?.predictions.map((prediction, index) => (
          <ExplorePredictionCard
            key={`${prediction.match_id}-${prediction.market}-${prediction.selection}-${index}`}
            prediction={prediction}
          />
        ))
      )}
    </Screen>
  );
}

function ExploreProductionScreen() {
  const resource = usePublicResource(getExplorePredictions);
  return (
    <ExploreView {...resource} onRefresh={() => void resource.refresh()} />
  );
}

function ExplorePreviewScreen() {
  const { t } = useLanguage();
  return (
    <Screen>
      <AppHeader eyebrow={t('Synthetic selections')} title={t('Explore')} />
      <SectionHeader
        title={t('Development preview')}
        detail={t('Explicit mock mode is enabled.')}
      />
      {mockMatches.map((match) => (
        <MatchCard key={match.id} match={match} />
      ))}
    </Screen>
  );
}

export default function ExploreScreen() {
  return config.developmentPreviewEnabled ? (
    <ExplorePreviewScreen />
  ) : (
    <ExploreProductionScreen />
  );
}
