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


# ===========================================================================
# score_checker: shared fixtures for the four new operators
# ===========================================================================

SCORE_DIR = Path("demo_projects/score_checker")
SCORE_SOURCE = SCORE_DIR / "score_checker.py"


def _score_mutation(operator_label: str) -> "Mutation":
    """Return the first mutation in score_checker.py with the given operator."""
    from backend.mutations.engine import generate_mutations
    for m in generate_mutations(SCORE_SOURCE):
        if m.operator == operator_label:
            return m
    pytest.fail(f"No {operator_label!r} mutation found in score_checker.py")


# ---------------------------------------------------------------------------
# Helpers to get specific mutations by operator *and* enclosing function name
# ---------------------------------------------------------------------------

def _score_mutation_for(operator_label: str, func_name: str) -> "Mutation":
    """Return the mutation in score_checker.py matching operator *and* the
    enclosing function/method *func_name*."""
    from backend.mutations.engine import generate_mutations
    from backend.ai.advisor import _infer_context
    for m in generate_mutations(SCORE_SOURCE):
        if m.operator == operator_label:
            _, meth = _infer_context(m.original_source, m.line_number)
            if meth == func_name:
                return m
    pytest.fail(
        f"No {operator_label!r} mutation inside '{func_name}' in score_checker.py"
    )


# ===========================================================================
# Operator: > → >=  (module-level function: is_high_score)
# ===========================================================================

@pytest.fixture(scope="module")
def gt_to_gte_func_mutation() -> "Mutation":
    return _score_mutation_for("> \u2192 >=", "is_high_score")


