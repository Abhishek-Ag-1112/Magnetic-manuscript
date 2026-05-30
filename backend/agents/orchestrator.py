"""
LangGraph Orchestrator — Wires all agents into a stateful multi-agent workflow.
Implements: Parse → Normalize → Load Rules → Rewrite → Convert Citations → Validate References → Format → Validate → Plagiarism
With retry logic for formatting failures and SSE event streaming support.
"""
import logging
import time
import json
from typing import Literal, Generator

from langgraph.graph import StateGraph, END

from utils.state import ManuscriptState
from agents.parsing_agent import parsing_agent
from agents.normalization_agent import normalization_agent
from agents.journal_loader_agent import journal_loader_agent
from agents.citation_agent import citation_agent
from agents.formatting_agent import formatting_agent
from agents.validation_agent import validation_agent
from agents.plagiarism_agent import plagiarism_agent
from agents.rewrite_agent import rewrite_agent
from agents.reference_validation_agent import reference_validation_agent

logger = logging.getLogger(__name__)


# ─── Agent display metadata for SSE ───
AGENT_META = {
    "parse": {
        "label": "Parsing Document",
        "description": "Extracting text, tables, and structure from your manuscript...",
        "icon": "FileSearch",
    },
    "normalize": {
        "label": "Normalizing Structure",
        "description": "Standardizing section names and hierarchy for the target journal...",
        "icon": "Layers",
    },
    "load_rules": {
        "label": "Loading Journal Rules",
        "description": "Applying journal-specific formatting and submission requirements...",
        "icon": "BookOpen",
    },
    "rewrite": {
        "label": "Rewriting for Journal Style",
        "description": "Adapting writing style, tone, and structure for the target journal...",
        "icon": "PenTool",
    },
    "convert_citations": {
        "label": "Converting Citations",
        "description": "Transforming citations and bibliography to the target style...",
        "icon": "Quote",
    },
    "validate_references": {
        "label": "Verifying References via CrossRef",
        "description": "Validating DOIs and verifying references against the CrossRef database...",
        "icon": "Database",
    },
    "format": {
        "label": "Formatting Layout",
        "description": "Generating publish-ready DOCX with proper margins, fonts, and layout...",
        "icon": "Layout",
    },
    "validate": {
        "label": "Validating Compliance",
        "description": "Checking against journal submission requirements and scoring compliance...",
        "icon": "ShieldCheck",
    },
    "check_plagiarism": {
        "label": "Checking Originality",
        "description": "Analyzing manuscript for self-plagiarism and originality issues...",
        "icon": "Fingerprint",
    },
}


def should_continue_after_validation(state: dict) -> Literal["retry_rewrite", "retry_normalize", "retry_format", "end"]:
    """Smart retry: route to the specific agent that can fix the violation."""
    current_step = state.get("current_step", "")

    if current_step.startswith("needs_reprocess"):
        retry_count = state.get("retry_count", 0)
        if retry_count < 3:
            # Extract which agent to route to from the step name
            if "rewrite" in current_step:
                logger.info(f"Smart retry → rewrite_agent (attempt {retry_count})")
                return "retry_rewrite"
            elif "normalize" in current_step:
                logger.info(f"Smart retry → normalization_agent (attempt {retry_count})")
                return "retry_normalize"
            elif "convert_citations" in current_step:
                logger.info(f"Smart retry → citation_agent (attempt {retry_count})")
                return "retry_format"  # citations flow through format
            else:
                logger.info(f"Smart retry → format_agent (attempt {retry_count})")
                return "retry_format"

    return "end"


def should_continue_after_parsing(state: dict) -> Literal["continue", "error"]:
    """Decide whether parsing was successful."""
    current_step = state.get("current_step", "")
    if current_step == "parsing_failed":
        return "error"
    return "continue"


def error_handler(state: dict) -> dict:
    """Handle errors in the pipeline."""
    errors = state.get("errors", [])
    logger.error(f"Pipeline error: {errors}")
    return {
        **state,
        "current_step": "error",
        "compliance_report": {
            "score": 0,
            "violations": [{"type": "pipeline_error", "message": str(errors), "severity": "error"}],
            "warnings": [],
            "summary": f"Processing failed with errors: {'; '.join(errors)}",
        },
    }


