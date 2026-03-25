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
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.prompt_template import (
    CLUSTER_REPO_PROMPT,
    CLUSTER_REPO_WITH_SEED_PROMPT,
    CLUSTER_MODULE_PROMPT,
    format_user_prompt,
    format_system_prompt,
    format_leaf_system_prompt,
)
from codewiki.src.be.prompt_template_v2 import (
    CLUSTER_REPO_PROMPT_V2,
    CLUSTER_REPO_WITH_SEED_PROMPT_V2,
    CLUSTER_MODULE_PROMPT_V2,
    format_cluster_prompt_v2,
)
from codewiki.src.be.cluster_modules import format_potential_core_components
from codewiki.src.be.utils import is_complex_module

logger = logging.getLogger(__name__)

# Default timeout for Claude Code CLI (seconds)
# Increased from 300s to 900s (15 min) for larger modules
DEFAULT_CLAUDE_CODE_TIMEOUT = 900

# Default max prompt size (in estimated tokens)
# Claude Code CLI with Opus 4.6 supports ~1M token context
# Setting to 800K to leave room for response and system prompt
DEFAULT_MAX_PROMPT_TOKENS = 800_000

# Debug mode - set CODEWIKI_DEBUG=1 to enable debug output
DEBUG_MODE = os.environ.get("CODEWIKI_DEBUG", "").lower() in ("1", "true", "yes")

# Debug output directory - defaults to current working directory
DEBUG_OUTPUT_DIR = os.environ.get("CODEWIKI_DEBUG_DIR", ".")


