"""Deterministic string normalization for TEFAS fund data.

The API gives no structured manager or category field — both are derived
from ``fonUnvan`` (the fund's legal name), and the allocation endpoint uses
abbreviated keys. Everything here is pure-Python and unit-tested; changing
any rule means re-running the backfill (aggregates are computed at ingest).

Allocation key legend verified against tefas-crawler v0.5.0's BreakdownSchema
(the legacy uppercase keys map 1:1 to today's lowercase ones, e.g. ÖSDB→osdb,
VİNT→vint, KİBD→kibd). ``bpp``/``btaa``/``btas``/``gyy``/``gsyy`` are newer
fields absent from that legend: bpp is Borsa Para Piyasası (negative values =
money-market borrowing) and gyy/gsyy are listed REIT / VC-trust shares;
btaa/btas remain unidentified and roll to ``other``.
"""
from __future__ import annotations

_TR_UPPER = str.maketrans({"i": "İ", "ı": "I"})


def tr_upper(text: str) -> str:
    """Turkish-safe uppercase (i→İ, ı→I before ASCII upper)."""
    return text.translate(_TR_UPPER).upper()


def _norm(fon_unvan: str) -> str:
    return " ".join(tr_upper(fon_unvan or "").split())


def extract_manager(fon_unvan: str) -> str:
    """Manager name from the fund-title prefix.

    ``"AK PORTFÖY ÇOKLU VARLIK … FON"`` → ``"AK PORTFÖY"``;
    EMK funds are run by pension companies
    (``"ALLIANZ HAYAT VE EMEKLİLİK A.Ş. … FONU"`` → prefix through ``A.Ş.``).
    Mis-bucketing only affects future manager views — sector sums are
    invariant to the grouping.
    """
    name = _norm(fon_unvan)
    if not name:
        return "BİLİNMEYEN"
    tokens = name.replace("PORTFOY", "PORTFÖY").split()
    if "PORTFÖY" in tokens:
        return " ".join(tokens[: tokens.index("PORTFÖY") + 1])
    if "EMEKLİLİK" in tokens:
        idx = tokens.index("EMEKLİLİK")
        for j in range(idx + 1, min(idx + 5, len(tokens))):
            if tokens[j] in ("A.Ş.", "A.S.", "A.Ş", "A.S"):
                return " ".join(tokens[: j + 1])
        return " ".join(tokens[: idx + 1])
    return " ".join(tokens[:2])


# First match wins — specific categories before generic ones, so e.g.
# "KATILIM HİSSE SENEDİ FONU" lands in equity, not participation.
_CATEGORY_KEYWORDS = [
    ("PARA PİYASASI", "money_market"),
    ("HİSSE SENEDİ", "equity"),
    ("BORÇLANMA ARAÇLARI", "debt"),
    ("KİRA SERTİFİKALARI", "lease_certificates"),
    ("SERBEST", "hedge"),
    ("ALTIN", "precious_metals"),
    ("KIYMETLİ MADEN", "precious_metals"),
    ("FON SEPETİ", "fund_of_funds"),
    ("KATILIM", "participation"),
    ("DEĞİŞKEN", "mixed"),
    ("KARMA", "mixed"),
]


def categorize_fund(fon_unvan: str) -> str:
    name = _norm(fon_unvan)
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in name:
            return category
    return "other"


# Allocation response keys that are not percentage fields.
ALLOCATION_META_KEYS = frozenset({"fonKodu", "fonUnvan", "tarih", "bilFiyat", "rn"})

