#!/usr/bin/env python3
"""Ürün benchmark toplayıcı: 32 <TICKER>.json -> matris + rapor + kalite kontrol.

Kanıt kuralını burada da ZORLARIZ: url'siz bir `yes` veya `partial` KUSURLUDUR,
raporda ayrı listelenir. Eksik kod = sessiz boşluk, ayrıca raporlanır.
"""
import json
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Taksonomi: kod -> (blok, kısa etiket) ------------------------------------
BLOCKS = {
    "A": "Mevduat & birikim",
    "B": "Bireysel kredi",
    "C": "Kart & ödeme",
    "D": "Yatırım",
    "E": "Sigorta & emeklilik",
    "F": "Kanal & dijital",
    "G": "KOBİ / esnaf",
    "H": "Dış ticaret",
    "I": "Kurumsal & hazine",
    "J": "Grup iştirakleri",
}

LABELS = {
    "A01": "Vadeli TL mevduat / katılma", "A02": "Döviz mevduat/katılma",
    "A03": "Altın hesabı", "A04": "Gümüş/platin/diğer maden",
    "A05": "KKM/DDM (hâlâ açık)", "A06": "Çocuk/genç hesabı",
    "A07": "Otomatik/hedefli birikim", "A08": "Emekli maaş promosyonu",
    "A09": "Günlük getirili/esnek hesap",
    "B01": "İhtiyaç kredisi/finansman", "B02": "Konut kredisi/finansmanı",
    "B03": "Taşıt kredisi", "B04": "KMH / ek hesap", "B05": "Karttan taksitli avans",
    "B06": "Yeşil bireysel kredi", "B07": "Eğitim/öğrenci kredisi",
    "B08": "Gayrimenkul teminatlı", "B09": "Borç transferi/yapılandırma",
    "C01": "Kendi kart markası", "C02": "Sanal kart", "C03": "Apple Pay",
    "C04": "Google Wallet", "C05": "Ön ödemeli/hediye kart",
    "C06": "QR ile kartsız ATM", "C07": "FAST + Kolay Adresleme",
    "C08": "Kendi dijital cüzdanı", "C09": "Yurt dışı hızlı transfer",
    "C10": "Ticari/kurumsal kart",
    "D01": "Yatırım fonu", "D02": "TEFAS (3. taraf fonları)",
    "D03": "Grup portföy fonları", "D04": "Hisse alım-satım (kendi kanalı)",
    "D05": "VİOP/vadeli", "D06": "Eurobond/tahvil/sukuk",
    "D07": "DİBS/kamu kira sertifikası", "D08": "Foreks (kaldıraçlı)",
    "D09": "Robo-advisor", "D10": "Fiziki altın al/teslim",
    "D11": "Yurt dışı hisse", "D12": "Kripto erişimi", "D13": "Özel bankacılık",
    "E01": "BES", "E02": "OKS", "E03": "Hayat sigortası", "E04": "Kasko/trafik",
    "E05": "Konut/DASK", "E06": "Tamamlayıcı sağlık", "E07": "Grup sigorta şirketi",
    "E08": "Grup emeklilik şirketi",
    "F01": "Mobil app (iOS+Android)", "F02": "Uzaktan edinim (görüntülü)",
    "F03": "Uçtan uca dijital müşterilik", "F04": "Açık bankacılık/API",
    "F05": "YZ/sesli asistan", "F06": "Kendi ATM ağı",
    "F07": "Ayrı dijital alt marka", "F08": "Tam İngilizce site",
    "F09": "WhatsApp bankacılığı", "F10": "Şube ağı",
    "G01": "İşletme/esnaf kredisi", "G02": "KGF kefaletli", "G03": "Tarım/çiftçi",
    "G04": "Ticari taşıt/iş makinesi", "G05": "Fiziki POS", "G06": "Sanal POS/e-tic.",
    "G07": "Yazarkasa POS (ÖKC)", "G08": "Mobil/softPOS", "G09": "Üye işyeri taksit",
    "G10": "Çek karnesi/tahsilat", "G11": "DBS/tedarikçi fin.",
    "G12": "e-Fatura/ön muhasebe", "G13": "KOBİ şubesiz açılış",
    "G14": "Hedefli segment (kadın vb.)",
    "H01": "Akreditif", "H02": "Vesaik/kabul-aval", "H03": "Teminat mektubu",
    "H04": "e-Teminat mektubu", "H05": "Eximbank aracılı", "H06": "Forfaiting/iskonto",
    "H07": "Yurt dışı şube/iştirak",
    "I01": "Yatırım/proje finansmanı", "I02": "Sendikasyon", "I03": "Forward",
    "I04": "Swap", "I05": "Opsiyon", "I06": "Emtia hedge", "I07": "Tahvil/sukuk ihraç",
    "I08": "Halka arz aracılığı", "I09": "M&A/kurumsal danışmanlık",
    "I10": "Nakit yön.+ERP/host-to-host", "I11": "Bordro/maaş paketi",
    "I12": "Yeşil ticari kredi",
    "J01": "Portföy yönetimi", "J02": "Aracı kurum", "J03": "Sigorta şirketi",
    "J04": "Emeklilik şirketi", "J05": "Leasing", "J06": "Faktoring",
    "J07": "Ödeme/e-para kuruluşu", "J08": "Yurt dışı banka iştiraki",
}
CODES = list(LABELS.keys())

