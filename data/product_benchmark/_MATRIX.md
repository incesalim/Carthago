## 6. Banka bazlı: kanıt kapsamı vs doğrulanmış raf

`kapsam` = kaç hücreyi doğrulayabildik (BİZE dair). `raf` = doğrulanan hücrelerin kaçı ürün var (BANKAYA dair, partial=0.5). Sıralama rafa göre; kapsamı %65 altı ⚠ ile işaretli.

| # | Banka | Küme | yes | part | no | unk | kapsam | raf |
|--:|---|---|--:|--:|--:|--:|--:|--:|
| 1 | **GARAN** | Büyük özel | 87 | 3 | 1 | 9 | 91% | **97%** |
| 2 | **YKBNK** | Büyük özel | 77 | 6 | 4 | 13 | 87% | **92%** |
| 3 | **ZIRAAT** | Kamu mevduat | 69 | 3 | 5 | 23 | 77% | **92%** |
| 4 | **ISCTR** | Büyük özel | 74 | 2 | 7 | 17 | 83% | **90%** |
| 5 | **DENIZ** | Yabancı büyük | 63 | 4 | 5 | 28 | 72% | **90%** |
| 6 | **AKBNK** | Büyük özel | 75 | 7 | 5 | 13 | 87% | **90%** |
| 7 | **QNBFB** | Yabancı büyük | 62 | 10 | 3 | 25 | 75% | **89%** |
| 8 | **TEB** | Yabancı büyük | 61 | 13 | 2 | 24 | 76% | **89%** |
| 9 | **FIBA** | Özel orta | 43 | 2 | 5 | 50 | 50% ⚠ | **88%** |
| 10 | **HALKB** | Kamu mevduat | 64 | 6 | 7 | 23 | 77% | **87%** |
| 11 | **SKBNK** | Özel orta | 56 | 2 | 8 | 34 | 66% | **86%** |
| 12 | **KUVEYT** | Katılım özel | 63 | 0 | 11 | 26 | 74% | **85%** |
| 13 | **ANADOLU** | Özel orta | 52 | 4 | 8 | 36 | 64% ⚠ | **84%** |
| 14 | **ICBCT** | İhtisas/niş | 40 | 4 | 7 | 49 | 51% ⚠ | **82%** |
| 15 | **VAKBN** | Kamu mevduat | 70 | 5 | 14 | 11 | 89% | **81%** |
| 16 | **ING** | Yabancı orta | 56 | 4 | 12 | 28 | 72% | **81%** |
| 17 | **TFKB** | Katılım özel | 44 | 2 | 10 | 44 | 56% ⚠ | **80%** |
| 18 | **ALBRK** | Katılım özel | 52 | 0 | 14 | 34 | 66% | **79%** |
| 19 | **ZIRAATK** | Katılım kamu | 49 | 5 | 13 | 33 | 67% | **77%** |
| 20 | **EMLAK** | Katılım kamu | 42 | 4 | 14 | 40 | 60% ⚠ | **73%** |
| 21 | **DUNYAK** | Dijital katılım | 30 | 2 | 11 | 57 | 43% ⚠ | **72%** |
| 22 | **BURGAN** | Yabancı orta | 46 | 3 | 19 | 32 | 68% | **70%** |
| 23 | **VAKIFK** | Katılım kamu | 47 | 4 | 20 | 29 | 71% | **69%** |
| 24 | **ODEA** | Yabancı orta | 44 | 4 | 19 | 33 | 67% | **69%** |
| 25 | **HSBC** | İhtisas/niş | 41 | 4 | 18 | 37 | 63% ⚠ | **68%** |
| 26 | **AKTIF** | İhtisas/niş | 37 | 19 | 15 | 29 | 71% | **65%** |
| 27 | **ALNTF** | Yabancı orta | 41 | 5 | 25 | 29 | 71% | **61%** |
| 28 | **ENPARA** | Dijital mevduat | 28 | 3 | 29 | 40 | 60% ⚠ | **49%** |
| 29 | **ZIRAATD** | Dijital mevduat | 23 | 4 | 27 | 46 | 54% ⚠ | **46%** |
| 30 | **HAYATK** | Dijital katılım | 25 | 1 | 36 | 38 | 62% ⚠ | **41%** |
| 31 | **COLENDI** | Dijital mevduat | 12 | 3 | 35 | 50 | 50% ⚠ | **27%** |
| 32 | **TOMK** | Dijital katılım | 15 | 2 | 68 | 15 | 85% | **19%** |

## 7. Öznitelik bazlı yaygınlık — ne ortak, ne ayrıştırıcı

`var` = yes sayısı, `yok` = no sayısı, `?` = doğrulanamayan. Yaygınlık = var/(var+yok+kısmi), yalnız doğrulanan hücreler üzerinden.

> **Payda kuralı:** yaygınlık yalnızca en az 22/32 bankada doğrulanabilen öznitelikler için hesaplandı. Daha az paydası olanlar aşağıda ayrı listelenir — çünkü araştırmacılar ürünü bulamadığında çoğu kez `no` değil `unknown` yazdı, bu da küçük paydalarda yaygınlığı yapay olarak yukarı çeker.

Yeterli paydalı öznitelik: **58/100**.

### Masaya giriş bileti (yaygınlık ≥ %90) — ayrım yaratmaz

| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |
|---|---|--:|--:|--:|--:|--:|
| A09 | Günlük getirili/esnek hesap | 23 | 0 | 0 | 9 | 100% |
| B01 | İhtiyaç kredisi/finansman | 32 | 0 | 0 | 0 | 100% |
| C02 | Sanal kart | 27 | 0 | 0 | 5 | 100% |
| F01 | Mobil app (iOS+Android) | 32 | 0 | 0 | 0 | 100% |
| F02 | Uzaktan edinim (görüntülü) | 25 | 0 | 0 | 7 | 100% |
| F03 | Uçtan uca dijital müşterilik | 25 | 0 | 0 | 7 | 100% |
| C07 | FAST + Kolay Adresleme | 27 | 1 | 0 | 4 | 98% |
| A01 | Vadeli TL mevduat / katılma | 31 | 0 | 1 | 0 | 97% |
| C01 | Kendi kart markası | 31 | 0 | 1 | 0 | 97% |
| D01 | Yatırım fonu | 31 | 0 | 1 | 0 | 97% |
| G10 | Çek karnesi/tahsilat | 21 | 0 | 1 | 10 | 95% |
| I03 | Forward | 21 | 0 | 1 | 10 | 95% |
| A02 | Döviz mevduat/katılma | 30 | 1 | 1 | 0 | 95% |
| A03 | Altın hesabı | 29 | 1 | 1 | 1 | 95% |
| I10 | Nakit yön.+ERP/host-to-host | 23 | 2 | 1 | 6 | 92% |
| G01 | İşletme/esnaf kredisi | 29 | 1 | 2 | 0 | 92% |
| G11 | DBS/tedarikçi fin. | 19 | 2 | 1 | 10 | 91% |
| D04 | Hisse alım-satım (kendi kanalı) | 27 | 4 | 1 | 0 | 91% |
| F06 | Kendi ATM ağı | 25 | 6 | 0 | 1 | 90% |