# API allocation field → display asset class. Unknown keys (new instruments)
# roll to "other" at aggregation time and are logged with their weight.
ASSET_ROLLUP: dict[str, str] = {
    # equities
    "hs": "equity_tr",            # Hisse Senedi
    "gyy": "equity_tr",           # Gayrimenkul Yatırım Ortaklığı payı (listed REIT)
    "gsyy": "equity_tr",          # Girişim Sermayesi Yatırım Ortaklığı payı
    "yhs": "equity_foreign",      # Yabancı Hisse Senedi
    # TL government debt
    "dt": "gov_debt_tr",          # Devlet Tahvili
    "hb": "gov_debt_tr",          # Hazine Bonosu
    # FX government debt
    "kba": "gov_debt_fx",         # Kamu Dış Borçlanma Araçları (eurobond)
    "eut": "gov_debt_fx",         # Eurotahvil
    "db": "gov_debt_fx",          # Döviz Ödemeli Bono
    "dot": "gov_debt_fx",         # Dövize Ödemeli Tahvil
    "kibd": "gov_debt_fx",        # Döviz Kamu İç Borçlanma Araçları
    # corporate debt (TL + FX + securitized)
    "ost": "corp_debt",           # Özel Sektör Tahvili
    "fb": "corp_debt",            # Finansman Bonosu
    "bb": "corp_debt",            # Banka Bonosu
    "vdm": "corp_debt",           # Varlığa Dayalı Menkul Kıymetler
    "osdb": "corp_debt",          # Özel Sektör Dış Borçlanma Araçları
    # foreign issuers' debt
    "yba": "foreign_debt",        # Yabancı Borçlanma Aracı
    "ybkb": "foreign_debt",       # Yabancı Kamu Borçlanma Araçları
    "ybosb": "foreign_debt",      # Yabancı Özel Sektör Borçlanma Araçları
    # participation-finance instruments
    "kh": "participation",        # Katılma Hesabı
    "khtl": "participation",      # Katılma Hesabı (TL)
    "khd": "participation",       # Katılma Hesabı (Döviz)
    "khau": "participation",      # Katılma Hesabı (Altın)
    "kks": "participation",       # Kamu Kira Sertifikaları
    "kkstl": "participation",     # Kamu Kira Sertifikaları (TL)
    "kksd": "participation",      # Kamu Kira Sertifikaları (Döviz)
    "kksyd": "participation",     # Kamu Yurt Dışı Kira Sertifikaları
    "osks": "participation",      # Özel Sektör Kira Sertifikaları
    "oksyd": "participation",     # Özel Sektör Yurt Dışı Kira Sertifikaları
    # money market & deposits (repo can be negative = borrowing)
    "r": "money_market",          # Repo
    "tr": "money_market",         # Ters Repo
    "tpp": "money_market",        # Takasbank Para Piyasası
    "bpp": "money_market",        # Borsa Para Piyasası
    "vm": "money_market",         # Vadeli Mevduat
    "vmtl": "money_market",       # Vadeli Mevduat (TL)
    "vmd": "money_market",        # Vadeli Mevduat (Döviz)
    "vmau": "money_market",       # Vadeli Mevduat (Altın)
    "vint": "money_market",       # Vadeli İşlemler Nakit Teminatları
    # precious metals (incl. gold-denominated sovereigns)
    "km": "precious_metals",      # Kıymetli Madenler
    "kmbyf": "precious_metals",   # Kıymetli Madenler BYF
    "kmkba": "precious_metals",   # Kıymetli Madenler Kamu Borçlanma Araçları
    "kmkks": "precious_metals",   # Kıymetli Madenler Kamu Kira Sertifikaları
    # fund units
    "yyf": "fund_units",          # Yatırım Fonları Katılma Payları
    "byf": "fund_units",          # BYF Katılma Payları (ETF)
    "ybyf": "fund_units",         # Yabancı Borsa Yatırım Fonları
    "fkb": "fund_units",          # Fon Katılma Belgesi
    "gykb": "fund_units",         # Gayrimenkul Yatırım Fonu Katılma Payları
    "gsykb": "fund_units",        # Girişim Sermayesi YF Katılma Payları
    # everything else
    "d": "other",                 # Diğer
    "t": "other",                 # Türev Araçları
    "gas": "other",               # Gayrimenkul Sertifikası
    "ymk": "other",               # Yabancı Menkul Kıymet (unspecified)
    "btaa": "other",              # unidentified (new field, post-2021)
    "btas": "other",              # unidentified (new field, post-2021)
}

ASSET_CLASSES = [
    "equity_tr", "equity_foreign", "gov_debt_tr", "gov_debt_fx", "corp_debt",
    "foreign_debt", "participation", "money_market", "precious_metals",
    "fund_units", "other",
]
