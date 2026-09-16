import { AppHeader, Screen } from '@/components/ui';
import { MyBetsView } from '@/components/MyBets';
import { useProductSession } from '@/features/session/ProductSessionContext';

export function BetsScreen({
  accessToken,
}: {
  accessToken?: string | null;
} = {}) {
  return (
    <Screen>
      <AppHeader eyebrow="Personal workspace" title="My Bets" />
      <MyBetsView {...(accessToken === undefined ? {} : { accessToken })} />
    </Screen>
  );
}

function ConnectedBetsScreen() {
  const session = useProductSession();
  return <BetsScreen accessToken={session.accessToken} />;
}

export default ConnectedBetsScreen;
