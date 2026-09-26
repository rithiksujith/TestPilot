"""
Mutation Workflow — ties the engine and runner together.

Single-mutation usage (backward-compatible)
-------------------------------------------
    from backend.runner.workflow import run_mutation_workflow
    result = run_mutation_workflow(
        source_file="demo_projects/bank_account/bank_account.py",
        project_dir="demo_projects/bank_account",
    )
    print(result.summary())

All-mutations usage (Phase 3)
------------------------------
    from backend.runner.workflow import run_all_mutations_workflow
    report = run_all_mutations_workflow(
        source_file="demo_projects/calculator/calculator.py",
        project_dir="demo_projects/calculator",
    )
    print(report.summary())

CLI
---
    python -m backend.runner.workflow demo_projects/bank_account/bank_account.py \\
                                      demo_projects/bank_account
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from backend.mutations.engine import (
    Mutation,
    generate_mutation,
    generate_mutations,
    write_mutated_project,
)
from backend.runner.runner import KILLED, SURVIVED, RunResult, run_tests


# ---------------------------------------------------------------------------
# Single-mutation result (unchanged — backward compatible)
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
# Multi-mutation report (Phase 3)
# ---------------------------------------------------------------------------

@dataclass
class MutationReport:
    """Aggregated results for all mutations found in a source file."""

    results: list[WorkflowResult] = field(default_factory=list)

    # ---- derived statistics ------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def killed(self) -> int:
        return sum(1 for r in self.results if r.status == KILLED)

    @property
    def survived(self) -> int:
        return sum(1 for r in self.results if r.status == SURVIVED)

    @property
    def mutation_score(self) -> float:
        """Percentage of mutations killed (0.0–100.0).  Returns 0.0 for empty."""
        if self.total == 0:
            return 0.0
        return self.killed / self.total * 100

    # ---- display -----------------------------------------------------------

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "TestPilot - Mutation Report",
            "=" * 60,
        ]
        for r in self.results:
            operator_ascii = r.mutation.operator.replace("\u2192", "->")
            lines.append(
                f"  #{r.mutation.id:>3}  line {r.mutation.line_number:<4} "
                f"{operator_ascii:<12}  {r.status}"
            )
        lines += [
            "-" * 60,
            f"Total     : {self.total}",
            f"Killed    : {self.killed}",
            f"Survived  : {self.survived}",
            f"Score     : {self.mutation_score:.1f}%",
            "=" * 60,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow functions
# ---------------------------------------------------------------------------

def run_mutation_workflow(
    source_file: str | Path,
    project_dir: str | Path,
    mutation_id: int = 1,
) -> WorkflowResult:
    """Run the full pipeline for a **single** mutation (first operator found).

    This function is kept unchanged for backward compatibility with
    Person 1's pipeline and the existing API routes.
    """
    mutation = generate_mutation(source_file, mutation_id=mutation_id)
    tmp_dir = write_mutated_project(mutation, project_dir)

    try:
        run_result = run_tests(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return WorkflowResult(mutation=mutation, run_result=run_result)


def run_all_mutations_workflow(
    source_file: str | Path,
    project_dir: str | Path,
    start_id: int = 1,
) -> MutationReport:
    """Run the full pipeline for **every** mutation found in *source_file*.

    Each mutation is applied independently:
      - a fresh temp copy of *project_dir* is created
      - pytest is run against that copy
      - the copy is deleted

    Returns a :class:`MutationReport` with per-mutation results and an
    aggregate mutation score.
    """
    mutations = generate_mutations(source_file, start_id=start_id)
    report = MutationReport()

    for mutation in mutations:
        tmp_dir = write_mutated_project(mutation, project_dir)
        try:
            run_result = run_tests(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        report.results.append(WorkflowResult(mutation=mutation, run_result=run_result))

    return report


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
