"""
TestPilot Source Discovery — locates Python source files in a project directory.

This module is responsible only for finding candidate source files.
It does NOT apply mutation logic or filter files based on operator support —
that remains the mutation engine's concern.

Usage
-----
    from backend.discovery import discover_source_files
    from pathlib import Path

    sources = discover_source_files(Path("demo_projects/bank_account"))
    # [PosixPath('demo_projects/bank_account/bank_account.py')]
"""

from __future__ import annotations

from pathlib import Path


def discover_source_files(project_dir: str | Path) -> list[Path]:
    """Return sorted non-test Python source files under *project_dir*.

    Recursively walks *project_dir* and collects every ``.py`` file that is
    not a test file, skipping ``__pycache__`` directories entirely.

    Exclusion rules
    ---------------
    * Files whose name starts with ``test_``  (e.g. ``test_app.py``)
    * Files whose name ends with   ``_test.py`` (e.g. ``app_test.py``)
    * Anything inside a ``__pycache__`` directory at any depth

    Parameters
    ----------
    project_dir:
        Root directory of the project to inspect.

    Returns
    -------
    list[Path]
        Sorted list of absolute ``Path`` objects for each discovered source
        file.  Returns an empty list if no eligible files are found.

    Raises
    ------
    NotADirectoryError
        If *project_dir* does not exist or is not a directory.
    """
    project_dir = Path(project_dir).resolve()

    if not project_dir.is_dir():
        raise NotADirectoryError(f"project_dir is not a directory: {project_dir}")

    results: list[Path] = []

    for path in project_dir.rglob("*.py"):
        # Skip anything inside __pycache__ at any depth.
        if "__pycache__" in path.parts:
            continue

        name = path.name
        # Skip test files by naming convention.
        if name.startswith("test_") or name.endswith("_test.py"):
            continue

        results.append(path)

    return sorted(results)
