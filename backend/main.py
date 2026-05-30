"""
Magnetic Manuscript — FastAPI Backend
AI-powered multi-agent academic manuscript formatting engine.
"""
import os
import re
import json
import logging
import shutil
from pathlib import Path, PurePosixPath
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()

# ── CONFIGURATION ──
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024  # Default 50 MB
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

from utils.helpers import (
    generate_session_id, detect_file_type,
    UPLOAD_DIR, OUTPUT_DIR,
)
from utils.state import ProcessRequest

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Magnetic Manuscript",
    description="AI-powered multi-agent academic manuscript formatting engine",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────
# FILE-BASED SESSION PERSISTENCE
# ──────────────────────────────────────────

def _validate_session_id(session_id: str) -> str:
    """Validate session ID to prevent path traversal attacks."""
    if not session_id or not re.match(r'^[a-zA-Z0-9_-]{1,64}$', session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format.")
    return session_id


def _session_file(session_id: str):
    return OUTPUT_DIR / session_id / "session.json"

def _save_session(session_id: str, data: dict):
    try:
        out_dir = OUTPUT_DIR / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(_session_file(session_id), "w", encoding="utf-8") as f:
            json.dump(data, f, default=str)
    except Exception as e:
        logger.error(f"Failed to save session {session_id}: {e}")

def _load_session(session_id: str) -> dict:
    path = _session_file(session_id)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _session_exists(session_id: str) -> bool:
    return _session_file(session_id).exists()


@app.get("/")
async def root():
    return {"message": "Magnetic Manuscript API", "version": "2.0.0"}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "version": "2.0.0"}


# ──────────────────────────────────────────
# JOURNAL & FAMILY ENDPOINTS
# ──────────────────────────────────────────

@app.get("/api/journals")
async def get_journals():
    """List all available journal configurations."""
    from utils.helpers import list_available_journals
    return list_available_journals()

@app.get("/api/families")
async def get_families():
    """List all available format families."""
    from utils.helpers import list_available_families
    return list_available_families()