### Yaygın ama evrensel değil (%75–%90)

| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |
|---|---|--:|--:|--:|--:|--:|
| C10 | Ticari/kurumsal kart | 25 | 0 | 3 | 4 | 89% |
| E03 | Hayat sigortası | 28 | 1 | 3 | 0 | 89% |
| H03 | Teminat mektubu | 28 | 1 | 3 | 0 | 89% |
| G05 | Fiziki POS | 23 | 0 | 3 | 6 | 88% |
| I01 | Yatırım/proje finansmanı | 23 | 0 | 3 | 6 | 88% |
| H02 | Vesaik/kabul-aval | 22 | 0 | 3 | 7 | 88% |
| D06 | Eurobond/tahvil/sukuk | 24 | 3 | 2 | 3 | 88% |
| H01 | Akreditif | 25 | 0 | 4 | 3 | 86% |
| E01 | BES | 26 | 1 | 4 | 1 | 85% |
| E05 | Konut/DASK | 25 | 1 | 4 | 2 | 85% |
| G06 | Sanal POS/e-tic. | 18 | 1 | 3 | 10 | 84% |
| B03 | Taşıt kredisi | 26 | 0 | 5 | 1 | 84% |
| F10 | Şube ağı | 26 | 1 | 5 | 0 | 83% |
| E06 | Tamamlayıcı sağlık | 21 | 1 | 4 | 6 | 83% |
| J01 | Portföy yönetimi | 20 | 0 | 5 | 7 | 80% |
| E04 | Kasko/trafik | 25 | 1 | 6 | 0 | 80% |
| A04 | Gümüş/platin/diğer maden | 21 | 1 | 5 | 5 | 80% |
| J02 | Aracı kurum | 21 | 1 | 5 | 5 | 80% |
| A07 | Otomatik/hedefli birikim | 17 | 1 | 4 | 10 | 80% |
| D13 | Özel bankacılık | 19 | 0 | 5 | 8 | 79% |
| B02 | Konut kredisi/finansmanı | 25 | 0 | 7 | 0 | 78% |
| D03 | Grup portföy fonları | 21 | 0 | 6 | 5 | 78% |
| D07 | DİBS/kamu kira sertifikası | 16 | 2 | 4 | 10 | 77% |

### Gerçek ayrıştırıcılar (%25–%75) — rekabetin olduğu yer

| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |
|---|---|--:|--:|--:|--:|--:|
| B04 | KMH / ek hesap | 23 | 0 | 9 | 0 | 72% |
| D05 | VİOP/vadeli | 14 | 3 | 6 | 9 | 67% |
| I04 | Swap | 17 | 0 | 9 | 6 | 65% |
| A06 | Çocuk/genç hesabı | 14 | 0 | 8 | 10 | 64% |
| J08 | Yurt dışı banka iştiraki | 12 | 3 | 7 | 10 | 61% |
| B05 | Karttan taksitli avans | 13 | 0 | 10 | 9 | 57% |
| E08 | Grup emeklilik şirketi | 6 | 20 | 3 | 3 | 55% |
| E07 | Grup sigorta şirketi | 5 | 24 | 2 | 1 | 55% |
| H07 | Yurt dışı şube/iştirak | 14 | 2 | 12 | 4 | 54% |
| B07 | Eğitim/öğrenci kredisi | 8 | 1 | 16 | 7 | 34% |
| A05 | KKM/DDM (hâlâ açık) | 5 | 7 | 15 | 5 | 31% |
| J04 | Emeklilik şirketi | 5 | 5 | 16 | 6 | 29% |
| J03 | Sigorta şirketi | 4 | 7 | 16 | 5 | 28% |
| D12 | Kripto erişimi | 6 | 0 | 18 | 8 | 25% |

### Nadir / niş (< %25)

| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |
|---|---|--:|--:|--:|--:|--:|
| F07 | Ayrı dijital alt marka | 5 | 1 | 24 | 2 | 18% |
| D08 | Foreks (kaldıraçlı) | 1 | 2 | 25 | 4 | 7% |

### ⚠ Kanıt yetersiz — payda < 22, yaygınlık HESAPLANMADI

Bu öznitelikler için bir sonraki turda hedefli doğrulama gerekiyor. `var` sayısı bir ALT SINIRDIR, oran değildir.

| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |
|---|---|--:|--:|--:|--:|--:|
| C03 | Apple Pay | 2 | 0 | 19 | 11 | 10% |
| C08 | Kendi dijital cüzdanı | 7 | 3 | 11 | 11 | 40% |
| F08 | Tam İngilizce site | 20 | 0 | 1 | 11 | 95% |
| G04 | Ticari taşıt/iş makinesi | 18 | 1 | 2 | 11 | 88% |
| G07 | Yazarkasa POS (ÖKC) | 18 | 0 | 3 | 11 | 86% |
| G08 | Mobil/softPOS | 17 | 1 | 3 | 11 | 83% |
| I05 | Opsiyon | 15 | 0 | 6 | 11 | 71% |
| D11 | Yurt dışı hisse | 4 | 2 | 14 | 12 | 25% |
| J05 | Leasing | 15 | 0 | 5 | 12 | 75% |
| B09 | Borç transferi/yapılandırma | 9 | 0 | 10 | 13 | 47% |
| I11 | Bordro/maaş paketi | 18 | 0 | 1 | 13 | 95% |
| B06 | Yeşil bireysel kredi | 9 | 0 | 8 | 15 | 53% |
| C06 | QR ile kartsız ATM | 15 | 2 | 0 | 15 | 94% |
| C09 | Yurt dışı hızlı transfer | 16 | 0 | 1 | 15 | 94% |
| D10 | Fiziki altın al/teslim | 9 | 0 | 8 | 15 | 53% |
| J06 | Faktoring | 10 | 0 | 7 | 15 | 59% |
| G02 | KGF kefaletli | 15 | 0 | 1 | 16 | 94% |
| G03 | Tarım/çiftçi | 14 | 0 | 2 | 16 | 88% |
| F04 | Açık bankacılık/API | 15 | 0 | 0 | 17 | 100% |
| H06 | Forfaiting/iskonto | 12 | 2 | 1 | 17 | 87% |
| J07 | Ödeme/e-para kuruluşu | 9 | 0 | 5 | 18 | 64% |
| C04 | Google Wallet | 1 | 0 | 12 | 19 | 8% |
| D02 | TEFAS (3. taraf fonları) | 11 | 0 | 2 | 19 | 85% |
| D09 | Robo-advisor | 3 | 4 | 6 | 19 | 38% |
| G13 | KOBİ şubesiz açılış | 12 | 0 | 1 | 19 | 92% |
| H05 | Eximbank aracılı | 12 | 0 | 1 | 19 | 92% |
| I07 | Tahvil/sukuk ihraç | 6 | 4 | 3 | 19 | 62% |
| I08 | Halka arz aracılığı | 8 | 2 | 3 | 19 | 69% |
| B08 | Gayrimenkul teminatlı | 4 | 0 | 8 | 20 | 33% |
| G09 | Üye işyeri taksit | 10 | 1 | 1 | 20 | 88% |
| G14 | Hedefli segment (kadın vb.) | 10 | 0 | 2 | 20 | 83% |
| A08 | Emekli maaş promosyonu | 11 | 0 | 0 | 21 | 100% |
| I12 | Yeşil ticari kredi | 10 | 0 | 1 | 21 | 91% |
| C05 | Ön ödemeli/hediye kart | 3 | 1 | 6 | 22 | 35% |
| G12 | e-Fatura/ön muhasebe | 5 | 3 | 2 | 22 | 65% |
| I02 | Sendikasyon | 7 | 0 | 3 | 22 | 70% |
| I09 | M&A/kurumsal danışmanlık | 4 | 3 | 3 | 22 | 55% |
| H04 | e-Teminat mektubu | 7 | 0 | 2 | 23 | 78% |
| F05 | YZ/sesli asistan | 6 | 1 | 1 | 24 | 81% |
| E02 | OKS | 3 | 0 | 4 | 25 | 43% |
| I06 | Emtia hedge | 1 | 1 | 4 | 26 | 25% |
| F09 | WhatsApp bankacılığı | 2 | 0 | 0 | 30 | 100% |

## 8. Blok bazlı raf genişliği (doğrulanan hücreler üzerinden)

| Banka | Mevduat & birikim | Bireysel kredi | Kart & ödeme | Yatırım | Sigorta & emeklilik | Kanal & dijital | KOBİ / esnaf | Dış ticaret | Kurumsal & hazine | Grup iştirakleri |
|---|---|---|---|---|---|---|---|---|---|---|
| **ZIRAAT** | 100% | 100% | 100% | 61% | 86% | 100% | 100% | 100% | 100% | 71% |
| **HALKB** | 88% | 78% | 92% | 80% | 88% | 83% | 100% | 92% | 88% | 83% |
| **VAKBN** | 94% | 71% | 60% | 79% | 86% | 89% | 89% | 83% | 86% | 75% |
| **AKBNK** | 86% | 100% | 78% | 85% | 86% | 94% | 100% | 100% | 100% | 75% |
| **ISCTR** | 83% | 100% | 62% | 77% | 100% | 86% | 100% | 100% | 100% | 100% |
| **YKBNK** | 100% | 100% | 100% | 83% | 86% | 89% | 92% | 100% | 100% | 75% |
| **GARAN** | 100% | 100% | 100% | 96% | 94% | 90% | 100% | 100% | 100% | 94% |
| **DENIZ** | 94% | 100% | 75% | 100% | 86% | 88% | 100% | 100% | 92% | 75% |
| **QNBFB** | 100% | 92% | 67% | 71% | 100% | 100% | 95% | 92% | 85% | 100% |
| **TEB** | 93% | 100% | 64% | 69% | 100% | 100% | 96% | 100% | 83% | 86% |
| **ING** | 78% | 86% | 71% | 56% | 86% | 86% | 100% | 90% | 100% | 64% |
| **BURGAN** | 75% | 50% | 64% | 77% | 60% | 80% | 100% | 80% | 100% | 29% |
| **ALNTF** | 50% | 50% | 57% | 50% | 86% | 83% | 88% | 75% | 79% | 25% |
| **ODEA** | 81% | 67% | 50% | 60% | 86% | 86% | 88% | 83% | 100% | 0% |
| **SKBNK** | 86% | 100% | 83% | 62% | 83% | 86% | 100% | 100% | 100% | 67% |
| **ANADOLU** | 92% | 71% | 67% | 81% | 86% | 80% | 100% | 100% | 100% | 67% |
| **FIBA** | 100% | 83% | 83% | 71% | 86% | 88% | 100% | 100% | 100% | 100% |
| **KUVEYT** | 89% | 67% | 75% | 86% | 100% | 100% | 100% | 100% | 83% | 50% |
| **ALBRK** | 80% | 75% | 57% | 46% | 100% | 100% | 100% | 100% | 75% | 100% |
| **TFKB** | 83% | 60% | 71% | 75% | 86% | 100% | 100% | 100% | 75% | 50% |
| **VAKIFK** | 93% | 33% | 83% | 67% | 80% | 86% | 100% | 75% | 50% | 14% |
| **ZIRAATK** | 93% | 62% | 71% | 67% | 86% | 83% | 100% | 80% | 67% | 60% |
| **EMLAK** | 100% | 33% | 75% | 57% | 86% | 86% | 100% | 83% | 67% | 50% |
| **ENPARA** | 71% | 50% | 75% | 36% | 21% | 58% | 100% | 0% | 17% | 100% |
| **COLENDI** | 42% | 33% | 30% | 0% | 0% | 58% | 43% | 50% | — | — |
| **ZIRAATD** | 67% | 40% | 75% | 75% | 67% | 64% | 14% | 0% | 0% | 50% |
| **HAYATK** | 57% | 25% | 75% | 36% | 0% | 64% | 100% | 67% | 33% | 0% |
| **TOMK** | 75% | 11% | 67% | 20% | 19% | 50% | 0% | 0% | 0% | 0% |
| **DUNYAK** | 100% | 67% | 100% | 44% | 86% | 80% | 100% | 50% | 50% | — |
| **HSBC** | 57% | 50% | 62% | 70% | 71% | 67% | 50% | 100% | 100% | 50% |
| **ICBCT** | 88% | 80% | 71% | 88% | 80% | 80% | 83% | 100% | 92% | 62% |
| **AKTIF** | 29% | 62% | 72% | 69% | 43% | 88% | 83% | 62% | 83% | 50% |

## 9. Tam matris

● var · ◐ kısmi · · yok · ? doğrulanamadı

### Blok A — Mevduat & birikim

