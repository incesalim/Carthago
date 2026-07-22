# Türk Bankaları Ürün Benchmark — Taksonomi ve Kanıt Kuralları

Tarih: 2026-07-21. Bu dosya **spec**'tir. 11 araştırmacının hepsi AYNI hücre
setini doldurur; aksi halde matris karşılaştırılamaz.

---

## 1. Kanıt kuralı (en önemli bölüm — atlanamaz)

**Her `yes` bir URL ile gelir. URL yoksa `yes` yoktur.**

Eğitim hafızandan "Akbank'ın tabii ki konut kredisi vardır" diye doldurma.
Doğruysa bile kanıtsızdır ve bu raporun tek değeri kanıtlı olmasıdır.

Değer alfabesi — dördü de farklı şey söyler:

| Değer | Anlamı | Şartı |
|---|---|---|
| `yes` | Banka bu ürünü satıyor | Bankanın KENDİ alan adında ürünü gösteren bir sayfa. `url` zorunlu. |
| `no` | Banka bu ürünü satmıyor | İlgili kategori sayfasına bakıldı, ürün orada YOK. `url` = baktığın kategori sayfası. Bu bankaya dair bir olgudur. |
| `partial` | Var ama kısıtlı | İştirak üzerinden, sadece şubede, sadece mevcut müşteriye, sadece belli segmente, ya da acentelik olarak. `note` kısıtı yazar. `url` zorunlu. |
| `unknown` | Doğrulayamadık | Site bloklu, sayfa bulunamadı, kategori sayfası yok. **Bu BİZE dair bir olgudur, bankaya dair değil.** `note` nedeni yazar. |

`unknown` yazmaktan çekinme. Uydurulmuş bir `no`, dürüst bir `unknown`'dan
çok daha pahalıya patlar — matrisi sessizce yanlışlar.

