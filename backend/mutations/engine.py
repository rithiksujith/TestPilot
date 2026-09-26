"""
Mutation Engine — first-pass implementation.

Supported operator:
    >= → >   (GreaterThanOrEqual to GreaterThan)

Workflow
--------
1. Read a Python source file.
2. Locate the first occurrence of ``>=`` in the source text.
3. Build a Mutation dataclass that records where and what was changed.
4. Write a temporary copy of the project with the mutation applied so that
   the test runner can execute pytest against it without touching the originals.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Mutation:
    """Describes a single mutation that was (or could be) applied."""

    id: int
    source_file: Path          # absolute path to the original source file
    line_number: int           # 1-based line number where the change occurs
    operator: str              # human-readable label, e.g. ">= → >"
    original_line: str         # the original line (stripped)
    mutated_line: str          # the mutated line (stripped)
    original_source: str       # full original file contents
    mutated_source: str        # full mutated file contents


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

OPERATOR_PAIRS = [
    (">=", ">"),   # the only operator we support right now
]


def generate_mutation(source_path: str | Path, mutation_id: int = 1) -> Mutation:
    """Return a :class:`Mutation` for the first ``>=`` found in *source_path*.

    Raises
    ------
    ValueError
        If no ``>=`` operator is found in the file.
    """
    source_path = Path(source_path).resolve()
    original_source = source_path.read_text(encoding="utf-8")
    lines = original_source.splitlines(keepends=True)

    for original_op, mutated_op in OPERATOR_PAIRS:
        for line_index, line in enumerate(lines):
            stripped = line.lstrip()
            # Skip comment-only lines so we mutate actual code, not docs.
            if stripped.startswith("#"):
                continue
            if original_op in line:
                mutated_line = line.replace(original_op, mutated_op, 1)
                mutated_lines = lines[:line_index] + [mutated_line] + lines[line_index + 1:]
                mutated_source = "".join(mutated_lines)

                return Mutation(
                    id=mutation_id,
                    source_file=source_path,
                    line_number=line_index + 1,
                    operator=f"{original_op} → {mutated_op}",
                    original_line=line.rstrip("\n"),
                    mutated_line=mutated_line.rstrip("\n"),
                    original_source=original_source,
                    mutated_source=mutated_source,
                )

    raise ValueError(f"No supported mutation operator found in {source_path}")


def write_mutated_project(mutation: Mutation, project_dir: str | Path) -> Path:
    """Copy *project_dir* to a fresh temp directory and apply *mutation*.

    Returns the path to the temporary directory.  The caller is responsible
    for deleting it (use :func:`backend.runner.workflow.run_mutation_workflow`
    which handles cleanup automatically).
    """
    project_dir = Path(project_dir).resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix="testpilot_mutant_"))

    # Copy the entire project directory into the temp location.
    shutil.copytree(src=project_dir, dst=tmp_dir, dirs_exist_ok=True)

    # Overwrite only the mutated file — keep its relative path inside the project.
    relative = mutation.source_file.relative_to(project_dir)
    mutated_file = tmp_dir / relative
    mutated_file.write_text(mutation.mutated_source, encoding="utf-8")

    return tmp_dir
