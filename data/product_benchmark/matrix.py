#!/usr/bin/env python3
"""Benchmark matrisi + analiz.

METODOLOJİK UYARI (rapora da girer):
`unknown` oranı bankadan bankaya çok değişiyor. Ham `yes` sayısıyla sıralama
yapmak, AZ ARAŞTIRILAN bankayı DAR RAFLI gibi gösterir — bu bir ölçüm
yanlılığıdır, bulgu değil. Bu yüzden iki ayrı şey raporlanır:
  - kanıt kapsamı   = (yes+no+partial)/100  → BİZE dair (araştırma derinliği)
  - doğrulanmış raf = yes/(yes+no+partial)  → BANKAYA dair (raf genişliği)
Sıralama ikincisiyle yapılır, ama kapsamı düşük bankalar işaretlenir.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aggregate import CODES, LABELS, CLUSTERS, ORDER, BLOCKS, load, GLYPH  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
LOW_COVERAGE = 0.65   # bu eşiğin altı "kapsamı düşük" damgası yer


def val(d, code):
    a = d.get("attributes", {}).get(code)
    return (a or {}).get("v", "unknown")


def main():
    data = load()
    present = [t for t in ORDER if t in data]
    out = []

    # ---------- 1. banka bazlı özet ----------
    stats = {}
    for t in present:
        c = Counter(val(data[t], code) for code in CODES)
        verified = c["yes"] + c["no"] + c["partial"]
        stats[t] = {
            "yes": c["yes"], "no": c["no"], "partial": c["partial"],
            "unknown": c["unknown"], "verified": verified,
            "coverage": verified / len(CODES),
            "shelf": (c["yes"] + 0.5 * c["partial"]) / verified if verified else 0.0,
        }

    out.append("## 6. Banka bazlı: kanıt kapsamı vs doğrulanmış raf\n")
    out.append("`kapsam` = kaç hücreyi doğrulayabildik (BİZE dair). "
               "`raf` = doğrulanan hücrelerin kaçı ürün var (BANKAYA dair, "
               "partial=0.5). Sıralama rafa göre; kapsamı %65 altı ⚠ ile işaretli.\n")
    out.append("| # | Banka | Küme | yes | part | no | unk | kapsam | raf |")
    out.append("|--:|---|---|--:|--:|--:|--:|--:|--:|")
    cl_of = {t: name for name, banks in CLUSTERS for t in banks}
    ranked = sorted(present, key=lambda t: -stats[t]["shelf"])
    for i, t in enumerate(ranked, 1):
        s = stats[t]
        flag = " ⚠" if s["coverage"] < LOW_COVERAGE else ""
        out.append(f"| {i} | **{t}** | {cl_of[t]} | {s['yes']} | {s['partial']} "
                   f"| {s['no']} | {s['unknown']} | {s['coverage']*100:.0f}%{flag} "
                   f"| **{s['shelf']*100:.0f}%** |")
    out.append("")

    # ---------- 2. öznitelik bazlı yaygınlık ----------
    out.append("## 7. Öznitelik bazlı yaygınlık — ne ortak, ne ayrıştırıcı\n")
    out.append("`var` = yes sayısı, `yok` = no sayısı, `?` = doğrulanamayan. "
               "Yaygınlık = var/(var+yok+kısmi), yalnız doğrulanan hücreler üzerinden.\n")
    rows = []
    for code in CODES:
        c = Counter(val(data[t], code) for t in present)
        ver = c["yes"] + c["no"] + c["partial"]
        pen = (c["yes"] + 0.5 * c["partial"]) / ver if ver else None
        rows.append((code, c, ver, pen))

    def fmt_rows(rs):
        o = ["| Kod | Öznitelik | var | kısmi | yok | ? | yaygınlık |",
             "|---|---|--:|--:|--:|--:|--:|"]
        for code, c, ver, pen in rs:
            p = f"{pen*100:.0f}%" if pen is not None else "—"
            o.append(f"| {code} | {LABELS[code]} | {c['yes']} | {c['partial']} "
                     f"| {c['no']} | {c['unknown']} | {p} |")
        return o

    # ── YANLILIK DÜZELTMESİ ──────────────────────────────────────────────
    # Araştırmacılar egzotik özniteliklerde ürünü BULAMAYINCA çoğu zaman `no`
    # değil `unknown` yazdı (kategori sayfasında o ürün hiç anılmıyor).
    # Sonuç: payda küçüldükçe yaygınlık YUKARI sapar — "WhatsApp bankacılığı
    # %100 yaygın (2/2 doğrulanmış, 28 unknown)" gibi saçma bir satır çıkar.
    # Bu yüzden yaygınlık YALNIZCA yeterli paydası olan öznitelikler için
    # raporlanır; gerisi ayrı bir "kanıt yetersiz" listesine düşer.
    MIN_VER = int(0.70 * len(present))   # 30 bankada ≥21 doğrulanmış hücre

    scored = [r for r in rows if r[3] is not None and r[2] >= MIN_VER]
    thin = [r for r in rows if r[3] is None or r[2] < MIN_VER]
    scored.sort(key=lambda r: -r[3])
    thin.sort(key=lambda r: -r[2])

    out.append(f"> **Payda kuralı:** yaygınlık yalnızca en az {MIN_VER}/{len(present)} "
               f"bankada doğrulanabilen öznitelikler için hesaplandı. Daha az "
               f"paydası olanlar aşağıda ayrı listelenir — çünkü araştırmacılar "
               f"ürünü bulamadığında çoğu kez `no` değil `unknown` yazdı, bu da "
               f"küçük paydalarda yaygınlığı yapay olarak yukarı çeker.\n")
    out.append(f"Yeterli paydalı öznitelik: **{len(scored)}/{len(CODES)}**.\n")

    out.append("### Masaya giriş bileti (yaygınlık ≥ %90) — ayrım yaratmaz\n")
    out += fmt_rows([r for r in scored if r[3] >= 0.90])
    out.append("")
    out.append("### Yaygın ama evrensel değil (%75–%90)\n")
    out += fmt_rows([r for r in scored if 0.75 <= r[3] < 0.90])
    out.append("")
    out.append("### Gerçek ayrıştırıcılar (%25–%75) — rekabetin olduğu yer\n")
    out += fmt_rows([r for r in scored if 0.25 <= r[3] < 0.75])
    out.append("")
    out.append("### Nadir / niş (< %25)\n")
    out += fmt_rows([r for r in scored if r[3] < 0.25])
    out.append("")
    out.append(f"### ⚠ Kanıt yetersiz — payda < {MIN_VER}, yaygınlık HESAPLANMADI\n")
    out.append("Bu öznitelikler için bir sonraki turda hedefli doğrulama gerekiyor. "
               "`var` sayısı bir ALT SINIRDIR, oran değildir.\n")
    out += fmt_rows(thin)
    out.append("")

    # ---------- 3. blok bazlı ısı ----------
    out.append("## 8. Blok bazlı raf genişliği (doğrulanan hücreler üzerinden)\n")
    hdr = "| Banka | " + " | ".join(BLOCKS[b] for b in "ABCDEFGHIJ") + " |"
    out.append(hdr)
    out.append("|---" * 11 + "|")
    for t in present:
        cells = []
        for b in "ABCDEFGHIJ":
            codes_b = [c for c in CODES if c.startswith(b)]
            c = Counter(val(data[t], code) for code in codes_b)
            ver = c["yes"] + c["no"] + c["partial"]
            if not ver:
                cells.append("—")
            else:
                pct = (c["yes"] + 0.5 * c["partial"]) / ver
                cells.append(f"{pct*100:.0f}%")
        out.append(f"| **{t}** | " + " | ".join(cells) + " |")
    out.append("")

    # ---------- 4. tam matris ----------
    out.append("## 9. Tam matris\n")
    out.append("● var · ◐ kısmi · · yok · ? doğrulanamadı\n")
    for b in "ABCDEFGHIJ":
        codes_b = [c for c in CODES if c.startswith(b)]
        out.append(f"### Blok {b} — {BLOCKS[b]}\n")
        out.append("| Banka | " + " | ".join(codes_b) + " |")
        out.append("|---" * (len(codes_b) + 1) + "|")
        for t in present:
            gl = " | ".join(GLYPH[val(data[t], c)] for c in codes_b)
            out.append(f"| {t} | {gl} |")
        out.append("")
        out.append("<sub>" + " · ".join(f"**{c}** {LABELS[c]}" for c in codes_b) + "</sub>\n")

    with open(os.path.join(HERE, "_MATRIX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"[yazıldı] _MATRIX.md — {len(present)} banka, {len(CODES)} öznitelik")

    # konsola sadece analiz kısmı (matris çok uzun)
    cut = out.index("## 9. Tam matris\n") if "## 9. Tam matris\n" in out else len(out)
    print("\n".join(out[:cut]))


if __name__ == "__main__":
    main()
