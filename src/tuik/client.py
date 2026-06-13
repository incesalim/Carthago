"""TÜİK statistical-portal client — discover + download bulletin Excel tables.

The robust deterministic channel (reverse-engineered from the `emraher/tuikr`
R package; the SDMX `nsiws.tuik.gov.tr/rest` endpoint 401s without auth, and
the `data.tuik.gov.tr/Bulten` pages are JS-rendered):

  1. GET veriportali.tuik.gov.tr/<lang>/statistical-themes   → sets NSC_ESNS cookie
  2. GET .../api/<lang>/data/statistical-themes (Referer/Origin/X-Requested-With)
     → ~1.2 MB JSON theme tree; leaf `url` fields carry the exact
       `/api/<lang>/data/downloads?t=i&p=<encoded>` Excel URLs (the encoded `p`
       is GIVEN, not constructed) and SDMX dataflow ids in databrowser URLs
  3. GET the download URL (same session) → .xls (OLE2/BIFF) → pandas/xlrd

A single `TuikClient` instance reuses one cookie session + one cached theme
tree, so each refresh fetches the tree once and resolves every table by name.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache

import pandas as pd
import requests

BASE = "https://veriportali.tuik.gov.tr"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class TuikClient:
    def __init__(self, lang: str = "en", timeout: int = 60):
        self.lang = lang
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,tr-TR;q=0.8,tr;q=0.7",
                "User-Agent": _UA,
            }
        )
        self._tree: list[tuple[str, str]] | None = None  # [(full_label, url)]

    # -- discovery ---------------------------------------------------------
    def _load_tree(self) -> list[tuple[str, str]]:
        if self._tree is not None:
            return self._tree
        page = f"{BASE}/{self.lang}/statistical-themes"
        self.s.get(page, timeout=self.timeout)  # sets NSC_ESNS cookie
        api = f"{BASE}/api/{self.lang}/data/statistical-themes"
        r = self.s.get(
            api,
            headers={"Referer": page, "Origin": BASE, "X-Requested-With": "XMLHttpRequest"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        flat: list[tuple[str, str]] = []

        def walk(node: dict, path: list[str]) -> None:
            name = node.get("name", "")
            url = node.get("url", "")
            p = path + [name]
            if url and "downloads?" in url:
                flat.append((" / ".join(p), url))
            for c in node.get("children", []) or []:
                walk(c, p)

        for n in r.json()["data"]:
            walk(n, [])
        self._tree = flat
        return flat

    def find_url(self, pattern: str, exclude: str | None = None) -> str:
        """First Excel-download URL whose theme path matches `pattern` (regex,
        case-insensitive) and not `exclude`. Raises if none."""
        rx = re.compile(pattern, re.I)
        ex = re.compile(exclude, re.I) if exclude else None
        for label, url in self._load_tree():
            if rx.search(label) and not (ex and ex.search(label)):
                return url
        raise LookupError(f"no TÜİK table matches {pattern!r}")

    # -- download ----------------------------------------------------------
    def download_table(self, pattern: str, exclude: str | None = None) -> pd.DataFrame:
        """Resolve a table by name pattern, download its .xls, return the first
        sheet as a header-less DataFrame (raw cells — the parser handles layout)."""
        url = self.find_url(pattern, exclude)
        full = url if url.startswith("http") else BASE + url
        r = self.s.get(full, headers={"Accept": "*/*", "Referer": BASE + "/"}, timeout=self.timeout)
        r.raise_for_status()
        xl = pd.ExcelFile(io.BytesIO(r.content))  # xlrd (OLE2) / openpyxl by magic
        return xl.parse(xl.sheet_names[0], header=None)


@lru_cache(maxsize=1)
def get_client() -> TuikClient:
    return TuikClient()
