import type { FixtureCardModel } from '@/components/MatchCard';

export type MockMatch = FixtureCardModel;

// Development-only synthetic fixtures. These are not predictions or live facts.
export const mockMatches: MockMatch[] = [
  {
    id: 'dev-alpha-beta',
    homeTeam: 'Northbridge FC',
    awayTeam: 'Harbor Athletic',
    kickoff: '18:30',
    competition: 'Development League',
    quality: 'Strong',
    locked: false,
  },
  {
    id: 'dev-orchard-riverside',
    homeTeam: 'Orchard United',
    awayTeam: 'Riverside City',
    kickoff: '21:00',
    competition: 'Mock Cup',
    quality: 'Value',
    locked: true,
  },
];

export const aiActions = [
  'Coupon Builder',
  'Today’s Best Value',
  'Explain a Pick',
  'Ask PitchValue',
] as const;
