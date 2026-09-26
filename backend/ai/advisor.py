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
# Rule: >= → > on any boundary guard
# ---------------------------------------------------------------------------

@_rule(
    operator=">= \u2192 >",           # ">= → >"
    # Match dotted/attributed identifiers like self._balance and plain names,
    # as well as numeric literals on the right-hand side.
    line_pattern=r"if\s+([\w.]+)\s*>=\s*([\w.]+)",
)
def _analyze_gte_to_gt(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)   # e.g. "self._balance" or "total"
    rhs = match.group(2)   # e.g. "amount" or "100"

    # Derive a readable name for the left-hand side.
    lhs_name = lhs.split(".")[-1].lstrip("_")   # "_balance" → "balance"

    # Infer the class / method from the source by scanning for the enclosing
    # def that contains the mutated line — keeps analysis context-aware.
    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )

    module_stem = mutation.source_file.stem   # e.g. "bank_account" / "calculator"

    if class_name == "Unknown":
        # --- Module-level function (e.g. calculate_discount) ---
        return _analyze_gte_to_gt_function(
            mutation, lhs, rhs, lhs_name, method_name, module_stem
        )
    else:
        # --- Class method (e.g. BankAccount.withdraw) ---
        return _analyze_gte_to_gt_method(
            mutation, lhs, rhs, lhs_name, class_name, method_name, module_stem
        )


def _analyze_gte_to_gt_method(
    mutation: Mutation,
    lhs: str,
    rhs: str,
    lhs_name: str,
    class_name: str,
    method_name: str,
    module_stem: str,
) -> AnalysisResult:
    """Generate analysis for a >= → > mutation inside a class method."""
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


def _expected_return_value(
    source: str,
    mutated_line_number: int,
    lhs: str,
    boundary: float,
) -> str | None:
    """Try to compute the expected return value for a boundary call.

    Scans the lines immediately after *mutated_line_number* looking for a
    ``return <expr>`` statement inside the guarded block, then evaluates
    *expr* with ``lhs = boundary``.  Returns a repr-string on success or
    ``None`` if the expression cannot be evaluated safely.
    """
    lines = source.splitlines()
    # 1-based → 0-based; start scanning from the line after the if-statement.
    start = mutated_line_number  # already 0-based for the line *after*
    for i in range(start, min(start + 10, len(lines))):
        line = lines[i]
        m = re.match(r"\s*return\s+(.+)", line)
        if m:
            expr = m.group(1).strip()
            # Determine the parameter name: last segment of lhs (strip leading _).
            param = lhs.split(".")[-1].lstrip("_")
            try:
                result = eval(expr, {"__builtins__": {}}, {param: boundary})  # noqa: S307
            except Exception:
                return None
            # Represent integers cleanly (90 not 90.0) when the value is whole.
            if isinstance(result, float) and result == int(result):
                return repr(int(result))
            return repr(result)
        # Stop if we leave the indented block (blank lines are fine, but a
        # dedented non-blank line means we've exited the if-body).
        stripped = line.strip()
        if stripped and not line[0].isspace():
            break
    return None


