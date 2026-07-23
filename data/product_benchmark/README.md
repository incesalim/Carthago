# Ürün benchmark — ham veri

Türk bankalarının ürün rafı: **hangi banka hangi ürünleri satıyor**, bankanın
kendi yayınına dayalı kanıtla. Rapor:
[`docs/knowledge/turkish-bank-product-benchmark-2026-07-22.md`](../../docs/knowledge/turkish-bank-product-benchmark-2026-07-22.md).

## Dosyalar

| Dosya | Ne |
|---|---|
| `<TICKER>.json` | Banka başına 100 öznitelik + kanıt URL'i (32 dosya, 3.200 hücre, 793+ benzersiz URL) |
| `TAXONOMY.md` | Spec: 100 kod / 10 blok, kanıt kuralı, evren tanımı, çıktı şeması |
| `_NARRATIVE.md` | Raporun elle yazılan bölümü (§1–5) |
| `aggregate.py` | Kanıt QC: eksik kod + kanıtsız `yes` avı → `_QC_REPORT.md` |
| `matrix.py` | Matris + yaygınlık analizi (§6–9) → `_MATRIX.md` |
| `build_report.sh` | Üçünü zincirleyip raporu yeniden üretir |
| `_template.html` + `make_artifact.py` | İnteraktif kanıt matrisi (tek dosya, kendi kendine yeten HTML); payload'ı JSON'lardan üretip şablona enjekte eder |
| `benchmark_explorer.html` | Üretilen interaktif görünüm — Claude Artifact olarak yayınlandı |

Yeniden üretim: `./build_report.sh` (rapor) · `python make_artifact.py` (interaktif HTML).
İkisi de deterministik ve idempotent — kaynak JSON'lar değişince yeniden çalıştır.

## Değer alfabesi — ikisi bankaya, ikisi bize dair

`yes` bankanın kendi alan adında kanıtlı ürün · `no` kategori sayfasına bakıldı,
ürün yok (**bankaya** dair olgu) · `partial` iştirak/acentelik/şube-only ·
`unknown` doğrulanamadı (**bize** dair olgu, bankanın eksiği değil).

Bu ayrım raporun tamamını taşır: uydurulmuş bir `no`, dürüst bir `unknown`'dan
çok daha pahalıya patlar — matrisi sessizce yanlışlar.

## ⚠️ İki ölçüm yanlılığı

1. **`unknown` oranı bankaya göre değişiyor** → ham `yes` sayısıyla sıralama az
   araştırılan bankayı dar raflı gösterir. Bu yüzden "kanıt kapsamı" (bize dair)
   ile "doğrulanmış raf" (bankaya dair) ayrı raporlanır.
2. **Yaygınlıkta payda seçilim yanlısı** — araştırmacı ürünü bulamayınca çoğu kez
   `no` değil `unknown` yazdı, bu da küçük paydalarda oranı yukarı çeker. Bu
   nedenle yaygınlık yalnızca ≥22/32 paydalı **58/100** öznitelik için hesaplanır.

## Durum

**32/32 banka TAMAM.** 0 kalite sorunu, 0 eksik hücre, 0 kanıtsız `yes`.

⚠️ Kanıt kuralının bilinen sınırı: otomatik kontrol "URL var mı" diye sorabilir,
"URL bu iddiayı taşıyor mu" diye soramaz. ZIRAATD'nin grup-sigorta iddiası bir
ücret tarifesine dayanıyordu (ürün satışı ≠ şirket sahipliği) ve düzeltildi —
raporun §4.1'i. **Sahiplik iddiaları yalnızca iştirak listesi / KAP ile
kanıtlanmalı**; Blok J bir sonraki turda `kap_ownership` §7'den doldurulacak.
