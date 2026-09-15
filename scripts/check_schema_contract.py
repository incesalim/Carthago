"""Verify publishable staging columns against a fresh versioned serving schema."""
import importlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import push_to_d1 as push  # noqa: E402
from src.pipeline.schema import compare_schema, migrated_schema  # noqa: E402


def check() -> list[str]:
    expected = migrated_schema()
    staging = sqlite3.connect(":memory:")
    try:
        for name, fn in vars(push).items():
            if name.startswith("_init_") and name.endswith("_schema"):
                fn(staging)
        for module, function in [
            ("src.analyst.schema", "init_analyst_schema"),
            ("src.tbb.schema", "init_schema"), ("src.tbb.schema", "init_acquisition_schema"),
            ("src.transcripts.schema", "init_schema"), ("src.release_calendar.schema", "init_schema"),
            ("src.scrapers.evds_scraper", "init_schema"), ("src.scrapers.weekly_api_scraper", "ensure_schema"),
            ("scripts.build_api_catalog", "ensure_schema"),
        ]:
            getattr(importlib.import_module(module), function)(staging)
        present = {r[0] for r in staging.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        errors = compare_schema(expected, staging, present & set(push.SYNC_TABLES), staging=True)
        # Exercise the actual SQL emitter, including local-only extraction-log
        # migrations, against a clean target rather than just comparing names.
        staging.execute("INSERT INTO bank_audit_extractions(bank_ticker,period,kind,pdf_path) "
                        "VALUES ('TEST','2026Q2','unconsolidated','test.pdf')")
        try:
            expected.executescript("\n".join(push.fetch_recent(staging, "bank_audit_extractions", 24)))
        except sqlite3.Error as exc:
            errors.append(f"publisher insert rejected by migration-only DB: {exc}")
        return errors
    finally:
        expected.close()
        staging.close()


if __name__ == "__main__":
    problems = check()
    print("\n".join(problems) if problems else "Serving/staging schema contract passes")
    raise SystemExit(bool(problems))
