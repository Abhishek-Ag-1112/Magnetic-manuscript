"""
Formatting & Layout Agent — Uses LLM to polish content for the target journal,
then applies deterministic formatting to generate publish-ready DOCX.
"""
import os
import json
import logging
import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from services.document_formatter import format_document
from utils.helpers import generate_session_id

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")


CONTENT_POLISH_PROMPT = """You are an expert academic manuscript formatter preparing a paper for submission to "{journal_name}".

Journal requirements:
- Font: {font}, {font_size}pt
- Line spacing: {line_spacing}
- Section order: {section_order}
- Heading style: {heading_style}
- Keywords required: {keywords_required}
{extra_notes}

Here is the current manuscript data:
Title: {title}
Authors: {authors}
Abstract: {abstract}
Keywords: {keywords}
Sections: {section_names}

YOUR TASKS:
1. Ensure section headings match the journal's naming convention exactly: {section_order}
2. If any required section is missing, check if its content exists under a different heading and rename it.
3. If new keywords are required, generate them.
4. DO NOT change the text of the abstract or any section content.

Return ONLY valid JSON:
{{
  "title": "original title",
  "abstract": "original abstract EXACTLY as provided",
  "keywords": ["keyword1", "keyword2", ...],
  "section_renames": {{
    "Old Heading": "New Journal-Standard Heading"
  }}
}}"""


def formatting_agent(state: dict) -> dict:
    """
    Apply journal-specific formatting:
    1. Use LLM to check section headings for the target journal
    2. Apply deterministic DOCX formatting
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        journal_rules = state.get("journal_rules", {})

        if not structured:
            errors.append("No structured content available for formatting")
            return {**state, "errors": errors, "current_step": "formatting_failed"}

        if not journal_rules:
            errors.append("No journal rules loaded for formatting")
            return {**state, "errors": errors, "current_step": "formatting_failed"}

        # Step 1: LLM section heading pass
        structured = _polish_for_journal(structured, journal_rules)

        # Step 2: Extract session ID
        session_id = state.get("session_id", "")
        if not session_id:
            raw_path = state.get("raw_input_path", "")
            parts = raw_path.replace("\\", "/").split("/")
            for i, part in enumerate(parts):
                if part == "uploads" and i + 1 < len(parts):
                    session_id = parts[i + 1]
                    break
            if not session_id:
                session_id = generate_session_id()

        # Step 3: Generate formatted document
        logger.info(f"Generating formatted document for session {session_id}")
        result = format_document(structured, journal_rules, session_id)

        docx_path = result.get("docx_path", "")
        pdf_path = result.get("pdf_path")
        latex_path = result.get("latex_path")

        if not docx_path:
            errors.append("Document generation failed — no output file created")
            return {**state, "errors": errors, "current_step": "formatting_failed"}

        logger.info(f"Generated DOCX: {docx_path}")
        if latex_path:
            logger.info(f"Generated LaTeX: {latex_path}")

        return {
            **state,
            "structured_json": structured,
            "formatted_doc_path": docx_path,
            "formatted_pdf_path": pdf_path or "",
            "formatted_latex_path": latex_path or "",
            "formatted_structure": structured,
            "current_step": "formatting_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Formatting failed: {str(e)}")
        errors.append(f"Formatting error: {str(e)}")
        return {**state, "errors": errors, "current_step": "formatting_failed"}


def _polish_for_journal(structured: dict, rules: dict) -> dict:
    """Use LLM to rename sections for the specific journal. Content remains untouched."""
    try:
        journal_name = rules.get("journal_name", rules.get("family_name", "the journal"))
        abstract = structured.get("abstract", "")
        keywords = structured.get("keywords", [])
        keywords_required = rules.get("keywords_required", False)
        section_order = rules.get("section_order", [])
        sections = structured.get("sections", [])
        section_names = [s.get("heading", "") for s in sections]

        # Check if polishing is needed
        needs_polish = (
            (keywords_required and not keywords) or
            not _sections_match_order(section_names, section_order)
        )

        if not needs_polish:
            logger.info("Content headings match journal requirements — skipping LLM polish")
            return structured

        logger.info(f"Polishing headings for {journal_name}")

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=2048)

        prompt = CONTENT_POLISH_PROMPT.format(
            journal_name=journal_name,
            font=rules.get("font", "Times New Roman"),
            font_size=rules.get("font_size", 12),
            line_spacing=rules.get("line_spacing", 1.5),
            section_order=json.dumps(section_order),
            heading_style=rules.get("heading_style", "bold_title_case"),
            keywords_required=keywords_required,
            extra_notes=rules.get("notes", ""),
            title=structured.get("title", ""),
            authors=", ".join(structured.get("authors", [])),
            abstract=abstract,
            keywords=", ".join(keywords) if keywords else "(none)",
            section_names=json.dumps(section_names),
        )

        response = llm.invoke([
            SystemMessage(content="You align manuscript structure to journals. Return ONLY valid JSON."),
            HumanMessage(content=prompt),
        ])

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1]

        result = json.loads(content.strip())

        # Abstract modification is REMOVED to preserve word-for-word accuracy verbatim.


        # Apply keywords if generated
        new_keywords = result.get("keywords", [])
        if new_keywords and (not keywords or keywords_required):
            structured["keywords"] = new_keywords
            logger.info(f"Generated {len(new_keywords)} keywords")

        # Apply section renames
        renames = result.get("section_renames", {})
        if renames:
            for sec in structured.get("sections", []):
                old_heading = sec.get("heading", "")
                if old_heading in renames:
                    sec["heading"] = renames[old_heading]
                    logger.info(f"Renamed section: '{old_heading}' → '{renames[old_heading]}'")

    except Exception as e:
        logger.warning(f"LLM polishing failed (continuing with original): {e}")

    return structured


def _sections_match_order(current: list, required: list) -> bool:
    """Check if current sections roughly match the required order."""
    required_body = [s.lower() for s in required if s.lower() not in ("abstract", "references", "keywords")]
    current_lower = [s.lower() for s in current]

    matched = 0
    for req in required_body:
        for cur in current_lower:
            if req in cur or cur in req:
                matched += 1
                break

    return matched >= len(required_body) * 0.7