@app.get("/api/journals/{journal_id}")
async def get_journal_details(journal_id: str):
    """Get detailed journal configuration."""
    from utils.helpers import load_journal_config
    try:
        return load_journal_config(journal_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Journal '{journal_id}' not found.")

@app.get("/api/families/{family_id}")
async def get_family_details(family_id: str):
    """Get detailed family configuration."""
    from utils.helpers import load_family_config
    try:
        return load_family_config(family_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Family '{family_id}' not found.")


# ──────────────────────────────────────────
# FILE UPLOAD
# ──────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a manuscript file for processing."""
    allowed_types = {"docx", "pdf", "txt", "md", "markdown"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""

    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(allowed_types)}",
        )

    # Sanitize filename to prevent path traversal
    safe_filename = PurePosixPath(file.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    session_id = generate_session_id()
    file_type = detect_file_type(safe_filename)

    # Read file and enforce size limit
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
        )

    # Save uploaded file
    upload_dir = UPLOAD_DIR / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Save session metadata
    _save_session(session_id, {
        "session_id": session_id,
        "file_name": safe_filename,
        "file_path": str(file_path),
        "file_type": file_type,
        "status": "uploaded",
    })

    return {
        "session_id": session_id,
        "file_name": safe_filename,
        "file_type": file_type,
        "message": f"File uploaded successfully. Session: {session_id}",
    }


# ──────────────────────────────────────────
# PROCESSING (Standard + SSE Streaming)
# ──────────────────────────────────────────

@app.post("/api/process")
async def process_manuscript(request: ProcessRequest):
    """Process the uploaded manuscript through the multi-agent pipeline."""
    _validate_session_id(request.session_id)
    session = _load_session(request.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a file first.")

    file_path = session.get("file_path", "")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found.")

    from agents.orchestrator import run_pipeline

    try:
        result = run_pipeline(
            file_path=file_path,
            journal_name=request.journal_name or "",
            family_name=request.family_name or "",
            session_id=request.session_id,
        )

        # Build response
        response = {
            "session_id": request.session_id,
            "status": "complete",
            "compliance_report": result.get("compliance_report", {}),
            "plagiarism_report": result.get("plagiarism_report", {}),
            "errors": result.get("errors", []),
        }

        if result.get("formatted_doc_path"):
            response["docx_download_url"] = f"/api/download/{request.session_id}/docx"
        if result.get("formatted_pdf_path"):
            response["pdf_download_url"] = f"/api/download/{request.session_id}/pdf"
        if result.get("formatted_latex_path"):
            response["latex_download_url"] = f"/api/download/{request.session_id}/latex"

        # Add before/after comparison
        original = result.get("original_content", {})
        formatted = result.get("structured_json", {})
        if original and formatted:
            response["comparison"] = {
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

        # Update session
        _save_session(request.session_id, {**session, "status": "complete", **response})

        return response

    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


from fastapi import WebSocket, WebSocketDisconnect
import asyncio

import queue
import threading

@app.websocket("/api/process/ws/{session_id}")
async def process_websocket(websocket: WebSocket, session_id: str, journal: str = "", family: str = ""):
    """
    WebSocket endpoint for real-time pipeline execution, 
    running LangGraph in a thread to prevent blocking event loop.
    """
    await websocket.accept()

    # Validate session_id (can't use HTTPException in WS, send error event instead)
    if not session_id or not re.match(r'^[a-zA-Z0-9_-]{1,64}$', session_id):
        await websocket.send_json({"type": "error", "data": {"error": "Invalid session ID format."}})
        await websocket.close()
        return

    session = _load_session(session_id)

    if not session:
        await websocket.send_json({"type": "error", "data": {"error": "Session not found."}})
        await websocket.close()
        return

    file_path = session.get("file_path", "")
    if not file_path or not Path(file_path).exists():
        await websocket.send_json({"type": "error", "data": {"error": "Uploaded file not found."}})
        await websocket.close()
        return

    def pipeline_worker(q, fp, jn, fn, sid):
        from agents.orchestrator import run_pipeline_ws
        try:
            final_result = None
            for event_dict in run_pipeline_ws(
                file_path=fp,
                journal_name=jn,
                family_name=fn,
                session_id=sid,
            ):
                q.put(event_dict)
                # Capture the result event for session saving
                if event_dict.get("type") == "result":
                    final_result = event_dict.get("data", {})

            # Save session so download endpoints work
            if final_result:
                try:
                    existing = _load_session(sid) or {}
                    out_dir = OUTPUT_DIR / sid

                    # Find output files directly in the output directory
                    docx_path = out_dir / "manuscript.docx"
                    pdf_path = out_dir / "manuscript.pdf"
                    tex_path = out_dir / "manuscript.tex"

                    existing.update({
                        "status": final_result.get("status", "complete"),
                        "formatted_doc_path": str(docx_path) if docx_path.exists() else "",
                        "formatted_pdf_path": str(pdf_path) if pdf_path.exists() else "",
                        "formatted_latex_path": str(tex_path) if tex_path.exists() else "",
                        "compliance_report": final_result.get("compliance_report", {}),
                        "plagiarism_report": final_result.get("plagiarism_report", {}),
                        "errors": final_result.get("errors", []),
                    })

                    # Also store download URLs for status endpoint
                    if docx_path.exists():
                        existing["docx_download_url"] = f"/api/download/{sid}/docx"
                    if pdf_path.exists():
                        existing["pdf_download_url"] = f"/api/download/{sid}/pdf"
                    if tex_path.exists():
                        existing["latex_download_url"] = f"/api/download/{sid}/latex"

                    _save_session(sid, existing)
                    logger.info(f"Saved WebSocket session results for {sid}")
                except Exception as save_err:
                    logger.warning(f"Failed to save WS session: {save_err}")

        except Exception as e:
            logger.error(f"Worker pipeline error: {str(e)}")
            q.put({"type": "error", "data": {"error": str(e)}})
        finally:
            q.put(None)

    q = queue.Queue()
    thread = threading.Thread(
        target=pipeline_worker, 
        args=(q, file_path, journal, family, session_id),
        daemon=True,
    )
    thread.start()

    try:
        while True:
            try:
                event = q.get_nowait()
                if event is None:
                    break
                await websocket.send_json(event)
            except queue.Empty:
                await asyncio.sleep(0.05)
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WS processing failed: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "data": {"error": str(e)}})
        except:
            pass
    finally:
        # Wait for the pipeline thread to finish (timeout 5 min)
        thread.join(timeout=300)
        try:
            await websocket.close()
        except:
            pass


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """Get processing status for a session."""
    _validate_session_id(session_id)
    session = _load_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    status = session.get("status", "unknown")

    response = {
        "session_id": session_id,
        "status": status,
    }

    if status == "complete":
        response["compliance_report"] = session.get("compliance_report", {})
        response["plagiarism_report"] = session.get("plagiarism_report", {})
        if session.get("docx_download_url"):
            response["docx_download_url"] = session["docx_download_url"]
        if session.get("pdf_download_url"):
            response["pdf_download_url"] = session["pdf_download_url"]
        if session.get("latex_download_url"):
            response["latex_download_url"] = session["latex_download_url"]
        if session.get("comparison"):
            response["comparison"] = session["comparison"]

    return response


# ──────────────────────────────────────────
# DOWNLOADS
# ──────────────────────────────────────────

@app.get("/api/download/{session_id}/docx")
async def download_docx(session_id: str):
    """Download the formatted DOCX file."""
    _validate_session_id(session_id)
    docx_path = OUTPUT_DIR / session_id / "manuscript.docx"
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="DOCX file not found.")

    return FileResponse(
        path=str(docx_path),
        filename="manuscript.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

@app.get("/api/download/{session_id}/pdf")
async def download_pdf(session_id: str):
    """Download the formatted PDF file."""
    _validate_session_id(session_id)
    pdf_path = OUTPUT_DIR / session_id / "manuscript.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found. Pandoc may not be installed.")

    return FileResponse(
        path=str(pdf_path),
        filename="manuscript.pdf",
        media_type="application/pdf",
    )

