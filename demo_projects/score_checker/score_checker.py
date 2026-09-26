"""
ScoreChecker — demo module that exercises the remaining mutation operators.

Operators present
-----------------
    >  (strict greater-than)   — in is_high_score
    == (equality)              — in grade_label
    != (inequality)            — in needs_review
    +  (addition)              — in total_score
"""


def is_high_score(score: float, threshold: float = 90.0) -> bool:
    """Return True when *score* strictly exceeds *threshold*."""
    if score > threshold:
        return True
    return False


def grade_label(score: float) -> str:
    """Return a letter grade label for *score*."""
    if score == 100:
        return "A+"
    if score >= 90:
        return "A"
    return "B"


def needs_review(status: str) -> bool:
    """Return True when *status* is not 'approved'."""
    if status != "approved":
        return True
    return False


def total_score(base: float, bonus: float) -> float:
    """Return the combined score."""
    return base + bonus


class ScoreBoard:
    """Minimal scoreboard used for class-method mutation tests."""

    def __init__(self, passing_mark: float = 50.0) -> None:
        self._passing_mark = passing_mark

    def is_passing(self, score: float) -> bool:
        """Return True when *score* strictly exceeds the passing mark."""
        if score > self._passing_mark:
            return True
        return False

    def is_exact_pass(self, score: float) -> bool:
        """Return True when *score* equals the passing mark exactly."""
        if score == self._passing_mark:
            return True
        return False

    def is_failed(self, score: float) -> bool:
        """Return True when *score* is not equal to passing mark (failed path)."""
        if score != self._passing_mark:
            return True
        return False

    def combined(self, extra: float) -> float:
        """Return passing mark plus *extra*."""
        return self._passing_mark + extra
