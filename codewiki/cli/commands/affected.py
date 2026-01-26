"""
CLI command for detecting affected modules between two dependency graph versions.

This command compares two dependency graphs and outputs:
- JSON array of affected module paths to stdout (for piping)
- Human-readable summary to stderr
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from codewiki.src.be.graph_diff import (
    compare_dependency_graphs,
    get_affected_components,
    map_components_to_modules,
    DiffResult,
)


def load_json_file(file_path: Path, description: str) -> dict:
    """
    Load and validate a JSON file.

    Args:
        file_path: Path to the JSON file
        description: Description for error messages

    Returns:
        Parsed JSON content as dict

    Raises:
        click.ClickException: If file cannot be loaded or parsed
    """
    if not file_path.exists():
        raise click.ClickException(f"{description} not found: {file_path}")

    if not file_path.is_file():
        raise click.ClickException(f"{description} is not a file: {file_path}")

    # Check file size for security (warn if > 100MB)
    file_size = file_path.stat().st_size
    if file_size > 100 * 1024 * 1024:  # 100MB
        click.echo(
            f"Warning: {description} is large ({file_size / 1024 / 1024:.1f}MB). "
            "This may use significant memory.",
            err=True
        )

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in {description}: {e}")
    except IOError as e:
        raise click.ClickException(f"Cannot read {description}: {e}")

    if not isinstance(data, dict):
        raise click.ClickException(
            f"{description} must be a JSON object, got {type(data).__name__}"
        )

    return data


def resolve_paths(
    old_graph: Optional[str],
    new_graph: Optional[str],
    module_tree: Optional[str],
    old_dir: Optional[str],
    new_dir: Optional[str],
) -> tuple[Path, Path, Path]:
    """
    Resolve file paths from CLI arguments.

    Supports two modes:
    1. Explicit paths: --old-graph, --new-graph, --module-tree
    2. Directory convention: --old-dir, --new-dir with standard file names

    Returns:
        Tuple of (old_graph_path, new_graph_path, module_tree_path)
    """
    # Check for mutually exclusive options
    has_explicit = old_graph or new_graph
    has_directory = old_dir or new_dir

    if has_explicit and has_directory:
        raise click.ClickException(
            "Cannot use both explicit paths (--old-graph, --new-graph) "
            "and directory mode (--old-dir, --new-dir)"
        )

    if has_explicit:
        if not old_graph:
            raise click.ClickException("--old-graph is required when using explicit paths")
        if not new_graph:
            raise click.ClickException("--new-graph is required when using explicit paths")
        if not module_tree:
            raise click.ClickException("--module-tree is required when using explicit paths")

        return (
            Path(old_graph).resolve(),
            Path(new_graph).resolve(),
            Path(module_tree).resolve(),
        )

    if has_directory:
        if not old_dir:
            raise click.ClickException("--old-dir is required when using directory mode")
        if not new_dir:
            raise click.ClickException("--new-dir is required when using directory mode")

        old_dir_path = Path(old_dir).resolve()
        new_dir_path = Path(new_dir).resolve()

        # Convention: dependency_graph.json in temp/dependency_graphs/
        old_graph_path = old_dir_path / "dependency_graph.json"
        new_graph_path = new_dir_path / "dependency_graph.json"

        # Module tree is in new directory
        module_tree_path = new_dir_path / "module_tree.json"

        # Override with explicit module-tree if provided
        if module_tree:
            module_tree_path = Path(module_tree).resolve()

        return old_graph_path, new_graph_path, module_tree_path

    # Default: use temp/dependency_graphs convention
    raise click.ClickException(
        "Please specify either:\n"
        "  --old-graph PATH --new-graph PATH --module-tree PATH\n"
        "or:\n"
        "  --old-dir PATH --new-dir PATH"
    )


def log_verbose_diff(diff: DiffResult, verbose: bool) -> None:
    """Log component-level changes in verbose mode."""
    if not verbose:
        return

    if diff.added:
        click.echo(f"\nAdded components ({len(diff.added)}):", err=True)
        for cid in sorted(diff.added)[:10]:
            click.echo(f"  + {cid}", err=True)
        if len(diff.added) > 10:
            click.echo(f"  ... and {len(diff.added) - 10} more", err=True)

    if diff.removed:
        click.echo(f"\nRemoved components ({len(diff.removed)}):", err=True)
        for cid in sorted(diff.removed)[:10]:
            click.echo(f"  - {cid}", err=True)
        if len(diff.removed) > 10:
            click.echo(f"  ... and {len(diff.removed) - 10} more", err=True)

    if diff.modified:
        click.echo(f"\nModified components ({len(diff.modified)}):", err=True)
        for cid in sorted(diff.modified)[:10]:
            click.echo(f"  ~ {cid}", err=True)
        if len(diff.modified) > 10:
            click.echo(f"  ... and {len(diff.modified) - 10} more", err=True)


def log_verbose_traversal(
    changed_count: int,
    affected_count: int,
    depth: int,
    verbose: bool
) -> None:
    """Log traversal information in verbose mode."""
    if not verbose:
        return

    dependents_count = affected_count - changed_count
    if dependents_count > 0:
        click.echo(
            f"\nTraversal ({depth}-hop): Found {dependents_count} dependent components",
            err=True
        )


@click.command("affected-modules")
@click.option(
    "--old-graph",
    type=click.Path(),
    help="Path to old dependency graph JSON"
)
@click.option(
    "--new-graph",
    type=click.Path(),
    help="Path to new dependency graph JSON"
)
@click.option(
    "--module-tree",
    type=click.Path(),
    help="Path to module_tree.json"
)
@click.option(
    "--old-dir",
    type=click.Path(),
    help="Directory containing old dependency graph"
)
@click.option(
    "--new-dir",
    type=click.Path(),
    help="Directory containing new dependency graph and module tree"
)
@click.option(
    "--depth",
    default=2,
    type=int,
    help="Dependency traversal depth (default: 2)"
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Show detailed change information"
)
def affected_modules(
    old_graph: Optional[str],
    new_graph: Optional[str],
    module_tree: Optional[str],
    old_dir: Optional[str],
    new_dir: Optional[str],
    depth: int,
    verbose: bool,
) -> None:
    """
    Detect modules affected by changes between two dependency graphs.

    Compares two dependency graph versions and identifies which modules
    need their documentation regenerated. Outputs a JSON array of module
    paths to stdout, suitable for piping to other commands.

    Examples:

    \b
    # Using explicit file paths
    $ codewiki affected-modules \\
        --old-graph ./v1/dependency_graph.json \\
        --new-graph ./v2/dependency_graph.json \\
        --module-tree ./v2/module_tree.json

    \b
    # Using directory convention
    $ codewiki affected-modules \\
        --old-dir ./temp/v1 \\
        --new-dir ./temp/v2

    \b
    # With custom depth and verbose output
    $ codewiki affected-modules \\
        --old-dir ./old --new-dir ./new \\
        --depth 3 -v

    \b
    # Pipe output to jq for formatting
    $ codewiki affected-modules --old-dir ./v1 --new-dir ./v2 | jq .
    """
    import time
    start_time = time.time()

    try:
        # Resolve file paths
        old_graph_path, new_graph_path, module_tree_path = resolve_paths(
            old_graph, new_graph, module_tree, old_dir, new_dir
        )

        if verbose:
            click.echo(f"Loading old graph: {old_graph_path}", err=True)
            click.echo(f"Loading new graph: {new_graph_path}", err=True)
            click.echo(f"Loading module tree: {module_tree_path}", err=True)

        # Load files
        load_start = time.time()
        old_graph_data = load_json_file(old_graph_path, "Old dependency graph")
        new_graph_data = load_json_file(new_graph_path, "New dependency graph")
        module_tree_data = load_json_file(module_tree_path, "Module tree")
        load_time = time.time() - load_start

        if verbose:
            click.echo(f"\nLoad time: {load_time:.2f}s", err=True)
            click.echo(f"Old graph: {len(old_graph_data)} components", err=True)
            click.echo(f"New graph: {len(new_graph_data)} components", err=True)

        # Compare graphs
        compare_start = time.time()
        diff = compare_dependency_graphs(old_graph_data, new_graph_data)
        compare_time = time.time() - compare_start

        if verbose:
            click.echo(f"Compare time: {compare_time:.2f}s", err=True)

        log_verbose_diff(diff, verbose)

        # Handle identical graphs
        if diff.is_empty:
            click.echo(json.dumps([]))
            click.echo("Changes detected: 0 added, 0 modified, 0 removed", err=True)
            click.echo("Affected components: 0", err=True)
            click.echo("Affected modules: 0", err=True)
            return

        # Get affected components (including N-hop dependents)
        traverse_start = time.time()
        # Use new_graph for traversal (current state of dependencies)
        affected_components = get_affected_components(
            diff.all_changed,
            new_graph_data,
            depth=depth
        )
        traverse_time = time.time() - traverse_start

        if verbose:
            click.echo(f"Traverse time: {traverse_time:.2f}s", err=True)

        log_verbose_traversal(
            len(diff.all_changed),
            len(affected_components),
            depth,
            verbose
        )

        # Map to modules
        map_start = time.time()
        affected_module_paths = map_components_to_modules(
            affected_components,
            module_tree_data
        )
        map_time = time.time() - map_start

        if verbose:
            click.echo(f"Map time: {map_time:.2f}s", err=True)

        # Check for unmapped components
        if verbose:
            # Count how many affected components mapped to modules
            mapped_count = 0
            for module_path in affected_module_paths:
                # This is a simplification - actual counting would need module tree traversal
                mapped_count += 1

            unmapped_estimate = len(affected_components) - mapped_count
            if unmapped_estimate > len(affected_components) * 0.1:
                click.echo(
                    f"\nWarning: Some affected components may not be mapped to modules",
                    err=True
                )

        # Output JSON to stdout
        click.echo(json.dumps(affected_module_paths))

        # Output summary to stderr
        total_time = time.time() - start_time
        click.echo(
            f"Changes detected: {len(diff.added)} added, "
            f"{len(diff.modified)} modified, {len(diff.removed)} removed",
            err=True
        )
        click.echo(
            f"Affected components: {len(affected_components)} "
            f"(including {depth}-hop dependents)",
            err=True
        )
        click.echo(f"Affected modules: {len(affected_module_paths)}", err=True)

        if verbose:
            click.echo(f"\nTotal time: {total_time:.2f}s", err=True)

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")