@app.get("/api/download/{session_id}/latex")
async def download_latex(session_id: str):
    """Download the formatted LaTeX file."""
    _validate_session_id(session_id)
    latex_path = OUTPUT_DIR / session_id / "manuscript.tex"
    if not latex_path.exists():
        raise HTTPException(status_code=404, detail="LaTeX file not found.")

    return FileResponse(
        path=str(latex_path),
        filename="manuscript.tex",
        media_type="application/x-latex",
    )

@app.get("/api/download/{session_id}/report")
async def download_report(session_id: str):
    """Download the compliance report as JSON."""
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    report = session.get("compliance_report", {})
    return report


# ──────────────────────────────────────────
# WOW FEATURES — ADVANCED ENDPOINTS
# ──────────────────────────────────────────

@app.post("/api/reroute")
async def reroute_journal(session_id: str, journal_name: str = "", family_name: str = ""):
    """
    One-Click Multi-Journal Reroute.
    Reuses existing parsed/structured content, skips parsing,
    and reformats for a different journal in seconds.
    """
    import threading

    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Process a manuscript first.")

    structured = session.get("structured_json")
    if not structured:
        raise HTTPException(status_code=400, detail="No structured content found. Process the manuscript first.")

    if not journal_name and not family_name:
        raise HTTPException(status_code=400, detail="Specify either journal_name or family_name for rerouting.")

    # Import reroute pipeline (skips parse step)
    from agents.orchestrator import create_manuscript_pipeline
    from utils.state import ManuscriptState

    logger.info(f"Rerouting session {session_id} to journal: {journal_name or family_name}")

    # Build state with existing structured content
    reroute_state = ManuscriptState(
        raw_input_path=session.get("raw_input_path", ""),
        file_type=session.get("file_type", ""),
        parsed_text=session.get("parsed_text", ""),
        structured_json=structured,
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
        remediation_instructions=[],
        errors=[],
        current_step="normalize_start",
        retry_count=0,
    )
    reroute_state["session_id"] = session_id

    def run_reroute():
        try:
            pipeline = create_manuscript_pipeline()
            final_state = None
            for step in pipeline.stream(reroute_state):
                node_name = list(step.keys())[0]
                node_state = step[node_name]
                final_state = node_state

            if final_state:
                _save_session(session_id, {
                    **session,
                    "rerouted_journal": journal_name or family_name,
                    "structured_json": final_state.get("structured_json", structured),
                    "formatted_doc_path": final_state.get("formatted_doc_path", ""),
                    "formatted_pdf_path": final_state.get("formatted_pdf_path", ""),
                    "formatted_latex_path": final_state.get("formatted_latex_path", ""),
                    "compliance_report": final_state.get("compliance_report", {}),
                    "plagiarism_report": final_state.get("plagiarism_report", {}),
                    "reference_validation": final_state.get("reference_validation", {}),
                })
        except Exception as e:
            logger.error(f"Reroute failed: {e}")

    thread = threading.Thread(target=run_reroute)
    thread.start()

    return {
        "session_id": session_id,
        "status": "rerouting",
        "target_journal": journal_name or family_name,
        "message": f"Rerouting manuscript to {journal_name or family_name}. Check /api/status/{session_id} for progress.",
    }


@app.get("/api/recommend-journal/{session_id}")
async def recommend_journal(session_id: str):
    """
    AI-Powered Journal Matchmaker.
    Analyzes the manuscript and recommends the best 3 journals.
    """
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json")
    if not structured:
        raise HTTPException(status_code=400, detail="No structured content. Process manuscript first.")

    from agents.journal_recommender_agent import journal_recommender_agent

    result = journal_recommender_agent(structured)

    # Save recommendations to session
    session["journal_recommendations"] = result.get("recommendations", [])
    _save_session(session_id, session)

    return result


