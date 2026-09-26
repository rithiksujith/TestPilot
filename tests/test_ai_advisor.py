"""
Tests for the TestPilot AI Advisor.

All tests use Person 2's generate_mutation() to produce the Mutation input,
so the advisor is always tested against real engine output — not hand-crafted
stubs.  This keeps the contract between the engine and the advisor verified
end-to-end without duplicating mutation logic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.mutations.engine import Mutation, generate_mutation
from backend.ai.advisor import AnalysisResult, analyze_surviving_mutation

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEMO_DIR = Path("demo_projects/bank_account")
DEMO_SOURCE = DEMO_DIR / "bank_account.py"

CALC_DIR = Path("demo_projects/calculator")
CALC_SOURCE = CALC_DIR / "calculator.py"


@pytest.fixture(scope="module")
def bank_account_mutation() -> Mutation:
    """Real Mutation produced by Person 2's engine for the demo project."""
    return generate_mutation(DEMO_SOURCE, mutation_id=1)


@pytest.fixture(scope="module")
def bank_account_analysis(bank_account_mutation: Mutation) -> AnalysisResult:
    """AnalysisResult for the >= → > bank_account mutation."""
    return analyze_surviving_mutation(bank_account_mutation)


@pytest.fixture(scope="module")
def calculator_mutation() -> Mutation:
    """Real Mutation for calculate_discount's >= → > guard."""
    # The >= in calculate_discount is the first mutation opportunity in the file
    # that uses the >= operator; generate_mutations lets us pick by index.
    from backend.mutations.engine import generate_mutations
    mutations = generate_mutations(CALC_SOURCE)
    # find the first >= → > mutation
    for m in mutations:
        if m.operator == ">= \u2192 >":
            return m
    pytest.fail("No >= → > mutation found in calculator.py")


@pytest.fixture(scope="module")
def calculator_analysis(calculator_mutation: Mutation) -> AnalysisResult:
    """AnalysisResult for the calculate_discount >= → > mutation."""
    return analyze_surviving_mutation(calculator_mutation)


# ===========================================================================
# AnalysisResult shape
# ===========================================================================

class TestAnalysisResultShape:
    """The advisor must return all six required fields."""

    def test_returns_analysis_result_instance(self, bank_account_analysis):
        assert isinstance(bank_account_analysis, AnalysisResult)

    def test_mutation_id_matches_input(self, bank_account_mutation, bank_account_analysis):
        assert bank_account_analysis.mutation_id == bank_account_mutation.id

    def test_explanation_is_non_empty_string(self, bank_account_analysis):
        assert isinstance(bank_account_analysis.explanation, str)
        assert len(bank_account_analysis.explanation) > 0

    def test_risk_is_non_empty_string(self, bank_account_analysis):
        assert isinstance(bank_account_analysis.risk, str)
        assert len(bank_account_analysis.risk) > 0

    def test_missing_behavior_is_non_empty_string(self, bank_account_analysis):
        assert isinstance(bank_account_analysis.missing_behavior, str)
        assert len(bank_account_analysis.missing_behavior) > 0

    def test_suggested_test_name_is_non_empty_string(self, bank_account_analysis):
        assert isinstance(bank_account_analysis.suggested_test_name, str)
        assert len(bank_account_analysis.suggested_test_name) > 0

    def test_suggested_test_is_non_empty_string(self, bank_account_analysis):
        assert isinstance(bank_account_analysis.suggested_test, str)
        assert len(bank_account_analysis.suggested_test) > 0


# ===========================================================================
# Explanation content
# ===========================================================================

class TestExplanationContent:
    """Verify the explanation captures the semantic meaning of the mutation."""

    def test_explanation_mentions_withdrawal_condition(self, bank_account_analysis):
        # Must describe what the operator change does in context.
        text = bank_account_analysis.explanation.lower()
        assert "withdrawal" in text or "withdraw" in text or "balance" in text

    def test_explanation_references_both_operators(self, bank_account_analysis):
        # The reader must see both the original and mutated operators.
        assert ">=" in bank_account_analysis.explanation
        assert ">" in bank_account_analysis.explanation

    def test_explanation_mentions_boundary_semantics(self, bank_account_analysis):
        # Must explain that the boundary case (equal) is affected.
        text = bank_account_analysis.explanation.lower()
        assert "equal" in text or "exact" in text or "boundary" in text or "exactly" in text