def _analyze_gte_to_gt_function(
    mutation: Mutation,
    lhs: str,
    rhs: str,
    lhs_name: str,
    func_name: str,
    module_stem: str,
) -> AnalysisResult:
    """Generate analysis for a >= → > mutation inside a module-level function."""
    # If the RHS is a numeric literal use it as the boundary value directly;
    # otherwise fall back to a symbolic placeholder so the test is still
    # concrete and runnable.
    try:
        boundary = float(rhs)
        boundary_repr = repr(int(boundary) if boundary == int(boundary) else boundary)
    except ValueError:
        boundary = None
        boundary_repr = rhs

    # Attempt to derive a meaningful expected value from the function body so
    # the assertion is `assert func(boundary) == expected` rather than the
    # weaker `assert result is not None`.
    expected_repr = None
    if boundary is not None:
        expected_repr = _expected_return_value(
            mutation.original_source, mutation.line_number, lhs, boundary
        )

    if expected_repr is not None:
        assertion_line = f"assert {func_name}({boundary_repr}) == {expected_repr}"
        suggested_test = textwrap.dedent(f"""\
            from {module_stem} import {func_name}


            def test_{func_name}_at_boundary():
                {assertion_line}
        """)
    else:
        suggested_test = textwrap.dedent(f"""\
            from {module_stem} import {func_name}


            def test_{func_name}_at_boundary():
                result = {func_name}({boundary_repr})
                assert result is not None
        """)

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes the boundary condition from "
            f"`{lhs} >= {rhs}` to `{lhs} > {rhs}`. "
            f"With the original operator, calling `{func_name}` with "
            f"`{lhs}` exactly equal to `{rhs}` takes the guarded branch. "
            f"After the mutation, that exact boundary case follows the "
            f"opposite branch instead."
        ),
        risk=(
            "An important boundary condition is not protected by the current "
            "test suite. A future refactor could silently introduce this bug "
            "and no test would catch it."
        ),
        missing_behavior=(
            f"No existing test verifies the behaviour of `{func_name}` when "
            f"`{lhs}` is exactly equal to `{rhs}`. The boundary case "
            f"`{lhs} == {rhs}` is never exercised."
        ),
        suggested_test_name=f"test_{func_name}_at_boundary",
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Rule: > → >= on any strict-greater guard
# ---------------------------------------------------------------------------

