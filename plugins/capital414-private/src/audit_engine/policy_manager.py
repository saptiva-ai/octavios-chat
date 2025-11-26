"""
Policy Manager for Copiloto 414.

Manages policy configurations and auto-detection for document validation.

Key responsibilities:
- Load policies from policies.yaml
- Auto-detect appropriate policy based on document content
- Provide policy-specific configuration to validators
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from copy import deepcopy
import yaml
import structlog
from dataclasses import dataclass, field

from ..schemas.models import DocumentInput as Document
from .auditors.compliance_auditor import load_compliance_config

logger = structlog.get_logger(__name__)


# ============================================================================
# Policy Configuration Models
# ============================================================================


@dataclass
class PolicyConfig:
    """
    Policy configuration loaded from YAML.

    Represents a complete validation policy that can be applied to a document.
    """

    id: str
    name: str
    description: str
    auto_detect: bool
    client_name: Optional[str]

    # Auditor configurations
    disclaimers: Dict[str, Any]
    logo: Dict[str, Any]
    format: Dict[str, Any]
    grammar: Dict[str, Any]
    typography: Dict[str, Any] = field(default_factory=dict)

    # For auto-detection policy
    heuristics: Optional[List[Dict[str, Any]]] = None
    fallback: Optional[str] = None
    confidence_threshold: Optional[float] = None

    def to_compliance_config(self) -> Dict[str, Any]:
        """
        Convert policy to compliance config format expected by auditors.

        Returns:
            Dict compatible with compliance_auditor.load_compliance_config()
        """
        base_config = load_compliance_config()
        config = deepcopy(base_config)

        # ------------------------------------------------------------------
        # Disclaimers
        # ------------------------------------------------------------------
        policy_disclaimers = self.disclaimers or {}
        disclaimers_config = config.get("disclaimers", {})

        # Track enable flag
        disclaimers_config["enabled"] = policy_disclaimers.get("enabled", True)

        # Map templates by ID from base config
        base_templates = {
            tpl.get("id"): tpl
            for tpl in base_config.get("disclaimers", {}).get("templates", [])
            if isinstance(tpl, dict) and tpl.get("id")
        }

        template_ids = policy_disclaimers.get("templates")
        if template_ids:
            resolved_templates: List[Dict[str, Any]] = []
            for template_id in template_ids:
                template = base_templates.get(template_id)
                if template:
                    resolved_templates.append(deepcopy(template))
                else:
                    additional_template = PolicyManager().get_additional_template(template_id)
                    if additional_template:
                        resolved_templates.append(deepcopy(additional_template))
                    else:
                        logger.warning(
                            "Policy template not found in compliance config",
                            policy_id=self.id,
                            template_id=template_id,
                        )
            if resolved_templates:
                disclaimers_config["templates"] = resolved_templates

        if "min_coverage" in policy_disclaimers:
            disclaimers_config["min_coverage"] = policy_disclaimers["min_coverage"]
        if "tolerance" in policy_disclaimers:
            disclaimers_config["default_tolerance"] = policy_disclaimers["tolerance"]
        if "severity" in policy_disclaimers:
            disclaimers_config["missing_severity"] = policy_disclaimers["severity"]
        if "client_name" in policy_disclaimers:
            disclaimers_config["policy_client_name"] = policy_disclaimers["client_name"]

        config["disclaimers"] = disclaimers_config

        # ------------------------------------------------------------------
        # Logo
        # ------------------------------------------------------------------
        policy_logo = self.logo or {}
        logo_config = config.get("logo", {})
        logo_config["enabled"] = policy_logo.get("enabled", True)

        if "template" in policy_logo:
            logo_config["template_path"] = policy_logo["template"]

        for key in ("min_similarity", "min_area", "required_pages", "severity"):
            if key in policy_logo:
                logo_config[key] = policy_logo[key]

        config["logo"] = logo_config

        # ------------------------------------------------------------------
        # Format
        # ------------------------------------------------------------------
        policy_format = self.format or {}
        format_config = config.get("format", {})
        format_config["enabled"] = policy_format.get("enabled", True)

        for section in ("numeric_format", "fonts", "font_sizes", "colors", "images"):
            if section in policy_format:
                default_section = format_config.get(section, {})
                section_data = policy_format.get(section, {})
                if isinstance(section_data, dict):
                    merged = deepcopy(default_section)
                    merged.update(section_data)
                    format_config[section] = merged
                else:
                    format_config[section] = section_data

        # Backward compatibility with legacy "numbers" key
        if "numbers" in policy_format and "numeric_format" not in format_config:
            legacy = policy_format["numbers"] or {}
            format_config["numeric_format"] = {
                "enabled": True,
                "style": "EU",
                "thousand_sep": legacy.get("thousands_separator", "."),
                "decimal_sep": legacy.get("decimal_separator", ","),
                "min_decimals": legacy.get("min_decimals", 2),
                "max_decimals": legacy.get("max_decimals", 2),
                "severity": legacy.get("severity", "medium"),
            }

        config["format"] = format_config

        # ------------------------------------------------------------------
        # Typography
        # ------------------------------------------------------------------
        policy_typography = getattr(self, "typography", None) or {}
        typography_config = config.get("typography", {})
        if policy_typography:
            merged = deepcopy(typography_config)
            merged.update(policy_typography)
            typography_config = merged

        if policy_typography or "enabled" not in typography_config:
            typography_config["enabled"] = policy_typography.get(
                "enabled",
                typography_config.get("enabled", True),
            )

        config["typography"] = typography_config

        # ------------------------------------------------------------------
        # Grammar
        # ------------------------------------------------------------------
        policy_grammar = getattr(self, "grammar", None) or {}
        grammar_config = config.get("grammar", {})
        grammar_config["enabled"] = policy_grammar.get(
            "enabled", grammar_config.get("enabled", True)
        )

        for key, value in policy_grammar.items():
            if key == "enabled":
                continue
            grammar_config[key] = value

        config["grammar"] = grammar_config

        # ------------------------------------------------------------------
        # Color Palette (Phase 3)
        # ------------------------------------------------------------------
        policy_color_palette = getattr(self, "color_palette", None) or {}
        color_palette_config = config.get("color_palette", {})
        if policy_color_palette:
            merged = deepcopy(color_palette_config)
            merged.update(policy_color_palette)
            color_palette_config = merged

        if policy_color_palette or "enabled" not in color_palette_config:
            color_palette_config["enabled"] = policy_color_palette.get(
                "enabled",
                color_palette_config.get("enabled", True),
            )

        config["color_palette"] = color_palette_config

        # ------------------------------------------------------------------
        # Entity Consistency (Phase 4)
        # ------------------------------------------------------------------
        policy_entity_consistency = getattr(self, "entity_consistency", None) or {}
        entity_consistency_config = config.get("entity_consistency", {})
        if policy_entity_consistency:
            merged = deepcopy(entity_consistency_config)
            merged.update(policy_entity_consistency)
            entity_consistency_config = merged

        if policy_entity_consistency or "enabled" not in entity_consistency_config:
            entity_consistency_config["enabled"] = policy_entity_consistency.get(
                "enabled",
                entity_consistency_config.get("enabled", True),
            )

        config["entity_consistency"] = entity_consistency_config

        # ------------------------------------------------------------------
        # Semantic Consistency (Phase 5 - FINAL)
        # ------------------------------------------------------------------
        policy_semantic_consistency = getattr(self, "semantic_consistency", None) or {}
        semantic_consistency_config = config.get("semantic_consistency", {})
        if policy_semantic_consistency:
            merged = deepcopy(semantic_consistency_config)
            merged.update(policy_semantic_consistency)
            semantic_consistency_config = merged

        if policy_semantic_consistency or "enabled" not in semantic_consistency_config:
            semantic_consistency_config["enabled"] = policy_semantic_consistency.get(
                "enabled",
                semantic_consistency_config.get("enabled", True),
            )

        config["semantic_consistency"] = semantic_consistency_config

        return config


# ============================================================================
# Policy Loader
# ============================================================================


class PolicyManager:
    """
    Singleton manager for policy configurations.

    Loads policies from YAML and provides policy resolution.
    """

    _instance: Optional[PolicyManager] = None
    _policies: Dict[str, PolicyConfig] = {}
    _config_path: Path

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Determine config path
        config_dir = Path(__file__).parent.parent / "config"
        self._config_path = config_dir / "policies.yaml"
        self._additional_templates: Dict[str, Dict[str, Any]] = {}

        # Load policies
        self._load_policies()
        self._initialized = True

        logger.info(
            "PolicyManager initialized",
            policies_loaded=len(self._policies),
            config_path=str(self._config_path)
        )

    def _load_policies(self) -> None:
        """Load all policies from policies.yaml."""
        if not self._config_path.exists():
            logger.warning(
                "Policies config not found, using defaults",
                path=str(self._config_path)
            )
            self._policies = self._get_default_policies()
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            policies_data = config.get("policies", [])
            additional_templates = config.get("additional_disclaimer_templates", []) or []

            self._additional_templates = {
                tpl.get("id"): tpl
                for tpl in additional_templates
                if isinstance(tpl, dict) and tpl.get("id")
            }

            for policy_data in policies_data:
                policy = PolicyConfig(
                    id=policy_data.get("id"),
                    name=policy_data.get("name"),
                    description=policy_data.get("description"),
                    auto_detect=policy_data.get("auto_detect", False),
                    client_name=policy_data.get("client_name"),
                    disclaimers=policy_data.get("disclaimers", {}),
                    logo=policy_data.get("logo", {}),
                    format=policy_data.get("format", {}),
                    grammar=policy_data.get("grammar", {}),
                    typography=policy_data.get("typography", {}),
                    heuristics=policy_data.get("heuristics"),
                    fallback=policy_data.get("fallback"),
                    confidence_threshold=policy_data.get("confidence_threshold", 0.5)
                )

                self._policies[policy.id] = policy

                logger.debug(
                    "Policy loaded",
                    policy_id=policy.id,
                    policy_name=policy.name,
                    auto_detect=policy.auto_detect
                )

        except Exception as exc:
            logger.error(
                "Failed to load policies from YAML",
                error=str(exc),
                path=str(self._config_path),
                exc_info=True
            )
            # Fall back to defaults
            self._policies = self._get_default_policies()
            self._additional_templates = {}

    def _get_default_policies(self) -> Dict[str, PolicyConfig]:
        """
        Get default policies if YAML is missing.

        Returns basic 414-std policy.
        """
        self._additional_templates = {}
        return {
            "414-std": PolicyConfig(
                id="414-std",
                name="414 Capital Standard",
                description="Default policy",
                auto_detect=False,
                client_name=None,
                disclaimers={
                    "enabled": True,
                    "templates": ["414-std-es-v1", "414-std-es-v2"],
                    "min_coverage": 1.0,
                    "tolerance": 0.85,
                    "severity": "high"
                },
                logo={
                    "enabled": True,
                    "min_similarity": 0.75,
                    "required_pages": ["first", "last"],
                    "severity": "high"
                },
                format={
                    "enabled": True,
                    "numeric_format": {
                        "enabled": True,
                        "style": "MX",
                        "thousand_sep": ",",
                        "decimal_sep": ".",
                        "min_decimals": 2,
                        "max_decimals": 2,
                        "severity": "high",
                    },
                    "fonts": {"severity": "medium"},
                    "colors": {"severity": "low"},
                    "images": {"severity": "low", "max_ratio": 0.65, "min_ratio": 0.02},
                },
                grammar={
                    "enabled": True,
                    "language": "es",
                    "severity": {"spelling": "low", "grammar": "medium"},
                    "max_issues_per_page": 25,
                },
                typography={
                    "enabled": True,
                    "heading_font_threshold": 18,
                    "max_heading_levels": 5,
                    "min_line_spacing": 0.5,
                    "max_line_spacing": 2.5,
                    "severity_heading": "low",
                    "severity_spacing": "low",
                },
            )
        }

    def get_policy(self, policy_id: str) -> Optional[PolicyConfig]:
        """
        Get policy by ID.

        Args:
            policy_id: Policy identifier

        Returns:
            PolicyConfig or None if not found
        """
        return self._policies.get(policy_id)

    def get_additional_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Return additional disclaimer template defined in policies.yaml."""
        template = self._additional_templates.get(template_id)
        return deepcopy(template) if template else None

    def list_policies(self) -> List[PolicyConfig]:
        """Get all available policies."""
        return list(self._policies.values())

    async def detect_policy(self, document: Document) -> Tuple[str, float]:
        """
        Auto-detect appropriate policy for document.

        Uses heuristics from "auto" policy configuration:
        1. Logo detection (weight: 40%)
        2. Keyword matching (weight: 35%)
        3. Disclaimer template matching (weight: 25%)

        Args:
            document: Document to analyze

        Returns:
            Tuple[policy_id, confidence_score]

        Example:
            policy_id, confidence = await manager.detect_policy(doc)
            if confidence >= 0.5:
                print(f"Detected policy: {policy_id}")
            else:
                print("Low confidence, using fallback")
        """
        # Get auto-detection policy config
        auto_policy = self._policies.get("auto")
        if not auto_policy or not auto_policy.heuristics:
            logger.warning("Auto-detection policy not configured, using fallback")
            return auto_policy.fallback if auto_policy else "414-std", 0.0

        score_map: Dict[str, float] = {}

        # Process each heuristic
        for heuristic in auto_policy.heuristics:
            heuristic_type = heuristic.get("type")
            weight = heuristic.get("weight", 0.0)
            config = heuristic.get("config", {})

            if heuristic_type == "logo_detection":
                # Heuristic 1: Logo detection
                policy_id = await self._detect_by_logo(document, config)
                if policy_id:
                    score_map[policy_id] = score_map.get(policy_id, 0.0) + weight

            elif heuristic_type == "keyword_match":
                # Heuristic 2: Keyword matching
                policy_id = await self._detect_by_keywords(document, config)
                if policy_id:
                    score_map[policy_id] = score_map.get(policy_id, 0.0) + weight

            elif heuristic_type == "disclaimer_match":
                # Heuristic 3: Disclaimer template matching
                policy_id = await self._detect_by_disclaimer(document, config)
                if policy_id:
                    score_map[policy_id] = score_map.get(policy_id, 0.0) + weight

        # Select policy with highest score
        if score_map:
            best_policy = max(score_map, key=score_map.get)
            best_score = score_map[best_policy]

            logger.info(
                "Policy auto-detection completed",
                document_id=str(document.id),
                detected_policy=best_policy,
                confidence=best_score,
                all_scores=score_map
            )

            # Check if confidence is above threshold
            if best_score >= auto_policy.confidence_threshold:
                return best_policy, best_score

        # Fall back to default
        fallback = auto_policy.fallback or "414-std"
        logger.info(
            "Policy auto-detection: using fallback",
            document_id=str(document.id),
            fallback_policy=fallback,
            reason="low_confidence" if score_map else "no_matches"
        )

        return fallback, 0.0

    async def _detect_by_logo(self, document: Document, config: Dict[str, Any]) -> Optional[str]:
        """
        Detect policy by logo presence.

        Args:
            document: Document to analyze
            config: Logo heuristic config

        Returns:
            Policy ID if logo detected, None otherwise
        """
        # TODO: Implement quick logo check without full validation
        # For now, check if document has 414 Capital keywords in title/filename
        if "414" in document.filename.lower() or "capital" in document.filename.lower():
            target_policy = config.get("target_policy", "414-std")
            logger.debug("Logo heuristic: filename suggests 414 Capital", policy=target_policy)
            return target_policy

        return None

    async def _detect_by_keywords(self, document: Document, config: Dict[str, Any]) -> Optional[str]:
        """
        Detect policy by keyword matching in document text.

        Args:
            document: Document to analyze
            config: Keyword heuristic config

        Returns:
            Policy ID if keywords matched, None otherwise
        """
        # Get text sample from first, second, and last pages
        pages_to_check = config.get("pages_to_check", [0, 1, -1])
        text_sample = ""

        if document.pages:
            for page_idx in pages_to_check:
                if -len(document.pages) <= page_idx < len(document.pages):
                    page = document.pages[page_idx]
                    text_sample += page.text_md[:500] + "\n"

        # Check patterns
        patterns = config.get("patterns", [])
        for pattern in patterns:
            keywords = pattern.get("keywords", [])
            target_policy = pattern.get("target_policy")

            for keyword in keywords:
                if keyword in text_sample:
                    logger.debug(
                        "Keyword heuristic: match found",
                        keyword=keyword,
                        policy=target_policy
                    )
                    return target_policy

        return None

    async def _detect_by_disclaimer(self, document: Document, config: Dict[str, Any]) -> Optional[str]:
        """
        Detect policy by disclaimer template matching.

        Args:
            document: Document to analyze
            config: Disclaimer heuristic config

        Returns:
            Policy ID if disclaimer matched, None otherwise
        """
        # TODO: Implement disclaimer template matching
        # This requires fuzzy matching against templates - defer to full validation
        # For V1, we'll rely on logo and keyword heuristics
        pages_to_check = config.get("pages_to_check", [0, 1, -1])
        text_sample = ""

        if document.pages:
            for page_idx in pages_to_check:
                if -len(document.pages) <= page_idx < len(document.pages):
                    page = document.pages[page_idx]
                    text_sample += page.text_md[:500] + "\n"
        
        if "disclaimer" in text_sample.lower():
            target_policy = config.get("target_policy", "414-std")
            logger.debug("Disclaimer heuristic: found disclaimer keyword", policy=target_policy)
            return target_policy

        return None


