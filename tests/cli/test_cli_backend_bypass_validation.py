"""
Tests for CLI backend bypass API key validation feature.

Tests cover:
- --use-claude-code bypasses API key validation
- --use-gemini-code bypasses API key validation
- Direct API mode still requires API key validation
- CLI binary validation still works
- Default config created when using CLI backend without config file
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from click.testing import CliRunner

from codewiki.cli.commands.generate import generate_command


class TestCLIBackendBypassValidation:
    """Tests for CLI backend API key bypass validation."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_generator_only(self):
        """Mock only generator and filesystem - config manager is tested."""
        with patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

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
                'validate': mock_validate,
                'is_git': mock_is_git,
                'generator': mock_generator,
            }

    # Test: Direct API mode requires API key
    def test_direct_api_mode_requires_config(self, runner, mock_generator_only):
        """Direct API mode (no CLI flags) requires API key configuration."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr:
            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = False  # No config file
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                [],  # No CLI backend flags
                catch_exceptions=False
            )

            # Should fail with configuration error
            assert result.exit_code != 0
            assert "Configuration not found" in result.output or "config" in result.output.lower()

    def test_direct_api_mode_requires_api_key(self, runner, mock_generator_only):
        """Direct API mode requires API key to be configured."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr:
            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = False  # API key not set
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                [],  # No CLI backend flags
                catch_exceptions=False
            )

            # Should fail with configuration error
            assert result.exit_code != 0
            assert "incomplete" in result.output.lower() or "config" in result.output.lower()

    # Test: Claude Code CLI bypasses API key validation
    def test_claude_code_bypasses_api_key_check_no_config(self, runner, mock_generator_only):
        """--use-claude-code should work without any configuration file."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/claude'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = False  # No config file
            mock_config_instance.get_config.return_value = None
            mock_config_instance.get_api_key.return_value = None
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-claude-code"],
                catch_exceptions=False
            )

            # Should NOT fail on config validation
            # May fail later for other reasons, but not config
            assert "Configuration not found" not in result.output
            assert "Configuration is incomplete" not in result.output

    def test_claude_code_bypasses_api_key_check_incomplete_config(self, runner, mock_generator_only):
        """--use-claude-code works even with incomplete config (no API key)."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/claude'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = False  # Would fail without CLI flag

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
            mock_config_instance.get_api_key.return_value = None  # No API key

            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-claude-code"],
                catch_exceptions=False
            )

            # Should NOT fail on config validation
            assert "Configuration is incomplete" not in result.output

    # Test: Gemini CLI bypasses API key validation
    def test_gemini_code_bypasses_api_key_check_no_config(self, runner, mock_generator_only):
        """--use-gemini-code should work without any configuration file."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/gemini'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = False  # No config file
            mock_config_instance.get_config.return_value = None
            mock_config_instance.get_api_key.return_value = None
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-gemini-code"],
                catch_exceptions=False
            )

            # Should NOT fail on config validation
            assert "Configuration not found" not in result.output
            assert "Configuration is incomplete" not in result.output

    def test_gemini_code_bypasses_api_key_check_incomplete_config(self, runner, mock_generator_only):
        """--use-gemini-code works even with incomplete config (no API key)."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/gemini'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = False  # Would fail without CLI flag

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
            mock_config_instance.get_api_key.return_value = None  # No API key

            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-gemini-code"],
                catch_exceptions=False
            )

            # Should NOT fail on config validation
            assert "Configuration is incomplete" not in result.output


class TestCLIBinaryValidation:
    """Tests for CLI binary availability validation."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    def test_claude_code_not_found_error(self, runner):
        """--use-claude-code fails gracefully when claude binary not found."""
        with patch('shutil.which', return_value=None):
            result = runner.invoke(
                generate_command,
                ["--use-claude-code"],
                catch_exceptions=False
            )

            assert result.exit_code != 0
            assert "Claude Code CLI not found" in result.output

    def test_gemini_code_not_found_error(self, runner):
        """--use-gemini-code fails gracefully when gemini binary not found."""
        with patch('shutil.which', return_value=None):
            result = runner.invoke(
                generate_command,
                ["--use-gemini-code"],
                catch_exceptions=False
            )

            assert result.exit_code != 0
            assert "Gemini CLI not found" in result.output


class TestCLIBackendMutualExclusivity:
    """Tests for CLI backend mutual exclusivity."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    def test_cannot_use_both_cli_backends(self, runner):
        """Cannot use --use-claude-code and --use-gemini-code together."""
        with patch('shutil.which', return_value='/usr/bin/claude'):
            result = runner.invoke(
                generate_command,
                ["--use-claude-code", "--use-gemini-code"],
                catch_exceptions=False
            )

            assert result.exit_code != 0
            assert "Cannot use both" in result.output


