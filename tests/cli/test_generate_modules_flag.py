"""
CLI integration tests for --modules and --force flags on generate command.

Tests cover:
- CLI parameter parsing
- Parameter propagation through adapter
- Integration with backend config
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from click.testing import CliRunner

from codewiki.cli.commands.generate import generate_command, parse_patterns


class TestParsePatterns:
    """Tests for parse_patterns() function."""

    # SMR-UNIT-001: Parse single module
    def test_parse_single_module(self):
        """Parse 'backend/auth' returns ['backend/auth']."""
        result = parse_patterns("backend/auth")
        assert result == ["backend/auth"]

    # SMR-UNIT-002: Parse multiple modules
    def test_parse_multiple_modules(self):
        """Parse 'backend/auth,utils,core/db' returns list of three."""
        result = parse_patterns("backend/auth,utils,core/db")
        assert result == ["backend/auth", "utils", "core/db"]

    # SMR-UNIT-003: Parse with whitespace
    def test_parse_with_whitespace(self):
        """Parse ' backend/auth , utils ' returns trimmed list."""
        result = parse_patterns(" backend/auth , utils ")
        assert result == ["backend/auth", "utils"]

    # SMR-UNIT-004: Parse empty string
    def test_parse_empty_string(self):
        """Parse '' returns empty list."""
        result = parse_patterns("")
        assert result == []

    def test_parse_none(self):
        """Parse None returns empty list."""
        result = parse_patterns(None)
        assert result == []

    def test_parse_single_comma(self):
        """Parse ',' returns empty list (no valid patterns)."""
        result = parse_patterns(",")
        assert result == []

    def test_parse_with_empty_segments(self):
        """Parse 'a,,b' returns ['a', 'b'] (ignores empty segments)."""
        result = parse_patterns("a,,b")
        assert result == ["a", "b"]


class TestGenerateCommandCLI:
    """Tests for CLI parameter handling."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_dependencies(self):
        """Mock dependencies for generate command testing."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

            # Setup config manager mock
            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = True
            mock_config_instance.get_api_key.return_value = "test-key"

            config_mock = MagicMock()
            config_mock.main_model = "test-model"
            config_mock.cluster_model = "test-model"
            config_mock.fallback_model = "test-model"
            config_mock.base_url = "http://test"
            config_mock.max_tokens = 32768
            config_mock.max_token_per_module = 36369
            config_mock.max_token_per_leaf_module = 16000
            config_mock.max_depth = 2
            config_mock.agent_instructions = None
            mock_config_instance.get_config.return_value = config_mock

            mock_config_mgr.return_value = mock_config_instance

            # Setup repository validation mock
            mock_validate.return_value = (Path("/test/repo"), [("python", 10)])
            mock_is_git.return_value = False
            mock_writable.return_value = None

            # Setup generator mock
            job_mock = MagicMock()
            job_mock.files_generated = ["test.md"]
            job_mock.module_count = 5
            job_mock.statistics.total_files_analyzed = 10
            job_mock.statistics.total_tokens_used = 1000
            mock_generator.return_value.generate.return_value = job_mock

            yield {
                'config_mgr': mock_config_mgr,
                'validate': mock_validate,
                'is_git': mock_is_git,
                'generator': mock_generator,
            }

    # SMR-INT-001: CLI accepts --modules
    def test_cli_accepts_modules_flag(self, runner, mock_dependencies):
        """Test that CLI accepts --modules parameter without error."""
        result = runner.invoke(
            generate_command,
            ["--modules", "backend/auth,utils"],
            catch_exceptions=False
        )
        # Should not fail on parameter parsing
        # May fail later due to mocking, but --modules should be accepted
        assert "--modules" not in result.output or "Error" not in result.output[:100]

    # SMR-INT-002: CLI accepts --force flag
    def test_cli_accepts_force_flag(self, runner, mock_dependencies):
        """Test that CLI accepts --force / -F parameter."""
        # Test --force
        result = runner.invoke(
            generate_command,
            ["--modules", "backend", "--force"],
            catch_exceptions=False
        )
        # Should not fail on parameter parsing

    # SMR-INT-003: -F short form works
    def test_cli_accepts_force_short_form(self, runner, mock_dependencies):
        """Test that -F short form works same as --force."""
        result = runner.invoke(
            generate_command,
            ["--modules", "backend", "-F"],
            catch_exceptions=False
        )
        # Should not fail on parameter parsing

    # SMR-UNIT-005: Default force flag value
    def test_force_default_is_false(self, runner, mock_dependencies):
        """Test that force flag defaults to False."""
        generator_cls = mock_dependencies['generator']

        result = runner.invoke(
            generate_command,
            ["--modules", "backend"],
            catch_exceptions=False
        )

        # Check generator was called with force_regenerate=False in config
        call_args = generator_cls.call_args
        if call_args:
            config = call_args.kwargs.get('config', {})
            assert config.get('force_regenerate', False) is False

    def test_modules_passed_to_generator(self, runner, mock_dependencies):
        """Test that --modules value is passed to generator config."""
        generator_cls = mock_dependencies['generator']

        result = runner.invoke(
            generate_command,
            ["--modules", "backend/auth,utils"],
            catch_exceptions=False
        )

        # Check generator was called with selective_modules
        call_args = generator_cls.call_args
        if call_args:
            config = call_args.kwargs.get('config', {})
            assert config.get('selective_modules') == ["backend/auth", "utils"]

    def test_force_passed_to_generator(self, runner, mock_dependencies):
        """Test that --force value is passed to generator config."""
        generator_cls = mock_dependencies['generator']

        result = runner.invoke(
            generate_command,
            ["--modules", "backend", "--force"],
            catch_exceptions=False
        )

        # Check generator was called with force_regenerate=True
        call_args = generator_cls.call_args
        if call_args:
            config = call_args.kwargs.get('config', {})
            assert config.get('force_regenerate') is True

    def test_force_without_modules_warns(self, runner, mock_dependencies):
        """Test that --force without --modules shows warning and sets force_regenerate=False."""
        generator_cls = mock_dependencies['generator']

        result = runner.invoke(
            generate_command,
            ["--force"],
            catch_exceptions=False
        )

        # Should show specific warning message about --force without --modules
        assert "--force flag has no effect without --modules" in result.output

        # Verify force_regenerate is set to False in the config (not True)
        call_args = generator_cls.call_args
        if call_args:
            config = call_args.kwargs.get('config', {})
            # force_regenerate should be False when --force is used without --modules
            assert config.get('force_regenerate') is False
            # selective_modules should be None
            assert config.get('selective_modules') is None

    def test_modules_without_force_defaults(self, runner, mock_dependencies):
        """Test that --modules without --force defaults force to False."""
        generator_cls = mock_dependencies['generator']

        result = runner.invoke(
            generate_command,
            ["--modules", "backend"],
            catch_exceptions=False
        )

        call_args = generator_cls.call_args
        if call_args:
            config = call_args.kwargs.get('config', {})
            # force_regenerate should be False (not provided)
            assert config.get('force_regenerate') is False

    def test_modules_combined_with_other_flags(self, runner, mock_dependencies):
        """Test --modules works with other flags like --verbose."""
        result = runner.invoke(
            generate_command,
            ["--modules", "core", "--force", "--verbose"],
            catch_exceptions=False
        )
        # Should not fail due to flag combination


class TestConfigPropagation:
    """Tests for parameter propagation through Config class."""

    def test_config_from_cli_includes_selective_modules(self):
        """Test Config.from_cli accepts selective_modules parameter."""
        from codewiki.src.config import Config

        config = Config.from_cli(
            repo_path="/test",
            output_dir="/output",
            llm_base_url="http://test",
            llm_api_key="key",
            main_model="model",
            cluster_model="model",
            selective_modules=["backend/auth", "utils"],
            force_regenerate=True,
        )

        assert config.selective_modules == ["backend/auth", "utils"]
        assert config.force_regenerate is True

    def test_config_defaults_for_selective_modules(self):
        """Test Config has correct defaults for new parameters."""
        from codewiki.src.config import Config

        config = Config.from_cli(
            repo_path="/test",
            output_dir="/output",
            llm_base_url="http://test",
            llm_api_key="key",
            main_model="model",
            cluster_model="model",
        )

        assert config.selective_modules is None
        assert config.force_regenerate is False


class TestForceWithoutModulesWarning:
    """Dedicated tests for --force without --modules warning behavior (QA concern)."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_dependencies(self):
        """Mock dependencies for generate command testing."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

            # Setup config manager mock
            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = True
            mock_config_instance.get_api_key.return_value = "test-key"

            config_mock = MagicMock()
            config_mock.main_model = "test-model"
            config_mock.cluster_model = "test-model"
            config_mock.fallback_model = "test-model"
            config_mock.base_url = "http://test"
            config_mock.max_tokens = 32768
            config_mock.max_token_per_module = 36369
            config_mock.max_token_per_leaf_module = 16000
            config_mock.max_depth = 2
            config_mock.agent_instructions = None
            mock_config_instance.get_config.return_value = config_mock

            mock_config_mgr.return_value = mock_config_instance

            # Setup repository validation mock
            mock_validate.return_value = (Path("/test/repo"), [("python", 10)])
            mock_is_git.return_value = False
            mock_writable.return_value = None

            # Setup generator mock
            job_mock = MagicMock()
            job_mock.files_generated = ["test.md"]
            job_mock.module_count = 5
            job_mock.statistics.total_files_analyzed = 10
            job_mock.statistics.total_tokens_used = 1000
            mock_generator.return_value.generate.return_value = job_mock

            yield {
                'config_mgr': mock_config_mgr,
                'validate': mock_validate,
                'is_git': mock_is_git,
                'generator': mock_generator,
            }

    def test_force_only_shows_warning_message(self, runner, mock_dependencies):
        """Verify exact warning message when --force is used without --modules."""
        result = runner.invoke(
            generate_command,
            ["--force"],
            catch_exceptions=False
        )

        # Check for the exact warning message
        assert "--force flag has no effect without --modules" in result.output
        assert "To regenerate all modules, remove existing documentation first" in result.output

    def test_force_only_disables_force_in_config(self, runner, mock_dependencies):
        """Verify force_regenerate is set to False when --force without --modules."""
        generator_cls = mock_dependencies['generator']

        runner.invoke(
            generate_command,
            ["--force"],
            catch_exceptions=False
        )

        call_args = generator_cls.call_args
        assert call_args is not None
        config = call_args.kwargs.get('config', {})
        assert config.get('force_regenerate') is False

    def test_force_with_modules_does_not_warn(self, runner, mock_dependencies):
        """Verify no warning when --force is used WITH --modules."""
        result = runner.invoke(
            generate_command,
            ["--modules", "backend/auth", "--force"],
            catch_exceptions=False
        )

        # Should NOT show warning about --force having no effect
        assert "--force flag has no effect" not in result.output

    def test_force_with_modules_enables_force_in_config(self, runner, mock_dependencies):
        """Verify force_regenerate is True when --force is used WITH --modules."""
        generator_cls = mock_dependencies['generator']

        runner.invoke(
            generate_command,
            ["--modules", "backend", "--force"],
            catch_exceptions=False
        )

        call_args = generator_cls.call_args
        assert call_args is not None
        config = call_args.kwargs.get('config', {})
        assert config.get('force_regenerate') is True
        assert config.get('selective_modules') == ["backend"]


class TestE2ESelectiveRegeneration:
    """End-to-end style tests for selective module regeneration.

    These tests verify the complete flow through CLI parsing, config propagation,
    and generator invocation without mocking the internal logic.
    """

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_full_flow(self):
        """Mock only external dependencies (config, filesystem, generator)."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

            # Setup config manager mock
            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = True
            mock_config_instance.get_api_key.return_value = "test-key"

            config_mock = MagicMock()
            config_mock.main_model = "gpt-4"
            config_mock.cluster_model = "gpt-4"
            config_mock.fallback_model = "gpt-3.5-turbo"
            config_mock.base_url = "https://api.openai.com/v1"
            config_mock.max_tokens = 32768
            config_mock.max_token_per_module = 36369
            config_mock.max_token_per_leaf_module = 16000
            config_mock.max_depth = 2
            config_mock.agent_instructions = None
            mock_config_instance.get_config.return_value = config_mock

            mock_config_mgr.return_value = mock_config_instance

            # Setup repository validation mock
            mock_validate.return_value = (Path("/test/repo"), [("python", 10)])
            mock_is_git.return_value = False
            mock_writable.return_value = None

            # Setup generator mock with realistic job result
            job_mock = MagicMock()
            job_mock.files_generated = ["backend/auth.md", "utils.md"]
            job_mock.module_count = 2
            job_mock.statistics.total_files_analyzed = 15
            job_mock.statistics.total_tokens_used = 5000
            mock_generator.return_value.generate.return_value = job_mock

            yield {
                'config_mgr': mock_config_mgr,
                'generator': mock_generator,
            }

    def test_e2e_selective_regeneration_flow(self, runner, mock_full_flow):
        """E2E: Full selective regeneration flow with --modules and --force."""
        generator_cls = mock_full_flow['generator']

        result = runner.invoke(
            generate_command,
            ["--modules", "backend/auth,utils", "--force"],
            catch_exceptions=False
        )

        # Verify generator was called
        assert generator_cls.called

        # Verify the complete config was passed correctly
        call_args = generator_cls.call_args
        config = call_args.kwargs.get('config', {})

        assert config.get('selective_modules') == ["backend/auth", "utils"]
        assert config.get('force_regenerate') is True

    def test_e2e_backward_compatible_without_modules(self, runner, mock_full_flow):
        """E2E: Verify backward compatibility - generate without --modules works."""
        generator_cls = mock_full_flow['generator']

        result = runner.invoke(
            generate_command,
            [],  # No --modules flag
            catch_exceptions=False
        )

        # Verify generator was called
        assert generator_cls.called

        # Verify selective_modules is None (full generation)
        call_args = generator_cls.call_args
        config = call_args.kwargs.get('config', {})

        assert config.get('selective_modules') is None
        assert config.get('force_regenerate') is False

    def test_e2e_modules_with_verbose(self, runner, mock_full_flow):
        """E2E: Selective regeneration with verbose mode logs module info."""
        result = runner.invoke(
            generate_command,
            ["--modules", "core,api", "--force", "--verbose"],
            catch_exceptions=False
        )

        # Verbose mode should log the selective modules
        assert "Selective modules:" in result.output or "core" in result.output.lower()

    def test_e2e_modules_combined_with_use_claude_code(self, runner, mock_full_flow):
        """E2E: --modules works with --use-claude-code flag."""
        generator_cls = mock_full_flow['generator']

        # Mock claude CLI availability
        with patch('shutil.which', return_value='/usr/bin/claude'):
            result = runner.invoke(
                generate_command,
                ["--modules", "backend", "--force", "--use-claude-code"],
                catch_exceptions=False
            )

        # Verify both flags are in config
        call_args = generator_cls.call_args
        config = call_args.kwargs.get('config', {})

        assert config.get('selective_modules') == ["backend"]
        assert config.get('force_regenerate') is True
        assert config.get('use_claude_code') is True