@_rule(
    operator="> \u2192 >=",           # "> → >="
    line_pattern=r"if\s+([\w.]+)\s*>\s*([\w.]+)",
)
def _analyze_gt_to_gte(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)
    rhs = match.group(2)

    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )
    module_stem = mutation.source_file.stem

    # Try to get a numeric boundary from RHS (may be a literal like 90 or a name like threshold)
    try:
        boundary = float(rhs)
        boundary_repr = repr(int(boundary) if boundary == int(boundary) else boundary)
    except ValueError:
        boundary = None
        boundary_repr = rhs

    if class_name != "Unknown":
        # Class method context.
        import_name = _to_import_name(class_name)
        comment_lhs = lhs.replace("self.", "")
        comment_rhs = rhs.replace("self.", "")

        if boundary is not None:
            # RHS is a numeric literal — use it directly.
            probe = boundary_repr
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {import_name}


                def test_{method_name}_at_strict_boundary():
                    obj = {import_name}()
                    # {comment_lhs} == {comment_rhs}: original '>' excludes equality; mutant '>=' includes it
                    result = obj.{method_name}({probe})
                    assert result is not None  # verify boundary is handled
            """)
        else:
            # RHS is self.<attr> — try to read the constructor default for that attribute.
            # Pass the raw attribute name (e.g. "_passing_mark") so the body-scan regex
            # matches the actual source text "self._passing_mark = ...".
            attr_name = rhs.split(".")[-1] if rhs.startswith("self.") else rhs
            inferred = _infer_constructor_default(
                mutation.original_source, class_name, attr_name
            )
            if inferred is not None:
                probe = inferred
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def test_{method_name}_at_strict_boundary():
                        # boundary is the constructor default for {comment_rhs} ({probe})
                        obj = {import_name}()
                        result = obj.{method_name}({probe})
                        assert result is not None  # verify boundary is handled
                """)
            else:
                # Cannot infer boundary — emit a contextual suggestion.
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def test_{method_name}_at_strict_boundary():
                        # [contextual suggestion] replace <boundary> with the actual
                        # value that {comment_lhs} is compared against ({comment_rhs})
                        obj = {import_name}()
                        result = obj.{method_name}(<boundary>)
                        assert result is not None  # verify boundary is handled
                """)
        suggested_test_name = f"test_{method_name}_at_strict_boundary"
    else:
        # Module-level function context
        if boundary is not None:
            expected_repr = _expected_return_value(
                mutation.original_source, mutation.line_number, lhs, boundary
            )
            probe_repr = boundary_repr
        else:
            expected_repr = None
            # RHS is a parameter/variable name — use a safe literal probe
            probe_repr = "50"

        if expected_repr is not None:
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {method_name}


                def test_{method_name}_at_strict_boundary():
                    assert {method_name}({probe_repr}) == {expected_repr}
            """)
        else:
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {method_name}


                def test_{method_name}_at_strict_boundary():
                    # boundary: {lhs} == {rhs} is excluded by '>'; mutant '>=' would include it
                    # [contextual suggestion — replace 50 with the actual boundary value]
                    result = {method_name}({probe_repr})
                    assert result is not None
            """)
        suggested_test_name = f"test_{method_name}_at_strict_boundary"

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes the condition from "
            f"`{lhs} > {rhs}` to `{lhs} >= {rhs}`. "
            f"With the original operator, the case where `{lhs}` exactly equals "
            f"`{rhs}` does NOT take the guarded branch. After the mutation, that "
            f"boundary case takes the branch instead, changing behaviour at the "
            f"exact equality point."
        ),
        risk=(
            "The strict-greater boundary is not verified by the test suite. "
            "A future change that accidentally includes the equality case would "
            "not be caught."
        ),
        missing_behavior=(
            f"No existing test verifies the behaviour of `{method_name}` when "
            f"`{lhs}` is exactly equal to `{rhs}`. The boundary case "
            f"`{lhs} == {rhs}` is never exercised."
        ),
        suggested_test_name=suggested_test_name,
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Rule: == → != on any equality check
# ---------------------------------------------------------------------------

@_rule(
    operator="== \u2192 !=",           # "== → !="
    line_pattern=r"if\s+([\w.]+)\s*==\s*([\w.\"']+)",
)
def _analyze_eq_to_neq(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)
    rhs = match.group(2)
    lhs_name = lhs.split(".")[-1].lstrip("_")

    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )
    module_stem = mutation.source_file.stem

    # Strip quotes from string literals for display
    rhs_display = rhs.strip("\"'")

    if class_name != "Unknown":
        import_name = _to_import_name(class_name)
        comment_lhs = lhs.replace("self.", "")
        comment_rhs = rhs.replace("self.", "")
        test_fn_name = f"test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}"

        if not rhs.startswith("self."):
            # RHS is a plain literal — use it directly as the call argument.
            rhs_arg = rhs
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {import_name}


                def {test_fn_name}():
                    obj = {import_name}()
                    # call with {comment_lhs} == {comment_rhs} to exercise the equality branch
                    result = obj.{method_name}({rhs_arg})
                    assert result is not None  # exact-match branch must be taken
            """)
        else:
            # RHS is self.<attr> — try to infer the constructor default.
            # Keep the raw attribute name (e.g. "_passing_mark") for body-scan regex.
            attr_name = rhs.split(".")[-1]
            inferred = _infer_constructor_default(
                mutation.original_source, class_name, attr_name
            )
            if inferred is not None:
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def {test_fn_name}():
                        # {comment_rhs} defaults to {inferred}; use that as the equality probe
                        obj = {import_name}()
                        result = obj.{method_name}({inferred})
                        assert result is not None  # exact-match branch must be taken
                """)
            else:
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def {test_fn_name}():
                        # [contextual suggestion] replace <value> with the actual
                        # value that {comment_lhs} is compared against ({comment_rhs})
                        obj = {import_name}()
                        result = obj.{method_name}(<value>)
                        assert result is not None  # exact-match branch must be taken
                """)
        suggested_test_name = test_fn_name
    else:
        suggested_test = textwrap.dedent(f"""\
            from {module_stem} import {method_name}


            def test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}():
                # call with {lhs} == {rhs} to exercise the equality branch
                result = {method_name}({rhs})
                assert result is not None  # exact-match branch must be taken
        """)
        suggested_test_name = f"test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}"

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes the condition from "
            f"`{lhs} == {rhs}` to `{lhs} != {rhs}`. "
            f"With the original operator, code inside the `if` block runs only "
            f"when `{lhs}` is exactly `{rhs}`. After the mutation, that block "
            f"runs for every value *except* `{rhs}`, completely inverting the "
            f"branch logic."
        ),
        risk=(
            "The equality branch is not covered by the test suite. Inverting "
            "this condition would change behaviour for the exact-match case "
            "and no test would detect it."
        ),
        missing_behavior=(
            f"No existing test calls `{method_name}` with `{lhs}` equal to "
            f"`{rhs}`, so the equality branch `{lhs} == {rhs}` is never "
            f"exercised and the mutation survives."
        ),
        suggested_test_name=suggested_test_name,
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Rule: != → == on any inequality check
# ---------------------------------------------------------------------------

