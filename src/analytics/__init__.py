"""
BDDK Analytics Module
=====================
This module provides data processing and metrics calculation for BDDK banking data.
"""

from .metrics_catalog import (
    METRICS_CATALOG,
    CALCULATED_RATIOS,
    GROWTH_METRICS,
    BANK_TYPES,
    CURRENCY_TYPES,
    PRIMARY_BANK_TYPES,
    METRIC_CATEGORIES,
    get_metric,
    get_metrics_by_category,
    list_all_metrics,
)

from .metrics_engine import MetricsEngine, engine
from .data_store import MetricsDataStore, data_store
from . import metrics_ext

__all__ = [
    # Catalog
    "METRICS_CATALOG",
    "CALCULATED_RATIOS",
    "GROWTH_METRICS",
    "BANK_TYPES",
    "CURRENCY_TYPES",
    "PRIMARY_BANK_TYPES",
    "METRIC_CATEGORIES",
    "get_metric",
    "get_metrics_by_category",
    "list_all_metrics",
    # Engine
    "MetricsEngine",
    "engine",
    # Data Store
    "MetricsDataStore",
    "data_store",
]
