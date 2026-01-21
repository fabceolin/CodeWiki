"""
Gemini CLI adapter for CodeWiki.

This module provides functions to invoke Gemini CLI as an alternative LLM backend
for module clustering and documentation generation.

## Usage

The adapter invokes Gemini CLI in non-interactive mode with YOLO mode:
    gemini -y "prompt"

Or via stdin for large prompts:
    echo "prompt" | gemini -y

## Prompt Size Limits

Gemini 2.0 has a context window of approximately:
- **~1,000,000 tokens** (1M context window)

The adapter validates prompt size before sending and raises `GeminiCodeError`
if the prompt exceeds the configurable `max_prompt_tokens` limit (default: 900K tokens).

## Error Handling

- `GeminiCodeError`: Raised for all CLI failures (not found, timeout, exit code != 0, prompt too large)
- Timeout: Configurable via `gemini_code_timeout` in config (default: 600s)
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

# Default timeout for Gemini CLI (seconds) - longer due to larger context
DEFAULT_GEMINI_CODE_TIMEOUT = 600

# Default max prompt size (in estimated tokens)
# Gemini 2.0 has ~1M token context window
# Setting to 900K to leave room for response
DEFAULT_MAX_PROMPT_TOKENS = 900_000


class GeminiCodeError(Exception):
    """Exception raised when Gemini CLI invocation fails."""

    def __init__(self, message: str, returncode: Optional[int] = None, stderr: Optional[str] = None):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def _find_gemini_cli(config_path: Optional[str] = None) -> str:
    """
    Find the Gemini CLI executable.

    Args:
        config_path: Optional configured path to gemini CLI

    Returns:
        Path to gemini CLI executable

    Raises:
        GeminiCodeError: If CLI cannot be found
    """
    if config_path:
        if shutil.which(config_path):
            return config_path
        raise GeminiCodeError(f"Gemini CLI not found at configured path: {config_path}")

    # Try default 'gemini' in PATH
    gemini_path = shutil.which("gemini")
    if gemini_path:
        return gemini_path

    raise GeminiCodeError(
        "Gemini CLI not found in PATH. "
        "Please install Gemini CLI: npm install -g @anthropic-ai/gemini-cli "
        "or configure the path with 'codewiki config set --gemini-code-path <path>'"
    )


def _invoke_gemini_code(
    prompt: str,
    timeout: int = DEFAULT_GEMINI_CODE_TIMEOUT,
    gemini_code_path: Optional[str] = None,
    working_dir: Optional[str] = None,
    max_prompt_tokens: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> str:
    """
    Invoke Gemini CLI with a prompt and return the output.

    Args:
        prompt: The prompt to send to Gemini
        timeout: Timeout in seconds (default: 600)
        gemini_code_path: Optional path to gemini CLI executable
        working_dir: Optional working directory for the subprocess
        max_prompt_tokens: Maximum allowed prompt size in estimated tokens (default: 900K)

    Returns:
        The stdout output from Gemini CLI

    Raises:
        GeminiCodeError: If CLI invocation fails or prompt exceeds size limit
    """
    # Calculate prompt size metrics first
    prompt_chars = len(prompt)
    prompt_tokens_estimate = prompt_chars // 4  # Rough estimate: ~4 chars per token

    logger.info(f"Prompt size: {prompt_chars:,} chars (~{prompt_tokens_estimate:,} tokens estimated)")

    # Check prompt size limit before invoking CLI
    if prompt_tokens_estimate > max_prompt_tokens:
        raise GeminiCodeError(
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

    cli_path = _find_gemini_cli(gemini_code_path)

    # Build command - use -y for YOLO mode (auto-approve all actions)
    # Use --output-format text for clean output
    # Prompt is passed via stdin to handle large prompts
    cmd = [cli_path, "-y", "--output-format", "text"]

    logger.info(f"Invoking Gemini CLI: {cli_path}")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,  # Pass prompt via stdin
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        if result.returncode != 0:
            raise GeminiCodeError(
                f"Gemini CLI returned non-zero exit code: {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        # Filter out Gemini CLI log lines from stdout
        output_lines = result.stdout.split('\n')
        filtered_lines = []
        skip_prefixes = (
            'YOLO mode',
            'Loaded cached',
            'Loading extension',
            'Initializing',
            'Connected to',
        )
        for line in output_lines:
            if not any(line.startswith(prefix) for prefix in skip_prefixes):
                filtered_lines.append(line)

        return '\n'.join(filtered_lines)

    except subprocess.TimeoutExpired:
        raise GeminiCodeError(f"Gemini CLI timed out after {timeout} seconds")
    except FileNotFoundError:
        raise GeminiCodeError(f"Gemini CLI executable not found: {cli_path}")
    except GeminiCodeError:
        raise  # Re-raise our own exceptions as-is
    except Exception as e:
        raise GeminiCodeError(f"Failed to invoke Gemini CLI: {str(e)}")


def gemini_code_cluster(
    leaf_nodes: List[str],
    components: Dict[str, Node],
    config: Any,
    current_module_tree: Dict[str, Any] = None,
    current_module_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cluster code components into modules using Gemini CLI.

    Args:
        leaf_nodes: List of component IDs to cluster
        components: Dictionary mapping component IDs to Node objects
        config: Configuration object with gemini_code_path and timeout settings
        current_module_tree: Current module tree for context (optional)
        current_module_name: Name of current module being subdivided (optional)

    Returns:
        Dictionary representing the module tree with grouped components

    Raises:
        GeminiCodeError: If clustering fails
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
    timeout = getattr(config, "gemini_code_timeout", DEFAULT_GEMINI_CODE_TIMEOUT)
    gemini_path = getattr(config, "gemini_code_path", None)

    # Invoke Gemini CLI
    logger.info("Invoking Gemini CLI for module clustering...")
    response = _invoke_gemini_code(prompt, timeout=timeout, gemini_code_path=gemini_path)

    # Parse the response - expect JSON wrapped in <GROUPED_COMPONENTS> tags
    # Be more flexible: try to find JSON even if closing tag is missing
    try:
        if "<GROUPED_COMPONENTS>" in response:
            # Extract content after opening tag
            response_content = response.split("<GROUPED_COMPONENTS>")[1]
            # Try to find closing tag, but if not present, use the rest
            if "</GROUPED_COMPONENTS>" in response_content:
                response_content = response_content.split("</GROUPED_COMPONENTS>")[0]
            # Clean up any trailing text after the JSON
            response_content = response_content.strip()
        else:
            # Try to find raw JSON in response
            logger.warning("No <GROUPED_COMPONENTS> tag found, attempting to parse raw JSON...")
            response_content = response.strip()

        # Try to parse as JSON first, fall back to eval
        import json
        try:
            module_tree = json.loads(response_content)
        except json.JSONDecodeError:
            # Try eval as fallback (for Python dict literals)
            module_tree = eval(response_content)

        if not isinstance(module_tree, dict):
            logger.error(f"Invalid module tree format - expected dict, got {type(module_tree)}")
            return {}

        # Normalize module tree: ensure each module has 'children' key for compatibility
        for module_name, module_info in module_tree.items():
            if "children" not in module_info:
                module_info["children"] = {}

        return module_tree

    except Exception as e:
        logger.error(f"Failed to parse Gemini clustering response: {e}")
        logger.error(f"Response: {response[:500]}...")
        return {}


def gemini_code_generate_docs(
    module_name: str,
    core_component_ids: List[str],
    components: Dict[str, Node],
    module_tree: Dict[str, Any],
    config: Any,
    output_path: str,
) -> str:
    """
    Generate documentation for a module using Gemini CLI.

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
        GeminiCodeError: If documentation generation fails
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

    # Combine into full prompt for Gemini CLI
    full_prompt = f"""You are a documentation assistant. Follow these instructions:

{system_prompt}

---

Now complete this task:

{user_prompt}

IMPORTANT: Output ONLY the markdown documentation content. Do not wrap in code blocks.
Save the documentation to: {output_path}/{module_name}.md
"""

    # Get timeout and path from config
    timeout = getattr(config, "gemini_code_timeout", DEFAULT_GEMINI_CODE_TIMEOUT)
    gemini_path = getattr(config, "gemini_code_path", None)
    repo_path = getattr(config, "repo_path", None)

    # Invoke Gemini CLI
    logger.info(f"Invoking Gemini CLI for documentation: {module_name}")
    response = _invoke_gemini_code(
        full_prompt,
        timeout=timeout,
        gemini_code_path=gemini_path,
        working_dir=repo_path,
    )

    return response


def gemini_code_generate_overview(
    prompt: str,
    config: Any,
) -> str:
    """
    Generate repository or module overview using Gemini CLI.

    Args:
        prompt: The formatted overview prompt (REPO_OVERVIEW_PROMPT or MODULE_OVERVIEW_PROMPT)
        config: Configuration object

    Returns:
        The raw response from Gemini CLI

    Raises:
        GeminiCodeError: If overview generation fails
    """
    # Get timeout and path from config
    timeout = getattr(config, "gemini_code_timeout", DEFAULT_GEMINI_CODE_TIMEOUT)
    gemini_path = getattr(config, "gemini_code_path", None)
    repo_path = getattr(config, "repo_path", None)

    logger.info("Invoking Gemini CLI for overview generation...")
    response = _invoke_gemini_code(
        prompt,
        timeout=timeout,
        gemini_code_path=gemini_path,
        working_dir=repo_path,
    )

    return response
