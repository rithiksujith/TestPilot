"""
Tests for the TestPilot mutation engine and test runner — Phase 3.

Covers
------
* Each of the five mutation operators
* Multiple mutations discovered in a single file
* Unique mutation IDs
* Comments are NOT mutated
* String literals are NOT mutated
* KILLED / SURVIVED classification
* Mutation score calculation
* Backward-compatible generate_mutation() (single-mutation API)
* MutationReport aggregate (total, killed, survived, score)
* Integration: run_all_mutations_workflow on the calculator demo
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from backend.mutations.engine import (
    Mutation,
    generate_mutation,
    generate_mutations,
    write_mutated_project,
)
from backend.runner.runner import KILLED, SURVIVED, run_tests
from backend.runner.workflow import (
    MutationReport,
    WorkflowResult,
    run_all_mutations_workflow,
    run_mutation_workflow,
)

# ---------------------------------------------------------------------------
# Paths (relative to project root where pytest is invoked)
# ---------------------------------------------------------------------------

BANK_DIR = Path("demo_projects/bank_account")
BANK_SOURCE = BANK_DIR / "bank_account.py"

CALC_DIR = Path("demo_projects/calculator")
CALC_SOURCE = CALC_DIR / "calculator.py"


# ===========================================================================
# Helpers
# ===========================================================================

def _write_source(tmp_path: Path, code: str) -> Path:
    """Write *code* to tmp_path/source.py and return the path."""
    p = tmp_path / "source.py"
    p.write_text(textwrap.dedent(code))
    return p


# ===========================================================================
# Engine — individual operators
# ===========================================================================

class TestGteToGt:
    """Operator >=  →  >"""

    def test_operator_label(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x >= 10
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert ">= \u2192 >" in ops

    def test_mutated_line_replaces_token(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x >= 10
        """)
        m = next(m for m in generate_mutations(src) if m.operator == ">= \u2192 >")
        assert ">=" not in m.mutated_line
        assert ">" in m.mutated_line

    def test_gte_mutation_on_bank_account(self):
        mutations = generate_mutations(BANK_SOURCE)
        ops = [m.operator for m in mutations]
        assert ">= \u2192 >" in ops


