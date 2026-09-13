import { Tabs } from 'expo-router';
import { StyleSheet, Text } from 'react-native';

import { tabRoutes } from '@/lib/routes';
import { colors, touchTarget, typeScale } from '@/theme/tokens';

function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <Text
      accessibilityElementsHidden
      style={[styles.icon, focused && styles.iconFocused]}
    >
      {label.slice(0, 1)}
    </Text>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.background },
        tabBarActiveTintColor: colors.secondary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          minHeight: 64,
        },
        tabBarLabelStyle: { fontSize: typeScale.caption, fontWeight: '700' },
        tabBarItemStyle: { minHeight: touchTarget },
      }}
    >
      {tabRoutes.map((route) => (
        <Tabs.Screen
          key={route.name}
          name={route.name}
          options={{
            title: route.title,
            tabBarIcon: ({ focused }) => (
              <TabIcon label={route.title} focused={focused} />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  icon: {
    color: colors.textSecondary,
    fontSize: typeScale.body,
    fontWeight: '800',
  },
  iconFocused: { color: colors.secondary },
});
