"""
Plagiarism Detection Agent — Checks manuscript for originality issues.
Uses n-gram fingerprinting for self-plagiarism detection and
LLM for advanced analysis of potentially copied patterns.
"""
import os
import re
import json
import logging
import hashlib
from collections import Counter
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")


PLAGIARISM_ANALYSIS_PROMPT = """You are an academic plagiarism and originality expert analyzing a research manuscript.

Analyze the following manuscript excerpt for potential originality issues:

Title: {title}
Abstract: {abstract}

Section samples:
{section_samples}

ANALYZE FOR:
1. **Self-plagiarism patterns**: Repeated passages, duplicated sentences across sections
2. **Writing style consistency**: Does the writing style change dramatically between sections (which may indicate copy-paste from different sources)?
3. **Citation integrity**: Are claims made without proper attribution? Are there passages that read like textbook definitions that should be cited?
4. **Unusual phrasing**: Are there phrases that seem overly generic or "template-like" that are commonly found in many papers?
5. **Overall originality assessment**: Rate the manuscript's originality

Return ONLY valid JSON:
{{
  "originality_score": <0-100>,
  "self_plagiarism_flags": [
    {{"text": "repeated passage", "locations": ["Section A", "Section B"], "severity": "low|medium|high"}}
  ],
  "style_inconsistencies": [
    {{"description": "style change noted", "severity": "low|medium|high"}}
  ],
  "uncited_claims": [
    {{"text": "claim without citation", "severity": "low|medium|high"}}
  ],
  "overall_assessment": "brief summary of originality analysis"
}}"""


def plagiarism_agent(state: dict) -> dict:
    """
    Check manuscript for plagiarism and originality issues.
    Combines n-gram fingerprinting with LLM analysis.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        if not structured:
            errors.append("No structured content for plagiarism check")
            return {**state, "errors": errors, "current_step": "plagiarism_failed"}

        sections = structured.get("sections", [])
        abstract = structured.get("abstract", "")
        title = structured.get("title", "")
        raw_text = structured.get("raw_text", "")

        # Collect all text
        all_text = abstract + "\n"
        for sec in sections:
            all_text += sec.get("content", "") + "\n"

        if len(all_text.strip()) < 100:
            # Too short to analyze
            return {
                **state,
                "plagiarism_report": {
                    "originality_score": 100,
                    "status": "skipped",
                    "message": "Document too short for meaningful analysis",
                    "self_plagiarism": [],
                    "style_issues": [],
                    "uncited_claims": [],
                },
                "current_step": "plagiarism_complete",
                "errors": errors,
            }

        # Step 1: N-gram fingerprinting for self-plagiarism
        self_plag_results = _check_self_plagiarism(sections, abstract)

        # Step 2: Sentence-level duplicate detection
        duplicates = _find_duplicate_sentences(all_text)

        # Step 3: LLM originality analysis
        llm_analysis = _llm_originality_check(title, abstract, sections)

        # Combine results
        originality_score = 100
        all_flags = []

        # Penalize for self-plagiarism (but gently — academic papers have normal overlap)
        if self_plag_results:
            for flag in self_plag_results:
                if flag["severity"] == "high":
                    originality_score -= 6
                elif flag["severity"] == "medium":
                    originality_score -= 3
                else:
                    originality_score -= 1
            all_flags.extend(self_plag_results)

        # Penalize for duplicates (minor — some repetition is normal)
        if duplicates:
            dup_penalty = min(len(duplicates) * 2, 10)
            originality_score -= dup_penalty

        # Incorporate LLM analysis
        if llm_analysis:
            llm_score = llm_analysis.get("originality_score", 100)
            # Weight: 60% our analysis, 40% LLM analysis
            originality_score = int(originality_score * 0.6 + llm_score * 0.4)

        originality_score = max(0, min(100, originality_score))

        plagiarism_report = {
            "originality_score": originality_score,
            "status": "complete",
            "self_plagiarism": all_flags,
            "duplicate_sentences": duplicates[:5],  # Top 5
            "style_issues": llm_analysis.get("style_inconsistencies", []) if llm_analysis else [],
            "uncited_claims": llm_analysis.get("uncited_claims", []) if llm_analysis else [],
            "overall_assessment": llm_analysis.get("overall_assessment", "") if llm_analysis else "",
            "summary": _generate_plagiarism_summary(originality_score),
        }

        logger.info(f"Plagiarism check complete. Originality: {originality_score}/100")

        return {
            **state,
            "plagiarism_report": plagiarism_report,
            "current_step": "plagiarism_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Plagiarism check failed: {str(e)}")
        errors.append(f"Plagiarism check error: {str(e)}")
        return {
            **state,
            "plagiarism_report": {
                "originality_score": -1,
                "status": "error",
                "message": str(e),
            },
            "current_step": "plagiarism_failed",
            "errors": errors,
        }


def _check_self_plagiarism(sections: list, abstract: str) -> list:
    """Check for repeated passages between sections using n-gram fingerprinting."""
    flags = []
    section_texts = {}

    if abstract:
        section_texts["Abstract"] = abstract

    for sec in sections:
        heading = sec.get("heading", "Unknown")
        content = sec.get("content", "")
        if content.strip():
            section_texts[heading] = content

    # Generate 5-gram fingerprints for each section
    section_ngrams = {}
    for name, text in section_texts.items():
        ngrams = _generate_ngrams(text, n=5)
        section_ngrams[name] = set(ngrams)

    # Pairs that naturally overlap in academic papers — don't flag these
    expected_overlap_pairs = {
        frozenset({"abstract", "introduction"}),
        frozenset({"abstract", "conclusion"}),
        frozenset({"abstract", "conclusions"}),
        frozenset({"abstract", "discussion"}),
        frozenset({"introduction", "conclusion"}),
        frozenset({"introduction", "conclusions"}),
        frozenset({"results", "discussion"}),
        frozenset({"results", "results and discussion"}),
    }

    # Compare each pair of sections
    names = list(section_ngrams.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            ngrams_a = section_ngrams[name_a]
            ngrams_b = section_ngrams[name_b]

            if not ngrams_a or not ngrams_b:
                continue

            # Skip expected overlap pairs (Abstract/Intro, Abstract/Conclusion, etc.)
            pair_key = frozenset({name_a.lower().strip(), name_b.lower().strip()})
            if pair_key in expected_overlap_pairs:
                continue

            overlap = ngrams_a & ngrams_b
            overlap_ratio = len(overlap) / min(len(ngrams_a), len(ngrams_b))

            if overlap_ratio > 0.4:
                severity = "high" if overlap_ratio > 0.6 else "medium"
                sample = list(overlap)[:1]
                sample_text = " ".join(sample[0]) if sample else ""
                flags.append({
                    "text": f"Significant overlap ({overlap_ratio:.0%}) between sections",
                    "sample": sample_text,
                    "locations": [name_a, name_b],
                    "severity": severity,
                    "overlap_ratio": round(overlap_ratio, 2),
                })
            elif overlap_ratio > 0.25:
                flags.append({
                    "text": f"Minor overlap ({overlap_ratio:.0%}) between sections",
                    "locations": [name_a, name_b],
                    "severity": "low",
                    "overlap_ratio": round(overlap_ratio, 2),
                })

    return flags


def _find_duplicate_sentences(text: str) -> list:
    """Find duplicate or near-duplicate sentences in the text."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.split()) > 8]

    # Find exact or near-duplicates
    seen = {}
    duplicates = []

    for sent in sentences:
        # Normalize: lowercase and remove extra whitespace
        normalized = re.sub(r'\s+', ' ', sent.lower().strip())
        # Create a fingerprint (first 100 chars)
        fingerprint = normalized[:100]

        if fingerprint in seen:
            duplicates.append({
                "sentence": sent[:120] + "..." if len(sent) > 120 else sent,
                "count": 2,
            })
        else:
            seen[fingerprint] = sent

    return duplicates


