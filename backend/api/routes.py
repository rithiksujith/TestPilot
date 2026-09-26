"""
TestPilot API routes.

Endpoints
---------
GET  /api/health      — liveness check
POST /api/analyze     — run the mutation pipeline on a project and return JSON
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.discovery import discover_source_files
from backend.pipeline import PipelineResult, run_pipeline

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Body for POST /api/analyze.

    ``project_dir`` is required (defaults to the bank_account demo so that an
    empty body ``{}`` still works).  ``source_file`` is optional: when omitted
    the API discovers Python source files in ``project_dir`` automatically and
    selects the first one.
    """

    source_file: Optional[str] = Field(
        default=None,
        description=(
            "Path to the Python source file to mutate (relative to project root). "
            "If omitted, the first source file discovered in project_dir is used."
        ),
    )
    project_dir: str = Field(
        default="demo_projects/bank_account",
        description="Root directory of the project under test.",
    )
    mutation_id: int = Field(
        default=1,
        description="Numeric identifier for this mutation run.",
        ge=1,
    )


class AiInsightResponse(BaseModel):
    """Subset of AnalysisResult exposed to the frontend."""

    explanation: str
    risk: str
    missing_behavior: str
    suggested_test: str
    suggested_test_name: str


class AnalyzeResponse(BaseModel):
    """JSON representation of a PipelineResult."""

    mutation_id: int
    source_file: str
    line_number: int
    operator: str
    original_line: str
    mutated_line: str
    status: str                             # "KILLED" or "SURVIVED"
    mutation_score: Optional[float]         # 0.0 (survived) or 1.0 (killed); None if unavailable
    ai_insight: Optional[AiInsightResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipeline_result_to_response(result: PipelineResult) -> AnalyzeResponse:
    """Convert a PipelineResult dataclass into the API response model."""
    ai = None
    if result.ai_insight is not None:
        a = result.ai_insight
        ai = AiInsightResponse(
            explanation=a.explanation,
            risk=a.risk,
            missing_behavior=a.missing_behavior,
            suggested_test=a.suggested_test,
            suggested_test_name=a.suggested_test_name,
        )

    # mutation_score: simple single-mutation score
    #   1.0 = mutation was killed (good — tests caught it)
    #   0.0 = mutation survived (bad — tests missed it)
    mutation_score = 1.0 if result.status == "KILLED" else 0.0

    return AnalyzeResponse(
        mutation_id=result.mutation_id,
        source_file=str(result.source_file),
        line_number=result.line_number,
        operator=result.operator,
        original_line=result.original_line,
        mutated_line=result.mutated_line,
        status=result.status,
        mutation_score=mutation_score,
        ai_insight=ai,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health", summary="Liveness check")
def health() -> dict:
    """Return ``{"status": "ok"}`` to confirm the server is running."""
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse, summary="Run mutation pipeline")
def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    """Run the full mutation-testing pipeline and return a structured result.

    The pipeline:
    1. Resolves the source file — uses the explicit ``source_file`` when
       provided, otherwise discovers Python source files in ``project_dir``
       and selects the first one.
    2. Generates a mutation (``>=`` → ``>``) in *source_file*.
    3. Copies *project_dir* to a temp directory with the mutation applied.
    4. Runs pytest inside that temp directory.
    5. Classifies the result as **KILLED** or **SURVIVED**.
    6. If SURVIVED, calls the AI advisor for an explanation and a suggested test.
    7. Returns the combined result as JSON.

    For the demo, send an empty body ``{}`` to analyze the bank_account project
    via automatic source-file discovery.
    """
    project = Path(body.project_dir)

    if not project.is_dir():
        raise HTTPException(
            status_code=422,
            detail=f"project_dir not found: {body.project_dir}",
        )

    if body.source_file is not None:
        source = Path(body.source_file)
        if not source.exists():
            raise HTTPException(
                status_code=422,
                detail=f"source_file not found: {body.source_file}",
            )
    else:
        candidates = discover_source_files(project)
        if not candidates:
            raise HTTPException(
                status_code=422,
                detail=f"No Python source files found in project_dir: {body.project_dir}",
            )
        source = candidates[0]

    try:
        result = run_pipeline(
            source_file=source,
            project_dir=project,
            mutation_id=body.mutation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _pipeline_result_to_response(result)
