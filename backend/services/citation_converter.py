"""
Citation Converter Service — converts citations between academic styles.
Supports: APA 7, IEEE, Vancouver, Nature, Harvard, Chicago, MLA 9, AMA
"""
import re
from typing import Optional


# Citation style templates
CITATION_STYLES = {
    "apa": {
        "in_text": "({authors}, {year})",
        "reference": "{authors} ({year}). {title}. {journal}, {volume}({issue}), {pages}. {doi}",
        "format": "author_date",
    },
    "ieee": {
        "in_text": "[{number}]",
        "reference": "[{number}] {authors}, \"{title},\" {journal}, vol. {volume}, no. {issue}, pp. {pages}, {year}.",
        "format": "numbered",
    },
    "vancouver": {
        "in_text": "({number})",
        "reference": "{number}. {authors}. {title}. {journal}. {year};{volume}({issue}):{pages}.",
        "format": "numbered",
    },
    "nature": {
        "in_text": "{number}",
        "reference": "{number}. {authors}. {title}. {journal} {volume}, {pages} ({year}).",
        "format": "numbered",
    },
    "springer": {
        "in_text": "[{number}]",
        "reference": "{number}. {authors}. {title}. {journal}. {year};{volume}({issue}):{pages}.",
        "format": "numbered",
    },
    "elsevier": {
        "in_text": "[{number}]",
        "reference": "[{number}] {authors}, {title}, {journal} {volume} ({year}) {pages}.",
        "format": "numbered",
    },
    "harvard": {
        "in_text": "({authors}, {year})",
        "reference": "{authors} {year}, '{title}', {journal}, vol. {volume}, no. {issue}, pp. {pages}.",
        "format": "author_date",
    },
    "chicago": {
        "in_text": "({authors} {year}, {pages})",
        "reference": "{authors}. \"{title}.\" {journal} {volume}, no. {issue} ({year}): {pages}.",
        "format": "author_date",
    },
}


def detect_citation_style(references: list, text: str = "") -> str:
    """Detect the citation style used in the text."""
    if not references and not text:
        return "unknown"

    # Check in-text patterns
    text_to_check = text if text else " ".join(references)

    # IEEE style: [1], [2], [3]
    if re.search(r"\[\d+\]", text_to_check):
        # Could be IEEE, Springer, or Elsevier
        if references:
            ref = references[0] if references else ""
            if ref.startswith("[") and "vol." in ref.lower():
                return "ieee"
            elif ";" in ref:
                return "vancouver"
            else:
                return "ieee"
        return "ieee"

    # Nature: superscript numbers (plain numbers in text)
    if re.search(r"(?<!\w)\d+(?!\w)", text_to_check):
        return "nature"

    # APA: (Author, Year)
    if re.search(r"\([A-Z][a-z]+(?:\s(?:et al\.)?)?,\s\d{4}\)", text_to_check):
        return "apa"

    # Harvard: similar to APA
    if re.search(r"\([A-Z][a-z]+\s\d{4}\)", text_to_check):
        return "harvard"

    return "apa"  # default


def parse_reference(ref_text: str) -> dict:
    """Parse a reference string into structured data."""
    parsed = {
        "authors": "",
        "year": "",
        "title": "",
        "journal": "",
        "volume": "",
        "issue": "",
        "pages": "",
        "doi": "",
        "number": "",
        "raw": ref_text,
    }

    # Remove leading number/bracket
    clean_ref = re.sub(r"^\s*(?:\[\d+\]|\d+\.|\(\d+\))\s*", "", ref_text)

    # Try to extract year
    year_match = re.search(r"\((\d{4})\)|(\d{4})", clean_ref)
    if year_match:
        parsed["year"] = year_match.group(1) or year_match.group(2)

    # Try to extract DOI
    doi_match = re.search(r"(https?://doi\.org/[^\s]+|10\.\d{4,}/[^\s]+)", clean_ref)
    if doi_match:
        parsed["doi"] = doi_match.group(1)

    # Try to extract volume/issue/pages
    vol_match = re.search(r"(?:vol\.?\s*)?(\d+)\s*(?:\((\d+)\))?\s*(?:,\s*(?:pp\.?\s*)?(\d+[-–]\d+))?", clean_ref)
    if vol_match:
        parsed["volume"] = vol_match.group(1) or ""
        parsed["issue"] = vol_match.group(2) or ""
        parsed["pages"] = vol_match.group(3) or ""

    # First part is usually authors
    parts = re.split(r"\.\s+|\(\d{4}\)", clean_ref, maxsplit=2)
    if parts:
        parsed["authors"] = parts[0].strip().rstrip(",").rstrip(".")

    # Title is typically the second part
    if len(parts) > 1:
        title = parts[1].strip().strip('"').strip("'").rstrip(".")
        parsed["title"] = title

    return parsed