| Banka | A01 | A02 | A03 | A04 | A05 | A06 | A07 | A08 | A09 |
|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| HALKB | ● | ● | ● | ● | · | ● | ● | ● | ? |
| VAKBN | ● | ● | ● | ● | ◐ | ● | ● | ● | ● |
| AKBNK | ● | ● | ● | ? | · | ● | ● | ● | ? |
| ISCTR | ● | ● | ● | · | ? | ● | ? | ? | ● |
| YKBNK | ● | ● | ● | ● | ● | ● | ● | ● | ? |
| GARAN | ● | ● | ● | ● | ● | ● | ● | ? | ● |
| DENIZ | ● | ● | ● | ● | ◐ | ● | ● | ● | ● |
| QNBFB | ● | ● | ● | ● | ? | ? | ● | ● | ● |
| TEB | ● | ● | ● | ? | ? | ● | ◐ | ● | ● |
| ING | ● | ● | ● | · | · | ● | ● | ● | ● |
| BURGAN | ● | ● | ● | ● | ● | · | · | ? | ● |
| ALNTF | ● | ● | ● | · | · | · | · | ? | ● |
| ODEA | ● | ● | ● | ● | ◐ | · | ● | ? | ● |
| SKBNK | ● | ● | ● | ? | · | ● | ● | ? | ● |
| ANADOLU | ● | ● | ● | ● | ◐ | ? | ? | ? | ● |
| FIBA | ● | ● | ● | ● | ● | ● | ? | ? | ● |
| KUVEYT | ● | ● | ● | ● | · | ● | ● | ● | ● |
| ALBRK | ● | ● | ● | ● | · | ? | ? | ? | ? |
| TFKB | ● | ● | ● | ● | · | ? | ? | ? | ● |
| VAKIFK | ● | ● | ● | ● | ◐ | ? | ● | ● | ? |
| ZIRAATK | ● | ● | ● | ● | ◐ | ? | ● | ? | ● |
| EMLAK | ● | ● | ● | ● | ? | ● | ● | ? | ? |
| ENPARA | ● | ● | ● | ● | · | · | ● | ? | ? |
| COLENDI | ● | ◐ | · | · | · | ? | ? | ? | ● |
| ZIRAATD | ● | ● | ● | · | · | ? | ? | ? | ● |
| HAYATK | ● | ● | ● | ? | · | · | · | ? | ● |
| TOMK | ● | ● | ● | ● | · | · | ● | ? | ● |
| DUNYAK | ● | ● | ● | ● | ? | ? | ? | ? | ? |
| HSBC | ● | ● | ● | ● | · | · | · | ? | ? |
| ICBCT | ● | ● | ? | ? | ◐ | ? | ? | ? | ● |
| AKTIF | · | · | ◐ | ◐ | · | · | ? | ? | ● |

<sub>**A01** Vadeli TL mevduat / katılma · **A02** Döviz mevduat/katılma · **A03** Altın hesabı · **A04** Gümüş/platin/diğer maden · **A05** KKM/DDM (hâlâ açık) · **A06** Çocuk/genç hesabı · **A07** Otomatik/hedefli birikim · **A08** Emekli maaş promosyonu · **A09** Günlük getirili/esnek hesap</sub>

### Blok B — Bireysel kredi

| Banka | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 |
|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ● | ● | ● | ● | ● | ● | ? |
| HALKB | ● | ● | ● | ● | ● | ● | ● | · | · |
| VAKBN | ● | ● | ● | ● | ? | ? | · | ● | · |
| AKBNK | ● | ● | ● | ● | ● | ? | ? | ? | ● |
| ISCTR | ● | ● | ● | ● | ● | ? | ● | ? | ● |
| YKBNK | ● | ● | ● | ● | ● | ? | ? | ? | ● |
| GARAN | ● | ● | ● | ● | ● | ● | ? | ? | ● |
| DENIZ | ● | ● | ● | ● | ● | ? | ● | ? | ? |
| QNBFB | ● | ● | ● | ● | ? | ? | ◐ | ? | ● |
| TEB | ● | ● | ● | ● | ? | ● | ? | ? | ● |
| ING | ● | ● | ● | ● | ? | ● | · | ? | ● |
| BURGAN | ● | ● | ● | ● | ? | · | · | · | · |
| ALNTF | ● | ● | ● | ● | ? | · | · | · | · |
| ODEA | ● | ● | ● | ● | ● | · | · | ● | · |
| SKBNK | ● | ● | ● | ● | ● | ● | ? | ? | ? |
| ANADOLU | ● | ● | ● | ● | ● | · | · | ? | ? |
| FIBA | ● | ● | ● | ● | ? | ? | · | ? | ● |
| KUVEYT | ● | ● | ● | · | · | ? | ● | ? | ? |
| ALBRK | ● | ● | ● | · | · | ● | ● | ● | ? |
| TFKB | ● | ● | ● | · | · | ? | ? | ? | ? |
| VAKIFK | ● | ● | ● | · | · | · | · | · | · |
| ZIRAATK | ● | ● | ● | · | · | ● | ● | ? | · |
| EMLAK | ● | ● | ● | · | · | · | · | · | · |
| ENPARA | ● | · | · | ● | ● | ? | · | ? | ? |
| COLENDI | ● | · | · | ● | · | ? | · | ? | ? |
| ZIRAATD | ● | · | · | ● | ? | ? | · | ? | ? |
| HAYATK | ● | · | ? | · | · | · | ● | · | · |
| TOMK | ● | · | · | · | · | · | · | · | · |
| DUNYAK | ● | ● | ● | · | · | ● | ? | ? | ? |
| HSBC | ● | · | · | ● | ● | ? | · | ? | ? |
| ICBCT | ● | ● | ● | ● | ? | ? | · | ? | ? |
| AKTIF | ● | · | ● | ● | ● | ? | · | · | ● |

<sub>**B01** İhtiyaç kredisi/finansman · **B02** Konut kredisi/finansmanı · **B03** Taşıt kredisi · **B04** KMH / ek hesap · **B05** Karttan taksitli avans · **B06** Yeşil bireysel kredi · **B07** Eğitim/öğrenci kredisi · **B08** Gayrimenkul teminatlı · **B09** Borç transferi/yapılandırma</sub>

### Blok C — Kart & ödeme

