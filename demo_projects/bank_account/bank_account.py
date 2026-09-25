class BankAccount:
    """A simple bank account with deposit and withdrawal support."""

    def __init__(self, initial_balance: float = 0.0) -> None:
        if initial_balance < 0:
            raise ValueError("Initial balance cannot be negative.")
        self._balance = initial_balance

    @property
    def balance(self) -> float:
        return self._balance

    def deposit(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")
        self._balance += amount

    def withdraw(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive.")
        # NOTE: uses >= so that withdrawing exactly the balance is allowed.
        # Mutating >= to > would silently break that boundary case.
        if self._balance >= amount:
            self._balance -= amount
        else:
            raise ValueError("Insufficient funds.")
