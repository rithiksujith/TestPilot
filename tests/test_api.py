"""
Tests for the TestPilot FastAPI API.

Strategy
--------
* Unit tests use ``unittest.mock.patch`` to replace ``run_all_pipeline`` so
  they run instantly without spawning subprocesses.
* One slow integration test calls the real pipeline end-to-end via the
  TestClient to verify the full stack works together.

All tests use FastAPI's built-in ``TestClient`` (backed by httpx).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.ai.advisor import AnalysisResult
from backend.main import app
from backend.pipeline import PipelineReport, PipelineResult
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
        mutation_id=2,
        source_file=Path(DEMO_SOURCE).resolve(),
        line_number=30,
        operator=">= \u2192 >",
        original_line="        if self._balance >= amount:",
        mutated_line="        if self._balance > amount:",
        status=KILLED,
        pytest_exit_code=1,
        pytest_output="1 failed",
        ai_insight=None,
    )


def _fake_report_survived_only() -> PipelineReport:
    """Report with one SURVIVED mutation."""
    return PipelineReport(results=[_fake_survived_result()])


def _fake_report_killed_only() -> PipelineReport:
    """Report with one KILLED mutation."""
    return PipelineReport(results=[_fake_killed_result()])


def _fake_report_mixed() -> PipelineReport:
    """Report with one SURVIVED and one KILLED mutation."""
    return PipelineReport(results=[_fake_survived_result(), _fake_killed_result()])


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

    def test_empty_body_uses_demo_defaults(self):
        """An empty body {} should reach the pipeline with the demo project defaults."""
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={})

        assert response.status_code == 200
        mock_pipe.assert_called_once()
        call_kwargs = mock_pipe.call_args
        assert "bank_account" in str(call_kwargs)


# ===========================================================================
# POST /api/analyze — aggregate response fields
# ===========================================================================

class TestAnalyzeAggregateFields:
    @pytest.fixture(autouse=True)
    def mock_pipeline(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_mixed()
            self.response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        self.data = self.response.json()

    def test_returns_200(self):
        assert self.response.status_code == 200

    def test_has_total(self):
        assert self.data["total"] == 2

    def test_has_killed(self):
        assert self.data["killed"] == 1

    def test_has_survived(self):
        assert self.data["survived"] == 1

    def test_has_mutation_score(self):
        # 1 killed out of 2 = 50.0
        assert self.data["mutation_score"] == pytest.approx(50.0)

    def test_has_mutations_list(self):
        assert isinstance(self.data["mutations"], list)
        assert len(self.data["mutations"]) == 2


# ===========================================================================
# POST /api/analyze — individual mutation item shape
# ===========================================================================

class TestMutationItemShape:
    @pytest.fixture(autouse=True)
    def mock_pipeline(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            self.response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        self.data = self.response.json()
        self.mutation = self.data["mutations"][0]

    def test_has_id(self):
        assert self.mutation["id"] == 1

    def test_has_source_file(self):
        assert "bank_account" in self.mutation["source_file"]

    def test_has_line_number(self):
        assert self.mutation["line_number"] == 23

    def test_has_operator(self):
        assert ">=" in self.mutation["operator"]
        assert ">" in self.mutation["operator"]

    def test_has_original_line(self):
        assert ">=" in self.mutation["original_line"]

    def test_has_mutated_line(self):
        assert ">" in self.mutation["mutated_line"]

    def test_has_status(self):
        assert self.mutation["status"] == SURVIVED


# ===========================================================================
# POST /api/analyze — ai_insight only on SURVIVED
# ===========================================================================

class TestAiInsightPresence:
    def test_survived_mutation_has_ai_insight(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        mutation = response.json()["mutations"][0]
        assert mutation["ai_insight"] is not None

    def test_killed_mutation_has_no_ai_insight(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_killed_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        mutation = response.json()["mutations"][0]
        assert mutation["ai_insight"] is None

    def test_ai_insight_has_explanation(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        ai = response.json()["mutations"][0]["ai_insight"]
        assert ai["explanation"]

    def test_ai_insight_has_risk(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        ai = response.json()["mutations"][0]["ai_insight"]
        assert ai["risk"]

    def test_ai_insight_has_missing_behavior(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        ai = response.json()["mutations"][0]["ai_insight"]
        assert ai["missing_behavior"]

    def test_ai_insight_has_suggested_test(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        ai = response.json()["mutations"][0]["ai_insight"]
        assert ai["suggested_test"]

    def test_ai_insight_has_suggested_test_name(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        ai = response.json()["mutations"][0]["ai_insight"]
        assert ai["suggested_test_name"]


# ===========================================================================
# POST /api/analyze — pipeline error propagation
# ===========================================================================

class TestAnalyzeErrorHandling:
    def test_pipeline_value_error_returns_422(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.side_effect = ValueError("No supported mutation operator found")
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        assert response.status_code == 422
        assert "No supported mutation operator found" in response.json()["detail"]


# ===========================================================================
# POST /api/analyze — empty mutations list
# ===========================================================================

class TestEmptyMutationsReport:
    def test_empty_report_returns_zeros(self):
        with patch("backend.api.routes.run_all_pipeline") as mock:
            mock.return_value = PipelineReport(results=[])
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        data = response.json()
        assert response.status_code == 200
        assert data["total"] == 0
        assert data["killed"] == 0
        assert data["survived"] == 0
        assert data["mutation_score"] == 0.0
        assert data["mutations"] == []


# ===========================================================================
# POST /api/analyze — source-file discovery (source_file omitted)
# ===========================================================================

class TestAnalyzeWithDiscovery:
    """Tests for the auto-discovery path where source_file is not supplied."""

    def test_project_dir_only_calls_pipeline(self):
        """Omitting source_file should still reach run_all_pipeline via discovery."""
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={
                "project_dir": DEMO_DIR,
            })
        assert response.status_code == 200
        mock_pipe.assert_called_once()

    def test_project_dir_only_discovers_bank_account(self):
        """When source_file is omitted, discovery must resolve to bank_account.py."""
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_survived_only()
            client.post("/api/analyze", json={
                "project_dir": DEMO_DIR,
            })
        call_kwargs = mock_pipe.call_args
        assert "bank_account" in str(call_kwargs)

    def test_project_dir_only_returns_200(self):
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_killed_only()
            response = client.post("/api/analyze", json={
                "project_dir": DEMO_DIR,
            })
        assert response.status_code == 200

    def test_project_dir_only_response_has_mutations(self):
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_killed_only()
            response = client.post("/api/analyze", json={
                "project_dir": DEMO_DIR,
            })
        data = response.json()
        assert "mutations" in data
        assert data["mutations"][0]["status"] in (KILLED, SURVIVED)

    def test_invalid_project_dir_returns_422(self):
        response = client.post("/api/analyze", json={
            "project_dir": "does_not_exist_dir",
        })
        assert response.status_code == 422

    def test_project_dir_with_no_sources_returns_422(self, tmp_path):
        """A project dir containing only test files should yield 422."""
        (tmp_path / "test_only.py").write_text("def test_x(): pass\n")
        response = client.post("/api/analyze", json={
            "project_dir": str(tmp_path),
        })
        assert response.status_code == 422
        assert "No Python source files" in response.json()["detail"]

    def test_discovery_uses_first_sorted_source(self, tmp_path):
        """Exactly which file discovery picks must be the first sorted result."""
        (tmp_path / "aaa.py").write_text("x = 1 >= 0\n")
        (tmp_path / "zzz.py").write_text("y = 2 >= 1\n")
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_killed_only()
            client.post("/api/analyze", json={"project_dir": str(tmp_path)})
        called_source = str(mock_pipe.call_args.kwargs.get("source_file", ""))
        assert "aaa.py" in called_source

    def test_empty_body_uses_discovery(self):
        """An empty body {} must route through discovery (not a hardcoded path)."""
        with patch("backend.api.routes.discover_source_files") as mock_disc, \
             patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_disc.return_value = [Path(DEMO_SOURCE).resolve()]
            mock_pipe.return_value = _fake_report_survived_only()
            response = client.post("/api/analyze", json={})
        assert response.status_code == 200
        mock_disc.assert_called_once()


# ===========================================================================
# POST /api/analyze — explicit source_file still works
# ===========================================================================

class TestAnalyzeWithExplicitSourceFile:
    """Ensure the existing explicit source_file path is fully preserved."""

    def test_explicit_source_file_is_used(self):
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_survived_only()
            client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        called_source = str(mock_pipe.call_args.kwargs.get("source_file", ""))
        assert "bank_account.py" in called_source

    def test_explicit_source_file_does_not_call_discovery(self):
        with patch("backend.api.routes.discover_source_files") as mock_disc, \
             patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_survived_only()
            client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        mock_disc.assert_not_called()

    def test_explicit_nonexistent_source_file_returns_422(self):
        response = client.post("/api/analyze", json={
            "source_file": "ghost_file.py",
            "project_dir": DEMO_DIR,
        })
        assert response.status_code == 422
        assert "source_file not found" in response.json()["detail"]

    def test_returns_200_with_explicit_source_and_project(self):
        with patch("backend.api.routes.run_all_pipeline") as mock_pipe:
            mock_pipe.return_value = _fake_report_killed_only()
            response = client.post("/api/analyze", json={
                "source_file": DEMO_SOURCE,
                "project_dir": DEMO_DIR,
            })
        assert response.status_code == 200


# ===========================================================================
# POST /api/analyze — bank_account end-to-end integration (slow)
# ===========================================================================

class TestAnalyzeIntegration:
    """Calls the real pipeline via the API — spawns pytest in a subprocess."""

    def test_bank_account_returns_200(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert response.status_code == 200

    def test_bank_account_has_total(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        assert response.json()["total"] >= 1

    def test_bank_account_has_mutations_list(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        data = response.json()
        assert isinstance(data["mutations"], list)
        assert len(data["mutations"]) >= 1

    def test_bank_account_has_mutation_score(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        score = response.json()["mutation_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_bank_account_survived_mutation_has_ai_insight(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        mutations = response.json()["mutations"]
        survived = [m for m in mutations if m["status"] == SURVIVED]
        assert len(survived) >= 1
        assert survived[0]["ai_insight"] is not None

    def test_bank_account_killed_mutation_has_no_ai_insight(self):
        response = client.post("/api/analyze", json={
            "source_file": DEMO_SOURCE,
            "project_dir": DEMO_DIR,
        })
        mutations = response.json()["mutations"]
        killed = [m for m in mutations if m["status"] == KILLED]
        # bank_account demo may or may not have killed mutations; only check if present
        for m in killed:
            assert m["ai_insight"] is None


# ===========================================================================
# POST /api/analyze — bank_account end-to-end via discovery (slow)
# ===========================================================================

class TestBankAccountViaDiscovery:
    """Integration tests: run the real pipeline using only project_dir."""

    def test_project_dir_only_returns_200(self):
        response = client.post("/api/analyze", json={
            "project_dir": DEMO_DIR,
        })
        assert response.status_code == 200

    def test_project_dir_only_has_mutations(self):
        response = client.post("/api/analyze", json={
            "project_dir": DEMO_DIR,
        })
        assert len(response.json()["mutations"]) >= 1

    def test_project_dir_only_source_file_is_bank_account(self):
        response = client.post("/api/analyze", json={
            "project_dir": DEMO_DIR,
        })
        mutations = response.json()["mutations"]
        assert all("bank_account" in m["source_file"] for m in mutations)

    def test_project_dir_only_mutation_score_is_float(self):
        response = client.post("/api/analyze", json={
            "project_dir": DEMO_DIR,
        })
        score = response.json()["mutation_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0
