"""Faaliyet Raporları (bank annual / activity reports) lane.

Deterministic extraction of *franchise & operational* statistics (branch /
employee / ATM / POS / merchant / customer / card counts) from Turkish bank
annual reports — narrative PDFs published on the same investor-relations pages
the audit-report lane already tracks.

This lane is fully separate from ``src/audit_reports`` (the BS/P&L/audit tables
are frozen). The only cross-lane touch is a *read-only* sanity cross-check of
branch/employee counts against ``bank_audit_profile`` (see ``loader.py``).

No LLM API is used — extraction is regex + pdf word-coordinate anchors, exactly
like the audit extractors (cf. ``audit_reports/loans_by_sector.py`` and
``audit_reports/bank_profile.py``).
"""
