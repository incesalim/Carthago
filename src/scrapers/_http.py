"""HTTP helpers for Turkish-regulator endpoints with cert-chain quirks.

BDDK (www.bddk.org.tr) serves only the leaf certificate, omitting the
GlobalSign RSA OV SSL CA 2018 intermediate. Browsers compensate via
AIA chasing; Python's `ssl` module does not. We vendor the missing
intermediate in `_ca/bddk_intermediates.pem` and expose a CA bundle
that combines it with certifi's root store.

Usage:
    from src.scrapers._http import bddk_session
    s = bddk_session()
    r = s.get("https://www.bddk.org.tr/Duyuru/Liste", timeout=30)

Or for ad-hoc calls:
    requests.get(url, verify=bddk_verify(), timeout=30)
"""
from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

import certifi
import requests

_CA_DIR = Path(__file__).resolve().parent / "_ca"
_BDDK_INTERMEDIATES = _CA_DIR / "bddk_intermediates.pem"


@lru_cache(maxsize=1)
def bddk_verify() -> str:
    """Path to a CA bundle that trusts both certifi roots and vendored
    BDDK intermediates. Generated once per process into a temp file."""
    out = Path(tempfile.gettempdir()) / "bddk_ca_bundle.pem"
    payload = (
        Path(certifi.where()).read_bytes()
        + b"\n"
        + _BDDK_INTERMEDIATES.read_bytes()
    )
    # Avoid pointless rewrites if a previous process produced the same bundle.
    if not out.exists() or out.read_bytes() != payload:
        out.write_bytes(payload)
    return str(out)


def bddk_session() -> requests.Session:
    """A `requests.Session` preconfigured to verify BDDK's broken chain."""
    s = requests.Session()
    s.verify = bddk_verify()
    return s