# ===========================================================================
# Missing behaviour
# ===========================================================================

class TestMissingBehavior:
    """The missing_behavior field must name the unexercised scenario."""

    def test_missing_behavior_identifies_exact_balance_case(self, bank_account_analysis):
        text = bank_account_analysis.missing_behavior.lower()
        # Must mention the concept of withdrawing exactly the balance.
        assert "exact" in text or "entire" in text or "equal" in text or "balance" in text

    def test_missing_behavior_mentions_no_existing_test(self, bank_account_analysis):
        text = bank_account_analysis.missing_behavior.lower()
        assert "no " in text or "not " in text or "never" in text or "missing" in text


# ===========================================================================
# Risk
# ===========================================================================

class TestRisk:
    """risk must communicate why the gap is dangerous."""

    def test_risk_mentions_boundary_or_condition(self, bank_account_analysis):
        text = bank_account_analysis.risk.lower()
        assert "boundary" in text or "condition" in text or "bug" in text or "unprotected" in text or "not protected" in text

    def test_risk_is_different_from_explanation(self, bank_account_analysis):
        # risk and explanation serve different purposes; they must not be identical.
        assert bank_account_analysis.risk != bank_account_analysis.explanation


# ===========================================================================
# Suggested test name
# ===========================================================================

class TestSuggestedTestName:
    def test_name_follows_pytest_convention(self, bank_account_analysis):
        name = bank_account_analysis.suggested_test_name
        assert name.startswith("test_"), f"Name must start with 'test_', got: {name!r}"

    def test_name_is_snake_case(self, bank_account_analysis):
        name = bank_account_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), (
            f"Name must be snake_case, got: {name!r}"
        )

    def test_name_references_withdraw_or_balance(self, bank_account_analysis):
        name = bank_account_analysis.suggested_test_name
        assert "withdraw" in name or "balance" in name, (
            f"Name should reference the tested behaviour, got: {name!r}"
        )


# ===========================================================================
# Suggested test code
# ===========================================================================

