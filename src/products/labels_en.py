"""English labels for the product-shelf benchmark — authored once, exact.

These are the column headers on a regulatory-adjacent grid, so they are authored
by hand (not machine-translated), the same discipline migration 0032 used for the
BDDK English labels. The Turkish source lives in data/product_benchmark/TAXONOMY.md
and aggregate.py's LABELS; build.py asserts these keys match CODES exactly, so a
taxonomy change that isn't reflected here fails the build rather than shipping a
blank column.
"""
from __future__ import annotations

BLOCKS_EN: dict[str, str] = {
    "A": "Deposits & savings",
    "B": "Personal lending",
    "C": "Cards & payments",
    "D": "Investment",
    "E": "Insurance & pension",
    "F": "Channels & digital",
    "G": "SME / merchant",
    "H": "Trade finance",
    "I": "Corporate & treasury",
    "J": "Group subsidiaries",
}

# Shown on the four-state legend and the cell detail.
STATES_EN: dict[str, str] = {
    "yes": "Has it",
    "partial": "Partial",
    "no": "No",
    "unknown": "Unverified",
}

# code -> English attribute label. Order/blocks/distinctive come from aggregate.py.
LABELS_EN: dict[str, str] = {
    # A — Deposits & savings
    "A01": "Time TL deposit / participation account",
    "A02": "FX deposit / participation account",
    "A03": "Gold account (buy/sell grams)",
    "A04": "Silver / platinum / other precious-metal account",
    "A05": "FX-protected deposit (KKM/DDM) still open",
    "A06": "Child / youth account",
    "A07": "Automatic / goal-based savings",
    "A08": "Pensioner salary promotion",
    "A09": "Daily-yield / flexible account (no term break)",
    # B — Personal lending
    "B01": "Personal loan / financing",
    "B02": "Mortgage / housing finance",
    "B03": "Vehicle loan",
    "B04": "Overdraft / revolving credit line",
    "B05": "Card instalment cash advance",
    "B06": "Green personal loan (EV / solar / efficiency)",
    "B07": "Education / student loan",
    "B08": "Property-backed personal loan",
    "B09": "Debt transfer / loan restructuring",
    # C — Cards & payments
    "C01": "Own credit-card brand",
    "C02": "Virtual card",
    "C03": "Apple Pay",
    "C04": "Google Wallet / Google Pay",
    "C05": "Prepaid / gift card",
    "C06": "Cardless ATM withdrawal via QR",
    "C07": "FAST + Easy Addressing (instant payments)",
    "C08": "Own digital wallet",
    "C09": "Cross-border money transfer (WU / UPT / MoneyGram / Wise)",
    "C10": "Commercial / corporate credit card",
    # D — Investment
    "D01": "Mutual funds",
    "D02": "Third-party funds via TEFAS",
    "D03": "In-house asset-manager funds",
    "D04": "Equity trading (bank's own channel)",
    "D05": "Derivatives exchange (VIOP) / futures",
    "D06": "Eurobonds / corporate bonds / sukuk",
    "D07": "Government bonds (DIBS) / sovereign sukuk",
    "D08": "Leveraged FX (forex)",
    "D09": "Robo-advisor / automated portfolio",
    "D10": "Physical gold purchase / delivery",
    "D11": "Foreign equities (US markets etc.)",
    "D12": "Crypto-asset access",
    "D13": "Private banking segment",
    # E — Insurance & pension
    "E01": "Private pension (BES)",
    "E02": "Auto-enrolment pension (OKS)",
    "E03": "Life insurance",
    "E04": "Motor / traffic insurance",
    "E05": "Home insurance / DASK",
    "E06": "Complementary health insurance",
    "E07": "In-group insurance company",
    "E08": "In-group pension company",
    # F — Channels & digital
    "F01": "Mobile app (iOS + Android)",
    "F02": "Remote onboarding (video ID)",
    "F03": "Fully digital account opening",
    "F04": "Open banking / developer API",
    "F05": "AI / voice assistant (in-app)",
    "F06": "Own ATM network",
    "F07": "Separate all-digital sub-brand",
    "F08": "Full English website",
    "F09": "WhatsApp banking",
    "F10": "Branch network",
    # G — SME / merchant
    "G01": "Business / tradesman loan",
    "G02": "KGF-guaranteed loan",
    "G03": "Agriculture / farmer loan",
    "G04": "Commercial vehicle / equipment finance",
    "G05": "Physical POS",
    "G06": "Virtual POS / e-commerce payments",
    "G07": "Cash-register POS (OKC)",
    "G08": "Mobile / softPOS (Android POS)",
    "G09": "Merchant instalment programme",
    "G10": "Cheque book / cheque collection",
    "G11": "Direct debit (DBS) / supplier finance",
    "G12": "e-Invoice / pre-accounting / digital SME suite",
    "G13": "Branchless SME account opening",
    "G14": "Targeted segment programme (women entrepreneurs etc.)",
    # H — Trade finance
    "H01": "Letters of credit",
    "H02": "Documentary collection / acceptance-aval",
    "H03": "Letters of guarantee",
    "H04": "e-Letter of guarantee",
    "H05": "Eximbank-intermediated export loans",
    "H06": "Forfaiting / discounting / receivables finance",
    "H07": "Own foreign branch or bank subsidiary",
    # I — Corporate & treasury
    "I01": "Investment / project finance",
    "I02": "Syndicated / club loans",
    "I03": "FX forward",
    "I04": "Swap (currency / rate)",
    "I05": "Options",
    "I06": "Commodity hedging",
    "I07": "Bond / sukuk issuance arranging",
    "I08": "IPO underwriting",
    "I09": "M&A / corporate-finance advisory",
    "I10": "Cash management + ERP / host-to-host",
    "I11": "Payroll package",
    "I12": "Sustainability-linked / green commercial loan",
    # J — Group subsidiaries
    "J01": "Asset-management company",
    "J02": "Brokerage (securities / investment)",
    "J03": "Insurance company",
    "J04": "Pension company",
    "J05": "Leasing (financial leasing)",
    "J06": "Factoring",
    "J07": "Payment / e-money institution",
    "J08": "Foreign bank subsidiary",
}

# Benchmark peer clusters -> English (data/product_benchmark/aggregate.py CLUSTERS).
CLUSTERS_EN: dict[str, str] = {
    "Kamu mevduat": "State deposit",
    "Büyük özel": "Large private",
    "Yabancı büyük": "Foreign — large",
    "Yabancı orta": "Foreign — mid",
    "Özel orta": "Private — mid",
    "Katılım özel": "Participation — private",
    "Katılım kamu": "Participation — state",
    "Dijital mevduat": "Digital deposit",
    "Dijital katılım": "Digital participation",
    "İhtisas/niş": "Specialist / niche",
}
