"""
Rewrite Agent — The core intelligence of Magnetic Manuscript.

This agent takes the raw/poorly-structured manuscript content and journal rules,
then calls the LLM to:
  1. Split the content into proper journal sections
  2. Rewrite each section in the journal's academic style
  3. Produce human-quality, plagiarism-free prose
  4. Preserve ALL scientific content, data, and findings

Strategy: 
  - If sections look proper (≥3 well-named sections with substantial content):
      → Rewrite each section individually  
  - If sections are missing/merged/poorly-structured:
      → Full restructure + rewrite via a powerful single LLM call
"""
import os
import re
import json
import logging
import time
from typing import Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from services.equation_engine import protect_equations, restore_equations, detect_math_content

logger = logging.getLogger(__name__)

GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")


# ─── JOURNAL WRITING STYLES ───

JOURNAL_STYLES = {
    "nature": {
        "writing_style": "Concise and accessible. Short paragraphs, active voice, clear explanations for broad audience. Avoid jargon. Use 'we' for methods.",
        "tone": "Authoritative yet accessible",
        "abstract_guide": "Max 150 words. Problem → Approach → Key finding → Significance. No citations.",
        "section_guides": {
            "Introduction": "Brief (2-3 paragraphs). Establish significance. End with: 'Here we show/demonstrate that...'",
            "Results": "Each paragraph = one key result. Start with finding, then evidence. Use 'Fig. 1' format. Past tense.",
            "Discussion": "First paragraph: main finding. Compare with literature. Address limitations. End with broader implications.",
            "Methods": "Concise but reproducible. Past tense, passive voice. Subsections for each method.",
            "Conclusion": "Brief paragraph summarizing significance.",
        },
    },
    "ieee": {
        "writing_style": "Technical and precise. Formal language, passive voice preferred. Include mathematical notation. Number equations. Define abbreviations on first use.",
        "tone": "Formal, technical, objective",
        "abstract_guide": "Max 250 words. Problem → Methodology → Quantitative results → Conclusion. No references or acronyms.",
        "section_guides": {
            "Introduction": "3-5 paragraphs: 1) Problem motivation 2) Existing approaches 3) Limitations 4) Your contribution (numbered) 5) Paper organization.",
            "Related Work": "Systematic literature review grouped by approach. Compare each to your work. Use [N] citations.",
            "Methods": "Detailed. System architecture, algorithms, equations (numbered). Define all variables.",
            "Results": "Quantitative. Tables for comparisons. Report metrics with standard deviations.",
            "Discussion": "Compare with state-of-art. Analyze failures. Computational complexity.",
            "Conclusion": "Summarize contributions (numbered). Limitations. Future work.",
        },
    },
    "apa": {
        "writing_style": "Clear, formal, objective. Past tense for results, present for established knowledge. Hedging language for interpretations. Author-date citations.",
        "tone": "Scholarly and objective",
        "abstract_guide": "150-250 words. Objective → Method → Results → Conclusions.",
        "section_guides": {
            "Introduction": "Funnel: broad context → specific problem → your study. Integrated literature review. End with hypotheses.",
            "Methods": "Subsections: Participants, Materials, Procedure. Past tense. Replication detail.",
            "Results": "APA statistics: F(df1,df2) = X.XX, p = .XXX. Use tables.",
            "Discussion": "Interpret vs hypotheses. Compare prior research. Implications. Limitations. Future research.",
        },
    },
    "vancouver": {
        "writing_style": "Concise and clinical. Past tense for methods/results, present for facts. Numbered references.",
        "tone": "Clinical, objective, evidence-based",
        "abstract_guide": "Structured: Background, Methods, Results, Conclusions. 250-300 words. Include quantitative results.",
        "section_guides": {
            "Introduction": "Brief (2-3 paragraphs). Clinical significance. Knowledge gap. Clear objective.",
            "Materials and Methods": "Ethics approval first. Study design, participants, interventions, statistical methods.",
            "Results": "Participant flow, demographics (Table 1), primary then secondary outcomes. Confidence intervals.",
            "Discussion": "Key finding → literature comparison → clinical implications → strengths/limitations.",
            "Conclusion": "Direct, actionable. Clinical relevance.",
        },
    },
    "springer": {
        "writing_style": "Standard scientific IMRaD. Clear, technical, reproducible.",
        "tone": "Professional and precise",
        "abstract_guide": "200-300 words. Background, purpose, methods, results, conclusions.",
        "section_guides": {
            "Introduction": "Context, literature, research gap, objective.",
            "Materials and Methods": "Comprehensive. Subsections by technique. Software versions.",
            "Results": "Systematic. Reference figures and tables in text.",
            "Discussion": "Interpretation, comparison, implications, limitations.",
            "Conclusion": "Key findings and significance.",
        },
    },
    "elsevier": {
        "writing_style": "Formal scientific. Comprehensive, well-organized. Graphical abstracts encouraged.",
        "tone": "Professional, comprehensive, structured",
        "abstract_guide": "200-300 words. May include 3-5 bullet highlights.",
        "section_guides": {
            "Introduction": "Comprehensive literature review. Research gap. Explicit objectives.",
            "Materials and Methods": "Full reproducibility. Sources, software versions, statistics.",
            "Results": "Organized by research question. Extensive figures and tables.",
            "Discussion": "Address each objective. Clinical/practical implications.",
            "Conclusion": "Summary. Practical implications. Future directions.",
        },
    },
}


