"""
Mutation Workflow — ties the engine and runner together.

Usage (from project root)
--------------------------
    python -m backend.runner.workflow demo_projects/bank_account/bank_account.py \\
                                      demo_projects/bank_account

Or import and call directly:

    from backend.runner.workflow import run_mutation_workflow
    result = run_mutation_workflow(
        source_file="demo_projects/bank_account/bank_account.py",
        project_dir="demo_projects/bank_account",
    )
    print(result)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.mutations.engine import Mutation, generate_mutation, write_mutated_project
from backend.runner.runner import RunResult, run_tests


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class WorkflowResult:
    """Combined output of the full mutation → test → classify pipeline."""

    mutation: Mutation
    run_result: RunResult

    @property
    def status(self) -> str:
        return self.run_result.status

    def summary(self) -> str:
        # Use ASCII-safe operator label for terminals that can't render Unicode.
        operator_ascii = self.mutation.operator.replace("\u2192", "->")
        lines = [
            "=" * 60,
            "TestPilot - Mutation Result",
            "=" * 60,
            f"File        : {self.mutation.source_file}",
            f"Line        : {self.mutation.line_number}",
            f"Operator    : {operator_ascii}",
            f"Original    : {self.mutation.original_line.strip()}",
            f"Mutated     : {self.mutation.mutated_line.strip()}",
            "-" * 60,
            f"Status      : {self.status}",
            f"Exit code   : {self.run_result.exit_code}",
            "-" * 60,
            "Pytest output:",
            self.run_result.output.strip(),
            "=" * 60,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

def run_mutation_workflow(
    source_file: str | Path,
    project_dir: str | Path,
    mutation_id: int = 1,
) -> WorkflowResult:
    """Run the full pipeline for a single mutation.

    Steps
    -----
    1. Generate mutation (find ``>=`` → ``>``) in *source_file*.
    2. Copy *project_dir* to a temp directory with the mutation applied.
    3. Run pytest inside that temp directory.
    4. Classify the result as KILLED or SURVIVED.
    5. Delete the temp directory.

    Returns a :class:`WorkflowResult` regardless of classification.
    """
    # Step 1 — generate mutation
    mutation = generate_mutation(source_file, mutation_id=mutation_id)

    # Step 2 — write mutated project to temp dir
    tmp_dir = write_mutated_project(mutation, project_dir)

    try:
        # Step 3 & 4 — run tests and classify
        run_result = run_tests(tmp_dir)
    finally:
        # Step 5 — always clean up, even on unexpected errors
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return WorkflowResult(mutation=mutation, run_result=run_result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m backend.runner.workflow <source_file> <project_dir>")
        sys.exit(1)

    result = run_mutation_workflow(
        source_file=sys.argv[1],
        project_dir=sys.argv[2],
    )
    print(result.summary())
    sys.exit(0 if result.status == "SURVIVED" else 1)
