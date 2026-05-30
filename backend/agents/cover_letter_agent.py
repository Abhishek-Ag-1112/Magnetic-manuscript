"""
Cover Letter Agent — Generates professional journal submission cover letters.
"""
import logging
import json

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


COVER_LETTER_PROMPT = """Generate a professional cover letter for submitting the following manuscript to {journal_name}.

**Manuscript Title:** {title}

**Authors:** {authors}

**Abstract:** {abstract}

**Key Findings / Novelty:**
Based on the abstract and sections listed below, identify the top 3 novel contributions:
{section_summaries}

**Journal Name:** {journal_name}

Write a formal, professional cover letter that:
1. Addresses the "Editor-in-Chief" of {journal_name}
2. States the manuscript title and that it is being submitted for consideration
3. Briefly describes the research (2-3 sentences)
4. Highlights 2-3 key novel contributions and why they matter
5. States why this journal is the right venue for this work
6. Confirms the manuscript is original and not under consideration elsewhere
7. Lists all authors and confirms their agreement
8. Ends with a professional closing

The letter should be approximately 300-400 words, formal but not overly stiff.
Return ONLY the cover letter text, no JSON or markdown code blocks.
"""


def cover_letter_agent(manuscript_data: dict, journal_name: str) -> dict:
    """
    Generate a professional cover letter for journal submission.

    Args:
        manuscript_data: Dict with title, abstract, authors, sections
        journal_name: Target journal name

    Returns:
        Dict with cover letter text and metadata
    """
    try:
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=2000,
        )

        title = manuscript_data.get("title", "Untitled Manuscript")
        abstract = manuscript_data.get("abstract", "")
        authors = manuscript_data.get("authors", [])
        sections = manuscript_data.get("sections", [])

        # Build section summaries for context
        section_summaries = []
        for sec in sections[:6]:
            heading = sec.get("heading", "")
            content = sec.get("content", "")[:200]
            if heading and content:
                section_summaries.append(f"- {heading}: {content}...")

        authors_text = ", ".join(authors) if isinstance(authors, list) else str(authors)
        if not authors_text:
            authors_text = "[Author names]"

        prompt = COVER_LETTER_PROMPT.format(
            journal_name=journal_name,
            title=title,
            authors=authors_text,
            abstract=abstract[:600],
            section_summaries="\n".join(section_summaries) if section_summaries else "Not available",
        )

        response = llm.invoke([
            SystemMessage(content=(
                "You are a senior academic researcher writing a cover letter "
                "for a journal submission. Write in a formal, professional tone. "
                "Return ONLY the cover letter text."
            )),
            HumanMessage(content=prompt),
        ])

        cover_letter = response.content.strip()

        # Clean up any markdown formatting
        if cover_letter.startswith("```"):
            lines = cover_letter.split("\n")
            cover_letter = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return {
            "cover_letter": cover_letter,
            "journal_name": journal_name,
            "manuscript_title": title,
            "word_count": len(cover_letter.split()),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Cover letter generation failed: {str(e)}")
        return {
            "cover_letter": "",
            "error": str(e),
            "status": "error",
        }
