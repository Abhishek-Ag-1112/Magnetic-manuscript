"""
Compliance Checker Service — validates manuscripts against journal rules.
Generates compliance score with per-category breakdown and detailed violation/warning reports.
"""
import re
from typing import Optional

from utils.helpers import word_count


def check_compliance(structured_json: dict, journal_rules: dict) -> dict:
    """
    Validate the manuscript against journal rules.
    Returns a compliance report with score, per-category breakdown, violations, and warnings.
    """
    violations = []
    warnings = []
    checks_passed = 0
    total_checks = 0

    # Category scores tracking
    categories = {
        "structure": {"passed": 0, "total": 0, "label": "Section Structure"},
        "content": {"passed": 0, "total": 0, "label": "Content Quality"},
        "citations": {"passed": 0, "total": 0, "label": "Citations & References"},
        "metadata": {"passed": 0, "total": 0, "label": "Metadata Completeness"},
        "formatting": {"passed": 0, "total": 0, "label": "Formatting Compliance"},
    }

    # 1. Abstract word limit check
    total_checks += 1
    categories["content"]["total"] += 1
    abstract = structured_json.get("abstract", "")
    abstract_limit = journal_rules.get("abstract_word_limit", 300)
    abstract_words = word_count(abstract)

    abstract_tolerance = int(abstract_limit * 1.05)  # 5% tolerance
    if abstract_words > abstract_tolerance:
        violations.append({
            "type": "abstract_word_limit",
            "message": f"Abstract exceeds word limit: {abstract_words}/{abstract_limit} words",
            "severity": "error",
            "current": abstract_words,
            "limit": abstract_limit,
            "category": "content",
        })
    elif abstract_words > abstract_limit:
        warnings.append({
            "type": "abstract_near_limit",
            "message": f"Abstract slightly over word limit: {abstract_words}/{abstract_limit} words (within 5% tolerance)",
            "severity": "warning",
            "category": "content",
        })
        checks_passed += 1
        categories["content"]["passed"] += 1
    elif abstract_words == 0:
        violations.append({
            "type": "missing_abstract",
            "message": "Abstract is missing",
            "severity": "error",
            "category": "content",
        })
    else:
        checks_passed += 1
        categories["content"]["passed"] += 1
        if abstract_words > abstract_limit * 0.9:
            warnings.append({
                "type": "abstract_near_limit",
                "message": f"Abstract is near word limit: {abstract_words}/{abstract_limit} words",
                "severity": "warning",
                "category": "content",
            })

    # 2. Mandatory sections check
    total_checks += 1
    categories["structure"]["total"] += 1
    section_order = journal_rules.get("section_order", [])
    existing_sections = set()
    for sec in structured_json.get("sections", []):
        heading = sec.get("heading", "").lower().strip()
        heading = re.sub(r"^\d+\.?\s*", "", heading)
        existing_sections.add(heading)

    if abstract:
        existing_sections.add("abstract")
    if structured_json.get("references"):
        existing_sections.add("references")

    section_equivalences = {
        "methods": {"methods", "method", "methodology", "materials and methods",
                    "materials & methods", "experimental methods", "experimental",
                    "experimental setup", "experimental procedures", "star methods",
                    "procedures", "experimental design", "experimental section",
                    "materials", "technique", "techniques"},
        "results": {"results", "result", "findings", "experimental results",
                    "results and discussion", "significance"},
        "discussion": {"discussion", "analysis", "results and discussion",
                       "general discussion", "interpretation"},
        "conclusion": {"conclusion", "conclusions", "concluding remarks",
                       "summary", "summary and conclusions", "significance"},
        "introduction": {"introduction", "background", "overview", "preface"},
        "related work": {"related work", "related works", "literature review",
                         "prior work", "state of the art", "background"},
        "acknowledgments": {"acknowledgments", "acknowledgements", "acknowledgment",
                            "author contributions", "authors contributions",
                            "funding", "declarations"},
    }

    def _sections_match(required: str, existing_set: set) -> bool:
        req = required.lower().strip()
        for ex in existing_set:
            if req in ex or ex in req:
                return True
        for group_key, equivalents in section_equivalences.items():
            if req in equivalents or req == group_key:
                for ex in existing_set:
                    if ex in equivalents or ex == group_key:
                        return True
        return False

    missing_sections = []
    for required in section_order:
        if not _sections_match(required, existing_sections):
            missing_sections.append(required)

    if missing_sections:
        all_content = " ".join(s.get("content", "") for s in structured_json.get("sections", [])).lower()
        raw = structured_json.get("raw_text", "").lower()

        section_indicators = {
            "methods": ["experiment", "assay", "strain", "buffer", "culture",
                        "incubat", "plasmid", "pcr", "primer", "construct",
                        "protocol", "measure", "sample", "procedure", "method"],
            "materials and methods": ["experiment", "assay", "strain", "buffer",
                        "culture", "plasmid", "pcr", "primer", "protocol"],
            "conclusion": ["conclud", "summary", "in conclusion", "in summary",
                          "our findings", "this study", "we have shown",
                          "taken together", "overall"],
            "acknowledgments": ["acknowledge", "funding", "grant", "supported by",
                                "contribution", "thank", "grateful"],
            "discussion": ["suggest", "implicat", "consistent with", "in contrast",
                          "previous studies", "future work", "limitation"],
            "introduction": ["background", "previously", "in this study",
                            "the aim of", "is known to", "has been shown"],
        }

        truly_missing = []
        soft_missing = []
        for ms in missing_sections:
            ms_lower = ms.lower().strip()
            indicators = section_indicators.get(ms_lower, [])
            if indicators:
                has_content = sum(1 for ind in indicators if ind in raw) >= 2
                if has_content:
                    soft_missing.append(ms)
                else:
                    truly_missing.append(ms)
            else:
                soft_missing.append(ms)

        if truly_missing:
            violations.append({
                "type": "missing_sections",
                "message": f"Missing required sections: {', '.join(truly_missing)}",
                "severity": "error",
                "missing": truly_missing,
                "category": "structure",
            })
        else:
            checks_passed += 1
            categories["structure"]["passed"] += 1

        if soft_missing:
            warnings.append({
                "type": "sections_not_separate",
                "message": f"Content for '{', '.join(soft_missing)}' found but not as standalone section",
                "severity": "warning",
                "category": "structure",
            })
    else:
        checks_passed += 1
        categories["structure"]["passed"] += 1

    # 3. Section order check
    total_checks += 1
    categories["structure"]["total"] += 1
    if section_order and structured_json.get("sections"):
        current_sections = [sec.get("heading", "").lower().strip() for sec in structured_json.get("sections", [])]
        current_sections = [re.sub(r"^\d+\.?\s*", "", s) for s in current_sections if s]

        order_correct = True
        last_idx = -1
        for ordered in section_order:
            ordered_lower = ordered.lower().strip()
            for i, current in enumerate(current_sections):
                if _sections_match(ordered, {current}):
                    if i < last_idx:
                        order_correct = False
                        break
                    last_idx = i
                    break

        if order_correct:
            checks_passed += 1
            categories["structure"]["passed"] += 1
        else:
            warnings.append({
                "type": "section_order",
                "message": "Section order does not match journal requirements",
                "severity": "warning",
                "category": "structure",
            })
            categories["structure"]["passed"] += 0.5
            checks_passed += 0.5
    else:
        checks_passed += 1
        categories["structure"]["passed"] += 1

    # 4. Title check
    total_checks += 1
    categories["metadata"]["total"] += 1
    title = structured_json.get("title", "")
    if not title:
        violations.append({
            "type": "missing_title",
            "message": "Manuscript title is missing",
            "severity": "error",
            "category": "metadata",
        })
    else:
        checks_passed += 1
        categories["metadata"]["passed"] += 1
        if len(title.split()) > 20:
            warnings.append({
                "type": "long_title",
                "message": f"Title may be too long: {len(title.split())} words",
                "severity": "warning",
                "category": "metadata",
            })

    # 5. References check
    total_checks += 1
    categories["citations"]["total"] += 1
    references = structured_json.get("references", [])
    max_refs = journal_rules.get("max_references")

    if not references:
        violations.append({
            "type": "missing_references",
            "message": "No references found",
            "severity": "error",
            "category": "citations",
        })
    else:
        checks_passed += 1
        categories["citations"]["passed"] += 1
        if max_refs and len(references) > max_refs:
            warnings.append({
                "type": "too_many_references",
                "message": f"References exceed recommended limit: {len(references)}/{max_refs}",
                "severity": "warning",
                "category": "citations",
            })

    # 6. Citation-reference consistency
    total_checks += 1
    categories["citations"]["total"] += 1
    raw_text = structured_json.get("raw_text", "")
    all_content = " ".join([sec.get("content", "") for sec in structured_json.get("sections", [])])
    full_text = raw_text or all_content

    cited_numbers = set()
    for match in re.finditer(r"\[(\d+)\]", full_text):
        num = int(match.group(1))
        if num <= 100:
            cited_numbers.add(num)
    for match in re.finditer(r"\((\d{1,2})\)", full_text):
        cited_numbers.add(int(match.group(1)))

    if cited_numbers and references:
        uncited = []
        for i in range(1, len(references) + 1):
            if i not in cited_numbers:
                uncited.append(i)

        missing_refs = [n for n in cited_numbers if n > len(references)]

        if missing_refs and len(missing_refs) > len(cited_numbers) * 0.3:
            violations.append({
                "type": "citation_reference_mismatch",
                "message": f"In-text citations reference non-existent entries: {sorted(missing_refs)[:10]}",
                "severity": "error",
                "category": "citations",
            })
        elif missing_refs:
            warnings.append({
                "type": "citation_reference_mismatch",
                "message": f"Some citations may not match references: {sorted(missing_refs)[:5]}",
                "severity": "warning",
                "category": "citations",
            })
            checks_passed += 1
            categories["citations"]["passed"] += 1

        if uncited:
            warnings.append({
                "type": "uncited_references",
                "message": f"References not cited in text: {uncited}",
                "severity": "warning",
                "category": "citations",
            })
    else:
        checks_passed += 1
        categories["citations"]["passed"] += 1

    # 7. Figure numbering
    total_checks += 1
    categories["formatting"]["total"] += 1
    figures = structured_json.get("figures", [])
    if figures:
        fig_numbers = []
        for fig in figures:
            fig_match = re.search(r"(?:Figure|Fig\.?)\s+(\d+)", fig, re.IGNORECASE)
            if fig_match:
                fig_numbers.append(int(fig_match.group(1)))

        if fig_numbers:
            fig_numbers = sorted(set(fig_numbers))
            expected = list(range(1, max(fig_numbers) + 1))
            missing_figs = [n for n in expected if n not in fig_numbers]
            if missing_figs and len(missing_figs) > len(fig_numbers):
                warnings.append({
                    "type": "figure_numbering_gap",
                    "message": f"Significant gaps in figure numbering. Missing: Figure {missing_figs}",
                    "severity": "warning",
                    "category": "formatting",
                })
            else:
                checks_passed += 1
                categories["formatting"]["passed"] += 1
        else:
            checks_passed += 1
            categories["formatting"]["passed"] += 1
    else:
        checks_passed += 1
        categories["formatting"]["passed"] += 1

    # 8. Table numbering
    total_checks += 1
    categories["formatting"]["total"] += 1
    tables = structured_json.get("tables", [])
    if tables:
        table_numbers = []
        for tbl in tables:
            tbl_match = re.search(r"Table\s+(\d+)", tbl, re.IGNORECASE)
            if tbl_match:
                table_numbers.append(int(tbl_match.group(1)))

        if table_numbers:
            expected = list(range(1, max(table_numbers) + 1))
            missing_tbls = [n for n in expected if n not in table_numbers]
            if missing_tbls:
                warnings.append({
                    "type": "table_numbering_gap",
                    "message": f"Gaps in table numbering. Missing: Table {missing_tbls}",
                    "severity": "warning",
                    "category": "formatting",
                })
            else:
                checks_passed += 1
                categories["formatting"]["passed"] += 1
        else:
            checks_passed += 1
            categories["formatting"]["passed"] += 1
    else:
        checks_passed += 1
        categories["formatting"]["passed"] += 1

    # 9. Keywords check
    total_checks += 1
    categories["metadata"]["total"] += 1
    if journal_rules.get("keywords_required", False):
        keywords = structured_json.get("keywords", [])
        if not keywords:
            warnings.append({
                "type": "missing_keywords",
                "message": "Keywords are required but not found",
                "severity": "warning",
                "category": "metadata",
            })
        else:
            checks_passed += 1
            categories["metadata"]["passed"] += 1
    else:
        checks_passed += 1
        categories["metadata"]["passed"] += 1

    # 10. Content structure quality
    total_checks += 1
    categories["content"]["total"] += 1
    sections = structured_json.get("sections", [])
    empty_sections = []
    for sec in sections:
        if not sec.get("content", "").strip():
            empty_sections.append(sec.get("heading", "Unknown"))

    if empty_sections:
        warnings.append({
            "type": "empty_sections",
            "message": f"Sections with no content: {', '.join(empty_sections)}",
            "severity": "warning",
            "category": "content",
        })
    else:
        checks_passed += 1
        categories["content"]["passed"] += 1

    # 11. Authors check
    total_checks += 1
    categories["metadata"]["total"] += 1
    authors = structured_json.get("authors", [])
    if not authors:
        warnings.append({
            "type": "missing_authors",
            "message": "No authors detected in manuscript",
            "severity": "warning",
            "category": "metadata",
        })
    else:
        checks_passed += 1
        categories["metadata"]["passed"] += 1

    # 12. Page limit check (formatting)
    total_checks += 1
    categories["formatting"]["total"] += 1
    page_limit = journal_rules.get("page_limit")
    if page_limit:
        total_words = sum(word_count(sec.get("content", "")) for sec in sections)
        total_words += word_count(abstract)
        # Rough estimate: ~300 words/page single column, ~500 words/page double column
        cols = journal_rules.get("columns", 1)
        words_per_page = 500 if cols == 2 else 300
        estimated_pages = max(1, total_words // words_per_page)

        if estimated_pages > page_limit:
            warnings.append({
                "type": "page_limit_exceeded",
                "message": f"Estimated {estimated_pages} pages exceeds limit of {page_limit} pages",
                "severity": "warning",
                "category": "formatting",
            })
        else:
            checks_passed += 1
            categories["formatting"]["passed"] += 1
    else:
        checks_passed += 1
        categories["formatting"]["passed"] += 1

    # ──── NEW CHECKS (13-21) ──────────────────────────────────────

    # 13. Reference format consistency check
    total_checks += 1
    categories["citations"]["total"] += 1
    if references:
        citation_style = journal_rules.get("citation_style", "")
        bracketed = sum(1 for r in references if r.strip().startswith("["))
        parenthetical = sum(1 for r in references if r.strip().startswith("("))
        numbered = sum(1 for r in references if re.match(r"^\d+\.", r.strip()))

        # Check if the majority use the same style
        styles = [bracketed, parenthetical, numbered]
        dominant = max(styles)
        total_refs = len(references)
        if total_refs > 0 and dominant / total_refs < 0.7:
            warnings.append({
                "type": "reference_format_inconsistent",
                "message": "References use inconsistent formatting styles",
                "severity": "warning",
                "category": "citations",
            })
        else:
            checks_passed += 1
            categories["citations"]["passed"] += 1
    else:
        checks_passed += 1
        categories["citations"]["passed"] += 1

    # 14. In-text citation style check
    total_checks += 1
    categories["citations"]["total"] += 1
    target_citation_style = journal_rules.get("citation_style", "")
    if target_citation_style and full_text:
        bracket_cites = len(re.findall(r"\[\d+\]", full_text))
        paren_cites = len(re.findall(r"\(\d+\)", full_text))
        author_date_cites = len(re.findall(r"\([A-Z][a-z]+(?:\s(?:et al\.?)?)?,\s\d{4}\)", full_text))

        if target_citation_style in ("ieee", "elsevier", "springer"):
            # Should use [N] style
            if paren_cites > bracket_cites and bracket_cites < 3:
                warnings.append({
                    "type": "wrong_citation_style",
                    "message": f"Expected [N] bracket citations for {target_citation_style} style, found mostly parenthetical",
                    "severity": "warning",
                    "category": "citations",
                })
            else:
                checks_passed += 1
                categories["citations"]["passed"] += 1
        elif target_citation_style in ("apa", "harvard"):
            # Should use (Author, Year) style
            if bracket_cites > author_date_cites and author_date_cites < 3:
                warnings.append({
                    "type": "wrong_citation_style",
                    "message": f"Expected (Author, Year) citations for {target_citation_style} style, found mostly numbered",
                    "severity": "warning",
                    "category": "citations",
                })
            else:
                checks_passed += 1
                categories["citations"]["passed"] += 1
        else:
            checks_passed += 1
            categories["citations"]["passed"] += 1
    else:
        checks_passed += 1
        categories["citations"]["passed"] += 1

    # 15. Figure/Table cross-reference check
    total_checks += 1
    categories["formatting"]["total"] += 1
    if full_text:
        text_fig_refs = set(int(m) for m in re.findall(r"(?:Figure|Fig\.?)\s+(\d+)", full_text, re.IGNORECASE))
        text_table_refs = set(int(m) for m in re.findall(r"Table\s+(\d+)", full_text, re.IGNORECASE))

        extracted_figs = structured_json.get("extracted_images", [])
        extracted_tables = structured_json.get("extracted_tables", [])
        fig_count = len(extracted_figs) if extracted_figs else 0
        table_count = len(extracted_tables) if extracted_tables else 0

        missing_fig_refs = [n for n in text_fig_refs if n > fig_count] if fig_count > 0 else []
        missing_table_refs = [n for n in text_table_refs if n > table_count] if table_count > 0 else []

        if missing_fig_refs or missing_table_refs:
            items = []
            if missing_fig_refs:
                items.append(f"Figure(s) {missing_fig_refs}")
            if missing_table_refs:
                items.append(f"Table(s) {missing_table_refs}")
            warnings.append({
                "type": "missing_cross_references",
                "message": f"Text references non-existent: {', '.join(items)}",
                "severity": "warning",
                "category": "formatting",
            })
        else:
            checks_passed += 1
            categories["formatting"]["passed"] += 1
    else:
        checks_passed += 1
        categories["formatting"]["passed"] += 1

    # 16. Title word limit check
    total_checks += 1
    categories["metadata"]["total"] += 1
    title_word_limit = journal_rules.get("title_word_limit", 25)
    if title:
        title_words = len(title.split())
        if title_words > title_word_limit:
            warnings.append({
                "type": "title_too_long",
                "message": f"Title has {title_words} words, recommended max is {title_word_limit}",
                "severity": "warning",
                "category": "metadata",
            })
        else:
            checks_passed += 1
            categories["metadata"]["passed"] += 1
    else:
        checks_passed += 1
        categories["metadata"]["passed"] += 1

    # 17. Section word count check (min content per section)
    total_checks += 1
    categories["content"]["total"] += 1
    thin_sections = []
    for sec in sections:
        section_words = word_count(sec.get("content", ""))
        heading = sec.get("heading", "").lower()
        min_words = 50
        if heading in ("introduction", "methods", "results", "discussion"):
            min_words = 100  # Major sections need more content
        if section_words < min_words and section_words > 0:
            thin_sections.append(f"{sec.get('heading', 'Unknown')} ({section_words} words)")

    if thin_sections:
        warnings.append({
            "type": "thin_sections",
            "message": f"Sections with minimal content: {', '.join(thin_sections[:5])}",
            "severity": "warning",
            "category": "content",
        })
    else:
        checks_passed += 1
        categories["content"]["passed"] += 1

    # 18. Data availability statement check
    total_checks += 1
    categories["structure"]["total"] += 1
    requires_data_availability = journal_rules.get("requires_data_availability", False)
    if requires_data_availability:
        has_data_statement = any(
            "data availability" in sec.get("heading", "").lower()
            for sec in sections
        )
        if not has_data_statement:
            da_in_text = "data availability" in full_text.lower() or "data are available" in full_text.lower()
            if not da_in_text:
                warnings.append({
                    "type": "missing_data_availability",
                    "message": "Data Availability Statement is required but not found",
                    "severity": "warning",
                    "category": "structure",
                })
            else:
                checks_passed += 1
                categories["structure"]["passed"] += 1
        else:
            checks_passed += 1
            categories["structure"]["passed"] += 1
    else:
        checks_passed += 1
        categories["structure"]["passed"] += 1

    # 19. Abbreviation first-use check (sample check)
    total_checks += 1
    categories["content"]["total"] += 1
    abbr_pattern = re.findall(r"\b([A-Z]{2,6})\b", full_text)
    common_abbrs = {"IEEE", "ACM", "DOI", "URL", "API", "DNA", "RNA", "HIV", "USA", "UK", "AI", "ML", "NLP",
                    "CPU", "GPU", "RAM", "PDF", "HTML", "CSS", "JSON", "XML", "SQL", "HTTP", "HTTPS", "PhD"}
    custom_abbrs = set(a for a in abbr_pattern if a not in common_abbrs and len(a) >= 3)
    undefined_abbrs = []
    for abbr in list(custom_abbrs)[:10]:
        # Check if the abbreviation is defined somewhere (word in parentheses)
        define_pattern = f"({abbr})" if f"({abbr})" in full_text else None
        if not define_pattern:
            undefined_abbrs.append(abbr)

    if undefined_abbrs and len(undefined_abbrs) > 3:
        warnings.append({
            "type": "undefined_abbreviations",
            "message": f"Abbreviations used without definition: {', '.join(undefined_abbrs[:5])}",
            "severity": "warning",
            "category": "content",
        })
    else:
        checks_passed += 1
        categories["content"]["passed"] += 1

    # 20. CrossRef DOI coverage check (if reference validation data exists)
    total_checks += 1
    categories["citations"]["total"] += 1
    # This relies on the reference_validation data from the pipeline
    # We check if references have DOIs (a proxy for quality)
    if references:
        doi_count = sum(1 for r in references if re.search(r"10\.\d{4,}/", str(r)))
        doi_ratio = doi_count / len(references) if references else 0
        if doi_ratio < 0.3 and len(references) > 5:
            warnings.append({
                "type": "low_doi_coverage",
                "message": f"Only {doi_count}/{len(references)} references ({int(doi_ratio*100)}%) have DOIs",
                "severity": "warning",
                "category": "citations",
            })
        else:
            checks_passed += 1
            categories["citations"]["passed"] += 1
    else:
        checks_passed += 1
        categories["citations"]["passed"] += 1

    # 21. Overall manuscript word count check
    total_checks += 1
    categories["content"]["total"] += 1
    total_word_count = sum(word_count(sec.get("content", "")) for sec in sections)
    total_word_count += word_count(abstract)
    max_word_count = journal_rules.get("max_word_count", 10000)
    min_word_count = journal_rules.get("min_word_count", 1000)

    if total_word_count < min_word_count and total_word_count > 0:
        warnings.append({
            "type": "manuscript_too_short",
            "message": f"Manuscript has {total_word_count} words, minimum recommended is {min_word_count}",
            "severity": "warning",
            "category": "content",
        })
    elif total_word_count > max_word_count:
        warnings.append({
            "type": "manuscript_too_long",
            "message": f"Manuscript has {total_word_count} words, maximum is {max_word_count}",
            "severity": "warning",
            "category": "content",
        })
    else:
        checks_passed += 1
        categories["content"]["passed"] += 1

    # Calculate score
    checks_passed = int(checks_passed) if isinstance(checks_passed, float) else checks_passed
    base_score = int((checks_passed / total_checks) * 100) if total_checks > 0 else 0

    # Penalty
    violation_penalty = len(violations) * 8
    warning_penalty = len(warnings) * 1

    # Bonus
    bonus = 0
    if structured_json.get("title"):
        bonus += 2
    if structured_json.get("authors"):
        bonus += 1
    if structured_json.get("keywords"):
        bonus += 1
    if len(structured_json.get("references", [])) >= 5:
        bonus += 1

    score = min(100, max(0, base_score - violation_penalty - warning_penalty + bonus))

    # Build category breakdown
    category_scores = {}
    for key, cat in categories.items():
        if cat["total"] > 0:
            cat_score = int((cat["passed"] / cat["total"]) * 100)
        else:
            cat_score = 100
        category_scores[key] = {
            "label": cat["label"],
            "score": cat_score,
            "passed": int(cat["passed"]) if isinstance(cat["passed"], float) else cat["passed"],
            "total": cat["total"],
        }

    return {
        "score": score,
        "total_checks": total_checks,
        "checks_passed": checks_passed,
        "violations": violations,
        "warnings": warnings,
        "categories": category_scores,
        "summary": _generate_summary(score, violations, warnings),
        "journal_name": journal_rules.get("journal_name", journal_rules.get("family_name", "Unknown")),
    }


def _generate_summary(score: int, violations: list, warnings: list) -> str:
    """Generate a human-readable compliance summary."""
    if score >= 90:
        grade = "Excellent"
        message = "Your manuscript is well-formatted and largely compliant."
    elif score >= 70:
        grade = "Good"
        message = "Your manuscript has minor issues that should be addressed."
    elif score >= 50:
        grade = "Fair"
        message = "Your manuscript has several issues that need attention."
    else:
        grade = "Needs Improvement"
        message = "Your manuscript requires significant formatting changes."

    summary = f"{grade} ({score}/100): {message}"
    if violations:
        summary += f" Found {len(violations)} violation(s)."
    if warnings:
        summary += f" Found {len(warnings)} warning(s)."

    return summary