def build_manuscript_graph() -> StateGraph:
    """Build the LangGraph workflow for manuscript processing."""

    # Create the graph
    workflow = StateGraph(ManuscriptState)

    # Add nodes
    workflow.add_node("parse", parsing_agent)
    workflow.add_node("normalize", normalization_agent)
    workflow.add_node("load_rules", journal_loader_agent)
    workflow.add_node("rewrite", rewrite_agent)
    workflow.add_node("convert_citations", citation_agent)
    workflow.add_node("validate_references", reference_validation_agent)
    workflow.add_node("format", formatting_agent)
    workflow.add_node("validate", validation_agent)
    workflow.add_node("check_plagiarism", plagiarism_agent)
    workflow.add_node("error_handler", error_handler)

    # Set entry point
    workflow.set_entry_point("parse")

    # Add edges
    workflow.add_conditional_edges(
        "parse",
        should_continue_after_parsing,
        {
            "continue": "normalize",
            "error": "error_handler",
        },
    )

    workflow.add_edge("normalize", "load_rules")
    workflow.add_edge("load_rules", "rewrite")
    workflow.add_edge("rewrite", "convert_citations")
    workflow.add_edge("convert_citations", "validate_references")
    workflow.add_edge("validate_references", "format")
    workflow.add_edge("format", "validate")
    workflow.add_edge("validate", "check_plagiarism")

    # Smart conditional edges after plagiarism check (routes to specific agent or finishes)
    workflow.add_conditional_edges(
        "check_plagiarism",
        should_continue_after_validation,
        {
            "retry_rewrite": "rewrite",
            "retry_normalize": "normalize",
            "retry_format": "format",
            "end": END,
        },
    )

    workflow.add_edge("error_handler", END)

    return workflow


def create_manuscript_pipeline():
    """Create and compile the manuscript processing pipeline."""
    workflow = build_manuscript_graph()
    app = workflow.compile()
    return app


def run_pipeline(
    file_path: str,
    journal_name: str = "",
    family_name: str = "",
    session_id: str = "",
) -> dict:
    """
    Run the complete manuscript processing pipeline.

    Args:
        file_path: Path to the uploaded manuscript file
        journal_name: Specific journal name (e.g., 'nature')
        family_name: Format family name (e.g., 'nature_style')
        session_id: Unique session identifier

    Returns:
        Final state with formatted document paths and compliance report
    """
    pipeline = create_manuscript_pipeline()

    initial_state = ManuscriptState(
        raw_input_path=file_path,
        file_type="",
        parsed_text="",
        structured_json={},
        selected_journal=journal_name,
        selected_family=family_name,
        journal_rules={},
        citation_style="",
        formatted_structure={},
        formatted_doc_path="",
        formatted_pdf_path="",
        formatted_latex_path="",
        compliance_report={},
        plagiarism_report={},
        original_content={},
        reference_validation={},
        errors=[],
        current_step="start",
        retry_count=0,
    )

    # Add session_id to state
    initial_state["session_id"] = session_id

    logger.info(f"Starting pipeline for session {session_id}")
    logger.info(f"File: {file_path}")
    logger.info(f"Journal: {journal_name}, Family: {family_name}")

    # Run the pipeline
    final_state = None
    for step in pipeline.stream(initial_state):
        node_name = list(step.keys())[0]
        node_state = step[node_name]
        current_step = node_state.get("current_step", "")
        logger.info(f"[{node_name}] Step: {current_step}")
        final_state = node_state

    if final_state is None:
        return {
            "errors": ["Pipeline produced no output"],
            "compliance_report": {
                "score": 0,
                "violations": [],
                "warnings": [],
                "summary": "Pipeline failed to produce output",
            },
        }

    return final_state


