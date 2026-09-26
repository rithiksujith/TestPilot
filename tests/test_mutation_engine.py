"""
Tests for the TestPilot mutation engine and test runner.

These tests use the demo_projects/bank_account project as a real fixture
so the assertions match documented, expected behaviour.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from backend.mutations.engine import generate_mutation, write_mutated_project
from backend.runner.runner import KILLED, SURVIVED, run_tests
from backend.runner.workflow import run_mutation_workflow

# ---------------------------------------------------------------------------
# Paths (relative to project root where pytest is invoked)
# ---------------------------------------------------------------------------

DEMO_DIR = Path("demo_projects/bank_account")
DEMO_SOURCE = DEMO_DIR / "bank_account.py"


# ===========================================================================
# Mutation Engine
# ===========================================================================

class TestGenerateMutation:
    def test_returns_mutation_for_gte_operator(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert mutation.operator == ">= → >"

    def test_mutation_id_is_stored(self):
        mutation = generate_mutation(DEMO_SOURCE, mutation_id=42)

        assert mutation.id == 42

    def test_line_number_is_positive(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert mutation.line_number >= 1

    def test_original_line_contains_gte(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert ">=" in mutation.original_line

    def test_mutated_line_contains_gt_not_gte(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert ">=" not in mutation.mutated_line
        assert ">" in mutation.mutated_line

    def test_mutated_source_differs_from_original(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert mutation.mutated_source != mutation.original_source

    def test_source_file_is_absolute(self):
        mutation = generate_mutation(DEMO_SOURCE)

        assert mutation.source_file.is_absolute()

    def test_raises_when_no_operator_found(self, tmp_path):
        # A file that contains no >= operator.
        source = tmp_path / "no_op.py"
        source.write_text("def foo():\n    return 1\n")

        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutation(source)


class TestWriteMutatedProject:
    def test_creates_temp_directory(self):
        mutation = generate_mutation(DEMO_SOURCE)
        tmp_dir = write_mutated_project(mutation, DEMO_DIR)

        try:
            assert tmp_dir.exists()
            assert tmp_dir.is_dir()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_temp_dir_contains_test_file(self):
        mutation = generate_mutation(DEMO_SOURCE)
        tmp_dir = write_mutated_project(mutation, DEMO_DIR)

        try:
            assert (tmp_dir / "test_bank_account.py").exists()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_mutated_source_file_has_changed_operator(self):
        mutation = generate_mutation(DEMO_SOURCE)
        tmp_dir = write_mutated_project(mutation, DEMO_DIR)

        try:
            mutated_content = (tmp_dir / "bank_account.py").read_text()
            # The specific code line must use > not >=.
            assert "if self._balance > amount:" in mutated_content
            assert "if self._balance >= amount:" not in mutated_content
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_original_source_file_is_unchanged(self):
        mutation = generate_mutation(DEMO_SOURCE)
        original_content = DEMO_SOURCE.read_text()

        tmp_dir = write_mutated_project(mutation, DEMO_DIR)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        assert DEMO_SOURCE.read_text() == original_content


# ===========================================================================
# Test Runner
# ===========================================================================

class TestRunTests:
    def test_passing_suite_returns_survived(self, tmp_path):
        # Write a trivial module + test that always passes.
        (tmp_path / "module.py").write_text("def add(a, b): return a + b\n")
        (tmp_path / "test_module.py").write_text(
            textwrap.dedent("""\
                from module import add
                def test_add():
                    assert add(1, 2) == 3
            """)
        )

        result = run_tests(tmp_path)

        assert result.status == SURVIVED
        assert result.exit_code == 0

    def test_failing_suite_returns_killed(self, tmp_path):
        # Write a test that always fails.
        (tmp_path / "test_fail.py").write_text(
            textwrap.dedent("""\
                def test_always_fails():
                    assert False, "deliberate failure"
            """)
        )

        result = run_tests(tmp_path)

        assert result.status == KILLED
        assert result.exit_code != 0

    def test_output_is_captured(self, tmp_path):
        (tmp_path / "test_simple.py").write_text("def test_ok(): pass\n")

        result = run_tests(tmp_path)

        # pytest always prints something (at least the summary line)
        assert len(result.output) > 0


# ===========================================================================
# Workflow (integration)
# ===========================================================================

class TestRunMutationWorkflow:
    def test_demo_project_mutation_survives(self):
        """The >= → > mutation in bank_account.py must be classified SURVIVED
        because the existing test suite has no boundary test for exact-balance
        withdrawal.
        """
        result = run_mutation_workflow(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        assert result.mutation.operator == ">= → >"
        assert result.status == SURVIVED

    def test_workflow_cleans_up_temp_dir(self, tmp_path, monkeypatch):
        """After the workflow completes the temp directory must be deleted."""
        created_dirs: list[Path] = []
        original_write = write_mutated_project

        def tracking_write(mutation, project_dir):
            tmp_dir = original_write(mutation, project_dir)
            created_dirs.append(tmp_dir)
            return tmp_dir

        monkeypatch.setattr(
            "backend.runner.workflow.write_mutated_project", tracking_write
        )

        run_mutation_workflow(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        assert len(created_dirs) == 1
        assert not created_dirs[0].exists(), "Temp dir was not cleaned up"

    def test_summary_contains_status(self):
        result = run_mutation_workflow(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        summary = result.summary()
        assert "SURVIVED" in summary or "KILLED" in summary
        # summary() uses ASCII -> for terminal compatibility
        assert ">= -> >" in summary
