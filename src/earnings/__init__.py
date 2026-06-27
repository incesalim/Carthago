"""Earnings lane: per-bank, per-quarter earnings artifacts for BIST banks.

Two populators feed one table, ``bank_earnings``:

* ``from_kap`` — classifies the KAP disclosures already ingested into
  ``news_items`` (``source='kap'``) into earnings events. In practice KAP for
  Turkish banks only carries the *results filing* (``Finansal Rapor``, a
  ``disclosureType='FR'`` disclosure with structured ``year``/``period`` fields)
  — banks do NOT file earnings-call invites or investor-presentation decks on
  KAP, so those kinds stay empty from this source. The classifier still
  recognises them by keyword so the lane lights up automatically if that ever
  changes.
* ``presentations`` — discovers each bank's quarterly investor/earnings
  presentation PDF from its IR site, reusing the audit-lane discovery engine
  (``src/audit_reports/discovery.py``). These are the actual "earnings
  presentation" artifacts (``kind='presentation_deck'``).
"""