class TestGtToGte:
    """Operator >  →  >="""

    def test_operator_label(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x > 10
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert "> \u2192 >=" in ops

    def test_mutated_line_replaces_token(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x > 10
        """)
        m = next(m for m in generate_mutations(src) if m.operator == "> \u2192 >=")
        assert m.mutated_line.count(">=") == 1

    def test_gt_not_double_mutated(self, tmp_path):
        """A '>=' on a line must not also produce a '>' mutation for the same token."""
        src = _write_source(tmp_path, """\
            def f(x):
                return x >= 5
        """)
        mutations = generate_mutations(src)
        # '>=' produces '>= → >' but must NOT also produce '> → >='
        # because the tokenizer sees '>=' as a single OP token.
        gt_to_gte = [m for m in mutations if m.operator == "> \u2192 >="]
        gte_to_gt = [m for m in mutations if m.operator == ">= \u2192 >"]
        assert len(gte_to_gt) == 1
        assert len(gt_to_gte) == 0


class TestEqToNeq:
    """Operator ==  →  !="""

    def test_operator_label(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x == 0
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert "== \u2192 !=" in ops

    def test_mutated_source_contains_neq(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x == 0
        """)
        m = next(m for m in generate_mutations(src) if m.operator == "== \u2192 !=")
        assert "!=" in m.mutated_line
        assert "==" not in m.mutated_line


class TestNeqToEq:
    """Operator !=  →  =="""

    def test_operator_label(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x != 0
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert "!= \u2192 ==" in ops

    def test_mutated_source_contains_eq(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x != 0
        """)
        m = next(m for m in generate_mutations(src) if m.operator == "!= \u2192 ==")
        assert "==" in m.mutated_line
        assert "!=" not in m.mutated_line


class TestAddToSub:
    """Operator +  →  -"""

    def test_operator_label(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                return a + b
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert "+ \u2192 -" in ops

    def test_mutated_line_uses_minus(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                return a + b
        """)
        m = next(m for m in generate_mutations(src) if m.operator == "+ \u2192 -")
        assert "a - b" in m.mutated_line


# ===========================================================================
# Engine — multiple mutations in one file
# ===========================================================================

class TestMultipleMutations:
    def test_multiple_operators_in_file(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                if a >= b:
                    return a + b
                return a == b
        """)
        mutations = generate_mutations(src)
        ops = [m.operator for m in mutations]
        assert ">= \u2192 >" in ops
        assert "+ \u2192 -" in ops
        assert "== \u2192 !=" in ops

    def test_count_matches_distinct_tokens(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                x = a + b
                y = a + b
                return x >= y
        """)
        mutations = generate_mutations(src)
        # Two '+' tokens and one '>='
        ops = [m.operator for m in mutations]
        assert ops.count("+ \u2192 -") == 2
        assert ops.count(">= \u2192 >") == 1
        assert len(mutations) == 3

    def test_mutations_are_independent(self, tmp_path):
        """Each mutation changes only its own token; the others remain original."""
        src = _write_source(tmp_path, """\
            def f(a, b):
                return a + b >= 10
        """)
        mutations = generate_mutations(src)
        plus_mut = next(m for m in mutations if m.operator == "+ \u2192 -")
        gte_mut  = next(m for m in mutations if m.operator == ">= \u2192 >")

        # The '+' mutation must not change '>='
        assert ">=" in plus_mut.mutated_source
        # The '>=' mutation must not change '+'
        assert "+" in gte_mut.mutated_source

    def test_returns_list_not_single(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return x >= 0
        """)
        result = generate_mutations(src)
        assert isinstance(result, list)

    def test_raises_when_no_operator(self, tmp_path):
        src = _write_source(tmp_path, """\
            def foo():
                return 1
        """)
        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutations(src)


# ===========================================================================
# Engine — unique IDs
# ===========================================================================

class TestMutationIds:
    def test_ids_are_unique(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                x = a + b
                y = a + b
                return x >= y
        """)
        mutations = generate_mutations(src)
        ids = [m.id for m in mutations]
        assert len(ids) == len(set(ids)), "Duplicate mutation IDs detected"

    def test_ids_start_at_default(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                return a + b
        """)
        mutations = generate_mutations(src)
        assert mutations[0].id == 1

    def test_ids_start_at_custom_value(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                return a + b >= 10
        """)
        mutations = generate_mutations(src, start_id=10)
        assert mutations[0].id == 10
        assert mutations[1].id == 11

    def test_ids_increment_by_one(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(a, b):
                x = a + b
                y = a + b
                return x >= y
        """)
        mutations = generate_mutations(src, start_id=5)
        expected = list(range(5, 5 + len(mutations)))
        assert [m.id for m in mutations] == expected

    def test_single_mutation_id_stored(self):
        mutation = generate_mutation(BANK_SOURCE, mutation_id=42)
        assert mutation.id == 42


# ===========================================================================
# Engine — comments not mutated
# ===========================================================================

class TestCommentsNotMutated:
    def test_inline_comment_with_operator_ignored(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                # if x >= 10: this is a comment
                return 1
        """)
        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutations(src)

    def test_standalone_comment_line_ignored(self, tmp_path):
        src = _write_source(tmp_path, """\
            # x >= 10 would trigger discount
            def f(x):
                return 1
        """)
        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutations(src)

    def test_code_and_comment_on_same_line(self, tmp_path):
        """Only the code operator should be mutated, not the one in the comment."""
        src = _write_source(tmp_path, """\
            def f(x):
                return x >= 10  # also x >= 5?
        """)
        mutations = generate_mutations(src)
        # Exactly one mutation — the tokenizer finds a single '>=' OP token
        assert len(mutations) == 1
        assert mutations[0].operator == ">= \u2192 >"


# ===========================================================================
# Engine — strings not mutated
# ===========================================================================

class TestStringsNotMutated:
    def test_operator_inside_string_ignored(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f():
                msg = "value >= 10"
                return msg
        """)
        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutations(src)

    def test_operator_inside_fstring_ignored(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                return f"result: {x} >= 0"
        """)
        with pytest.raises(ValueError, match="No supported mutation operator"):
            generate_mutations(src)

    def test_operator_inside_docstring_ignored(self, tmp_path):
        src = _write_source(tmp_path, """\
            def f(x):
                \"\"\"Return True if x >= 10.\"\"\"
                return x >= 10
        """)
        mutations = generate_mutations(src)
        # Only the real '>=' in the return statement should be found
        assert len(mutations) == 1


# ===========================================================================
# Engine — write_mutated_project (unchanged behaviour)
# ===========================================================================

class TestWriteMutatedProject:
    def test_creates_temp_directory(self):
        mutation = generate_mutation(BANK_SOURCE)
        tmp_dir = write_mutated_project(mutation, BANK_DIR)
        try:
            assert tmp_dir.exists() and tmp_dir.is_dir()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_temp_dir_contains_test_file(self):
        mutation = generate_mutation(BANK_SOURCE)
        tmp_dir = write_mutated_project(mutation, BANK_DIR)
        try:
            assert (tmp_dir / "test_bank_account.py").exists()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_mutated_source_file_has_changed_operator(self):
        mutation = generate_mutation(BANK_SOURCE)
        tmp_dir = write_mutated_project(mutation, BANK_DIR)
        try:
            mutated_content = (tmp_dir / "bank_account.py").read_text()
            assert "if self._balance > amount:" in mutated_content
            assert "if self._balance >= amount:" not in mutated_content
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_original_source_file_is_unchanged(self):
        mutation = generate_mutation(BANK_SOURCE)
        original_content = BANK_SOURCE.read_text()
        tmp_dir = write_mutated_project(mutation, BANK_DIR)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        assert BANK_SOURCE.read_text() == original_content


# ===========================================================================
# Runner — KILLED / SURVIVED classification
# ===========================================================================

class TestRunTests:
    def test_passing_suite_returns_survived(self, tmp_path):
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
        assert len(result.output) > 0


# ===========================================================================
# MutationReport — score and aggregation
# ===========================================================================

class TestMutationReport:
    def _make_run_result(self, status: str):
        from backend.runner.runner import RunResult
        return RunResult(status=status, exit_code=0 if status == SURVIVED else 1, output="")

    def _make_workflow_result(self, mutation, status: str) -> WorkflowResult:
        return WorkflowResult(mutation=mutation, run_result=self._make_run_result(status))

    def _dummy_mutation(self, id_: int, tmp_path: Path) -> Mutation:
        src = tmp_path / f"s{id_}.py"
        src.write_text(f"def f(): return {id_} + 1\n")
        return generate_mutation(src, mutation_id=id_)

    def test_empty_report_score_is_zero(self):
        report = MutationReport()
        assert report.mutation_score == 0.0

    def test_total_count(self, tmp_path):
        report = MutationReport()
        for i in range(4):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), KILLED)
            )
        assert report.total == 4

    def test_killed_count(self, tmp_path):
        report = MutationReport()
        for i in range(3):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), KILLED)
            )
        report.results.append(
            self._make_workflow_result(self._dummy_mutation(4, tmp_path), SURVIVED)
        )
        assert report.killed == 3
        assert report.survived == 1

    def test_score_75_percent(self, tmp_path):
        """4 total, 3 killed → 75 %."""
        report = MutationReport()
        statuses = [KILLED, KILLED, KILLED, SURVIVED]
        for i, status in enumerate(statuses):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), status)
            )
        assert report.mutation_score == pytest.approx(75.0)

    def test_score_100_percent(self, tmp_path):
        report = MutationReport()
        for i in range(3):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), KILLED)
            )
        assert report.mutation_score == pytest.approx(100.0)

    def test_score_0_percent(self, tmp_path):
        report = MutationReport()
        for i in range(2):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), SURVIVED)
            )
        assert report.mutation_score == pytest.approx(0.0)

    def test_summary_contains_score(self, tmp_path):
        report = MutationReport()
        statuses = [KILLED, KILLED, KILLED, SURVIVED]
        for i, status in enumerate(statuses):
            report.results.append(
                self._make_workflow_result(self._dummy_mutation(i + 1, tmp_path), status)
            )
        s = report.summary()
        assert "75.0%" in s
        assert "Killed" in s or "killed" in s.lower()

    def test_summary_lists_each_mutation(self, tmp_path):
        report = MutationReport()
        report.results.append(
            self._make_workflow_result(self._dummy_mutation(1, tmp_path), KILLED)
        )
        report.results.append(
            self._make_workflow_result(self._dummy_mutation(2, tmp_path), SURVIVED)
        )
        s = report.summary()
        assert KILLED in s
        assert SURVIVED in s


