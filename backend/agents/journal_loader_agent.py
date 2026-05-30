"""
Journal Rule Loader Agent — Loads and merges journal-specific rules.
Handles family defaults + journal overrides → final_rules.
"""
import logging

from utils.helpers import load_journal_config, load_family_config

logger = logging.getLogger(__name__)


def journal_loader_agent(state: dict) -> dict:
    """
    Load journal formatting rules.
    Merges family defaults with journal-specific overrides.
    """
    errors = state.get("errors", [])

    try:
        journal_name = state.get("selected_journal", "")
        family_name = state.get("selected_family", "")

        if not journal_name and not family_name:
            errors.append("No journal or format family selected")
            return {**state, "errors": errors, "current_step": "rule_loading_failed"}

        rules = {}

        if journal_name:
            # Load journal config (includes family merge)
            try:
                rules = load_journal_config(journal_name)
                logger.info(f"Loaded journal rules: {rules.get('journal_name', journal_name)}")
            except FileNotFoundError:
                errors.append(f"Journal config not found: {journal_name}")
                if family_name:
                    rules = load_family_config(family_name)
                else:
                    return {**state, "errors": errors, "current_step": "rule_loading_failed"}
        elif family_name:
            # Load family config only
            try:
                rules = load_family_config(family_name)
                logger.info(f"Loaded family rules: {rules.get('family_name', family_name)}")
            except FileNotFoundError:
                errors.append(f"Family config not found: {family_name}")
                return {**state, "errors": errors, "current_step": "rule_loading_failed"}

        # Validate essential rules
        essential_keys = ["font", "font_size", "line_spacing", "citation_style"]
        for key in essential_keys:
            if key not in rules:
                # Set defaults
                defaults = {
                    "font": "Times New Roman",
                    "font_size": 12,
                    "line_spacing": 1.5,
                    "citation_style": "apa",
                }
                rules[key] = defaults.get(key)
                logger.warning(f"Missing rule '{key}', using default: {rules[key]}")

        return {
            **state,
            "journal_rules": rules,
            "citation_style": rules.get("citation_style", "apa"),
            "current_step": "rules_loaded",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Rule loading failed: {str(e)}")
        errors.append(f"Rule loading error: {str(e)}")
        return {**state, "errors": errors, "current_step": "rule_loading_failed"}
