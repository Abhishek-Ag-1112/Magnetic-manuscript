"""
BibTeX Export Service — Converts references to BibTeX format.
Supports export for Overleaf and standalone .bib files.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# BibTeX entry types based on reference content heuristics
ENTRY_TYPES = {
    "journal": "@article",
    "conference": "@inproceedings",
    "book": "@book",
    "thesis": "@phdthesis",
    "report": "@techreport",
    "online": "@misc",
}


def references_to_bibtex(references: list, citation_style: str = "") -> str:
    """
    Convert a list of reference strings to BibTeX format.

    Args:
        references: List of reference strings
        citation_style: Source citation style (helps with parsing)

    Returns:
        Complete .bib file content as a string
    """
    entries = []

    for i, ref in enumerate(references):
        ref_text = ref if isinstance(ref, str) else str(ref)
        entry = _parse_reference_to_bibtex(ref_text, i + 1)
        if entry:
            entries.append(entry)

    bibtex_content = "\n\n".join(entries)

    # Add header comment
    header = (
        "% BibTeX references exported by Magnetic Manuscript\n"
        f"% Total entries: {len(entries)}\n"
        "% Generated automatically — please review for accuracy\n\n"
    )

    return header + bibtex_content


def _parse_reference_to_bibtex(ref_text: str, index: int) -> Optional[str]:
    """Parse a single reference string into a BibTeX entry."""

    # Clean up reference text
    ref_clean = re.sub(r"^\[?\d+\]?\s*", "", ref_text).strip()
    ref_clean = re.sub(r"^\d+\.\s*", "", ref_clean).strip()

    if len(ref_clean) < 10:
        return None

    # Extract common fields
    authors = _extract_authors(ref_clean)
    year = _extract_year(ref_clean)
    title = _extract_title(ref_clean)
    doi = _extract_doi(ref_clean)
    journal = _extract_journal(ref_clean)
    volume = _extract_volume(ref_clean)
    pages = _extract_pages(ref_clean)

    # Determine entry type
    entry_type = _determine_entry_type(ref_clean)

    # Generate citation key
    first_author_last = authors.split(",")[0].split()[-1] if authors else "Unknown"
    first_author_last = re.sub(r"[^a-zA-Z]", "", first_author_last)
    cite_key = f"{first_author_last}{year}_{index}" if year else f"{first_author_last}_{index}"

    # Build BibTeX entry
    fields = []
    if authors:
        fields.append(f"  author    = {{{authors}}}")
    if title:
        fields.append(f"  title     = {{{title}}}")
    if journal:
        fields.append(f"  journal   = {{{journal}}}")
    if year:
        fields.append(f"  year      = {{{year}}}")
    if volume:
        fields.append(f"  volume    = {{{volume}}}")
    if pages:
        fields.append(f"  pages     = {{{pages}}}")
    if doi:
        fields.append(f"  doi       = {{{doi}}}")

    if not fields:
        # Fallback: store raw text as note
        fields.append(f"  note      = {{{ref_clean[:200]}}}")

    entry = f"{entry_type}{{{cite_key},\n"
    entry += ",\n".join(fields)
    entry += "\n}"

    return entry


def _extract_authors(text: str) -> str:
    """Extract author names from reference text."""
    # Look for pattern: "LastName, F.M., LastName, F.M., ..."
    author_match = re.match(r"^(.+?)(?:\.|,\s*[\"'])", text)
    if author_match:
        author_str = author_match.group(1)
        # Clean: only take content before title patterns
        if len(author_str) < 200:
            return author_str.strip().rstrip(",").rstrip(".")

    # Try: "F.M. LastName, F.M. LastName"
    author_block = text.split('"')[0].split("'")[0]
    if "," in author_block:
        parts = author_block.split(",")
        if len(parts) <= 8:
            return ", ".join(p.strip() for p in parts[:6]).rstrip(",").rstrip(".")

    return text[:50].strip()


def _extract_year(text: str) -> str:
    """Extract publication year."""
    match = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", text)
    return match.group(1) if match else ""


def _extract_title(text: str) -> str:
    """Extract title from reference."""
    # Quoted title
    quoted = re.search(r'["\u201c](.+?)["\u201d]', text)
    if quoted:
        return quoted.group(1)

    # Title after authors (heuristic)
    parts = re.split(r"\.\s+", text, maxsplit=3)
    if len(parts) >= 2:
        candidate = parts[1].strip()
        if 10 < len(candidate) < 300:
            return candidate.rstrip(".")

    return ""


def _extract_doi(text: str) -> str:
    """Extract DOI."""
    match = re.search(r"(10\.\d{4,}/[^\s,]+)", text)
    return match.group(1).rstrip(".") if match else ""


def _extract_journal(text: str) -> str:
    """Extract journal name (heuristic)."""
    # Look for italicized journal (common in many styles)
    ital = re.search(r"_(.+?)_", text)
    if ital:
        return ital.group(1)

    # Look for common journal abbreviations
    parts = re.split(r"\.\s+", text)
    for part in parts[2:4]:
        # Journal names are usually shorter, title-cased
        if 5 < len(part) < 100 and not part[0].isdigit():
            return part.strip().rstrip(",").rstrip(".")

    return ""


def _extract_volume(text: str) -> str:
    """Extract volume number."""
    match = re.search(r"(?:vol\.|volume)\s*(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: number before parenthesized issue
    match = re.search(r"\b(\d{1,4})\s*\(\d+\)", text)
    return match.group(1) if match else ""


def _extract_pages(text: str) -> str:
    """Extract page numbers."""
    match = re.search(r"(?:pp?\.\s*|pages?\s+)(\d+[-–]\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace("–", "--")
    match = re.search(r"\b(\d{1,6})[-–](\d{1,6})\b", text)
    if match:
        return f"{match.group(1)}--{match.group(2)}"
    return ""


def _determine_entry_type(text: str) -> str:
    """Determine BibTeX entry type from reference content."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["proceedings", "conference", "workshop", "symposium"]):
        return ENTRY_TYPES["conference"]
    if any(kw in text_lower for kw in ["thesis", "dissertation"]):
        return ENTRY_TYPES["thesis"]
    if any(kw in text_lower for kw in ["technical report", "tech. rep."]):
        return ENTRY_TYPES["report"]
    if any(kw in text_lower for kw in ["http://", "https://", "accessed", "online"]):
        return ENTRY_TYPES["online"]
    if any(kw in text_lower for kw in ["publisher", "press", "edition", "isbn"]):
        return ENTRY_TYPES["book"]
    return ENTRY_TYPES["journal"]
