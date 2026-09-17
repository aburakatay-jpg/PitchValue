import { Tabs } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { SymbolView, SFSymbol } from 'expo-symbols';

import { tabRoutes } from '@/lib/routes';
import { colors, touchTarget, typeScale } from '@/theme/tokens';
import { useLanguage } from '@/features/language/LanguageContext';

const tabIconNames: Record<string, SFSymbol> = {
  Today: 'calendar',
  Explore: 'magnifyingglass',
  AI: 'sparkles',
  'My Bets': 'list.clipboard',
};

function TabIcon({ name, focused }: { name: SFSymbol; focused: boolean }) {
  return (
    <View style={styles.iconContainer}>
      <SymbolView
        name={name}
        tintColor={focused ? colors.secondary : colors.textSecondary}
        size={24}
      />
    </View>
  );
}

export default function TabLayout() {
  const { t } = useLanguage();
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
            title: t(route.title),
            tabBarIcon: ({ focused }) => (
              <TabIcon
                name={tabIconNames[route.title] || 'square'}
                focused={focused}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  iconContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    height: 32,
  },
});
