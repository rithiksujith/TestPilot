"""
TestPilot Pipeline — integration layer (Person 1).

Chains Person 2's mutation workflow with Person 3's AI advisor into a single
function that returns one structured result per mutation.

Flow
----
    generate mutation
          ↓
    create temporary mutated project
          ↓
    run pytest
          ↓
    classify KILLED / SURVIVED
          ↓
    if SURVIVED → analyze with advisor
          ↓
    return PipelineResult

Usage
-----
    from backend.pipeline import run_pipeline

    result = run_pipeline(
        source_file="demo_projects/bank_account/bank_account.py",
        project_dir="demo_projects/bank_account",
    )
    print(result)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.ai.advisor import AnalysisResult, analyze_surviving_mutation
from backend.runner.runner import KILLED, SURVIVED
from backend.runner.workflow import WorkflowResult, run_mutation_workflow


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Full output of the integrated mutation-testing pipeline."""

    mutation_id: int
    source_file: Path
    line_number: int
    operator: str
    original_line: str
    mutated_line: str
    status: str                         # KILLED or SURVIVED
    pytest_exit_code: int
    pytest_output: str
    ai_insight: Optional[AnalysisResult]  # None for KILLED mutations

    def __str__(self) -> str:
        operator_ascii = self.operator.replace("\u2192", "->")
        lines = [
            "=" * 60,
            "TestPilot — Pipeline Result",
            "=" * 60,
            f"File        : {self.source_file}",
            f"Line        : {self.line_number}",
            f"Operator    : {operator_ascii}",
            f"Original    : {self.original_line.strip()}",
            f"Mutated     : {self.mutated_line.strip()}",
            "-" * 60,
            f"Status      : {self.status}",
            f"Exit code   : {self.pytest_exit_code}",
        ]
        if self.ai_insight is not None:
            a = self.ai_insight
            lines += [
                "-" * 60,
                "AI Insight:",
                f"  explanation      : {a.explanation}",
                f"  risk             : {a.risk}",
                f"  missing_behavior : {a.missing_behavior}",
                f"  suggested_test   : {a.suggested_test_name}",
                "",
                "Suggested test code:",
                a.suggested_test,
            ]
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    source_file: str | Path,
    project_dir: str | Path,
    mutation_id: int = 1,
) -> PipelineResult:
    """Run the full mutation-testing pipeline for a single mutation.

    Parameters
    ----------
    source_file:
        Path to the Python source file to mutate.
    project_dir:
        Root directory of the project under test (must contain the test suite).
    mutation_id:
        Numeric identifier for the mutation (default 1).

    Returns
    -------
    PipelineResult
        Contains mutation metadata, test classification, and (for SURVIVED
        mutations) the advisor's AI insight.
    """
    workflow: WorkflowResult = run_mutation_workflow(
        source_file=source_file,
        project_dir=project_dir,
        mutation_id=mutation_id,
    )

    ai_insight: Optional[AnalysisResult] = None
    if workflow.status == SURVIVED:
        ai_insight = analyze_surviving_mutation(workflow.mutation)

    m = workflow.mutation
    r = workflow.run_result

    return PipelineResult(
        mutation_id=m.id,
        source_file=m.source_file,
        line_number=m.line_number,
        operator=m.operator,
        original_line=m.original_line,
        mutated_line=m.mutated_line,
        status=workflow.status,
        pytest_exit_code=r.exit_code,
        pytest_output=r.output,
        ai_insight=ai_insight,
    )
