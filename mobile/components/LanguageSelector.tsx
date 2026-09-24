import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  type LayoutChangeEvent,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SymbolView, type SFSymbol } from 'expo-symbols';

import {
  useLanguage,
  type Language,
} from '@/features/language/LanguageContext';
import {
  colors,
  createThemedStyleSheet,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

const languageOptions: readonly { value: Language; name: string }[] = [
  { value: 'en', name: 'English' },
  { value: 'tr', name: 'Türkçe' },
];

export function LanguageSelector() {
  const { language, setLanguage, t } = useLanguage();
  const [open, setOpen] = useState(false);
  const { height: windowHeight } = useWindowDimensions();
  const [backdropOpacity] = useState(() => new Animated.Value(0));
  const [sheetOffset] = useState(() => new Animated.Value(windowHeight));
  const sheetHeight = useRef(0);
  const opening = useRef(false);
  const closing = useRef(false);
  const selectedName =
    languageOptions.find((option) => option.value === language)?.name ?? '';
  const closeLabel = t('Close language selector');

  useEffect(
    () => () => {
      backdropOpacity.stopAnimation();
      sheetOffset.stopAnimation();
    },
    [backdropOpacity, sheetOffset],
  );

  const openSelector = () => {
    backdropOpacity.setValue(0);
    sheetOffset.setValue(windowHeight);
    opening.current = true;
    closing.current = false;
    setOpen(true);
    Animated.timing(backdropOpacity, {
      toValue: 1,
      duration: 180,
      useNativeDriver: true,
    }).start();
  };

  const onSheetLayout = (event: LayoutChangeEvent) => {
    sheetHeight.current = event.nativeEvent.layout.height;
    if (!opening.current || sheetHeight.current <= 0) return;
    opening.current = false;
    sheetOffset.setValue(sheetHeight.current);
    Animated.timing(sheetOffset, {
      toValue: 0,
      duration: 240,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  };

  const closeSelector = () => {
    if (closing.current || !open) return;
    closing.current = true;
    opening.current = false;
    Animated.parallel([
      Animated.timing(backdropOpacity, {
        toValue: 0,
        duration: 160,
        useNativeDriver: true,
      }),
      Animated.timing(sheetOffset, {
        toValue: sheetHeight.current || windowHeight,
        duration: 180,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start(({ finished }) => {
      if (finished) setOpen(false);
      closing.current = false;
    });
  };

  return (
    <>
      <Pressable
        accessibilityLabel={`${t('Language')}: ${selectedName}`}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={openSelector}
        style={({ pressed }) => [styles.row, pressed && styles.pressed]}
        testID="profile-language-row"
      >
        <Text style={styles.label}>{t('Language')}</Text>
        <View style={styles.valueArea}>
          <Text style={styles.value} testID="profile-language-value">
            {selectedName}
          </Text>
          <SymbolView
            accessibilityElementsHidden
            name={'chevron.right' as SFSymbol}
            size={15}
            tintColor={colors.textSecondary}
          />
        </View>
      </Pressable>

      <Modal
        animationType="none"
        onRequestClose={closeSelector}
        transparent
        visible={open}
      >
        <View style={styles.modalRoot} testID="language-selector-modal">
          <Animated.View
            pointerEvents="box-none"
            style={[styles.backdrop, { opacity: backdropOpacity }]}
            testID="language-selector-backdrop-motion"
          >
            <Pressable
              accessible={false}
              focusable={false}
              onPress={closeSelector}
              style={styles.backdropHitArea}
              testID="language-selector-backdrop"
            />
          </Animated.View>
          <Animated.View
            onLayout={onSheetLayout}
            style={[
              styles.sheetMotion,
              { transform: [{ translateY: sheetOffset }] },
            ]}
            testID="language-selector-sheet-motion"
          >
            <SafeAreaView edges={['bottom']} style={styles.sheet}>
              <View style={styles.sheetHeader}>
                <Text accessibilityRole="header" style={styles.sheetTitle}>
                  {t('Language')}
                </Text>
                <Pressable
                  accessibilityLabel={closeLabel}
                  accessibilityRole="button"
                  onPress={closeSelector}
                  style={styles.closeButton}
                  testID="language-selector-close"
                >
                  <SymbolView
                    accessibilityElementsHidden
                    name={'xmark' as SFSymbol}
                    size={18}
                    tintColor={colors.text}
                  />
                </Pressable>
              </View>
              <ScrollView contentContainerStyle={styles.options}>
                {languageOptions.map((option) => {
                  const selected = language === option.value;
                  return (
                    <Pressable
                      accessibilityLabel={option.name}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: selected }}
                      key={option.value}
                      onPress={() => {
                        setLanguage(option.value);
                        closeSelector();
                      }}
                      style={({ pressed }) => [
                        styles.option,
                        pressed && styles.pressed,
                      ]}
                      testID={`language-option-${option.value}`}
                    >
                      <Text style={styles.optionText}>{option.name}</Text>
                      {selected ? (
                        <SymbolView
                          accessibilityElementsHidden
                          name={'checkmark' as SFSymbol}
                          size={18}
                          tintColor={colors.interactiveTextAccent}
                          testID={`language-selected-${option.value}`}
                        />
                      ) : null}
                    </Pressable>
                  );
                })}
              </ScrollView>
            </SafeAreaView>
          </Animated.View>
        </View>
      </Modal>
    </>
  );
}

const styles = createThemedStyleSheet({
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingVertical: spacing.sm,
  },
  label: {
    color: colors.text,
    flexShrink: 1,
    ...typography.body,
    fontWeight: '700',
  },
  valueArea: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: spacing.xs,
  },
  value: {
    color: colors.interactiveTextAccent,
    flexShrink: 1,
    textAlign: 'right',
    ...typography.body,
  },
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  backdrop: {
    backgroundColor: colors.overlay,
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  backdropHitArea: { flex: 1 },
  sheetMotion: { maxHeight: '78%' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    paddingTop: spacing.md,
  },
  sheetHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
  },
  sheetTitle: { color: colors.text, ...typography.sectionTitle },
  closeButton: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touchTarget,
    minWidth: touchTarget,
  },
  options: { padding: spacing.md, paddingTop: spacing.sm },
  option: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  optionText: { color: colors.text, flex: 1, ...typography.body },
  pressed: { opacity: 0.8 },
});
