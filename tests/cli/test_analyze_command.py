"""
CLI integration tests for the analyze command.

Tests cover:
- Basic execution with valid repository (AC1)
- Custom output directory with --output (AC2)
- Include/exclude patterns filtering (AC3)
- Verbose mode output (AC3)
- Error handling for invalid paths (AC4, AC6)
- JSON output schema validation (AC5)
- Exit codes (AC4)
- Help text (AC7)
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.analyze import analyze_command
from codewiki.cli.main import cli


# =============================================================================
# Fixtures
# =============================================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_repo(temp_dir):
    """Create a sample Python repository for testing."""
    repo_dir = temp_dir / "sample_repo"
    repo_dir.mkdir()

    # Create main.py
    main_file = repo_dir / "main.py"
    main_file.write_text('''"""Sample main module."""

from utils import helper


def main():
    """Main entry point."""
    result = helper.calculate(10, 20)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
''')

    # Create utils package
    utils_dir = repo_dir / "utils"
    utils_dir.mkdir()

    init_file = utils_dir / "__init__.py"
    init_file.write_text('"""Utils package."""\n')

    helper_file = utils_dir / "helper.py"
    helper_file.write_text('''"""Helper utilities."""


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
''')

    return repo_dir


@pytest.fixture
def empty_repo(temp_dir):
    """Create an empty directory (no code files)."""
    repo_dir = temp_dir / "empty_repo"
    repo_dir.mkdir()
    # Add a non-code file
    readme = repo_dir / "README.md"
    readme.write_text("# Empty repo\n")
    return repo_dir


# =============================================================================
# Basic Execution Tests (AC1)
# =============================================================================

class TestBasicExecution:
    """Tests for basic command execution."""

    def test_analyze_with_valid_repository(self, runner, sample_repo, temp_dir):
        """Should successfully analyze a valid repository."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            # Change to sample repo directory
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0
            assert "Analysis Complete" in result.output

            # Check output file exists
            output_file = output_dir / "dependency_graph.json"
            assert output_file.exists()

    def test_analyze_creates_output_directory(self, runner, sample_repo, temp_dir):
        """Should create output directory if it doesn't exist."""
        output_dir = temp_dir / "new_output"

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0
            assert output_dir.exists()
            assert (output_dir / "dependency_graph.json").exists()

    def test_analyze_via_main_cli(self, runner, sample_repo, temp_dir):
        """Should work when invoked through main CLI group."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(cli, [
                "analyze",
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0


# =============================================================================
# Output Directory Tests (AC2)
# =============================================================================

class TestOutputDirectory:
    """Tests for --output flag."""

    def test_custom_output_directory(self, runner, sample_repo, temp_dir):
        """Should save output to specified directory."""
        custom_output = temp_dir / "custom" / "output"

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(custom_output),
            ])

            assert result.exit_code == 0
            assert (custom_output / "dependency_graph.json").exists()

    def test_default_output_directory(self, runner, sample_repo, temp_dir):
        """Should use ./docs as default output directory."""
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [])

            assert result.exit_code == 0
            # Default is ./docs
            default_output = sample_repo / "docs" / "dependency_graph.json"
            assert default_output.exists()


# =============================================================================
# Filtering Tests (AC3)
# =============================================================================

class TestFiltering:
    """Tests for include/exclude/focus options."""

    def test_include_patterns(self, runner, sample_repo, temp_dir):
        """Should respect --include patterns."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--include", "*.py",
            ])

            assert result.exit_code == 0

    def test_exclude_patterns(self, runner, sample_repo, temp_dir):
        """Should respect --exclude patterns."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--exclude", "*test*,*spec*",
            ])

            assert result.exit_code == 0

    def test_focus_option(self, runner, sample_repo, temp_dir):
        """Should accept --focus option."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--focus", "utils",
            ])

            assert result.exit_code == 0


# =============================================================================
# Verbose Mode Tests (AC3)
# =============================================================================