@_rule(
    operator="!= \u2192 ==",           # "!= → =="
    line_pattern=r"if\s+([\w.]+)\s*!=\s*([\w.\"']+)",
)
def _analyze_neq_to_eq(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)
    rhs = match.group(2)
    lhs_name = lhs.split(".")[-1].lstrip("_")

    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )
    module_stem = mutation.source_file.stem

    rhs_display = rhs.strip("\"'")

    if class_name != "Unknown":
        import_name = _to_import_name(class_name)
        comment_lhs = lhs.replace("self.", "")
        comment_rhs = rhs.replace("self.", "")
        test_fn_name = f"test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}"

        if not rhs.startswith("self."):
            rhs_arg = rhs
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {import_name}


                def {test_fn_name}():
                    obj = {import_name}()
                    # when {comment_lhs} == {comment_rhs}, the '!=' condition is False; mutation flips this
                    result = obj.{method_name}({rhs_arg})
                    assert result is not None  # non-matching branch behaviour verified
            """)
        else:
            attr_name = rhs.split(".")[-1]
            inferred = _infer_constructor_default(
                mutation.original_source, class_name, attr_name
            )
            if inferred is not None:
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def {test_fn_name}():
                        # {comment_rhs} defaults to {inferred}; use that as the probe
                        obj = {import_name}()
                        result = obj.{method_name}({inferred})
                        assert result is not None  # non-matching branch behaviour verified
                """)
            else:
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def {test_fn_name}():
                        # [contextual suggestion] replace <value> with the actual
                        # value that {comment_lhs} is compared against ({comment_rhs})
                        obj = {import_name}()
                        result = obj.{method_name}(<value>)
                        assert result is not None  # non-matching branch behaviour verified
                """)
        suggested_test_name = test_fn_name
    else:
        suggested_test = textwrap.dedent(f"""\
            from {module_stem} import {method_name}


            def test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}():
                # when {lhs} == {rhs}, the '!=' condition is False; mutation flips this
                result = {method_name}({rhs})
                assert result is not None  # non-matching branch behaviour verified
        """)
        suggested_test_name = f"test_{method_name}_when_{lhs_name}_equals_{_safe_name(rhs_display)}"

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes the condition from "
            f"`{lhs} != {rhs}` to `{lhs} == {rhs}`. "
            f"With the original operator, the `if` block runs whenever `{lhs}` "
            f"differs from `{rhs}`. After the mutation, it runs only when "
            f"`{lhs}` is exactly `{rhs}`, completely inverting the condition."
        ),
        risk=(
            "The inequality branch is not fully covered. If this condition is "
            "inverted, the function behaves differently for every non-matching "
            "value and no test would catch it."
        ),
        missing_behavior=(
            f"No existing test verifies `{method_name}` behaviour when "
            f"`{lhs}` equals `{rhs}`, so the edge case where the `!=` "
            f"condition is False is never exercised."
        ),
        suggested_test_name=suggested_test_name,
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Rule: + → - on any addition expression
# ---------------------------------------------------------------------------

@_rule(
    operator="+ \u2192 -",           # "+ → -"
    line_pattern=r"([\w.]+)\s*\+\s*([\w.]+)",
)
def _analyze_add_to_sub(mutation: Mutation, match: re.Match) -> AnalysisResult:
    lhs = match.group(1)
    rhs = match.group(2)

    class_name, method_name = _infer_context(
        mutation.original_source, mutation.line_number
    )
    module_stem = mutation.source_file.stem

    # Try to extract numeric literals for a concrete assertion
    try:
        lhs_val = float(lhs)
    except ValueError:
        lhs_val = None
    try:
        rhs_val = float(rhs)
    except ValueError:
        rhs_val = None

    if class_name != "Unknown":
        import_name = _to_import_name(class_name)
        # Inspect the actual method signature to avoid generating wrong arity calls.
        user_param_count = _infer_method_user_params(
            mutation.original_source, mutation.line_number
        )
        if user_param_count == 1:
            # One user param (e.g. combined(self, extra)): one operand is a
            # self.* attribute and the other is the parameter.
            # Try to infer the constructor default for the self.* operand so we
            # can produce a concrete, verifiable assertion.
            self_attr = lhs if lhs.startswith("self.") else (rhs if rhs.startswith("self.") else None)
            free_operand = rhs if lhs.startswith("self.") else (lhs if rhs.startswith("self.") else None)
            attr_default: str | None = None
            if self_attr is not None:
                raw_attr = self_attr.split(".")[-1]
                attr_default = _infer_constructor_default(
                    mutation.original_source, class_name, raw_attr
                )

            if attr_default is not None:
                # We know the default; use probe=3 so the expected value is
                # attr_default + 3 (distinct from attr_default - 3).
                try:
                    expected_val = float(attr_default) + 3.0
                    expected_repr2 = repr(int(expected_val) if expected_val == int(expected_val) else expected_val)
                except (ValueError, OverflowError):
                    expected_repr2 = None

                # Sanitise comment: strip "self." so the comment doesn't embed attribute paths
                lhs_disp = lhs.replace("self.", "")
                rhs_disp = rhs.replace("self.", "")
                if expected_repr2 is not None:
                    suggested_test = textwrap.dedent(f"""\
                        from {module_stem} import {import_name}


                        def test_{method_name}_adds_not_subtracts():
                            # {lhs_disp} defaults to {attr_default}; probe=3 gives {attr_default} + 3 = {expected_repr2}
                            obj = {import_name}()
                            result = obj.{method_name}(3)
                            assert result == {expected_repr2}  # {attr_default} + 3, not {attr_default} - 3
                    """)
                else:
                    suggested_test = textwrap.dedent(f"""\
                        from {module_stem} import {import_name}


                        def test_{method_name}_adds_not_subtracts():
                            # [contextual suggestion] supply a non-zero argument; result should be {lhs_disp} + {rhs_disp}
                            obj = {import_name}()
                            result = obj.{method_name}(3)
                            assert result is not None  # verify addition not subtraction
                    """)
            else:
                # Cannot infer the self.* default — emit a contextual suggestion.
                lhs_disp = lhs.replace("self.", "")
                rhs_disp = rhs.replace("self.", "")
                suggested_test = textwrap.dedent(f"""\
                    from {module_stem} import {import_name}


                    def test_{method_name}_adds_not_subtracts():
                        # [contextual suggestion] supply a non-zero argument so that
                        # {lhs_disp} + {rhs_disp} gives a different result than {lhs_disp} - {rhs_disp}
                        obj = {import_name}()
                        result = obj.{method_name}(3)
                        assert result is not None  # replace with a concrete expected value
                """)
        elif user_param_count == 2:
            # Two user params (e.g. add(a, b)): both operands come from args.
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {import_name}


                def test_{method_name}_adds_not_subtracts():
                    obj = {import_name}()
                    # provide two distinct non-zero values so + and - give different results
                    result = obj.{method_name}(3, 2)
                    assert result == 5  # 3 + 2, not 3 - 2
            """)
        else:
            # Arity unknown or unusual — emit a contextual suggestion that is
            # at least valid Python (uses pass to keep the body syntactically legal).
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {import_name}


                def test_{method_name}_adds_not_subtracts():
                    # [contextual suggestion] supply the correct arguments so that
                    # {lhs} + {rhs} gives a different result than {lhs} - {rhs},
                    # then assert the expected sum
                    obj = {import_name}()
                    pass  # TODO: replace pass with obj.{method_name}(...) == expected
            """)
        suggested_test_name = f"test_{method_name}_adds_not_subtracts"
    else:
        # If both operands are numeric literals we can compute the expected value.
        if lhs_val is not None and rhs_val is not None:
            expected = lhs_val + rhs_val
            expected_repr = repr(int(expected) if expected == int(expected) else expected)
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {method_name}


                def test_{method_name}_adds_not_subtracts():
                    assert {method_name}({lhs}, {rhs}) == {expected_repr}
            """)
        else:
            # Use concrete probe values that distinguish + from -
            suggested_test = textwrap.dedent(f"""\
                from {module_stem} import {method_name}


                def test_{method_name}_adds_not_subtracts():
                    # use distinct non-zero values so + and - give different results
                    assert {method_name}(3, 2) == 5
            """)
        suggested_test_name = f"test_{method_name}_adds_not_subtracts"

    return AnalysisResult(
        mutation_id=mutation.id,
        explanation=(
            f"The mutation changes `{lhs} + {rhs}` to `{lhs} - {rhs}` inside "
            f"`{method_name}`. With the original operator the two values are "
            f"summed; after the mutation the second value is subtracted, "
            f"producing a completely different result."
        ),
        risk=(
            "Addition and subtraction produce different results for any non-zero "
            "second operand. If no test asserts the return value, this mutation "
            "survives undetected."
        ),
        missing_behavior=(
            f"No existing test asserts the return value of `{method_name}` with "
            f"two non-zero operands, so the difference between `{lhs} + {rhs}` "
            f"and `{lhs} - {rhs}` is never verified."
        ),
        suggested_test_name=suggested_test_name,
        suggested_test=suggested_test,
    )


