# `src/transcripts/` — earnings-call transcripts

English earnings-call transcripts for the listed banks that publish them.

- `alphaspread.py` — source client/parser; `loader.py` / `schema.py` —
  persistence.

**Entry point:** `scripts/update_transcripts.py`
(`refresh-transcripts-weekly.yml` — manual, no cron yet).

**Writes:** `bank_call_transcripts`.