@app.post("/api/generate-cover-letter/{session_id}")
async def generate_cover_letter(session_id: str, journal_name: str = ""):
    """
    Auto Cover Letter Generator.
    Generates a professional submission cover letter for the target journal.
    """
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json")
    if not structured:
        raise HTTPException(status_code=400, detail="No structured content. Process manuscript first.")

    if not journal_name:
        journal_name = session.get("selected_journal", session.get("selected_family", "the journal"))

    from agents.cover_letter_agent import cover_letter_agent

    result = cover_letter_agent(structured, journal_name)

    # Save cover letter to session
    session["cover_letter"] = result.get("cover_letter", "")
    _save_session(session_id, session)

    return result


@app.get("/api/diff/{session_id}")
async def get_diff(session_id: str):
    """
    Interactive Before/After Diff View.
    Returns section-level diffs showing what was changed during rewriting.
    """
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    original = session.get("original_content", {})
    current = session.get("structured_json", {})

    if not original:
        return {"message": "No original content available for comparison", "diffs": []}

    diffs = []
    original_sections = {s.get("heading", "").lower(): s for s in original.get("sections", [])}
    current_sections = {s.get("heading", "").lower(): s for s in current.get("sections", [])}

    for heading, cur_sec in current_sections.items():
        orig_sec = original_sections.get(heading)
        if orig_sec:
            orig_content = orig_sec.get("content", "")
            cur_content = cur_sec.get("content", "")
            if orig_content != cur_content:
                diffs.append({
                    "section": cur_sec.get("heading", heading),
                    "original": orig_content[:500],
                    "modified": cur_content[:500],
                    "original_word_count": len(orig_content.split()),
                    "modified_word_count": len(cur_content.split()),
                    "changed": True,
                })
        else:
            diffs.append({
                "section": cur_sec.get("heading", heading),
                "original": None,
                "modified": cur_sec.get("content", "")[:500],
                "status": "new_section",
                "changed": True,
            })

    # Check abstract diff
    if original.get("abstract") and current.get("abstract"):
        if original["abstract"] != current["abstract"]:
            diffs.insert(0, {
                "section": "Abstract",
                "original": original["abstract"][:500],
                "modified": current["abstract"][:500],
                "original_word_count": len(original["abstract"].split()),
                "modified_word_count": len(current["abstract"].split()),
                "changed": True,
            })

    return {"session_id": session_id, "total_changes": len(diffs), "diffs": diffs}


@app.get("/api/reference-validation/{session_id}")
async def get_reference_validation(session_id: str):
    """
    Get CrossRef reference validation results.
    Shows which references have verified DOIs and which ones are missing.
    """
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    validation = session.get("reference_validation", {})
    return {
        "session_id": session_id,
        "validation": validation,
    }


@app.get("/api/export-bibtex/{session_id}")
async def export_bibtex(session_id: str):
    """
    BibTeX / Overleaf Export.
    Converts all references to .bib format for direct import into Overleaf or LaTeX editors.
    """
    from services.bibtex_exporter import references_to_bibtex
    from fastapi.responses import Response

    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json", {})
    references = structured.get("references", [])

    if not references:
        raise HTTPException(status_code=400, detail="No references found to export.")

    citation_style = session.get("citation_style", "")
    bibtex_content = references_to_bibtex(references, citation_style)

    # Save .bib file
    bib_path = OUTPUT_DIR / session_id / "references.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text(bibtex_content, encoding="utf-8")

    return Response(
        content=bibtex_content,
        media_type="application/x-bibtex",
        headers={"Content-Disposition": f"attachment; filename=references_{session_id}.bib"},
    )


