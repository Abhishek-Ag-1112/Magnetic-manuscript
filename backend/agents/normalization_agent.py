"""
Structure Normalization Agent — Uses LLM intelligence to ACTIVELY restructure
the manuscript to match journal requirements. This agent doesn't just rename 
sections — it splits, merges, and reorganizes content for compliance.
"""
import os
import re
import json
import logging
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")

# Standard section name mappings
SECTION_ALIASES = {
    "introduction": "Introduction",
    "intro": "Introduction",
    "background": "Background",
    "overview": "Introduction",
    "methods": "Methods",
    "method": "Methods",
    "methodology": "Methods",
    "materials and methods": "Materials and Methods",
    "materials & methods": "Materials and Methods",
    "experimental methods": "Methods",
    "star methods": "STAR Methods",
    "results": "Results",
    "result": "Results",
    "findings": "Results",
    "results and discussion": "Results and Discussion",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
    "conclusions": "Conclusion",
    "concluding remarks": "Conclusion",
    "summary": "Summary",
    "literature review": "Literature Review",
    "related work": "Related Work",
    "acknowledgments": "Acknowledgments",
    "acknowledgements": "Acknowledgments",
    "references": "References",
    "bibliography": "References",
    "abstract": "Abstract",
    "keywords": "Keywords",
    "data availability": "Data Availability",
    "supplementary material": "Supplementary Material",
    "significance": "Significance",
    "author contributions": "Author Contributions",
    "funding": "Funding",
    "conflict of interest": "Conflict of Interest",
}

RESTRUCTURE_PROMPT = """You are an expert academic manuscript editor restructuring a paper for {journal_name}.

The target journal REQUIRES these sections in this exact order: {section_order}

Current manuscript sections:
{current_sections}

INSTRUCTIONS:
Instead of rewriting content, your job is to MAP the existing sections to the required journal headings.
1. Assign every "Old Heading" to the most appropriate "New Heading" from the journal's required sequence.
2. If multiple old sections fit a single new heading, map them both to that same new heading (they will be merged).
3. If an old section doesn't clearly fit, map it to the closest match or keep its original name if it's supplementary info.
4. DO NOT write or include the content text. Only return the mapping.

Return ONLY a valid JSON array of objects with mapping:
[
  {{"old_heading": "Introduction", "new_heading": "Introduction"}},
  {{"old_heading": "Experimental Setup", "new_heading": "Methods"}},
  {{"old_heading": "Data Collection", "new_heading": "Methods"}}
]"""


