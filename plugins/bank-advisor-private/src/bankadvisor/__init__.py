"""
BankAdvisor module for financial reporting and KPIs.
"""
from .io_loader import load_all, get_data_paths, DataPaths
from .metrics import monthly_kpis
from .transforms import prepare_cnbv, prepare_castigos, enrich_with_castigos, normalize_bank_name

__all__ = [
    "load_all",
    "get_data_paths",
    "DataPaths",
    "monthly_kpis",
    "prepare_cnbv",
    "prepare_castigos",
    "enrich_with_castigos",
    "normalize_bank_name",
]
