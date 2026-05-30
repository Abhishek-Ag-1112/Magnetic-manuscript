"""
Parsing Agent — Detects file type, extracts text, identifies sections.
Uses LLM as PRIMARY structure detector when document lacks heading styles.
Splits large documents into manageable chunks for accurate extraction.
"""
import os
import json
import re
import logging
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from services.file_parser import parse_file
from utils.helpers import clean_text

GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")

logger = logging.getLogger(__name__)


# ─── PROMPTS ───

METADATA_PROMPT = """You are an expert at reading academic papers. Given the beginning of a research paper, extract:

1. The FULL paper title (usually the very first prominent text)
2. All authors (in order)
3. The complete abstract (labeled "Abstract" or the summary at the start)
4. Keywords if listed

TEXT (beginning of the paper):
\"\"\"
{text}
\"\"\"

Return ONLY valid JSON, nothing else:
{{
  "title": "the complete paper title",
  "authors": ["Author 1", "Author 2"],
  "abstract": "the complete abstract text",
  "keywords": ["keyword1", "keyword2"]
}}"""


SECTIONS_PROMPT = """You are an expert academic manuscript analyzer. Below is the BODY text of a research paper (excluding the title/abstract/references).

Your task: Identify EACH distinct section of this paper and return them as structured JSON.

RULES:
- Split ONLY at actual section boundaries (Introduction, Methods, Results, Discussion, etc.)
- Do NOT split paragraphs that belong to the same section
- Sub-headings within a section should be included in that section's content
- PRESERVE every single word — do not summarize, delete, or modify any text
- If you're unsure about a boundary, include the text in the preceding section

TEXT:
\"\"\"
{text}
\"\"\"

Return ONLY a valid JSON array:
[
  {{"heading": "Section Name", "content": "full section text..."}},
  ...
]"""


REFERENCES_PROMPT = """Extract ALL individual references/citations from the end of this academic paper.

TEXT (end of the paper):
\"\"\"
{text}
\"\"\"

Return ONLY a valid JSON array of reference strings:
["Reference 1 full text...", "Reference 2 full text...", ...]

If no references are found, return an empty array: []"""


def parsing_agent(state: dict) -> dict:
    """
    Parse the uploaded manuscript file.
    For complex documents without heading styles, use LLM for structure detection.
    """
    errors = state.get("errors", [])

    try:
        file_path = state.get("raw_input_path", "")
        if not file_path:
            errors.append("No input file path provided")
            return {**state, "errors": errors, "current_step": "parsing_failed"}

        # Parse the file
        structured = parse_file(file_path)
        raw_text = structured.get("raw_text", "")
        needs_llm = structured.get("needs_llm_structuring", False)

        # Check if parsing got meaningful structure
        has_sections = len(structured.get("sections", [])) >= 3
        has_title = bool(structured.get("title"))

        if needs_llm or not has_sections or not has_title:
            # Use LLM with chunked extraction for reliability
            logger.info("Using LLM for document structure analysis")
            llm_structured = _llm_chunked_extraction(raw_text)
            if llm_structured:
                llm_structured["raw_text"] = raw_text
                structured = llm_structured

        # Ensure raw_text
        if not structured.get("raw_text"):
            structured["raw_text"] = raw_text

        # Detect figures and tables from raw text
        if not structured.get("figures"):
            structured["figures"] = _detect_figures(raw_text)
        if not structured.get("tables"):
            structured["tables"] = _detect_tables(raw_text)

        logger.info(f"Parsed: title='{structured.get('title', '')[:60]}', "
                     f"sections={len(structured.get('sections', []))}, "
                     f"refs={len(structured.get('references', []))}")

        return {
            **state,
            "parsed_text": raw_text,
            "structured_json": structured,
            "current_step": "parsing_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Parsing failed: {str(e)}")
        errors.append(f"Parsing error: {str(e)}")
        return {**state, "errors": errors, "current_step": "parsing_failed"}


