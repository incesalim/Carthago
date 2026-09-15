# `src/kap/` — KAP ownership

Ownership data from the KAP Genel Bilgi Formu (§5 and §7).

- `client.py` — KAP API; `parser.py` — form sections → rows; `loader.py` /
  `schema.py` — local persistence.

**Entry point:** `scripts/update_kap_ownership.py` (via `scripts/refresh.py`;
weekly full replace).

**Writes:** `kap_ownership`.