def run_pipeline_ws(
    file_path: str,
    journal_name: str = "",
    family_name: str = "",
    session_id: str = "",
) -> Generator[dict, None, dict]:
    """
    Run the pipeline for WebSocket streaming.
    Yields dictionary payloads for each agent step.
    """
    pipeline = create_manuscript_pipeline()

    initial_state = ManuscriptState(
        raw_input_path=file_path,
        file_type="",
        parsed_text="",
        structured_json={},
        selected_journal=journal_name,
        selected_family=family_name,
        journal_rules={},
        citation_style="",
        formatted_structure={},
        formatted_doc_path="",
        formatted_pdf_path="",
        formatted_latex_path="",
        compliance_report={},
        plagiarism_report={},
        original_content={},
        reference_validation={},
        errors=[],
        current_step="start",
        retry_count=0,
    )

    initial_state["session_id"] = session_id

    # Emit pipeline start event
    yield {
        "type": "pipeline_start",
        "data": {
            "session_id": session_id,
            "total_agents": len(AGENT_META),
            "agents": list(AGENT_META.keys()),
        }
    }

    final_state = None
    agent_index = 0
    start_time = time.time()
    
    first_node = "parse"
    meta = AGENT_META.get(first_node)
    yield {
        "type": "agent_start",
        "data": {
            "agent": first_node,
            "index": agent_index,
            "label": meta["label"],
            "description": meta["description"],
            "icon": meta["icon"],
        }
    }

    for step in pipeline.stream(initial_state):
        node_name = list(step.keys())[0]
        node_state = step[node_name]
        current_step_name = node_state.get("current_step", "")

        meta = AGENT_META.get(node_name)
        if not meta:
            continue

        elapsed = round(time.time() - start_time, 2)

        details = {"step": current_step_name}
        if node_name == "parse":
            details["file_type"] = node_state.get("file_type", "")
            details["text_length"] = len(node_state.get("parsed_text", ""))
        elif node_name == "normalize":
            sections = node_state.get("structured_json", {}).get("sections", [])
            details["sections_found"] = len(sections)
            details["section_names"] = [s.get("heading", "") for s in sections]
        elif node_name == "load_rules":
            rules = node_state.get("journal_rules", {})
            details["journal"] = rules.get("journal_name", rules.get("family_name", ""))
            details["citation_style"] = rules.get("citation_style", "")
        elif node_name == "rewrite":
            sections = node_state.get("structured_json", {}).get("sections", [])
            details["sections_rewritten"] = len(sections)
        elif node_name == "convert_citations":
            details["citation_style"] = node_state.get("citation_style", "")
            refs = node_state.get("structured_json", {}).get("references", [])
            details["references_converted"] = len(refs)
        elif node_name == "validate_references":
            ref_val = node_state.get("reference_validation", {})
            details["total_references"] = ref_val.get("total", 0)
            details["verified"] = ref_val.get("validated", 0)
            details["dois_found"] = ref_val.get("doi_found", 0)
            details["dois_missing"] = ref_val.get("doi_missing", 0)
        elif node_name == "format":
            details["docx_path"] = node_state.get("formatted_doc_path", "")
            details["latex_path"] = node_state.get("formatted_latex_path", "")
        elif node_name == "validate":
            report = node_state.get("compliance_report", {})
            details["score"] = report.get("score", 0)
            details["violations"] = len(report.get("violations", []))
            details["warnings"] = len(report.get("warnings", []))
        elif node_name == "check_plagiarism":
            plag = node_state.get("plagiarism_report", {})
            details["originality_score"] = plag.get("originality_score", 0)

        yield {
            "type": "agent_complete",
            "data": {
                "agent": node_name,
                "index": agent_index,
                "label": meta["label"],
                "elapsed": elapsed,
                "details": details,
            }
        }

        agent_index += 1
        final_state = node_state

        next_node = None
        if node_name == "parse": next_node = "normalize" if not node_state.get("errors") else None
        elif node_name == "normalize": next_node = "load_rules"
        elif node_name == "load_rules": next_node = "rewrite"
        elif node_name == "rewrite": next_node = "convert_citations"
        elif node_name == "convert_citations": next_node = "format"
        elif node_name == "format": next_node = "validate"
        elif node_name == "validate": next_node = "check_plagiarism"
        elif node_name == "check_plagiarism":
            res = should_continue_after_validation(node_state)
            if res == "reprocess": next_node = "format"

        if next_node and next_node in AGENT_META:
            next_meta = AGENT_META[next_node]
            start_time = time.time()
            yield {
                "type": "agent_start",
                "data": {
                    "agent": next_node,
                    "index": agent_index,
                    "label": next_meta["label"],
                    "description": next_meta["description"],
                    "icon": next_meta["icon"],
                }
            }

    if final_state is None:
        final_state = {
            "errors": ["Pipeline produced no output"],
            "compliance_report": {
                "score": 0, "violations": [], "warnings": [],
                "summary": "Pipeline failed to produce output"
            },
        }

    status = "complete" if not final_state.get("errors") else "error"
    yield {
        "type": "pipeline_complete",
        "data": {"session_id": session_id, "status": status}
    }

    result_data = _extract_result(final_state, session_id)
    yield {
        "type": "result",
        "data": result_data
    }


def _extract_result(state: dict, session_id: str) -> dict:
    """Extract the result payload from the final pipeline state."""
    compliance_report = state.get("compliance_report", {})
    plagiarism_report = state.get("plagiarism_report", {})
    errors = state.get("errors", [])

    result = {
        "session_id": session_id,
        "status": "complete" if not errors else "error",
        "compliance_report": compliance_report,
        "plagiarism_report": plagiarism_report,
        "errors": errors,
    }

    if state.get("formatted_doc_path"):
        result["docx_download_url"] = f"/api/download/{session_id}/docx"
    if state.get("formatted_pdf_path"):
        result["pdf_download_url"] = f"/api/download/{session_id}/pdf"
    if state.get("formatted_latex_path"):
        result["latex_download_url"] = f"/api/download/{session_id}/latex"

    # Add original vs formatted for before/after comparison
    original = state.get("original_content", {})
    formatted = state.get("structured_json", {})
    if original and formatted:
        result["comparison"] = {
            "original": {
                "title": original.get("title", ""),
                "abstract": original.get("abstract", ""),
                "sections": [
                    {"heading": s.get("heading", ""), "content": s.get("content", "")[:500]}
                    for s in original.get("sections", [])
                ],
            },
            "formatted": {
                "title": formatted.get("title", ""),
                "abstract": formatted.get("abstract", ""),
                "sections": [
                    {"heading": s.get("heading", ""), "content": s.get("content", "")[:500]}
                    for s in formatted.get("sections", [])
                ],
            },
        }

    return result


def _sse_event(event_type: str, data: dict) -> str:
    """Format an SSE event string."""
    json_data = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {json_data}\n\n"
