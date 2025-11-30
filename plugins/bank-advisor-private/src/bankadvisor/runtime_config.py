"""
Runtime configuration loader for BankAdvisor.

Loads settings from config/bankadvisor.yaml and environment variables.
Environment variables take precedence over YAML config.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

import structlog

logger = structlog.get_logger(__name__)


class RuntimeConfig:
    """
    Centralized runtime configuration.

    Priority (highest to lowest):
    1. Environment variables
    2. config/bankadvisor.yaml
    3. Default values
    """

    _instance: Optional["RuntimeConfig"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_paths = [
            Path(__file__).parent.parent.parent / "config" / "bankadvisor.yaml",
            Path("/app/plugins/bank-advisor-private/config/bankadvisor.yaml"),
            Path("config/bankadvisor.yaml"),
        ]

        for path in config_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._config = yaml.safe_load(f) or {}
                    logger.info("runtime_config.loaded", path=str(path))
                    return
                except Exception as e:
                    logger.warning("runtime_config.load_failed", path=str(path), error=str(e))

        logger.warning("runtime_config.no_file_found", using_defaults=True)
        self._config = {}

    def _get(self, *keys: str, default: Any = None) -> Any:
        """Get nested config value."""
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    # =========================================================================
    # Bank Configuration
    # =========================================================================

    @property
    def primary_bank(self) -> str:
        """Get the primary bank (default for queries without bank)."""
        return os.environ.get("PRIMARY_BANK") or self._get("banks", "primary", default="INVEX")

    @property
    def aggregates(self) -> List[str]:
        """Get list of aggregate bank identifiers (SISTEMA, SECTOR, etc.)."""
        return self._get("banks", "aggregates", default=["SISTEMA"])

    @property
    def aggregate_aliases(self) -> Dict[str, str]:
        """Get mapping of phrases to aggregate banks."""
        return self._get("banks", "aggregate_aliases", default={
            "sistema": "SISTEMA",
            "sector": "SISTEMA",
            "sistema bancario": "SISTEMA",
        })

    def is_aggregate(self, bank: str) -> bool:
        """Check if a bank name is an aggregate (not individual bank)."""
        return bank.upper() in [a.upper() for a in self.aggregates]

    def resolve_aggregate_alias(self, text: str) -> Optional[str]:
        """Resolve aggregate alias to bank name."""
        text_lower = text.lower()
        for alias, bank in self.aggregate_aliases.items():
            if alias in text_lower:
                return bank
        return None

    # =========================================================================
    # Intent Configuration
    # =========================================================================

    @property
    def rules_confidence_threshold(self) -> float:
        """Minimum confidence to trust rules without LLM fallback."""
        return float(self._get("intent", "rules_confidence_threshold", default=0.9))

    @property
    def llm_fallback_enabled(self) -> bool:
        """Whether to use LLM fallback for low-confidence classifications."""
        env_val = os.environ.get("LLM_FALLBACK_ENABLED")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
        return self._get("intent", "llm_fallback_enabled", default=True)

    @property
    def llm_timeout_seconds(self) -> int:
        """Timeout for LLM API calls."""
        return int(self._get("intent", "llm_timeout_seconds", default=10))

    # =========================================================================
    # Performance Configuration
    # =========================================================================

    @property
    def bank_cache_ttl(self) -> int:
        """TTL for bank cache in seconds."""
        return int(self._get("performance", "bank_cache_ttl", default=3600))

    @property
    def max_rows(self) -> int:
        """Maximum rows to return in a single query."""
        return int(self._get("performance", "max_rows", default=1000))

    # =========================================================================
    # Defaults Configuration
    # =========================================================================

    @property
    def default_months(self) -> int:
        """Default number of months when no date range specified."""
        return int(self._get("defaults", "default_months", default=12))

    @property
    def apply_bank_default(self) -> bool:
        """Whether to auto-add primary bank when metric+date but no bank."""
        return self._get("defaults", "apply_bank_default", default=True)

    @property
    def apply_evolution_default(self) -> bool:
        """Whether to auto-format as evolution when >3 data points."""
        return self._get("defaults", "apply_evolution_default", default=True)


def get_runtime_config() -> RuntimeConfig:
    """Get the singleton RuntimeConfig instance."""
    return RuntimeConfig()
