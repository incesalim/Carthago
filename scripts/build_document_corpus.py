#!/usr/bin/env python3
"""Inventory and preserve the registered audit corpus independently of lane success.

The default is inventory-only. A capture requires --capture and an explicit
--bank/--period/--limit locally. Unbounded source capture belongs in Actions.
By default this entry point writes only its own output directory. --publish in
Actions also writes versioned artifacts to the separate document-corpus R2
namespace. It never writes D1, legacy databases, or acquisition objects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.audit_reports.document_corpus import (  # noqa: E402
    Filing, preserve_original, registered_sources, reconcile_inventory, source_identity,
)


def _write_json(path: Path, value) -> None:
    """Atomic, content-idempotent reports: an interrupted write leaves the last one."""
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_bytes(path, payload)


def _write_bytes(path: Path, payload: bytes) -> None:
    if path.exists() and path.read_bytes() == payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def filing_shard(row: dict, count: int) -> int:
    """Stable assignment: adding or reordering inventory entries cannot move a filing."""
    if count < 1:
        raise ValueError("Shard count must be positive")
    name = Filing(row["bank_ticker"], row["period"], row["kind"]).filename
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest(), "big") % count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO / "data/banks/audit_report_urls.json")
    parser.add_argument("--source-dir", type=Path, default=REPO / "data/audit_pdfs")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-r2", action="store_true", help="read the current R2 source inventory")
    source.add_argument("--inventory-json", type=Path, help="saved R2 inventory, offline")
    parser.add_argument("--output-dir", type=Path, default=REPO / "data/audit_capture/corpus-v1")
    parser.add_argument("--capture", action="store_true", help="preserve source evidence after inventory")
    parser.add_argument("--structure", action="store_true", help="add source-linked tables, paragraphs and headings")
    parser.add_argument("--annotations-dir", type=Path,
                        default=REPO / "tests/fixtures/document_annotations",
                        help="independently source-annotated regression cases")
    parser.add_argument("--publish", action="store_true", help="Actions-only: preserve verified artifact bytes in R2")
    parser.add_argument("--discard-published", action="store_true",
                        help="remove local source/evidence files only after verified R2 publication")
    parser.add_argument("--recheck-bytes", action="store_true",
                        help="bypass unchanged-object receipts and read back all selected source/artifact bytes")
    parser.add_argument("--bank", help="comma-separated registered bank tickers")
    parser.add_argument("--period", help="one YYYYQn")
    parser.add_argument("--kind", choices=["consolidated", "unconsolidated"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1,
                        help="divide the selected scope into this many stable, disjoint groups")
    parser.add_argument("--shard-index", type=int, default=0, help="zero-based group to process")
    parser.add_argument("--ocr-pages", default="", help="bounded read-only probe: comma-separated PDF pages")
    parser.add_argument("--ocr-dpi", type=int, choices=(300, 450, 600), default=300)
    parser.add_argument("--ocr-language", choices=("eng", "tur", "eng+tur", "tur+eng"), default="eng+tur")
    parser.add_argument("--ocr-annotations-dir", type=Path, default=REPO / "tests/fixtures/document_ocr_annotations")
    parser.add_argument("--vector-pages", default="", help="bounded read-only outline probe: PDF page numbers")
    parser.add_argument("--vector-reference", type=Path, help="local PDF used by the source-transcribed character atlas")
    parser.add_argument("--vector-annotations-dir", type=Path, default=REPO / "tests/fixtures/document_vector_annotations")
    parser.add_argument('--review-pages', default='', help='read-only visual review: up to four pages, or ALL for one filing in Actions')
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit cannot be negative")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-count must be positive and 0 <= --shard-index < --shard-count")
    try:
        ocr_pages = [int(value.strip()) for value in args.ocr_pages.split(",")] if args.ocr_pages else []
        if any(value < 1 for value in ocr_pages) or len(ocr_pages) > 4 or len(set(ocr_pages)) != len(ocr_pages):
            raise ValueError()
    except ValueError:
        parser.error("--ocr-pages must name one to four distinct positive PDF page numbers")
    if ocr_pages and (not args.capture or args.publish or not 1 <= args.limit <= 4):
        parser.error("OCR probes require --capture, --limit 1..4, and no --publish")
    if ocr_pages and not args.ocr_annotations_dir.is_dir():
        parser.error("OCR source annotation directory is missing")
    try:
        vector_pages = [int(value.strip()) for value in args.vector_pages.split(",")] if args.vector_pages else []
        if (any(value < 1 for value in vector_pages) or len(vector_pages) > 4
                or len(set(vector_pages)) != len(vector_pages)):
            raise ValueError()
    except ValueError:
        parser.error("--vector-pages must name one to four distinct positive PDF page numbers")
    if vector_pages and (not args.capture or args.publish or not 1 <= args.limit <= 4):
        parser.error("Vector probes require --capture, --limit 1..4, and no --publish")
    if vector_pages and not args.vector_annotations_dir.is_dir():
        parser.error("Vector source annotation directory is missing")
    review_pages = []
    if args.review_pages:
        if not args.capture or args.publish or not 1 <= args.limit <= 4:
            parser.error('Visual review packs require --capture, --limit 1..4, and no --publish')
        if args.review_pages == 'ALL':
            if args.limit != 1 or os.environ.get('GITHUB_ACTIONS') != 'true':
                parser.error('Whole-document rendering requires --limit 1 in Actions')
            review_pages = None
        else:
            try:
                review_pages = [int(value.strip()) for value in args.review_pages.split(',')]
                if (not 1 <= len(review_pages) <= 4 or review_pages != sorted(set(review_pages))
                        or any(n < 1 for n in review_pages)):
                    raise ValueError()
            except ValueError:
                parser.error('Visual review requires one to four ordered, distinct positive PDF pages or ALL')
    if args.structure and not args.capture:
        parser.error("--structure requires --capture")
    if args.capture and not args.annotations_dir.is_dir():
        parser.error("Source annotation directory is missing")
    if args.publish and not (args.from_r2 and args.capture and os.environ.get("GITHUB_ACTIONS") == "true"):
        parser.error("--publish requires --from-r2 --capture in Actions")
    if args.discard_published and not args.publish:
        parser.error("--discard-published requires --publish")
    if args.capture and not (args.bank or args.period or args.limit) and os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Unbounded corpus capture must run in Actions; select a local sample explicitly")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    registered = registered_sources(config)
    known_banks = set(config["banks"])
    banks = {b.strip().upper() for b in args.bank.split(",") if b.strip()} if args.bank else None
    if banks is not None and (not banks or banks - known_banks):
        parser.error("--bank must name registered bank tickers")
    if args.period:
        # Reuse the validated key type; do not silently turn a typo into a quiet run.
        try:
            Filing(next(iter(known_banks)), args.period, "consolidated")
        except ValueError as error:
            parser.error(str(error))
    if args.from_r2:
        from src.audit_reports import r2_storage
        acquired = r2_storage.list_audit_pdfs()
    elif args.inventory_json:
        acquired = json.loads(args.inventory_json.read_text(encoding="utf-8"))
    else:
        acquired = []
    inventory = reconcile_inventory(registered, acquired, args.source_dir.glob("*.pdf"))
    inventory["acquisition_checked"] = bool(args.from_r2 or args.inventory_json)
    if not inventory["acquisition_checked"]:
        # An unqueried external source is unknown, not evidence of absence.
        inventory["registered_missing"] = None
        for row in inventory["filings"]:
            row["acquisition_status"] = "not_checked"
    _write_json(args.output_dir / "inventory.json", inventory)
    print(f"Registered: {inventory['registered_filings']}; acquired: "
          f"{inventory['acquired_filings'] if inventory['acquisition_checked'] else 'not checked'}; "
          f"local: {inventory['local_filings']}")
    if not args.capture:
        return 0

    from src.audit_reports.document_evidence import (
        artifact_digest, capture_source_evidence, engine_identity, save_evidence,
    )
    store = None
    if args.publish:
        from src.audit_reports.document_corpus_store import CorpusStore
        store = CorpusStore(r2_storage.get_client(), r2_storage._bucket())
        from src.audit_reports.document_structure import structure_engine
        from src.audit_reports.document_corpus_resume import (
            annotation_identity, download_source, record_receipt, unchanged_index,
        )

    targets = [row for row in inventory["filings"]
               if row["bank_ticker"] in known_banks
               and (banks is None or row["bank_ticker"] in banks)
               and (args.period is None or row["period"] == args.period)
               and (args.kind is None or row["kind"] == args.kind)]
    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        parser.error("No registered/acquired filing matches the requested scope")
    scope = {"banks": sorted(banks) if banks is not None else "ALL", "period": args.period,
             "kind": args.kind, "limit": args.limit, "selected_filings": len(targets),
             "shard_count": args.shard_count, "shard_index": args.shard_index}
    targets = [row for row in targets if filing_shard(row, args.shard_count) == args.shard_index]
    scope["assigned_filings"] = len(targets)
    inventory["run_scope"] = scope
    _write_json(args.output_dir / "inventory.json", inventory)
    _write_json(args.output_dir / "capture-results.json", {"run_scope": scope, "filings": []})
    print(f"Group {args.shard_index + 1}/{args.shard_count}: {len(targets)}/"
          f"{scope['selected_filings']} selected filings", flush=True)
    if store:
        store.update_catalog(inventory, [], evidence_engine=engine_identity(),
                             structure_engine=structure_engine())
    results = []
    catalog_indexes = []

    def finish(filing, result):
        results.append(result)
        _write_json(args.output_dir / "capture-results.json", {"run_scope": scope, "filings": results})
        print(f"{filing.filename}: {result['status']}", flush=True)
        if store:
            index = store.read_index(filing)
            if index:
                catalog_indexes.append(index)
            if len(results) % 10 == 0 or len(results) == len(targets):
                store.update_catalog(inventory, catalog_indexes, evidence_engine=engine_identity(),
                                     structure_engine=structure_engine())
                catalog_indexes.clear()

    vector_atlas = None
    with tempfile.TemporaryDirectory(prefix="carthago-document-source-") as temp:
        for row in targets:
            filing = Filing(row["bank_ticker"], row["period"], row["kind"])
            result = {**filing.as_dict(), "status": "failed"}
            identity, original_key = None, None
            try:
                source_annotation_hash = (annotation_identity(args.annotations_dir, filing, source_only=True)
                                          if store else None)
                annotation_hash = (annotation_identity(args.annotations_dir, filing)
                                   if store and args.structure else "not_requested")
                source_url = row["source_urls"][0] if len(row["source_urls"]) == 1 else None
                if store and not args.recheck_bytes and len(row["object_keys"]) == 1:
                    cached = unchanged_index(store, filing, row["object_keys"][0], source_url,
                                             evidence_engine=engine_identity(),
                                             structure_engine=structure_engine() if args.structure else None,
                                             annotation_hash=annotation_hash,
                                             source_annotation_hash=source_annotation_hash)
                    if cached:
                        saved = cached["current"]
                        structured = saved.get("structure_current") if args.structure else None
                        result.update(status="structured_candidates" if structured else "source_preserved",
                                      source=saved["source"], page_count=saved["page_count"],
                                      text_characters=saved["text_characters"], image_regions=saved["image_regions"],
                                      original=saved["original_key"], artifact=saved["evidence_key"],
                                      evidence_reused=True, artifact_changed=False, published=True,
                                      reuse_check="verified_object_versions_unchanged",
                                      semantic_verification="not_performed",
                                      benchmark=cached["resume_receipt"]["benchmark"])
                        result["source_benchmark"] = cached["resume_receipt"].get("source_benchmark")
                        if structured:
                            result.update({key: structured[key] for key in
                                           ("table_candidates", "text_blocks", "pages_with_issues")})
                            result["structure"] = structured["key"]
                            result['structure_diagnostics'] = structured.get('diagnostics')
                if not result.get("reuse_check"):
                    # In R2 mode, always read the current object. A cached filename
                    # cannot prove that its PDF bytes still match a mutable R2 key.
                    # Only the byte-verified storage receipt above can skip this GET.
                    acquisition = None
                    if args.from_r2:
                        if len(row["object_keys"]) != 1:
                            raise ValueError("Missing or ambiguous acquired source")
                        pdf = Path(temp) / filing.filename
                        if store:
                            acquisition = download_source(store, row["object_keys"][0], pdf)
                        else:
                            r2_storage.download_to(row["object_keys"][0], pdf)
                    else:
                        if len(row["local_paths"]) != 1:
                            raise ValueError("Missing or ambiguous local source")
                        pdf = Path(row["local_paths"][0])
                    provenance = {
                        "source_url": source_url,
                        "object_key": row["object_keys"][0] if args.from_r2 else None}
                    identity = source_identity(pdf, filing, **provenance)
                    original = args.output_dir / "sources" / identity["pdf_sha256"] / "original.pdf"
                    preserve_original(pdf, original, identity)
                    result.update(source=identity, original=str(original.relative_to(args.output_dir)))
                    if args.review_pages:
                        from src.audit_reports.document_review_pack import render_review_pack
                        pack = render_review_pack(original, identity, original.parent / 'review-pages', review_pages)
                        result['visual_review'] = pack
                        if pack['status'] != 'rendered':
                            raise ValueError('Source visual review rendering has named failures')
                    if store:
                        original_key = store.archive_source(identity, original)
                    records = store.cached_evidence(identity, engine_identity()) if store else None
                    reused = records is not None
                    if records is None:
                        records = capture_source_evidence(pdf, filing, **provenance)
                    manifest = records[0]
                    artifact = (args.output_dir / "sources" / manifest["source"]["pdf_sha256"]
                                / f"{artifact_digest(records)}.jsonl.gz")
                    changed = save_evidence(records, artifact)
                    from src.audit_reports.document_benchmark import check_source_annotations
                    source_benchmark = check_source_annotations(records, args.annotations_dir)
                    result["source_benchmark"] = source_benchmark
                    if source_benchmark["status"] == "failed":
                        raise ValueError(f"Source-text regression failed: {source_benchmark['checks']}")
                    if store:
                        store.publish(records, original, artifact)
                    result.update(source=manifest["source"],
                                  artifact=str(artifact.relative_to(args.output_dir)),
                                  original=str(original.relative_to(args.output_dir)))
                    structure_path = None
                    if args.structure:
                        from src.audit_reports.document_structure import structure_digest
                        from src.audit_reports.document_corpus_upgrade import build_or_reuse_structure
                        structure, result['structure_build'] = build_or_reuse_structure(pdf, records, store)
                        structure_path = artifact.parent / f"{structure_digest(structure)}.structure.json"
                        _write_json(structure_path, structure)
                        if args.from_r2 and not args.publish:
                            from src.audit_reports.document_corpus_store import CorpusStore
                            from src.audit_reports.document_region_upgrade import compare_retained_regions
                            reader = CorpusStore(r2_storage.get_client(), r2_storage._bucket())
                            result['retained_structure_comparison'] = compare_retained_regions(
                                pdf, records, structure, reader)
                        from src.audit_reports.document_benchmark import check_registered_annotations
                        benchmark = check_registered_annotations(structure, records, args.annotations_dir)
                        result["benchmark"] = benchmark
                        if benchmark["status"] == "failed":
                            raise ValueError(f"Source-annotated regression failed: {benchmark['checks']}")
                        if store:
                            store.publish_structure(structure, records)
                        result.update(structure=str(structure_path.relative_to(args.output_dir)),
                                      table_candidates=sum(len(p["tables"]) for p in structure["pages"]),
                                      text_blocks=sum(len(p["text_blocks"]) for p in structure["pages"]),
                                      pages_with_issues=sum(bool(p["issues"]) for p in structure["pages"]))
                        from src.audit_reports.document_quality import structure_diagnostics
                        result['structure_diagnostics'] = structure_diagnostics(structure)
                    if ocr_pages:
                        from src.audit_reports.document_ocr import capture_ocr_page, check_ocr_annotations, verify_ocr_page
                        result["text_recovery"] = []
                        for number in ocr_pages:
                            recovery, derivative = capture_ocr_page(
                                pdf, filing, number, args.output_dir / "ocr-models",
                                dpi=args.ocr_dpi, language=args.ocr_language, **provenance)
                            check = verify_ocr_page(recovery, derivative, pdf)
                            if not check["valid"]:
                                raise ValueError(f"OCR artifact retention failed: {check['errors']}")
                            base = artifact.parent / f"p{number}.{recovery['ocr_pdf_sha256']}"
                            observation_path, derivative_path = Path(str(base) + ".ocr.json"), Path(str(base) + ".ocr.pdf")
                            _write_json(observation_path, recovery)
                            _write_bytes(derivative_path, derivative)
                            benchmark = check_ocr_annotations(recovery, args.ocr_annotations_dir)
                            result["text_recovery"].append({"page": number, "status": "ocr_candidates",
                                "observation": str(observation_path.relative_to(args.output_dir)),
                                "derivative": str(derivative_path.relative_to(args.output_dir)),
                                "word_count": len(recovery["words"]), "retention_check": check,
                                "benchmark": benchmark,
                                "recognition_verified": False})
                            if benchmark["status"] == "failed":
                                raise ValueError(f"OCR source-token regression failed: {benchmark['checks']}")
                    if vector_pages:
                        from src.audit_reports import document_vector
                        if vector_atlas is None:
                            anchors = json.loads(document_vector.ANCHORS.read_text(encoding="utf-8"))
                            reference = args.vector_reference
                            if reference is None and identity["pdf_sha256"] == anchors["pdf_sha256"]:
                                reference = pdf
                            if reference is None and args.from_r2:
                                reference = Path(temp) / "vector-reference.pdf"
                                r2_storage.download_to(anchors["object_key"], reference)
                            if reference is None:
                                raise ValueError("This local vector probe requires --vector-reference or --from-r2")
                            candidate_atlas = document_vector.build_atlas(reference, anchors)
                            reference_copy = (args.output_dir / "sources" / anchors["pdf_sha256"] / "original.pdf")
                            preserve_original(reference, reference_copy, candidate_atlas["source"])
                            vector_atlas = candidate_atlas
                        atlas_path = artifact.parent / f"{document_vector.atlas_digest(vector_atlas)}.vector-atlas.json"
                        _write_json(atlas_path, vector_atlas)
                        result["vector_recovery"] = []
                        for number in vector_pages:
                            recovery = document_vector.capture_vector_page(pdf, filing, number, vector_atlas, **provenance)
                            check = document_vector.verify_vector_page(recovery, pdf, vector_atlas)
                            if not check["valid"]:
                                raise ValueError(f"Vector source retention failed: {check['errors']}")
                            address = document_vector.atlas_digest(recovery)
                            recovery_path = artifact.parent / f"p{number}.{address}.vector.json"
                            _write_json(recovery_path, recovery)
                            benchmark = document_vector.check_vector_annotations(recovery, args.vector_annotations_dir)
                            result["vector_recovery"].append({"page": number, "status": "vector_candidates",
                                "observation": str(recovery_path.relative_to(args.output_dir)),
                                "atlas": str(atlas_path.relative_to(args.output_dir)),
                                "reference_pdf": str(reference_copy.relative_to(args.output_dir)),
                                "matched_paths": len(recovery["matched_paths"]),
                                "unresolved_paths": len(recovery["unresolved_paths"]),
                                "retention_check": check, "benchmark": benchmark, "recognition_verified": False})
                            if benchmark["status"] == "failed":
                                raise ValueError(f"Vector source regression failed: {benchmark['checks']}")
                    result.update(status="source_preserved", source=manifest["source"],
                                  page_count=manifest["page_count"],
                                  text_characters=manifest["text_characters"],
                                  image_regions=manifest["image_regions"],
                                  artifact=str(artifact.relative_to(args.output_dir)),
                                  original=str(original.relative_to(args.output_dir)),
                                  artifact_changed=changed, evidence_reused=reused,
                                  published=store is not None, semantic_verification="not_performed")
                    if args.structure:
                        result["status"] = "structured_candidates"
                    if store:
                        record_receipt(store, filing, acquisition, annotation_hash, result.get("benchmark"),
                                       structure=args.structure, source_annotation_hash=source_annotation_hash,
                                       source_benchmark=source_benchmark)
                    if args.discard_published:
                        # These exact files are under this command's own output root.
                        # Their read-back-verified R2 copies and filing index now exist.
                        for published_path in [original, artifact] + ([structure_path] if structure_path else []):
                            published_path.resolve().relative_to(args.output_dir.resolve())
                            published_path.unlink()
            except Exception as error:
                # A failed source remains a named result and makes the run fail.
                # Good artifacts survive, but their count cannot hide this source.
                result["status"] = "failed"
                result["error"] = f"{type(error).__name__}: {error}"
                if store:
                    try:
                        store.record_failure(filing, result["error"], source=identity, original_key=original_key)
                    except Exception as index_error:
                        result["index_error"] = f"{type(index_error).__name__}: {index_error}"
            finally:
                temporary_pdf = Path(temp) / filing.filename
                if temporary_pdf.exists():
                    temporary_pdf.unlink()
            finish(filing, result)
    failures = sum(r["status"] == "failed" for r in results)
    print(f"Source preservation: {len(results) - failures}/{len(results)}; "
          "semantic verification: not performed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