Kaynak önceliği:
1. Bankanın kendi sitesi (ürün sayfası, fiyat/ücret tarifesi, "ürün ve hizmet
   ücretleri" PDF'i çok verimlidir — tüm ürün rafını tek sayfada listeler)
2. Bankanın mobil uygulama sayfası / App Store–Google Play açıklaması
3. Bankanın faaliyet raporu veya yatırımcı sunumu
4. KAP genel bilgi formu (iştirakler için)

Üçüncü taraf karşılaştırma siteleri (hangikredi, doviz.com vb.) **kanıt
değildir** — sadece nereye bakacağını bulmak için ipucudur.

---

## 2. Evren — 32 banka, 11 küme

Dışarıda bırakılanlar ve nedeni: TAKAS (takas/saklama kurumu, müşteri ürün
rafı yok), EXIM (ihracat kredi ajansı), KLNMA, TSKB, PASHA (toptancı
kalkınma/yatırım bankaları), ATBANK (toptancı, perakende rafı yok).

| # | Küme | Bankalar |
|---|---|---|
| 1 | Kamu mevduat | ZIRAAT, HALKB, VAKBN |
| 2 | Büyük özel A | AKBNK, ISCTR |
| 3 | Büyük özel B | YKBNK, GARAN |
| 4 | Yabancı büyük | DENIZ, QNBFB, TEB |
| 5 | Yabancı orta | ING, BURGAN, ALNTF, ODEA |
| 6 | Özel orta | SKBNK, ANADOLU, FIBA |
| 7 | Katılım özel | KUVEYT, ALBRK, TFKB |
| 8 | Katılım kamu | VAKIFK, ZIRAATK, EMLAK |
| 9 | Dijital mevduat | ENPARA, COLENDI, ZIRAATD |
| 10 | Dijital katılım | HAYATK, TOMK, DUNYAK |
| 11 | İhtisas / niş | HSBC, ICBCT, AKTIF |

Küme 9–10–11 için raf dardır: çok sayıda `no` beklenir. Bu bir bulgudur,
bir eksiklik değil — ama yine de kategori sayfasına bakarak doğrula.

**Katılım bankaları için terminoloji uyarısı:** ürün aynı, ad farklıdır.
"Mevduat" → katılma hesabı; "kredi" → finansman (murabaha/kâr payı);
"tahvil" → kira sertifikası (sukuk); "faiz" → kâr payı. Adı farklı diye
`no` yazma. Tersi de geçerli: faize dayalı ürünler (KMH, foreks, tahvil,
vadeli mevduat) katılım bankalarında gerçekten yoktur — orada `no` doğrudur
ve `note`'a "katılım bankacılığı ilkeleri gereği" yaz.

---

## 3. Öznitelikler

100 hücre, 10 blok. Kod → soru. Kodları AYNEN kullan.

### Blok A — Bireysel mevduat & birikim (9)
| Kod | Öznitelik | Not |
|---|---|---|
| A01 | Vadeli TL mevduat / TL katılma hesabı | temel |
| A02 | Döviz (USD/EUR) mevduat / katılma hesabı | temel |
| A03 | Altın hesabı (gram altın al-sat) | |
| A04 | Gümüş / platin / diğer kıymetli maden hesabı | ayrıştırıcı |
| A05 | Kur korumalı ürün (KKM/DDM) hâlâ açık mı | 2026'da çoğu kapalı olmalı; kapalıysa `no` |
| A06 | 18 yaş altı çocuk / genç hesabı | |
| A07 | Otomatik birikim / kumbara / hedefli birikim ürünü | ayrıştırıcı |
| A08 | Emekli maaşı promosyon ürünü | |
| A09 | Günlük getirili / esnek vadeli hesap (vadeyi bozmadan) | ayrıştırıcı |

### Blok B — Bireysel kredi (9)
| Kod | Öznitelik | Not |
|---|---|---|
| B01 | İhtiyaç kredisi / bireysel finansman | temel |
| B02 | Konut kredisi / konut finansmanı | |
| B03 | Taşıt kredisi (sıfır ve/veya 2. el) | |
| B04 | KMH / ek hesap (rotatif) | katılımda beklenmez |
| B05 | Kredi kartından taksitli nakit avans | katılımda beklenmez |
| B06 | Yeşil bireysel kredi (çatı GES, elektrikli araç, enerji verimliliği) | ayrıştırıcı |
| B07 | Eğitim / öğrenci kredisi | |
| B08 | Gayrimenkul teminatlı ihtiyaç kredisi | |
| B09 | Borç transferi / kredi yapılandırma ürünü | |

### Blok C — Kart & ödeme (10)
| Kod | Öznitelik | Not |
|---|---|---|
| C01 | Kendi kredi kartı markası var mı | `note`'a marka adını yaz (Bonus/World/Axess/Maximum/Paraf/Bankkart/CardFinans/Advantage/Play vb.) |
| C02 | Sanal kart | |
| C03 | Apple Pay | ayrıştırıcı |
| C04 | Google Wallet / Google Pay | ayrıştırıcı |
| C05 | Ön ödemeli / hediye kart | |
| C06 | QR ile ATM'den kartsız para çekme | |
| C07 | FAST + Kolay Adresleme | |
| C08 | Bankanın kendi dijital cüzdanı | ayrıştırıcı |
| C09 | Yurt dışı hızlı para transferi (Western Union / UPT / MoneyGram / Wise) | `note`'a sağlayıcıyı yaz |
| C10 | Ticari / kurumsal kredi kartı | |

### Blok D — Yatırım (13)
| Kod | Öznitelik | Not |
|---|---|---|
| D01 | Yatırım fonu satışı | |
| D02 | TEFAS üzerinden başka kurucuların fonları | ayrıştırıcı |
| D03 | Grup içi portföy yönetim şirketinin fonları | |
| D04 | Hisse senedi alım-satım (bankanın kendi kanalından) | ayrıştırıcı — çoğu banka aracı kuruma yönlendirir → `partial` |
| D05 | VİOP / vadeli işlem | |
| D06 | Eurobond / özel sektör tahvili / kira sertifikası | |
| D07 | Devlet iç borçlanma senedi (DİBS) / kamu kira sertifikası | |
| D08 | Kaldıraçlı işlem (foreks) | çoğunda `no` beklenir |
| D09 | Robo-advisor / otomatik portföy önerisi | ayrıştırıcı |
| D10 | Fiziki altın alım / teslimat | ayrıştırıcı |
| D11 | Yurt dışı hisse senedi (ABD borsaları vb.) | ayrıştırıcı |
| D12 | Kripto varlık erişimi (iştirak/iş birliği dahil) | ayrıştırıcı |
| D13 | Özel bankacılık (private banking) segmenti | `note`'a segment adını ve varsa eşiği yaz |

### Blok E — Sigorta & emeklilik (8)
| Kod | Öznitelik | Not |
|---|---|---|
| E01 | BES (bireysel emeklilik) satışı | |
| E02 | OKS (otomatik katılım) | |
| E03 | Hayat sigortası | |
| E04 | Kasko / trafik sigortası | |
| E05 | Konut sigortası / DASK | |
| E06 | Tamamlayıcı sağlık sigortası | ayrıştırıcı |
| E07 | Grup içi sigorta şirketi (yoksa `partial` = acentelik) | |
| E08 | Grup içi emeklilik şirketi (yoksa `partial` = acentelik) | |

### Blok F — Kanal & dijital (10)
| Kod | Öznitelik | Not |
|---|---|---|
| F01 | Mobil uygulama (iOS + Android) | |
| F02 | Uzaktan müşteri edinimi (görüntülü görüşme ile kimlik tespiti) | |
| F03 | Şubeye hiç gitmeden tam müşteri olma | F02'den farkı: süreç uçtan uca dijital mi |
| F04 | Açık bankacılık / geliştirici API portalı | ayrıştırıcı |
| F05 | Yapay zekâ / sesli asistan (uygulama içi) | ayrıştırıcı |
| F06 | Kendi ATM ağı | yoksa ortak kullanım anlaşması → `partial`, `note`'a ortağı yaz |
| F07 | Ayrı markalı tamamen dijital alt banka/marka | ayrıştırıcı |
| F08 | Sitenin tam İngilizce sürümü | |
| F09 | WhatsApp bankacılığı | ayrıştırıcı |
| F10 | Şube ağı var mı | dijital bankalarda `no` |

### Blok G — KOBİ / esnaf (14)
| Kod | Öznitelik | Not |
|---|---|---|
| G01 | İşletme / esnaf kredisi | |
| G02 | KGF kefaletli kredi | |
| G03 | Tarım / çiftçi kredisi | ayrıştırıcı |
| G04 | Ticari taşıt / iş makinesi finansmanı | |
| G05 | Fiziki POS | |
| G06 | Sanal POS / e-ticaret ödeme altyapısı | |
| G07 | Yazarkasa POS (ÖKC) | ayrıştırıcı |
| G08 | Mobil / yazılım POS (softPOS, Android POS) | ayrıştırıcı |
| G09 | Üye işyeri taksitlendirme programı | |
| G10 | Çek karnesi / çek tahsilat | |
| G11 | DBS (doğrudan borçlandırma) / tedarikçi finansmanı | ayrıştırıcı |
| G12 | e-Fatura / ön muhasebe / dijital KOBİ paketi | ayrıştırıcı |
| G13 | KOBİ için şubesiz dijital hesap açılışı | ayrıştırıcı |
| G14 | Kadın girişimci veya benzeri hedefli segment programı | |

### Blok H — Dış ticaret (7)
| Kod | Öznitelik | Not |
|---|---|---|
| H01 | Akreditif (ithalat / ihracat) | |
| H02 | Vesaik mukabili / kabul-aval kredili işlem | |
| H03 | Teminat mektubu | |
| H04 | e-Teminat mektubu (KEP / dijital teminat) | ayrıştırıcı |
| H05 | Eximbank aracılı ihracat kredisi | |
| H06 | Forfaiting / iskonto / ihracat alacağı finansmanı | |
| H07 | Kendi yurt dışı şubesi veya banka iştiraki | ayrıştırıcı |

### Blok I — Kurumsal & hazine (12)
| Kod | Öznitelik | Not |
|---|---|---|
| I01 | Yatırım kredisi / proje finansmanı | |
| I02 | Sendikasyon / kulüp kredisi | |
| I03 | Forward (vadeli döviz) | |
| I04 | Swap (para / faiz) | katılımda `no` beklenir |
| I05 | Opsiyon | |
| I06 | Emtia riskten korunma | ayrıştırıcı |
| I07 | Tahvil / kira sertifikası ihracına aracılık | |
| I08 | Halka arz aracılığı | ayrıştırıcı |
| I09 | Birleşme-devralma / kurumsal finansman danışmanlığı | ayrıştırıcı |
| I10 | Nakit yönetimi + ERP / host-to-host entegrasyon | ayrıştırıcı |
| I11 | Bordro / maaş ödeme paketi | |
| I12 | Sürdürülebilirlik bağlantılı veya yeşil ticari kredi | ayrıştırıcı |

### Blok J — Grup iştirakleri (8) — ürün rafının sınırını bunlar belirler
| Kod | Öznitelik |
|---|---|
| J01 | Portföy yönetimi şirketi |
| J02 | Aracı kurum (menkul değerler / yatırım) |
| J03 | Sigorta şirketi |
| J04 | Emeklilik şirketi |
| J05 | Leasing (finansal kiralama) |
| J06 | Faktoring |
| J07 | Ödeme kuruluşu / e-para kuruluşu |
| J08 | Yurt dışı banka iştiraki |

J bloğu için kaynak: bankanın "iştiraklerimiz / grup şirketlerimiz" sayfası
veya KAP genel bilgi formu §7. Kendi sitesinde iştirak listesi yoksa `unknown`.

---

## 4. Çıktı formatı

Her banka için bir dosya:
`<scratchpad>/products/<TICKER>.json`

```json
{
  "ticker": "AKBNK",
  "bank": "Akbank",
  "domain": "akbank.com",
  "researched_at": "2026-07-21",
  "attributes": {
    "A01": { "v": "yes", "url": "https://...", "note": "" },
    "A04": { "v": "no",  "url": "https://... (baktığım kategori sayfası)", "note": "kıymetli maden sayfasında yalnız altın var" },
    "D04": { "v": "partial", "url": "https://...", "note": "Ak Yatırım'a yönlendiriyor, banka uygulamasından değil" },
    "J08": { "v": "unknown", "url": "", "note": "iştirak listesi sayfası bulunamadı" }
  },
  "distinctive": [
    "Bu bankanın rafını akranlarından ayıran 3-6 madde. Kanıtlı olacak."
  ],
  "shelf_notes": "2-4 cümle: bu bankanın ürün stratejisi neye benziyor.",
  "coverage": { "yes": 0, "no": 0, "partial": 0, "unknown": 0 }
}
```

100 kodun **hepsi** `attributes` içinde bulunmalı. Eksik kod = sessiz boşluk;
matriste `unknown`'dan ayırt edilemez. Bilmiyorsan `unknown` yaz, atlama.
