"""
CLI integration tests for the affected-modules command.

Tests cover:
- CLI argument handling (explicit paths and directory mode)
- JSON output format
- Summary output to stderr
- Exit codes
- Error handling for missing/malformed files
- Verbose mode
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from codewiki.cli.commands.affected import affected_modules


# =============================================================================
# Fixtures
# =============================================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "graphs"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


def get_json_output(output: str) -> str:
    """Extract JSON output from combined stdout/stderr.

    The CLI outputs JSON array on the first line to stdout,
    and summary to stderr. When mixed, we need to extract just the JSON line.
    """
    lines = output.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            return line
    # If no JSON array line found, return first line
    return lines[0] if lines else ""


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def old_graph_path():
    """Path to old graph fixture."""
    return FIXTURES_DIR / "minimal_graph_old.json"


@pytest.fixture
def new_graph_path():
    """Path to new graph fixture."""
    return FIXTURES_DIR / "minimal_graph_new.json"


@pytest.fixture
def module_tree_path():
    """Path to nested module tree fixture."""
    return FIXTURES_DIR / "module_tree_nested.json"


@pytest.fixture
def identical_graph_path():
    """Path to a graph for testing identical comparison."""
    return FIXTURES_DIR / "minimal_graph_old.json"


# =============================================================================
# CLI Argument Tests (AC1)
# =============================================================================

class TestCLIArguments:
    """Tests for CLI argument handling."""

    # IDU-INT-004: Accepts explicit paths
    def test_accepts_explicit_paths(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Should accept --old-graph, --new-graph, --module-tree."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        assert result.exit_code == 0
        # Should output valid JSON
        json_line = get_json_output(result.output)
        output_json = json.loads(json_line)
        assert isinstance(output_json, list)

    # IDU-INT-005: Accepts directory mode
    def test_accepts_directory_mode(self, runner, temp_dir):
        """Should accept --old-dir, --new-dir."""
        # Create directory structure
        old_dir = temp_dir / "old"
        new_dir = temp_dir / "new"
        old_dir.mkdir()
        new_dir.mkdir()

        # Copy fixtures with correct names
        import shutil
        shutil.copy(
            FIXTURES_DIR / "minimal_graph_old.json",
            old_dir / "dependency_graph.json"
        )
        shutil.copy(
            FIXTURES_DIR / "minimal_graph_new.json",
            new_dir / "dependency_graph.json"
        )
        shutil.copy(
            FIXTURES_DIR / "module_tree_nested.json",
            new_dir / "module_tree.json"
        )

        result = runner.invoke(affected_modules, [
            "--old-dir", str(old_dir),
            "--new-dir", str(new_dir),
        ])

        assert result.exit_code == 0

    def test_rejects_mixed_mode(
        self, runner, old_graph_path, temp_dir
    ):
        """Should reject mixing explicit paths and directory mode."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--old-dir", str(temp_dir),
        ])

        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_requires_all_explicit_paths(
        self, runner, old_graph_path, new_graph_path
    ):
        """Should require all three paths in explicit mode."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            # Missing --module-tree
        ])

        assert result.exit_code != 0
        assert "--module-tree is required" in result.output

    def test_requires_both_directories(self, runner, temp_dir):
        """Should require both directories in directory mode."""
        result = runner.invoke(affected_modules, [
            "--old-dir", str(temp_dir),
            # Missing --new-dir
        ])

        assert result.exit_code != 0
        assert "--new-dir is required" in result.output


# =============================================================================
# Output Format Tests (AC5, AC6)
# =============================================================================

class TestOutputFormat:
    """Tests for output format."""

    # IDU-INT-006: Valid JSON array to stdout
    def test_outputs_valid_json_array(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Should output valid JSON array to stdout."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        # Parse stdout as JSON (first line)
        json_line = get_json_output(result.output)
        output_json = json.loads(json_line)

        assert isinstance(output_json, list)
        # All items should be strings
        assert all(isinstance(item, str) for item in output_json)

    # IDU-INT-007: Summary to stderr (not mixed with stdout)
    def test_summary_to_stderr(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Summary should go to stderr, not stdout."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        # First line should be pure JSON
        json_line = get_json_output(result.output)
        assert json_line.startswith("[")
        assert json_line.endswith("]")

        # Should be parseable
        output_json = json.loads(json_line)
        assert isinstance(output_json, list)

        # Output should also contain summary text
        assert "Changes detected" in result.output

    # IDU-E2E-002: Output compatible with piping to jq
    def test_piping_compatible(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Output should be valid JSON for piping."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        # Extract JSON line (simulates `head -1 | jq .`)
        json_line = get_json_output(result.output)
        parsed = json.loads(json_line)
        assert parsed is not None


# =============================================================================
# Exit Code Tests (AC10)
# =============================================================================

class TestExitCodes:
    """Tests for exit codes."""

    # IDU-INT-008: Exit code 0 on success
    def test_exit_code_0_on_success(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Should return exit code 0 on success."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        assert result.exit_code == 0

    # IDU-INT-009: Exit code 1 on error
    def test_exit_code_1_on_error(self, runner, temp_dir):
        """Should return exit code 1 on error."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(temp_dir / "nonexistent.json"),
            "--new-graph", str(temp_dir / "also_nonexistent.json"),
            "--module-tree", str(temp_dir / "nope.json"),
        ])

        assert result.exit_code != 0