class TestVerboseMode:
    """Tests for verbose mode."""

    def test_verbose_shows_languages(self, runner, sample_repo, temp_dir):
        """Verbose mode should show detected languages."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--verbose",
            ])

            assert result.exit_code == 0
            # Should show Python detected
            assert "python" in result.output.lower() or "files" in result.output.lower()

    def test_verbose_shows_component_types(self, runner, sample_repo, temp_dir):
        """Verbose mode should show component type breakdown."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--verbose",
            ])

            assert result.exit_code == 0
            assert "Component types:" in result.output

    def test_verbose_shows_patterns(self, runner, sample_repo, temp_dir):
        """Verbose mode should show include/exclude patterns when provided."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
                "--include", "*.py",
                "--verbose",
            ])

            assert result.exit_code == 0
            assert "Include patterns" in result.output


# =============================================================================
# Exit Code Tests (AC4)
# =============================================================================

class TestExitCodes:
    """Tests for exit codes."""

    def test_exit_code_0_on_success(self, runner, sample_repo, temp_dir):
        """Should return exit code 0 on success."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0

    def test_exit_code_nonzero_on_invalid_repo(self, runner, empty_repo, temp_dir):
        """Should return non-zero exit code for invalid repository."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(empty_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code != 0


# =============================================================================
# JSON Schema Tests (AC5)
# =============================================================================

class TestJSONSchema:
    """Tests for JSON output schema validation."""

    def test_json_has_metadata(self, runner, sample_repo, temp_dir):
        """Output JSON should have metadata section."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0

            output_file = output_dir / "dependency_graph.json"
            with open(output_file) as f:
                data = json.load(f)

            assert "metadata" in data
            assert "generated_at" in data["metadata"]
            assert "repo_path" in data["metadata"]
            assert "total_components" in data["metadata"]
            assert "total_leaf_nodes" in data["metadata"]

    def test_json_has_components(self, runner, sample_repo, temp_dir):
        """Output JSON should have components section."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0

            output_file = output_dir / "dependency_graph.json"
            with open(output_file) as f:
                data = json.load(f)

            assert "components" in data
            assert isinstance(data["components"], dict)

            # Check component structure
            for comp_id, comp in data["components"].items():
                assert "name" in comp
                assert "type" in comp
                assert "file_path" in comp
                assert "depends_on" in comp

    def test_json_has_leaf_nodes(self, runner, sample_repo, temp_dir):
        """Output JSON should have leaf_nodes section."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0

            output_file = output_dir / "dependency_graph.json"
            with open(output_file) as f:
                data = json.load(f)

            assert "leaf_nodes" in data
            assert isinstance(data["leaf_nodes"], list)

    def test_json_is_valid(self, runner, sample_repo, temp_dir):
        """Output should be valid JSON."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(sample_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code == 0

            output_file = output_dir / "dependency_graph.json"
            # Should not raise
            with open(output_file) as f:
                data = json.load(f)
            assert data is not None


# =============================================================================
# Error Handling Tests (AC4, AC6)
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_repository_error(self, runner, empty_repo, temp_dir):
        """Should handle repositories with no supported code files."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            os.chdir(str(empty_repo))

            result = runner.invoke(analyze_command, [
                "--output", str(output_dir),
            ])

            assert result.exit_code != 0
            assert "No supported code files" in result.output

    def test_permission_error_message(self, runner, sample_repo, temp_dir):
        """Should show clear message for permission errors."""
        # Create a read-only directory
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), 0o444)

        try:
            with runner.isolated_filesystem(temp_dir=str(temp_dir)):
                os.chdir(str(sample_repo))

                result = runner.invoke(analyze_command, [
                    "--output", str(readonly_dir / "subdir"),
                ])

                # Should fail (can't create subdirectory)
                assert result.exit_code != 0
        finally:
            # Restore permissions for cleanup
            os.chmod(str(readonly_dir), 0o755)


# =============================================================================
# Help Text Tests (AC7)
# =============================================================================

class TestHelpText:
    """Tests for help text."""

    def test_help_shows_description(self, runner):
        """Help text should show command description."""
        result = runner.invoke(analyze_command, ["--help"])

        assert result.exit_code == 0
        assert "Analyze a code repository" in result.output

    def test_help_shows_examples(self, runner):
        """Help text should show usage examples."""
        result = runner.invoke(analyze_command, ["--help"])

        assert result.exit_code == 0
        assert "codewiki analyze" in result.output

    def test_help_shows_all_options(self, runner):
        """Help text should show all available options."""
        result = runner.invoke(analyze_command, ["--help"])

        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--include" in result.output
        assert "--exclude" in result.output
        assert "--focus" in result.output
        assert "--verbose" in result.output

    def test_help_via_main_cli(self, runner):
        """Help should work through main CLI group."""
        result = runner.invoke(cli, ["analyze", "--help"])

        assert result.exit_code == 0
        assert "Analyze a code repository" in result.output
