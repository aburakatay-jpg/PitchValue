import { useEffect, useState } from 'react';
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
import { getSavedSelections, getTrackingPerformance } from '@/lib/product-api';
import type {
  SavedSelection,
  TrackingPerformance,
} from '@/types/product-services';

export const myBetsTabs = ['Active', 'History', 'Performance'] as const;
export type MyBetsTab = (typeof myBetsTabs)[number];
export type MyBetsSectionState =
  'UNAVAILABLE' | 'LOADING' | 'ERROR' | 'EMPTY' | 'READY';

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
        Exclude<MyBetsSectionState, 'LOADING' | 'READY'>,
        { title: string; detail: string }
      >
    >
  >
> = {
  Active: {
    UNAVAILABLE: {
      title: 'Tracked selections unavailable',
      detail: 'Saving tracked selections is not available yet.',
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
      detail: 'Settled tracking history is not available yet.',
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
  accessToken,
  initialTab = 'Active',
  sectionStates = productionMyBetsStates,
}: {
  accessToken?: string | null;
  initialTab?: MyBetsTab;
  sectionStates?: Readonly<Record<MyBetsTab, MyBetsSectionState>>;
}) {
  const [selected, setSelected] = useState<MyBetsTab>(initialTab);
  const [remoteState, setRemoteState] = useState<MyBetsSectionState>('LOADING');
  const [records, setRecords] = useState<readonly SavedSelection[]>([]);
  const [metrics, setMetrics] = useState<TrackingPerformance | null>(null);
  useEffect(() => {
    if (accessToken === undefined) return;
    if (accessToken === null) return;
    const controller = new AbortController();
    const load = async () => {
      setRemoteState('LOADING');
      try {
        if (selected === 'Performance') {
          const value = await getTrackingPerformance(
            accessToken,
            controller.signal,
          );
          setMetrics(value);
          setRemoteState(value.tracked === 0 ? 'EMPTY' : 'READY');
        } else {
          const value = await getSavedSelections(
            accessToken,
            selected === 'Active' ? 'active' : 'history',
            controller.signal,
          );
          setRecords(value.records);
          setRemoteState(value.count === 0 ? 'EMPTY' : 'READY');
        }
      } catch {
        if (!controller.signal.aborted) setRemoteState('ERROR');
      }
    };
    void load();
    return () => controller.abort();
  }, [accessToken, selected]);
  const state =
    accessToken === undefined
      ? sectionStates[selected]
      : accessToken === null
        ? 'UNAVAILABLE'
        : remoteState;
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
      <MyBetsSection
        metrics={metrics}
        records={records}
        state={state}
        tab={selected}
      />
    </View>
  );
}

function MyBetsSection({
  tab,
  state,
  records,
  metrics,
}: {
  tab: MyBetsTab;
  state: MyBetsSectionState;
  records: readonly SavedSelection[];
  metrics: TrackingPerformance | null;
}) {
  if (state === 'LOADING') return <MyBetsSkeleton tab={tab} />;
  if (state === 'READY') {
    if (tab === 'Performance' && metrics) {
      return (
        <View style={sharedStyles.card}>
          <SectionHeader title="Track record" />
          <Text style={styles.note}>Tracked: {metrics.tracked}</Text>
          <Text style={styles.note}>Won: {metrics.wins}</Text>
          <Text style={styles.note}>Lost: {metrics.losses}</Text>
          <Text style={styles.note}>Void: {metrics.voids}</Text>
          <Text style={styles.note}>Withdrawn: {metrics.withdrawn}</Text>
          <Text style={styles.note}>
            ROI: {metrics.roi === null ? 'Unavailable' : `${metrics.roi}%`}
          </Text>
        </View>
      );
    }
    return (
      <View style={styles.stack}>
        {records.map((record) => (
          <View key={record.saved_selection_id} style={sharedStyles.card}>
            <Text style={styles.recordTitle}>
              {record.market.replaceAll('_', ' ')} ·{' '}
              {record.selection.replaceAll('_', ' ')}
            </Text>
            <Text style={styles.note}>
              {record.tracking_status}
              {record.outcome ? ` · ${record.outcome}` : ''}
            </Text>
          </View>
        ))}
      </View>
    );
  }
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
    paddingVertical: spacing.sm,
  },
  tabSelected: { backgroundColor: colors.primary },
  tabText: {
    color: colors.textSecondary,
    textAlign: 'center',
    ...typography.caption,
  },
  tabTextSelected: { color: colors.text },
  note: { color: colors.textSecondary, ...typography.caption },
  recordTitle: { color: colors.text, ...typography.body, fontWeight: '700' },
  skeleton: { gap: spacing.md },
});
