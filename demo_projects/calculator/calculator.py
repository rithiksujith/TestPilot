"""
Calculator — simple arithmetic with a discount calculation.

The discount rule uses a boundary condition so that the mutation engine
can apply the gte-to-gt operator and produce a surviving mutant when the
test suite does not cover the exact boundary value.
"""


def add(a: float, b: float) -> float:
    """Return the sum of *a* and *b*."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return *a* minus *b*."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Return *a* multiplied by *b*."""
    return a * b


def calculate_discount(total: float) -> float:
    """Return *total* after applying a 10 % discount for orders of 100 or more.

    A purchase of exactly 100 qualifies for the discount.  Tests that skip
    this exact boundary value will not detect the gte-to-gt mutation.
    """
    if total >= 100:
        return total * 0.9
    return total
