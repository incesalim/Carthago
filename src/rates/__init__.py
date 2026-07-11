"""Advertised per-bank lending & deposit rates lane.

Scrapes the rates each Turkish bank *advertises to new customers* — the one
per-bank rate the pipeline couldn't otherwise get. TCMB/EVDS and the BDDK
bulletin publish loan/deposit rates only at sector / bank-type granularity;
the audited P&L gives each bank's *realized* (effective) yield/cost, not its
posted rate. This lane fills that gap by parsing two public comparison pages.
"""
