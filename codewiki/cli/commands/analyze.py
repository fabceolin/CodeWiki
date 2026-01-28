"""
Analyze command for dependency graph generation.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import click

from codewiki.cli.utils.errors import (
    RepositoryError,
    FileSystemError,
    handle_error,
    EXIT_SUCCESS,
)
from codewiki.cli.utils.repo_validator import (
    validate_repository,
    check_writable_output,
)
from codewiki.cli.utils.logging import create_logger
from codewiki.src.config import Config


def parse_patterns(patterns_str: str) -> List[str]:
    """Parse comma-separated patterns into a list."""
    if not patterns_str:
        return []
    return [p.strip() for p in patterns_str.split(',') if p.strip()]


@click.command(name="analyze")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="docs",
    help="Output directory for dependency_graph.json (default: ./docs)",
)
@click.option(
    "--include",
    "-i",
    type=str,
    default=None,
    help="Comma-separated file patterns to include (e.g., '*.cs,*.py'). Overrides defaults.",
)
@click.option(
    "--exclude",
    "-e",
    type=str,
    default=None,
    help="Comma-separated patterns to exclude (e.g., '*Tests*,*Specs*,test_*')",
)
@click.option(
    "--focus",
    type=str,
    default=None,
    help="Comma-separated modules/paths to focus on during analysis (e.g., 'src/core,src/api')",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress and debug information",
)
@click.pass_context
def analyze_command(
    ctx,
    output: str,
    include: Optional[str],
    exclude: Optional[str],
    focus: Optional[str],
    verbose: bool,
):
    """
    Analyze a code repository and generate a dependency graph.

    This command parses source files in the current repository and builds a
    dependency graph showing relationships between code components (classes,
    functions, interfaces, etc.).

    The output is a JSON file that can be used for:
    - Inspecting the dependency graph before clustering
    - Debugging analysis issues
    - Integration with custom tooling
    - Input to the 'codewiki cluster' command

    No API key or LLM configuration is required for this command.

    Examples:

    \b
    # Basic analysis
    $ codewiki analyze

    \b
    # Analyze and output to custom directory
    $ codewiki analyze --output ./analysis

    \b
    # Analyze only Python files
    $ codewiki analyze --include "*.py"

    \b
    # Exclude test files
    $ codewiki analyze --exclude "*test*,*spec*"

    \b
    # Focus on specific modules
    $ codewiki analyze --focus "src/core,src/api"

    \b
    # Verbose output for debugging
    $ codewiki analyze --verbose
    """
    logger = create_logger(verbose=verbose)

    # Suppress httpx INFO logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        # Step 1: Validate repository
        logger.step("Validating repository...", 1, 3)

        repo_path = Path.cwd()
        repo_path, languages = validate_repository(repo_path)

        logger.success(f"Repository valid: {repo_path.name}")
        if verbose:
            logger.debug(f"Detected languages: {', '.join(f'{lang} ({count} files)' for lang, count in languages)}")

        # Step 2: Validate output directory
        logger.step("Validating output directory...", 2, 3)

        output_dir = Path(output).expanduser().resolve()

        # Create output directory if it doesn't exist
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise FileSystemError(
                    f"Cannot create output directory: {output_dir}\n\n"
                    f"Permission denied. Check write permissions for the parent directory."
                )
        else:
            check_writable_output(output_dir)

        logger.success(f"Output directory: {output_dir}")

        # Step 3: Build dependency graph
        logger.step("Building dependency graph...", 3, 3)

        # Build agent instructions dict from CLI options
        agent_instructions = None
        if any([include, exclude, focus]):
            agent_instructions = {}
            if include:
                agent_instructions['include_patterns'] = parse_patterns(include)
            if exclude:
                agent_instructions['exclude_patterns'] = parse_patterns(exclude)
            if focus:
                agent_instructions['focus_modules'] = parse_patterns(focus)

            if verbose:
                if include:
                    logger.debug(f"Include patterns: {parse_patterns(include)}")
                if exclude:
                    logger.debug(f"Exclude patterns: {parse_patterns(exclude)}")
                if focus:
                    logger.debug(f"Focus modules: {parse_patterns(focus)}")

        # Create minimal config for dependency analysis
        # No API key or LLM config needed for analysis
        config = Config(
            repo_path=str(repo_path),
            output_dir=str(output_dir / "temp"),
            dependency_graph_dir=str(output_dir),
            docs_dir=str(output_dir),
            max_depth=2,
            llm_base_url="",  # Not used for analysis
            llm_api_key="",   # Not used for analysis
            main_model="",    # Not used for analysis
            cluster_model="", # Not used for analysis
            agent_instructions=agent_instructions,
        )

        # Import and run dependency analysis
        from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder

        builder = DependencyGraphBuilder(config)
        components, leaf_nodes = builder.build_dependency_graph()

        # Build output JSON with metadata
        output_data = {
            "metadata": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "repo_path": str(repo_path),
                "total_components": len(components),
                "total_leaf_nodes": len(leaf_nodes),
            },
            "components": {
                comp_id: {
                    "name": comp.name,
                    "type": comp.component_type,
                    "file_path": comp.file_path,
                    "relative_path": comp.relative_path,
                    "source_code": comp.source_code,
                    "depends_on": list(comp.depends_on),
                    "start_line": comp.start_line,
                    "end_line": comp.end_line,
                }
                for comp_id, comp in components.items()
            },
            "leaf_nodes": leaf_nodes,
        }

        # Save to dependency_graph.json
        output_file = output_dir / "dependency_graph.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)

        logger.success(f"Dependency graph saved: {output_file}")

        # Summary
        click.echo()
        click.secho("Analysis Complete", fg="green", bold=True)
        click.echo(f"  Components: {len(components)}")
        click.echo(f"  Leaf nodes: {len(leaf_nodes)}")
        click.echo(f"  Output: {output_file}")

        if verbose:
            # Show component type breakdown
            type_counts = {}
            for comp in components.values():
                type_counts[comp.component_type] = type_counts.get(comp.component_type, 0) + 1
            click.echo("\n  Component types:")
            for comp_type, count in sorted(type_counts.items()):
                click.echo(f"    {comp_type}: {count}")

        sys.exit(EXIT_SUCCESS)

    except RepositoryError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except FileSystemError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        sys.exit(handle_error(e, verbose=verbose))
