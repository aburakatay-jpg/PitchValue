import { View } from 'react-native';

import { InlineNotice } from '@/components/feedback';
import { useLanguage } from '@/features/language/LanguageContext';
import { createThemedStyleSheet, colors, spacing } from '@/theme/tokens';

export function PushDisabledNotice() {
  const { t } = useLanguage();
  return (
    <View style={styles.container}>
      <InlineNotice
        title={t('Notifications are disabled')}
        detail={t(
          'Enable notifications in app settings to receive match updates.',
        )}
        tone="warning"
      />
    </View>
  );
}

const styles = createThemedStyleSheet({
  container: { padding: spacing.md, backgroundColor: colors.background },
});