# ============================================================================
# Global Instance
# ============================================================================

_policy_manager: Optional[PolicyManager] = None


def get_policy_manager() -> PolicyManager:
    """
    Get global PolicyManager instance (singleton).

    Returns:
        PolicyManager instance
    """
    global _policy_manager
    if _policy_manager is None:
        _policy_manager = PolicyManager()
    return _policy_manager


async def resolve_policy(
    policy_id: str,
    document: Optional[Document] = None
) -> PolicyConfig:
    """
    Resolve policy configuration.

    If policy_id is "auto", performs auto-detection on document.
    Otherwise, loads policy by ID.

    Args:
        policy_id: Policy identifier or "auto"
        document: Document for auto-detection (required if policy_id="auto")

    Returns:
        PolicyConfig

    Raises:
        ValueError: If policy not found or auto-detection requires document

    Example:
        policy = await resolve_policy("414-std")
        policy = await resolve_policy("auto", document=doc)
    """
    manager = get_policy_manager()

    if policy_id == "auto":
        if not document:
            raise ValueError("Auto-detection requires document parameter")

        detected_id, confidence = await manager.detect_policy(document)

        logger.info(
            "Policy resolved via auto-detection",
            detected_policy=detected_id,
            confidence=confidence,
            document_id=str(document.id)
        )

        policy_id = detected_id

    # Load policy
    policy = manager.get_policy(policy_id)

    if not policy:
        logger.error("Policy not found", policy_id=policy_id)
        raise ValueError(f"Policy not found: {policy_id}")

    return policy
