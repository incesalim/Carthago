# `src/analyst/` — deterministic detectors

Deterministic detectors over the audit snapshot that surface what moved, then
feed the memo/research layers. No LLM here.

- `detect_unit_change.py`, `detect_cross_period.py`, `detect_divergence.py`,
  `detect_opinion_change.py`, `detect_perimeter_change.py` — the detectors.
- `classify_basis.py`, `extract_basis_metadata.py`, `signals.py`, `periods.py`,
  `snapshot.py`, `schema.py` — supporting pieces.

**Entry points:** `scripts/analyst/detect.py` (`analyst-daily.yml`),
`scripts/analyst/prepare_filing_text.py` (`analyst-research.yml`).

**Writes:** `analyst_signals`, `analyst_basis_metadata`, `analyst_notes`
(staging `data/analyst.db`). Docs: [`docs/ANALYST.md`](../../docs/ANALYST.md),
[`docs/ANALYST_V2.md`](../../docs/ANALYST_V2.md).