class TestSuggestedTestCode:
    def test_suggested_test_imports_bank_account(self, bank_account_analysis):
        assert "bank_account" in bank_account_analysis.suggested_test

    def test_suggested_test_defines_a_function(self, bank_account_analysis):
        assert "def test_" in bank_account_analysis.suggested_test

    def test_suggested_test_contains_an_assertion(self, bank_account_analysis):
        assert "assert" in bank_account_analysis.suggested_test

    def test_suggested_test_is_valid_python(self, bank_account_analysis):
        # compile() raises SyntaxError on invalid Python.
        try:
            compile(bank_account_analysis.suggested_test, "<suggested_test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_suggested_test_name_matches_function_in_code(self, bank_account_analysis):
        # The suggested_test_name must appear as a def in the suggested_test body.
        expected = f"def {bank_account_analysis.suggested_test_name}("
        assert expected in bank_account_analysis.suggested_test, (
            f"Expected '{expected}' in suggested_test body"
        )

    def test_suggested_test_exercises_boundary_withdrawal(self, bank_account_analysis):
        # The test should withdraw the full balance, so the same amount used
        # for construction should appear as the withdraw argument.
        code = bank_account_analysis.suggested_test
        # Look for a withdraw call with a numeric argument.
        assert re.search(r"withdraw\s*\(\s*[\d.]+\s*\)", code), (
            "Suggested test must call withdraw() with a numeric amount"
        )

    def test_suggested_test_checks_zero_balance_after_withdrawal(self, bank_account_analysis):
        code = bank_account_analysis.suggested_test
        assert "== 0" in code or "== 0.0" in code, (
            "Suggested test must assert the balance is 0 after full withdrawal"
        )


# ===========================================================================
# Error handling
# ===========================================================================

class TestAnalyzeErrors:
    def test_raises_for_unsupported_operator(self, bank_account_mutation):
        # Build a mutation with an operator the advisor has no rule for.
        unsupported = Mutation(
            id=99,
            source_file=bank_account_mutation.source_file,
            line_number=bank_account_mutation.line_number,
            operator="<= \u2192 <",          # not implemented
            original_line=bank_account_mutation.original_line,
            mutated_line=bank_account_mutation.mutated_line,
            original_source=bank_account_mutation.original_source,
            mutated_source=bank_account_mutation.mutated_source,
        )

        with pytest.raises(ValueError, match="No analysis rule found"):
            analyze_surviving_mutation(unsupported)


# ===========================================================================
# Calculator: module-level function (calculate_discount)
# ===========================================================================

class TestCalculatorAnalysisShape:
    """The advisor must return all six fields for a module-level function too."""

    def test_returns_analysis_result_instance(self, calculator_analysis):
        assert isinstance(calculator_analysis, AnalysisResult)

    def test_mutation_id_matches_input(self, calculator_mutation, calculator_analysis):
        assert calculator_analysis.mutation_id == calculator_mutation.id


class TestCalculatorExplanation:
    """Explanation must be based on calculate_discount, not BankAccount."""

    def test_explanation_references_both_operators(self, calculator_analysis):
        assert ">=" in calculator_analysis.explanation
        assert ">" in calculator_analysis.explanation

    def test_explanation_does_not_mention_bank_account(self, calculator_analysis):
        text = calculator_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_explanation_mentions_boundary_semantics(self, calculator_analysis):
        text = calculator_analysis.explanation.lower()
        assert "equal" in text or "exact" in text or "boundary" in text or "exactly" in text

    def test_explanation_identifies_boundary_value(self, calculator_analysis):
        # The boundary for calculate_discount is total == 100.
        assert "100" in calculator_analysis.explanation


class TestCalculatorMissingBehavior:
    """missing_behavior must reference calculate_discount, not BankAccount."""

    def test_missing_behavior_mentions_calculate_discount(self, calculator_analysis):
        assert "calculate_discount" in calculator_analysis.missing_behavior

    def test_missing_behavior_identifies_boundary(self, calculator_analysis):
        # Must mention the boundary value or condition.
        text = calculator_analysis.missing_behavior.lower()
        assert "100" in text or "equal" in text or "boundary" in text


class TestCalculatorSuggestedTest:
    """Suggested test must call calculate_discount, not reference BankAccount."""

    def test_suggested_test_name_starts_with_test(self, calculator_analysis):
        assert calculator_analysis.suggested_test_name.startswith("test_")

    def test_suggested_test_name_is_snake_case(self, calculator_analysis):
        name = calculator_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), (
            f"Name must be snake_case, got: {name!r}"
        )

    def test_suggested_test_name_references_calculate_discount(self, calculator_analysis):
        assert "calculate_discount" in calculator_analysis.suggested_test_name

    def test_suggested_test_does_not_import_bank_account(self, calculator_analysis):
        assert "BankAccount" not in calculator_analysis.suggested_test
        assert "bank_account" not in calculator_analysis.suggested_test

    def test_suggested_test_imports_calculate_discount(self, calculator_analysis):
        assert "calculate_discount" in calculator_analysis.suggested_test

    def test_suggested_test_calls_calculate_discount_at_boundary(self, calculator_analysis):
        # Must call calculate_discount with the boundary value 100.
        code = calculator_analysis.suggested_test
        assert re.search(r"calculate_discount\s*\(\s*100\s*\)", code), (
            "Suggested test must call calculate_discount(100)"
        )

    def test_suggested_test_defines_a_function(self, calculator_analysis):
        assert "def test_" in calculator_analysis.suggested_test

    def test_suggested_test_contains_an_assertion(self, calculator_analysis):
        assert "assert" in calculator_analysis.suggested_test

    def test_suggested_test_is_valid_python(self, calculator_analysis):
        try:
            compile(calculator_analysis.suggested_test, "<suggested_test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_suggested_test_name_matches_function_in_code(self, calculator_analysis):
        expected = f"def {calculator_analysis.suggested_test_name}("
        assert expected in calculator_analysis.suggested_test, (
            f"Expected '{expected}' in suggested_test body"
        )

    def test_suggested_test_asserts_expected_value_not_none_check(self, calculator_analysis):
        # The assertion must be a concrete value check, not the weak `is not None`.
        code = calculator_analysis.suggested_test
        assert "is not None" not in code, (
            "Suggested test must not use the weak 'assert result is not None'; "
            "it must assert the expected return value."
        )

    def test_suggested_test_asserts_calculate_discount_100_equals_90(self, calculator_analysis):
        # calculate_discount(100) == 100 * 0.9 == 90; the generated test must
        # verify this exact expected value so the mutation is killed.
        code = calculator_analysis.suggested_test
        assert re.search(r"calculate_discount\s*\(\s*100\s*\)\s*==\s*90", code), (
            "Suggested test must assert calculate_discount(100) == 90"
        )
