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
  'Sign In': 'Sign In',
  'Sign out': 'Sign out',
  Guest: 'Guest',
  Premium: 'Premium',
  'Premium Active': 'Premium Active',
  'Premium Trial': 'Premium Trial',
  'Premium Inactive': 'Premium Inactive',
  'Premium Expired': 'Premium Expired',
  Language: 'Language',
  'Account status': 'Account status',
  Access: 'Access',
  'View Premium': 'View Premium',
  Version: 'Version',
  'Published analysis': 'Published analysis',
  'Synthetic fixture preview. No public analysis is attached.':
    'Synthetic fixture preview. No public analysis is attached.',
  'Guest access includes public Today, Explore, and Match Detail\n              discovery.':
    'Guest access includes public Today, Explore, and Match Detail\n              discovery.',
  'Guest access includes public Today, Explore, and Match Detail\n            discovery.':
    'Guest access includes public Today, Explore, and Match Detail\n            discovery.',
  'Guest access includes public Today, Explore, and Match Detail discovery.':
    'Guest access includes public Today, Explore, and Match Detail discovery.',

  'Football programme': 'Football programme',
  'Fixtures are ordered by kickoff.': 'Fixtures are ordered by kickoff.',
  'There are no fixtures available for this day.':
    'There are no fixtures available for this day.',
  'Only analyses that meet PitchValue publication criteria appear here.':
    'Only analyses that meet PitchValue publication criteria appear here.',
  'PitchValue only surfaces analyses that meet its publication criteria.':
    'PitchValue only surfaces analyses that meet its publication criteria.',
  'Full market analysis': 'Full market analysis',
  'Bet Score details': 'Bet Score details',
  'Model agreement when authoritative data is available':
    'Model agreement when authoritative data is available',
  'AI explanations': 'AI explanations',
  Monthly: 'Monthly',
  '3 Months': '3 Months',
  Annual: 'Annual',
  'Not found': 'Not found',
  'Coupon Builder': 'Coupon Builder',
  'Organize eligible published analyses into 1–4 selections.':
    'Organize eligible published analyses into 1–4 selections.',
  'Today’s Best Value': 'Today’s Best Value',
  'Review the current public analysis pool in published order.':
    'Review the current public analysis pool in published order.',
  'Explain a Pick': 'Explain a Pick',
  'Choose a published analysis as authoritative context.':
    'Choose a published analysis as authoritative context.',
  'Ask PitchValue': 'Ask PitchValue',
  'Ask grounded questions when the assistant service is available.':
    'Ask grounded questions when the assistant service is available.',
  'Public signals available when published':
    'Public signals available when published',
  'Currently unavailable': 'Currently unavailable',
  'No eligible value signals available right now':
    'No eligible value signals available right now',
  'PitchValue will not create alternatives when the public publication pool is empty.':
    'PitchValue will not create alternatives when the public publication pool is empty.',
  'Current published signals': 'Current published signals',
  'Shown in published order. No additional ranking is applied.':
    'Shown in published order. No additional ranking is applied.',
  'No pick selected': 'No pick selected',
  'An explanation must start from an authoritative published PitchValue analysis.':
    'An explanation must start from an authoritative published PitchValue analysis.',
  'Choose published context': 'Choose published context',
  'Only public analysis is offered. Choosing it does not generate a new prediction.':
    'Only public analysis is offered. Choosing it does not generate a new prediction.',
  'Explanation unavailable': 'Explanation unavailable',
  'The published': 'The published',
  'analysis is selected, but a detailed explanation is not available.':
    'analysis is selected, but a detailed explanation is not available.',
  'Ask PitchValue unavailable': 'Ask PitchValue unavailable',
  'The assistant is currently unavailable. No answer or prediction will be generated.':
    'The assistant is currently unavailable. No answer or prediction will be generated.',
  Question: 'Question',
  'Question for PitchValue': 'Question for PitchValue',
  'Ask about a published PitchValue analysis':
    'Ask about a published PitchValue analysis',
  'Send question unavailable': 'Send question unavailable',
  'Send unavailable': 'Send unavailable',
  'Choose a preference to preview the intended experience. No coupon will be generated.':
    'Choose a preference to preview the intended experience. No coupon will be generated.',
  Safe: 'Safe',
  'Prioritizes stronger supporting evidence.':
    'Prioritizes stronger supporting evidence.',
  Balanced: 'Balanced',
  'Balances confidence and potential value.':
    'Balances confidence and potential value.',
  Bold: 'Bold',
  'Uses more aggressive combinations from eligible signals.':
    'Uses more aggressive combinations from eligible signals.',
  'A future coupon may contain 1–4 selections and only one selection from each match.':
    'A future coupon may contain 1–4 selections and only one selection from each match.',
  'No publishable signals': 'No publishable signals',
  'Coupon Builder will not use unpublished or internal analysis to fill the pool.':
    'Coupon Builder will not use unpublished or internal analysis to fill the pool.',
  'eligible signal': 'eligible signal',
  'eligible signals': 'eligible signals',
  available: 'available',
  Only: 'Only',
  'eligible signal is': 'eligible signal is',
  'eligible signals are': 'eligible signals are',
  'available right now. A future builder must not force four selections.':
    'available right now. A future builder must not force four selections.',
  'A future builder may use 1–4 selections and must keep one selection per canonical match.':
    'A future builder may use 1–4 selections and must keep one selection per canonical match.',
  'Coupon Builder unavailable': 'Coupon Builder unavailable',
  'Coupon generation is not available. Eligible public analyses are not combined automatically.':
    'Coupon generation is not available. Eligible public analyses are not combined automatically.',
  'PitchValue AI': 'PitchValue AI',
  'AI explains PitchValue analysis. It does not create independent predictions.':
    'AI explains PitchValue analysis. It does not create independent predictions.',
  'Published analysis context could not be loaded. Please try again shortly.':
    'Published analysis context could not be loaded. Please try again shortly.',
  'Public analysis unavailable': 'Public analysis unavailable',
  'Showing the last available public analysis context.':
    'Showing the last available public analysis context.',
  'Could not refresh public analysis': 'Could not refresh public analysis',
  'AI access is not available yet. Viewing Premium options will not change access.':
    'AI access is not available yet. Viewing Premium options will not change access.',
  'Premium AI foundation': 'Premium AI foundation',
  Active: 'Active',
  History: 'History',
  Performance: 'Performance',
  Tracked: 'Tracked',
  Won: 'Won',
  Lost: 'Lost',
  Void: 'Void',
  Withdrawn: 'Withdrawn',
  'No active bets': 'No active bets',
  'No bet history': 'No bet history',
  'Tracked selections unavailable': 'Tracked selections unavailable',
  'Saving tracked selections is not available yet.':
    'Saving tracked selections is not available yet.',
  'Unable to load tracked selections': 'Unable to load tracked selections',
  'Previously verified records would remain unchanged.':
    'Previously verified records would remain unchanged.',
  'No tracked selections yet': 'No tracked selections yet',
  'Authoritatively saved analyses will appear here when tracking is available.':
    'Authoritatively saved analyses will appear here when tracking is available.',
  'History unavailable': 'History unavailable',
  'Settled tracking history is not available yet.':
    'Settled tracking history is not available yet.',
  'Unable to load history': 'Unable to load history',
  'No records are hidden or reclassified by the mobile app.':
    'No records are hidden or reclassified by the mobile app.',
  'No settled records yet': 'No settled records yet',
  'Authoritatively settled tracked records will appear here.':
    'Authoritatively settled tracked records will appear here.',
  'Performance unavailable': 'Performance unavailable',
  'Authoritative stake and return data do not exist, so ROI is not calculated.':
    'Authoritative stake and return data do not exist, so ROI is not calculated.',
  'Performance is temporarily unavailable':
    'Performance is temporarily unavailable',
  'Active and history records can remain independently available.':
    'Active and history records can remain independently available.',
  'No performance record yet': 'No performance record yet',
  'Metrics require authoritative settled tracking records.':
    'Metrics require authoritative settled tracking records.',
  'Track record': 'Track record',
  'No default stake, unit stake, payout, profit, win rate, or financial metric is inferred.':
    'No default stake, unit stake, payout, profit, win rate, or financial metric is inferred.',
  Use: 'Use',
  'as explanation context': 'as explanation context',
  'PUBLISHED ANALYSIS': 'PUBLISHED ANALYSIS',
  'Bet Score': 'Bet Score',
  Edge: 'Edge',
  'Sign in with email': 'Sign in with email',
  'Create an account': 'Create an account',
  'Verify email': 'Verify email',
  'Enter the verification token sent to your email.':
    'Enter the verification token sent to your email.',
  'Sign Up': 'Sign Up',
  'Verification Token': 'Verification Token',
  'Password must be 8+ chars with uppercase, lowercase, and number.':
    'Password must be 8+ chars with uppercase, lowercase, and number.',
  'Password cannot be the same as email.':
    'Password cannot be the same as email.',
  'Confirm Password': 'Confirm Password',
  'Passwords do not match.': 'Passwords do not match.',
  'Show password': 'Show password',
  'Hide password': 'Hide password',
  'Country Code (2 letters)': 'Country Code (2 letters)',
  'Please enter a valid 2-letter country code.':
    'Please enter a valid 2-letter country code.',
  'I am 18 years of age or older.': 'I am 18 years of age or older.',
  Verify: 'Verify',
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
  'No matches scheduled': 'Bugün için planlanmış maç yok',
  'No publishable signals right now': 'Şu anda yayınlanabilir sinyal yok',
  'Score unavailable': 'Skor kullanılamıyor',
  'Not enough reliable data': 'Yeterli güvenilir veri yok',
  'Final Check unavailable': 'Son Kontrol kullanılamıyor',
  'Sign in': 'Giriş yap',
  'Sign In': 'Giriş Yap',
  'Sign out': 'Çıkış yap',
  Guest: 'Misafir',
  Premium: 'Premium',
  'Premium Active': 'Premium Aktif',
  'Premium Trial': 'Premium Deneme',
  'Premium Inactive': 'Premium Pasif',
  'Premium Expired': 'Premium Süresi Doldu',
  Language: 'Dil',
  'Account status': 'Hesap durumu',
  Access: 'Erişim',
  'View Premium': "Premium'u Görüntüle",
  Version: 'Sürüm',

  'Football programme': 'Futbol programı',
  'Fixtures are ordered by kickoff.': 'Maçlar başlama saatine göre sıralanır.',
  'There are no fixtures available for this day.':
    'Bu gün için mevcut maç bulunmuyor.',
  'Only analyses that meet PitchValue publication criteria appear here.':
    'Yalnızca PitchValue yayın kriterlerini karşılayan analizler burada gösterilir.',
  'PitchValue only surfaces analyses that meet its publication criteria.':
    'PitchValue yalnızca yayın kriterlerini karşılayan analizleri gösterir.',
  'Guest access includes public Today, Explore, and Match Detail discovery.':
    'Misafir erişimi; Bugün, Keşfet ve Maç Detayı gibi herkese açık alanları kullanmanıza olanak tanır.',
  'Subscription management and restoration are currently unavailable.':
    'Abonelik yönetimi ve satın alma geri yükleme işlemleri şu anda kullanılamıyor.',
  '18+ · Betting can involve financial loss.':
    '18+ · Bahis finansal kayıp riski içerir.',
  'Full Responsible Gambling information is not yet available.':
    'Sorumlu Oyun bilgileri henüz kullanıma hazır değil.',
  'Legal and support destinations are not yet available.':
    'Yasal bilgiler ve destek bağlantıları henüz kullanıma hazır değil.',
  'Full market analysis': 'Tüm market analizleri',
  'Bet Score details': 'Bet Score ayrıntıları',
  'Model agreement when authoritative data is available':
    'Yetkili veri mevcut olduğunda model uyumu',
  'AI explanations': 'AI açıklamaları',
  Monthly: 'Aylık',
  '3 Months': '3 Aylık',
  Annual: 'Yıllık',
  'Not found': 'Bulunamadı',
  'Published analysis': 'Yayınlanan analiz',
  'Synthetic fixture preview. No public analysis is attached.':
    'Sentetik fikstür önizlemesi. Hiçbir açık analiz eklenmedi.',
  'Coupon Builder': 'Kupon Oluşturucu',
  'Organize eligible published analyses into 1–4 selections.':
    'Uygun yayınlanmış analizleri 1-4 seçim halinde düzenleyin.',
  'Today’s Best Value': 'Günün En İyi Değeri',
  'Review the current public analysis pool in published order.':
    'Mevcut genel analiz havuzunu yayınlanma sırasına göre inceleyin.',
  'Explain a Pick': 'Analizi Açıkla',
  'Choose a published analysis as authoritative context.':
    'Yetkili bağlam olarak yayınlanmış bir analiz seçin.',
  'Ask PitchValue': "PitchValue'a Sor",
  'Ask grounded questions when the assistant service is available.':
    'Asistan hizmeti mevcut olduğunda temellendirilmiş sorular sorun.',
  'Public signals available when published':
    'Açık sinyaller yayınlandığında mevcuttur',
  'Currently unavailable': 'Şu anda mevcut değil',
  'No eligible value signals available right now':
    'Şu anda uygun değer sinyali bulunmuyor',
  'PitchValue will not create alternatives when the public publication pool is empty.':
    'PitchValue, genel yayın havuzu boş olduğunda alternatifler oluşturmaz.',
  'Current published signals': 'Mevcut yayınlanan sinyaller',
  'Shown in published order. No additional ranking is applied.':
    'Yayınlanma sırasına göre gösterilmektedir. Ek bir sıralama uygulanmaz.',
  'No pick selected': 'Seçim yapılmadı',
  'An explanation must start from an authoritative published PitchValue analysis.':
    'Açıklama, yetkili ve yayınlanmış bir PitchValue analizi ile başlamalıdır.',
  'Choose published context': 'Yayınlanan bağlamı seçin',
  'Only public analysis is offered. Choosing it does not generate a new prediction.':
    'Sadece açık analiz sunulmaktadır. Seçilmesi yeni bir tahmin üretmez.',
  'Explanation unavailable': 'Açıklama mevcut değil',
  'The published': 'Yayınlanan',
  'analysis is selected, but a detailed explanation is not available.':
    'analizi seçildi, ancak detaylı bir açıklama mevcut değil.',
  'Ask PitchValue unavailable': "PitchValue'ya Sor özelliği mevcut değil",
  'The assistant is currently unavailable. No answer or prediction will be generated.':
    'Asistan şu anda kullanılamıyor. Herhangi bir cevap veya tahmin üretilmeyecektir.',
  Question: 'Soru',
  'Question for PitchValue': 'PitchValue için Soru',
  'Ask about a published PitchValue analysis':
    'Yayınlanmış bir PitchValue analizi hakkında soru sorun',
  'Send question unavailable': 'Soru gönderme mevcut değil',
  'Send unavailable': 'Gönderilemiyor',
  'Choose a preference to preview the intended experience. No coupon will be generated.':
    'Planlanan deneyimi önizlemek için bir tercih seçin. Kupon oluşturulmayacaktır.',
  Safe: 'Temkinli',
  'Prioritizes stronger supporting evidence.':
    'Daha güçlü destekleyici kanıtlara öncelik verir.',
  Balanced: 'Dengeli',
  'Balances confidence and potential value.':
    'Güven ve potansiyel değeri dengeler.',
  Bold: 'Cesur',
  'Uses more aggressive combinations from eligible signals.':
    'Uygun sinyallerden daha agresif kombinasyonlar kullanır.',
  'A future coupon may contain 1–4 selections and only one selection from each match.':
    'Gelecekteki bir kupon 1-4 seçim içerebilir ve her maçtan sadece bir seçim yer alabilir.',
  'No publishable signals': 'Yayınlanabilir sinyal bulunmuyor',
  'Coupon Builder will not use unpublished or internal analysis to fill the pool.':
    'Kupon Oluşturucu havuzu doldurmak için yayınlanmamış veya dahili analizleri kullanmaz.',
  'eligible signal': 'uygun sinyal',
  'eligible signals': 'uygun sinyaller',
  available: 'mevcut',
  Only: 'Sadece',
  'eligible signal is': 'uygun sinyal',
  'eligible signals are': 'uygun sinyal',
  'available right now. A future builder must not force four selections.':
    'şu anda mevcut. Gelecekteki bir oluşturucu dört seçimi zorunlu kılmamalıdır.',
  'A future builder may use 1–4 selections and must keep one selection per canonical match.':
    'Gelecekteki bir oluşturucu 1-4 seçim kullanabilir ve her geçerli maç için bir seçimi korumalıdır.',
  'Coupon Builder unavailable': 'Kupon Oluşturucu mevcut değil',
  'Coupon generation is not available. Eligible public analyses are not combined automatically.':
    'Kupon oluşturma mevcut değil. Uygun açık analizler otomatik olarak birleştirilmez.',
  'PitchValue AI': 'PitchValue AI',
  'AI explains PitchValue analysis. It does not create independent predictions.':
    'Yapay zeka PitchValue analizini açıklar. Bağımsız tahminler üretmez.',
  'Published analysis context could not be loaded. Please try again shortly.':
    'Yayınlanan analiz bağlamı yüklenemedi. Lütfen kısa süre sonra tekrar deneyin.',
  'Public analysis unavailable': 'Açık analiz mevcut değil',
  'Showing the last available public analysis context.':
    'Kullanılabilen son açık analiz bağlamı gösteriliyor.',
  'Could not refresh public analysis': 'Açık analiz yenilenemedi',
  'AI access is not available yet. Viewing Premium options will not change access.':
    'Yapay zeka erişimi henüz mevcut değil. Premium seçenekleri görüntülemek erişimi değiştirmez.',
  'Premium AI foundation': 'Premium AI temeli',
  Active: 'Aktif',
  History: 'Geçmiş',
  Performance: 'Performans',
  Tracked: 'Takip edilen',
  Won: 'Kazanan',
  Lost: 'Kaybeden',
  Void: 'İade',
  Withdrawn: 'Geri çekilen',
  'No active bets': 'Aktif bahis yok',
  'No bet history': 'Bahis geçmişi yok',
  'Tracked selections unavailable': 'Takip edilen seçimler kullanılamıyor',
  'Saving tracked selections is not available yet.':
    'Takip edilen seçimleri kaydetme henüz mevcut değil.',
  'Unable to load tracked selections': 'Takip edilen seçimler yüklenemiyor',
  'Previously verified records would remain unchanged.':
    'Daha önce doğrulanan kayıtlar değişmeden kalacaktır.',
  'No tracked selections yet': 'Henüz takip edilen seçim yok',
  'Authoritatively saved analyses will appear here when tracking is available.':
    'Yetkili olarak kaydedilen analizler takip mevcut olduğunda burada görünecektir.',
  'History unavailable': 'Geçmiş kullanılamıyor',
  'Settled tracking history is not available yet.':
    'Sonuçlanmış takip geçmişi henüz mevcut değil.',
  'Unable to load history': 'Geçmiş yüklenemiyor',
  'No records are hidden or reclassified by the mobile app.':
    'Hiçbir kayıt mobil uygulama tarafından gizlenmez veya yeniden sınıflandırılmaz.',
  'No settled records yet': 'Henüz sonuçlanmış kayıt yok',
  'Authoritatively settled tracked records will appear here.':
    'Yetkili olarak sonuçlanan takip edilen kayıtlar burada görünecektir.',
  'Performance unavailable': 'Performans kullanılamıyor',
  'Authoritative stake and return data do not exist, so ROI is not calculated.':
    'Yetkili bahis ve getiri verileri mevcut değildir, bu nedenle ROI hesaplanmaz.',
  'Performance is temporarily unavailable':
    'Performans geçici olarak kullanılamıyor',
  'Active and history records can remain independently available.':
    'Aktif ve geçmiş kayıtlar bağımsız olarak mevcut kalabilir.',
  'No performance record yet': 'Henüz performans kaydı yok',
  'Metrics require authoritative settled tracking records.':
    'Metrikler için yetkili ve sonuçlanmış takip kayıtları gereklidir.',
  'Track record': 'Kayıt geçmişi',
  'No default stake, unit stake, payout, profit, win rate, or financial metric is inferred.':
    'Varsayılan bir bahis, birim bahis, ödeme, kâr, kazanma oranı veya finansal metrik çıkarımı yapılmaz.',
  Use: 'Kullan',
  'as explanation context': 'açıklama bağlamı olarak',
  'PUBLISHED ANALYSIS': 'YAYINLANAN ANALİZ',
  'Bet Score': 'Bahis Skoru',
  Edge: 'Avantaj',
  'Sign in with email': 'E-posta ile giriş yap',
  'Create an account': 'Hesap oluştur',
  'Verify email': 'E-postayı doğrula',
  'Enter the verification token sent to your email.':
    'E-postanıza gönderilen doğrulama kodunu girin.',
  'Sign Up': 'Kayıt Ol',
  'Verification Token': 'Doğrulama Kodu',
  'Password must be 8+ chars with uppercase, lowercase, and number.':
    'Şifre en az 8 karakter olmalı, büyük/küçük harf ve sayı içermelidir.',
  'Password cannot be the same as email.':
    'Şifre e-posta adresi ile aynı olamaz.',
  'Confirm Password': 'Şifreyi Onayla',
  'Passwords do not match.': 'Şifreler eşleşmiyor.',
  'Show password': 'Şifreyi göster',
  'Hide password': 'Şifreyi gizle',
  'Country Code (2 letters)': 'Ülke Kodu (2 harf)',
  'Please enter a valid 2-letter country code.':
    'Lütfen geçerli 2 harfli bir ülke kodu girin.',
  'I am 18 years of age or older.': '18 yaşından büyük olduğumu onaylıyorum.',
  Verify: 'Doğrula',
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
