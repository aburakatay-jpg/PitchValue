import { Text, View } from 'react-native';

import { PremiumGuard } from '@/components/PremiumGuard';
import {
  AppHeader,
  Chip,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';

export function BetsScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Personal workspace" title="My Bets" />
      <View style={sharedStyles.row}>
        {['Active', 'History', 'Performance'].map((tab, index) => (
          <Chip key={tab} label={tab} selected={index === 0} />
        ))}
      </View>
      <SectionHeader
        title="Your saved picks"
        detail="No performance figures are generated in this foundation."
      />
      <PremiumGuard>
        <Text style={sharedStyles.body}>Premium bet workspace placeholder</Text>
      </PremiumGuard>
    </Screen>
  );
}

export default BetsScreen;
