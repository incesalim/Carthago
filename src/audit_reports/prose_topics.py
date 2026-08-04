"""Canonical topics for audit-report prose — the normalized key beside the
as-reported address.

`heading_path` records where a block sits in the filing *as the bank printed it*.
That is the right thing to store and the wrong thing to query, because the same
disclosure moves. Measured across the 162 local filings:

  * the equity note appears at **13 distinct paths** (5.V, 5.I.g.1, 5.II.12, 5.2,
    5.I.i.1, …), deposits at 13, derivatives at 26;
  * the **audit firm does not explain it** — KPMG's deposit note sits at 5.II.1.2,
    5.II.a.1 *and* 5.II.a; Deloitte's at three others;
  * it is not even stable within a bank — 6 of 14 banks use more than one path
    for the deposit note across their own filings.

What *is* stable is the caption. BRSA mandates the note wording, so 19 banks print
"Gerçeğe uygun değer farkı diğer kapsamlı gelire yansıtılan finansal varlıklar"
character-for-character. So the canonical key is derived from the heading TEXT,
not from its position.

Rules are ordered most-specific-first and matched on the folded heading: the FVOCI
and FVPL captions share their first five words, and a general rule tested first
would swallow the specific one — the same failure the section-role rules have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Captions carry slashes, commas and parentheses — "kâr/zarara yansıtılan" never
# matches a keyword written "KAR ZARARA YANSITILAN" unless punctuation is
# flattened first. This single omission cost 51 FVPL headings alone.
_PUNCT = re.compile(r"[^A-Z0-9]+")


def normalise(folded: str) -> str:
    return _PUNCT.sub(" ", folded).strip()


@dataclass(frozen=True)
class Topic:
    slug: str
    label_en: str
    label_tr: str
    group: str          # coarse bucket for the UI: assets / liabilities / pl / …
    keywords: tuple[str, ...]   # folded, uppercase, ASCII — TR and EN both


# Ordered. A caption matches the FIRST topic whose keyword it contains.
TOPICS: list[Topic] = [
    # --- §5 assets ---------------------------------------------------------
    Topic("fvoci_assets", "Financial assets at FVOCI",
          "GUD farkı diğer kapsamlı gelire yansıtılan finansal varlıklar", "assets",
          ("DIGER KAPSAMLI GELIRE YANSITILAN", "FAIR VALUE THROUGH OTHER COMPREHENSIVE")),
    Topic("fvpl_assets", "Financial assets at FVPL",
          "GUD farkı kâr/zarara yansıtılan finansal varlıklar", "assets",
          ("KAR ZARARA YANSITILAN", "FAIR VALUE THROUGH PROFIT")),
    Topic("amortised_cost_assets", "Financial assets at amortised cost",
          "İtfa edilmiş maliyeti üzerinden değerlenen finansal varlıklar", "assets",
          ("ITFA EDILMIS MALIYET", "AMORTISED COST", "AMORTIZED COST")),
    Topic("cash_and_cbrt", "Cash and balances with the central bank",
          "Nakit değerler ve TCMB", "assets",
          ("NAKIT DEGERLER", "MERKEZ BANKASI HESABI", "CASH AND BALANCES",
           "CENTRAL BANK OF")),
    Topic("banks_placements", "Banks and placements",
          "Bankalar ve yurt dışı bankalar", "assets",
          ("BANKALAR VE YURT DISI", "BANKALAR HESABINA ILISKIN", "BANKS HESAB",
           "DUE FROM BANKS")),
    Topic("derivatives", "Derivative instruments", "Türev finansal araçlar", "assets",
          ("TUREV FINANSAL", "TUREV ARAC", "ALIM SATIM AMACLI TUREV", "DERIVATIVE")),
    Topic("credit_derivatives", "Credit derivatives", "Kredi türevleri", "assets",
          ("KREDI TUREVLERINE", "CREDIT DERIVATIVE")),
    Topic("stage_loans", "Standard and close-monitoring loans",
          "Standart nitelikli ve yakın izlemedeki krediler", "assets",
          ("STANDART NITELIKLI", "YAKIN IZLEMEDEKI", "CLOSE MONITORING")),
    Topic("npl_policy", "Write-off / liquidation policy for NPLs",
          "Zarar niteliğindeki krediler için tasfiye politikası", "assets",
          ("ZARAR NITELIGINDEKI", "TASFIYE POLITIKA", "WRITE OFF POLIC")),
    Topic("consumer_loans", "Consumer loans and credit cards",
          "Tüketici kredileri ve bireysel kredi kartları", "assets",
          ("TUKETICI KREDILERI", "BIREYSEL KREDI KART", "CONSUMER LOANS")),
    Topic("commercial_loans", "Commercial instalment loans and corporate cards",
          "Taksitli ticari krediler ve kurumsal kredi kartları", "assets",
          ("TAKSITLI TICARI", "KURUMSAL KREDI KART", "COMMERCIAL INSTAL")),
    Topic("fx_indexed_loans", "FX-indexed loans", "Dövize endeksli krediler", "assets",
          ("DOVIZE ENDEKSLI", "FOREIGN CURRENCY INDEXED")),
    Topic("subsidiaries", "Investments in associates and subsidiaries",
          "İştirakler ve bağlı ortaklıklar", "assets",
          ("ISTIRAKLERE ILISKIN", "BAGLI ORTAKLIKLARA ILISKIN", "ASSOCIATES",
           "SUBSIDIARIES")),
    Topic("tangible_assets", "Tangible assets", "Maddi duran varlıklar", "assets",
          ("MADDI DURAN VARLIK", "TANGIBLE ASSET")),
    Topic("intangible_assets", "Intangible assets", "Maddi olmayan duran varlıklar",
          "assets", ("MADDI OLMAYAN DURAN", "INTANGIBLE ASSET")),
    Topic("held_for_sale", "Assets held for sale and discontinued operations",
          "Satış amaçlı elde tutulan ve durdurulan faaliyetler", "assets",
          ("SATIS AMACLI ELDE TUTULAN", "HELD FOR SALE", "DISCONTINUED OPERATION")),
    Topic("deferred_tax", "Deferred tax", "Ertelenmiş vergi", "assets",
          ("ERTELENMIS VERGI", "DEFERRED TAX")),

    # --- §5 liabilities and equity ----------------------------------------
    Topic("deposits", "Deposits", "Mevduat", "liabilities",
          ("MEVDUAT", "DEPOSIT")),
    Topic("funds_borrowed", "Funds borrowed", "Alınan krediler", "liabilities",
          ("ALINAN KREDILER", "FUNDS BORROWED", "FUNDS PROVIDED")),
    Topic("money_market", "Money-market funding", "Para piyasaları", "liabilities",
          ("PARA PIYASALARI", "MONEY MARKET")),
    Topic("securities_issued", "Securities issued", "İhraç edilen menkul kıymetler",
          "liabilities", ("IHRAC EDILEN MENKUL", "SECURITIES ISSUED", "DEBT SECURITIES ISSUED")),
    Topic("provisions", "Provisions", "Karşılıklar", "liabilities",
          ("KARSILIKLARA ILISKIN", "PROVISIONS")),
    Topic("paid_in_capital", "Paid-in capital and the registered-capital system",
          "Ödenmiş sermaye ve kayıtlı sermaye sistemi", "equity",
          ("ODENMIS SERMAYE", "KAYITLI SERMAYE", "PAID IN CAPITAL")),
    Topic("share_privileges", "Privileges on shares representing capital",
          "Sermayeyi temsil eden hisse senetlerine tanınan imtiyazlar", "equity",
          ("IMTIYAZLARA ILISKIN", "PRIVILEGES")),
    Topic("capital_changes", "Capital movements since the last financial year",
          "Son mali yıldan itibaren sermaye hareketleri", "equity",
          ("SON MALI YILIN", "SERMAYE HAREKET")),
    Topic("equity", "Equity", "Özkaynaklar", "equity",
          ("OZKAYNAK", "SHAREHOLDERS EQUITY")),

    # --- §5 P&L ------------------------------------------------------------
    Topic("tax_provision", "Tax provision on continuing/discontinued operations",
          "Sürdürülen/durdurulan faaliyetler vergi karşılığı", "pl",
          ("FAALIYETLER VERGI KARSILIGI", "TAX PROVISION")),
    Topic("pre_tax_profit", "Pre-tax profit on continuing/discontinued operations",
          "Sürdürülen/durdurulan faaliyetler vergi öncesi kâr", "pl",
          ("VERGI ONCESI KAR", "PROFIT BEFORE TAX")),
    Topic("net_profit", "Net profit for the period",
          "Dönem net kâr/zararı", "pl",
          ("DONEM NET KAR", "NET PROFIT", "NET INCOME FOR THE PERIOD")),
    Topic("banking_income_expense", "Ordinary banking income and expense items",
          "Olağan bankacılık işlemlerinden gelir ve gider kalemleri", "pl",
          ("OLAGAN BANKACILIK", "ORDINARY BANKING")),
    Topic("other_operating_expenses", "Other operating expenses",
          "Diğer faaliyet giderleri", "pl",
          ("DIGER FAALIYET GIDER", "OTHER OPERATING EXPENSE")),

    # --- §5 other disclosures ---------------------------------------------
    Topic("related_party", "Transactions with the bank's risk group",
          "Bankanın dahil olduğu risk grubu", "other",
          ("DAHIL OLDUGU RISK GRUB", "RISK GROUP")),
    Topic("services_on_behalf", "Services rendered on behalf of third parties",
          "Başkaları nam ve hesabına verilen hizmetler", "other",
          ("BASKALARI NAM VE HESABINA", "ON BEHALF OF THIRD")),
    Topic("audit_fees", "Fees for services from the independent auditor",
          "Bağımsız denetçiden alınan hizmetler", "other",
          ("DENETIM KURULUSUNDAN ALINAN", "DENETCIDEN ALINAN", "AUDIT FEE")),
    Topic("off_balance_commitments", "Contingencies and commitments from off-balance items",
          "Nazım hesap kalemlerinden muhtemel zararlar ve taahhütler", "other",
          ("NAZIM HESAP KALEMLERINDEN", "CONTINGENT LIABILIT", "COMMITMENTS")),
    Topic("subsequent_events", "Events after the reporting period",
          "Bilanço sonrası hususlar", "other",
          ("BILANCO SONRASI", "SUBSEQUENT EVENT", "AFTER THE REPORTING")),
    Topic("segment_reporting", "Segment reporting", "Bölümlere göre raporlama", "other",
          ("BOLUMLERE GORE RAPORLAMA", "BOLUMLEMEYE GORE", "SEGMENT REPORTING")),
    Topic("estimate_changes", "Changes in accounting estimates",
          "Tahminlerdeki değişiklikler", "other",
          ("TAHMINDEKI DEGISIKLIK", "TAHMINLERDEKI DEGISIKLIK", "YAPILAN BIR TAHMIN",
           "CHANGE IN ACCOUNTING ESTIMATE")),
    Topic("historical_performance", "Historical income, profitability and liquidity",
          "Geçmiş dönem gelir, kârlılık ve likidite bilgileri", "other",
          ("GELIRLERI KARLILIGI VE LIKIDITESINE", "PROFITABILITY AND LIQUIDITY")),
    Topic("cash_flow_items", "Other items in the cash-flow statement",
          "Nakit akış tablosundaki diğer kalemler", "other",
          ("NAKIT AKIS TABLOSUNDA YER ALAN", "CASH FLOW STATEMENT")),

    Topic("employee_benefits", "Employee benefit obligations",
          "Çalışanların haklarına ilişkin yükümlülükler", "liabilities",
          ("CALISANLARIN HAKLARINA", "EMPLOYEE BENEFIT", "EMPLOYEE RIGHTS")),
    Topic("fee_income", "Fee and commission income and expense",
          "Ücret ve komisyon gelir ve giderleri", "pl",
          ("UCRET VE KOMISYON", "FEE AND COMMISSION", "FEES AND COMMISSION")),
    Topic("repo_securities_lending", "Repos and securities lending",
          "Satış ve geri alış anlaşmaları, menkul değer ödünç işlemleri", "liabilities",
          ("GERI ALIS ANLASMALARI", "ODUNC VERILMES", "REPURCHASE AGREEMENT",
           "SECURITIES LENDING")),
    Topic("consolidation_basis", "Basis of consolidation",
          "Konsolidasyon esasları", "policy",
          ("KONSOLIDE FINANSAL TABLOLARININ DUZENLENMESIN", "KONSOLIDASYON ESAS",
           "BASIS OF CONSOLIDATION", "CONSOLIDATION PRINCIPLES")),
    Topic("accounting_basis", "Basis of preparation",
          "Finansal tabloların hazırlanma esasları", "policy",
          ("HAZIRLANMASINDA IZLENEN MUHASEBE", "SUNUM ESASLARI",
           "FINANSAL TABLOLAR ILE BUNLARA ILISKIN",
           "BASIS OF PRESENTATION", "PREPARATION OF THE FINANCIAL STATEMENTS")),
    Topic("fx_policy", "FX transactions and instrument strategy",
          "Finansal araç kullanım stratejisi ve yabancı para işlemler", "policy",
          ("KULLANIM STRATEJISI", "YABANCI PARA CINSI", "FOREIGN CURRENCY TRANSACTION",
           "STRATEGY FOR USE OF FINANCIAL")),
    Topic("forward_option_contracts", "Forwards, options and derivative products",
          "Vadeli işlem ve opsiyon sözleşmeleri", "assets",
          ("VADELI ISLEM VE OPSIYON", "TUREV URUN", "FORWARD AND OPTION")),
    Topic("offsetting", "Offsetting of financial instruments",
          "Finansal varlık ve yükümlülüklerin netleştirilmesi", "policy",
          ("NETLESTIRILMES", "OFFSETTING")),
    Topic("impairment_policy", "Impairment of financial assets",
          "Finansal varlıklarda değer düşüklüğü", "policy",
          ("DEGER DUSUKLUGU", "IMPAIRMENT OF FINANCIAL")),
    Topic("goodwill", "Goodwill", "Şerefiye", "assets",
          ("SEREFIYE", "GOODWILL")),

    Topic("leases", "Leases", "Kiralama işlemleri", "policy",
          ("KIRALAMA ISLEMLERINE", "LEASING TRANSACTION", "LEASES")),
    Topic("borrowings", "Borrowings", "Borçlanmalar", "liabilities",
          ("BORCLANMALARA ILISKIN", "BORROWINGS")),
    Topic("government_grants", "Government grants", "Devlet teşvikleri", "other",
          ("DEVLET TESVIK", "GOVERNMENT GRANT", "GOVERNMENT INCENTIVE")),
    Topic("funding_policy", "Diversity of funding sources and maturities",
          "Fon kaynaklarının ve sürelerinin çeşitliliği", "risk",
          ("FON KAYNAKLARININ VE SURELERININ", "DIVERSITY OF FUNDING")),
    Topic("counterparty_credit_risk", "Counterparty credit risk",
          "Karşı taraf kredi riski", "risk",
          ("KARSI TARAF KREDI RISKI", "COUNTERPARTY CREDIT RISK")),

    # --- §4 risk -----------------------------------------------------------
    Topic("capital_adequacy", "Capital adequacy", "Sermaye yeterliliği", "risk",
          ("SERMAYE YETERLILIGI", "CAPITAL ADEQUACY")),
    Topic("credit_risk", "Credit risk", "Kredi riski", "risk",
          ("KREDI RISKINE ILISKIN", "CREDIT RISK")),
    Topic("market_risk", "Market risk", "Piyasa riski", "risk",
          ("PIYASA RISKINE ILISKIN", "MARKET RISK")),
    Topic("fx_risk", "Currency risk", "Kur riski", "risk",
          ("KUR RISKINE ILISKIN", "CURRENCY RISK")),
    Topic("interest_rate_risk", "Interest-rate risk", "Faiz oranı riski", "risk",
          ("FAIZ ORANI RISKINE", "INTEREST RATE RISK")),
    Topic("liquidity_risk", "Liquidity risk", "Likidite riski", "risk",
          ("LIKIDITE RISKI", "LIQUIDITY RISK", "LIQUIDITY COVERAGE")),
    Topic("operational_risk", "Operational risk", "Operasyonel risk", "risk",
          ("OPERASYONEL RISK", "OPERATIONAL RISK")),
    Topic("leverage_ratio", "Leverage ratio", "Kaldıraç oranı", "risk",
          ("KALDIRAC ORANI", "LEVERAGE RATIO")),
]

BY_SLUG: dict[str, Topic] = {t.slug: t for t in TOPICS}


def topic_of(heading: str | None, fold=None) -> str | None:
    """Canonical topic slug for a heading, or None when nothing matches.

    `fold` is injected so this module stays import-light; prose.py passes its own
    Turkish-safe folder.
    """
    if not heading:
        return None
    if fold is None:                       # pragma: no cover - convenience path
        from .prose import _fold as fold
    folded = normalise(fold(heading))
    for t in TOPICS:
        if any(k in folded for k in t.keywords):
            return t.slug
    return None
