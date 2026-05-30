"""
Data-to-Results Engine — Converts raw data (CSV/JSON) into academic Results sections.
Analyzes statistical significance, trends, and formats them into publication-ready prose and tables.
"""
import logging
import json
import pandas as pd
import io

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# Use the environment GROQ_MODEL or fallback
import os
GROQ_MODEL = os.getenv("GROQ_MODEL", "moonshotai/kimi-k2-instruct")

DATA_ANALYSIS_PROMPT = """You are an expert data scientist and academic author. 
Analyze the following dataset and write a professional, publication-ready "Results" section.

DATASET SUMMARY:
Columns: {columns}
Row Count: {row_count}
Basic Statistics:
{stats}

DATA PREVIEW (First few rows):
{data_preview}

INSTRUCTIONS:
1. Identify key trends, outliers, or significant findings in the data.
2. Write a comprehensive "Results" section in formal academic language describing these findings.
3. Incorporate at least one Markdown table summarizing the most important metrics.
4. If there appear to be statistically significant correlations, mention them (e.g., "A strong positive correlation was observed...").
5. Do NOT hallucinate data — strictly stick to the uploaded dataset.
6. Return the output as beautiful Markdown format, suitable for inclusion in a manuscript.

Return ONLY the markdown text.
"""

def process_data_to_results(file_content: bytes, filename: str) -> str:
    """
    Process uploaded CSV/Excel data and return a generated Results section.
    """
    try:
        # Load data based on extension
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ValueError("Unsupported data format. Please upload CSV or Excel.")

        # Extract stats
        columns = ", ".join(df.columns.tolist())
        row_count = len(df)
        
        # Get basic descriptive stats for numeric columns
        numeric_df = df.select_dtypes(include='number')
        if not numeric_df.empty:
            stats = numeric_df.describe().to_string()
        else:
            stats = "No numeric columns available for statistical summary."

        # Data preview
        preview = df.head(10).to_string()

        # Generate results using LLM
        llm = ChatGroq(model=GROQ_MODEL, temperature=0.1, max_tokens=2048)
        
        prompt = DATA_ANALYSIS_PROMPT.format(
            columns=columns,
            row_count=row_count,
            stats=stats,
            data_preview=preview
        )

        response = llm.invoke([
            SystemMessage(content="You generate academic Results sections from raw datasets."),
            HumanMessage(content=prompt)
        ])

        return response.content.strip()

    except Exception as e:
        logger.error(f"Data-to-Results Engine failed: {str(e)}")
        raise e