# ===========================================================================
# Single-mutation workflow (backward-compatible)
# ===========================================================================

class TestRunMutationWorkflow:
    def test_demo_project_mutation_survives(self):
        result = run_mutation_workflow(
            source_file=BANK_SOURCE,
            project_dir=BANK_DIR,
        )
        assert result.mutation.operator == ">= \u2192 >"
        assert result.status == SURVIVED

    def test_workflow_cleans_up_temp_dir(self, monkeypatch):
        created_dirs: list[Path] = []
        original_write = write_mutated_project

        def tracking_write(mutation, project_dir):
            tmp_dir = original_write(mutation, project_dir)
            created_dirs.append(tmp_dir)
            return tmp_dir

        monkeypatch.setattr(
            "backend.runner.workflow.write_mutated_project", tracking_write
        )
        run_mutation_workflow(source_file=BANK_SOURCE, project_dir=BANK_DIR)
        assert len(created_dirs) == 1
        assert not created_dirs[0].exists(), "Temp dir was not cleaned up"

    def test_summary_contains_status(self):
        result = run_mutation_workflow(
            source_file=BANK_SOURCE,
            project_dir=BANK_DIR,
        )
        summary = result.summary()
        assert "SURVIVED" in summary or "KILLED" in summary
        assert ">= -> >" in summary


