"""Summarize build/audit_templates_catalog.json into a per-bank frequency
report and a draft registry skeleton.

Output:
  build/audit_templates_summary.txt   — human-readable, frequency-sorted
  build/audit_templates_registry.json — machine-readable draft registry
                                         (most-common label per row-type)

Run after `python scripts/catalog_audit_templates.py`.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG = REPO_ROOT / "build" / "audit_templates_catalog.json"
SUMMARY = REPO_ROOT / "build" / "audit_templates_summary.txt"
REGISTRY = REPO_ROOT / "build" / "audit_templates_registry.json"

_DATA = re.compile(r"\d{1,3}[.,]\d{3}")


def _strip_values(line: str) -> str:
    """Strip trailing data values and footnote refs, leaving the row label."""
    # Truncate at first thousands-separated number or trailing parenthesized number.
    s = line.strip()
    # Remove leading footnote ref like "(*) " or "(1) ".
    s = re.sub(r"^\(\*+\)\s*", "", s)
    # Truncate at first numeric data column.
    m = re.search(r"\s+\(?\s*-?\d{1,3}[.,]\d{3}", s)
    if m:
        s = s[:m.start()].rstrip()
    # Also strip lone trailing digits like "- - -" or "- 25.4 -".
    s = re.sub(r"(?:\s+[-\d.,()]+)+$", "", s).strip()
    return s


def main():
    if not CATALOG.exists():
        print(f"ERROR: {CATALOG} not found. Run catalog_audit_templates.py first.",
              file=sys.stderr)
        sys.exit(1)

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    summary_lines: list[str] = []
    registry: dict[str, dict] = {}

    for ticker in sorted(catalog):
        entry = catalog[ticker]
        summary_lines.append(f"\n{'='*78}\n{ticker}  ({entry['pdfs_scanned']} PDFs, "
                             f"periods: {entry['periods'][0]} .. {entry['periods'][-1]})\n{'='*78}")

        # ---- npl_brsa ----
        prov_labels = Counter()
        gross_labels = Counter()
        net_labels = Counter()
        header_labels = Counter()
        for c in entry["npl_brsa_contexts"]:
            header_labels[c["header"].strip()] += 1
            prov_labels[_strip_values(c["provision_line"])] += 1
            # Gross = closest data line above (skipping sub-rows by requiring
            # the label to be 'Bakiye' / 'Balance' / 'Brüt' / 'Gross' / 'EOP'
            # for the parent row variant).
            for la in reversed(c["lines_above_provision"]):
                if not _DATA.search(la):
                    continue
                if re.search(r"Net|Karşılık|Provision", la, re.IGNORECASE):
                    continue
                gross_labels[_strip_values(la)] += 1
                break
            for lb in c["lines_below_provision"]:
                if not _DATA.search(lb):
                    continue
                if not re.search(r"Net|Bilanço", lb, re.IGNORECASE):
                    continue
                net_labels[_strip_values(lb)] += 1
                break

        summary_lines.append(f"\n  [npl_brsa] {len(entry['npl_brsa_contexts'])} contexts")
        summary_lines.append("    Provision row labels:")
        for k, n in prov_labels.most_common(8):
            summary_lines.append(f"      {n:>4}x  {k!r}")
        summary_lines.append("    Gross row labels:")
        for k, n in gross_labels.most_common(8):
            summary_lines.append(f"      {n:>4}x  {k!r}")
        summary_lines.append("    Net row labels:")
        for k, n in net_labels.most_common(8):
            summary_lines.append(f"      {n:>4}x  {k!r}")

        # ---- loans_by_stage ----
        toplam_labels = Counter()
        toplam_widths = Counter()
        for c in entry.get("loans_by_stage_contexts", []):
            ln = c["toplam_line"]
            toplam_labels[_strip_values(ln)] += 1
            nums = re.findall(r"\d{1,3}[.,]\d{3}", ln)
            toplam_widths[len(nums)] += 1
        summary_lines.append(f"\n  [loans_by_stage] {len(entry.get('loans_by_stage_contexts', []))} contexts")
        summary_lines.append("    Toplam labels:")
        for k, n in toplam_labels.most_common(5):
            summary_lines.append(f"      {n:>4}x  {k!r}")
        summary_lines.append(f"    Column widths: {dict(toplam_widths)}")

        # ---- loans_ecl_brsa ----
        ecl_s1 = Counter()
        ecl_s2 = Counter()
        for c in entry.get("loans_ecl_brsa_contexts", []):
            label = _strip_values(c["line"])
            if c["kind_label"] == "s1":
                ecl_s1[label] += 1
            else:
                ecl_s2[label] += 1
        summary_lines.append(f"\n  [loans_ecl_brsa] s1={sum(ecl_s1.values())} s2={sum(ecl_s2.values())}")
        summary_lines.append("    Stage 1 row labels:")
        for k, n in ecl_s1.most_common(5):
            summary_lines.append(f"      {n:>4}x  {k!r}")
        summary_lines.append("    Stage 2 row labels:")
        for k, n in ecl_s2.most_common(5):
            summary_lines.append(f"      {n:>4}x  {k!r}")

        # ---- Draft registry entry ----
        registry[ticker] = {
            "era": f"{entry['periods'][0]}..{entry['periods'][-1]}",
            "npl_brsa": {
                "provision_label_top3": [k for k, _ in prov_labels.most_common(3)],
                "gross_label_top3":     [k for k, _ in gross_labels.most_common(3)],
                "net_label_top3":       [k for k, _ in net_labels.most_common(3)],
            },
            "loans_by_stage": {
                "toplam_label_top3":    [k for k, _ in toplam_labels.most_common(3)],
                "column_widths_seen":   dict(toplam_widths),
            },
            "loans_ecl_brsa": {
                "s1_label_top3":        [k for k, _ in ecl_s1.most_common(3)],
                "s2_label_top3":        [k for k, _ in ecl_s2.most_common(3)],
            },
        }

    SUMMARY.write_text("\n".join(summary_lines), encoding="utf-8")
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"wrote {SUMMARY} ({len(catalog)} banks)")
    print(f"wrote {REGISTRY}")


if __name__ == "__main__":
    main()
