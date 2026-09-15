# `src/products/` — product-shelf benchmark

Product attributes and per-bank product offering/profile, seeded from a frozen
snapshot.

- `build.py` — build the product shelf; `labels_en.py` — English labels;
  `schema.py` — tables. Runs as a module.

**Entry point:** `python -m src.products.build` (`build-products.yml`, manual).

**Writes:** `product_attributes`, `bank_products`, `bank_product_profile`.