def _llm_chunked_extraction(text: str) -> dict:
    """
    Use LLM with a chunked strategy + regex fallbacks:
    1. Send beginning of text → extract title, authors, abstract
    2. Send end of text → extract references
    3. Send body text → extract sections
    Each step has retry logic and regex fallbacks.
    """
    result = {
        "title": "",
        "authors": [],
        "abstract": "",
        "keywords": [],
        "sections": [],
        "figures": [],
        "tables": [],
        "references": [],
    }

    llm = ChatGroq(
        model=GROQ_MODEL,
        temperature=0.0,
        max_tokens=8192,
    )

    # ── STEP 1: Extract metadata from beginning (with retry) ──
    for attempt in range(2):
        try:
            beginning = text[:8000]
            logger.info(f"LLM: Extracting title, authors, abstract (attempt {attempt+1})...")

            response = llm.invoke([
                SystemMessage(content="You extract metadata from academic papers. Return ONLY valid JSON."),
                HumanMessage(content=METADATA_PROMPT.format(text=beginning)),
            ])
            metadata = _parse_json_response(response.content)
            if metadata:
                result["title"] = metadata.get("title", "")
                result["authors"] = metadata.get("authors", [])
                result["abstract"] = metadata.get("abstract", "")
                result["keywords"] = metadata.get("keywords", [])
                logger.info(f"  ✓ Title: {result['title'][:80]}")
                logger.info(f"  ✓ Authors: {len(result['authors'])}")
                logger.info(f"  ✓ Abstract: {len(result['abstract'])} chars")

                if result["abstract"] and result["title"]:
                    break  # Got what we need
        except Exception as e:
            logger.warning(f"Metadata extraction attempt {attempt+1} failed: {e}")

    # Regex fallback for abstract
    if not result["abstract"]:
        abs_match = re.search(
            r"(?:Abstract|ABSTRACT)[:\s]*\n([\s\S]{50,2000}?)(?:\n\s*(?:Keywords|Introduction|KEYWORDS|INTRODUCTION|1[\.\s]))",
            text, re.IGNORECASE
        )
        if abs_match:
            result["abstract"] = abs_match.group(1).strip()
            logger.info(f"  ✓ Abstract (regex fallback): {len(result['abstract'])} chars")

    # ── STEP 2: Extract references from end (with retry) ──
    for attempt in range(2):
        try:
            ending = text[-12000:]
            logger.info(f"LLM: Extracting references (attempt {attempt+1})...")

            response = llm.invoke([
                SystemMessage(content="You extract references from academic papers. Return ONLY a valid JSON array of strings."),
                HumanMessage(content=REFERENCES_PROMPT.format(text=ending)),
            ])
            refs = _parse_json_response(response.content)
            if isinstance(refs, list):
                result["references"] = [r for r in refs if isinstance(r, str) and len(r) > 10]
                logger.info(f"  ✓ References: {len(result['references'])}")
                if len(result["references"]) > 0:
                    break
        except Exception as e:
            logger.warning(f"Reference extraction attempt {attempt+1} failed: {e}")

    # Regex fallback for references
    if not result["references"]:
        ref_match = re.search(r"(?:References|REFERENCES|Bibliography)\s*\n([\s\S]+?)$", text, re.IGNORECASE)
        if ref_match:
            ref_block = ref_match.group(1).strip()
            # Split by numbered patterns [1], 1., (1)
            refs = re.split(r"\n\s*(?:\[\d+\]|\d+\.\s|\(\d+\))", ref_block)
            refs = [r.strip() for r in refs if r.strip() and len(r.strip()) > 15]
            if refs:
                result["references"] = refs
                logger.info(f"  ✓ References (regex fallback): {len(refs)}")

    # ── STEP 3: Extract body sections ──
    try:
        # Remove the abstract region and references region from body
        body_start = 0
        if result["abstract"]:
            abs_pos = text.find(result["abstract"][:80])
            if abs_pos > 0:
                body_start = abs_pos + len(result["abstract"])

        # Find where references start
        ref_patterns = [
            r"\nReferences\s*\n", r"\nBibliography\s*\n",
            r"\nREFERENCES\s*\n", r"\nLiterature Cited\s*\n",
        ]
        body_end = len(text)
        for pattern in ref_patterns:
            match = re.search(pattern, text)
            if match:
                body_end = match.start()
                break

        body = text[body_start:body_end].strip()

        # Send body to LLM (limit to 30K chars for reliability)
        body_chunk = body[:30000] if len(body) > 30000 else body
        logger.info(f"LLM: Extracting sections from body ({len(body_chunk)} chars)...")

        response = llm.invoke([
            SystemMessage(content="You analyze academic paper structure. Return ONLY a valid JSON array."),
            HumanMessage(content=SECTIONS_PROMPT.format(text=body_chunk)),
        ])
        sections = _parse_json_response(response.content)
        if isinstance(sections, list):
            cleaned = []
            for sec in sections:
                if isinstance(sec, dict) and "heading" in sec:
                    cleaned.append({
                        "heading": sec["heading"],
                        "content": sec.get("content", ""),
                    })
            result["sections"] = cleaned
            logger.info(f"  ✓ Sections: {len(cleaned)}")
    except Exception as e:
        logger.warning(f"Section extraction failed: {e}")

    # ── FALLBACK: If we got nothing useful, make a single section ──
    if not result["sections"] and text:
        logger.warning("LLM extraction failed — falling back to single section")
        result["sections"] = [{"heading": "Content", "content": clean_text(text[:30000])}]

    if not result["title"]:
        for line in text.split("\n"):
            line = line.strip()
            if line and len(line) > 10 and len(line) < 200:
                result["title"] = line
                break

    return result


def _parse_json_response(content: str):
    """Parse JSON from LLM response, handling markdown fences."""
    content = content.strip()

    # Remove markdown fences
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 3:
            content = parts[1]

    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        # Look for array
        arr_match = re.search(r"\[[\s\S]*\]", content)
        if arr_match:
            try:
                return json.loads(arr_match.group())
            except json.JSONDecodeError:
                pass

        # Look for object
        obj_match = re.search(r"\{[\s\S]*\}", content)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

    return None


def _detect_figures(text: str) -> list:
    """Detect figure references in text."""
    figures = []
    for match in re.finditer(r"((?:Figure|Fig\.?)\s+\d+[^.\n]*\.?)", text, re.IGNORECASE):
        fig = match.group(1).strip()
        if len(fig) > 10:
            figures.append(fig)
    return figures[:20]


def _detect_tables(text: str) -> list:
    """Detect table references in text."""
    tables = []
    for match in re.finditer(r"(Table\s+\d+[^.\n]*\.?)", text, re.IGNORECASE):
        tbl = match.group(1).strip()
        if len(tbl) > 10:
            tables.append(tbl)
    return tables[:20]
