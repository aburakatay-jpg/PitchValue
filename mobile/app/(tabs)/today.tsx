import { TodayFixtureCard } from '@/components/discovery';
import {
  FixtureCardSkeleton,
  InlineNotice,
  StaleIndicator,
} from '@/components/feedback';
import { MatchCard } from '@/components/MatchCard';
import {
  AppHeader,
  EmptyState,
  Screen,
  SectionHeader,
  UnavailableState,
} from '@/components/ui';
import { mockMatches } from '@/dev/mock-data';
import { usePublicResource } from '@/hooks/use-public-resource';
import { config } from '@/lib/config';
import { getTodayFixtures, type PublicApiError } from '@/lib/public-api';
import type {
  PublicFixtureSummary,
  TodayFixturesResponse,
} from '@/types/public-api';

import { useLanguage } from '@/features/language/LanguageContext';

export function chronologicalFixtures(
  fixtures: readonly PublicFixtureSummary[],
): readonly PublicFixtureSummary[] {
  return [...fixtures].sort((left, right) => {
    const kickoffDifference =
      Date.parse(left.kickoff) - Date.parse(right.kickoff);
    return kickoffDifference || left.match_id - right.match_id;
  });
}

function dateLabel(value: string, language: string): string {
  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  const formatted = new Intl.DateTimeFormat(
    language === 'tr' ? 'tr-TR' : 'en-GB',
    {
      day: 'numeric',
      month: 'long',
      weekday: 'long',
    },
  ).format(parsed);
  return language === 'tr'
    ? formatted.toLocaleUpperCase('tr-TR')
    : formatted.toUpperCase();
}

export function TodayView({
  data,
  error,
  initialLoading,
  onRefresh,
  refreshing,
}: {
  data: TodayFixturesResponse | null;
  error: PublicApiError | null;
  initialLoading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const { t, language } = useLanguage();

  if (initialLoading && data === null) {
    return (
      <Screen>
        <AppHeader title={t('Today')} />
        <SectionHeader
          title={t('Football programme')}
          detail={t('Loading today’s fixtures')}
        />
        <FixtureCardSkeleton />
        <FixtureCardSkeleton />
        <FixtureCardSkeleton />
      </Screen>
    );
  }
  if (!data && error) {
    return (
      <Screen>
        <AppHeader title={t('Today')} />
        <UnavailableState
          title={t('Match data is temporarily unavailable')}
          detail={t('Please try again shortly.')}
          retry={onRefresh}
        />
      </Screen>
    );
  }
  const fixtures = chronologicalFixtures(data?.fixtures ?? []);
  return (
    <Screen onRefresh={onRefresh} refreshing={refreshing}>
      <AppHeader
        eyebrow={data ? dateLabel(data.fixture_date, language) : undefined}
        title={t('Today')}
      />
      <SectionHeader
        title={t('Football programme')}
        detail={t('Fixtures are ordered by kickoff.')}
      />
      {error ? (
        <InlineNotice
          title={t('Could not refresh match data')}
          detail={t('Showing the last available fixture list.')}
          tone="negative"
        />
      ) : null}
      {data?.state === 'STALE_FIXTURE_DATA' ||
      fixtures.some((fixture) => fixture.freshness.state === 'STALE') ? (
        <StaleIndicator
          detail={t(
            'Freshness is based on the latest persisted source evidence.',
          )}
        />
      ) : null}
      {data?.state === 'PROVIDER_UNAVAILABLE' && !error ? (
        <InlineNotice
          title={t('Fixture service is currently unavailable')}
          tone="warning"
        />
      ) : null}
      {fixtures.length === 0 && data?.state === 'PROVIDER_UNAVAILABLE' ? (
        <UnavailableState
          title={t('Match data is temporarily unavailable')}
          detail={t('The fixture service could not confirm today’s programme.')}
          retry={onRefresh}
        />
      ) : fixtures.length === 0 ? (
        <EmptyState
          title={t('No matches scheduled')}
          detail={t('There are no fixtures available for this day.')}
        />
      ) : (
        fixtures.map((fixture) => (
          <TodayFixtureCard
            fixture={fixture}
            key={fixture.match_id}
            timezone={data?.timezone ?? 'Europe/Istanbul'}
          />
        ))
      )}
    </Screen>
  );
}

function TodayProductionScreen() {
  const resource = usePublicResource(getTodayFixtures);
  return <TodayView {...resource} onRefresh={() => void resource.refresh()} />;
}

function TodayPreviewScreen() {
  const { t } = useLanguage();
  return (
    <Screen>
      <AppHeader eyebrow={t('Development preview')} title={t('Today')} />
      <SectionHeader
        title={t('Football programme')}
        detail={t('Synthetic fixtures arranged by kickoff.')}
      />
      {mockMatches.map((match) => (
        <MatchCard key={match.id} match={match} />
      ))}
    </Screen>
  );
}

export function TodayScreen() {
  return config.developmentPreviewEnabled ? (
    <TodayPreviewScreen />
  ) : (
    <TodayProductionScreen />
  );
}

export default TodayScreen;
