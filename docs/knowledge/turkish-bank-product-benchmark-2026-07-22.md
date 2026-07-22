# Türk Bankaları Ürün Benchmark — hangi banka hangi ürünlere sahip

**Tarih:** 2026-07-22 · **Durum:** 32/32 banka TAMAM
· **Kapsam:** 100 öznitelik × 32 banka = 3.200 hücre, hepsi kanıt URL'li

---

## 1. Neden bu çalışma, ve ne sorduk

Bu depodaki her şey bugüne kadar bankaların **finansallarını** ölçtü: bilanço,
P&L, sermaye, likidite, kredi kalitesi. Hepsi çıktı tarafı — bir bankanın ne
kazandığı. Hiçbiri **ne sattığını** söylemiyor. Ürün rafı, o finansalların
girdisidir: bir bankanın komisyon geliri hangi ürünlerden gelebilir, hangi
segmente girebilir, nerede yapısal olarak rekabet dışıdır.

Sorulan soru dar ve cevaplanabilir olacak şekilde şöyle kuruldu:

> Bir müşteri bu bankaya gittiğinde **hangi ürünü alabilir, hangisini
> alamaz** — ve bunu bankanın kendi yayınladığı belgeyle kanıtlayabiliyor
> muyuz?

Bu, "hangi banka daha iyi" sorusu **değildir**. Raf genişliği bir kalite
ölçüsü değil, bir **strateji** ölçüsüdür: dar raflı bir dijital banka bilinçli
olarak dardır, geniş raflı bir kamu bankası bilinçli olarak geniştir.

### Neden 100 öznitelik, neden bu 100

Taksonomi üç ilkeyle kuruldu:

1. **Ayrıştırıcılık.** Her bankada olan bir ürün (vadesiz hesap) sıfır bilgi
   taşır. Rafın değeri, bankaların ayrıştığı yerdedir. Bu yüzden listeye hem
   "masaya giriş bileti" kalemleri (kontrol amaçlı) hem de kripto, robo-danışman,
   softPOS, platin hesabı, yurt dışı hisse gibi ayrıştırıcılar kondu.
2. **Segment bütünlüğü.** Kullanıcı kapsamı bireysel + KOBİ + ticari/kurumsal
   olarak seçti, çünkü Türk bankalarının çoğu için asıl fark KOBİ ve dış
   ticaret rafında ortaya çıkıyor — bireysel raf büyük ölçüde yakınsamış durumda.
3. **Yapısal belirleyicilik.** Blok J (grup iştirakleri) ürün değil, ürünün
   *sınırıdır*: kendi portföy şirketi olmayan banka fon üretemez, sadece
   dağıtır. Bu blok olmadan matris "neden" sorusunu cevaplayamaz.

10 blok: mevduat/birikim (9), bireysel kredi (9), kart/ödeme (10), yatırım (13),
sigorta/emeklilik (8), kanal/dijital (10), KOBİ/esnaf (14), dış ticaret (7),
kurumsal/hazine (12), grup iştirakleri (8).

### Evren: 32 banka, neden bu 32

38 bankalık denetim evreninden **6'sı dışarıda**: TAKAS (takas/saklama kurumu,
müşteri ürün rafı yok), EXIM (ihracat kredi ajansı), TSKB, KLNMA, PASHA
(toptancı kalkınma/yatırım bankaları), ATBANK (toptancı). Bunların matrisi
tanım gereği boş çıkardı ve ortalamaları bozardı.

---

## 2. Yöntem

11 araştırma hattı paralel çalıştı, hepsi **aynı** 100-kodluk spec'i doldurdu.
Kaynak önceliği: bankanın kendi alan adı → ücret tarifesi/ürün sayfası →
faaliyet raporu → KAP. Üçüncü taraf karşılaştırma siteleri kanıt sayılmadı.

### 2.1 Kanıt kuralı

Dört değer, dördü de farklı şey söyler — ve ikisi **bankaya**, ikisi **bize**
dair olgudur. Bu ayrım raporun tamamını taşıyor:

| Değer | Kime dair | Şartı |
|---|---|---|
| `yes` | bankaya | Bankanın kendi alan adında ürünü gösteren sayfa. URL zorunlu. |
| `no` | **bankaya** | Kategori sayfasına bakıldı, ürün orada yok. URL = bakılan sayfa. |
| `partial` | bankaya | Var ama kısıtlı: iştirak üzerinden, acentelik, sadece şubede, segment-only. |
| `unknown` | **bize** | Doğrulanamadı — sayfa yok, site bloklu. Bankanın eksiği değil, bizim. |

