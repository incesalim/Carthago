# Türk Bankaları Ürün Benchmark — hangi banka hangi ürünlere sahip

**Tarih:** 2026-07-22 · **Durum:** 30/32 banka tamam (HALKB + VAKBN devam ediyor)
· **Kapsam:** 100 öznitelik × 30 banka = 3.000 hücre, hepsi kanıt URL'li

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

**Sonuç:** 3.000 hücrenin tamamı dolu, **kanıtsız tek bir `yes`/`partial` yok**
(0/3.000). Bu, çalışmanın en önemli çıktısı — matristeki her "var", tıklanabilir
bir banka sayfasına dayanıyor.

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
21/30 bankada doğrulanabilen öznitelikler için** hesaplandı. **100 öznitelikten
51'i** bu eşiği geçiyor; kalan 49'u ayrı bir "kanıt yetersiz" listesinde ve
oranları **hesaplanmadı** — oradaki `var` sayıları birer **alt sınırdır**.

---

## 3. Bulgular

### 3.1 Bireysel raf yakınsadı; rekabet artık yatırım, ödeme ve iştirak yapısında

Doğrulanan 51 özniteliğin 16'sı %90+ yaygınlıkta: ihtiyaç kredisi, mobil
uygulama, sanal kart, FAST, vadeli TL/döviz mevduat, altın hesabı, kendi kart
markası, yatırım fonu, uzaktan müşteri edinimi, günlük getirili hesap. Bunlar
**masaya giriş bileti** — burada rekabet yok, sadece eşik var.

Gerçek ayrışma üç yerde:
- **Yatırım derinliği:** VİOP %64, kripto %27, foreks %8, yurt dışı hisse (alt
  sınır 4 banka).
- **Ödeme mimarisi:** kendi dijital cüzdanı, softPOS, yazarkasa POS.
- **Grup yapısı** — aşağıdaki bulgu.

### 3.2 En büyük yapısal bulgu: bankasürans üretim değil, dağıtım

Sigorta satan 27 bankadan **yalnızca 6'sında** grup içi sigorta şirketi var;
**21'i acentelik** yapıyor (`partial`). Emeklilikte tablo aynı: 7 sahiplik,
17 acentelik.

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

### 3.3 Dijital bankalar dar rafla yarışıyor — ve bu bilinçli

Doğrulanmış raf sıralamasının son beşi tamamen dijital/yeni giren:
TOMK %19, COLENDI %27, HAYATK %41, ENPARA %49, ZIRAATD %52.

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

### 4.1 Çözülmemiş çelişki (1 adet)

**Ziraat grubu sigorta sahipliği.** `ZIRAAT` dosyası E07'yi `partial` işaretleyip
"Ziraat Sigorta 2020'de Türkiye Sigorta'ya devroldu, grup dışı" diyor; `ZIRAATD`
(Ziraat Dinamik) aynı grup için E07/J03'ü `yes` + "grup sigorta şirketi (Ziraat
Sigorta)" diye işaretlemiş. **İkisi aynı anda doğru olamaz.** ZIRAAT'in notu
daha spesifik ve tarihsel olarak doğrulanabilir görünüyor; bir sonraki turda
tek kaynaktan teyit edilip ZIRAATD düzeltilmeli. Bulgu 3.2'deki "6 sahiplik"
sayısı bu çelişkiye duyarlıdır (5 veya 6).

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

### 4.3 Eksik bankalar (2 adet)

**HALKB ve VAKBN** bu turda tamamlanamadı — araştırma hattı oturum limitine
takıldı. Kamu mevduat kümesi şu an yalnız ZIRAAT ile temsil ediliyor, dolayısıyla
**küme düzeyindeki kamu bankası genellemeleri bu iki banka eklenene kadar
yapılmamalı.**

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

1. **HALKB + VAKBN'i tamamla** — kamu kümesi eksik.
2. **Blok J'yi `kap_ownership` §7'den yeniden doldur** — 8 öznitelik × 32 banka,
   web yerine kendi veritabanımızdan, deterministik.
3. **Ziraat sigorta çelişkisini çöz** (§4.1).
4. **Zayıf paydalı 49 özniteliği hedefli doğrula** — özellikle POS ailesi
   (G06–G08) ve dijital cüzdan (C08), çünkü bunlar gerçek ayrıştırıcı.
5. Ancak bundan sonra: bu matrisin kalıcı bir veri hattına ve `/products`
   sayfasına taşınıp taşınmayacağına karar ver. Bakım maliyeti gerçek —
   banka siteleri sık değişiyor — ve karar bu turun bulgularıyla verilmeli.

---
