"""
Tests for the TestPilot FastAPI API.

Strategy
--------
* Unit tests use ``unittest.mock.patch`` to replace ``run_pipeline`` so they
  run instantly without spawning subprocesses.
* One slow integration test calls the real pipeline end-to-end via the
  TestClient to verify the full stack works together.

All tests use FastAPI's built-in ``TestClient`` (backed by httpx2).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.ai.advisor import AnalysisResult
from backend.main import app
from backend.pipeline import PipelineResult
from backend.runner.runner import KILLED, SURVIVED

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fake data
# ---------------------------------------------------------------------------

DEMO_SOURCE = "demo_projects/bank_account/bank_account.py"
DEMO_DIR = "demo_projects/bank_account"


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


def _fake_survived_result() -> PipelineResult:
    return PipelineResult(
        mutation_id=1,
        source_file=Path(DEMO_SOURCE).resolve(),
        line_number=23,
        operator=">= \u2192 >",
        original_line="        if self._balance >= amount:",
        mutated_line="        if self._balance > amount:",
        status=SURVIVED,
        pytest_exit_code=0,
        pytest_output="1 passed",
        ai_insight=_fake_analysis(),
    )


def _fake_killed_result() -> PipelineResult:
    return PipelineResult(
        mutation_id=1,
        source_file=Path(DEMO_SOURCE).resolve(),
        line_number=23,
        operator=">= \u2192 >",
        original_line="        if self._balance >= amount:",
        mutated_line="        if self._balance > amount:",
        status=KILLED,
        pytest_exit_code=1,
        pytest_output="1 failed",
        ai_insight=None,
    )


# ===========================================================================
# GET /api/health
# ===========================================================================

class TestHealthEndpoint:
    def test_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_returns_status_ok(self):
        response = client.get("/api/health")
        assert response.json() == {"status": "ok"}

    def test_content_type_is_json(self):
        response = client.get("/api/health")
        assert "application/json" in response.headers["content-type"]


# ===========================================================================
# POST /api/analyze — request validation
# ===========================================================================

class TestAnalyzeRequestValidation:
    def test_missing_source_file_returns_422(self):
        response = client.post("/api/analyze", json={
            "source_file": "does_not_exist.py",
            "project_dir": DEMO_DIR,
        })
        assert response.status_code == 422

    def test_missing_project_dir_returns_422(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": "does_not_exist_dir",
        })
        assert response.status_code == 422

    def test_mutation_id_must_be_positive(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
            "mutation_id": 0,
        })
        assert response.status_code == 422

    def test_empty_body_uses_demo_defaults(self):
        """An empty body {} should reach the pipeline with the demo project defaults."""
        with patch("backend.api.routes.run_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_survived_result()
            response = client.post("/api/analyze", json={})

        assert response.status_code == 200
        mock_pipe.assert_called_once()
        call_kwargs = mock_pipe.call_args
        assert "bank_account" in str(call_kwargs)


# ===========================================================================
# POST /api/analyze — SURVIVED response shape
# ===========================================================================

class TestAnalyzeSurvivedResponse:
    @pytest.fixture(autouse=True)
    def mock_pipeline(self):
        with patch("backend.api.routes.run_pipeline") as mock:
            mock.return_value = _fake_survived_result()
            self.response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        self.data = self.response.json()

    def test_returns_200(self):
        assert self.response.status_code == 200

    def test_has_mutation_id(self):
        assert self.data["mutation_id"] == 1

    def test_has_source_file(self):
        assert "bank_account" in self.data["source_file"]

    def test_has_line_number(self):
        assert self.data["line_number"] == 23

    def test_has_operator(self):
        assert ">=" in self.data["operator"]
        assert ">" in self.data["operator"]

    def test_has_original_line(self):
        assert ">=" in self.data["original_line"]

    def test_has_mutated_line(self):
        assert ">" in self.data["mutated_line"]

    def test_status_is_survived(self):
        assert self.data["status"] == SURVIVED

    def test_mutation_score_is_zero_for_survived(self):
        assert self.data["mutation_score"] == 0.0

    def test_ai_insight_is_present(self):
        assert self.data["ai_insight"] is not None

    def test_ai_insight_has_explanation(self):
        assert self.data["ai_insight"]["explanation"]

    def test_ai_insight_has_risk(self):
        assert self.data["ai_insight"]["risk"]

    def test_ai_insight_has_missing_behavior(self):
        assert self.data["ai_insight"]["missing_behavior"]

    def test_ai_insight_has_suggested_test(self):
        assert self.data["ai_insight"]["suggested_test"]

    def test_ai_insight_has_suggested_test_name(self):
        assert self.data["ai_insight"]["suggested_test_name"]


# ===========================================================================
# POST /api/analyze — KILLED response shape
# ===========================================================================

class TestAnalyzeKilledResponse:
    @pytest.fixture(autouse=True)
    def mock_pipeline(self):
        with patch("backend.api.routes.run_pipeline") as mock:
            mock.return_value = _fake_killed_result()
            self.response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        self.data = self.response.json()

    def test_returns_200(self):
        assert self.response.status_code == 200

    def test_status_is_killed(self):
        assert self.data["status"] == KILLED

    def test_mutation_score_is_one_for_killed(self):
        assert self.data["mutation_score"] == 1.0

    def test_ai_insight_is_null_for_killed(self):
        assert self.data["ai_insight"] is None


# ===========================================================================
# POST /api/analyze — pipeline error propagation
# ===========================================================================

class TestAnalyzeErrorHandling:
    def test_pipeline_value_error_returns_422(self):
        with patch("backend.api.routes.run_pipeline") as mock:
            mock.side_effect = ValueError("No supported mutation operator found")
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        assert response.status_code == 422
        assert "No supported mutation operator found" in response.json()["detail"]


# ===========================================================================
# POST /api/analyze — mutation_id forwarding
# ===========================================================================

class TestMutationIdForwarding:
    def test_mutation_id_forwarded_to_pipeline(self):
        with patch("backend.api.routes.run_pipeline") as mock:
            mock.return_value = _fake_killed_result()
            client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
                "mutation_id": 5,
            })
        _, kwargs = mock.call_args
        assert kwargs.get("mutation_id") == 5


# ===========================================================================
# Real end-to-end integration test (slow — runs subprocess)
# ===========================================================================

class TestAnalyzeIntegration:
    """Calls the real pipeline via the API — spawns pytest in a subprocess."""

    def test_bank_account_returns_survived(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert response.status_code == 200
        assert response.json()["status"] == SURVIVED

    def test_bank_account_operator(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert ">=" in response.json()["operator"]

    def test_bank_account_has_ai_insight(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert response.json()["ai_insight"] is not None

    def test_bank_account_mutation_score_zero(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert response.json()["mutation_score"] == 0.0