**Sonuç:** 3.200 hücrenin tamamı dolu, **kanıtsız tek bir `yes`/`partial` yok**
(0/3.200), 793 benzersiz kanıt URL'i. Matristeki her "var" tıklanabilir bir
banka sayfasına dayanıyor.

⚠️ Ama bu kuralın bir sınırı var ve çalışma sırasında bu sınıra çarptık:
**"URL var" ile "URL iddiayı destekliyor" aynı şey değildir.** Otomatik kontrol
yalnızca birincisini görebilir. Gerçek bir vaka §4.1'de — bir grup-sahipliği
iddiası bir *ücret tarifesi* sayfasına dayandırılmıştı; sayfa ürünün satıldığını
kanıtlıyordu, şirketin sahipliğini değil. Kanıt zincirinin zayıf halkası budur.

### 2.2 İki ölçüm yanlılığı — tablolara bakmadan önce okunmalı

Bu iki tuzak fark edilmezse rapor sessizce yanlış okunur.

**(a) `unknown` oranı bankadan bankaya değişiyor → ham `yes` sayısı yanıltıcı.**
Araştırma derinliği eşit değildi (bir noktada oturumun web arama bütçesi
tükendi ve sonraki hatlar yalnız doğrudan sayfa çekerek ilerledi). GARAN'da 9
`unknown` varken DUNYAK'ta 57 var. Ham `yes` sayısıyla sıralama yapmak,
**az araştırılan bankayı dar raflı gibi gösterir.** Bu bir ölçüm hatasıdır,
bulgu değil. Bu yüzden iki ayrı sayı raporlanır:

- **kanıt kapsamı** = (yes+no+partial)/100 → *bize* dair, araştırma derinliği
- **doğrulanmış raf** = (yes + 0,5×partial)/doğrulanan → *bankaya* dair

Sıralama **rafa** göre yapılır; kapsamı %65'in altındaki bankalar ⚠ ile
işaretlidir ve sıralamadaki yerleri geçicidir.

**(b) Öznitelik yaygınlığında payda seçilim yanlısı.** Araştırmacılar egzotik
bir ürünü bulamadığında çoğu kez `no` değil `unknown` yazdı (kategori sayfası
o ürünü hiç anmıyor). Bu, küçük paydalarda yaygınlığı **yapay olarak yukarı**
çeker: ham hesapta "WhatsApp bankacılığı %100 yaygın" çıkıyordu — 2 bankada
doğrulanmış, 28'i `unknown` olduğu için. Bu yüzden yaygınlık **yalnızca en az
22/32 bankada doğrulanabilen öznitelikler için** hesaplandı. **100 öznitelikten
58'i** bu eşiği geçiyor; kalan 42'si ayrı bir "kanıt yetersiz" listesinde ve
oranları **hesaplanmadı** — oradaki `var` sayıları birer **alt sınırdır**.

---

## 3. Bulgular

### 3.1 Bireysel raf yakınsadı; rekabet artık yatırım, ödeme ve iştirak yapısında

Doğrulanan 58 özniteliğin **19'u %90+ yaygınlıkta**: ihtiyaç kredisi, mobil
uygulama, sanal kart, FAST, vadeli TL/döviz mevduat, altın hesabı, kendi kart
markası, yatırım fonu, uzaktan müşteri edinimi, günlük getirili hesap. Bunlar
**masaya giriş bileti** — burada rekabet yok, sadece eşik var. 23 öznitelik
%75–90 bandında (yaygın ama evrensel değil), ve asıl rekabet **14 özniteliğin**
%25–75 bandında yaşanıyor.

Gerçek ayrışma üç yerde:
- **Yatırım derinliği:** kripto 6 banka (18 `no`), kaldıraçlı foreks yalnızca
  **1** banka (Burgan), yurt dışı hisse dar bir azınlık.
- **Ödeme mimarisi:** kendi dijital cüzdanı 7 banka + 3 kısmi, softPOS,
  yazarkasa POS.
- **Grup yapısı** — aşağıdaki iki bulgu.

### 3.2 En büyük yapısal bulgu: bankasürans üretim değil, dağıtım

Sigorta satan 29 bankadan **yalnızca 5'inde** grup içi sigorta şirketi var;
**24'ü acentelik** yapıyor (`partial`). Emeklilikte tablo aynı: 6 sahiplik,
20 acentelik. İştirak tarafından bakıldığında daha da net: 32 bankanın
**16'sında sigorta şirketi iştiraki yok** (J03 `no`), 16'sında emeklilik
şirketi iştiraki yok (J04 `no`).

