"""
Tests for backend/pipeline.py — the integration layer (Person 1).

Strategy
--------
* Use the real demo project so the pipeline is exercised end-to-end.
* Mock run_mutation_workflow + analyze_surviving_mutation in unit tests to keep
  those fast and isolated (no subprocess / no temp directories).
* One slow integration test verifies the real bank_account flow produces the
  expected SURVIVED result with a valid AI insight.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.ai.advisor import AnalysisResult
from backend.mutations.engine import Mutation
from backend.pipeline import PipelineReport, PipelineResult, run_all_pipeline, run_pipeline
from backend.runner.runner import KILLED, SURVIVED
from backend.runner.runner import RunResult
from backend.runner.workflow import MutationReport, WorkflowResult

# ---------------------------------------------------------------------------
# Shared paths (relative to project root)
# ---------------------------------------------------------------------------

DEMO_DIR = Path("demo_projects/bank_account")
DEMO_SOURCE = DEMO_DIR / "bank_account.py"


# ---------------------------------------------------------------------------
# Helpers — build lightweight fakes without touching the real engine
# ---------------------------------------------------------------------------

def _fake_mutation(operator: str = ">= \u2192 >") -> Mutation:
    return Mutation(
        id=1,
        source_file=DEMO_SOURCE.resolve(),
        line_number=23,
        operator=operator,
        original_line="        if self._balance >= amount:",
        mutated_line="        if self._balance > amount:",
        original_source="",
        mutated_source="",
    )


def _fake_run_result(status: str, exit_code: int = 0) -> RunResult:
    return RunResult(status=status, exit_code=exit_code, output="1 passed")


def _fake_workflow_result(status: str) -> WorkflowResult:
    mutation = _fake_mutation()
    run_result = _fake_run_result(
        status=status,
        exit_code=0 if status == SURVIVED else 1,
    )
    return WorkflowResult(mutation=mutation, run_result=run_result)


def _fake_analysis() -> AnalysisResult:
    return AnalysisResult(
        mutation_id=1,
        explanation="The mutation changes >= to >.",
        risk="A boundary condition is unprotected.",
        missing_behavior="No test withdraws exactly the balance.",
        suggested_test_name="test_withdraw_entire_balance",
        suggested_test=(
            "from bank_account import BankAccount\n\n"
            "def test_withdraw_entire_balance():\n"
            "    account = BankAccount(100.0)\n"
            "    account.withdraw(100.0)\n"
            "    assert account.balance == 0.0\n"
        ),
    )


# ===========================================================================
# PipelineResult shape
# ===========================================================================

class TestPipelineResultShape:
    """PipelineResult must expose all expected fields."""

    def setup_method(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()
            self.result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

    def test_returns_pipeline_result(self):
        assert isinstance(self.result, PipelineResult)

    def test_has_mutation_id(self):
        assert self.result.mutation_id == 1

    def test_has_source_file(self):
        assert isinstance(self.result.source_file, Path)

    def test_has_line_number(self):
        assert self.result.line_number == 23

    def test_has_operator(self):
        assert self.result.operator == ">= \u2192 >"

    def test_has_original_line(self):
        assert ">=" in self.result.original_line

    def test_has_mutated_line(self):
        assert ">" in self.result.mutated_line

    def test_has_status(self):
        assert self.result.status in (KILLED, SURVIVED)

    def test_has_pytest_exit_code(self):
        assert isinstance(self.result.pytest_exit_code, int)

    def test_has_pytest_output(self):
        assert isinstance(self.result.pytest_output, str)


# ===========================================================================
# SURVIVED path
# ===========================================================================

class TestSurvivedMutation:
    """For a SURVIVED mutation the pipeline must invoke the advisor and attach
    the AI insight to the result."""

    def test_ai_insight_is_not_none(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()

            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.ai_insight is not None

    def test_advisor_called_with_mutation(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            wf_result = _fake_workflow_result(SURVIVED)
            mock_wf.return_value = wf_result
            mock_ai.return_value = _fake_analysis()

            run_pipeline(DEMO_SOURCE, DEMO_DIR)

        mock_ai.assert_called_once_with(wf_result.mutation)

    def test_ai_insight_fields_present(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()

            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        a = result.ai_insight
        assert a.explanation
        assert a.risk
        assert a.missing_behavior
        assert a.suggested_test
        assert a.suggested_test_name


# ===========================================================================
# KILLED path
# ===========================================================================

class TestKilledMutation:
    """For a KILLED mutation the advisor must NOT be called and ai_insight
    must be None."""

    def test_ai_insight_is_none_for_killed(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(KILLED)
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.ai_insight is None
        mock_ai.assert_not_called()

    def test_status_is_killed(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation"),
        ):
            mock_wf.return_value = _fake_workflow_result(KILLED)
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.status == KILLED


# ===========================================================================
# Mutation ID forwarding
# ===========================================================================

class TestMutationIdForwarding:
    """The mutation_id parameter must be forwarded to run_mutation_workflow."""

    def test_mutation_id_forwarded(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            wf = _fake_workflow_result(KILLED)
            mock_wf.return_value = wf
            run_pipeline(DEMO_SOURCE, DEMO_DIR, mutation_id=7)

        _, kwargs = mock_wf.call_args
        assert kwargs.get("mutation_id") == 7 or mock_wf.call_args[0][2] == 7


# ===========================================================================
# __str__ / display
# ===========================================================================

class TestPipelineResultStr:
    def test_str_contains_status_survived(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert SURVIVED in str(result)

    def test_str_contains_operator(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert ">= ->" in str(result)

    def test_str_contains_ai_insight_for_survived(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = _fake_workflow_result(SURVIVED)
            mock_ai.return_value = _fake_analysis()
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert "AI Insight" in str(result)

    def test_str_no_ai_insight_for_killed(self):
        with (
            patch("backend.pipeline.run_mutation_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation"),
        ):
            mock_wf.return_value = _fake_workflow_result(KILLED)
            result = run_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert "AI Insight" not in str(result)


# ===========================================================================
# Real end-to-end integration test (slow — runs subprocess)
# ===========================================================================

class TestPipelineIntegration:
    """Run the full pipeline against the real demo project.  This executes
    pytest in a subprocess so it is the slowest test in the suite."""

    def test_bank_account_pipeline_survived(self):
        result = run_pipeline(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        assert result.status == SURVIVED

    def test_bank_account_operator(self):
        result = run_pipeline(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        assert result.operator == ">= \u2192 >"

    def test_bank_account_has_ai_insight(self):
        result = run_pipeline(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        assert result.ai_insight is not None

    def test_bank_account_ai_insight_fields_non_empty(self):
        result = run_pipeline(
            source_file=DEMO_SOURCE,
            project_dir=DEMO_DIR,
        )

        a = result.ai_insight
        assert a.explanation
        assert a.risk
        assert a.missing_behavior
        assert a.suggested_test
        assert a.suggested_test_name


# ===========================================================================
# Helpers for multi-mutation tests
# ===========================================================================

def _fake_mutation_n(n: int, operator: str = ">= \u2192 >") -> Mutation:
    """Build a fake Mutation with id=n."""
    return Mutation(
        id=n,
        source_file=DEMO_SOURCE.resolve(),
        line_number=23 + n,
        operator=operator,
        original_line="        if self._balance >= amount:",
        mutated_line="        if self._balance > amount:",
        original_source="",
        mutated_source="",
    )


def _fake_workflow_result_n(n: int, status: str) -> WorkflowResult:
    mutation = _fake_mutation_n(n)
    run_result = _fake_run_result(
        status=status,
        exit_code=0 if status == SURVIVED else 1,
    )
    return WorkflowResult(mutation=mutation, run_result=run_result)


def _fake_mutation_report(statuses: list[str]) -> MutationReport:
    """Build a MutationReport with one WorkflowResult per entry in *statuses*."""
    report = MutationReport()
    for i, status in enumerate(statuses, start=1):
        report.results.append(_fake_workflow_result_n(i, status))
    return report


# ===========================================================================
# run_all_pipeline — PipelineReport shape
# ===========================================================================

class TestRunAllPipelineReport:
    """run_all_pipeline must return a PipelineReport with correct stats."""

    def _run(self, statuses: list[str]) -> PipelineReport:
        mr = _fake_mutation_report(statuses)
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            mock_ai.return_value = _fake_analysis()
            return run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

    def test_returns_pipeline_report(self):
        result = self._run([KILLED, SURVIVED])
        assert isinstance(result, PipelineReport)

    def test_total_count(self):
        result = self._run([KILLED, SURVIVED, KILLED])
        assert result.total == 3

    def test_killed_count(self):
        result = self._run([KILLED, SURVIVED, KILLED])
        assert result.killed == 2

    def test_survived_count(self):
        result = self._run([KILLED, SURVIVED, KILLED])
        assert result.survived == 1

    def test_mutation_score_all_killed(self):
        result = self._run([KILLED, KILLED])
        assert result.mutation_score == 100.0

    def test_mutation_score_partial(self):
        result = self._run([KILLED, SURVIVED])
        assert result.mutation_score == pytest.approx(50.0)

    def test_mutation_score_empty(self):
        result = self._run([])
        assert result.mutation_score == 0.0

    def test_results_list_length(self):
        result = self._run([KILLED, SURVIVED, SURVIVED])
        assert len(result.results) == 3


# ===========================================================================
# run_all_pipeline — survivor analysis
# ===========================================================================

class TestRunAllPipelineSurvivorAnalysis:
    """Advisor must be called only for SURVIVED mutations."""

    def test_advisor_called_for_each_survivor(self):
        mr = _fake_mutation_report([KILLED, SURVIVED, SURVIVED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            mock_ai.return_value = _fake_analysis()
            run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert mock_ai.call_count == 2

    def test_advisor_not_called_for_killed(self):
        mr = _fake_mutation_report([KILLED, KILLED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        mock_ai.assert_not_called()

    def test_survived_result_has_ai_insight(self):
        mr = _fake_mutation_report([SURVIVED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            mock_ai.return_value = _fake_analysis()
            result = run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.results[0].ai_insight is not None

    def test_killed_result_has_no_ai_insight(self):
        mr = _fake_mutation_report([KILLED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            result = run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.results[0].ai_insight is None
        mock_ai.assert_not_called()

    def test_mixed_ai_insight_presence(self):
        """In a mixed report, only SURVIVED entries carry an AI insight."""
        mr = _fake_mutation_report([KILLED, SURVIVED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            mock_ai.return_value = _fake_analysis()
            result = run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.results[0].ai_insight is None   # KILLED
        assert result.results[1].ai_insight is not None  # SURVIVED

    def test_gte_to_gt_operator_preserved(self):
        """The >= → > operator label must be preserved on each PipelineResult."""
        mr = _fake_mutation_report([SURVIVED])
        with (
            patch("backend.pipeline.run_all_mutations_workflow") as mock_wf,
            patch("backend.pipeline.analyze_surviving_mutation") as mock_ai,
        ):
            mock_wf.return_value = mr
            mock_ai.return_value = _fake_analysis()
            result = run_all_pipeline(DEMO_SOURCE, DEMO_DIR)

        assert result.results[0].operator == ">= \u2192 >"
