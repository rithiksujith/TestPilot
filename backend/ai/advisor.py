"""
AI Advisor — first-pass analysis component.

Takes information about a surviving mutation and produces a structured
explanation of the likely test gap: what boundary condition is missing,
why it matters, and a concrete suggested test.

Design
------
This version is deterministic — no external AI service, no network calls,
no database.  Analysis is driven by pattern-matching rules keyed on the
mutation operator and the code context visible in the mutated line.

The advisor accepts Person 2's :class:`~backend.mutations.engine.Mutation`
dataclass directly and never duplicates or reimplements mutation logic.

The analysis contract established here is what Person 1's API layer will
expose to the outside world.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

from backend.mutations.engine import Mutation


# ---------------------------------------------------------------------------
# Output data model
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Structured explanation of a surviving mutation's test gap."""

    mutation_id: int
    explanation: str        # what the operator change means in plain English
    risk: str               # why the gap matters
    missing_behavior: str   # the specific scenario no test exercises
    suggested_test_name: str
    suggested_test: str     # ready-to-run pytest source (indented, importable)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

# Each rule is a dict with:
#   "operator"        — the mutation operator label produced by the engine
#   "line_pattern"    — regex matched against the *original* mutated line
#   "analyze"         — callable(mutation, match) -> AnalysisResult

_RULES: list[dict] = []


def _rule(operator: str, line_pattern: str):
    """Decorator that registers an analysis rule for a given operator."""
    def decorator(fn):
        _RULES.append({
            "operator": operator,
            "line_pattern": re.compile(line_pattern),
            "analyze": fn,
        })
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Rule: >= → > on a balance-vs-amount guard
# ---------------------------------------------------------------------------

@_rule(
    operator=">= \u2192 >",           # ">= → >"
    # Match dotted/attributed identifiers like self._balance and plain names.
    line_pattern=r"if\s+([\w.]+)\s*>=\s*([\w.]+)",
)
def _analyze_gte_to_gt(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)   # e.g. "self._balance"  (captured without self.)
    rhs = match.group(2)   # e.g. "amount"

    # Derive a readable name for the left-hand side.
    lhs_name = lhs.split(".")[-1].lstrip("_")   # "_balance" → "balance"

    # Infer the class / method from the source by scanning for the enclosing
    # def that contains the mutated line — keeps analysis context-aware.
    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )

    # Build the suggested test using the inferred names so it is always
    # concrete and directly runnable against the real module.
    module_stem = mutation.source_file.stem          # e.g. "bank_account"
    import_name = _to_import_name(class_name)        # e.g. "BankAccount"
    test_amount = 100.0

    suggested_test = textwrap.dedent(f"""\
        from {module_stem} import {import_name}


        def test_withdraw_entire_{lhs_name}():
            account = {import_name}({test_amount})
            account.{method_name}({test_amount})
            assert account.{lhs_name} == 0.0
    """)

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes the withdrawal condition from "
            f"`{lhs} >= {rhs}` to `{lhs} > {rhs}`. "
            f"With the original operator, withdrawing exactly the available "
            f"{lhs_name} is allowed. After the mutation, that boundary case "
            f"raises an error instead of succeeding."
        ),
        risk=(
            "An important boundary condition is not protected by the current "
            "test suite. A future refactor could silently introduce this bug "
            "and no test would catch it."
        ),
        missing_behavior=(
            f"No existing test verifies that {method_name}ing exactly the "
            f"available {lhs_name} succeeds. The boundary case "
            f"`{lhs} == {rhs}` is never exercised."
        ),
        suggested_test_name=f"test_withdraw_entire_{lhs_name}",
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _infer_context(source: str, mutated_line_number: int) -> tuple[str, str]:
    """Walk backwards from *mutated_line_number* to find the enclosing class
    and method names.  Returns ``("Unknown", "unknown")`` if not found.
    """
    lines = source.splitlines()
    # Search backwards from the mutated line (1-based → 0-based index).
    class_name = "Unknown"
    method_name = "unknown"

    for i in range(mutated_line_number - 1, -1, -1):
        line = lines[i]
        if method_name == "unknown":
            m = re.match(r"\s+def\s+(\w+)\s*\(", line)
            if m:
                method_name = m.group(1)
        if class_name == "Unknown":
            m = re.match(r"class\s+(\w+)", line)
            if m:
                class_name = m.group(1)
        if class_name != "Unknown" and method_name != "unknown":
            break

    return class_name, method_name


def _to_import_name(class_name: str) -> str:
    """Return the class name as-is — it's already PascalCase from the source."""
    return class_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_surviving_mutation(mutation: Mutation) -> AnalysisResult:
    """Analyse *mutation* and return a structured :class:`AnalysisResult`.

    The function tries each registered rule in order.  The first rule whose
    operator matches *and* whose line pattern matches the original mutated
    line is applied.

    Raises
    ------
    ValueError
        If no rule covers this mutation.  This is intentional: it makes gaps
        in coverage explicit rather than silently returning empty results.
    """
    original_line = mutation.original_line

    for rule in _RULES:
        if rule["operator"] != mutation.operator:
            continue
        m = rule["line_pattern"].search(original_line)
        if m:
            return rule["analyze"](mutation, m)

    raise ValueError(
        f"No analysis rule found for operator '{mutation.operator}' "
        f"on line: {original_line!r}"
    )
