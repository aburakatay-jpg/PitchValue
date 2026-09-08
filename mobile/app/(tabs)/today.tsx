import { MatchCard } from '@/components/MatchCard';
import { AppHeader, EmptyState, Screen, SectionHeader } from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';

export function TodayScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Development preview" title="Today" />
      <SectionHeader
        title="Football programme"
        detail="Synthetic fixtures arranged by kickoff."
      />
      {mockMatches.map((match) => (
        <MatchCard key={match.id} match={match} />
      ))}
      <EmptyState
        title="No strong value found"
        detail="Some slates will be quiet. PitchValue will not force a selection."
      />
    </Screen>
  );
}

export default TodayScreen;
