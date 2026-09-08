import { StyleSheet, Text, View } from 'react-native';

import { PremiumGuard } from '@/components/PremiumGuard';
import {
  AppHeader,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { aiActions } from '@/dev/mock-data';
import { colors, spacing, typeScale } from '@/theme/tokens';

export function AiScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Premium workspace" title="AI" />
      <SectionHeader
        title="Analysis tools"
        detail="Action shells only. No model is connected."
      />
      <View style={styles.grid}>
        {aiActions.map((action, index) => (
          <View key={action} style={sharedStyles.card}>
            <Text style={styles.number}>0{index + 1}</Text>
            <Text style={sharedStyles.strong}>{action}</Text>
            <Text style={sharedStyles.label}>
              Premium · unavailable in foundation build
            </Text>
          </View>
        ))}
      </View>
      <PremiumGuard>
        <Text style={sharedStyles.body}>Premium AI content placeholder</Text>
      </PremiumGuard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { gap: spacing.md },
  number: {
    color: colors.secondary,
    fontSize: typeScale.caption,
    fontWeight: '800',
  },
});

export default AiScreen;
