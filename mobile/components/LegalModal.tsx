import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SymbolView, type SFSymbol } from 'expo-symbols';

import { useLanguage } from '@/features/language/LanguageContext';
import { getLegalDocument, type LegalDocumentId } from '@/legal/content';
import {
  colors,
  createThemedStyleSheet,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

export function LegalModal({
  documentId,
  onClose,
}: {
  documentId: LegalDocumentId | null;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const document = documentId ? getLegalDocument(documentId) : null;

  return (
    <Modal
      accessibilityViewIsModal
      animationType="slide"
      onRequestClose={onClose}
      presentationStyle="pageSheet"
      transparent={false}
      visible={Boolean(document)}
    >
      {document ? (
        <SafeAreaView style={styles.safeArea} testID="legal-modal">
          <View style={styles.header}>
            <Text
              accessibilityRole="header"
              numberOfLines={3}
              style={styles.title}
              testID="legal-modal-title"
            >
              {document.title}
            </Text>
            <Pressable
              accessibilityLabel={t('Close')}
              accessibilityRole="button"
              onPress={onClose}
              style={({ pressed }) => [
                styles.closeButton,
                pressed && styles.pressed,
              ]}
              testID="legal-modal-close"
            >
              <SymbolView
                accessibilityElementsHidden
                importantForAccessibility="no"
                name={'xmark' as SFSymbol}
                size={18}
                tintColor={colors.text}
              />
            </Pressable>
          </View>
          <ScrollView
            accessibilityLabel={document.title}
            contentContainerStyle={styles.content}
            showsVerticalScrollIndicator
            testID="legal-modal-scroll"
          >
            <Text selectable style={styles.body} testID="legal-modal-content">
              {document.content}
            </Text>
          </ScrollView>
        </SafeAreaView>
      ) : null}
    </Modal>
  );
}

export function LegalTextLink({
  label,
  onPress,
  testID,
}: {
  label: string;
  onPress: () => void;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="link"
      onPress={onPress}
      style={({ pressed }) => [styles.link, pressed && styles.pressed]}
      testID={testID}
    >
      <Text style={styles.linkText}>{label}</Text>
    </Pressable>
  );
}

const styles = createThemedStyleSheet({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  header: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  title: {
    color: colors.text,
    flex: 1,
    ...typography.sectionTitle,
  },
  closeButton: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.pill,
    height: touchTarget,
    justifyContent: 'center',
    width: touchTarget,
  },
  content: { padding: spacing.lg, paddingBottom: spacing.xl },
  body: {
    color: colors.text,
    ...typography.body,
  },
  link: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
    paddingHorizontal: spacing.sm,
  },
  linkText: {
    color: colors.interactiveTextAccent,
    textAlign: 'center',
    ...typography.body,
  },
  pressed: { opacity: 0.76 },
});
