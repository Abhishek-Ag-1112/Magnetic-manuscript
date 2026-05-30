"""
Reference Validation Agent — Validates references against CrossRef API.
Verifies DOIs, discovers missing DOIs, and auto-fills metadata.
"""
import logging

from services.reference_validator import validate_references

logger = logging.getLogger(__name__)


def reference_validation_agent(state: dict) -> dict:
    """
    Validate all references against CrossRef.
    Discovers missing DOIs and verifies existing ones.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        references = structured.get("references", [])

        if not references:
            logger.warning("No references to validate")
            return {
                **state,
                "reference_validation": {
                    "total": 0,
                    "validated": 0,
                    "doi_found": 0,
                    "doi_missing": 0,
                    "errors": 0,
                    "details": [],
                },
                "current_step": "reference_validation_complete",
                "errors": errors,
            }

        logger.info(f"Validating {len(references)} references against CrossRef...")

        # Run CrossRef validation
        validation_result = validate_references(references)

        # Auto-fill discovered DOIs back into references
        enriched_references = list(references)
        for detail in validation_result.get("details", []):
            idx = detail.get("index", 0) - 1
            if 0 <= idx < len(enriched_references):
                ref_text = enriched_references[idx]
                doi = detail.get("doi", "")

                # If DOI was discovered (not already in the reference), append it
                if detail.get("status") == "doi_discovered" and doi:
                    if doi not in ref_text:
                        enriched_references[idx] = f"{ref_text} https://doi.org/{doi}"
                        logger.info(f"  [Ref {idx+1}] DOI discovered: {doi}")

                elif detail.get("status") == "valid_doi":
                    logger.info(f"  [Ref {idx+1}] DOI verified ✓: {doi}")

                elif detail.get("status") == "invalid_doi":
                    logger.warning(f"  [Ref {idx+1}] Invalid DOI: {doi}")

                elif detail.get("status") == "no_doi":
                    logger.info(f"  [Ref {idx+1}] No DOI found")

        # Update structured JSON with enriched references
        structured["references"] = enriched_references

        logger.info(
            f"Reference validation complete: "
            f"{validation_result['validated']}/{validation_result['total']} verified, "
            f"{validation_result['doi_found']} DOIs found"
        )

        return {
            **state,
            "structured_json": structured,
            "reference_validation": validation_result,
            "current_step": "reference_validation_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Reference validation failed: {str(e)}")
        errors.append(f"Reference validation error: {str(e)}")
        # Non-fatal: continue pipeline even if CrossRef is unreachable
        return {
            **state,
            "reference_validation": {"total": 0, "validated": 0, "error": str(e)},
            "current_step": "reference_validation_complete",
            "errors": errors,
        }
