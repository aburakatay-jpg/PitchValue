import { AppHeader, Screen } from '@/components/ui';
import { MyBetsView } from '@/components/MyBets';
import { useProductSession } from '@/features/session/ProductSessionContext';

import { useLanguage } from '@/features/language/LanguageContext';

export function BetsScreen({
  accessToken,
}: {
  accessToken?: string | null;
} = {}) {
  const { t } = useLanguage();
  return (
    <Screen>
      <AppHeader title={t('My Bets')} />
      <MyBetsView {...(accessToken === undefined ? {} : { accessToken })} />
    </Screen>
  );
}

function ConnectedBetsScreen() {
  const session = useProductSession();
  return <BetsScreen accessToken={session.accessToken} />;
}

export default ConnectedBetsScreen;