def format_reference(parsed: dict, style: str, number: int = 1) -> str:
    """Format a parsed reference into the target style."""
    style_config = CITATION_STYLES.get(style, CITATION_STYLES["apa"])
    template = style_config["reference"]

    # If we couldn't parse well, return cleaned original
    if not parsed.get("authors") or not parsed.get("title"):
        raw = parsed.get("raw", "")
        if style_config["format"] == "numbered":
            num_prefix = template.split("{authors}")[0].format(number=number)
            # Remove existing number prefix
            clean = re.sub(r"^\s*(?:\[\d+\]|\d+\.|\(\d+\))\s*", "", raw)
            return f"{num_prefix}{clean}"
        return raw

    formatted = template.format(
        number=number,
        authors=parsed.get("authors", ""),
        year=parsed.get("year", "n.d."),
        title=parsed.get("title", ""),
        journal=parsed.get("journal", ""),
        volume=parsed.get("volume", ""),
        issue=parsed.get("issue", ""),
        pages=parsed.get("pages", ""),
        doi=parsed.get("doi", ""),
    )

    # Clean up empty placeholders
    formatted = re.sub(r"\(\)", "", formatted)
    formatted = re.sub(r",\s*,", ",", formatted)
    formatted = re.sub(r"\s{2,}", " ", formatted)

    return formatted.strip()


def convert_citations(
    references: list,
    text: str,
    target_style: str,
    source_style: Optional[str] = None,
) -> dict:
    """
    Convert all citations from source to target style.
    Returns converted references and updated text.
    """
    if not source_style:
        source_style = detect_citation_style(references, text)

    target_config = CITATION_STYLES.get(target_style, CITATION_STYLES["apa"])

    # Parse all references
    parsed_refs = []
    for i, ref in enumerate(references):
        parsed = parse_reference(ref)
        parsed["number"] = str(i + 1)
        parsed_refs.append(parsed)

    # Format references in target style
    formatted_refs = []
    for i, parsed in enumerate(parsed_refs):
        formatted = format_reference(parsed, target_style, i + 1)
        formatted_refs.append(formatted)

    # Convert in-text citations
    updated_text = _convert_in_text_citations(
        text, parsed_refs, source_style, target_style
    )

    return {
        "references": formatted_refs,
        "text": updated_text,
        "source_style": source_style,
        "target_style": target_style,
    }


def _convert_in_text_citations(
    text: str,
    parsed_refs: list,
    source_style: str,
    target_style: str
) -> str:
    """Convert in-text citations in the manuscript text."""
    if not text:
        return text

    target_config = CITATION_STYLES.get(target_style, CITATION_STYLES["apa"])

    # Replace numbered citations: [1] -> (1) or (Author, Year)
    def replace_numbered(match):
        num = match.group(1)
        idx = int(num) - 1
        if target_config["format"] == "numbered":
            return target_config["in_text"].format(number=num)
        elif target_config["format"] == "author_date" and idx < len(parsed_refs):
            ref = parsed_refs[idx]
            authors = ref.get("authors", "").split(",")[0].strip()
            year = ref.get("year", "n.d.")
            return target_config["in_text"].format(authors=authors, year=year)
        return match.group(0)

    # Handle [N] style
    text = re.sub(r"\[(\d+)\]", replace_numbered, text)

    # Handle (N) style for Vancouver
    text = re.sub(r"\((\d+)\)(?!\w)", replace_numbered, text)

    return text


def reorder_references_numerically(references: list, text: str) -> tuple:
    """Reorder references based on order of appearance in text."""
    # Find all citation numbers in text
    citations = re.findall(r"\[(\d+)\]|\((\d+)\)", text)
    order = []
    for match in citations:
        num = int(match[0] or match[1])
        if num not in order:
            order.append(num)

    # Add any references not cited
    for i in range(1, len(references) + 1):
        if i not in order:
            order.append(i)

    # Reorder
    reordered = []
    mapping = {}
    for new_idx, old_idx in enumerate(order):
        if old_idx - 1 < len(references):
            reordered.append(references[old_idx - 1])
            mapping[old_idx] = new_idx + 1

    # Update citations in text
    def renumber(match):
        num = int(match.group(1) or match.group(2))
        new_num = mapping.get(num, num)
        if match.group(1):
            return f"[{new_num}]"
        return f"({new_num})"

    updated_text = re.sub(r"\[(\d+)\]|\((\d+)\)", renumber, text)

    return reordered, updated_text
