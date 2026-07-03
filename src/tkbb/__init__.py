"""TKBB (Türkiye Katılım Bankaları Birliği) digital-banking data lane.

Participation banks publish their digital statistics on TKBB's "Veri Peteği"
portal (https://tkbb.org.tr/veripetegi), served by a Turboard BI instance at
https://veri-petegi.tkbb.org.tr whose JSON API is publicly readable.

Modules:
- ``turboard``     — minimal generic client for the Turboard JSON:API
- ``digital``      — lane A: quarterly digital stats (dashlet registry, fetch)
- ``acquisition``  — lane B: monthly remote-vs-branch customer acquisition
- ``schema``       — SQLite/D1 DDL (mirrored by web/migrations/0017_tkbb_stats.sql)
- ``loader``       — idempotent INSERT OR REPLACE upserts
"""
