import { useState } from 'react';
import {
  Keyboard,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { SymbolView, type SFSymbol } from 'expo-symbols';
import {
  createThemedStyleSheet,
  colors,
  radii,
  spacing,
  touchTarget,
  typography,
} from '@/theme/tokens';

import { useLanguage } from '@/features/language/LanguageContext';

export type RegistrationCountry = Readonly<{
  value: 'GB' | 'DE' | 'FR' | 'ES' | 'PT' | 'NL' | 'IT' | 'TR' | 'OTHER';
  apiCode: string | null;
  flag: string;
  icon?: SFSymbol | undefined;
  label: string;
}>;

export const registrationCountries: readonly RegistrationCountry[] = [
  { value: 'GB', apiCode: 'GB', flag: '🇬🇧', label: 'United Kingdom' },
  { value: 'DE', apiCode: 'DE', flag: '🇩🇪', label: 'Germany' },
  { value: 'FR', apiCode: 'FR', flag: '🇫🇷', label: 'France' },
  { value: 'ES', apiCode: 'ES', flag: '🇪🇸', label: 'Spain' },
  { value: 'PT', apiCode: 'PT', flag: '🇵🇹', label: 'Portugal' },
  { value: 'NL', apiCode: 'NL', flag: '🇳🇱', label: 'Netherlands' },
  { value: 'IT', apiCode: 'IT', flag: '🇮🇹', label: 'Italy' },
  { value: 'TR', apiCode: 'TR', flag: '🇹🇷', label: 'Türkiye' },
  {
    value: 'OTHER',
    apiCode: null,
    flag: '',
    icon: 'globe.europe.africa.fill' as SFSymbol,
    label: 'Other',
  },
] as const;

export function CountrySelector({
  selected,
  onSelect,
}: {
  selected: RegistrationCountry | null;
  onSelect: (country: RegistrationCountry) => void;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const selectedLabel = selected
    ? `${selected.flag ? `${selected.flag} ` : ''}${t(selected.label)}`
    : t('Select country');

  return (
    <>
      <Pressable
        accessibilityLabel={`${t('Country')}: ${selectedLabel}`}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => {
          Keyboard.dismiss();
          setOpen(true);
        }}
        style={({ pressed }) => [styles.selector, pressed && styles.pressed]}
        testID="country-selector"
      >
        <View style={styles.selectedValue}>
          {selected?.icon ? (
            <SymbolView
              accessibilityElementsHidden
              name={selected.icon}
              size={19}
              testID="country-selected-icon"
              tintColor={colors.textSecondary}
            />
          ) : null}
          <Text style={selected ? styles.selectorValue : styles.placeholder}>
            {selectedLabel}
          </Text>
        </View>
        <SymbolView
          name={'chevron.down' as SFSymbol}
          size={16}
          tintColor={colors.textSecondary}
        />
      </Pressable>

      <Modal
        animationType="slide"
        onRequestClose={() => setOpen(false)}
        transparent
        visible={open}
      >
        <View style={styles.modalRoot}>
          <Pressable
            accessibilityLabel={t('Close country selector')}
            onPress={() => setOpen(false)}
            style={styles.backdrop}
          />
          <SafeAreaView edges={['bottom']} style={styles.sheet}>
            <View style={styles.sheetHeader}>
              <Text accessibilityRole="header" style={styles.sheetTitle}>
                {t('Country')}
              </Text>
              <Pressable
                accessibilityLabel={t('Close country selector')}
                accessibilityRole="button"
                onPress={() => setOpen(false)}
                style={styles.closeButton}
              >
                <SymbolView
                  name={'xmark' as SFSymbol}
                  size={18}
                  tintColor={colors.text}
                />
              </Pressable>
            </View>
            <ScrollView contentContainerStyle={styles.options}>
              {registrationCountries.map((country) => {
                const isSelected = selected?.value === country.value;
                return (
                  <Pressable
                    accessibilityLabel={t(country.label)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: isSelected }}
                    key={country.value}
                    onPress={() => {
                      onSelect(country);
                      setOpen(false);
                    }}
                    style={({ pressed }) => [
                      styles.option,
                      isSelected && styles.optionSelected,
                      pressed && styles.pressed,
                    ]}
                    testID={`country-option-${country.value}`}
                  >
                    <View style={styles.optionIdentity}>
                      {country.icon ? (
                        <SymbolView
                          accessibilityElementsHidden
                          name={country.icon}
                          size={20}
                          testID={`country-option-icon-${country.value}`}
                          tintColor={colors.textSecondary}
                        />
                      ) : (
                        <Text accessibilityElementsHidden style={styles.flag}>
                          {country.flag}
                        </Text>
                      )}
                      <Text style={styles.optionText}>{t(country.label)}</Text>
                    </View>
                    {isSelected ? (
                      <SymbolView
                        name={'checkmark' as SFSymbol}
                        size={18}
                        tintColor={colors.positive}
                      />
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>
    </>
  );
}

const styles = createThemedStyleSheet({
  selector: {
    alignItems: 'center',
    backgroundColor: colors.inputBackground,
    borderColor: colors.border,
    borderRadius: radii.md,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: touchTarget,
    paddingHorizontal: spacing.md,
  },
  selectorValue: { color: colors.text, flex: 1, ...typography.body },
  placeholder: { color: colors.textSecondary, flex: 1, ...typography.body },
  selectedValue: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: spacing.sm,
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
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    maxHeight: '78%',
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
  optionSelected: { backgroundColor: colors.surfaceRaised },
  optionIdentity: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: spacing.sm,
  },
  flag: { fontSize: 20, width: 24 },
  optionText: { color: colors.text, flex: 1, ...typography.body },
  pressed: { opacity: 0.8 },
});
