"""
Journal Recommender Agent — AI-powered journal matchmaking.
Analyzes manuscript content and recommends the best-fit journals.
"""
import logging
import json

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from utils.helpers import list_available_journals, list_available_families

logger = logging.getLogger(__name__)


RECOMMENDATION_PROMPT = """You are an expert academic publishing advisor. Based on the manuscript details below, recommend the TOP 3 most suitable journals from the available options.

**Manuscript Title:** {title}

**Abstract:** {abstract}

**Keywords:** {keywords}

**Section Headings:** {section_headings}

**Number of References:** {ref_count}

**Available Journals:**
{available_journals}

For each recommendation, provide:
1. journal_id - the exact ID from the available list
2. journal_name - the full name
3. match_score - a score from 0-100
4. reason - a 2-3 sentence explanation of why this journal is a good fit
5. considerations - any caveats or things to be aware of

Return ONLY a valid JSON array of 3 objects:
[
  {{"journal_id": "...", "journal_name": "...", "match_score": 90, "reason": "...", "considerations": "..."}},
  ...
]
"""


def journal_recommender_agent(manuscript_data: dict) -> dict:
    """
    Recommend the best journals for a manuscript based on content analysis.

    Args:
        manuscript_data: Dict with title, abstract, keywords, sections, references

    Returns:
        Dict with recommendations list and analysis metadata
    """
    try:
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=2000,
        )

        # Gather manuscript info
        title = manuscript_data.get("title", "Untitled")
        abstract = manuscript_data.get("abstract", "")
        keywords = manuscript_data.get("keywords", [])
        sections = manuscript_data.get("sections", [])
        references = manuscript_data.get("references", [])

        section_headings = [s.get("heading", "") for s in sections if s.get("heading")]

        # Get available journals
        journals = list_available_journals()
        families = list_available_families()

        journal_list = "\n".join([
            f"- {j['id']}: {j['name']} (family: {j['family']}, citation: {j['citation_style']})"
            for j in journals
        ])

        family_list = "\n".join([
            f"- {f['id']}: {f['name']} ({f.get('description', '')})"
            for f in families
        ])

        available_info = f"**Journals:**\n{journal_list}\n\n**Style Families:**\n{family_list}"

        prompt = RECOMMENDATION_PROMPT.format(
            title=title,
            abstract=abstract[:500],
            keywords=", ".join(keywords) if isinstance(keywords, list) else str(keywords),
            section_headings=", ".join(section_headings),
            ref_count=len(references),
            available_journals=available_info,
        )

        response = llm.invoke([
            SystemMessage(content=(
                "You are an expert academic publishing advisor. "
                "You help researchers find the best journals for their manuscripts. "
                "Return ONLY valid JSON."
            )),
            HumanMessage(content=prompt),
        ])

        content = response.content.strip()
        # Extract JSON from response
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        recommendations = json.loads(content)

        # Validate recommendations
        valid_ids = {j["id"] for j in journals}
        validated = []
        for rec in recommendations[:3]:
            if rec.get("journal_id") in valid_ids:
                validated.append(rec)
            else:
                # Try to find closest match
                for j in journals:
                    if rec.get("journal_name", "").lower() in j["name"].lower():
                        rec["journal_id"] = j["id"]
                        validated.append(rec)
                        break

        return {
            "recommendations": validated,
            "total_journals_analyzed": len(journals),
            "manuscript_title": title,
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Journal recommendation failed: {str(e)}")
        return {
            "recommendations": [],
            "error": str(e),
            "status": "error",
        }
