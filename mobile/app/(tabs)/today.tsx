import { MatchCard } from '@/components/MatchCard';
import { AppHeader, EmptyState, Screen, SectionHeader } from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { config } from '@/lib/config';

export function TodayScreen() {
  return (
    <Screen>
      <AppHeader
        eyebrow={
          config.developmentPreviewEnabled ? 'Development preview' : undefined
        }
        title="Today"
      />
      <SectionHeader
        title="Football programme"
        detail={
          config.developmentPreviewEnabled
            ? 'Synthetic fixtures arranged by kickoff.'
            : 'Fixtures appear chronologically when public data is connected.'
        }
      />
      {config.developmentPreviewEnabled
        ? mockMatches.map((match) => <MatchCard key={match.id} match={match} />)
        : null}
      {!config.developmentPreviewEnabled ? (
        <EmptyState
          title="Fixture data unavailable"
          detail="No synthetic fixtures are used as a production fallback."
        />
      ) : null}
    </Screen>
  );
}

export default TodayScreen;
