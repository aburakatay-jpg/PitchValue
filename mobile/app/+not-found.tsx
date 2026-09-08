import { Link, Stack } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing, typeScale } from '@/theme/tokens';

export default function NotFoundScreen() {
  return (
    <View style={styles.container}>
      <Stack.Screen options={{ title: 'Not found' }} />
      <Text style={styles.title}>This screen does not exist.</Text>
      <Link href="/(tabs)/today" style={styles.link}>
        Return to Today
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.background,
    gap: spacing.md,
    padding: spacing.lg,
  },
  title: { color: colors.text, fontSize: typeScale.title, fontWeight: '700' },
  link: {
    color: colors.secondary,
    fontSize: typeScale.body,
    padding: spacing.md,
  },
});
