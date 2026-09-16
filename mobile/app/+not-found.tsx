import { Link, Stack } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { stackScreenEdges } from '@/components/ui';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

export default function NotFoundScreen() {
  return (
    <SafeAreaView edges={stackScreenEdges} style={styles.safe}>
      <Stack.Screen options={{ title: 'Not found' }} />
      <View style={styles.container}>
        <Text accessibilityRole="header" style={styles.title}>
          This screen is unavailable
        </Text>
        <Text style={styles.detail}>
          Return to Today to continue browsing published PitchValue data.
        </Text>
        <Link href="/(tabs)/today" asChild>
          <Pressable
            accessibilityLabel="Return to Today"
            accessibilityRole="button"
            style={styles.action}
          >
            <Text style={styles.actionText}>Return to Today</Text>
          </Pressable>
        </Link>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { backgroundColor: colors.background, flex: 1 },
  container: {
    flex: 1,
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.lg,
  },
  title: { color: colors.text, ...typography.pageTitle },
  detail: { color: colors.textSecondary, ...typography.body },
  action: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: radii.md,
    justifyContent: 'center',
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  actionText: { color: colors.text, ...typography.body, fontWeight: '700' },
});
