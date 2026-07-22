#!/bin/sh
# Ürün benchmark raporunu yeniden üret.
#   ./build_report.sh   → docs/knowledge/turkish-bank-product-benchmark-<TARIH>.md
# Sıra: kanıt QC (aggregate.py) → matris+analiz (matrix.py) → anlatı ile birleştir.
set -e
cd "$(dirname "$0")"
DATE="${1:-2026-07-22}"
OUT="../../docs/knowledge/turkish-bank-product-benchmark-${DATE}.md"
PYTHONIOENCODING=utf-8 python aggregate.py > /dev/null
PYTHONIOENCODING=utf-8 python matrix.py   > /dev/null
cat _NARRATIVE.md _MATRIX.md > "$OUT"
echo "[yazıldı] $OUT"
