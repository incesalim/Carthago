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
