#!/usr/bin/env python3
"""Artifact'i yeniden üret: <TICKER>.json'lardan payload derle + _template.html'e enjekte.

Rapor (build_report.sh) gibi, interaktif matris de deterministik olarak yeniden
üretilebilir. Kaynak = JSON dosyaları; benchmark_explorer.html türetilmiş çıktıdır.

    python make_artifact.py     ->  benchmark_explorer.html
"""
import json
import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from aggregate import CODES, LABELS, BLOCKS, CLUSTERS, ORDER  # noqa

# Ayrıştırıcı işaretli öznitelikler (TAXONOMY.md'deki "ayrıştırıcı" notları)
DISTINCTIVE = set(
    "A04 A07 A09 C03 C04 C08 D02 D04 D09 D10 D11 D12 E06 F04 F05 F07 F09 "
    "G03 G07 G08 G11 G12 G13 H04 H07 I06 I08 I09 I10 I12".split()
)


def build_payload():
    data = {}
    for f in glob.glob(os.path.join(HERE, "*.json")):
        if os.path.basename(f).startswith("_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        data[d["ticker"]] = d

    present = [t for t in ORDER if t in data]
    cl_of = {t: name for name, banks in CLUSTERS for t in banks}

    banks = []
    for t in present:
        d = data[t]
        c = Counter((d["attributes"][x] or {}).get("v", "unknown") for x in CODES)
        ver = c["yes"] + c["no"] + c["partial"]
        banks.append({
            "ticker": t, "name": d.get("bank", t), "cluster": cl_of[t],
            "domain": d.get("domain", ""),
            "yes": c["yes"], "no": c["no"], "partial": c["partial"], "unknown": c["unknown"],
            "coverage": round(ver / len(CODES), 3),
            "shelf": round((c["yes"] + 0.5 * c["partial"]) / ver, 3) if ver else 0,
            "distinctive": d.get("distinctive", [])[:6],
            "shelf_notes": d.get("shelf_notes", ""),
            "cells": {x: {"v": (d["attributes"][x] or {}).get("v", "unknown"),
                          "n": (d["attributes"][x] or {}).get("note", ""),
                          "u": (d["attributes"][x] or {}).get("url", "")} for x in CODES},
        })

    min_ver = int(0.70 * len(present))
    attrs = []
    for code in CODES:
        c = Counter((data[t]["attributes"][code] or {}).get("v", "unknown") for t in present)
        ver = c["yes"] + c["no"] + c["partial"]
        pen = round((c["yes"] + 0.5 * c["partial"]) / ver, 3) if ver else None
        attrs.append({"code": code, "label": LABELS[code], "block": code[0],
                      "yes": c["yes"], "no": c["no"], "partial": c["partial"],
                      "unknown": c["unknown"], "pen": pen, "enough": ver >= min_ver,
                      "distinctive": code in DISTINCTIVE})

    urls = set(cell["u"] for bk in banks for cell in bk["cells"].values() if cell["u"])
    return {
        "meta": {"nbanks": len(present), "nattrs": len(CODES),
                 "ncells": len(present) * len(CODES), "min_ver": min_ver,
                 "date": "2026-07-22", "nurls": len(urls)},
        "blocks": [{"id": b, "name": BLOCKS[b]} for b in "ABCDEFGHIJ"],
        "clusters": [name for name, _ in CLUSTERS],
        "banks": banks, "attrs": attrs,
    }


def main():
    payload = json.dumps(build_payload(), ensure_ascii=False, separators=(",", ":"))
    assert "</script" not in payload, "payload contains </script — would break the page"
    tpl = open(os.path.join(HERE, "_template.html"), encoding="utf-8").read()
    assert "/*__PAYLOAD__*/" in tpl, "template placeholder missing"
    out = tpl.replace("/*__PAYLOAD__*/", payload)
    open(os.path.join(HERE, "benchmark_explorer.html"), "w", encoding="utf-8").write(out)
    print(f"[yazıldı] benchmark_explorer.html — {len(out)} bytes")


if __name__ == "__main__":
    main()
