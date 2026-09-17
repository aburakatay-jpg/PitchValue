import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useContext, useEffect, useState } from 'react';

export type Language = 'en' | 'tr';

interface Translations {
  [key: string]: string;
}

const en: Translations = {
  Today: 'Today',
  Explore: 'Explore',
  AI: 'AI',
  'My Bets': 'My Bets',
  Profile: 'Profile',
  Account: 'Account',
  Subscription: 'Subscription',
  Preferences: 'Preferences',
  'Responsible Gaming': 'Responsible Gaming',
  App: 'App',
  Loading: 'Loading...',
  Retry: 'Retry',
  Unavailable: 'Unavailable',
  'No matches scheduled': 'No matches scheduled',
  'No publishable signals right now': 'No publishable signals right now',
  'Score unavailable': 'Score unavailable',
  'Not enough reliable data': 'Not enough reliable data',
  'Final Check unavailable': 'Final Check unavailable',
  'Sign in': 'Sign in',
  'Sign out': 'Sign out',
  Guest: 'Guest',
  Language: 'Language',
  'Account status': 'Account status',
  Access: 'Access',
  'View Premium': 'View Premium',
  Version: 'Version',
};

const tr: Translations = {
  Today: 'Bugün',
  Explore: 'Keşfet',
  AI: 'AI',
  'My Bets': 'Bahislerim',
  Profile: 'Profil',
  Account: 'Hesap',
  Subscription: 'Abonelik',
  Preferences: 'Tercihler',
  'Responsible Gaming': 'Sorumlu Oyun',
  App: 'Uygulama',
  Loading: 'Yükleniyor...',
  Retry: 'Tekrar Dene',
  Unavailable: 'Kullanılamıyor',
  'No matches scheduled': 'Planlanmış maç yok',
  'No publishable signals right now': 'Şu an yayınlanabilir sinyal yok',
  'Score unavailable': 'Skor kullanılamıyor',
  'Not enough reliable data': 'Yeterli güvenilir veri yok',
  'Final Check unavailable': 'Son Kontrol kullanılamıyor',
  'Sign in': 'Giriş yap',
  'Sign out': 'Çıkış yap',
  Guest: 'Misafir',
  Language: 'Dil',
  'Account status': 'Hesap durumu',
  Access: 'Erişim',
  'View Premium': "Premium'u Görüntüle",
  Version: 'Sürüm',
};

const dicts: Record<Language, Translations> = { en, tr };

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: keyof typeof en | string) => string;
}

const LanguageContext = createContext<LanguageContextType | null>(null);

const STORAGE_KEY = 'pitchvalue_language';

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLang] = useState<Language>('en');
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((val) => {
        if (val === 'en' || val === 'tr') {
          setLang(val);
        }
      })
      .catch(() => {})
      .finally(() => setIsReady(true));
  }, []);

  const setLanguage = (lang: Language) => {
    setLang(lang);
    AsyncStorage.setItem(STORAGE_KEY, lang).catch(() => {});
  };

  const t = (key: string | number) => {
    if (typeof key !== 'string') return String(key);
    return dicts[language][key] || key;
  };

  if (!isReady) return null;

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}
