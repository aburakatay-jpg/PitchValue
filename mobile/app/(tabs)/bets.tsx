import { useRouter, type Href } from 'expo-router';
import { View, Text } from 'react-native';

import { AppHeader, Screen, Button } from '@/components/ui';
import { MyBetsView } from '@/components/MyBets';
import { useProductSession } from '@/features/session/ProductSessionContext';
import { useLanguage } from '@/features/language/LanguageContext';
import { colors, spacing } from '@/theme/tokens';

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
  const router = useRouter();
  const { t } = useLanguage();

  if (session.state === 'UNVERIFIED') {
    return (
      <Screen>
        <AppHeader title={t('My Bets')} />
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.md, gap: spacing.md }}>
          <Text style={{ color: colors.text, textAlign: 'center' }}>
            {t('Please verify your email address to view and track your bets.')}
          </Text>
          <Button onPress={() => router.push('/auth/email' as Href)}>
            {t('Verify Email')}
          </Button>
        </View>
      </Screen>
    );
  }

  return <BetsScreen accessToken={session.state === 'AUTHENTICATED' ? session.accessToken : null} />;
}

export default ConnectedBetsScreen;
