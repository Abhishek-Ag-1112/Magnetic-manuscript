"""
Validation & Compliance Agent — Checks manuscript against journal rules.
Generates compliance score and detailed violation report.
Implements SMART RETRY: routes failures to the specific agent that can fix each violation.
"""
import logging

from services.compliance_checker import check_compliance

logger = logging.getLogger(__name__)

# Map violation types to the agent that can fix them
VIOLATION_REMEDIATION_MAP = {
    "abstract_word_limit": "rewrite",
    "missing_abstract": "rewrite",
    "missing_sections": "normalize",
    "section_order": "normalize",
    "sections_not_separate": "normalize",
    "missing_references": "convert_citations",
    "citation_reference_mismatch": "convert_citations",
    "too_many_references": "rewrite",
    "missing_title": "rewrite",
    "empty_sections": "rewrite",
    "missing_keywords": "rewrite",
    "missing_authors": "rewrite",
    "page_limit_exceeded": "rewrite",
}


def validation_agent(state: dict) -> dict:
    """
    Validate the formatted manuscript against journal rules.
    Generates compliance report with score, violations, and warnings.
    Implements smart retry: identifies the best agent to fix each violation.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("formatted_structure", state.get("structured_json", {}))
        journal_rules = state.get("journal_rules", {})

        if not structured:
            errors.append("No manuscript content available for validation")
            return {**state, "errors": errors, "current_step": "validation_failed"}

        if not journal_rules:
            errors.append("No journal rules available for validation")
            return {**state, "errors": errors, "current_step": "validation_failed"}

        # Run compliance checks
        report = check_compliance(structured, journal_rules)

        logger.info(f"Compliance score: {report['score']}/100")
        logger.info(f"Violations: {len(report['violations'])}, Warnings: {len(report['warnings'])}")

        # Determine if we should retry formatting
        retry_count = state.get("retry_count", 0)
        score = report["score"]

        if score < 50 and retry_count < 2:
            # Smart retry: analyze violations and determine which agent to route to
            remediation_target, remediation_instructions = _analyze_violations(report)

            logger.warning(
                f"Low compliance score ({score}), routing to '{remediation_target}' "
                f"for remediation (attempt {retry_count + 1})"
            )
            logger.info(f"Remediation instructions: {remediation_instructions}")

            return {
                **state,
                "compliance_report": report,
                "retry_count": retry_count + 1,
                "current_step": f"needs_reprocess_{remediation_target}",
                "remediation_instructions": remediation_instructions,
                "errors": errors,
            }

        return {
            **state,
            "compliance_report": report,
            "current_step": "validation_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        errors.append(f"Validation error: {str(e)}")
        return {**state, "errors": errors, "current_step": "validation_failed"}


def _analyze_violations(report: dict) -> tuple:
    """
    Analyze violations and determine which agent should fix them.
    Returns (target_agent, remediation_instructions).
    """
    violations = report.get("violations", [])
    warnings = report.get("warnings", [])

    # Count how many violations each agent can fix
    agent_scores = {}
    instructions = []

    for violation in violations:
        vtype = violation.get("type", "")
        target_agent = VIOLATION_REMEDIATION_MAP.get(vtype, "format")
        agent_scores[target_agent] = agent_scores.get(target_agent, 0) + 2  # violations weight more

        # Build specific remediation instructions
        instructions.append({
            "type": vtype,
            "message": violation.get("message", ""),
            "severity": "error",
            "fix_agent": target_agent,
        })

    for warning in warnings:
        wtype = warning.get("type", "")
        target_agent = VIOLATION_REMEDIATION_MAP.get(wtype, "format")
        agent_scores[target_agent] = agent_scores.get(target_agent, 0) + 1

        instructions.append({
            "type": wtype,
            "message": warning.get("message", ""),
            "severity": "warning",
            "fix_agent": target_agent,
        })

    # Route to the agent that can fix the most violations
    if agent_scores:
        best_agent = max(agent_scores, key=agent_scores.get)
    else:
        best_agent = "format"  # Default fallback

    return best_agent, instructions
