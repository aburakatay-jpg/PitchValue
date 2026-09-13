import { View } from 'react-native';

import { MatchCard } from '@/components/MatchCard';
import {
  AppHeader,
  Chip,
  EmptyState,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { config } from '@/lib/config';

export default function ExploreScreen() {
  return (
    <Screen>
      <AppHeader
        eyebrow={
          config.developmentPreviewEnabled ? 'Synthetic selections' : undefined
        }
        title="Explore"
      />
      <SectionHeader
        title="PitchValue selections"
        detail="Filter controls are visual placeholders for a later data source."
      />
      <View style={sharedStyles.row}>
        {['All', 'Elite', 'Strong', 'Value'].map((filter, index) => (
          <Chip key={filter} label={filter} selected={index === 0} />
        ))}
      </View>
      {config.developmentPreviewEnabled
        ? mockMatches.map((match) => <MatchCard key={match.id} match={match} />)
        : null}
      {!config.developmentPreviewEnabled ? (
        <EmptyState
          title="No published analysis"
          detail="Explore stays empty until publication-safe analysis is available."
        />
      ) : null}
    </Screen>
  );
}
