"""Deterministic Money Operations engine. Integer minor units only.

Public surface used by the service layer. Builder 1 owns implementations in this
package. A model must not calculate canonical figures from this module.
"""
from .engine import (
    CALCULATION_VERSION,
    analyze,
    attribute_drivers,
    compare_periods,
    reconcile_account,
    validate_dataset,
)
from .ingest import DatasetValidationError

__all__ = [
    'CALCULATION_VERSION',
    'DatasetValidationError',
    'analyze',
    'attribute_drivers',
    'compare_periods',
    'reconcile_account',
    'validate_dataset',
]