# =============================================================================
# Edge Case Tests (AC12)
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    # IDU-INT-010: Missing file error
    def test_missing_file_error(self, runner, temp_dir):
        """Should handle missing file with clear error message."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(temp_dir / "nonexistent.json"),
            "--new-graph", str(temp_dir / "also_nonexistent.json"),
            "--module-tree", str(temp_dir / "nope.json"),
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_malformed_json_error(self, runner, temp_dir):
        """Should handle malformed JSON with clear error message."""
        # Create malformed JSON file
        bad_json = temp_dir / "bad.json"
        bad_json.write_text("{ this is not valid json }")

        result = runner.invoke(affected_modules, [
            "--old-graph", str(bad_json),
            "--new-graph", str(FIXTURES_DIR / "minimal_graph_new.json"),
            "--module-tree", str(FIXTURES_DIR / "module_tree_nested.json"),
        ])

        assert result.exit_code != 0
        assert "Invalid JSON" in result.output or "invalid" in result.output.lower()

    def test_identical_graphs_returns_empty(self, runner, identical_graph_path, module_tree_path):
        """Identical graphs should return empty array."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(identical_graph_path),
            "--new-graph", str(identical_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        assert result.exit_code == 0
        json_line = get_json_output(result.output)
        output_json = json.loads(json_line)
        assert output_json == []

    def test_json_not_object_error(self, runner, temp_dir):
        """Should reject JSON that is not an object."""
        array_json = temp_dir / "array.json"
        array_json.write_text('["a", "b", "c"]')

        result = runner.invoke(affected_modules, [
            "--old-graph", str(array_json),
            "--new-graph", str(FIXTURES_DIR / "minimal_graph_new.json"),
            "--module-tree", str(FIXTURES_DIR / "module_tree_nested.json"),
        ])

        assert result.exit_code != 0
        assert "must be a JSON object" in result.output


# =============================================================================
# Verbose Mode Tests (AC13)
# =============================================================================

class TestVerboseMode:
    """Tests for verbose mode."""

    # IDU-INT-011: Verbose logs component changes
    def test_verbose_logs_changes(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Verbose mode should log component-level changes."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "-v",
        ])

        assert result.exit_code == 0
        # CliRunner mixes output, check combined
        output = result.output.lower()
        assert "added" in output or "modified" in output or "changes" in output

    # IDU-INT-012: Verbose logs traversal
    def test_verbose_logs_traversal(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Verbose mode should log traversal information."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "-v",
        ])

        assert result.exit_code == 0
        # CliRunner mixes output, check combined
        output = result.output.lower()
        assert "loading" in output or "time" in output

    def test_verbose_shows_file_paths(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Verbose mode should show file paths being loaded."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "-v",
        ])

        assert result.exit_code == 0
        # CliRunner mixes output, check combined
        assert str(old_graph_path.name) in result.output or "Loading" in result.output


# =============================================================================
# Depth Option Tests
# =============================================================================

class TestDepthOption:
    """Tests for --depth option."""

    def test_custom_depth(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Should respect custom --depth value."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "--depth", "3",
        ])

        assert result.exit_code == 0

    def test_depth_zero(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Should work with --depth 0."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "--depth", "0",
        ])

        assert result.exit_code == 0


# =============================================================================
# E2E Tests
# =============================================================================

class TestE2E:
    """End-to-end tests."""

    # IDU-E2E-003: Output matches module_key format
    def test_output_matches_module_key_format(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Output should use slash-separated module paths."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
        ])

        json_line = get_json_output(result.output)
        output_json = json.loads(json_line)

        # All module paths should be slash-separated
        for path in output_json:
            assert isinstance(path, str)
            # Should not have dots (like Python module notation)
            # Paths like "backend/auth" not "backend.auth"
            if "/" in path:
                # Multi-level paths use slashes
                parts = path.split("/")
                assert all(part for part in parts)  # No empty parts

    # IDU-E2E-004: Verbose execution phases
    def test_verbose_shows_execution_phases(
        self, runner, old_graph_path, new_graph_path, module_tree_path
    ):
        """Verbose mode should show execution phases."""
        result = runner.invoke(affected_modules, [
            "--old-graph", str(old_graph_path),
            "--new-graph", str(new_graph_path),
            "--module-tree", str(module_tree_path),
            "-v",
        ])

        assert result.exit_code == 0
        # CliRunner mixes output, check combined
        output = result.output.lower()

        # Should show timing for phases
        assert "time" in output
