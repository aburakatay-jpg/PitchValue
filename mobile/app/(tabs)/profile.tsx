import { StyleSheet, Text, View } from 'react-native';

import {
  AppHeader,
  Screen,
  SectionHeader,
  sharedStyles,
} from '@/components/ui';
import { colors, radii, spacing, touchTarget, typeScale } from '@/theme/tokens';

const categories = [
  'Account',
  'Subscription',
  'Preferences',
  'Track Record',
  'Responsible Gaming',
  'App',
] as const;

export default function ProfileScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Guest profile" title="Profile" />
      <SectionHeader
        title="Settings"
        detail="Open a category as features become available."
      />
      <View style={styles.list}>
        {categories.map((category) => (
          <View
            accessibilityLabel={`${category} settings placeholder`}
            key={category}
            style={[sharedStyles.rowBetween, styles.row]}
          >
            <Text style={styles.label}>{category}</Text>
            <Text style={styles.chevron}>›</Text>
          </View>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
  },
  row: {
    minHeight: touchTarget + 8,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  label: { color: colors.text, fontSize: typeScale.body, fontWeight: '600' },
  chevron: { color: colors.textSecondary, fontSize: typeScale.title },
});
