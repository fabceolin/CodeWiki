"""
Claude Code CLI adapter for CodeWiki.

This module provides functions to invoke Claude Code CLI as an alternative LLM backend
for module clustering and documentation generation.

## Usage

The adapter invokes Claude Code CLI in non-interactive mode:
    claude --print --dangerously-skip-permissions -p -

Prompts are passed via stdin (not command line args) to support large prompts.

## Prompt Size Limits

Claude Code CLI has a prompt size limit of approximately:
- **~790,000 characters**
- **~198,000 tokens** (estimated at ~4 chars/token)

When exceeded, CLI returns exit code 1 with message: "Prompt is too long"

The adapter validates prompt size before sending and raises `ClaudeCodeError`
if the prompt exceeds the configurable `max_prompt_tokens` limit (default: 180K tokens).

## Error Handling

- `ClaudeCodeError`: Raised for all CLI failures (not found, timeout, exit code != 0, prompt too large)
- Timeout: Configurable via `claude_code_timeout` in config (default: 300s)
"""

import json
import logging
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.prompt_template import (
    CLUSTER_REPO_PROMPT,
    CLUSTER_MODULE_PROMPT,
    format_user_prompt,
    format_system_prompt,
    format_leaf_system_prompt,
)
from codewiki.src.be.cluster_modules import format_potential_core_components
from codewiki.src.be.utils import is_complex_module

logger = logging.getLogger(__name__)

# Default timeout for Claude Code CLI (seconds)
# Increased from 300s to 900s (15 min) for larger modules
DEFAULT_CLAUDE_CODE_TIMEOUT = 900

# Default max prompt size (in estimated tokens)
# Claude Code CLI limit is ~790K chars (~198K tokens)
# Setting to 180K to leave room for response and system prompt
DEFAULT_MAX_PROMPT_TOKENS = 180_000


class ClaudeCodeError(Exception):
    """Exception raised when Claude Code CLI invocation fails."""

    def __init__(self, message: str, returncode: Optional[int] = None, stderr: Optional[str] = None):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def _find_claude_code_cli(config_path: Optional[str] = None) -> str:
    """
    Find the Claude Code CLI executable.

    Args:
        config_path: Optional configured path to claude CLI

    Returns:
        Path to claude CLI executable

    Raises:
        ClaudeCodeError: If CLI cannot be found
    """
    if config_path:
        if shutil.which(config_path):
            return config_path
        raise ClaudeCodeError(f"Claude Code CLI not found at configured path: {config_path}")

    # Try default 'claude' in PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    raise ClaudeCodeError(
        "Claude Code CLI not found in PATH. "
        "Please install Claude Code CLI or configure the path with 'codewiki config set --claude-code-path <path>'"
    )


