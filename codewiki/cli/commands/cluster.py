"""
Cluster command for module clustering from dependency graph.
"""

import sys
import json
import logging
import os
from pathlib import Path
from typing import Optional
import click

from codewiki.cli.config_manager import ConfigManager
from codewiki.cli.utils.errors import (
    ConfigurationError,
    FileSystemError,
    APIError,
    handle_error,
    EXIT_SUCCESS,
)
from codewiki.cli.utils.repo_validator import check_writable_output
from codewiki.cli.utils.logging import create_logger
from codewiki.src.config import Config, FIRST_MODULE_TREE_FILENAME, MODULE_TREE_FILENAME


def validate_dependency_graph_schema(data: dict) -> bool:
    """
    Validate that the input JSON has the required schema.

    Expected schema:
    {
        "metadata": {...},
        "components": {...},
        "leaf_nodes": [...]
    }
    """
    if not isinstance(data, dict):
        return False
    if "components" not in data:
        return False
    if "leaf_nodes" not in data:
        return False
    if not isinstance(data["components"], dict):
        return False
    if not isinstance(data["leaf_nodes"], list):
        return False
    return True


@click.command(name="cluster")
@click.option(
    "--input",
    "-i",
    "input_path",
    type=click.Path(exists=True),
    required=True,
    help="Path to dependency_graph.json or directory containing it",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output directory for module tree files (default: same as input)",
)
@click.option(
    "--use-claude-code",
    is_flag=True,
    help="Use Claude Code CLI as the LLM backend instead of direct API calls",
)
@click.option(
    "--use-gemini-code",
    is_flag=True,
    help="Use Gemini CLI as the LLM backend instead of direct API calls (supports larger context)",
)
@click.option(
    "--max-token-per-module",
    type=int,
    default=None,
    help="Maximum tokens per module for clustering (overrides config)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum depth for hierarchical decomposition (overrides config)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress and debug information",
)
@click.pass_context
def cluster_command(
    ctx,
    input_path: str,
    output: Optional[str],
    use_claude_code: bool,
    use_gemini_code: bool,
    max_token_per_module: Optional[int],
    max_depth: Optional[int],
    verbose: bool,
):
    """
    Cluster code components into modules from a dependency graph.

    This command reads a dependency graph JSON file (from 'codewiki analyze') and
    clusters the components into hierarchical modules using LLM-guided partitioning.

    The output is two JSON files:
    - first_module_tree.json: Initial module tree structure
    - module_tree.json: Working copy of module tree

    These files can be used as input to 'codewiki document' for documentation generation.

    Examples:

    \b
    # Basic clustering with API
    $ codewiki cluster --input ./docs/dependency_graph.json

    \b
    # Cluster using Claude Code CLI (no API key required)
    $ codewiki cluster --input ./docs --use-claude-code

    \b
    # Cluster using Gemini CLI (larger context window)
    $ codewiki cluster --input ./docs --use-gemini-code

    \b
    # Custom output directory
    $ codewiki cluster --input ./docs --output ./clustering_output

    \b
    # Override clustering parameters
    $ codewiki cluster --input ./docs --max-token-per-module 50000 --max-depth 3

    \b
    # Verbose output for debugging
    $ codewiki cluster --input ./docs --verbose
    """
    logger = create_logger(verbose=verbose)

    # Suppress httpx INFO logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        # Step 1: Validate configuration
        logger.step("Validating configuration...", 1, 4)

        # Check CLI backend mutual exclusivity
        if use_claude_code and use_gemini_code:
            raise ConfigurationError(
                "Cannot use both --use-claude-code and --use-gemini-code.\n\n"
                "Please select only one CLI backend."
            )

        using_cli_backend = use_claude_code or use_gemini_code

        # Validate CLI binary availability
        if use_claude_code:
            import shutil
            claude_path = shutil.which("claude")
            if not claude_path:
                raise ConfigurationError(
                    "Claude Code CLI not found.\n\n"
                    "The --use-claude-code flag requires Claude Code CLI to be installed.\n\n"
                    "To install Claude Code CLI, see: https://docs.anthropic.com/en/docs/claude-code\n"
                    "Make sure 'claude' is available in your PATH."
                )
            if verbose:
                logger.debug(f"Claude Code CLI found: {claude_path}")
            logger.success("Claude Code CLI available")

        if use_gemini_code:
            import shutil
            gemini_path = shutil.which("gemini")
            if not gemini_path:
                raise ConfigurationError(
                    "Gemini CLI not found.\n\n"
                    "The --use-gemini-code flag requires Gemini CLI to be installed.\n\n"
                    "To install Gemini CLI: npm install -g @anthropic-ai/gemini-cli\n"
                    "Make sure 'gemini' is available in your PATH."
                )
            if verbose:
                logger.debug(f"Gemini CLI found: {gemini_path}")
            logger.success("Gemini CLI available")

        # Load configuration (only require full config for API mode)
        config_manager = ConfigManager()
        config_loaded = config_manager.load()

        if not using_cli_backend:
            if not config_loaded:
                raise ConfigurationError(
                    "Configuration not found or invalid.\n\n"
                    "Please run 'codewiki config set' to configure your LLM API credentials,\n"
                    "or use --use-claude-code or --use-gemini-code for CLI backends.\n\n"
                    "For more help: codewiki config --help"
                )

            if not config_manager.is_configured():
                raise ConfigurationError(
                    "Configuration is incomplete. Please run 'codewiki config validate'\n"
                    "or use --use-claude-code or --use-gemini-code for CLI backends."
                )

        config = config_manager.get_config()
        api_key = config_manager.get_api_key()

        # Create default configuration for CLI backend mode if no config exists
        if config is None and using_cli_backend:
            from codewiki.cli.models.config import Configuration
            config = Configuration(
                base_url="",
                main_model="",
                cluster_model="",
            )
            if verbose:
                logger.debug("Using default configuration for CLI backend mode")

        logger.success("Configuration valid")

        # Step 2: Validate input file
        logger.step("Validating input file...", 2, 4)

        input_path_obj = Path(input_path).expanduser().resolve()

        # Determine actual dependency graph file path
        if input_path_obj.is_dir():
            dependency_graph_path = input_path_obj / "dependency_graph.json"
        else:
            dependency_graph_path = input_path_obj

        if not dependency_graph_path.exists():
            raise FileSystemError(
                f"Dependency graph not found: {dependency_graph_path}\n\n"
                "Please run 'codewiki analyze' first to generate the dependency graph."
            )

        # Load and validate JSON
        try:
            with open(dependency_graph_path, 'r', encoding='utf-8') as f:
                input_data = json.load(f)
        except json.JSONDecodeError as e:
            raise FileSystemError(
                f"Invalid JSON in dependency graph file: {dependency_graph_path}\n\n"
                f"Error: {e}"
            )

        if not validate_dependency_graph_schema(input_data):
            raise FileSystemError(
                f"Invalid dependency graph schema: {dependency_graph_path}\n\n"
                "Expected schema with 'components' (object) and 'leaf_nodes' (array).\n"
                "Please run 'codewiki analyze' to generate a valid dependency graph."
            )

        logger.success(f"Input valid: {dependency_graph_path}")
        if verbose:
            logger.debug(f"Components: {len(input_data['components'])}")
            logger.debug(f"Leaf nodes: {len(input_data['leaf_nodes'])}")

        # Step 3: Validate output directory
        logger.step("Validating output directory...", 3, 4)

        if output:
            output_dir = Path(output).expanduser().resolve()
        else:
            # Default: same directory as input
            output_dir = dependency_graph_path.parent

        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise FileSystemError(
                    f"Cannot create output directory: {output_dir}\n\n"
                    "Permission denied. Check write permissions for the parent directory."
                )
        else:
            check_writable_output(output_dir)

        logger.success(f"Output directory: {output_dir}")

        # Step 4: Run clustering
        logger.step("Clustering modules...", 4, 4)

        # Convert input data components back to Node objects
        from codewiki.src.be.dependency_analyzer.models.core import Node

        components = {}
        for comp_id, comp_data in input_data["components"].items():
            components[comp_id] = Node(
                id=comp_id,
                name=comp_data.get("name", ""),
                component_type=comp_data.get("type", "unknown"),
                file_path=comp_data.get("file_path", ""),
                relative_path=comp_data.get("relative_path", ""),
                source_code=comp_data.get("source_code"),
                depends_on=set(comp_data.get("depends_on", [])),
                start_line=comp_data.get("start_line", 0),
                end_line=comp_data.get("end_line", 0),
            )

        leaf_nodes = input_data["leaf_nodes"]

        # Create backend config
        backend_config = Config(
            repo_path=input_data.get("metadata", {}).get("repo_path", str(output_dir)),
            output_dir=str(output_dir / "temp"),
            dependency_graph_dir=str(output_dir),
            docs_dir=str(output_dir),
            max_depth=max_depth if max_depth is not None else (config.max_depth if config else 2),
            llm_base_url=config.base_url if config else "",
            llm_api_key=api_key if api_key else "",
            main_model=config.main_model if config else "",
            cluster_model=config.cluster_model if config else "",
            max_token_per_module=max_token_per_module if max_token_per_module is not None else (config.max_token_per_module if config else 36369),
            use_claude_code=use_claude_code,
            use_gemini_code=use_gemini_code,
        )

        if verbose:
            if use_claude_code:
                logger.debug("Using Claude Code CLI for clustering")
            elif use_gemini_code:
                logger.debug("Using Gemini CLI for clustering")
            else:
                logger.debug(f"Using API model: {backend_config.cluster_model}")

        # Run clustering
        try:
            if use_claude_code:
                from codewiki.src.be.claude_code_adapter import claude_code_cluster
                module_tree = claude_code_cluster(leaf_nodes, components, backend_config)
            elif use_gemini_code:
                from codewiki.src.be.gemini_code_adapter import gemini_code_cluster
                module_tree = gemini_code_cluster(leaf_nodes, components, backend_config)
            else:
                from codewiki.src.be.cluster_modules import cluster_modules
                module_tree = cluster_modules(leaf_nodes, components, backend_config)

            if not module_tree:
                # If clustering returns empty, create a default single-module tree
                logger.warning("Clustering returned empty result - creating default module tree")
                module_tree = {
                    "root": {
                        "components": leaf_nodes,
                        "children": {},
                    }
                }

        except Exception as e:
            raise APIError(f"Module clustering failed: {e}")

        # Save output files
        first_module_tree_path = output_dir / FIRST_MODULE_TREE_FILENAME
        module_tree_path = output_dir / MODULE_TREE_FILENAME

        with open(first_module_tree_path, 'w', encoding='utf-8') as f:
            json.dump(module_tree, f, indent=2)

        with open(module_tree_path, 'w', encoding='utf-8') as f:
            json.dump(module_tree, f, indent=2)

        logger.success(f"Module tree saved: {first_module_tree_path}")

        # Summary
        click.echo()
        click.secho("Clustering Complete", fg="green", bold=True)
        click.echo(f"  Modules: {len(module_tree)}")
        click.echo(f"  Output: {first_module_tree_path}")
        click.echo(f"          {module_tree_path}")

        if verbose:
            click.echo("\n  Module structure:")
            for module_name, module_info in module_tree.items():
                comp_count = len(module_info.get("components", []))
                children_count = len(module_info.get("children", {}))
                click.echo(f"    {module_name}: {comp_count} components, {children_count} children")

        sys.exit(EXIT_SUCCESS)

    except ConfigurationError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except FileSystemError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except APIError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        sys.exit(handle_error(e, verbose=verbose))
