"""
Citation Conversion Agent — Detects and converts citations between academic styles.
"""
import logging

from services.citation_converter import (
    convert_citations,
    detect_citation_style,
    reorder_references_numerically,
    CITATION_STYLES,
)

logger = logging.getLogger(__name__)


def citation_agent(state: dict) -> dict:
    """
    Detect and convert citations to the target journal style.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        journal_rules = state.get("journal_rules", {})
        target_style = state.get("citation_style", journal_rules.get("citation_style", "apa"))

        if not structured:
            errors.append("No structured content available for citation conversion")
            return {**state, "errors": errors, "current_step": "citation_failed"}

        references = structured.get("references", [])
        raw_text = structured.get("raw_text", "")

        if not references:
            logger.warning("No references found, skipping citation conversion")
            return {
                **state,
                "current_step": "citation_complete",
                "errors": errors,
            }

        # Detect current style
        current_style = detect_citation_style(references, raw_text)
        logger.info(f"Detected citation style: {current_style}, target: {target_style}")

        # Convert citations
        result = convert_citations(
            references=references,
            text=raw_text,
            target_style=target_style,
            source_style=current_style,
        )

        # Update structured JSON with converted references
        structured["references"] = result["references"]
        structured["raw_text"] = result["text"]

        # Also update section content with converted in-text citations
        for section in structured.get("sections", []):
            section_text = section.get("content", "")
            if section_text:
                section_result = convert_citations(
                    references=references,
                    text=section_text,
                    target_style=target_style,
                    source_style=current_style,
                )
                section["content"] = section_result["text"]

        # Reorder references if numeric style
        target_config = CITATION_STYLES.get(target_style, {})
        if target_config.get("format") == "numbered":
            all_section_text = " ".join([s.get("content", "") for s in structured.get("sections", [])])
            reordered_refs, updated_text = reorder_references_numerically(
                structured["references"],
                all_section_text,
            )
            structured["references"] = reordered_refs

        return {
            **state,
            "structured_json": structured,
            "current_step": "citation_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Citation conversion failed: {str(e)}")
        errors.append(f"Citation conversion error: {str(e)}")
        return {**state, "errors": errors, "current_step": "citation_failed"}