def normalization_agent(state: dict) -> dict:
    """
    Normalize and ACTIVELY restructure the manuscript for the target journal.
    Uses LLM to map existing sections to the correct journal structure without touching text.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        if not structured:
            errors.append("No structured content available for normalization")
            return {**state, "errors": errors, "current_step": "normalization_failed"}

        sections = structured.get("sections", [])
        journal_rules = state.get("journal_rules", {})
        section_order = journal_rules.get("section_order", [])
        journal_name = journal_rules.get("journal_name", journal_rules.get("family_name", "the target journal"))

        # Step 1: Basic heading normalization
        normalized_sections = []
        for sec in sections:
            heading = sec.get("heading", "").strip()
            normalized_heading = _normalize_heading(heading)
            normalized_sections.append({
                "heading": normalized_heading,
                "content": sec.get("content", ""),
                "original_heading": heading,
            })

        # Step 2: Remove empties and merge duplicates
        normalized_sections = [s for s in normalized_sections if s.get("content", "").strip()]
        normalized_sections = _remove_duplicates(normalized_sections)

        # Step 3: Check if we need LLM restructuring
        if section_order and len(normalized_sections) > 0:
            existing_names = {s["heading"].lower() for s in normalized_sections}
            required_names = {s.lower() for s in section_order if s.lower() not in ("abstract", "references", "keywords")}
            
            # Check how many required sections are present
            found = 0
            for req in required_names:
                for ex in existing_names:
                    if req in ex or ex in req or _are_equivalent(req, ex):
                        found += 1
                        break

            needs_restructure = found < len(required_names) * 0.7

            if needs_restructure:
                logger.info(f"LLM restructuring: {found}/{len(required_names)} required sections found")
                restructured = _llm_restructure(normalized_sections, section_order, journal_name)
                if restructured:
                    normalized_sections = restructured
            else:
                # Simple reorder
                normalized_sections = _reorder_sections(normalized_sections, section_order)

        # Update the structured JSON
        structured["sections"] = normalized_sections

        # Step 4: Extract keywords if not present
        if not structured.get("keywords"):
            structured["keywords"] = _extract_keywords(structured)

        # Step 5: Safety net — back-fill missing critical content from raw text
        raw_text = structured.get("raw_text", "")

        # Back-fill references if missing
        if not structured.get("references") and raw_text:
            refs = _extract_references_from_raw(raw_text)
            if refs:
                structured["references"] = refs
                logger.info(f"Back-filled {len(refs)} references from raw text")

        # Back-fill abstract if missing
        if not structured.get("abstract") and raw_text:
            abstract_text = _extract_abstract_from_raw(raw_text)
            if abstract_text:
                structured["abstract"] = abstract_text
                logger.info(f"Back-filled abstract ({len(abstract_text)} chars) from raw text")

        # Back-fill authors if missing
        if not structured.get("authors") and raw_text:
            authors = _extract_authors_from_raw(raw_text)
            if authors:
                structured["authors"] = authors
                logger.info(f"Back-filled {len(authors)} authors from raw text")

        # Step 6 preservation check: We NO LONGER trim or rewrite abstracts.
        # Strict preservation of all text is enforced per user requirement.
        logger.info(f"Preserving abstract exactly as parsed: {len(structured.get('abstract', '').split())} words")

        return {
            **state,
            "structured_json": structured,
            "current_step": "normalization_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Normalization failed: {str(e)}")
        errors.append(f"Normalization error: {str(e)}")
        return {**state, "errors": errors, "current_step": "normalization_failed"}


def _are_equivalent(a: str, b: str) -> bool:
    """Check if two section names are equivalent."""
    groups = [
        {"methods", "method", "methodology", "materials and methods", "experimental"},
        {"results", "findings", "experimental results"},
        {"discussion", "analysis"},
        {"conclusion", "conclusions", "concluding remarks", "summary"},
        {"introduction", "background", "overview"},
        {"acknowledgments", "acknowledgements", "author contributions", "funding"},
    ]
    for group in groups:
        if a in group and b in group:
            return True
    return False


def _llm_restructure(sections: list, section_order: list, journal_name: str) -> list:
    """Use LLM to map existing headings to target journal headings, safely merging content."""
    try:
        # Build sections summary for the prompt
        sections_summary = []
        for s in sections:
            content_preview = s["content"][:300] + "..." if len(s["content"]) > 300 else s["content"]
            sections_summary.append(f'Old Heading: "{s["heading"]}"\nContent preview: {content_preview}\n---')

        current_sections_text = "\n".join(sections_summary)

        # Filter section_order to remove abstract/refs (handled separately)
        body_order = [s for s in section_order if s.lower() not in ("abstract", "references", "keywords")]

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=2048)

        response = llm.invoke([
            SystemMessage(content="You map manuscript sections to required journal structures. Return ONLY valid JSON array."),
            HumanMessage(content=RESTRUCTURE_PROMPT.format(
                journal_name=journal_name,
                section_order=json.dumps(body_order),
                current_sections=current_sections_text,
            )),
        ])

        content = response.content.strip()
        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1]

        mapping_result = json.loads(content.strip())
        
        # Apply the mapping securely
        if isinstance(mapping_result, list) and len(mapping_result) > 0:
            mapping_dict = {}
            for map_item in mapping_result:
                if isinstance(map_item, dict) and "old_heading" in map_item and "new_heading" in map_item:
                    mapping_dict[map_item["old_heading"]] = map_item["new_heading"]

            structured_dict = {}
            for sec in sections:
                old_head = sec.get("heading")
                content_text = sec.get("content", "")
                new_head = mapping_dict.get(old_head, old_head) # Fallback to old if not mapped
                
                if new_head not in structured_dict:
                    structured_dict[new_head] = content_text
                else:
                    # Merge content safely
                    structured_dict[new_head] += f"\n\n{content_text}"

            # Convert back to list format in the specified order where possible
            cleaned = []
            seen_heads = set()
            
            # Add required sections in order
            for req_head in body_order:
                for active_head in list(structured_dict.keys()):
                    if req_head.lower() == active_head.lower() or _are_equivalent(req_head.lower(), active_head.lower()):
                        if active_head not in seen_heads:
                            cleaned.append({"heading": req_head, "content": structured_dict[active_head]})
                            seen_heads.add(active_head)
            
            # Append anything that didn't fit the strict order at the end
            for active_head, text in structured_dict.items():
                if active_head not in seen_heads:
                    cleaned.append({"heading": active_head, "content": text})

            logger.info(f"LLM securely mapped into {len(cleaned)} sections without data loss")
            return cleaned

    except Exception as e:
        logger.warning(f"LLM restructuring mapping failed: {e}")

    return None


def _normalize_heading(heading: str) -> str:
    """Normalize a section heading to standard academic form."""
    cleaned = re.sub(r"^\d+[\.\)]\s*", "", heading).strip()
    cleaned = re.sub(r"^[IVXLC]+[\.\)]\s*", "", cleaned).strip()

    lookup = cleaned.lower().strip()
    if lookup in SECTION_ALIASES:
        return SECTION_ALIASES[lookup]

    return cleaned.title() if cleaned else heading


def _remove_duplicates(sections: list) -> list:
    """Remove duplicate sections, merging content of duplicates."""
    seen = {}
    result = []

    for sec in sections:
        heading = sec["heading"]
        if heading in seen:
            idx = seen[heading]
            existing_content = result[idx]["content"]
            new_content = sec["content"]
            if new_content and new_content not in existing_content:
                result[idx]["content"] = f"{existing_content}\n\n{new_content}"
        else:
            seen[heading] = len(result)
            result.append(sec)

    return result


def _reorder_sections(sections: list, order: list) -> list:
    """Reorder sections based on journal-specified order."""
    ordered = []
    remaining = list(sections)
    order_normalized = [s.lower().strip() for s in order]

    for target in order_normalized:
        if target in ("abstract", "references", "keywords"):
            continue

        best_idx = None
        for i, sec in enumerate(remaining):
            sec_heading = sec["heading"].lower().strip()
            if sec_heading == target or target in sec_heading or sec_heading in target or _are_equivalent(target, sec_heading):
                best_idx = i
                break

        if best_idx is not None:
            ordered.append(remaining.pop(best_idx))

    ordered.extend(remaining)
    return ordered






def _extract_keywords(structured: dict) -> list:
    """Extract keywords using LLM."""
    try:
        abstract = structured.get("abstract", "")
        title = structured.get("title", "")

        if not abstract and not title:
            return []

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=200)

        prompt = f"""Extract 4-6 academic keywords from this manuscript.
