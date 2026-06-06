"""TBB (Türkiye Bankalar Birliği) digital-banking statistics lane.

Quarterly sector-wide digital / internet / mobile banking statistics published
by the Banks Association of Turkey as a legacy ``.xls`` workbook. This package
discovers the per-quarter download, parses the multi-sheet workbook into a tidy
long table, and upserts it into the bulletin-lane SQLite DB.

Modules:
- :mod:`src.tbb.parser` — workbook → tidy ``TbbStat`` rows
- :mod:`src.tbb.client` — discover quarterly reports + download the ``.xls``
- :mod:`src.tbb.schema` — ``tbb_digital_stats`` DDL + ``init_schema``
- :mod:`src.tbb.loader` — idempotent upsert
"""
