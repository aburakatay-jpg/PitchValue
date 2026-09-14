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
  if (initialLoading && data === null) {
    return (
      <Screen>
        <AppHeader title="Explore" />
        <SectionHeader
          title="Published analysis"
          detail="Loading value signals"
        />
        <PredictionCardSkeleton />
        <PredictionCardSkeleton />
      </Screen>
    );
  }
  if (!data && error) {
    return (
      <Screen>
        <AppHeader title="Explore" />
        <UnavailableState
          title="Unable to load value signals"
          detail="Please try again shortly."
          retry={onRefresh}
        />
      </Screen>
    );
  }
  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <AppHeader title="Explore" />
      <SectionHeader
        title="Published analysis"
        detail="Only analyses that meet PitchValue publication criteria appear here."
      />
      {error ? (
        <InlineNotice
          title="Could not refresh value signals"
          detail="Showing the last available published analyses."
          tone="negative"
        />
      ) : null}
      {(data?.predictions.length ?? 0) === 0 ? (
        <EmptyState
          title="No publishable signals right now"
          detail="PitchValue only surfaces analyses that meet its publication criteria."
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
  return (
    <Screen>
      <AppHeader eyebrow="Synthetic selections" title="Explore" />
      <SectionHeader
        title="Development preview"
        detail="Explicit mock mode is enabled."
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