def _generate_ngrams(text: str, n: int = 5) -> list:
    """Generate word n-grams from text."""
    words = re.findall(r'\w+', text.lower())
    if len(words) < n:
        return []
    return [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]


def _llm_originality_check(title: str, abstract: str, sections: list) -> dict:
    """Use LLM to analyze originality and detect potential plagiarism patterns."""
    try:
        # Prepare section samples (first 300 chars of each)
        section_samples = []
        for sec in sections[:5]:  # Max 5 sections
            heading = sec.get("heading", "")
            content = sec.get("content", "")[:400]
            section_samples.append(f"[{heading}]: {content}...")

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=2048)

        response = llm.invoke([
            SystemMessage(content="You are an academic originality expert. Return ONLY valid JSON."),
            HumanMessage(content=PLAGIARISM_ANALYSIS_PROMPT.format(
                title=title,
                abstract=abstract[:500],
                section_samples="\n\n".join(section_samples),
            )),
        ])

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1]

        result = json.loads(content.strip())
        return result

    except Exception as e:
        logger.warning(f"LLM originality check failed: {e}")
        return None


def _generate_plagiarism_summary(score: int) -> str:
    """Generate a human-readable plagiarism summary."""
    if score >= 90:
        return f"Excellent originality ({score}/100). The manuscript appears to be highly original."
    elif score >= 75:
        return f"Good originality ({score}/100). Minor overlaps detected — likely acceptable."
    elif score >= 60:
        return f"Fair originality ({score}/100). Some passages may need revision or additional citations."
    else:
        return f"Low originality ({score}/100). Significant concerns detected — recommend thorough review."
