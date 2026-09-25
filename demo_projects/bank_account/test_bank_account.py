import pytest
from bank_account import BankAccount


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_default_balance_is_zero():
    account = BankAccount()
    assert account.balance == 0.0


def test_initial_balance_is_set():
    account = BankAccount(100.0)
    assert account.balance == 100.0


def test_negative_initial_balance_raises():
    with pytest.raises(ValueError):
        BankAccount(-50.0)


# ---------------------------------------------------------------------------
# Deposit
# ---------------------------------------------------------------------------

def test_deposit_increases_balance():
    account = BankAccount(50.0)
    account.deposit(25.0)
    assert account.balance == 75.0


def test_zero_deposit_raises():
    account = BankAccount(50.0)
    with pytest.raises(ValueError):
        account.deposit(0)


def test_negative_deposit_raises():
    account = BankAccount(50.0)
    with pytest.raises(ValueError):
        account.deposit(-10.0)


# ---------------------------------------------------------------------------
# Withdrawal — intentional gap: exact-balance boundary is NOT tested
# ---------------------------------------------------------------------------

def test_withdraw_reduces_balance():
    account = BankAccount(100.0)
    account.withdraw(40.0)
    assert account.balance == 60.0


def test_withdraw_more_than_balance_raises():
    account = BankAccount(100.0)
    with pytest.raises(ValueError):
        account.withdraw(150.0)


def test_zero_withdrawal_raises():
    account = BankAccount(100.0)
    with pytest.raises(ValueError):
        account.withdraw(0)


def test_negative_withdrawal_raises():
    account = BankAccount(100.0)
    with pytest.raises(ValueError):
        account.withdraw(-10.0)


# NOTE: There is deliberately NO test for withdrawing exactly the available
# balance (e.g. account.withdraw(100.0) when balance == 100.0).
# The production code allows this via `balance >= amount`, but the tests
# never exercise that boundary, so mutating >= to > would go undetected.