| Banka | C01 | C02 | C03 | C04 | C05 | C06 | C07 | C08 | C09 | C10 |
|---|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ? | ? | ? | ● | ● | ● | ● | ● |
| HALKB | ● | ● | ? | ? | ? | ● | ● | ◐ | ? | ● |
| VAKBN | ● | ● | · | · | · | ● | ● | ● | · | ● |
| AKBNK | ● | ● | · | · | ? | ● | ● | ● | ● | ● |
| ISCTR | ● | ? | · | · | ● | ? | ● | · | ● | ● |
| YKBNK | ● | ● | ● | ? | ● | ● | ● | ● | ● | ● |
| GARAN | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| DENIZ | ● | ● | · | · | ? | ? | ● | ● | ● | ● |
| QNBFB | ● | ● | · | · | ? | ● | ● | · | ● | ● |
| TEB | ● | ● | · | · | ? | ? | ● | ◐ | ? | ● |
| ING | ● | ● | · | ? | ? | ● | ● | · | ? | ● |
| BURGAN | ● | ● | · | ? | ? | ◐ | ● | · | ? | ● |
| ALNTF | ● | ● | · | ? | · | ? | ● | · | ? | ● |
| ODEA | ● | ? | · | ? | ? | ? | ? | ? | ? | ? |
| SKBNK | ● | ● | ? | ? | ? | ● | ● | · | ? | ● |
| ANADOLU | ● | ● | ? | ? | · | ? | ● | · | ? | ● |
| FIBA | ● | ● | ? | ? | ? | ? | ● | · | ● | ● |
| KUVEYT | ● | ● | · | · | ? | ● | ● | ? | ● | ● |
| ALBRK | ● | ● | · | · | · | ? | ? | ? | ● | ● |
| TFKB | ● | ● | · | · | ? | ● | ? | ? | ● | ● |
| VAKIFK | ● | ● | · | ? | ? | ● | ● | ? | ? | ● |
| ZIRAATK | ● | ● | · | ? | · | ? | ● | ? | ● | ● |
| EMLAK | ● | ? | · | ? | ? | ? | ● | ? | ● | ? |
| ENPARA | ● | ● | ? | ? | ? | ◐ | ● | · | ? | ● |
| COLENDI | · | ● | ? | ? | ? | ? | ◐ | · | ? | · |
| ZIRAATD | ● | ● | ? | ? | ? | ● | ● | ◐ | ? | · |
| HAYATK | ● | ? | ? | ? | · | ? | ● | ? | ? | ● |
| TOMK | ● | ● | ? | ? | ? | ? | ? | ? | ? | · |
| DUNYAK | ● | ? | ? | ? | ? | ● | ● | ? | ? | ? |
| HSBC | ● | ● | · | · | ? | ? | ● | · | ● | ● |
| ICBCT | ● | ● | · | · | ? | ? | ● | ? | ● | ● |
| AKTIF | ● | ● | · | · | ◐ | ● | ● | ● | ● | ? |

<sub>**C01** Kendi kart markası · **C02** Sanal kart · **C03** Apple Pay · **C04** Google Wallet · **C05** Ön ödemeli/hediye kart · **C06** QR ile kartsız ATM · **C07** FAST + Kolay Adresleme · **C08** Kendi dijital cüzdanı · **C09** Yurt dışı hızlı transfer · **C10** Ticari/kurumsal kart</sub>

### Blok D — Yatırım

| Banka | D01 | D02 | D03 | D04 | D05 | D06 | D07 | D08 | D09 | D10 | D11 | D12 | D13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ? | ● | ◐ | ● | ● | ? | · | ? | · | ? | · | ● |
| HALKB | ● | ● | ● | ● | ● | ● | ● | · | ? | ? | ? | · | ● |
| VAKBN | ● | ● | ● | ● | ● | ● | ● | · | ◐ | ● | ? | · | ● |
| AKBNK | ● | ● | ● | ● | ● | ● | ● | · | ◐ | ● | ◐ | ● | ● |
| ISCTR | ● | ● | ● | ● | ◐ | ● | ● | · | ● | ● | ◐ | · | ● |
| YKBNK | ● | ● | ● | ● | ● | ● | ● | ◐ | ◐ | ? | ● | · | ● |
| GARAN | ● | ● | ● | ● | ● | ● | ● | ◐ | ● | ? | ● | ● | ● |
| DENIZ | ● | ? | ● | ● | ● | ● | ● | ? | ? | ? | ? | ? | ● |
| QNBFB | ● | ? | ● | ◐ | ◐ | ◐ | ◐ | ? | ? | ? | ? | ? | ● |
| TEB | ● | ? | ● | ◐ | ◐ | ◐ | ◐ | ? | ◐ | ? | ? | ? | ● |
| ING | ● | ? | ● | ● | ● | ? | ? | · | ? | · | · | · | ● |
| BURGAN | ● | ● | · | ● | ● | ● | ● | ● | ● | · | ● | · | ● |
| ALNTF | ● | ? | · | ● | ● | ● | ● | · | ? | · | · | · | ? |
| ODEA | ● | ? | · | ● | ● | ● | ● | · | ? | · | · | ● | ? |
| SKBNK | ● | ● | ? | ● | ? | ● | ● | · | ? | ? | · | · | ? |
| ANADOLU | ● | ? | ? | ◐ | ● | ● | ● | · | ? | ? | ? | ● | ● |
| FIBA | ● | ? | ? | ● | ? | ● | ? | · | ? | ? | · | ● | ● |
| KUVEYT | ● | ? | ● | ● | ? | ● | ? | · | ? | ● | ? | ? | ● |
| ALBRK | ● | · | ● | ● | · | ● | · | · | · | ● | · | · | ● |
| TFKB | ● | ? | ● | ● | ? | ● | ? | · | ? | ● | ● | · | ? |
| VAKIFK | ● | ? | ● | ● | ? | ● | ● | · | ? | ● | · | · | ? |
| ZIRAATK | ● | ? | ● | ● | ? | ● | ● | · | ? | ? | · | · | ● |
| EMLAK | ● | ? | ? | ● | ? | ● | ? | · | ? | ● | · | · | ? |
| ENPARA | ● | ● | ● | ● | · | · | · | · | ? | · | · | ? | · |
| COLENDI | · | · | · | · | · | · | · | · | · | · | · | ? | · |
| ZIRAATD | ● | ? | ● | ● | ? | ? | ? | ? | ? | ? | ? | ? | · |
| HAYATK | ● | ● | · | ● | · | ● | ? | · | · | ? | · | · | · |
| TOMK | ● | ? | · | ● | · | ? | · | · | · | ? | · | · | · |
| DUNYAK | ● | ? | ? | ● | · | ● | ? | · | · | ● | · | · | ? |
| HSBC | ● | ? | ● | ● | ● | ● | ● | · | · | ? | ? | · | ● |
| ICBCT | ● | ● | ● | ● | ● | ● | ● | · | ? | ? | ? | ? | ? |
| AKTIF | ● | ? | ● | ● | ? | ◐ | ? | · | ? | · | ? | ● | ● |