def _invoke_claude_code(
    prompt: str,
    timeout: int = DEFAULT_CLAUDE_CODE_TIMEOUT,
    claude_code_path: Optional[str] = None,
    working_dir: Optional[str] = None,
    max_prompt_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> str:
    """
    Invoke Claude Code CLI with a prompt and return the output.

    Args:
        prompt: The prompt to send to Claude Code
        timeout: Timeout in seconds (default: 300)
        claude_code_path: Optional path to claude CLI executable
        working_dir: Optional working directory for the subprocess
        max_prompt_tokens: Maximum allowed prompt size in estimated tokens (default: 150K)

    Returns:
        The stdout output from Claude Code CLI

    Raises:
        ClaudeCodeError: If CLI invocation fails or prompt exceeds size limit
    """
    # Calculate prompt size metrics first
    prompt_chars = len(prompt)
    prompt_tokens_estimate = prompt_chars // 4  # Rough estimate: ~4 chars per token

    logger.info(f"Prompt size: {prompt_chars:,} chars (~{prompt_tokens_estimate:,} tokens estimated)")

    # Check prompt size limit before invoking CLI
    if prompt_tokens_estimate > max_prompt_tokens:
        raise ClaudeCodeError(
            f"Prompt too large: ~{prompt_tokens_estimate:,} tokens estimated, "
            f"max allowed: {max_prompt_tokens:,} tokens. "
            f"Consider reducing the scope or splitting the request."
        )

    # Warn if prompt is approaching the limit (over 66% of max)
    if prompt_tokens_estimate > max_prompt_tokens * 0.66:
        logger.warning(
            f"Large prompt: ~{prompt_tokens_estimate:,} tokens "
            f"({prompt_tokens_estimate * 100 // max_prompt_tokens}% of {max_prompt_tokens:,} limit)"
        )

    cli_path = _find_claude_code_cli(claude_code_path)

    # Build command - use --print for non-interactive mode
    # --dangerously-skip-permissions allows automated execution without interactive prompts
    # Prompt is passed via stdin to handle large prompts (CLI args have size limits)
    cmd = [cli_path, "--print", "--dangerously-skip-permissions", "-p", "-"]

    logger.info(f"Invoking Claude Code CLI: {cli_path}")

    try:
        # Inherit environment and add any Claude-specific env vars
        import os
        env = os.environ.copy()

        result = subprocess.run(
            cmd,
            input=prompt,  # Pass prompt via stdin
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
            env=env,  # Pass environment variables including CLAUDE_CODE_OAUTH_TOKEN
        )

        if result.returncode != 0:
            raise ClaudeCodeError(
                f"Claude Code CLI returned non-zero exit code: {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return result.stdout

    except subprocess.TimeoutExpired:
        raise ClaudeCodeError(f"Claude Code CLI timed out after {timeout} seconds")
    except FileNotFoundError:
        raise ClaudeCodeError(f"Claude Code CLI executable not found: {cli_path}")
    except ClaudeCodeError:
        raise  # Re-raise our own exceptions as-is
    except Exception as e:
        raise ClaudeCodeError(f"Failed to invoke Claude Code CLI: {str(e)}")


def claude_code_cluster(
    leaf_nodes: List[str],
    components: Dict[str, Node],
    config: Any,
    current_module_tree: Dict[str, Any] = None,
    current_module_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cluster code components into modules using Claude Code CLI.

    Args:
        leaf_nodes: List of component IDs to cluster
        components: Dictionary mapping component IDs to Node objects
        config: Configuration object with claude_code_path and timeout settings
        current_module_tree: Current module tree for context (optional)
        current_module_name: Name of current module being subdivided (optional)

    Returns:
        Dictionary representing the module tree with grouped components

    Raises:
        ClaudeCodeError: If clustering fails
    """
    if current_module_tree is None:
        current_module_tree = {}

    # Format the potential core components for the prompt
    potential_core_components, _ = format_potential_core_components(leaf_nodes, components)

    # Build the clustering prompt
    if current_module_tree == {}:
        prompt = CLUSTER_REPO_PROMPT.format(potential_core_components=potential_core_components)
    else:
        # Format the module tree for context
        lines = []

        def _format_tree(tree: Dict[str, Any], indent: int = 0):
            for key, value in tree.items():
                if key == current_module_name:
                    lines.append(f"{'  ' * indent}{key} (current module)")
                else:
                    lines.append(f"{'  ' * indent}{key}")
                lines.append(f"{'  ' * (indent + 1)} Core components: {', '.join(value.get('components', []))}")
                children = value.get("children", {})
                if isinstance(children, dict) and len(children) > 0:
                    lines.append(f"{'  ' * (indent + 1)} Children:")
                    _format_tree(children, indent + 2)

        _format_tree(current_module_tree, 0)
        formatted_module_tree = "\n".join(lines)

        prompt = CLUSTER_MODULE_PROMPT.format(
            potential_core_components=potential_core_components,
            module_tree=formatted_module_tree,
            module_name=current_module_name,
        )

    # Get timeout and path from config
    timeout = getattr(config, "claude_code_timeout", DEFAULT_CLAUDE_CODE_TIMEOUT)
    claude_path = getattr(config, "claude_code_path", None)

    # Invoke Claude Code CLI
    logger.info("Invoking Claude Code CLI for module clustering...")
    response = _invoke_claude_code(prompt, timeout=timeout, claude_code_path=claude_path)

    # Parse the response - expect JSON wrapped in <GROUPED_COMPONENTS> tags
    try:
        if "<GROUPED_COMPONENTS>" not in response or "</GROUPED_COMPONENTS>" not in response:
            logger.error(f"Invalid Claude Code response format - missing component tags: {response[:200]}...")
            return {}

        response_content = response.split("<GROUPED_COMPONENTS>")[1].split("</GROUPED_COMPONENTS>")[0]
        module_tree = eval(response_content.strip())

        if not isinstance(module_tree, dict):
            logger.error(f"Invalid module tree format - expected dict, got {type(module_tree)}")
            return {}

        # Normalize module tree: ensure each module has 'children' key for compatibility
        for module_name, module_info in module_tree.items():
            if "children" not in module_info:
                module_info["children"] = {}

        return module_tree

    except Exception as e:
        logger.error(f"Failed to parse Claude Code clustering response: {e}")
        logger.error(f"Response: {response[:500]}...")
        return {}


def claude_code_generate_docs(
    module_name: str,
    core_component_ids: List[str],
    components: Dict[str, Node],
    module_tree: Dict[str, Any],
    config: Any,
    output_path: str,
) -> str:
    """
    Generate documentation for a module using Claude Code CLI.

    Args:
        module_name: Name of the module to document
        core_component_ids: List of component IDs in this module
        components: Dictionary mapping component IDs to Node objects
        module_tree: The full module tree for context
        config: Configuration object
        output_path: Path where documentation should be saved

    Returns:
        The generated markdown documentation

    Raises:
        ClaudeCodeError: If documentation generation fails
    """
    # Determine if this is a complex or leaf module
    is_complex = is_complex_module(components, core_component_ids)

    # Get custom instructions from config
    custom_instructions = None
    if hasattr(config, "get_prompt_addition"):
        custom_instructions = config.get_prompt_addition()

    # Build system prompt based on complexity
    if is_complex:
        system_prompt = format_system_prompt(module_name, custom_instructions)
    else:
        system_prompt = format_leaf_system_prompt(module_name, custom_instructions)

    # Build user prompt with module context
    user_prompt = format_user_prompt(
        module_name=module_name,
        core_component_ids=core_component_ids,
        components=components,
        module_tree=module_tree,
    )

    # Combine into full prompt for Claude Code CLI
    # Claude Code handles system/user separation internally, so we combine them
    full_prompt = f"""You are a documentation assistant. Follow these instructions:

{system_prompt}

---

Now complete this task:

{user_prompt}

IMPORTANT: Output ONLY the markdown documentation content. Do not wrap in code blocks.
Save the documentation to: {output_path}/{module_name}.md
"""

    # Get timeout and path from config
    timeout = getattr(config, "claude_code_timeout", DEFAULT_CLAUDE_CODE_TIMEOUT)
    claude_path = getattr(config, "claude_code_path", None)
    repo_path = getattr(config, "repo_path", None)

    # Invoke Claude Code CLI
    logger.info(f"Invoking Claude Code CLI for documentation: {module_name}")
    response = _invoke_claude_code(
        full_prompt,
        timeout=timeout,
        claude_code_path=claude_path,
        working_dir=repo_path,
    )

    return response


def claude_code_generate_overview(
    prompt: str,
    config: Any,
) -> str:
    """
    Generate repository or module overview using Claude Code CLI.

    Args:
        prompt: The formatted overview prompt (REPO_OVERVIEW_PROMPT or MODULE_OVERVIEW_PROMPT)
        config: Configuration object

    Returns:
        The raw response from Claude Code CLI

    Raises:
        ClaudeCodeError: If overview generation fails
    """
    # Get timeout and path from config
    timeout = getattr(config, "claude_code_timeout", DEFAULT_CLAUDE_CODE_TIMEOUT)
    claude_path = getattr(config, "claude_code_path", None)
    repo_path = getattr(config, "repo_path", None)

    logger.info("Invoking Claude Code CLI for overview generation...")
    response = _invoke_claude_code(
        prompt,
        timeout=timeout,
        claude_code_path=claude_path,
        working_dir=repo_path,
    )

    return response
