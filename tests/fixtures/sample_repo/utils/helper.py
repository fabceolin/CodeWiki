"""Helper utilities for testing."""


class Calculator:
    """A simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two numbers."""
        return a - b


def calculate(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    calc = Calculator()
    return calc.add(a, b)
