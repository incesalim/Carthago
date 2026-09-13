"""Measure the real audit candidate gates on a disposable snapshot copy.

This is fault injection, NOT a source-accuracy or table-completeness certificate.
Every selected filing/lane gets a fresh baseline through revalidate_partition.
Only initially accepted, populated lanes enter the mutation denominator. Curated
skips, absent data, baseline failures and validator exceptions remain separate.
Each fault is rolled back before the next. The input database is opened read-only;
all mutations use an in-memory backup. Whole-corpus runs belong in Actions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import gzip
import json
import math
import os
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.reextract_statement import _satisfies_candidate_gate  # noqa: E402
from scripts.revalidate_audit_db import revalidate_partition  # noqa: E402
from src.audit_reports.registry import BY_KEY, validation_gate  # noqa: E402
from src.audit_reports.schema import init_schema  # noqa: E402
from src.audit_reports.units import MONEY_COLUMNS  # noqa: E402

IDENTITY = {"bank_ticker", "period", "kind", "statement"}
NON_MEASURES = IDENTITY | {"item_order", "item_id", "source_page", "page",
                           "page_start", "page_end", "disclosed"}
TEXT_FIELDS = {"item_name", "hierarchy", "footnote", "heading_snippet",
               "basis_text", "opinion_text", "source_text", "section_role", "heading",
               "heading_path", "topic", "text"}


def quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def disposable_database(path: Path):
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(":memory:")
    try:
        source.backup(target)
        # Upgrade only the disposable copy. Missing source columns are reported
        # separately, never mistaken for populated evidence after this upgrade.
        original_schema = {
            row[0]: [dict(zip(("cid", "name", "type", "notnull", "default", "pk"), c))
                     for c in source.execute(f"PRAGMA table_info({quoted(row[0])})")]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        init_schema(target)
        target.commit()
        target.row_factory = sqlite3.Row
        yield target, original_schema
    finally:
        target.close()
        source.close()


def lane_rows(conn, partition, lane):
    st = BY_KEY[lane]
    where = "bank_ticker=? AND period=? AND kind=?"
    params = list(partition)
    if st.statement:
        where += " AND statement=?"
        params.append(st.statement)
    rows = [dict(row) for row in conn.execute(
        f"SELECT rowid AS _rowid_, * FROM {quoted(st.table)} WHERE {where} ORDER BY rowid",
        params)]
    return rows, where, params


def verdict(results, lane):
    gates = validation_gate(lane)
    detail = {}
    for gate in gates:
        result = results.get(gate)
        detail[gate] = None if result is None else {
            "passed": result.passed, "failed": result.failed, "skipped": result.skipped,
            "failures": result.failures[:8], "failure_count": len(result.failures),
        }
    accepted = bool(gates) and all(
        results.get(g) is not None and _satisfies_candidate_gate(
            results[g], allow_conditional_na=BY_KEY[lane].conditional)
        for g in gates)
    return {"accepted": accepted, "gates": detail}


@dataclass(frozen=True)
class Fault:
    operator: str
    rowid: int | None = None
    column: str | None = None
    replacement: float | str | None = None


def fault_inventory(rows, columns):
    numeric = {c["name"] for c in columns
               if c["type"].upper() in {"REAL", "INTEGER", "FLOAT", "NUMERIC"}
               and c["name"] not in NON_MEASURES and not c["pk"]}
    if rows:
        yield Fault("delete_table")
    for col in sorted(numeric):
        if any(row.get(col) is not None for row in rows):
            yield Fault("null_column", column=col)
    for row in rows:
        rid = row["_rowid_"]
        yield Fault("delete_row", rid)
        for col in sorted(numeric):
            val = row.get(col)
            if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
                continue
            yield Fault("cell_null", rid, col)
            yield Fault("cell_value", rid, col, val * 10 if val else 100)
            if val:
                yield Fault("cell_zero", rid, col, 0)
                yield Fault("cell_sign", rid, col, -val)
        for col in sorted(row):
            if (col in TEXT_FIELDS or col.endswith("_source_json")) and row[col]:
                op = "remove_note" if col == "footnote" else (
                    "remove_evidence" if col.endswith("_source_json") else "erase_text")
                yield Fault(op, rid, col, "")
    periods = {r.get("period_type") for r in rows}
    if "current" in periods and "prior" in periods:
        yield Fault("swap_periods")


def select_faults(rows, columns, per_operator):
    """Stable hash sampling within EACH operator, with the full candidate count.

    A capped run is explicitly a sample. Hash order avoids always choosing the
    first headline or the first currency column. Zero requests all candidates.
    """
    grouped = defaultdict(list)
    for fault in fault_inventory(rows, columns):
        key = hashlib.sha256(json.dumps(asdict(fault), sort_keys=True).encode()).hexdigest()
        grouped[fault.operator].append((key, fault))
    selected = [fault for op in sorted(grouped)
                for _, fault in sorted(grouped[op])[:per_operator or None]]
    return selected, {op: len(values) for op, values in sorted(grouped.items())}


def apply_fault(conn, table, where, params, fault):
    if fault.operator == "delete_table":
        conn.execute(f"DELETE FROM {quoted(table)} WHERE {where}", params)
    elif fault.operator == "null_column":
        conn.execute(f"UPDATE {quoted(table)} SET {quoted(fault.column)}=NULL WHERE {where}", params)
    elif fault.operator == "scale_filing":
        # Coherent unit error: change every monetary fact in the filing, keeping
        # ratios, counts, raw source evidence and neighbouring filings intact.
        # Many within-filing identities remain true under this corruption.
        for money_table, names in MONEY_COLUMNS.items():
            available = {r[1] for r in conn.execute(f"PRAGMA table_info({quoted(money_table)})")}
            fields = sorted(set(names) & available)
            if fields:
                assignments = ",".join(f"{quoted(c)}={quoted(c)}*1000" for c in fields)
                conn.execute(f"UPDATE {quoted(money_table)} SET {assignments} "
                             "WHERE bank_ticker=? AND period=? AND kind=?", params[:3])
    elif fault.operator == "swap_periods":
        # Two steps avoid colliding with a current/prior composite primary key.
        conn.execute(f"UPDATE {quoted(table)} SET period_type='audit:' || period_type "
                     f"WHERE {where} AND period_type IN ('current','prior')", params)
        conn.execute(f"UPDATE {quoted(table)} SET period_type=CASE period_type "
                     "WHEN 'audit:current' THEN 'prior' ELSE 'current' END "
                     f"WHERE {where} AND period_type IN ('audit:current','audit:prior')", params)
    elif fault.operator == "delete_row":
        conn.execute(f"DELETE FROM {quoted(table)} WHERE rowid=?", (fault.rowid,))
    else:
        conn.execute(f"UPDATE {quoted(table)} SET {quoted(fault.column)}=? WHERE rowid=?",
                     (fault.replacement, fault.rowid))


def audit_lane(conn, partition, lane, baseline, original_schema, per_operator):
    st = BY_KEY[lane]
    rows, where, params = lane_rows(conn, partition, lane)
    columns = [dict(row) for row in conn.execute(f"PRAGMA table_info({quoted(st.table)})")]
    original_names = {c["name"] for c in original_schema.get(st.table, [])}
    record = {"partition": list(partition), "lane": lane, "table": st.table,
              "rows": len(rows), "baseline": verdict(baseline, lane),
              "source_missing_columns": [c["name"] for c in columns if c["name"] not in original_names],
              "state": "eligible", "cases": [], "candidates": {}}
    if not rows:
        record["state"] = "empty"
    elif not record["baseline"]["accepted"]:
        gates = record["baseline"]["gates"].values()
        record["state"] = "baseline_failed" if any(g and g["failed"] for g in gates) else "unproven"
    if record["state"] != "eligible":
        return record
    faults, record["candidates"] = select_faults(rows, columns, per_operator)
    if any(row.get(col) for row in rows for col in MONEY_COLUMNS.get(st.table, ())):
        faults.append(Fault("scale_filing"))
        record["candidates"]["scale_filing"] = 1
    by_id = {r["_rowid_"]: r for r in rows}
    key_names = [c["name"] for c in columns if c["pk"]]
    for fault in faults:
        row = by_id.get(fault.rowid, {})
        case = {**asdict(fault), "row_key": {k: row[k] for k in key_names if k in row}}
        if fault.column:
            before = row.get(fault.column)
            case["before"] = before if not isinstance(before, str) else {
                "length": len(before), "sha256": hashlib.sha256(before.encode()).hexdigest(),
                "preview": before[:120]}
        conn.execute("SAVEPOINT audit_fault")
        try:
            apply_fault(conn, st.table, where, params, fault)
            after = verdict(revalidate_partition(conn, *partition), lane)
            case.update(outcome="escaped" if after["accepted"] else "rejected", after=after)
        except sqlite3.IntegrityError as exc:
            # A NOT NULL/UNIQUE storage constraint is distinct from a validator.
            case.update(outcome="storage_rejected", error=str(exc))
        except Exception as exc:
            # A broken audit or validator is not a successful rejection.
            case.update(outcome="execution_error", error=f"{type(exc).__name__}: {exc}")
        finally:
            conn.execute("ROLLBACK TO audit_fault")
            conn.execute("RELEASE audit_fault")
        record["cases"].append(case)
    return record


def registered_partitions(conn):
    # Match coverage's registered census, then include snapshot expected rows.
    profiles = json.loads((REPO / "data/audit_profiles.json").read_text(encoding="utf-8"))
    parts = {tuple(key.split("|")) for key in profiles}
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='bank_audit_expected'").fetchone()
    if exists:
        parts.update(tuple(r) for r in conn.execute(
            "SELECT DISTINCT bank_ticker,period,kind FROM bank_audit_expected"))
    return sorted(parts)


def summarize(records):
    lanes = {}
    for record in records:
        lane = lanes.setdefault(record["lane"], {
            "baselines": Counter(), "outcomes": Counter(), "operators": defaultdict(Counter),
            "available_faults": 0, "tested_faults": 0})
        lane["baselines"][record["state"]] += 1
        lane["available_faults"] += sum(record.get("candidates", {}).values())
        for case in record.get("cases", []):
            lane["tested_faults"] += 1
            lane["outcomes"][case["outcome"]] += 1
            lane["operators"][case["operator"]][case["outcome"]] += 1
    return lanes


def pull_pinned_snapshot(destination: Path, etag: str):
    """One conditional R2 GET; no upload/D1 capability is used by this path."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Snapshot audit downloads belong in GitHub Actions")
    if not etag or destination.exists():
        raise ValueError("A pinned ETag and a new destination are required")
    from src.audit_reports.r2_storage import _bucket, get_client
    obj = get_client().get_object(Bucket=_bucket(), Key="state/bank_audit.db.gz", IfMatch=etag)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output, gzip.GzipFile(fileobj=obj["Body"]) as stream:
            shutil.copyfileobj(stream, output)
    finally:
        obj["Body"].close()
    return {"key": "state/bank_audit.db.gz", "etag": obj["ETag"],
            "last_modified": obj["LastModified"].isoformat()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--banks", default="ALL")
    ap.add_argument("--lanes", default="ALL")
    ap.add_argument("--per-operator", type=int, default=2, help="Faults per operator per lane/filing; 0=all")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--pull-snapshot", action="store_true", help="Actions only; requires --snapshot-etag")
    ap.add_argument("--snapshot-etag", default="")
    args = ap.parse_args(argv)
    if args.per_operator < 0 or not 0 <= args.shard < args.shards:
        ap.error("invalid sample or shard")
    if args.db.resolve() == args.output.resolve():
        ap.error("output must not overwrite the input database")
    lanes = list(BY_KEY) if args.lanes == "ALL" else args.lanes.split(",")
    if set(lanes) - set(BY_KEY):
        ap.error("unknown lane")
    snapshot = pull_pinned_snapshot(args.db, args.snapshot_etag) if args.pull_snapshot else None
    sha_before = digest(args.db)
    records = []
    with disposable_database(args.db) as (conn, schema):
        partitions = registered_partitions(conn)
        if args.banks != "ALL":
            banks = set(args.banks.upper().split(","))
            partitions = [p for p in partitions if p[0] in banks]
        if not partitions:
            ap.error("selection contains no registered filings")
        partitions = partitions[args.shard::args.shards]
        for idx, partition in enumerate(partitions):
            try:
                baseline = revalidate_partition(conn, *partition)
            except Exception as exc:
                records.extend({"partition": list(partition), "lane": lane,
                                "state": "baseline_error", "error": f"{type(exc).__name__}: {exc}"}
                               for lane in lanes)
                continue
            for lane in lanes:
                records.append(audit_lane(conn, partition, lane, baseline, schema, args.per_operator))
            print(f"[{idx + 1}/{len(partitions)}] {'|'.join(partition)}", flush=True)
    unchanged = digest(args.db) == sha_before
    report = {"schema": "audit-gate-measurement-1", "input_sha256": sha_before,
              "snapshot": snapshot, "code_sha": os.environ.get("GITHUB_SHA"),
              "input_unchanged": unchanged, "source_accuracy_tested": False,
              "table_completeness_certified": False, "per_operator_limit": args.per_operator,
              "shard": args.shard, "shards": args.shards, "partition_count": len(partitions),
              "lanes": lanes, "summary": summarize(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    errors = any(r["state"] == "baseline_error" or any(
        c["outcome"] == "execution_error" for c in r.get("cases", [])) for r in records)
    return int(not unchanged or errors)


if __name__ == "__main__":
    raise SystemExit(main())