@app.get("/api/tone-analysis/{session_id}")
async def analyze_tone(session_id: str):
    """
    AI Academic Tone Analyzer.
    Analyzes the manuscript for academic tone, formality, and potential AI-detection flags.
    Returns a score and suggestions for improving academic authenticity.
    """
    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json", {})
    sections = structured.get("sections", [])

    if not sections:
        raise HTTPException(status_code=400, detail="No content to analyze.")

    # Quick heuristic analysis (fast, no LLM needed)
    full_text = " ".join(s.get("content", "") for s in sections)
    abstract = structured.get("abstract", "")

    # Tone metrics
    total_words = len(full_text.split())
    sentence_count = len([s for s in full_text.split(".") if len(s.strip()) > 5])
    avg_sentence_len = total_words / max(sentence_count, 1)

    # Academic language indicators
    passive_voice_count = len(re.findall(r"\b(?:was|were|is|are|been|being)\s+\w+ed\b", full_text, re.IGNORECASE))
    hedging_words = len(re.findall(r"\b(?:may|might|could|suggest|indicate|appear|seem|possibly|potentially|likely)\b", full_text, re.IGNORECASE))
    informal_words = len(re.findall(r"\b(?:really|very|just|quite|pretty|stuff|things|lots|gonna|awesome|cool|basically|actually)\b", full_text, re.IGNORECASE))
    first_person = len(re.findall(r"\b(?:I|my|me|mine)\b", full_text))
    contractions = len(re.findall(r"\b\w+n't\b|\b\w+'s\b|\b\w+'re\b|\b\w+'ve\b|\b\w+'ll\b|\b\w+'d\b", full_text))

    # Calculate score
    academic_score = 80  # Start at 80
    academic_score += min(10, hedging_words)  # Bonus for hedging language
    academic_score += min(5, passive_voice_count // 5)  # Some passive is good
    academic_score -= informal_words * 3  # Penalty for informal language
    academic_score -= first_person * 2  # Penalty for first person
    academic_score -= contractions * 5  # Strong penalty for contractions
    if avg_sentence_len < 12:
        academic_score -= 5  # Too simple
    if avg_sentence_len > 35:
        academic_score -= 5  # Too complex

    academic_score = max(0, min(100, academic_score))

    suggestions = []
    if informal_words > 3:
        suggestions.append("Replace informal language (e.g., 'very', 'really', 'stuff') with precise academic terms")
    if first_person > 5:
        suggestions.append("Reduce first-person pronouns; use passive voice or 'the authors' instead")
    if contractions > 0:
        suggestions.append(f"Found {contractions} contractions — expand all contractions for formal academic writing")
    if hedging_words < 3:
        suggestions.append("Add hedging language (e.g., 'may suggest', 'potentially indicates') for scientific caution")
    if avg_sentence_len < 15:
        suggestions.append("Sentences are quite short — combine related ideas for more scholarly prose")

    return {
        "session_id": session_id,
        "academic_tone_score": academic_score,
        "metrics": {
            "total_words": total_words,
            "avg_sentence_length": round(avg_sentence_len, 1),
            "passive_voice_instances": passive_voice_count,
            "hedging_words": hedging_words,
            "informal_words": informal_words,
            "first_person_pronouns": first_person,
            "contractions": contractions,
        },
        "suggestions": suggestions,
        "assessment": "Excellent" if academic_score >= 85 else "Good" if academic_score >= 70 else "Needs improvement" if academic_score >= 50 else "Significant revision needed",
    }


@app.get("/api/equation-info/{session_id}")
async def get_equation_info(session_id: str):
    """
    Equation & Math Statistics.
    Returns information about detected equations in the manuscript.
    """
    from services.equation_engine import extract_equations

    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json", {})
    full_text = " ".join(s.get("content", "") for s in structured.get("sections", []))

    result = extract_equations(full_text)
    return {
        "session_id": session_id,
        "total_equations": result["total"],
        "display_equations": result["display_count"],
        "inline_equations": result["inline_count"],
        "equations": [
            {"id": eq["id"], "type": eq["type"], "preview": eq["inner"][:80]}
            for eq in result["equations"]
        ],
    }


@app.post("/api/generate-results")
async def generate_results(file: UploadFile = File(...)):
    """
    Data-to-Results Engine.
    Upload a CSV or Excel file, and get back an academic Results section in Markdown.
    """
    from agents.data_results_agent import process_data_to_results

    if not file.filename.endswith((".csv", ".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are supported")

    try:
        content = await file.read()
        results_markdown = process_data_to_results(content, file.filename)
        return {
            "filename": file.filename,
            "results_markdown": results_markdown
        }
    except Exception as e:
        logger.error(f"Failed to generate results from data: {e}")
        raise HTTPException(status_code=500, detail=f"Data processing failed: {str(e)}")


@app.get("/api/accessibility-check/{session_id}")
async def check_accessibility(session_id: str):
    """
    Accessibility & Inclusive Language Checker.
    Analyzes the manuscript for WCAG compliance and inclusive academic language.
    """
    from agents.accessibility_agent import analyze_accessibility

    _validate_session_id(session_id)
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    structured = session.get("structured_json", {})
    if not structured:
        raise HTTPException(status_code=400, detail="No structured content found.")

    result = analyze_accessibility(structured)
    return {
        "session_id": session_id,
        "accessibility_report": result
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
