import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, sharedStyles } from '@/components/ui';
import { colors, spacing, touchTarget, typeScale } from '@/theme/tokens';

export type FixtureCardModel = Readonly<{
  id: string;
  homeTeam: string;
  awayTeam: string;
  kickoff: string;
  competition: string;
  quality: 'Elite' | 'Strong' | 'Value';
  locked: boolean;
}>;

export function MatchCard({ match }: { match: FixtureCardModel }) {
  return (
    <Link href={{ pathname: '/match/[id]', params: { id: match.id } }} asChild>
      <Pressable
        accessibilityLabel={`Open ${match.homeTeam} versus ${match.awayTeam}`}
        accessibilityRole="button"
        style={styles.card}
      >
        <View style={sharedStyles.rowBetween}>
          <Text style={styles.competition}>{match.competition}</Text>
          <Text style={styles.kickoff}>{match.kickoff}</Text>
        </View>
        <Text style={styles.teams}>{match.homeTeam}</Text>
        <Text style={styles.teams}>{match.awayTeam}</Text>
        <View style={sharedStyles.rowBetween}>
          <Badge
            label={match.quality}
            tone={match.quality === 'Value' ? 'accent' : 'primary'}
          />
          <Text style={styles.state}>
            {match.locked ? 'Premium insight locked' : 'Preview available'}
          </Text>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  card: { ...sharedStyles.card, minHeight: touchTarget, gap: spacing.sm },
  competition: { color: colors.textSecondary, fontSize: typeScale.caption },
  kickoff: {
    color: colors.secondary,
    fontSize: typeScale.body,
    fontWeight: '800',
  },
  teams: { color: colors.text, fontSize: typeScale.title, fontWeight: '700' },
  state: {
    color: colors.textSecondary,
    flexShrink: 1,
    fontSize: typeScale.caption,
    textAlign: 'right',
  },
});
