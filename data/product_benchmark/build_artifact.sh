#!/bin/sh
# Artifact'i yeniden üret: JSON payload derle + template'e enjekte.
#   ./build_artifact.sh  → benchmark_explorer.html
# (template bu klasörde _template.html olarak tutulmaz; artifact.py payload'ı
#  doğrudan JSON dosyalarından okur ve gömülü şablonla birleştirir.)
set -e; cd "$(dirname "$0")"
PYTHONIOENCODING=utf-8 python make_artifact.py
echo "[yazıldı] benchmark_explorer.html"
