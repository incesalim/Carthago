"""Turn KAP Genel Bilgi Formu itemObjects into tidy kap_ownership rows.

Items extracted (all under the form's §5 "Sermaye ve Ortaklık Yapısı"):

- ``kpy41_acc5_sermayede_dogrudan``   → item 'shareholder' — direct holders
  of ≥5% of capital/voting rights, plus DİĞER and TOPLAM rows. Non-listed
  KAP members file the variant ``kpy41_acc5_ortaklik_yapisi`` instead
  (same grid minus voting rights; used only when the primary is absent).
- ``kpy41_acc5_son_durum_sermayeye``  → item 'indirect_shareholder' — ≥5%
  indirect (ultimate) holders.
- ``kpy41_acc5_fiili_dolasimdaki_pay``→ item 'free_float' — actual free
  float, nominal TL + % (KAP refreshes this one near-daily for listed banks).
- ``kpy41_acc5_odenmis_sermaye``      → item 'paid_in_capital' (scalar TL;
  non-listed variant ``…_odenmis_sermaye_2``).
- ``kpy41_acc5_kayitli_sermaye_tavani``→ item 'capital_ceiling' (scalar TL;
  non-listed variant ``…_kayitli_sermaye_tavani_2``).

Caveat: in the non-listed ``ortaklik_yapisi`` grid some banks enter the
ratio into the TL column too (e.g. Ziraat reports shareInCapital "100");
``ratio_pct`` is the authoritative field there.

Values keep KAP's Turkish number formatting at the source; they are parsed
to floats here. ``as_of`` is the filing date of the form item — ownership
rows can be years old if the structure hasn't changed since.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class OwnershipRow:
    bank_ticker: str
    bank_name: str
    kap_company_id: int
    item: str
    seq: int
    holder: str | None
    share_tl: float | None
    ratio_pct: float | None
    voting_pct: float | None
    as_of: str | None


def parse_tr_number(s: object) -> float | None:
    """'2.119.027.173,7' → 2119027173.7; also accepts '100', '294493196,25'."""
    if s is None:
        return None
    t = str(s).strip().replace("%", "").replace(" ", "")
    if not t or t in {"-", "—"}:
        return None
    # Dots are thousands separators only when a decimal comma is present or
    # they group exactly 3 digits; KAP uses Turkish formatting throughout.
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_as_of(s: object) -> str | None:
    """Normalise KAP's date spellings to ISO YYYY-MM-DD.

    Seen in the wild: '01/08/2020', '17/06/2016 16:36:29', '20260610'.
    """
    if not s:
        return None
    t = str(s).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _grid(value: object) -> list[dict]:
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def ownership_rows(
    bank_ticker: str,
    bank_name: str,
    kap_company_id: int,
    items: dict[str, dict],
) -> list[OwnershipRow]:
    rows: list[OwnershipRow] = []

    def add(item: str, seq: int, holder: str | None, share: object,
            ratio: object, voting: object, as_of: object) -> None:
        rows.append(OwnershipRow(
            bank_ticker=bank_ticker,
            bank_name=bank_name,
            kap_company_id=kap_company_id,
            item=item,
            seq=seq,
            holder=(holder or "").strip() or None,
            share_tl=parse_tr_number(share),
            ratio_pct=parse_tr_number(ratio),
            voting_pct=parse_tr_number(voting),
            as_of=parse_as_of(as_of),
        ))

    direct = items.get("kpy41_acc5_sermayede_dogrudan")
    if not (direct and _grid(direct.get("value"))):
        # Non-listed members file the same grid under a variant key.
        direct = items.get("kpy41_acc5_ortaklik_yapisi")
    if direct:
        for i, r in enumerate(_grid(direct.get("value"))):
            add("shareholder", i, r.get("shareholder"), r.get("shareInCapital"),
                r.get("ratioInCapital"), r.get("votingRightRatio"),
                direct.get("creationDate"))

    indirect = items.get("kpy41_acc5_son_durum_sermayeye")
    if indirect:
        for i, r in enumerate(_grid(indirect.get("value"))):
            add("indirect_shareholder", i, r.get("shareholder"),
                r.get("shareInCapital"), r.get("ratioInCapital"), None,
                indirect.get("creationDate"))

    free = items.get("kpy41_acc5_fiili_dolasimdaki_pay")
    if free:
        for i, r in enumerate(_grid(free.get("value"))):
            add("free_float", i, r.get("isin"), r.get("actualSharesOutstanding"),
                r.get("actualOutstandingSharesRatio"), None,
                r.get("creationDate") or free.get("creationDate"))

    for keys, item_name in (
        (("kpy41_acc5_odenmis_sermaye", "kpy41_acc5_odenmis_sermaye_2"),
         "paid_in_capital"),
        (("kpy41_acc5_kayitli_sermaye_tavani", "kpy41_acc5_kayitli_sermaye_tavani_2"),
         "capital_ceiling"),
    ):
        for key in keys:
            obj = items.get(key)
            if obj and isinstance(obj.get("value"), (str, int, float)):
                val = parse_tr_number(obj["value"])
                if val is not None:
                    add(item_name, 0, None, obj["value"], None, None,
                        obj.get("creationDate"))
                    break

    return rows