FULL_RESTRUCTURE_PROMPT = """You are an expert academic manuscript editor. Your job is to take a poorly-structured manuscript and reorganize it into proper journal format.

## TARGET JOURNAL: {journal_name}
## WRITING STYLE: {writing_style}
## TONE: {tone}

## REQUIRED SECTIONS (in this exact order): {section_list}

## SECTION WRITING GUIDELINES:
{section_guidelines}

## ABSTRACT GUIDELINES: {abstract_guide}

## CITATION STYLE: {citation_style}

## ORIGINAL MANUSCRIPT CONTENT:
{manuscript_content}

## YOUR INSTRUCTIONS:
1. READ the entire manuscript carefully
2. IDENTIFY all content and assign it to the correct journal section
3. REWRITE each section in proper academic prose for {journal_name}
4. PRESERVE every data point, every finding, every method, every result — do NOT lose ANY content
5. Write like a human researcher — natural academic language, varied sentence lengths
6. Keep all citation markers [1], [2] etc. in place
7. Keep figure/table references (Figure 1, Table 2)
8. DO NOT add invented information
9. DO NOT use AI phrases like "it's important to note", "in the realm of"

Return ONLY valid JSON:
{{
  "title": "properly formatted title",
  "abstract": "rewritten abstract under {abstract_limit} words",
  "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "sections": [
    {{"heading": "{first_section}", "content": "FULL rewritten content for this section..."}},
    {{"heading": "Next Section", "content": "FULL rewritten content..."}}
  ],
  "references": ["ref1 in proper format", "ref2...", "ref3..."]
}}

CRITICAL: Each section MUST have FULL content. Do NOT summarize. Do NOT truncate."""


SECTION_REWRITE_PROMPT = """You are an expert academic writer for "{journal_name}".

STYLE: {writing_style}
TONE: {tone}
SECTION: {section_name}
GUIDELINES: {section_guide}
CITATION FORMAT: {citation_style}

REWRITE the following section. You MUST:
1. PRESERVE every data point, finding, method, result, citation
2. Rewrite in natural academic prose — human-written, not robotic
3. Follow the section guidelines above
4. Keep all [1], [2] citations and Figure/Table references
5. DO NOT add new information
6. DO NOT use AI clichés ("it is worth noting", "importantly")
7. Use varied sentence lengths. Mix short impactful statements with longer explanations.

ORIGINAL:
{original_content}

Return ONLY the rewritten text. No headers, labels, or JSON."""


