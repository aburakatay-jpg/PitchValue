# Mobil Hukuki İçerik Yapısı

`content.ts`, uygulama içindeki hukuki belge kimliklerini başlık ve tam içerikle eşleyen tek merkezi kaynaktır. Profil, kayıt, paywall, hesap silme ve analiz yüzeyleri aynı kimlikleri kullanarak `LegalModal` bileşenini açar.

Uzun hukuki metinleri ekran bileşenlerine kopyalamayın. Yeni bir hukuki giriş noktası eklerken mevcut `LegalDocumentId` değerini kullanın; metin değişikliği gerekiyorsa yalnızca merkezi içerik dosyasını ve gerektiğinde ikincil public web Markdown belgesini güncelleyin.
