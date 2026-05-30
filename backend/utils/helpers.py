"""
Utility helpers for file handling, text cleaning, etc.
"""
import os
import re
import uuid
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
JOURNAL_RULES_DIR = BASE_DIR / "journal_rules"
FAMILIES_DIR = JOURNAL_RULES_DIR / "families"
JOURNALS_DIR = JOURNAL_RULES_DIR / "journals"

# Ensure dirs exist
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def generate_session_id() -> str:
    return str(uuid.uuid4())[:12]


def detect_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    mapping = {
        "docx": "docx",
        "pdf": "pdf",
        "txt": "txt",
        "md": "markdown",
        "markdown": "markdown",
    }
    return mapping.get(ext, "unknown")


def clean_text(text: str) -> str:
    """Remove excessive whitespace and control characters."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def load_journal_config(journal_name: str) -> dict:
    """Load a specific journal config, merging family defaults."""
    journal_file = JOURNALS_DIR / f"{journal_name}.json"
    if not journal_file.exists():
        raise FileNotFoundError(f"Journal config not found: {journal_name}")

    with open(journal_file, "r", encoding="utf-8") as f:
        journal_config = json.load(f)

    family_name = journal_config.get("family", "")
    family_file = FAMILIES_DIR / f"{family_name}.json"

    family_config = {}
    if family_file.exists():
        with open(family_file, "r", encoding="utf-8") as f:
            family_config = json.load(f)

    # Merge: family defaults + journal overrides
    merged = {**family_config, **journal_config}
    return merged


def load_family_config(family_name: str) -> dict:
    """Load a format family config."""
    family_file = FAMILIES_DIR / f"{family_name}.json"
    if not family_file.exists():
        raise FileNotFoundError(f"Family config not found: {family_name}")

    with open(family_file, "r", encoding="utf-8") as f:
        return json.load(f)


def list_available_journals() -> list:
    """List all available journal configs."""
    journals = []
    for f in JOURNALS_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            journals.append({
                "id": f.stem,
                "name": data.get("journal_name", f.stem),
                "family": data.get("family", ""),
                "citation_style": data.get("citation_style", ""),
            })
    return journals


def list_available_families() -> list:
    """List all available format families."""
    families = []
    for f in FAMILIES_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            families.append({
                "id": f.stem,
                "name": data.get("family_name", f.stem),
                "citation_style": data.get("citation_style", ""),
                "description": data.get("description", ""),
            })
    return families


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def parse_llm_json(content: str):
    """Parse JSON from LLM response, handling markdown fences and fallback extraction."""
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
        # Try to find JSON array
        arr_match = re.search(r"\[[\s\S]*\]", content)
        if arr_match:
            try:
                return json.loads(arr_match.group())
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        obj_match = re.search(r"\{[\s\S]*\}", content)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

    return None