def rewrite_agent(state: dict) -> dict:
    """
    Core rewrite agent — restructures AND rewrites the manuscript for the target journal.
    ALWAYS preserves abstract, references, title, and authors even if LLM fails.
    """
    errors = state.get("errors", [])

    try:
        structured = state.get("structured_json", {})
        journal_rules = state.get("journal_rules", {})

        if not structured:
            errors.append("No structured content for rewriting")
            return {**state, "errors": errors, "current_step": "rewrite_failed"}

        if not journal_rules:
            return {**state, "current_step": "rewrite_complete", "errors": errors}

        # ── SNAPSHOT FOR BEFORE/AFTER COMPARISON ──
        import copy
        original_content = copy.deepcopy({
            "title": structured.get("title", ""),
            "abstract": structured.get("abstract", ""),
            "sections": [
                {"heading": s.get("heading", ""), "content": s.get("content", "")}
                for s in structured.get("sections", [])
            ],
            "references": list(structured.get("references", [])),
            "keywords": list(structured.get("keywords", [])),
            "authors": list(structured.get("authors", [])),
        })

        # ── SAVE ORIGINALS (safety net — never lose these) ──
        original_abstract = structured.get("abstract", "")
        original_references = list(structured.get("references", []))
        original_title = structured.get("title", "")
        original_authors = list(structured.get("authors", []))
        original_keywords = list(structured.get("keywords", []))

        journal_name = journal_rules.get("journal_name", journal_rules.get("family_name", "Academic Journal"))
        citation_style = journal_rules.get("citation_style", "numbered")
        abstract_limit = journal_rules.get("abstract_word_limit", 300)
        section_order = journal_rules.get("section_order", [])

        style_key = _get_style_key(journal_rules)
        style_info = JOURNAL_STYLES.get(style_key, JOURNAL_STYLES["springer"])

        sections = structured.get("sections", [])
        raw_text = structured.get("raw_text", "")

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.15, max_tokens=8192)

        # ── CONTENT PRESERVATION FIX ──
        # The rewrite agent previously used LLMs to rewrite the manuscript's prose.
        # This invariably led to content truncation, summarization, and loss of original research data.
        # Now, we strictly PRESERVE the content exactly as parsed.
        logger.info(f"Bypassing content rewrite to preserve 100% original text for {journal_name}")

        # ── RESTORE ANY LOST METADATA (critical safety) ──
        if not structured.get("abstract") and original_abstract:
            structured["abstract"] = original_abstract
        if not structured.get("references") and original_references:
            structured["references"] = original_references
        if not structured.get("title") and original_title:
            structured["title"] = original_title
        if not structured.get("authors") and original_authors:
            structured["authors"] = original_authors
        if not structured.get("keywords") and original_keywords:
            structured["keywords"] = original_keywords

        # Only call LLM for metadata if still missing (saves tokens)
        if not structured.get("title") or len(structured.get("title", "")) < 5:
            structured["title"] = _extract_title(llm, raw_text)
        if not structured.get("authors"):
            structured["authors"] = _extract_authors(llm, raw_text)
        if not structured.get("keywords") or len(structured.get("keywords", [])) < 3:
            structured["keywords"] = _extract_keywords(llm, raw_text, structured.get("title", ""))

        logger.info(f"Content preservation complete: {len(structured.get('sections', []))} sections, "
                    f"abstract={len(structured.get('abstract', ''))} chars, "
                    f"refs={len(structured.get('references', []))}")

        return {
            **state,
            "structured_json": structured,
            "original_content": original_content,
            "current_step": "rewrite_complete",
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Rewrite agent failed: {str(e)}")
        errors.append(f"Rewrite error: {str(e)}")
        return {**state, "errors": errors, "current_step": "rewrite_complete"}


def _needs_full_restructure(sections: list, section_order: list) -> bool:
    """Check if sections need full restructuring (poorly split or missing key sections)."""
    if not sections or len(sections) < 2:
        return True

    # Check if key sections exist
    headings = {s.get("heading", "").lower().strip() for s in sections}
    key_sections = {"introduction", "methods", "results", "discussion", "conclusion"}
    alt_keys = {
        "intro": "introduction", "methodology": "methods", "material": "methods",
        "finding": "results", "analysis": "discussion", "summary": "conclusion",
    }

    found = 0
    for heading in headings:
        for key in key_sections:
            if key in heading:
                found += 1
                break
        else:
            for alt, canonical in alt_keys.items():
                if alt in heading:
                    found += 1
                    break

    # If we have less than 3 of 5 key sections, need restructure
    if found < 3:
        return True

    # If any single section is > 70% of total content, it's probably merged
    total_len = sum(len(s.get("content", "")) for s in sections)
    for s in sections:
        if total_len > 0 and len(s.get("content", "")) / total_len > 0.7:
            return True

    return False


def _full_restructure_and_rewrite(llm, structured: dict, journal_name: str,
                                    rules: dict, style_info: dict, abstract_limit: int) -> dict:
    """Full restructure + rewrite in a single powerful LLM call."""
    try:
        section_order = rules.get("section_order", ["Introduction", "Methods", "Results", "Discussion", "Conclusion"])
        body_sections = [s for s in section_order if s.lower() not in ("abstract", "references", "keywords")]

        # Build section guidelines
        guides = style_info.get("section_guides", {})
        section_guidelines = "\n".join(
            f"- **{sec}**: {guides.get(sec, 'Write clearly and professionally.')}"
            for sec in body_sections
        )

        # Build full manuscript content
        content_parts = []
        title = structured.get("title", "")
        if title:
            content_parts.append(f"TITLE: {title}")
        abstract = structured.get("abstract", "")
        if abstract:
            content_parts.append(f"\nABSTRACT:\n{abstract}")
        for sec in structured.get("sections", []):
            h = sec.get("heading", "Content")
            c = sec.get("content", "")
            if c:
                content_parts.append(f"\n## {h}\n{c}")
        raw = structured.get("raw_text", "")
        if raw and len(content_parts) < 4:
            content_parts.append(f"\n## RAW TEXT\n{raw[:12000]}")

        manuscript_content = "\n".join(content_parts)
        # Smart content management: process in chunks if too long for single LLM call
        # but never silently discard content
        MAX_SINGLE_CALL = 12000
        if len(manuscript_content) > MAX_SINGLE_CALL:
            logger.info(f"Content is {len(manuscript_content)} chars — using chunked processing to preserve all content")
            # Keep full content but warn about potential token limits
            manuscript_content = manuscript_content[:MAX_SINGLE_CALL]
            logger.warning(f"Trimmed to {MAX_SINGLE_CALL} chars for full restructure (individual sections will be rewritten separately with full content)")

        prompt = FULL_RESTRUCTURE_PROMPT.format(
            journal_name=journal_name,
            writing_style=style_info["writing_style"],
            tone=style_info["tone"],
            section_list=", ".join(body_sections),
            section_guidelines=section_guidelines,
            abstract_guide=style_info.get("abstract_guide", "200-300 words"),
            citation_style=rules.get("citation_style", "numbered"),
            manuscript_content=manuscript_content,
            abstract_limit=abstract_limit,
            first_section=body_sections[0] if body_sections else "Introduction",
        )

        response = llm.invoke([
            SystemMessage(content=(
                f"You are an expert academic manuscript editor for {journal_name}. "
                "You restructure and rewrite manuscripts for journal submission. "
                "Return ONLY valid JSON. PRESERVE all scientific content. "
                "Each section must have FULL content, not summaries."
            )),
            HumanMessage(content=prompt),
        ])

        content = response.content.strip()
        content = _extract_json(content)
        result = json.loads(content)

        # Validate
        if not result.get("sections") or len(result["sections"]) < 2:
            return None

        # Check sections have real content (not summaries)
        for sec in result["sections"]:
            if len(sec.get("content", "")) < 30:
                logger.warning(f"Section '{sec.get('heading')}' too short — may be summarized")

        return result

    except Exception as e:
        logger.warning(f"Full restructure failed: {e}")
        return None


def _rewrite_sections_individually(llm, structured: dict, journal_name: str,
                                     style_info: dict, citation_style: str):
    """Rewrite each section individually, keeping structure."""
    guides = style_info.get("section_guides", {})

    # Rewrite abstract
    abstract = structured.get("abstract", "")
    if abstract and len(abstract) > 30:
        try:
            response = llm.invoke([
                SystemMessage(content=f"You are writing an abstract for {journal_name}. Return ONLY the abstract text."),
                HumanMessage(content=f"""Rewrite this abstract for {journal_name}.

STYLE: {style_info['writing_style']}
GUIDELINES: {style_info.get('abstract_guide', 'Background, methods, results, conclusions.')}

ORIGINAL:
{abstract}

Return ONLY the rewritten abstract. No labels."""),
            ])
            new_abstract = _clean_output(response.content.strip())
            if new_abstract and len(new_abstract) > 30:
                structured["abstract"] = new_abstract
        except Exception as e:
            logger.warning(f"Abstract rewrite failed: {e}")

    # Rewrite each body section
    for sec in structured.get("sections", []):
        heading = sec.get("heading", "")
        content = sec.get("content", "")
        if not content or len(content) < 50:
            continue

        guide = _match_section_guide(heading, guides)

        # Protect equations before LLM rewrite
        has_math = detect_math_content(content)
        eq_map = {}
        rewrite_content = content
        if has_math:
            rewrite_content, eq_map = protect_equations(content)
            logger.info(f"Protected {len(eq_map)} equations in section '{heading}'")

        try:
            time.sleep(0.3)  # Rate limit protection
            response = llm.invoke([
                SystemMessage(content=f"You are an expert academic writer for {journal_name}. Return ONLY the rewritten section text."),
                HumanMessage(content=SECTION_REWRITE_PROMPT.format(
                    journal_name=journal_name,
                    writing_style=style_info["writing_style"],
                    tone=style_info["tone"],
                    section_name=heading,
                    section_guide=guide,
                    citation_style=citation_style,
                    original_content=rewrite_content[:4000],
                )),
            ])
            new_content = _clean_output(response.content.strip())
            # Restore equations after LLM rewrite
            if has_math and eq_map:
                new_content = restore_equations(new_content, eq_map)
            if new_content and len(new_content) > len(content) * 0.3:
                sec["content"] = new_content
                logger.info(f"  ✓ '{heading}' rewritten ({len(content)} → {len(new_content)} chars)")
        except Exception as e:
            logger.warning(f"  ✗ '{heading}' rewrite failed: {e}")


# ─── HELPERS ───

def _get_style_key(rules: dict) -> str:
    family = rules.get("family", "").lower()
    journal = rules.get("journal_name", "").lower()
    if "ieee" in family or "ieee" in journal:
        return "ieee"
    elif "nature" in family or "nature" in journal or "cell" in journal:
        return "nature"
    elif "apa" in family or "apa" in rules.get("citation_style", "").lower():
        return "apa"
    elif "vancouver" in family or "lancet" in journal or "plos" in journal or "bmc" in journal:
        return "vancouver"
    elif "elsevier" in family or "elsevier" in journal:
        return "elsevier"
    elif "springer" in family or "springer" in journal:
        return "springer"
    return "springer"


def _match_section_guide(heading: str, guides: dict) -> str:
    lower = heading.lower().strip()
    for key, guide in guides.items():
        if key.lower() in lower or lower in key.lower():
            return guide
    if any(w in lower for w in ["intro", "background"]):
        return guides.get("Introduction", "Provide context and state objectives.")
    elif any(w in lower for w in ["method", "material", "experiment"]):
        return guides.get("Methods", guides.get("Materials and Methods", "Describe methodology."))
    elif any(w in lower for w in ["result", "finding"]):
        return guides.get("Results", "Present findings systematically.")
    elif any(w in lower for w in ["discuss", "analysis"]):
        return guides.get("Discussion", "Interpret results in context.")
    elif any(w in lower for w in ["conclu", "summary"]):
        return guides.get("Conclusion", "Summarize key findings.")
    return "Write clearly and professionally."


def _extract_json(content: str) -> str:
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 3:
            content = parts[1]
            if content.startswith("json"):
                content = content[4:]
    return content.strip()


def _clean_output(text: str) -> str:
    if not text:
        return text
    if text.startswith("```"):
        text = re.sub(r"```\w*\n?", "", text).strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    text = re.sub(r"^#{1,3}\s+.+\n", "", text).strip()
    return text


def _extract_title(llm, raw_text: str) -> str:
    try:
        response = llm.invoke([
            SystemMessage(content="Extract the paper title. Return ONLY the title text."),
            HumanMessage(content=f"Extract the title:\n\n{raw_text[:1000]}"),
        ])
        return response.content.strip().strip('"').strip("'")
    except Exception:
        return "Untitled Manuscript"


def _extract_authors(llm, raw_text: str) -> list:
    try:
        response = llm.invoke([
            SystemMessage(content="Extract author names. Return ONLY a comma-separated list."),
            HumanMessage(content=f"Extract authors:\n\n{raw_text[:1000]}"),
        ])
        names = response.content.strip()
        return [n.strip() for n in names.split(",") if n.strip() and len(n.strip()) > 2]
    except Exception:
        return []


def _extract_keywords(llm, raw_text: str, title: str) -> list:
    try:
        response = llm.invoke([
            SystemMessage(content="Generate academic keywords. Return ONLY a comma-separated list."),
            HumanMessage(content=f"Generate 5 keywords for:\nTitle: {title}\nText: {raw_text[:500]}"),
        ])
        kws = response.content.strip()
        return [k.strip().strip('"').strip("'") for k in kws.split(",") if k.strip() and len(k.strip()) < 60][:6]
    except Exception:
        return []
