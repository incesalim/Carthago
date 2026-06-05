"""Cloudflare R2 storage for BRSA audit-report PDFs.

R2 has an S3-compatible API, so we use boto3. Credentials come from env vars:
  R2_ACCOUNT_ID        — 32-hex Cloudflare account id (from endpoint URL)
  R2_ACCESS_KEY_ID     — S3 access key from the R2 token UI
  R2_SECRET_ACCESS_KEY — S3 secret key from the R2 token UI
  R2_BUCKET            — bucket name (default: bddk-audit-reports)

Key convention mirrors the previous local layout:
    <ticker_lower>/<TICKER>_<period>_<kind>.pdf
e.g. akbnk/AKBNK_2026Q1_consolidated.pdf

This lets the migration script transfer files 1:1 and keeps the existing
filename parser (STD_PAT in extract_all_audit_reports.py) working unchanged.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False


DEFAULT_BUCKET = "bddk-audit-reports"


@dataclass
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str

    @property
    def endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_env(cls) -> "R2Config":
        missing = [
            v for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
            if not os.environ.get(v)
        ]
        if missing:
            raise RuntimeError(
                f"Missing R2 env vars: {', '.join(missing)}. "
                f"Set them in your shell or GitHub Secrets."
            )
        return cls(
            account_id=os.environ["R2_ACCOUNT_ID"],
            access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            bucket=os.environ.get("R2_BUCKET", DEFAULT_BUCKET),
        )


@lru_cache(maxsize=1)
def get_client():
    """Singleton boto3 S3 client pointed at R2."""
    if not _HAS_BOTO3:
        raise RuntimeError(
            "boto3 not installed. `pip install boto3` (already in requirements.txt)."
        )
    cfg = R2Config.from_env()
    # R2 needs signature_version=s3v4 and addressing_style=virtual is fine.
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key_id,
        aws_secret_access_key=cfg.secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


@lru_cache(maxsize=1)
def _bucket() -> str:
    return os.environ.get("R2_BUCKET", DEFAULT_BUCKET)


def make_key(ticker: str, period: str, kind: str) -> str:
    """Canonical R2 object key for a (ticker, period, kind) PDF."""
    return f"{ticker.lower()}/{ticker.upper()}_{period.upper()}_{kind.lower()}.pdf"


# Filename → (ticker, period, kind) parser. Mirrors make_key's output.
KEY_FILENAME_PAT = re.compile(
    r"^([A-Z]+)_(\d{4}Q\d)_(consolidated|unconsolidated)\.pdf$", re.I
)


def list_audit_pdfs() -> list[tuple[str, str, str, str]]:
    """Return every audit-report PDF in R2 as [(ticker, period, kind, key), ...].

    Filters out any keys that don't match the canonical filename convention,
    so callers can rely on the tuple shape."""
    out: list[tuple[str, str, str, str]] = []
    for key, _size in list_keys():
        if not key.endswith(".pdf"):
            continue
        name = key.split("/")[-1]
        m = KEY_FILENAME_PAT.match(name)
        if not m:
            continue
        out.append((m.group(1).upper(), m.group(2).upper(), m.group(3).lower(), key))
    return out


def exists(key: str) -> bool:
    """True if an object exists at this key."""
    client = get_client()
    try:
        client.head_object(Bucket=_bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def upload_bytes(body: bytes, key: str, content_type: str = "application/pdf") -> int:
    """Upload bytes to R2. Returns size in bytes."""
    client = get_client()
    client.put_object(
        Bucket=_bucket(),
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return len(body)


def upload_file(path: str | Path, key: str, content_type: str = "application/pdf") -> int:
    """Upload a local file to R2. Returns size in bytes."""
    path = Path(path)
    client = get_client()
    client.upload_file(
        Filename=str(path),
        Bucket=_bucket(),
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )
    return path.stat().st_size


def download_bytes(key: str) -> bytes:
    """Download an object as bytes."""
    client = get_client()
    obj = client.get_object(Bucket=_bucket(), Key=key)
    return obj["Body"].read()


def download_to(key: str, dest: str | Path) -> int:
    """Download an object to a local file. Returns size in bytes."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    client = get_client()
    client.download_file(Bucket=_bucket(), Key=key, Filename=str(dest))
    return dest.stat().st_size


def list_keys(prefix: str = "") -> Iterable[tuple[str, int]]:
    """Yield (key, size) tuples for all objects under a prefix."""
    client = get_client()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            yield obj["Key"], obj["Size"]


def delete(key: str) -> None:
    client = get_client()
    client.delete_object(Bucket=_bucket(), Key=key)


# ---------------------------------------------------------------------------
# Snapshot history — keep dated backups so a bad run can't destroy the only copy
# ---------------------------------------------------------------------------
def upload_history(local_gz: str | Path, lane: str, date_str: str, keep: int = 7) -> str:
    """Upload a dated backup of a snapshot to state/history/<lane>-<date>.db.gz
    and prune older copies to the newest `keep`. `date_str` is YYYYMMDD (passed
    in by the caller so the key sorts chronologically). Returns the key written.

    R2 free tier easily covers this: 7 × ~55 MB ≈ 0.4 GB and a handful of
    Class-A ops per run.
    """
    key = f"state/history/{lane}-{date_str}.db.gz"
    upload_file(local_gz, key, content_type="application/gzip")
    prune_history(lane, keep)
    return key


def prune_history(lane: str, keep: int = 7) -> int:
    """Keep only the newest `keep` dated snapshots for a lane, delete the rest.
    Returns the number deleted. Keys are `state/history/<lane>-YYYYMMDD.db.gz`,
    so a lexicographic sort is chronological."""
    prefix = f"state/history/{lane}-"
    keys = sorted(k for k, _ in list_keys(prefix) if k.endswith(".db.gz"))
    to_delete = keys[:-keep] if len(keys) > keep else []
    for k in to_delete:
        delete(k)
    return len(to_delete)


if __name__ == "__main__":
    # Smoke test: list everything in the bucket
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = R2Config.from_env()
    print(f"endpoint: {cfg.endpoint}")
    print(f"bucket:   {cfg.bucket}")
    total = 0
    n = 0
    for key, size in list_keys():
        n += 1
        total += size
        if n <= 20:
            print(f"  {size:>12,} B  {key}")
    print(f"\n{n} objects, {total / 1024 / 1024:.1f} MB total")