@pytest.fixture(scope="module")
def gt_to_gte_func_analysis(gt_to_gte_func_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(gt_to_gte_func_mutation)


@pytest.fixture(scope="module")
def gt_to_gte_method_mutation() -> "Mutation":
    return _score_mutation_for("> \u2192 >=", "is_passing")


@pytest.fixture(scope="module")
def gt_to_gte_method_analysis(gt_to_gte_method_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(gt_to_gte_method_mutation)


class TestGtToGteAnalysisShape:
    """AnalysisResult must have all required fields for > → >= mutations."""

    def test_func_returns_analysis_result(self, gt_to_gte_func_analysis):
        assert isinstance(gt_to_gte_func_analysis, AnalysisResult)

    def test_func_mutation_id_matches(self, gt_to_gte_func_mutation, gt_to_gte_func_analysis):
        assert gt_to_gte_func_analysis.mutation_id == gt_to_gte_func_mutation.id

    def test_method_returns_analysis_result(self, gt_to_gte_method_analysis):
        assert isinstance(gt_to_gte_method_analysis, AnalysisResult)

    def test_method_mutation_id_matches(self, gt_to_gte_method_mutation, gt_to_gte_method_analysis):
        assert gt_to_gte_method_analysis.mutation_id == gt_to_gte_method_mutation.id


class TestGtToGteExplanation:
    def test_func_explanation_mentions_both_operators(self, gt_to_gte_func_analysis):
        assert ">" in gt_to_gte_func_analysis.explanation
        assert ">=" in gt_to_gte_func_analysis.explanation

    def test_func_explanation_mentions_boundary(self, gt_to_gte_func_analysis):
        text = gt_to_gte_func_analysis.explanation.lower()
        assert "equal" in text or "boundary" in text or "exact" in text

    def test_func_explanation_no_bank_account(self, gt_to_gte_func_analysis):
        text = gt_to_gte_func_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_method_explanation_mentions_both_operators(self, gt_to_gte_method_analysis):
        assert ">" in gt_to_gte_method_analysis.explanation
        assert ">=" in gt_to_gte_method_analysis.explanation

    def test_method_explanation_no_bank_account(self, gt_to_gte_method_analysis):
        text = gt_to_gte_method_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text


class TestGtToGteMissingBehavior:
    def test_func_missing_behavior_mentions_function(self, gt_to_gte_func_analysis):
        assert "is_high_score" in gt_to_gte_func_analysis.missing_behavior

    def test_func_missing_behavior_mentions_gap(self, gt_to_gte_func_analysis):
        text = gt_to_gte_func_analysis.missing_behavior.lower()
        assert "no " in text or "not " in text or "never" in text or "missing" in text

    def test_method_missing_behavior_mentions_function(self, gt_to_gte_method_analysis):
        assert "is_passing" in gt_to_gte_method_analysis.missing_behavior


class TestGtToGteSuggestedTest:
    def test_func_test_name_starts_with_test(self, gt_to_gte_func_analysis):
        assert gt_to_gte_func_analysis.suggested_test_name.startswith("test_")

    def test_func_test_name_is_snake_case(self, gt_to_gte_func_analysis):
        name = gt_to_gte_func_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), f"Not snake_case: {name!r}"

    def test_func_test_name_references_function(self, gt_to_gte_func_analysis):
        assert "is_high_score" in gt_to_gte_func_analysis.suggested_test_name

    def test_func_test_imports_function(self, gt_to_gte_func_analysis):
        assert "is_high_score" in gt_to_gte_func_analysis.suggested_test

    def test_func_test_no_bank_account(self, gt_to_gte_func_analysis):
        assert "BankAccount" not in gt_to_gte_func_analysis.suggested_test
        assert "bank_account" not in gt_to_gte_func_analysis.suggested_test

    def test_func_test_is_valid_python(self, gt_to_gte_func_analysis):
        try:
            compile(gt_to_gte_func_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_func_test_defines_a_function(self, gt_to_gte_func_analysis):
        assert "def test_" in gt_to_gte_func_analysis.suggested_test

    def test_func_test_contains_assertion(self, gt_to_gte_func_analysis):
        assert "assert" in gt_to_gte_func_analysis.suggested_test

    def test_func_test_name_matches_def(self, gt_to_gte_func_analysis):
        expected = f"def {gt_to_gte_func_analysis.suggested_test_name}("
        assert expected in gt_to_gte_func_analysis.suggested_test

    def test_func_test_no_unknown(self, gt_to_gte_func_analysis):
        assert "Unknown" not in gt_to_gte_func_analysis.suggested_test

    def test_method_test_name_references_function(self, gt_to_gte_method_analysis):
        assert "is_passing" in gt_to_gte_method_analysis.suggested_test_name

    def test_method_test_imports_scoreboard(self, gt_to_gte_method_analysis):
        assert "ScoreBoard" in gt_to_gte_method_analysis.suggested_test

    def test_method_test_no_bank_account(self, gt_to_gte_method_analysis):
        assert "BankAccount" not in gt_to_gte_method_analysis.suggested_test
        assert "bank_account" not in gt_to_gte_method_analysis.suggested_test

    def test_method_test_is_valid_python(self, gt_to_gte_method_analysis):
        try:
            compile(gt_to_gte_method_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_method_test_no_self_reference(self, gt_to_gte_method_analysis):
        # The test must not reference 'self._...' outside the class
        assert "self._" not in gt_to_gte_method_analysis.suggested_test

    def test_method_test_no_unknown(self, gt_to_gte_method_analysis):
        assert "Unknown" not in gt_to_gte_method_analysis.suggested_test


# ===========================================================================
# Operator: == → !=  (module-level: grade_label; class-method: is_exact_pass)
# ===========================================================================

@pytest.fixture(scope="module")
def eq_to_neq_func_mutation() -> "Mutation":
    return _score_mutation_for("== \u2192 !=", "grade_label")


@pytest.fixture(scope="module")
def eq_to_neq_func_analysis(eq_to_neq_func_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(eq_to_neq_func_mutation)


@pytest.fixture(scope="module")
def eq_to_neq_method_mutation() -> "Mutation":
    return _score_mutation_for("== \u2192 !=", "is_exact_pass")


@pytest.fixture(scope="module")
def eq_to_neq_method_analysis(eq_to_neq_method_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(eq_to_neq_method_mutation)


class TestEqToNeqAnalysisShape:
    def test_func_returns_analysis_result(self, eq_to_neq_func_analysis):
        assert isinstance(eq_to_neq_func_analysis, AnalysisResult)

    def test_method_returns_analysis_result(self, eq_to_neq_method_analysis):
        assert isinstance(eq_to_neq_method_analysis, AnalysisResult)


class TestEqToNeqExplanation:
    def test_func_explanation_mentions_both_operators(self, eq_to_neq_func_analysis):
        assert "==" in eq_to_neq_func_analysis.explanation
        assert "!=" in eq_to_neq_func_analysis.explanation

    def test_func_explanation_mentions_inversion(self, eq_to_neq_func_analysis):
        text = eq_to_neq_func_analysis.explanation.lower()
        assert "invert" in text or "only when" in text or "exact" in text or "every" in text

    def test_func_explanation_no_bank_account(self, eq_to_neq_func_analysis):
        text = eq_to_neq_func_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_method_explanation_no_bank_account(self, eq_to_neq_method_analysis):
        text = eq_to_neq_method_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text


class TestEqToNeqMissingBehavior:
    def test_func_missing_behavior_mentions_function(self, eq_to_neq_func_analysis):
        assert "grade_label" in eq_to_neq_func_analysis.missing_behavior

    def test_func_missing_behavior_mentions_gap(self, eq_to_neq_func_analysis):
        text = eq_to_neq_func_analysis.missing_behavior.lower()
        assert "no " in text or "not " in text or "never" in text

    def test_method_missing_behavior_mentions_function(self, eq_to_neq_method_analysis):
        assert "is_exact_pass" in eq_to_neq_method_analysis.missing_behavior


class TestEqToNeqSuggestedTest:
    def test_func_test_name_starts_with_test(self, eq_to_neq_func_analysis):
        assert eq_to_neq_func_analysis.suggested_test_name.startswith("test_")

    def test_func_test_name_is_snake_case(self, eq_to_neq_func_analysis):
        name = eq_to_neq_func_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), f"Not snake_case: {name!r}"

    def test_func_test_name_references_function(self, eq_to_neq_func_analysis):
        assert "grade_label" in eq_to_neq_func_analysis.suggested_test_name

    def test_func_test_imports_function(self, eq_to_neq_func_analysis):
        assert "grade_label" in eq_to_neq_func_analysis.suggested_test

    def test_func_test_no_bank_account(self, eq_to_neq_func_analysis):
        assert "BankAccount" not in eq_to_neq_func_analysis.suggested_test
        assert "bank_account" not in eq_to_neq_func_analysis.suggested_test

    def test_func_test_is_valid_python(self, eq_to_neq_func_analysis):
        try:
            compile(eq_to_neq_func_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_func_test_defines_a_function(self, eq_to_neq_func_analysis):
        assert "def test_" in eq_to_neq_func_analysis.suggested_test

    def test_func_test_contains_assertion(self, eq_to_neq_func_analysis):
        assert "assert" in eq_to_neq_func_analysis.suggested_test

    def test_func_test_name_matches_def(self, eq_to_neq_func_analysis):
        expected = f"def {eq_to_neq_func_analysis.suggested_test_name}("
        assert expected in eq_to_neq_func_analysis.suggested_test

    def test_func_test_calls_grade_label(self, eq_to_neq_func_analysis):
        assert "grade_label" in eq_to_neq_func_analysis.suggested_test

    def test_func_test_no_unknown(self, eq_to_neq_func_analysis):
        assert "Unknown" not in eq_to_neq_func_analysis.suggested_test

    def test_method_test_imports_scoreboard(self, eq_to_neq_method_analysis):
        assert "ScoreBoard" in eq_to_neq_method_analysis.suggested_test

    def test_method_test_no_bank_account(self, eq_to_neq_method_analysis):
        assert "BankAccount" not in eq_to_neq_method_analysis.suggested_test

    def test_method_test_is_valid_python(self, eq_to_neq_method_analysis):
        try:
            compile(eq_to_neq_method_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_method_test_no_self_reference(self, eq_to_neq_method_analysis):
        assert "self._" not in eq_to_neq_method_analysis.suggested_test

    def test_method_test_no_unknown(self, eq_to_neq_method_analysis):
        assert "Unknown" not in eq_to_neq_method_analysis.suggested_test


# ===========================================================================
# Operator: != → ==  (module-level: needs_review; class-method: is_failed)
# ===========================================================================

@pytest.fixture(scope="module")
def neq_to_eq_func_mutation() -> "Mutation":
    return _score_mutation_for("!= \u2192 ==", "needs_review")


@pytest.fixture(scope="module")
def neq_to_eq_func_analysis(neq_to_eq_func_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(neq_to_eq_func_mutation)


@pytest.fixture(scope="module")
def neq_to_eq_method_mutation() -> "Mutation":
    return _score_mutation_for("!= \u2192 ==", "is_failed")


@pytest.fixture(scope="module")
def neq_to_eq_method_analysis(neq_to_eq_method_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(neq_to_eq_method_mutation)


class TestNeqToEqAnalysisShape:
    def test_func_returns_analysis_result(self, neq_to_eq_func_analysis):
        assert isinstance(neq_to_eq_func_analysis, AnalysisResult)

    def test_method_returns_analysis_result(self, neq_to_eq_method_analysis):
        assert isinstance(neq_to_eq_method_analysis, AnalysisResult)


class TestNeqToEqExplanation:
    def test_func_explanation_mentions_both_operators(self, neq_to_eq_func_analysis):
        assert "!=" in neq_to_eq_func_analysis.explanation
        assert "==" in neq_to_eq_func_analysis.explanation

    def test_func_explanation_mentions_inversion(self, neq_to_eq_func_analysis):
        text = neq_to_eq_func_analysis.explanation.lower()
        assert "invert" in text or "whenever" in text or "only when" in text or "run" in text

    def test_func_explanation_no_bank_account(self, neq_to_eq_func_analysis):
        text = neq_to_eq_func_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_method_explanation_no_bank_account(self, neq_to_eq_method_analysis):
        text = neq_to_eq_method_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text


class TestNeqToEqMissingBehavior:
    def test_func_missing_behavior_mentions_function(self, neq_to_eq_func_analysis):
        assert "needs_review" in neq_to_eq_func_analysis.missing_behavior

    def test_func_missing_behavior_mentions_gap(self, neq_to_eq_func_analysis):
        text = neq_to_eq_func_analysis.missing_behavior.lower()
        assert "no " in text or "not " in text or "never" in text

    def test_method_missing_behavior_mentions_function(self, neq_to_eq_method_analysis):
        assert "is_failed" in neq_to_eq_method_analysis.missing_behavior


class TestNeqToEqSuggestedTest:
    def test_func_test_name_starts_with_test(self, neq_to_eq_func_analysis):
        assert neq_to_eq_func_analysis.suggested_test_name.startswith("test_")

    def test_func_test_name_is_snake_case(self, neq_to_eq_func_analysis):
        name = neq_to_eq_func_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), f"Not snake_case: {name!r}"

    def test_func_test_name_references_function(self, neq_to_eq_func_analysis):
        assert "needs_review" in neq_to_eq_func_analysis.suggested_test_name

    def test_func_test_imports_function(self, neq_to_eq_func_analysis):
        assert "needs_review" in neq_to_eq_func_analysis.suggested_test

    def test_func_test_no_bank_account(self, neq_to_eq_func_analysis):
        assert "BankAccount" not in neq_to_eq_func_analysis.suggested_test
        assert "bank_account" not in neq_to_eq_func_analysis.suggested_test

    def test_func_test_is_valid_python(self, neq_to_eq_func_analysis):
        try:
            compile(neq_to_eq_func_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_func_test_defines_a_function(self, neq_to_eq_func_analysis):
        assert "def test_" in neq_to_eq_func_analysis.suggested_test

    def test_func_test_contains_assertion(self, neq_to_eq_func_analysis):
        assert "assert" in neq_to_eq_func_analysis.suggested_test

    def test_func_test_name_matches_def(self, neq_to_eq_func_analysis):
        expected = f"def {neq_to_eq_func_analysis.suggested_test_name}("
        assert expected in neq_to_eq_func_analysis.suggested_test

    def test_func_test_no_unknown(self, neq_to_eq_func_analysis):
        assert "Unknown" not in neq_to_eq_func_analysis.suggested_test

    def test_method_test_imports_scoreboard(self, neq_to_eq_method_analysis):
        assert "ScoreBoard" in neq_to_eq_method_analysis.suggested_test

    def test_method_test_no_bank_account(self, neq_to_eq_method_analysis):
        assert "BankAccount" not in neq_to_eq_method_analysis.suggested_test

    def test_method_test_is_valid_python(self, neq_to_eq_method_analysis):
        try:
            compile(neq_to_eq_method_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_method_test_no_self_reference(self, neq_to_eq_method_analysis):
        assert "self._" not in neq_to_eq_method_analysis.suggested_test

    def test_method_test_no_unknown(self, neq_to_eq_method_analysis):
        assert "Unknown" not in neq_to_eq_method_analysis.suggested_test


# ===========================================================================
# Operator: + → -  (module-level: total_score; class-method: combined)
# ===========================================================================

@pytest.fixture(scope="module")
def add_to_sub_func_mutation() -> "Mutation":
    return _score_mutation_for("+ \u2192 -", "total_score")


@pytest.fixture(scope="module")
def add_to_sub_func_analysis(add_to_sub_func_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(add_to_sub_func_mutation)


@pytest.fixture(scope="module")
def add_to_sub_method_mutation() -> "Mutation":
    return _score_mutation_for("+ \u2192 -", "combined")


@pytest.fixture(scope="module")
def add_to_sub_method_analysis(add_to_sub_method_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(add_to_sub_method_mutation)


@pytest.fixture(scope="module")
def add_to_sub_calc_mutation() -> "Mutation":
    """The + → - mutation in calculator.py (add function)."""
    from backend.mutations.engine import generate_mutations
    for m in generate_mutations(CALC_SOURCE):
        if m.operator == "+ \u2192 -":
            return m
    pytest.fail("No + → - mutation found in calculator.py")


@pytest.fixture(scope="module")
def add_to_sub_calc_analysis(add_to_sub_calc_mutation) -> "AnalysisResult":
    return analyze_surviving_mutation(add_to_sub_calc_mutation)


class TestAddToSubAnalysisShape:
    def test_func_returns_analysis_result(self, add_to_sub_func_analysis):
        assert isinstance(add_to_sub_func_analysis, AnalysisResult)

    def test_method_returns_analysis_result(self, add_to_sub_method_analysis):
        assert isinstance(add_to_sub_method_analysis, AnalysisResult)

    def test_calc_returns_analysis_result(self, add_to_sub_calc_analysis):
        assert isinstance(add_to_sub_calc_analysis, AnalysisResult)


class TestAddToSubExplanation:
    def test_func_explanation_mentions_operators(self, add_to_sub_func_analysis):
        assert "+" in add_to_sub_func_analysis.explanation
        assert "-" in add_to_sub_func_analysis.explanation

    def test_func_explanation_mentions_sum_or_subtract(self, add_to_sub_func_analysis):
        text = add_to_sub_func_analysis.explanation.lower()
        assert "sum" in text or "add" in text or "subtract" in text

    def test_func_explanation_no_bank_account(self, add_to_sub_func_analysis):
        text = add_to_sub_func_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_method_explanation_no_bank_account(self, add_to_sub_method_analysis):
        text = add_to_sub_method_analysis.explanation.lower()
        assert "bankaccount" not in text and "bank_account" not in text

    def test_calc_explanation_mentions_add(self, add_to_sub_calc_analysis):
        assert "add" in add_to_sub_calc_analysis.explanation


class TestAddToSubMissingBehavior:
    def test_func_missing_behavior_mentions_function(self, add_to_sub_func_analysis):
        assert "total_score" in add_to_sub_func_analysis.missing_behavior

    def test_func_missing_behavior_mentions_gap(self, add_to_sub_func_analysis):
        text = add_to_sub_func_analysis.missing_behavior.lower()
        assert "no " in text or "not " in text or "never" in text

    def test_method_missing_behavior_mentions_function(self, add_to_sub_method_analysis):
        assert "combined" in add_to_sub_method_analysis.missing_behavior

    def test_calc_missing_behavior_mentions_add(self, add_to_sub_calc_analysis):
        assert "add" in add_to_sub_calc_analysis.missing_behavior


class TestAddToSubSuggestedTest:
    def test_func_test_name_starts_with_test(self, add_to_sub_func_analysis):
        assert add_to_sub_func_analysis.suggested_test_name.startswith("test_")

    def test_func_test_name_is_snake_case(self, add_to_sub_func_analysis):
        name = add_to_sub_func_analysis.suggested_test_name
        assert re.match(r"^[a-z_][a-z0-9_]*$", name), f"Not snake_case: {name!r}"

    def test_func_test_name_references_function(self, add_to_sub_func_analysis):
        assert "total_score" in add_to_sub_func_analysis.suggested_test_name

    def test_func_test_imports_function(self, add_to_sub_func_analysis):
        assert "total_score" in add_to_sub_func_analysis.suggested_test

    def test_func_test_no_bank_account(self, add_to_sub_func_analysis):
        assert "BankAccount" not in add_to_sub_func_analysis.suggested_test
        assert "bank_account" not in add_to_sub_func_analysis.suggested_test

    def test_func_test_is_valid_python(self, add_to_sub_func_analysis):
        try:
            compile(add_to_sub_func_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_func_test_contains_assertion(self, add_to_sub_func_analysis):
        assert "assert" in add_to_sub_func_analysis.suggested_test

    def test_func_test_name_matches_def(self, add_to_sub_func_analysis):
        expected = f"def {add_to_sub_func_analysis.suggested_test_name}("
        assert expected in add_to_sub_func_analysis.suggested_test

    def test_func_test_no_unknown(self, add_to_sub_func_analysis):
        assert "Unknown" not in add_to_sub_func_analysis.suggested_test

    def test_func_test_asserts_concrete_value(self, add_to_sub_func_analysis):
        # Must assert a concrete numeric value, not `is not None`
        assert "is not None" not in add_to_sub_func_analysis.suggested_test
        assert "==" in add_to_sub_func_analysis.suggested_test

    def test_method_test_imports_scoreboard(self, add_to_sub_method_analysis):
        assert "ScoreBoard" in add_to_sub_method_analysis.suggested_test

    def test_method_test_no_bank_account(self, add_to_sub_method_analysis):
        assert "BankAccount" not in add_to_sub_method_analysis.suggested_test

    def test_method_test_is_valid_python(self, add_to_sub_method_analysis):
        try:
            compile(add_to_sub_method_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_method_test_no_unknown(self, add_to_sub_method_analysis):
        assert "Unknown" not in add_to_sub_method_analysis.suggested_test

    def test_calc_test_imports_add(self, add_to_sub_calc_analysis):
        assert "add" in add_to_sub_calc_analysis.suggested_test

    def test_calc_test_is_valid_python(self, add_to_sub_calc_analysis):
        try:
            compile(add_to_sub_calc_analysis.suggested_test, "<test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"Suggested test is not valid Python: {exc}")

    def test_calc_test_asserts_concrete_value(self, add_to_sub_calc_analysis):
        assert "is not None" not in add_to_sub_calc_analysis.suggested_test
        assert "==" in add_to_sub_calc_analysis.suggested_test


# ===========================================================================
# No-BankAccount / no-Unknown cross-operator guard tests
# ===========================================================================

class TestNoBankAccountContamination:
    """Generated analysis must never reference BankAccount or 'Unknown' for
    mutations that have nothing to do with BankAccount."""

    def test_gt_to_gte_func_no_bank_account_in_all_fields(
        self, gt_to_gte_func_analysis
    ):
        for field in [
            gt_to_gte_func_analysis.explanation,
            gt_to_gte_func_analysis.missing_behavior,
            gt_to_gte_func_analysis.risk,
            gt_to_gte_func_analysis.suggested_test,
            gt_to_gte_func_analysis.suggested_test_name,
        ]:
            assert "BankAccount" not in field
            assert "bank_account" not in field
            assert "Unknown" not in field

    def test_eq_to_neq_func_no_bank_account_in_all_fields(
        self, eq_to_neq_func_analysis
    ):
        for field in [
            eq_to_neq_func_analysis.explanation,
            eq_to_neq_func_analysis.missing_behavior,
            eq_to_neq_func_analysis.risk,
            eq_to_neq_func_analysis.suggested_test,
            eq_to_neq_func_analysis.suggested_test_name,
        ]:
            assert "BankAccount" not in field
            assert "bank_account" not in field
            assert "Unknown" not in field

    def test_neq_to_eq_func_no_bank_account_in_all_fields(
        self, neq_to_eq_func_analysis
    ):
        for field in [
            neq_to_eq_func_analysis.explanation,
            neq_to_eq_func_analysis.missing_behavior,
            neq_to_eq_func_analysis.risk,
            neq_to_eq_func_analysis.suggested_test,
            neq_to_eq_func_analysis.suggested_test_name,
        ]:
            assert "BankAccount" not in field
            assert "bank_account" not in field
            assert "Unknown" not in field

    def test_add_to_sub_func_no_bank_account_in_all_fields(
        self, add_to_sub_func_analysis
    ):
        for field in [
            add_to_sub_func_analysis.explanation,
            add_to_sub_func_analysis.missing_behavior,
            add_to_sub_func_analysis.risk,
            add_to_sub_func_analysis.suggested_test,
            add_to_sub_func_analysis.suggested_test_name,
        ]:
            assert "BankAccount" not in field
            assert "bank_account" not in field
            assert "Unknown" not in field


# ===========================================================================
# Regression tests: Bug 1 — + → - must not generate wrong argument count
#                   Bug 2 — self.* boundary must not be presented as hardcoded 50
# ===========================================================================

class TestAddToSubMethodArityRegression:
    """Bug 1: _analyze_add_to_sub must not call obj.method(3, 2) for a
    single-parameter method like ScoreBoard.combined(self, extra)."""

    def test_combined_test_calls_method_with_one_argument(
        self, add_to_sub_method_analysis
    ):
        # The generated test must call combined() with exactly one argument,
        # not two — combined(self, extra) only accepts one user argument.
        code = add_to_sub_method_analysis.suggested_test
        # Reject any call of the form combined(x, y)
        import re as _re
        assert not _re.search(r"combined\s*\(\s*\w+\s*,\s*\w+\s*\)", code), (
            "combined() takes one argument; generated test must not pass two"
        )

    def test_combined_test_is_valid_python(self, add_to_sub_method_analysis):
        # The generated test must compile without SyntaxError even if it is a
        # contextual suggestion (e.g. using pass).
        try:
            compile(add_to_sub_method_analysis.suggested_test, "<combined_test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"combined() suggested test is not valid Python: {exc}")


class TestGtToGteSelfBoundaryRegression:
    """Bug 2: when the RHS is self.<attr>, the probe used in the generated
    test must be the actual constructor default, not an arbitrary 50."""

    def test_is_passing_probe_is_not_bare_50(self, gt_to_gte_method_analysis):
        # The generated test should use the inferred default (50.0) clearly
        # attributed to the constructor, NOT silently present a magic 50.
        # Either it uses the inferred value *with* an explanatory comment, or
        # it emits a contextual suggestion — it must NOT silently use 50
        # as though it were the known boundary.
        code = gt_to_gte_method_analysis.suggested_test
        # If "50" appears, the test comment must explain why (inferred default
        # or contextual marker) — i.e. the word "contextual" or "default"
        # must also be present.
        import re as _re
        has_50 = bool(_re.search(r"\b50\b", code))
        if has_50:
            assert "default" in code or "contextual" in code, (
                "Probe value 50 appears without any explanation of where it "
                "comes from; the test silently presents an arbitrary value as "
                "the boundary."
            )

    def test_is_passing_test_is_valid_python(self, gt_to_gte_method_analysis):
        try:
            compile(gt_to_gte_method_analysis.suggested_test, "<is_passing_test>", "exec")
        except SyntaxError as exc:
            pytest.fail(f"is_passing() suggested test is not valid Python: {exc}")