<sub>**D01** Yatırım fonu · **D02** TEFAS (3. taraf fonları) · **D03** Grup portföy fonları · **D04** Hisse alım-satım (kendi kanalı) · **D05** VİOP/vadeli · **D06** Eurobond/tahvil/sukuk · **D07** DİBS/kamu kira sertifikası · **D08** Foreks (kaldıraçlı) · **D09** Robo-advisor · **D10** Fiziki altın al/teslim · **D11** Yurt dışı hisse · **D12** Kripto erişimi · **D13** Özel bankacılık</sub>

### Blok E — Sigorta & emeklilik

| Banka | E01 | E02 | E03 | E04 | E05 | E06 | E07 | E08 |
|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| HALKB | ● | ● | ● | ● | ● | ● | ◐ | ◐ |
| VAKBN | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| AKBNK | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| ISCTR | ● | ? | ● | ● | ● | ● | ● | ● |
| YKBNK | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| GARAN | ● | ● | ● | ● | ● | ● | ◐ | ● |
| DENIZ | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| QNBFB | ● | ? | ● | ● | ● | ? | ● | ● |
| TEB | ● | ? | ● | ● | ● | ? | ● | ● |
| ING | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| BURGAN | ● | ? | ● | · | ? | ? | ◐ | ◐ |
| ALNTF | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| ODEA | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| SKBNK | ● | ? | ● | ● | ● | ? | ◐ | ◐ |
| ANADOLU | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| FIBA | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| KUVEYT | ● | ● | ● | ● | ● | ● | ● | ● |
| ALBRK | ● | ? | ● | ● | ● | ● | ● | ● |
| TFKB | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| VAKIFK | ● | ? | ● | ● | ? | ? | ◐ | ◐ |
| ZIRAATK | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| EMLAK | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| ENPARA | · | · | · | ● | · | · | ◐ | ? |
| COLENDI | · | · | · | · | · | · | ? | ? |
| ZIRAATD | ● | ? | ● | · | ● | ? | ◐ | ◐ |
| HAYATK | · | · | · | · | · | · | · | · |
| TOMK | · | · | ● | · | · | · | ◐ | · |
| DUNYAK | ● | ? | ● | ● | ● | ● | ◐ | ◐ |
| HSBC | ● | ? | ● | · | ● | ● | ◐ | ◐ |
| ICBCT | ? | ? | ● | ● | ● | ● | · | ? |
| AKTIF | ◐ | ? | ◐ | ◐ | ◐ | ◐ | ◐ | · |

<sub>**E01** BES · **E02** OKS · **E03** Hayat sigortası · **E04** Kasko/trafik · **E05** Konut/DASK · **E06** Tamamlayıcı sağlık · **E07** Grup sigorta şirketi · **E08** Grup emeklilik şirketi</sub>

### Blok F — Kanal & dijital

| Banka | F01 | F02 | F03 | F04 | F05 | F06 | F07 | F08 | F09 | F10 |
|---|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ● | ● | ? | ● | ● | ? | ? | ● |
| HALKB | ● | ● | ● | ● | ◐ | ● | · | ● | ? | ● |
| VAKBN | ● | ● | ● | ● | ● | ● | · | ● | ? | ● |
| AKBNK | ● | ● | ● | ● | ● | ● | ◐ | ● | ? | ● |
| ISCTR | ● | ? | ? | ● | ● | ● | · | ● | ? | ● |
| YKBNK | ● | ● | ● | ● | ? | ● | · | ● | ● | ● |
| GARAN | ● | ● | ● | ● | ● | ● | · | ● | ● | ● |
| DENIZ | ● | ● | ● | ● | ? | ● | · | ● | ? | ● |
| QNBFB | ● | ● | ● | ? | ? | ● | ● | ? | ? | ● |
| TEB | ● | ● | ● | ? | ? | ● | ● | ? | ? | ● |
| ING | ● | ● | ● | ? | ? | ● | · | ● | ? | ● |
| BURGAN | ● | ? | ? | ? | ? | ● | · | ● | ? | ● |
| ALNTF | ● | ● | ● | ? | ? | ● | · | ? | ? | ● |
| ODEA | ● | ● | ● | ● | ? | ● | · | ? | ? | ● |
| SKBNK | ● | ● | ● | ? | ? | ● | · | ● | ? | ● |
| ANADOLU | ● | ? | ? | ● | ? | ● | · | ? | ? | ● |
| FIBA | ● | ● | ● | ● | ? | ● | · | ● | ? | ● |
| KUVEYT | ● | ● | ● | ● | ? | ● | ● | ● | ? | ● |
| ALBRK | ● | ● | ● | ● | ? | ● | ? | ● | ? | ● |
| TFKB | ● | ? | ? | ? | ● | ● | ? | ? | ? | ● |
| VAKIFK | ● | ● | ● | ? | ? | ● | · | ● | ? | ● |
| ZIRAATK | ● | ? | ? | ● | ? | ● | · | ● | ? | ● |
| EMLAK | ● | ● | ● | ? | ? | ● | · | ● | ? | ● |
| ENPARA | ● | ● | ● | ? | ? | ◐ | · | ? | ? | · |
| COLENDI | ● | ● | ● | ? | ? | ◐ | · | ? | ? | · |
| ZIRAATD | ● | ● | ● | ? | ● | ◐ | · | ? | ? | · |
| HAYATK | ● | ● | ● | ? | ? | ◐ | · | ● | ? | · |
| TOMK | ● | ● | ● | ? | ? | ◐ | · | · | ? | · |
| DUNYAK | ● | ● | ● | ? | ? | ? | · | ? | ? | ● |
| HSBC | ● | ? | ? | ? | · | ● | · | ● | ? | ● |
| ICBCT | ● | ? | ? | ? | ? | ● | · | ● | ? | ● |
| AKTIF | ● | ● | ● | ● | ? | ◐ | ● | ● | ? | ◐ |

<sub>**F01** Mobil app (iOS+Android) · **F02** Uzaktan edinim (görüntülü) · **F03** Uçtan uca dijital müşterilik · **F04** Açık bankacılık/API · **F05** YZ/sesli asistan · **F06** Kendi ATM ağı · **F07** Ayrı dijital alt marka · **F08** Tam İngilizce site · **F09** WhatsApp bankacılığı · **F10** Şube ağı</sub>

### Blok G — KOBİ / esnaf