class TestDefaultConfigForCLIBackend:
    """Tests for default configuration creation in CLI backend mode."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_generator_only(self):
        """Mock only generator and filesystem."""
        with patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

            mock_validate.return_value = (Path("/test/repo"), [("python", 10)])
            mock_is_git.return_value = False
            mock_writable.return_value = None

            job_mock = MagicMock()
            job_mock.files_generated = ["test.md"]
            job_mock.module_count = 5
            job_mock.statistics.total_files_analyzed = 10
            job_mock.statistics.total_tokens_used = 1000
            mock_generator.return_value.generate.return_value = job_mock

            yield {
                'generator': mock_generator,
            }

    def test_default_config_created_for_claude_backend(self, runner, mock_generator_only):
        """Default config values used when using Claude backend without config file."""
        generator_cls = mock_generator_only['generator']

        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/claude'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = False
            mock_config_instance.get_config.return_value = None
            mock_config_instance.get_api_key.return_value = None
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-claude-code"],
                catch_exceptions=False
            )

            # Verify generator was called with default values
            call_args = generator_cls.call_args
            assert call_args is not None
            config = call_args.kwargs.get('config', {})

            # Default values from Configuration class
            assert config.get('max_tokens') == 32768
            assert config.get('max_token_per_module') == 36369
            assert config.get('max_token_per_leaf_module') == 16000
            assert config.get('max_depth') == 2
            assert config.get('use_claude_code') is True

    def test_default_config_created_for_gemini_backend(self, runner, mock_generator_only):
        """Default config values used when using Gemini backend without config file."""
        generator_cls = mock_generator_only['generator']

        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('shutil.which', return_value='/usr/bin/gemini'):

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = False
            mock_config_instance.get_config.return_value = None
            mock_config_instance.get_api_key.return_value = None
            mock_config_mgr.return_value = mock_config_instance

            result = runner.invoke(
                generate_command,
                ["--use-gemini-code"],
                catch_exceptions=False
            )

            # Verify generator was called with default values
            call_args = generator_cls.call_args
            assert call_args is not None
            config = call_args.kwargs.get('config', {})

            # Default values from Configuration class
            assert config.get('max_tokens') == 32768
            assert config.get('max_depth') == 2
            assert config.get('use_gemini_code') is True


class TestRegressionDirectAPIMode:
    """Regression tests to ensure direct API mode behavior is unchanged."""

    @pytest.fixture
    def runner(self):
        """Create a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_configured_dependencies(self):
        """Mock with fully configured dependencies (direct API mode)."""
        with patch('codewiki.cli.commands.generate.ConfigManager') as mock_config_mgr, \
             patch('codewiki.cli.commands.generate.validate_repository') as mock_validate, \
             patch('codewiki.cli.commands.generate.is_git_repository') as mock_is_git, \
             patch('codewiki.cli.commands.generate.check_writable_output') as mock_writable, \
             patch('codewiki.cli.commands.generate.CLIDocumentationGenerator') as mock_generator:

            mock_config_instance = MagicMock()
            mock_config_instance.load.return_value = True
            mock_config_instance.is_configured.return_value = True
            mock_config_instance.get_api_key.return_value = "test-api-key"

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

            mock_validate.return_value = (Path("/test/repo"), [("python", 10)])
            mock_is_git.return_value = False
            mock_writable.return_value = None

            job_mock = MagicMock()
            job_mock.files_generated = ["test.md"]
            job_mock.module_count = 5
            job_mock.statistics.total_files_analyzed = 10
            job_mock.statistics.total_tokens_used = 1000
            mock_generator.return_value.generate.return_value = job_mock

            yield {
                'config_mgr': mock_config_mgr,
                'generator': mock_generator,
            }

    def test_direct_api_mode_still_works_with_config(self, runner, mock_configured_dependencies):
        """Direct API mode works normally when properly configured."""
        generator_cls = mock_configured_dependencies['generator']

        result = runner.invoke(
            generate_command,
            [],  # No CLI backend flags - direct API mode
            catch_exceptions=False
        )

        # Should succeed
        assert generator_cls.called

        # Verify API key is passed to generator
        call_args = generator_cls.call_args
        config = call_args.kwargs.get('config', {})
        assert config.get('api_key') == "test-api-key"
        assert config.get('use_claude_code') is False
        assert config.get('use_gemini_code') is False

    def test_direct_api_mode_uses_configured_models(self, runner, mock_configured_dependencies):
        """Direct API mode uses configured model settings."""
        generator_cls = mock_configured_dependencies['generator']

        result = runner.invoke(
            generate_command,
            [],
            catch_exceptions=False
        )

        call_args = generator_cls.call_args
        config = call_args.kwargs.get('config', {})
        assert config.get('main_model') == "test-model"
        assert config.get('cluster_model') == "test-model"
        assert config.get('base_url') == "http://test"