# ===========================================================================
# All-mutations workflow — calculator integration
# ===========================================================================

class TestRunAllMutationsWorkflow:
    def test_calculator_returns_multiple_results(self):
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        assert report.total > 1

    def test_calculator_ids_are_unique(self):
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        ids = [r.mutation.id for r in report.results]
        assert len(ids) == len(set(ids))

    def test_calculator_gte_mutation_survives(self):
        """The >= → > mutation in calculate_discount must SURVIVE (boundary gap)."""
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        gte_results = [
            r for r in report.results
            if r.mutation.operator == ">= \u2192 >"
        ]
        assert len(gte_results) == 1
        assert gte_results[0].status == SURVIVED

    def test_calculator_add_mutation_killed(self):
        """The + → - mutation in the add() function must be KILLED."""
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        add_results = [
            r for r in report.results
            if r.mutation.operator == "+ \u2192 -"
        ]
        # At least one should be killed because test_add_positive_numbers covers it
        assert any(r.status == KILLED for r in add_results)

    def test_calculator_score_is_between_0_and_100(self):
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        assert 0.0 <= report.mutation_score <= 100.0

    def test_calculator_score_partial(self):
        """With the known test gaps, score must be < 100 (>= → > survives)."""
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        assert report.mutation_score < 100.0

    def test_calculator_summary_output(self):
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
        )
        s = report.summary()
        assert "Score" in s
        assert "%" in s
        assert "SURVIVED" in s or "KILLED" in s

    def test_temp_dirs_all_cleaned_up(self, monkeypatch):
        created: list[Path] = []
        original_write = write_mutated_project

        def tracking_write(mutation, project_dir):
            tmp_dir = original_write(mutation, project_dir)
            created.append(tmp_dir)
            return tmp_dir

        monkeypatch.setattr(
            "backend.runner.workflow.write_mutated_project", tracking_write
        )
        run_all_mutations_workflow(source_file=CALC_SOURCE, project_dir=CALC_DIR)
        assert len(created) > 0
        for d in created:
            assert not d.exists(), f"Temp dir not cleaned up: {d}"

    def test_start_id_respected(self):
        report = run_all_mutations_workflow(
            source_file=CALC_SOURCE,
            project_dir=CALC_DIR,
            start_id=100,
        )
        ids = [r.mutation.id for r in report.results]
        assert ids[0] == 100
        assert ids == list(range(100, 100 + len(ids)))
