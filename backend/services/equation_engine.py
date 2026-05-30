"""
Equation & Math Preservation Engine — Detects, preserves, and formats mathematical equations.
Ensures LaTeX equations survive the rewriting pipeline intact.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Patterns to detect various math notations
MATH_PATTERNS = {
    "latex_display": re.compile(r"\$\$(.+?)\$\$", re.DOTALL),           # $$...$$
    "latex_inline": re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)"),  # $...$
    "latex_env": re.compile(r"\\begin\{(equation|align|gather|multline)\*?\}(.+?)\\end\{\1\*?\}", re.DOTALL),
    "bracket_display": re.compile(r"\\\[(.+?)\\\]", re.DOTALL),         # \[...\]
    "paren_inline": re.compile(r"\\\((.+?)\\\)"),                       # \(...\)
    "unicode_math": re.compile(r"[∑∏∫∂∇√∞≤≥≠±×÷∈∉⊂⊃∪∩αβγδεζηθλμνπρσφψω]"),
}

# Common equation number pattern
EQUATION_NUMBER_PATTERN = re.compile(r"\((\d+)\)\s*$", re.MULTILINE)


def extract_equations(text: str) -> dict:
    """
    Extract all mathematical equations from text.
    Returns a dict with equation details and placeholders.
    """
    equations = []
    equation_map = {}  # placeholder -> original equation

    eq_counter = 0

    # Extract display equations ($$...$$)
    for match in MATH_PATTERNS["latex_display"].finditer(text):
        eq_counter += 1
        eq_id = f"__EQ_DISPLAY_{eq_counter}__"
        equations.append({
            "id": eq_id,
            "type": "display",
            "content": match.group(0),
            "inner": match.group(1).strip(),
            "position": match.start(),
        })
        equation_map[eq_id] = match.group(0)

    # Extract LaTeX environments (\begin{equation}...\end{equation})
    for match in MATH_PATTERNS["latex_env"].finditer(text):
        eq_counter += 1
        eq_id = f"__EQ_ENV_{eq_counter}__"
        equations.append({
            "id": eq_id,
            "type": "environment",
            "env_name": match.group(1),
            "content": match.group(0),
            "inner": match.group(2).strip(),
            "position": match.start(),
        })
        equation_map[eq_id] = match.group(0)

    # Extract bracket display equations (\[...\])
    for match in MATH_PATTERNS["bracket_display"].finditer(text):
        eq_counter += 1
        eq_id = f"__EQ_BRACKET_{eq_counter}__"
        equations.append({
            "id": eq_id,
            "type": "display_bracket",
            "content": match.group(0),
            "inner": match.group(1).strip(),
            "position": match.start(),
        })
        equation_map[eq_id] = match.group(0)

    # Extract inline equations ($...$)
    for match in MATH_PATTERNS["latex_inline"].finditer(text):
        eq_counter += 1
        eq_id = f"__EQ_INLINE_{eq_counter}__"
        equations.append({
            "id": eq_id,
            "type": "inline",
            "content": match.group(0),
            "inner": match.group(1).strip(),
            "position": match.start(),
        })
        equation_map[eq_id] = match.group(0)

    # Extract parenthetical inline (\(...\))
    for match in MATH_PATTERNS["paren_inline"].finditer(text):
        eq_counter += 1
        eq_id = f"__EQ_PAREN_{eq_counter}__"
        equations.append({
            "id": eq_id,
            "type": "inline_paren",
            "content": match.group(0),
            "inner": match.group(1).strip(),
            "position": match.start(),
        })
        equation_map[eq_id] = match.group(0)

    return {
        "equations": equations,
        "equation_map": equation_map,
        "total": len(equations),
        "display_count": sum(1 for e in equations if e["type"] in ("display", "environment", "display_bracket")),
        "inline_count": sum(1 for e in equations if e["type"] in ("inline", "inline_paren")),
    }


def protect_equations(text: str) -> tuple:
    """
    Replace all equations with placeholders to protect them during LLM rewriting.
    Returns (protected_text, equation_map).
    """
    result = extract_equations(text)
    equation_map = result["equation_map"]
    protected_text = text

    # Replace longest matches first to avoid partial replacements
    sorted_eqs = sorted(equation_map.items(), key=lambda x: len(x[1]), reverse=True)
    for placeholder, original in sorted_eqs:
        protected_text = protected_text.replace(original, placeholder, 1)

    logger.info(f"Protected {len(equation_map)} equations ({result['display_count']} display, {result['inline_count']} inline)")
    return protected_text, equation_map


def restore_equations(text: str, equation_map: dict) -> str:
    """
    Restore equations from placeholders after LLM rewriting.
    """
    restored = text
    restored_count = 0

    for placeholder, original in equation_map.items():
        if placeholder in restored:
            restored = restored.replace(placeholder, original)
            restored_count += 1
        else:
            # Placeholder was lost during rewriting — append equation as a note
            logger.warning(f"Equation placeholder {placeholder} not found in rewritten text")

    logger.info(f"Restored {restored_count}/{len(equation_map)} equations")
    return restored


def detect_math_content(text: str) -> bool:
    """Check if text contains mathematical content."""
    for pattern in MATH_PATTERNS.values():
        if pattern.search(text):
            return True
    return False


def number_equations(text: str) -> str:
    """
    Auto-number unnumbered display equations sequentially.
    """
    eq_num = 0
    lines = text.split("\n")
    result = []

    for line in lines:
        # Check for display equations without numbers
        if MATH_PATTERNS["latex_display"].search(line) or MATH_PATTERNS["bracket_display"].search(line):
            if not EQUATION_NUMBER_PATTERN.search(line):
                eq_num += 1
                line = line.rstrip() + f"  ({eq_num})"
        result.append(line)

    return "\n".join(result)
