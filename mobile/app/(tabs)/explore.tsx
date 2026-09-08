import { View } from 'react-native';

import { MatchCard } from '@/components/MatchCard';
import {
  AppHeader,
  Chip,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';

export default function ExploreScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Synthetic selections" title="Explore" />
      <SectionHeader
        title="PitchValue selections"
        detail="Filter controls are visual placeholders for a later data source."
      />
      <View style={sharedStyles.row}>
        {['All', 'Elite', 'Strong', 'Value'].map((filter, index) => (
          <Chip key={filter} label={filter} selected={index === 0} />
        ))}
      </View>
      {mockMatches.map((match) => (
        <MatchCard key={match.id} match={match} />
      ))}
    </Screen>
  );
}