Yani Türk bankacılığında sigorta, ezici çoğunlukta **başkasının ürününü
dağıtmak**tır. Bu, komisyon geliri kalitesi açısından belirleyici: acente
komisyon alır, sahip teknik kâr da alır.

Sahiplik yapanlar: **İş Bankası** (Anadolu Sigorta + Anadolu Hayat + Milli
Reasürans — matristeki en dikey-entegre grup, Blok J'nin 8 kategorisinin
hepsi gerçek iştirak), **QNB** (Cigna Finans), **Kuveyt Türk** (Neova Katılım
Sigorta + Katılım Emeklilik), **Albaraka** (Bereket Sigorta), **Garanti**
(hayat tarafında Garanti BBVA Emeklilik; elementerde Eureko acenteliği),
**TEB** (grup ortağı BNP Paribas Cardif — doğrudan iştirak değil).

Karşı örnek olarak **Akbank**: sigorta/emeklilik Sabancı *kardeş* şirketleri
(Aksigorta/AgeSA) üzerinden — aynı holding, ama bankanın iştiraki değil, yani
acentelik. Yapı Kredi 2013'te sigortayı Allianz'a satmış; bugün bankasürans.

**Kamu tarafında bu bir tercih değil, bir devlet politikasının sonucu.** Üç kamu
mevduat bankasının (Ziraat, Halkbank, VakıfBank) **hiçbirinde** grup içi sigorta
veya emeklilik şirketi yok — Ziraat Sigorta, Halk Sigorta ve Vakıf Emeklilik
2020'de tek çatı altında **Türkiye Sigorta** ve **Türkiye Hayat ve Emeklilik**
olarak birleştirildi. Üç banka da bugün kendi eski sigortacısının *acentesi*.
Bu, üç bankanın da iştirak listesinde bağımsız olarak doğrulandı (VakıfBank'ınki
pay oranlarıyla birlikte). Kamu bankalarının bancassurance komisyonu artık
tamamen dağıtım geliridir; teknik kâr başka bir bilançodadır.

### 3.3 Dijital bankalar dar rafla yarışıyor — ve bu bilinçli

Doğrulanmış raf sıralamasının son beşi tamamen dijital/yeni giren:
TOMK %19, COLENDI %27, HAYATK %41, ZIRAATD %46, ENPARA %49. 32 bankanın
tamamında bu beş sıra kesintisiz — hiçbir şubeli banka bu bandın altına inmiyor.

Bu bir zayıflık raporu değil, bir **strateji tespiti**: dar raf, dar maliyet.
İçlerinde iki sürpriz var:
- **COLENDI** bireysel tarafta en dar rafa sahip (kredi kartı yok, yalnız sanal
  banka kartı, yatırım/sigorta yok) ama **KOBİ tarafı beklenmedik derin**:
  spot/taksitli ticari kredi, teminat mektubu, tedarikçi finansmanı.
- **ENPARA** dijitallerin en genişi ve gümüş hesabı gibi akranlarında olmayan
  bir kalemi var; Şirketim ile uçtan uca dijital KOBİ + POS sunuyor.

### 3.4 Katılım bankalarındaki `no`'lar rekabetçi değil, doktrinel

KMH, karttan taksitli nakit avans, kaldıraçlı foreks, swap ve opsiyon 9 katılım
bankasının tamamında `no` — ürün eksikliği değil, **katılım bankacılığı
ilkelerinin sonucu**. Matrisi okurken bu blok ayrı değerlendirilmeli; aksi
halde katılım bankaları yapay olarak "eksik" görünür.

Buna karşılık katılım tarafı iki yerde mevduat bankalarını **geçiyor**:
- **Kıymetli maden:** Kuveyt Türk (gümüş + platin + ATM'den 1 gr fiziki altın
  teslimi), Emlak Katılım (gümüş + platin + Altın Çocuk + Altuni Şube), Dünya
  Katılım (altın/gümüş/platin/paladyum + fiziki teslimat).
- **Açık bankacılık:** Kuveyt Türk'ün PSD2 uyumlu API Market'i (455 API) sektörde
  en olgun raflardan.

Ayrıca **Emlak Katılım'ın "Gönlüne Göre" sıfır kâr oranlı konut finansmanı**
(önce peşinat biriktir, sonra finansman) matriste eşi olmayan tek ürün.

### 3.5 Kart programları: kendi markası azınlıkta