Title: {title}
Abstract: {abstract[:500]}

Return ONLY a comma-separated list of keywords, no explanation."""

        response = llm.invoke([HumanMessage(content=prompt)])
        keywords_text = response.content.strip()

        keywords_text = re.sub(r"^(Keywords?:?\s*)", "", keywords_text, flags=re.IGNORECASE)
        keywords = [kw.strip().strip('"').strip("'").strip("-").strip("•") for kw in keywords_text.split(",")]
        keywords = [kw for kw in keywords if kw and len(kw) < 60 and not kw.startswith("{")]

        return keywords[:6]

    except Exception as e:
        logger.warning(f"Keyword extraction failed: {str(e)}")
        return []


def _extract_references_from_raw(raw_text: str) -> list:
    """Extract references from raw text using regex — handles missing headers."""
    # Try 1: Look for explicit "References" heading
    ref_match = re.search(
        r'(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY|Works Cited)\s*\n([\s\S]+?)$',
        raw_text, re.IGNORECASE
    )
    if ref_match:
        ref_block = ref_match.group(1).strip()
        refs = re.split(r'\n\s*(?:\[\d+\]|\d+\.\s|\(\d+\))', ref_block)
        refs = [r.strip() for r in refs if r.strip() and len(r.strip()) > 15]
        if refs:
            return refs

    # Try 2: Look for numbered reference lines at end of document
    # References often appear as lines starting with [1], 1., etc.
    last_chunk = raw_text[-15000:]  # Last ~15K chars
    lines = last_chunk.split('\n')

    ref_lines = []
    in_refs = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect lines that look like references
        is_ref_line = bool(re.match(r'^\[\d+\]', stripped))  # [1] Author...
        is_ref_line = is_ref_line or bool(re.match(r'^\d+\.\s+[A-Z]', stripped))  # 1. Author...
        is_ref_line = is_ref_line or bool(re.match(r'^\(\d+\)', stripped))  # (1) Author...

        # Also detect continuation of a reference (contains journal-like patterns)
        has_journal_pattern = bool(re.search(
            r'\d{4}[;,.]|\bvol\b|\bpp?\.\s*\d|\bet al\b|doi:|https?://|Mol\s+|Proc\s+|BMC\s+|J\s+\w+\s+\w+',
            stripped, re.IGNORECASE
        ))

        if is_ref_line:
            in_refs = True
            ref_lines.append(stripped)
        elif in_refs and has_journal_pattern and len(stripped) > 20:
            # Continuation of reference section
            ref_lines.append(stripped)
        elif in_refs and not has_journal_pattern and len(ref_lines) > 3:
            # End of references
            break

    if len(ref_lines) >= 3:
        # Clean numbered prefixes and return
        cleaned = []
        for ref in ref_lines:
            ref = re.sub(r'^\[\d+\]\s*', '', ref)
            ref = re.sub(r'^\d+\.\s+', '', ref)
            ref = re.sub(r'^\(\d+\)\s*', '', ref)
            if ref and len(ref) > 15:
                cleaned.append(ref)
        return cleaned

    # Try 3: Look for lines containing typical citation patterns near end
    ref_candidates = []
    for line in lines[-100:]:
        stripped = line.strip()
        if stripped and len(stripped) > 30 and re.search(
            r'(?:\d{4}[;,.].*(?:\d+[:-]\d+|doi:|pp?\.))|(?:et al\.)', stripped
        ):
            ref_candidates.append(stripped)

    if len(ref_candidates) >= 5:
        return ref_candidates

    return []


def _extract_abstract_from_raw(raw_text: str) -> str:
    """Extract abstract from raw text using regex."""
    patterns = [
        r'(?:Abstract|ABSTRACT)[:\s]*\n([\s\S]{50,2000}?)(?:\n\s*(?:Keywords|KEYWORDS|Introduction|INTRODUCTION|1[\.\s]))',
        r'(?:Abstract|ABSTRACT)[:\s]*\n([\s\S]{50,2000}?)(?:\n\n)',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            abstract = match.group(1).strip()
            if len(abstract) > 50:
                return abstract
    return ""


def _extract_authors_from_raw(raw_text: str) -> list:
    """Extract authors from raw text using heuristics."""
    lines = raw_text.split('\n')[:20]  # Authors are usually in the first 20 lines

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Look for lines with comma-separated names (likely authors)
        # Skip very short or very long lines
        if 10 < len(line) < 300:
            # Check if line contains multiple names separated by commas
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                # Check if parts look like names (2-4 words each)
                looks_like_names = all(
                    1 <= len(p.split()) <= 5 and not any(c.isdigit() for c in p)
                    for p in parts if p
                )
                if looks_like_names:
                    return [p for p in parts if p]

    return []

