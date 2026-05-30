"""
Manuscript State Model — shared across all agents.
"""
from typing import TypedDict, Optional
from pydantic import BaseModel


class ManuscriptState(TypedDict, total=False):
    """Global state passed through the LangGraph pipeline."""
    raw_input_path: str
    file_type: str
    parsed_text: str
    structured_json: dict
    selected_journal: str
    selected_family: str
    journal_rules: dict
    citation_style: str
    formatted_structure: dict
    formatted_doc_path: str
    formatted_pdf_path: str
    formatted_latex_path: str
    compliance_report: dict
    plagiarism_report: dict
    original_content: dict        # Stores pre-rewrite content for before/after comparison
    reference_validation: dict    # CrossRef validation results
    remediation_instructions: list  # Violations to fix on retry (smart retry)
    journal_recommendations: list   # AI-recommended journals
    cover_letter: str               # Generated cover letter text
    errors: list
    current_step: str
    retry_count: int


class UploadResponse(BaseModel):
    session_id: str
    file_name: str
    file_type: str
    message: str


class ProcessRequest(BaseModel):
    session_id: str
    journal_name: Optional[str] = None
    family_name: Optional[str] = None


class ProcessResponse(BaseModel):
    session_id: str
    status: str
    compliance_report: Optional[dict] = None
    plagiarism_report: Optional[dict] = None
    docx_download_url: Optional[str] = None
    pdf_download_url: Optional[str] = None
    latex_download_url: Optional[str] = None
    errors: Optional[list] = None
    comparison: Optional[dict] = None
