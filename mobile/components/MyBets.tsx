import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { SkeletonBlock } from '@/components/feedback';
import { SectionHeader, sharedStyles } from '@/components/ui';
import {
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

export const myBetsTabs = ['Active', 'History', 'Performance'] as const;
export type MyBetsTab = (typeof myBetsTabs)[number];
export type MyBetsSectionState = 'UNAVAILABLE' | 'LOADING' | 'ERROR' | 'EMPTY';

export const productionMyBetsStates: Readonly<
  Record<MyBetsTab, MyBetsSectionState>
> = {
  Active: 'UNAVAILABLE',
  History: 'UNAVAILABLE',
  Performance: 'UNAVAILABLE',
};

const sectionCopy: Readonly<
  Record<
    MyBetsTab,
    Readonly<
      Record<
        Exclude<MyBetsSectionState, 'LOADING'>,
        { title: string; detail: string }
      >
    >
  >
> = {
  Active: {
    UNAVAILABLE: {
      title: 'Tracked selections unavailable',
      detail:
        'PitchValue does not yet have an account-backed saved-record service.',
    },
    ERROR: {
      title: 'Unable to load tracked selections',
      detail: 'Previously verified records would remain unchanged.',
    },
    EMPTY: {
      title: 'No tracked selections yet',
      detail:
        'Authoritatively saved analyses will appear here when tracking is available.',
    },
  },
  History: {
    UNAVAILABLE: {
      title: 'History unavailable',
      detail: 'No authoritative user-record settlement service is connected.',
    },
    ERROR: {
      title: 'Unable to load history',
      detail: 'No records are hidden or reclassified by the mobile app.',
    },
    EMPTY: {
      title: 'No settled records yet',
      detail: 'Authoritatively settled tracked records will appear here.',
    },
  },
  Performance: {
    UNAVAILABLE: {
      title: 'Performance unavailable',
      detail:
        'Authoritative stake and return data do not exist, so ROI is not calculated.',
    },
    ERROR: {
      title: 'Performance is temporarily unavailable',
      detail: 'Active and history records can remain independently available.',
    },
    EMPTY: {
      title: 'No performance record yet',
      detail: 'Metrics require authoritative settled tracking records.',
    },
  },
};

export function MyBetsView({
  initialTab = 'Active',
  sectionStates = productionMyBetsStates,
}: {
  initialTab?: MyBetsTab;
  sectionStates?: Readonly<Record<MyBetsTab, MyBetsSectionState>>;
}) {
  const [selected, setSelected] = useState<MyBetsTab>(initialTab);
  return (
    <View style={styles.stack}>
      <View accessibilityRole="tablist" style={styles.tabs}>
        {myBetsTabs.map((tab) => (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected: selected === tab }}
            key={tab}
            onPress={() => setSelected(tab)}
            style={[styles.tab, selected === tab && styles.tabSelected]}
          >
            <Text
              style={[
                styles.tabText,
                selected === tab && styles.tabTextSelected,
              ]}
            >
              {tab}
            </Text>
          </Pressable>
        ))}
      </View>
      <MyBetsSection state={sectionStates[selected]} tab={selected} />
    </View>
  );
}

function MyBetsSection({
  tab,
  state,
}: {
  tab: MyBetsTab;
  state: MyBetsSectionState;
}) {
  if (state === 'LOADING') return <MyBetsSkeleton tab={tab} />;
  const copy = sectionCopy[tab][state];
  return (
    <View accessibilityLiveRegion="polite" style={sharedStyles.card}>
      <SectionHeader title={copy.title} detail={copy.detail} />
      {tab === 'Performance' ? (
        <Text style={styles.note}>
          No default stake, unit stake, payout, profit, win rate, or financial
          metric is inferred.
        </Text>
      ) : null}
    </View>
  );
}

export function MyBetsSkeleton({ tab }: { tab: MyBetsTab }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.skeleton}
      testID={`my-bets-${tab.toLowerCase()}-skeleton`}
    >
      <SkeletonBlock height={20} width="48%" />
      <SkeletonBlock height={60} />
      <SkeletonBlock height={60} />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: spacing.lg },
  tabs: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    flexDirection: 'row',
    padding: spacing.xs,
  },
  tab: {
    alignItems: 'center',
    borderRadius: radii.sm,
    flex: 1,
    justifyContent: 'center',
    minHeight: touchTarget,
    paddingHorizontal: spacing.xs,
  },
  tabSelected: { backgroundColor: colors.primary },
  tabText: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
  tabTextSelected: { color: colors.text },
  note: { color: colors.textSecondary, ...typography.caption },
  skeleton: { gap: spacing.md },
});
