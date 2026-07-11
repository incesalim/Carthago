"""Cloudflare R2 storage for annual-report (Faaliyet Raporu) PDFs.

Reuses the audit lane's boto3 client (``audit_reports.r2_storage.get_client`` —
read-only import, the audit module is unchanged) and, by default, its bucket
(``bddk-audit-reports``): the R2 S3 access key in use is scoped to that one
bucket, so a dedicated ``bddk-faaliyet-reports`` bucket is not reachable without
widening the token. Collision is avoided by the key convention alone — the
``_faaliyet.pdf`` suffix keeps these objects fully disjoint from audit reports
(``<TICKER>_<period>_<kind>.pdf``), and the audit lane only ever touches keys it
constructs from its own config (it never lists the bucket to pick extraction
targets), so the two families coexist safely:

    <ticker_lower>/<TICKER>_<fiscal_year>_<lang>_faaliyet.pdf
e.g. akbnk/AKBNK_2025_tr_faaliyet.pdf

To move to a dedicated bucket later, create it, grant the R2 token access
(dashboard), and set R2_FAALIYET_BUCKET=bddk-faaliyet-reports. All calls pass
``Bucket=`` explicitly, so nothing here depends on the audit lane's R2_BUCKET
env var.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from src.audit_reports.r2_storage import get_client  # boto3 S3 client (read-only reuse)

try:
    from botocore.exceptions import ClientError
    _HAS_BOTO3 = True
except ImportError:  # pragma: no cover
    _HAS_BOTO3 = False


DEFAULT_BUCKET = "bddk-audit-reports"


def bucket() -> str:
    return os.environ.get("R2_FAALIYET_BUCKET", DEFAULT_BUCKET)


def make_key(ticker: str, year: int, lang: str = "tr") -> str:
    """Canonical R2 object key for a (ticker, fiscal_year, lang) annual-report PDF."""
    return f"{ticker.lower()}/{ticker.upper()}_{year}_{lang.lower()}_faaliyet.pdf"


def exists(key: str) -> bool:
    client = get_client()
    try:
        client.head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def upload_bytes(body: bytes, key: str) -> int:
    get_client().put_object(Bucket=bucket(), Key=key, Body=body,
                            ContentType="application/pdf")
    return len(body)


def download_bytes(key: str) -> bytes:
    obj = get_client().get_object(Bucket=bucket(), Key=key)
    return obj["Body"].read()


def download_to(key: str, dest: str | Path) -> int:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    get_client().download_file(Bucket=bucket(), Key=key, Filename=str(dest))
    return dest.stat().st_size


def list_keys(prefix: str = "") -> Iterable[tuple[str, int]]:
    paginator = get_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            yield obj["Key"], obj["Size"]
