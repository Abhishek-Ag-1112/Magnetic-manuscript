"""
Accessibility & Inclusive Language Checker.
Analyzes the manuscript for inclusive academic language and WCAG accessibility principles
(e.g., ensuring figures have descriptive captions/alt-text, checking reading level).
"""
import logging
import json
import re

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

import os
GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")

ACCESSIBILITY_PROMPT = """You are an expert academic editor specializing in DEI (Diversity, Equity, and Inclusion) and digital accessibility (WCAG).
Analyze the following manuscript excerpts and provide an accessibility report.

INSTRUCTIONS:
1. Identify any non-inclusive language (e.g., "mankind" -> "humanity", "whitelist" -> "allowlist", gendered pronouns where neutral could apply).
2. Check if the text references Figures/Tables without providing adequate descriptive context (which would fail alt-text principles).
3. Evaluate the general readability and cognitive accessibility of the text.
4. Provide specific, actionable suggestions.
5. Do NOT rewrite the text natively, just return an analysis report.

Return ONLY valid JSON in this exact format:
{{
  "overall_score": 85,
  "inclusive_language_issues": [
    {{"original": "mankind", "suggestion": "humanity", "context": "the history of mankind..."}}
  ],
  "accessibility_warnings": [
    "Figure 1 is mentioned but lacks a descriptive caption summary in the text."
  ],
  "readability_feedback": "The text uses overly complex nested sentences in the Methodology section."
}}

MANUSCRIPT PREVIEW (First ~3000 chars):
{text_preview}
"""

def analyze_accessibility(structured: dict) -> dict:
    """
    Analyzes manuscript structured content for accessibility and inclusive language.
    """
    try:
        # Extract plain text preview
        text_parts = []
        if structured.get("abstract"):
            text_parts.append(structured["abstract"])
            
        for sec in structured.get("sections", []):
            text_parts.append(sec.get("content", ""))
            
        full_text = " ".join(text_parts)
        text_preview = full_text[:3000]
        
        if not text_preview.strip():
            return {
                "overall_score": 100,
                "inclusive_language_issues": [],
                "accessibility_warnings": ["No text provided for analysis."],
                "readability_feedback": ""
            }

        llm = ChatGroq(model=GROQ_MODEL, temperature=0.0, max_tokens=1024)
        
        response = llm.invoke([
            SystemMessage(content="You are an accessibility and inclusive language analyzer. Return ONLY JSON."),
            HumanMessage(content=ACCESSIBILITY_PROMPT.format(text_preview=text_preview))
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
        logger.error(f"Accessibility Agent failed: {str(e)}")
        return {
            "overall_score": 0,
            "inclusive_language_issues": [],
            "accessibility_warnings": [f"Analysis failed: {str(e)}"],
            "readability_feedback": "Error analyzing readability."
        }
