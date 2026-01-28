"""Sample main module for testing."""

from utils import helper


def main():
    """Main entry point."""
    result = helper.calculate(10, 20)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