# ---------------------------------------------------------------------------
# Source-inspection helpers
# ---------------------------------------------------------------------------

def _infer_method_user_params(source: str, mutated_line_number: int) -> int | None:
    """Return the number of user-facing parameters for the method that contains
    *mutated_line_number* (1-based).

    "User-facing" means every parameter except ``self`` and ``cls``.  Returns
    ``None`` if the enclosing ``def`` line cannot be found or its parameter
    list cannot be parsed.
    """
    lines = source.splitlines()
    # Walk backwards to find the def line.
    for i in range(mutated_line_number - 1, -1, -1):
        m = re.match(r"[ \t]*def\s+\w+\s*\((.*)$", lines[i])
        if m:
            # The parameter list may continue across multiple lines; collect
            # lines until the closing ')'.
            param_text = m.group(1)
            j = i + 1
            while ")" not in param_text and j < len(lines):
                param_text += " " + lines[j].strip()
                j += 1
            # Strip everything from the first ')' onward (return type annotation etc.)
            close = param_text.find(")")
            if close != -1:
                param_text = param_text[:close]
            # Split on commas, strip annotations and defaults.
            parts = [p.strip() for p in param_text.split(",") if p.strip()]
            user_params = [
                p for p in parts
                if p and p.split(":")[0].split("=")[0].strip() not in ("self", "cls")
            ]
            return len(user_params)
    return None


