"""
Mutation Engine — Phase 3 implementation.

Supported operators
-------------------
    >= → >     (GreaterThanOrEqual → GreaterThan)
    >  → >=    (GreaterThan → GreaterThanOrEqual)
    == → !=    (Equal → NotEqual)
    != → ==    (NotEqual → Equal)
    +  → -     (Add → Subtract)

Key design decisions
--------------------
* Uses Python's ``tokenize`` module to locate operators precisely: strings and
  comments are never mutated because they appear as dedicated token types that
  are explicitly skipped.
* Finds ALL mutation opportunities in a file (not just the first one).
* Each opportunity gets a unique, stable integer ID starting from
  ``start_id`` (default 1).
* The ``Mutation`` dataclass is unchanged so Person 1's pipeline keeps working.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import tokenize
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
    original_line: str         # the original line (stripped of trailing newline)
    mutated_line: str          # the mutated line (stripped of trailing newline)
    original_source: str       # full original file contents
    mutated_source: str        # full mutated file contents


# ---------------------------------------------------------------------------
# Operator table
# ---------------------------------------------------------------------------

# Order matters when one operator is a prefix of another: longer first so that
# ">=" is checked before ">".
OPERATOR_PAIRS: list[tuple[str, str]] = [
    (">=", ">"),
    (">",  ">="),
    ("==", "!="),
    ("!=", "=="),
    ("+",  "-"),
]

# Map original operator string → replacement string for fast lookup.
_OP_MAP: dict[str, str] = {orig: repl for orig, repl in OPERATOR_PAIRS}


# ---------------------------------------------------------------------------
# Tokenize-based finder
# ---------------------------------------------------------------------------

def _find_mutable_tokens(source: str) -> list[tuple[int, int, int, str, str]]:
    """Return a list of (line_number, col_start, col_end, original_op, mutated_op)
    for every operator token in *source* that has a defined replacement.

    Token types OP are the only ones examined; STRING and COMMENT tokens are
    implicitly ignored because they appear as different token types.
    """
    results: list[tuple[int, int, int, str, str]] = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)

    try:
        for tok in tokens:
            tok_type, tok_string, tok_start, tok_end, _ = tok
            if tok_type != tokenize.OP:
                continue
            replacement = _OP_MAP.get(tok_string)
            if replacement is None:
                continue
            line_no, col_start = tok_start
            _, col_end = tok_end
            results.append((line_no, col_start, col_end, tok_string, replacement))
    except tokenize.TokenError:
        # Partial / invalid source — return whatever we found so far.
        pass

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mutations(
    source_path: str | Path,
    start_id: int = 1,
) -> list[Mutation]:
    """Return a :class:`Mutation` for **every** mutable operator in *source_path*.

    Mutations are returned in source order (top to bottom, left to right).
    IDs start at *start_id* and increment by 1.

    Raises
    ------
    ValueError
        If no mutable operator is found in the file.
    """
    source_path = Path(source_path).resolve()
    original_source = source_path.read_text(encoding="utf-8")
    lines = original_source.splitlines(keepends=True)

    opportunities = _find_mutable_tokens(original_source)
    if not opportunities:
        raise ValueError(f"No supported mutation operator found in {source_path}")

    mutations: list[Mutation] = []
    for offset, (line_no, col_start, col_end, orig_op, mut_op) in enumerate(opportunities):
        # line_no is 1-based; lines list is 0-based.
        line_index = line_no - 1
        original_line = lines[line_index]

        # Replace exactly the token span on this line.
        mutated_line = (
            original_line[:col_start]
            + mut_op
            + original_line[col_end:]
        )

        # Build full mutated source by swapping just that one line.
        mutated_source = "".join(
            lines[:line_index] + [mutated_line] + lines[line_index + 1:]
        )

        mutations.append(Mutation(
            id=start_id + offset,
            source_file=source_path,
            line_number=line_no,
            operator=f"{orig_op} \u2192 {mut_op}",
            original_line=original_line.rstrip("\n"),
            mutated_line=mutated_line.rstrip("\n"),
            original_source=original_source,
            mutated_source=mutated_source,
        ))

    return mutations


def generate_mutation(source_path: str | Path, mutation_id: int = 1) -> Mutation:
    """Return a :class:`Mutation` for the **first** mutable operator found.

    This is the legacy single-mutation entry point kept for backward
    compatibility with Person 1's pipeline.

    Raises
    ------
    ValueError
        If no supported operator is found in the file.
    """
    return generate_mutations(source_path, start_id=mutation_id)[0]


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

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