| Banka | G01 | G02 | G03 | G04 | G05 | G06 | G07 | G08 | G09 | G10 | G11 | G12 | G13 | G14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ● | ● | ● | ● | ? | ● | ● | ● | ● | ? | ? | ● |
| HALKB | ● | ● | ? | ? | ● | ● | ● | ● | ● | ? | ● | ? | ● | ● |
| VAKBN | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ◐ | ● | ● | · |
| AKBNK | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| ISCTR | ● | ● | ● | ● | ● | ● | ● | ● | ? | ● | ● | ● | ? | ● |
| YKBNK | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ? | · | ● | ● |
| GARAN | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ? | ? | ● | ● |
| DENIZ | ● | ? | ● | ● | ● | ? | ? | ? | ● | ● | ● | ? | ? | ? |
| QNBFB | ● | ● | ● | ◐ | ● | ● | ● | ● | ? | ● | ● | ● | ? | ? |
| TEB | ● | ? | ● | ● | ● | ● | ● | ● | ◐ | ● | ● | ● | ● | ● |
| ING | ● | ? | ? | ● | ● | ? | ● | ● | ? | ? | ? | ? | ● | ? |
| BURGAN | ● | ? | ? | ● | ? | ? | ? | ? | ? | ● | ● | ? | ? | ? |
| ALNTF | ● | ? | ? | ● | ● | ? | ? | ? | ? | ? | ? | ◐ | ? | ? |
| ODEA | ● | ? | ? | ? | ? | ? | ? | ? | ? | ● | ● | ◐ | ? | ? |
| SKBNK | ● | ● | ● | ● | ● | ● | ● | ● | ? | ● | ● | ? | ? | ? |
| ANADOLU | ● | ● | ● | ? | ● | ● | ● | ● | ● | ● | ? | ? | ? | ● |
| FIBA | ● | ? | ? | ? | ? | ? | ? | ? | ? | ● | ● | ? | ? | ? |
| KUVEYT | ● | ● | ● | ● | ● | ● | ● | ● | ? | ● | ● | ? | ? | ? |
| ALBRK | ● | ● | ● | ● | ● | ● | ● | ● | ? | ● | ● | ? | ? | ? |
| TFKB | ● | ? | ? | ? | ● | ● | ● | ● | ● | ● | ? | ? | ? | ? |
| VAKIFK | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ? | ? | ● |
| ZIRAATK | ● | ● | ? | ● | ● | ● | ● | ? | ? | ? | ● | ? | ? | ? |
| EMLAK | ● | ● | ? | ● | ? | ? | ? | ? | ? | ● | ● | ? | ? | ● |
| ENPARA | ● | ? | ? | ? | ● | ? | ● | ● | ? | ? | ? | ? | ● | ? |
| COLENDI | ● | ? | ? | ? | · | · | · | · | ? | ? | ● | ? | ● | ? |
| ZIRAATD | · | ? | ? | · | · | · | · | · | ? | ? | ? | ? | ● | ? |
| HAYATK | ● | ? | ? | ? | ● | ● | ? | ? | ? | ? | ● | ? | ● | ? |
| TOMK | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| DUNYAK | ● | ? | ? | ● | ? | ? | ? | ? | ? | ? | ● | ? | ? | ? |
| HSBC | ◐ | ? | · | ? | ? | ? | ? | ? | ? | ● | ? | ? | ? | ? |
| ICBCT | ● | ? | ? | ? | ● | ◐ | ? | ? | ? | ? | ? | ? | ? | ? |
| AKTIF | ● | ? | ? | ? | ● | ● | ● | ◐ | ? | ● | ◐ | ◐ | ● | ? |

<sub>**G01** İşletme/esnaf kredisi · **G02** KGF kefaletli · **G03** Tarım/çiftçi · **G04** Ticari taşıt/iş makinesi · **G05** Fiziki POS · **G06** Sanal POS/e-tic. · **G07** Yazarkasa POS (ÖKC) · **G08** Mobil/softPOS · **G09** Üye işyeri taksit · **G10** Çek karnesi/tahsilat · **G11** DBS/tedarikçi fin. · **G12** e-Fatura/ön muhasebe · **G13** KOBİ şubesiz açılış · **G14** Hedefli segment (kadın vb.)</sub>

### Blok H — Dış ticaret

| Banka | H01 | H02 | H03 | H04 | H05 | H06 | H07 |
|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | ● | ? | ? | ● | ● |
| HALKB | ● | ● | ● | ? | ● | ◐ | ● |
| VAKBN | ● | ● | ● | · | ? | ● | ● |
| AKBNK | ● | ● | ● | ● | ● | ● | ● |
| ISCTR | ● | ? | ● | ● | ? | ? | ● |
| YKBNK | ● | ? | ● | ? | ● | ● | ● |
| GARAN | ● | ● | ● | ? | ● | ● | ● |
| DENIZ | ● | ● | ● | ● | ? | ● | ● |
| QNBFB | ● | ● | ● | ● | ? | ● | ◐ |
| TEB | ● | ● | ● | ● | ● | ● | ● |
| ING | ● | ● | ● | ? | ● | ? | ◐ |
| BURGAN | ● | ● | ● | ? | ? | ● | · |
| ALNTF | ● | ● | ● | ? | ● | ◐ | · |
| ODEA | ● | ● | ● | ? | ● | ● | · |
| SKBNK | ● | ● | ● | ? | ? | ● | ● |
| ANADOLU | ● | ● | ● | ? | ? | ? | ● |
| FIBA | ● | ● | ● | ● | ? | ? | ? |
| KUVEYT | ● | ? | ● | ? | ● | ? | ● |
| ALBRK | ? | ? | ● | ? | ? | ? | ? |
| TFKB | ● | ● | ● | ? | ● | ? | ? |
| VAKIFK | ● | ● | ● | ? | ? | ? | · |
| ZIRAATK | ● | ● | ● | ? | ● | ? | · |
| EMLAK | ● | ● | ● | ? | ● | ● | · |
| ENPARA | · | · | · | ? | ? | ? | · |
| COLENDI | · | ? | ● | ? | ? | ? | ? |
| ZIRAATD | · | · | · | ? | ? | ? | · |
| HAYATK | ? | ? | ● | ● | ? | ? | · |
| TOMK | · | · | · | · | · | · | · |
| DUNYAK | ? | ? | ● | ? | ? | ? | · |
| HSBC | ● | ● | ● | ? | ? | ? | ● |
| ICBCT | ● | ● | ● | ? | ? | ? | ● |
| AKTIF | ● | ● | ◐ | ? | ? | ? | · |

<sub>**H01** Akreditif · **H02** Vesaik/kabul-aval · **H03** Teminat mektubu · **H04** e-Teminat mektubu · **H05** Eximbank aracılı · **H06** Forfaiting/iskonto · **H07** Yurt dışı şube/iştirak</sub>

### Blok I — Kurumsal & hazine

