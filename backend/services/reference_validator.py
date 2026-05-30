"""
Reference Validator Service — CrossRef API integration for DOI validation.
Validates references against CrossRef to verify DOIs and auto-fill metadata.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Use httpx if available, otherwise fallback to urllib
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    import urllib.request
    import json as json_mod


CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "MagneticManuscript/2.0 (mailto:contact@magneticmanuscript.dev)"


def validate_references(references: list) -> dict:
    """
    Validate a list of references against CrossRef.

    Args:
        references: List of reference strings

    Returns:
        dict with validation results per reference
    """
    results = {
        "total": len(references),
        "validated": 0,
        "doi_found": 0,
        "doi_missing": 0,
        "errors": 0,
        "details": [],
    }

    for i, ref in enumerate(references):
        ref_text = ref if isinstance(ref, str) else str(ref)

        # Try to extract existing DOI
        doi_match = re.search(r'(10\.\d{4,}/[^\s,]+)', ref_text)

        if doi_match:
            doi = doi_match.group(1)
            # Validate the existing DOI
            validation = _validate_doi(doi)
            if validation:
                results["validated"] += 1
                results["doi_found"] += 1
                results["details"].append({
                    "index": i + 1,
                    "status": "valid_doi",
                    "doi": doi,
                    "crossref_title": validation.get("title", ""),
                    "crossref_authors": validation.get("authors", []),
                    "original": ref_text[:200],
                })
            else:
                results["details"].append({
                    "index": i + 1,
                    "status": "invalid_doi",
                    "doi": doi,
                    "original": ref_text[:200],
                    "message": "DOI not found in CrossRef",
                })
        else:
            # Try to find DOI by searching CrossRef
            found_doi = _search_crossref(ref_text)
            if found_doi:
                results["doi_found"] += 1
                results["validated"] += 1
                results["details"].append({
                    "index": i + 1,
                    "status": "doi_discovered",
                    "doi": found_doi.get("doi", ""),
                    "crossref_title": found_doi.get("title", ""),
                    "original": ref_text[:200],
                    "message": "DOI found via CrossRef search",
                })
            else:
                results["doi_missing"] += 1
                results["details"].append({
                    "index": i + 1,
                    "status": "no_doi",
                    "original": ref_text[:200],
                    "message": "Could not find DOI for this reference",
                })

    return results


def _validate_doi(doi: str) -> Optional[dict]:
    """Validate a DOI against CrossRef and return metadata."""
    url = f"{CROSSREF_API}/{doi}"

    try:
        if HAS_HTTPX:
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200:
                    data = resp.json()
                    return _parse_crossref_item(data.get("message", {}))
        else:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json_mod.loads(resp.read().decode())
                return _parse_crossref_item(data.get("message", {}))
    except Exception as e:
        logger.debug(f"DOI validation failed for {doi}: {e}")

    return None


def _search_crossref(ref_text: str) -> Optional[dict]:
    """Search CrossRef for a reference by text query."""
    # Extract likely title portion (first ~100 chars, stopping at year or numbers)
    query = re.sub(r'\[?\d+\]?\s*', '', ref_text)  # Remove reference numbers
    query = re.sub(r'\(\d{4}\)', '', query)  # Remove years in parens
    query = query[:150].strip()

    if len(query) < 20:
        return None

    try:
        if HAS_HTTPX:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    CROSSREF_API,
                    params={"query": query, "rows": 1},
                    headers={"User-Agent": USER_AGENT},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("message", {}).get("items", [])
                    if items:
                        item = items[0]
                        score = item.get("score", 0)
                        if score > 50:  # Only accept high-confidence matches
                            return _parse_crossref_item(item)
        else:
            params = urllib.parse.urlencode({"query": query, "rows": 1})
            url = f"{CROSSREF_API}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json_mod.loads(resp.read().decode())
                items = data.get("message", {}).get("items", [])
                if items:
                    item = items[0]
                    score = item.get("score", 0)
                    if score > 50:
                        return _parse_crossref_item(item)
    except Exception as e:
        logger.debug(f"CrossRef search failed: {e}")

    return None


def _parse_crossref_item(item: dict) -> dict:
    """Parse a CrossRef work item into a simple dict."""
    title_list = item.get("title", [])
    title = title_list[0] if title_list else ""

    authors = []
    for author in item.get("author", []):
        name = f"{author.get('given', '')} {author.get('family', '')}".strip()
        if name:
            authors.append(name)

    return {
        "doi": item.get("DOI", ""),
        "title": title,
        "authors": authors,
        "journal": item.get("container-title", [""])[0] if item.get("container-title") else "",
        "year": str(item.get("published-print", {}).get("date-parts", [[""]])[0][0] or ""),
        "type": item.get("type", ""),
    }