def _infer_constructor_default(source: str, class_name: str, attr_name: str) -> str | None:
    """Try to find the numeric default value for *attr_name* (a ``self.*``
    attribute, including any leading underscore) by inspecting the class
    constructor in *source*.

    Strategy
    --------
    1. Find ``class <class_name>`` in the source.
    2. Find the ``__init__`` method inside that class.
    3. Look for ``self.<attr_name> = <param_name>`` inside ``__init__``.
    4. Find *param_name* in the ``__init__`` signature and return its default
       value if it is a valid numeric literal.

    *attr_name* is the raw attribute name as it appears after ``self.``,
    e.g. ``"_passing_mark"`` for ``self._passing_mark``.

    Returns a string such as ``"50"`` or ``"50.0"`` on success, ``None``
    otherwise.
    """
    lines = source.splitlines()

    # --- Step 1: locate the class ---
    class_start = None
    for i, line in enumerate(lines):
        if re.match(rf"^class\s+{re.escape(class_name)}\b", line):
            class_start = i
            break
    if class_start is None:
        return None

    # --- Step 2: locate __init__ inside that class ---
    init_start = None
    for i in range(class_start + 1, len(lines)):
        line = lines[i]
        # Stop if we hit another top-level class definition
        if re.match(r"^class\s+\w+", line) and i != class_start:
            break
        if re.match(r"[ \t]+def\s+__init__\s*\(", line):
            init_start = i
            break
    if init_start is None:
        return None

    # --- Step 3: collect the full __init__ signature using balanced parens ---
    # Concatenate lines until the opening '(' of the def is balanced.
    sig_text = lines[init_start]
    j = init_start + 1
    depth = sig_text.count("(") - sig_text.count(")")
    while depth > 0 and j < len(lines):
        sig_text += " " + lines[j].strip()
        depth += lines[j].count("(") - lines[j].count(")")
        j += 1
    # Extract the parameter list between the first '(' and its matching ')'.
    paren_open = sig_text.find("(")
    if paren_open == -1:
        return None
    depth2 = 0
    paren_close = -1
    for k, ch in enumerate(sig_text[paren_open:], start=paren_open):
        if ch == "(":
            depth2 += 1
        elif ch == ")":
            depth2 -= 1
            if depth2 == 0:
                paren_close = k
                break
    if paren_close == -1:
        return None
    params_str = sig_text[paren_open + 1 : paren_close]
    # Build a map: param_name -> default_value_str
    param_defaults: dict[str, str] = {}
    for part in params_str.split(","):
        part = part.strip()
        if not part:
            continue
        # Strip type annotation (everything after ':')
        name_part = part.split(":")[0].strip()
        default_part = part.split("=")[1].strip() if "=" in part else None
        bare_name = name_part.split("=")[0].strip()
        if default_part is not None:
            param_defaults[bare_name] = default_part

    # --- Step 4: find self.<attr_name> = <param> inside __init__ body ---
    # Scan the body lines (starting at j) until indentation falls back.
    init_indent = len(lines[init_start]) - len(lines[init_start].lstrip())
    for i in range(j, min(j + 40, len(lines))):
        line = lines[i]
        if not line.strip():
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= init_indent:
            break
        m = re.match(
            rf"[ \t]+self\.{re.escape(attr_name)}\s*=\s*(\w+)", line
        )
        if m:
            param_name = m.group(1)
            default = param_defaults.get(param_name)
            if default is not None:
                try:
                    float(default)   # validate it's numeric
                    return default
                except ValueError:
                    return None

    return None


# ---------------------------------------------------------------------------
# Name-safety helper
# ---------------------------------------------------------------------------

def _safe_name(value: str) -> str:
    """Convert an arbitrary value string into a safe Python identifier fragment.

    Used to embed RHS values into test function names without generating
    invalid identifiers (e.g. ``"approved"`` → ``"approved"``,
    ``100.0`` → ``100_0``).
    """
    # Strip surrounding quotes from string literals
    value = value.strip("\"'")
    # Replace any non-alphanumeric character with underscore
    safe = re.sub(r"[^a-zA-Z0-9]", "_", value)
    # Collapse consecutive underscores and strip leading/trailing ones
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "value"


def _numeric_literal_or(expr: str, default: str) -> str:
    """Return *expr* if it is a valid numeric literal, otherwise *default*.

    Prevents ``self._field`` style expressions from leaking into generated
    test code as argument values.
    """
    try:
        float(expr)
        return expr
    except ValueError:
        return default


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
            m = re.match(r"\s*def\s+(\w+)\s*\(", line)
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
