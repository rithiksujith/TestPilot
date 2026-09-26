"""
Test Runner — executes pytest inside a mutated project directory.

Classification
--------------
KILLED   — pytest exits with a non-zero code (at least one test failed).
           The mutation was caught by the test suite.

SURVIVED — pytest exits with code 0 (all tests passed despite the mutation).
           The test suite did NOT detect the change — a test gap exists.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

KILLED = "KILLED"
SURVIVED = "SURVIVED"


@dataclass
class RunResult:
    """Outcome of running pytest against a single mutated project."""

    status: str          # KILLED or SURVIVED
    exit_code: int       # raw pytest exit code
    output: str          # combined stdout + stderr from pytest


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests(project_dir: str | Path) -> RunResult:
    """Run pytest inside *project_dir* and return a :class:`RunResult`.

    pytest is invoked via ``sys.executable`` so it always runs in the same
    Python environment as TestPilot itself, regardless of PATH.

    The original source files are never touched — *project_dir* must be a
    temporary copy produced by the mutation engine.
    """
    project_dir = Path(project_dir).resolve()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", "-q"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )

    status = SURVIVED if result.returncode == 0 else KILLED
    output = result.stdout + result.stderr

    return RunResult(
        status=status,
        exit_code=result.returncode,
        output=output,
    )
