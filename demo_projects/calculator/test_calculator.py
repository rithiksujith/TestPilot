"""
Tests for calculator.py.

NOTE — intentional gap
----------------------
The boundary value of 100 is deliberately NOT tested so that the gte-to-gt
mutation survives: when the boundary check is changed, the behaviour for
values below 100 and clearly above 100 is identical, so these tests still
pass and the mutation goes undetected.
"""

import pytest

from calculator import add, subtract, multiply, calculate_discount


# ---------------------------------------------------------------------------
# Basic arithmetic
# ---------------------------------------------------------------------------

def test_add_positive_numbers():
    assert add(3, 4) == 7


def test_add_negative_numbers():
    assert add(-2, -5) == -7


def test_subtract_returns_difference():
    assert subtract(10, 3) == 7


def test_multiply_two_values():
    assert multiply(6, 7) == 42


def test_multiply_by_zero():
    assert multiply(99, 0) == 0


# ---------------------------------------------------------------------------
# calculate_discount — boundary value 100 intentionally omitted
# ---------------------------------------------------------------------------

def test_discount_not_applied_below_threshold():
    """Total of 50 is below 100 — no discount."""
    assert calculate_discount(50) == 50


def test_discount_not_applied_just_below_threshold():
    """Total of 99 is just below 100 — no discount."""
    assert calculate_discount(99) == 99


def test_discount_applied_clearly_above_threshold():
    """Total of 200 is well above 100 — 10 % discount applies."""
    assert calculate_discount(200) == pytest.approx(180.0)


def test_discount_applied_at_150():
    """Total of 150 qualifies for the discount."""
    assert calculate_discount(150) == pytest.approx(135.0)


def test_no_discount_for_zero():
    """Zero total — no discount."""
    assert calculate_discount(0) == 0