def _dump_debug_info(
    prompt: str,
    response: str,
    error_context: str = "",
    output_dir: str = None
) -> str:
    """
    Dump prompt and response to files for debugging.

    Args:
        prompt: The prompt that was sent to Claude
        response: The response received from Claude
        error_context: Additional context about the error
        output_dir: Directory to write debug files (defaults to DEBUG_OUTPUT_DIR)

    Returns:
        Path to the debug output directory
    """
    if output_dir is None:
        output_dir = DEBUG_OUTPUT_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = Path(output_dir) / f"codewiki_debug_{timestamp}"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Write prompt
    prompt_file = debug_dir / "prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    # Write response
    response_file = debug_dir / "response.txt"
    with open(response_file, "w", encoding="utf-8") as f:
        f.write(response)

    # Write error context if provided
    if error_context:
        error_file = debug_dir / "error.txt"
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(error_context)

    # Write summary
    summary_file = debug_dir / "summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"CodeWiki Debug Output\n")
        f.write(f"=" * 60 + "\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)\n")
        f.write(f"Response length: {len(response)} chars\n")
        f.write(f"\n")
        f.write(f"Files:\n")
        f.write(f"  - prompt.txt: Full prompt sent to Claude\n")
        f.write(f"  - response.txt: Full response from Claude\n")
        if error_context:
            f.write(f"  - error.txt: Error context\n")
        f.write(f"\n")
        f.write(f"Response preview (first 2000 chars):\n")
        f.write(f"-" * 60 + "\n")
        f.write(response[:2000])
        if len(response) > 2000:
            f.write(f"\n... (truncated, {len(response) - 2000} more chars)")

    logger.info(f"Debug info dumped to: {debug_dir}")
    return str(debug_dir)


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
    # Use --model to select a specific model (default: claude-opus-4-6[1m] for 1M context)
    import os
    model = os.environ.get("CODEWIKI_CLAUDE_MODEL", "claude-opus-4-6[1m]")
    cmd = [cli_path, "--print", "--dangerously-skip-permissions", "--model", model, "-p", "-"]

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

        # Log stderr if present (useful for debugging even on success)
        if result.stderr:
            logger.warning(f"Claude Code CLI stderr: {result.stderr[:500]}")

        if result.returncode != 0:
            logger.error(f"Claude Code CLI failed with exit code {result.returncode}")
            if result.stderr:
                logger.error(f"Claude Code CLI stderr (full): {result.stderr[:2000]}")
            if result.stdout:
                logger.error(f"Claude Code CLI stdout (tail): {result.stdout[-500:]}")
            raise ClaudeCodeError(
                f"Claude Code CLI returned non-zero exit code: {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        # Check for authentication errors in stdout (Claude CLI returns these with exit code 0)
        output = result.stdout or ""
        if "Invalid API key" in output or "Please run /login" in output:
            error_msg = (
                f"Claude Code CLI authentication failed. "
                f"Check CLAUDE_CODE_OAUTH_TOKEN environment variable. "
                f"Output: {output[:200]}"
            )
            logger.error(error_msg)
            raise ClaudeCodeError(error_msg, returncode=0, stderr=result.stderr)

        # Check for empty response - this indicates a problem
        if not output or len(output.strip()) == 0:
            error_msg = (
                f"Claude Code CLI returned empty response. "
                f"This may indicate an authentication issue or CLI error. "
                f"stderr: {result.stderr or 'empty'}"
            )
            logger.error(error_msg)
            # Dump debug info for empty response
            if DEBUG_MODE:
                _dump_debug_info(prompt, "", f"Empty response from CLI.\nstderr: {result.stderr or 'empty'}")
            raise ClaudeCodeError(error_msg, returncode=0, stderr=result.stderr)

        return output

    except subprocess.TimeoutExpired:
        raise ClaudeCodeError(f"Claude Code CLI timed out after {timeout} seconds")
    except FileNotFoundError:
        raise ClaudeCodeError(f"Claude Code CLI executable not found: {cli_path}")
    except ClaudeCodeError:
        raise  # Re-raise our own exceptions as-is
    except Exception as e:
        raise ClaudeCodeError(f"Failed to invoke Claude Code CLI: {str(e)}")


def _format_seed_modules_for_prompt(seed_modules: Dict[str, Any]) -> str:
    """Format seed modules as a readable string for the prompt."""
    lines = []
    for module_name, module_info in seed_modules.items():
        components_list = module_info.get("components", [])
        path = module_info.get("path", "")
        lines.append(f"Module: {module_name}")
        lines.append(f"  Path: {path}")
        lines.append(f"  Components ({len(components_list)}):")
        for comp in components_list[:10]:  # Show first 10 components
            lines.append(f"    - {comp}")
        if len(components_list) > 10:
            lines.append(f"    ... and {len(components_list) - 10} more")
        lines.append("")
    return "\n".join(lines)


def _get_seed_component_ids(seed_modules: Dict[str, Any]) -> set:
    """Get all component IDs that are already assigned to seed modules."""
    assigned = set()
    for module_info in seed_modules.values():
        assigned.update(module_info.get("components", []))
    return assigned


def claude_code_cluster(
    leaf_nodes: List[str],
    components: Dict[str, Node],
    config: Any,
    current_module_tree: Dict[str, Any] = None,
    current_module_name: Optional[str] = None,
    seed_modules: Optional[Dict[str, Any]] = None,
    use_v2_prompts: bool = True,
) -> Dict[str, Any]:
    """
    Cluster code components into modules using Claude Code CLI.

    Args:
        leaf_nodes: List of component IDs to cluster
        components: Dictionary mapping component IDs to Node objects
        config: Configuration object with claude_code_path and timeout settings
        current_module_tree: Current module tree for context (optional)
        current_module_name: Name of current module being subdivided (optional)
        seed_modules: Existing module tree to preserve and extend (optional)

    Returns:
        Dictionary representing the module tree with grouped components

    Raises:
        ClaudeCodeError: If clustering fails
    """
    if current_module_tree is None:
        current_module_tree = {}

    # Format the potential core components for the prompt
    potential_core_components, _ = format_potential_core_components(leaf_nodes, components)

    # Build the clustering prompt - use V2 advanced prompts by default for better reliability
    if use_v2_prompts:
        logger.info("Using V2 advanced prompt templates for clustering")
        prompt = format_cluster_prompt_v2(
            potential_core_components=potential_core_components,
            module_tree=current_module_tree if current_module_tree else None,
            module_name=current_module_name,
            seed_modules=seed_modules
        )
        if seed_modules:
            logger.info(f"Using seeded clustering with {len(seed_modules)} existing modules (V2 prompt)")
    else:
        # Legacy V1 prompts
        if seed_modules:
            # Use seed-aware prompt that preserves existing modules
            formatted_seed = _format_seed_modules_for_prompt(seed_modules)
            prompt = CLUSTER_REPO_WITH_SEED_PROMPT.format(
                seed_modules=formatted_seed,
                potential_core_components=potential_core_components
            )
            logger.info(f"Using seeded clustering with {len(seed_modules)} existing modules")
        elif current_module_tree == {}:
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

    # Debug mode: always dump prompt and response
    if DEBUG_MODE:
        debug_dir = _dump_debug_info(prompt, response, "Debug mode enabled - dumping all requests")
        logger.info(f"DEBUG: Prompt and response saved to {debug_dir}")

    # Parse the response - expect JSON wrapped in <GROUPED_COMPONENTS> tags
    try:
        # Try to find the tags (case-insensitive and flexible whitespace)
        import re

        # Look for the tags with flexible matching
        start_pattern = re.compile(r'<GROUPED_COMPONENTS>\s*', re.IGNORECASE)
        end_pattern = re.compile(r'\s*</GROUPED_COMPONENTS>', re.IGNORECASE)

        start_match = start_pattern.search(response)
        end_match = end_pattern.search(response)

        if not start_match or not end_match:
            # Try to find JSON-like content as fallback
            logger.warning(f"Missing GROUPED_COMPONENTS tags, attempting JSON extraction...")

            # Dump debug info on parsing failure
            debug_dir = _dump_debug_info(
                prompt, response,
                f"Missing GROUPED_COMPONENTS tags.\n"
                f"start_match: {start_match}\n"
                f"end_match: {end_match}\n"
                f"Response length: {len(response)} chars"
            )
            logger.warning(f"Debug info saved to: {debug_dir}")

            # Look for a dictionary pattern in the response
            json_pattern = re.compile(r'\{[^{}]*"[^"]+"\s*:\s*\{[^{}]*"path"[^}]*\}[^{}]*\}', re.DOTALL)
            json_match = json_pattern.search(response)

            if json_match:
                response_content = json_match.group(0)
                logger.info(f"Found JSON-like content: {response_content[:100]}...")
            else:
                logger.error(f"Invalid Claude Code response format - missing component tags: {response[:500]}...")
                return {}
        else:
            response_content = response[start_match.end():end_match.start()]

        # Clean up the content - remove any markdown code blocks
        response_content = response_content.strip()
        if response_content.startswith("```"):
            # Remove markdown code block markers
            lines = response_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response_content = "\n".join(lines)

        # Try to parse as Python dict (safer than eval)
        try:
            import ast
            module_tree = ast.literal_eval(response_content.strip())
        except (SyntaxError, ValueError) as parse_err:
            # Try JSON parsing as fallback
            try:
                module_tree = json.loads(response_content.strip())
            except json.JSONDecodeError as json_err:
                # Dump debug info on JSON parsing failure
                debug_dir = _dump_debug_info(
                    prompt, response,
                    f"JSON parsing failed.\n"
                    f"AST error: {parse_err}\n"
                    f"JSON error: {json_err}\n"
                    f"Content preview: {response_content[:500]}..."
                )
                logger.error(f"Failed to parse response as Python dict or JSON: {parse_err}")
                logger.error(f"Debug info saved to: {debug_dir}")
                return {}

        if not isinstance(module_tree, dict):
            # Dump debug info on type error
            debug_dir = _dump_debug_info(
                prompt, response,
                f"Invalid module tree type.\n"
                f"Expected: dict\n"
                f"Got: {type(module_tree)}\n"
                f"Value: {module_tree}"
            )
            logger.error(f"Invalid module tree format - expected dict, got {type(module_tree)}")
            logger.error(f"Debug info saved to: {debug_dir}")
            return {}

        # Normalize module tree: ensure each module has 'children' key for compatibility
        for module_name, module_info in module_tree.items():
            if isinstance(module_info, dict) and "children" not in module_info:
                module_info["children"] = {}

        logger.info(f"Successfully parsed {len(module_tree)} modules from Claude Code response")
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
