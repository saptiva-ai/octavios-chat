"""
Configuration service - loads synonyms and settings from YAML.
Production-grade: external config, no hardcoded values.

HU3 - NLP Query Interpretation
"""

import yaml
import os
from functools import lru_cache
from typing import Dict, List, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


class ConfigService:
    """
    Singleton service for loading and managing NLP configuration.
    Loads synonyms.yaml at startup and provides lookup methods.
    """
    _instance = None
    _config: Dict = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._load_config()
            ConfigService._initialized = True

    def _load_config(self):
        """Load synonyms.yaml at startup."""
        # Try multiple paths for different environments
        possible_paths = [
            # Development - relative to this file
            Path(__file__).parent.parent.parent / "config" / "synonyms.yaml",
            # Docker container path
            Path("/app/config/synonyms.yaml"),
            # Alternative container path
            Path("/app/plugins/bank-advisor-private/config/synonyms.yaml"),
        ]

        config_path = None
        for path in possible_paths:
            if path.exists():
                config_path = path
                break

        if config_path is None:
            logger.error(
                "config_service.file_not_found",
                tried_paths=[str(p) for p in possible_paths]
            )
            # Initialize with empty config to avoid crashes
            self._config = {"metrics": {}, "intents": {}}
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)

            logger.info(
                "config_service.loaded",
                path=str(config_path),
                metrics_count=len(self._config.get("metrics", {})),
                intents_count=len(self._config.get("intents", {}))
            )
        except Exception as e:
            logger.error("config_service.load_error", error=str(e))
            self._config = {"metrics": {}, "intents": {}}

    @property
    def metrics(self) -> Dict:
        """Get all metric configurations."""
        return self._config.get("metrics", {})

    def find_metric(self, text: str) -> Optional[str]:
        """
        Find metric ID from text using aliases.
        Returns metric key (e.g., 'imor') or None.

        Args:
            text: User query text

        Returns:
            Metric ID or None if not found
        """
        text_lower = text.lower()

        for metric_id, config in self.metrics.items():
            # Check exact match with metric_id
            if metric_id in text_lower:
                return metric_id

            # Check aliases
            for alias in config.get("aliases", []):
                if alias.lower() in text_lower:
                    return metric_id

        return None

    def get_metric_column(self, metric_id: str) -> Optional[str]:
        """Get database column name for a metric."""
        metric = self.metrics.get(metric_id)
        return metric.get("column") if metric else None

    def get_metric_display_name(self, metric_id: str) -> str:
        """Get human-readable name for a metric."""
        metric = self.metrics.get(metric_id)
        return metric.get("display_name", metric_id.upper()) if metric else metric_id.upper()

    def get_metric_type(self, metric_id: str) -> str:
        """Get metric type (ratio or currency)."""
        metric = self.metrics.get(metric_id)
        return metric.get("type", "currency") if metric else "currency"

    def get_all_metric_options(self) -> List[Dict[str, str]]:
        """Get list of all available metrics for clarification UI."""
        return [
            {"id": metric_id, "label": config.get("display_name", metric_id.upper())}
            for metric_id, config in self.metrics.items()
        ]

    @property
    def ambiguous_terms(self) -> Dict:
        """Get all ambiguous term configurations."""
        return self._config.get("ambiguous_terms", {})

    def check_ambiguous_term(self, text: str) -> Optional[Dict]:
        """
        Check if text contains an ambiguous term that requires clarification.

        Ambiguous terms are generic words that could match multiple specific metrics.
        For example, "cartera" could mean cartera_total, cartera_comercial, etc.

        Args:
            text: User query text

        Returns:
            Dict with ambiguity info if found, None otherwise.
            Structure: {
                "term": str,           # The ambiguous term found
                "message": str,        # Clarification message to show user
                "options": List[Dict]  # List of {id, label, description}
            }
        """
        import re
        text_lower = text.lower()

        for term, config in self.ambiguous_terms.items():
            # Use word boundary matching to avoid partial matches
            # e.g., "cartera" should match but "cartera total" should not
            # because "cartera total" is a specific metric alias
            pattern = r'\b' + re.escape(term) + r'\b'

            if re.search(pattern, text_lower):
                # Check if a more specific term is present
                # e.g., if user says "cartera total", don't trigger ambiguity
                is_specific = False
                for option in config.get("options", []):
                    metric_config = self.metrics.get(option["id"], {})
                    for alias in metric_config.get("aliases", []):
                        if alias.lower() in text_lower:
                            is_specific = True
                            break
                    if is_specific:
                        break

                if not is_specific:
                    logger.info(
                        "config_service.ambiguous_term_detected",
                        term=term,
                        query=text
                    )
                    return {
                        "term": term,
                        "message": config.get("message", f"¿Qué tipo de {term} te interesa?"),
                        "options": config.get("options", [])
                    }

        return None

    def reload(self):
        """Force reload configuration (useful for testing)."""
        ConfigService._initialized = False
        self._load_config()
        ConfigService._initialized = True


# Singleton accessor
def get_config() -> ConfigService:
    """Get the singleton ConfigService instance."""
    return ConfigService()
