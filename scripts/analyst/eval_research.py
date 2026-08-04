"""Score an Analyst V2 research run against the evaluation corpus.

Reads a run's `findings_*.json` + `verification_*.json` (downloaded run
artifacts or a local out-dir) and the corpus in `data/analyst_eval/cases.json`,
and reports per case: verified-finding markers hit, forbidden markers, the
verifier's own summary metrics, and the abstention verdict. Stdlib only.

    python scripts/analyst/eval_research.py --dir data/research
    python scripts/analyst/eval_research.py --dir path/to/downloaded/artifacts --case albrk_equity_discovery
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def fold(s: str) -> str:
    return s.replace("İ", "I").replace("ı", "i").lower()


def finding_text(f: dict) -> str:
    parts = [f.get("thesis", ""), f.get("materiality_rationale", "")]
    for c in f.get("claims", []):
        parts.append(json.dumps(c, ensure_ascii=False))
    for c in f.get("caveats", []):
        parts.append(c)
    return fold(" ".join(parts))


def score_case(case: dict, run_dir: Path) -> dict:
    tag = f"{case['bank']}_{case['period']}_{case['kind']}"
    findings_p = run_dir / f"findings_{tag}.json"
    verification_p = run_dir / f"verification_{tag}.json"
    if not findings_p.exists() or not verification_p.exists():
        return {"case_id": case["case_id"], "status": "NO_RUN", "detail": f"missing artifacts for {tag}"}

    findings = json.loads(findings_p.read_text(encoding="utf-8"))
    verification = json.loads(verification_p.read_text(encoding="utf-8"))
    verdict_of = {v["finding_id"]: v["verdict"] for v in verification.get("findings", [])}
    verified = [f for f in findings if verdict_of.get(f.get("finding_id")) in ("pass", "flag")]
    texts = [finding_text(f) for f in verified]
    all_text = " ".join(texts)

    problems: list[str] = []
    hits: list[str] = []

    for group in case.get("expected_markers", []):
        matched = [m for m in group if fold(m) in all_text]
        if matched:
            hits.append(f"expected: {matched[0]}")
        else:
            problems.append(f"missing expected marker group {group}")
    for group in case.get("alternative_markers", []):
        matched = [m for m in group if fold(m) in all_text]
        if matched:
            hits.append(f"alternative: {matched[0]}")
    for m in case.get("forbidden_markers", []):
        if fold(m) in all_text:
            problems.append(f"FORBIDDEN marker present: {m}")

    for tool in case.get("required_evidence_tools", []):
        evid_p = run_dir / f"evidence_{tag}.jsonl"
        cited = set()
        if evid_p.exists():
            by_id = {}
            for line in evid_p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    by_id[rec["evidence_id"]] = rec["tool"]
            for f in verified:
                for c in f.get("claims", []):
                    for eid in c.get("evidence_ids", []):
                        if eid in by_id:
                            cited.add(by_id[eid])
        if tool not in cited:
            problems.append(f"required evidence tool not cited by a verified finding: {tool}")

    abstained = not verified
    if abstained and not case.get("abstention_ok", False) and case.get("expected_markers"):
        problems.append("abstained where a material finding was expected")
    if abstained and case.get("abstention_ok", False):
        hits.append("abstention (acceptable)")

    summ = verification.get("summary", {})
    for metric in ("unsupported_numeric_claims", "association_mismatches", "contradictions"):
        if summ.get(metric, 0) > 0:
            problems.append(f"verifier: {metric}={summ[metric]} (publication bar is zero)")

    status = "PASS" if not problems else "FAIL"
    return {
        "case_id": case["case_id"], "status": status,
        "verified_findings": len(verified), "emitted_findings": len(findings),
        "hits": hits, "problems": problems, "verifier_summary": summ,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(REPO / "data" / "research"))
    ap.add_argument("--case", default=None)
    a = ap.parse_args()
    corpus = json.loads((REPO / "data" / "analyst_eval" / "cases.json").read_text(encoding="utf-8"))
    run_dir = Path(a.dir)
    results = []
    for case in corpus["cases"]:
        if a.case and case["case_id"] != a.case:
            continue
        results.append(score_case(case, run_dir))
    ran = [r for r in results if r["status"] != "NO_RUN"]
    for r in results:
        print(f"{r['case_id']}: {r['status']}" + (f" — {r.get('detail')}" if r.get("detail") else ""))
        for h in r.get("hits", []):
            print(f"    + {h}")
        for p in r.get("problems", []):
            print(f"    ! {p}")
    if ran:
        ok = sum(1 for r in ran if r["status"] == "PASS")
        print(f"\n{ok}/{len(ran)} scored cases pass ({len(results) - len(ran)} without a run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