| Banka | I01 | I02 | I03 | I04 | I05 | I06 | I07 | I08 | I09 | I10 | I11 | I12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ? | ● | ● | ● | ? | ? | ? | ? | ● | ● | ● |
| HALKB | ● | ● | ● | ● | ● | · | ? | ? | ? | ● | ● | ? |
| VAKBN | ● | ? | ● | ● | ● | · | ? | ? | ? | ● | ● | ? |
| AKBNK | ● | ? | ? | ? | ? | ? | ● | ● | ● | ● | ● | ● |
| ISCTR | ● | ● | ● | ● | ● | ? | ● | ● | ● | ● | ● | ● |
| YKBNK | ● | ● | ● | ● | ● | ? | ● | ● | ● | ● | ● | ? |
| GARAN | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ? | ? |
| DENIZ | ● | ? | ? | ? | ? | ? | ◐ | ● | ? | ● | ● | ● |
| QNBFB | ● | ? | ● | ● | ● | ? | ◐ | ◐ | ◐ | ● | ● | ● |
| TEB | ● | ? | ● | ● | ● | ? | ◐ | ◐ | ◐ | ● | ● | ? |
| ING | ● | ? | ● | ● | ● | ? | ? | ● | ? | ● | ● | ● |
| BURGAN | ● | ? | ● | ● | ● | ? | ? | ? | ? | ● | ● | ? |
| ALNTF | ● | ? | ● | ● | ● | · | ? | ? | ◐ | ● | ? | ? |
| ODEA | ● | ? | ● | ● | ● | ? | ? | ? | ? | ● | ● | ? |
| SKBNK | ● | ● | ● | ● | ● | ? | ? | ? | ? | ? | ? | ? |
| ANADOLU | ? | ? | ● | ● | ● | ? | ? | ● | ? | ● | ? | ? |
| FIBA | ? | ? | ? | ? | ? | ? | ? | ? | ? | ● | ? | ? |
| KUVEYT | ● | ? | ● | · | ? | ? | ? | ? | ? | ● | ● | ● |
| ALBRK | ? | ? | ● | · | ? | ? | ? | ? | ? | ● | ● | ? |
| TFKB | ? | ? | ● | · | ? | ? | ? | ● | ? | ● | ? | ? |
| VAKIFK | ● | ? | ? | · | · | ? | ? | ? | ? | ◐ | ● | ? |
| ZIRAATK | ● | ? | ● | · | · | ? | ? | ? | ? | ● | ? | ● |
| EMLAK | ● | ? | ? | · | · | ? | ? | ? | ? | ● | ● | ● |
| ENPARA | · | · | ? | ? | ? | ? | · | · | · | ? | ● | ? |
| COLENDI | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| ZIRAATD | · | · | ? | ? | ? | ? | · | · | · | ? | ? | ? |
| HAYATK | ? | ? | ? | · | · | ? | ? | ? | ? | ? | ● | ? |
| TOMK | · | · | · | · | · | · | · | · | · | · | · | · |
| DUNYAK | ● | ? | ? | · | · | ? | ? | ? | ? | ? | ? | ● |
| HSBC | ● | ● | ● | ● | ● | ? | ● | ? | ? | ● | ? | ? |
| ICBCT | ● | ● | ● | ● | ? | ? | ◐ | ? | ? | ● | ? | ? |
| AKTIF | ● | ? | ● | ● | ? | ◐ | ● | ? | ? | ◐ | ? | ? |

<sub>**I01** Yatırım/proje finansmanı · **I02** Sendikasyon · **I03** Forward · **I04** Swap · **I05** Opsiyon · **I06** Emtia hedge · **I07** Tahvil/sukuk ihraç · **I08** Halka arz aracılığı · **I09** M&A/kurumsal danışmanlık · **I10** Nakit yön.+ERP/host-to-host · **I11** Bordro/maaş paketi · **I12** Yeşil ticari kredi</sub>

### Blok J — Grup iştirakleri

| Banka | J01 | J02 | J03 | J04 | J05 | J06 | J07 | J08 |
|---|---|---|---|---|---|---|---|---|
| ZIRAAT | ● | ● | · | · | ● | ? | ● | ● |
| HALKB | ? | ● | ? | ? | ● | ? | ? | ◐ |
| VAKBN | ● | ● | · | · | ● | ● | ● | ● |
| AKBNK | ● | ● | ◐ | ◐ | ● | · | ● | ● |
| ISCTR | ● | ● | ● | ● | ● | ● | ● | ● |
| YKBNK | ● | ● | ◐ | ◐ | ● | ● | · | ● |
| GARAN | ● | ● | ◐ | ● | ● | ● | ● | ● |
| DENIZ | ● | ● | · | · | ● | ● | ● | ● |
| QNBFB | ● | ● | ● | ● | ● | ● | ● | ? |
| TEB | ● | ● | ◐ | ◐ | ● | ● | ? | ● |
| ING | ● | ● | · | · | ● | ● | ? | ◐ |
| BURGAN | · | ● | · | · | ● | · | ? | · |
| ALNTF | · | ● | · | · | ● | · | · | · |
| ODEA | · | · | · | · | · | · | · | · |
| SKBNK | ? | ● | · | · | ● | ● | ? | ● |
| ANADOLU | ? | ● | · | · | ● | ● | ? | ● |
| FIBA | ? | ● | ? | ? | ? | ? | ? | ? |
| KUVEYT | ● | · | ● | ● | · | · | · | ● |
| ALBRK | ● | ? | ● | ● | ? | ? | ● | ? |
| TFKB | ● | ● | · | · | ? | ? | ? | ? |
| VAKIFK | ● | · | · | · | · | · | ? | · |
| ZIRAATK | ● | ● | ◐ | ◐ | · | ? | ? | ? |
| EMLAK | ? | ? | ◐ | ◐ | ? | ? | ? | ? |
| ENPARA | ● | ● | ? | ? | ? | ? | ? | ? |
| COLENDI | ? | ? | ? | ? | ? | ? | ? | ? |
| ZIRAATD | ● | ● | · | · | ? | ? | ? | ? |
| HAYATK | · | · | · | · | ? | ? | · | · |
| TOMK | · | · | · | · | · | · | ? | · |
| DUNYAK | ? | ? | ? | ? | ? | ? | ? | ? |
| HSBC | ● | ◐ | · | · | ? | ? | ? | ● |
| ICBCT | ● | ● | · | ? | ? | ? | ? | ◐ |
| AKTIF | ● | ? | ◐ | · | ? | ? | ● | · |

<sub>**J01** Portföy yönetimi · **J02** Aracı kurum · **J03** Sigorta şirketi · **J04** Emeklilik şirketi · **J05** Leasing · **J06** Faktoring · **J07** Ödeme/e-para kuruluşu · **J08** Yurt dışı banka iştiraki</sub>
