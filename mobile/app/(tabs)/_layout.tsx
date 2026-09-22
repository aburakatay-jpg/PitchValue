import { Tabs } from 'expo-router';
import { View } from 'react-native';
import { SymbolView, SFSymbol } from 'expo-symbols';

import { tabRoutes } from '@/lib/routes';
import {
  colors,
  touchTarget,
  typeScale,
  createThemedStyleSheet,
} from '@/theme/tokens';
import { useLanguage } from '@/features/language/LanguageContext';

const tabIconNames: Record<string, SFSymbol> = {
  Today: 'calendar',
  Explore: 'magnifyingglass',
  PvE: 'sparkles',
  'My Bets': 'list.clipboard',
  Profile: 'person.crop.circle',
};

function TabIcon({ name, focused }: { name: SFSymbol; focused: boolean }) {
  return (
    <View style={styles.iconContainer}>
      <SymbolView
        name={name}
        tintColor={
          focused ? colors.interactiveTextAccent : colors.textSecondary
        }
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
        tabBarActiveTintColor: colors.interactiveTextAccent,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarStyle: {
          backgroundColor: colors.tabBarBackground,
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

const styles = createThemedStyleSheet({
  iconContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    height: 32,
  },
});
