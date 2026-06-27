"""HTTP fetch for annual-report PDFs from bank investor-relations sites.

Re-implements (does not import) the UA / Referer / ZIP / Java-wrapper handling
of ``scripts/sync_audit_reports.fetch_pdf_bytes`` so this lane is self-contained
and a change here can't perturb the audit sync. Annual reports come from the
same IR domains, so the same CDN gates apply.
"""
from __future__ import annotations

import io
import zipfile

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
# Banks whose CDN blocks bare requests — supply a Referer to bypass (mirrors the
# audit sync's REFERERS map; annual reports sit on the same domains).
REFERERS = {
    "TSKB":   "https://www.tskb.com.tr/",
    "QNBFB":  "https://www.qnb.com.tr/",
    "PASHA":  "https://www.pashabank.com.tr/",
    "AKTIF":  "https://www.aktifbank.com.tr/",
    "VAKIFK": "https://www.vakifkatilim.com.tr/",
}


def fetch_pdf_bytes(url: str, ticker: str = "", timeout: int = 120
                    ) -> tuple[bytes | None, str]:
    """Fetch a URL → ``(pdf_bytes | None, note)``. Unwraps the VAKIFK Java header
    and ZIP-wrapped PDFs, and verifies a %PDF magic so an HTML error page never
    masquerades as a report."""
    headers = dict(UA)
    if ticker in REFERERS:
        headers["Referer"] = REFERERS[ticker]
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return None, f"err:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http:{r.status_code}"
    body = r.content
    # VAKIFK CMS bug: PDFs wrapped in a 27-byte Java ObjectOutputStream header.
    if body[:4] == b"\xac\xed\x00\x05" and b"%PDF" in body[:64]:
        body = body[body.find(b"%PDF"):]
    # ZIP-wrapped PDFs.
    if body[:4] == b"PK\x03\x04":
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile:
            return None, "bad-zip"
        pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
        if not pdf_names:
            return None, "no-pdf-in-zip"
        body = zf.read(pdf_names[0])
    if not body.startswith(b"%PDF"):
        return None, f"not-pdf:{body[:8]!r}"
    return body, "ok"
