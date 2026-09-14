import { AppHeader, Screen } from '@/components/ui';
import { MyBetsView } from '@/components/MyBets';

export function BetsScreen() {
  return (
    <Screen>
      <AppHeader eyebrow="Personal workspace" title="My Bets" />
      <MyBetsView />
    </Screen>
  );
}

export default BetsScreen;