# Küme sırası (rapor sütun/satır düzeni)
CLUSTERS = [
    ("Kamu mevduat", ["ZIRAAT", "HALKB", "VAKBN"]),
    ("Büyük özel", ["AKBNK", "ISCTR", "YKBNK", "GARAN"]),
    ("Yabancı büyük", ["DENIZ", "QNBFB", "TEB"]),
    ("Yabancı orta", ["ING", "BURGAN", "ALNTF", "ODEA"]),
    ("Özel orta", ["SKBNK", "ANADOLU", "FIBA"]),
    ("Katılım özel", ["KUVEYT", "ALBRK", "TFKB"]),
    ("Katılım kamu", ["VAKIFK", "ZIRAATK", "EMLAK"]),
    ("Dijital mevduat", ["ENPARA", "COLENDI", "ZIRAATD"]),
    ("Dijital katılım", ["HAYATK", "TOMK", "DUNYAK"]),
    ("İhtisas/niş", ["HSBC", "ICBCT", "AKTIF"]),
]
ORDER = [t for _, banks in CLUSTERS for t in banks]

GLYPH = {"yes": "●", "partial": "◐", "no": "·", "unknown": "?"}


def load():
    data = {}
    for path in glob.glob(os.path.join(HERE, "*.json")):
        name = os.path.basename(path)
        if name.startswith("_"):
            continue
        with open(path, encoding="utf-8") as f:
            try:
                d = json.load(f)
            except Exception as e:
                print(f"[BOZUK JSON] {name}: {e}", file=sys.stderr)
                continue
        data[d["ticker"]] = d
    return data


def cell(d, code):
    a = d.get("attributes", {}).get(code)
    if not a:
        return None
    return a


def main():
    data = load()
    present = [t for t in ORDER if t in data]
    missing_banks = [t for t in ORDER if t not in data]

    problems = []      # (ticker, code, issue)
    missing_codes = {} # ticker -> [codes]
    for t in present:
        d = data[t]
        mc = [c for c in CODES if c not in d.get("attributes", {})]
        if mc:
            missing_codes[t] = mc
        for c in CODES:
            a = cell(d, c)
            if a is None:
                continue
            v = a.get("v")
            if v not in GLYPH:
                problems.append((t, c, f"geçersiz değer '{v}'"))
            if v in ("yes", "partial") and not a.get("url"):
                problems.append((t, c, f"{v} ama url yok"))

    # --- rapor ---
    out = []
    out.append("# Türk Bankaları Ürün Benchmark — kanıt kontrolü\n")
    out.append(f"Bankalar: {len(present)}/{len(ORDER)} dosya bulundu.")
    if missing_banks:
        out.append(f"**Eksik dosya:** {', '.join(missing_banks)}")
    out.append("")

    # kapsama tablosu
    out.append("## Banka kapsama özeti\n")
    out.append("| Banka | yes | partial | no | unknown | kanıtsız yes/partial | eksik kod |")
    out.append("|---|--:|--:|--:|--:|--:|--:|")
    for t in present:
        d = data[t]
        counts = {"yes": 0, "partial": 0, "no": 0, "unknown": 0}
        nourl = 0
        for c in CODES:
            a = cell(d, c)
            if not a:
                continue
            v = a.get("v")
            if v in counts:
                counts[v] += 1
            if v in ("yes", "partial") and not a.get("url"):
                nourl += 1
        mc = len(missing_codes.get(t, []))
        out.append(f"| {t} | {counts['yes']} | {counts['partial']} | {counts['no']} "
                   f"| {counts['unknown']} | {nourl} | {mc} |")
    out.append("")

    # kalite sorunları
    out.append("## Kalite sorunları (düzeltilmeli)\n")
    if missing_codes:
        out.append("**Eksik kodlar (sessiz boşluk):**")
        for t, cs in missing_codes.items():
            out.append(f"- {t}: {len(cs)} eksik → {', '.join(cs)}")
    if problems:
        out.append("\n**Kanıt/değer sorunları:**")
        for t, c, iss in problems:
            out.append(f"- {t} {c} ({LABELS[c]}): {iss}")
    if not missing_codes and not problems:
        out.append("Yok — tüm hücreler dolu ve kanıtlı. ✅")
    out.append("")

    with open(os.path.join(HERE, "_QC_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out))
    print(f"\n[yazıldı] _QC_REPORT.md — {len(problems)} sorun, "
          f"{sum(len(v) for v in missing_codes.values())} eksik hücre")


if __name__ == "__main__":
    main()