29 bankanın kendi kart markası var ama bunların önemli kısmı **franchise**:
Bonus'u Garanti dışında Denizbank, TEB, ING, Alternatifbank, Şekerbank
kullanıyor; World'ü Yapı Kredi dışında Albaraka. Yani "kendi kart markası"
hücresi `yes` olsa da, arkasındaki program mimarisi ortak. Rafın gerçek
ayrıştırıcısı kart markası değil, **kendi dijital cüzdanı**: ZiraatPay, Juzdan
(Akbank), World Pay, GarantiPay, fastPay (Denizbank), N Kolay (Aktif) — ve
QNB Cüzdan'ın **5 Ocak 2026'da kapatılmış olması**, yani bir raf geri çekilmesi.

### 3.6 Raf geri çekilmeleri, ilerlemeler kadar bilgilendirici

Matris üç net daralma yakaladı:
- **HSBC Türkiye** bireysel kredi rafını daraltmış: `/krediler` sayfasında
  konut ve taşıt kredisi **yeni satışta yok**.
- **QNB Cüzdan** kapatıldı (Ocak 2026).
- **KKM/DDM** tasfiye ediliyor: 5 bankada hâlâ listeleniyor, 14'ünde kapalı.

### 3.7 Beklentiyi bozan bankalar

- **DUNYAK (Dünya Katılım)** "dijital katılım bankası" varsayımıyla
  sınıflandırılmıştı; araştırma **ülke geneli fiziki şube ağı, kiralık kasa ve
  kurumsal internet şubesi** olan tam kapsamlı bir katılım bankası olduğunu
  gösterdi. Küme etiketi yanlıştı — matris düzeltti.
- **BURGAN**, orta ölçekli bir banka için sıra dışı yatırım rafı sunuyor:
  15 ülke/18 borsada yurt dışı hisse, **kaldıraçlı foreks (matristeki tek `yes`)**,
  robo-danışman ve dört metalli kıymetli maden.
- **ANADOLU**, "ticari ağırlıklı küçük banka" beklentisine karşın Hollanda'da
  banka iştiraki (Anadolubank Nederland N.V.), kripto platform transferi ve
  BaaS/servis bankacılığı sunuyor.
- **AKTIF**, mevduat toplamayan bir yatırım bankası olmasına rağmen gerçek bir
  kredi kartı (Passo/Passolig), UPT yurt dışı transfer, PAVO yazarkasa POS ve
  kripto platformu ile perakende-benzeri bir ekosistem işletiyor.
- **ODEA**, neredeyse hiç finansal iştiraki olmadan (yalnız Odeatech) tüm rafı
  banka bünyesinde sunuyor — matristeki en "tek gövde" yapı.

---

## 4. Veri kalitesi: çelişkiler ve boşluklar

Bu bölüm raporun güvenilirlik sınırıdır; atlanmamalı.

### 4.1 Çözülen çelişki — ve ortaya çıkardığı yöntem dersi

**Ziraat grubu sigorta sahipliği. ÇÖZÜLDÜ, veri düzeltildi.**

`ZIRAAT` dosyası E07'yi `partial` işaretleyip "Ziraat Sigorta 2020'de Türkiye
Sigorta'ya devroldu, grup dışı" derken, `ZIRAATD` (Ziraat Dinamik) aynı grup
için E07/E08/J03/J04'ü `yes` + "grup sigorta şirketi" diye işaretlemişti. İkisi
aynı anda doğru olamazdı.

Çözüm, iddiaların **kanıtlarını karşılaştırınca** çıktı:

| | ZIRAATD'nin dayanağı | ZIRAAT + VAKBN'in dayanağı |
|---|---|---|
| Sayfa | ürün ve hizmet **ücret tarifesi** | bankanın **iştirak listesi** (VAKBN'inki pay oranlarıyla) |
| Ne kanıtlar | sigorta ürünü *satıldığını* | grup şirketi *olup olmadığını* |
| İddiaya uygun mu | **hayır** | evet |

ZIRAATD'nin dört hücresi `partial`/`no` olarak düzeltildi ve düzeltme gerekçesi
hücrelerin `note` alanına yazıldı (`data/product_benchmark/ZIRAATD.json`).
HALKB + VAKBN'in bağımsız araştırması aynı deseni üçüncü kez doğruladı —
bulgu 3.2'nin son paragrafı bu düzeltmeden doğdu.

**Ders (kanıt kuralının sınırı):** otomatik kontrol "URL var mı" diye sorabilir,
"URL bu iddiayı taşıyor mu" diye soramaz. Bir ücret tarifesi, bir ürünün
satıldığının kanıtıdır; onu üreten şirketin sahipliğinin değil. **Sahiplik
iddiaları yalnızca iştirak listesi / KAP formu ile kanıtlanmalı** — sonraki
turda Blok J'nin tamamı bu yüzden `kap_ownership` §7'den doldurulmalı (§5.2).

### 4.2 Zayıf paydalı öznitelikler (49 adet)

Yaygınlık hesaplanmayan 49 öznitelik arasında en çok ilgi çekenler ve
doğrulanabilen banka sayıları: Apple Pay (20), kendi dijital cüzdanı (19),
yurt dışı hisse (20), softPOS (19), yazarkasa POS (19), leasing iştiraki (18),
opsiyon (19). Bunlar için `var` sayısı **alt sınırdır** — gerçek yaygınlık
daha yüksek olabilir.

Apple Pay özel bir not hak ediyor: 2 banka kendi alan adında kanıt buldu
(Yapı Kredi — ücret tarifesinde adı geçiyor; Garanti BBVA), 18 banka kendi
sayfasında bulamadı. `no` gerekçelerinin çoğu usulüne uygun ("kendi alan
adında Apple Pay sayfası yok"), ancak bir kısmı piyasa-geneli varsayımdan
türetilmiş. Bulgu muhtemelen gerçek (Türkiye'de sınırlı banka desteği) ama
tek turluk hedefli doğrulama gerektiriyor.

### 4.3 Evren tamamlandı

**32/32 banka tamam.** HALKB ve VAKBN ilk turda oturum limitine takılmıştı;
ikinci bir hatla tamamlandılar ve kamu kümesi artık üç bankayla temsil ediliyor
(bu tamamlanma, §3.2'deki kamu bancassurance bulgusunu mümkün kıldı).

Kalan tek `unknown` yoğunluğu HALKB'in iştirak bloğunda: `/tr/bankamiz/ortakliklar`
sayfası JavaScript ile yükleniyor ve doğrudan çekimde boş gövde dönüyor —
bu yüzden HALKB'in J bloğunun 5/8'i `unknown`. Bu, §5.2'deki KAP çözümünün
gerekçelerinden biri.

### 4.4 Sistematik boşluk: Blok I ve Blok J

Kurumsal/hazine (I) ve grup iştirakleri (J) bloklarında `unknown` oranı belirgin
şekilde yüksek. Nedeni yapısal: bankalar türev ve sendikasyon ürünlerini kalem
kalem web sitesinde listelemiyor, birçoğunun iştirak sayfası ya yok ya 404
(FIBA, EMLAK). Bu blokların doğru kaynağı web sitesi değil, **KAP genel bilgi
formu §7** — ve o veri bu depoda `kap_ownership` tablosunda zaten mevcut.
Sonraki turda J bloğu web araştırması yerine oradan doldurulmalı; hem daha
güvenilir hem sıfır maliyetli.

---

## 5. Sonraki tur (öncelik sırasıyla)

**5.1** ~~HALKB + VAKBN'i tamamla~~ — **YAPILDI** (§4.3).
**5.2** ~~Ziraat sigorta çelişkisini çöz~~ — **YAPILDI**, veri düzeltildi (§4.1).

**5.3 Blok J'yi `kap_ownership` §7'den yeniden doldur.** En yüksek getirili
adım. 8 öznitelik × 32 banka; veri zaten D1'de, deterministik ve bedava. Üç
ayrı gerekçe aynı yere işaret ediyor: (a) §4.1'in dersi — sahiplik iddiası
web sayfasıyla kanıtlanamaz; (b) HALKB'in iştirak sayfası JS ile yükleniyor,
FIBA ve EMLAK'ınki 404 veriyor; (c) J bloğu `unknown` oranı en yüksek bloklardan.

**5.4 Zayıf paydalı 42 özniteliği hedefli doğrula** — öncelik gerçek
ayrıştırıcılarda: POS ailesi (G06–G08), dijital cüzdan (C08), Apple/Google
cüzdan (C03/C04). Bunlar `no`-yerine-`unknown` yanlılığının en yoğun olduğu
yer ve tam da rekabetin görüldüğü bant.

**5.5 Kurumsal/hazine (Blok I) için kaynak değiştir.** Bankalar türev ve
sendikasyon ürünlerini web sitesinde kalem kalem listelemiyor; bu blok için
doğru kaynak ürün sayfası değil, faaliyet raporu veya yatırımcı sunumu.

**5.6 Ancak bundan sonra:** bu matrisin kalıcı bir veri hattına ve `/products`
sayfasına taşınıp taşınmayacağına karar ver. Bakım maliyeti gerçek — banka
siteleri sık değişiyor, ürün varlığı ikili bir sinyal olarak gürültülü — ve
karar bu turun bulgularıyla verilmeli, peşinen değil.

---
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
