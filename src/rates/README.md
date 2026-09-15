# `src/rates/` — advertised (posted) rates

The only **per-bank** rate source: loan rates from doviz.com and deposit rates
from hangikredi. (EVDS/BDDK publish rates at sector level only.)

- `scraper.py` — scrape + parse; `schema.py` — table. Runs as a module.

**Entry point:** `python -m src.rates.scraper` (`refresh-advertised-rates.yml`,
Mon 06:00 UTC).

**Writes:** `bank_advertised_rates`. Sources expose only "today", so history
accretes forward.