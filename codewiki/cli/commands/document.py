"""
Document command for documentation generation from module tree.
"""

import sys
import json
import logging
import os
import asyncio
from pathlib import Path
from typing import Optional, List
import click

from codewiki.cli.config_manager import ConfigManager
from codewiki.cli.utils.errors import (
    ConfigurationError,
    RepositoryError,
    FileSystemError,
    APIError,
    handle_error,
    EXIT_SUCCESS,
)
from codewiki.cli.utils.repo_validator import (
    validate_repository,
    check_writable_output,
)
from codewiki.cli.utils.logging import create_logger
from codewiki.src.config import (
    Config,
    FIRST_MODULE_TREE_FILENAME,
    MODULE_TREE_FILENAME,
    set_cli_context,
)


def parse_patterns(patterns_str: str) -> List[str]:
    """Parse comma-separated patterns into a list."""
    if not patterns_str:
        return []
    return [p.strip() for p in patterns_str.split(',') if p.strip()]


def validate_module_tree_schema(data: dict) -> bool:
    """
    Validate that the module tree JSON has the expected schema.

    Expected schema:
    {
        "module_name": {
            "components": [...],
            "children": {...}
        }
    }
    """
    if not isinstance(data, dict):
        return False
    # Check that at least one module exists with proper structure
    for module_name, module_info in data.items():
        if not isinstance(module_info, dict):
            return False
        if "components" not in module_info:
            return False
    return True


@click.command(name="document")
@click.option(
    "--input",
    "-i",
    "input_path",
    type=click.Path(exists=True),
    required=True,
    help="Path to directory containing first_module_tree.json and dependency_graph.json",
)
@click.option(
    "--repo",
    "-r",
    type=click.Path(exists=True),
    default=None,
    help="Path to source repository (default: current directory)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output directory for documentation (default: same as input)",
)
@click.option(
    "--modules",
    "-m",
    type=str,
    default=None,
    help="Comma-separated module paths to regenerate (e.g., 'backend/auth,utils')",
)
@click.option(
    "--force",
    "-F",
    is_flag=True,
    help="Force regeneration of specified modules, overwriting existing documentation",
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
    "--github-pages",
    is_flag=True,
    help="Generate index.html for GitHub Pages deployment",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress and debug information",
)
@click.pass_context
def document_command(
    ctx,
    input_path: str,
    repo: Optional[str],
    output: Optional[str],
    modules: Optional[str],
    force: bool,
    use_claude_code: bool,
    use_gemini_code: bool,
    github_pages: bool,
    verbose: bool,
):
    """
    Generate documentation from a module tree.

    This command reads a module tree JSON file (from 'codewiki cluster') and
    generates markdown documentation for each module using LLM-powered analysis.

    The output includes:
    - Markdown files for each module (*.md)
    - Repository overview (overview.md)
    - Generation metadata (metadata.json)
    - Optional HTML viewer (index.html with --github-pages)

    Requires access to the source repository for reading component code.

    Examples:

    \b
    # Basic documentation generation
    $ codewiki document --input ./docs

    \b
    # Specify source repository location
    $ codewiki document --input ./docs --repo /path/to/repo

    \b
    # Generate using Claude Code CLI (no API key required)
    $ codewiki document --input ./docs --use-claude-code

    \b
    # Regenerate specific modules only
    $ codewiki document --input ./docs --modules "backend/auth,utils"

    \b
    # Force regenerate specific modules
    $ codewiki document --input ./docs --modules "backend/auth" --force

    \b
    # Generate with GitHub Pages HTML viewer
    $ codewiki document --input ./docs --github-pages

    \b
    # Custom output directory
    $ codewiki document --input ./docs --output ./output

    \b
    # Verbose output for debugging
    $ codewiki document --input ./docs --verbose
    """
    logger = create_logger(verbose=verbose)

    # Suppress httpx INFO logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        # Step 1: Validate configuration
        logger.step("Validating configuration...", 1, 5)

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

        # Load configuration
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

        # Step 2: Validate input files
        logger.step("Validating input files...", 2, 5)

        input_path_obj = Path(input_path).expanduser().resolve()

        if not input_path_obj.is_dir():
            raise FileSystemError(
                f"Input path must be a directory: {input_path}\n\n"
                "The directory should contain first_module_tree.json and dependency_graph.json"
            )

        # Check for required files
        first_module_tree_path = input_path_obj / FIRST_MODULE_TREE_FILENAME
        module_tree_path = input_path_obj / MODULE_TREE_FILENAME
        dependency_graph_path = input_path_obj / "dependency_graph.json"

        if not first_module_tree_path.exists():
            raise FileSystemError(
                f"Module tree not found: {first_module_tree_path}\n\n"
                "Please run 'codewiki cluster' first to generate the module tree."
            )

        if not dependency_graph_path.exists():
            raise FileSystemError(
                f"Dependency graph not found: {dependency_graph_path}\n\n"
                "Please run 'codewiki analyze' first to generate the dependency graph."
            )

        # Load and validate module tree
        try:
            with open(first_module_tree_path, 'r', encoding='utf-8') as f:
                module_tree = json.load(f)
        except json.JSONDecodeError as e:
            raise FileSystemError(
                f"Invalid JSON in module tree file: {first_module_tree_path}\n\n"
                f"Error: {e}"
            )

        if not validate_module_tree_schema(module_tree):
            raise FileSystemError(
                f"Invalid module tree schema: {first_module_tree_path}\n\n"
                "Expected schema with module names containing 'components' arrays."
            )

        # Load dependency graph for components
        try:
            with open(dependency_graph_path, 'r', encoding='utf-8') as f:
                dependency_graph = json.load(f)
        except json.JSONDecodeError as e:
            raise FileSystemError(
                f"Invalid JSON in dependency graph file: {dependency_graph_path}\n\n"
                f"Error: {e}"
            )

        logger.success(f"Input valid: {input_path_obj}")
        if verbose:
            logger.debug(f"Modules: {len(module_tree)}")
            logger.debug(f"Components: {len(dependency_graph.get('components', {}))}")

        # Step 3: Validate repository
        logger.step("Validating repository...", 3, 5)

        if repo:
            repo_path = Path(repo).expanduser().resolve()
        else:
            repo_path = Path.cwd()

        repo_path, languages = validate_repository(repo_path)

        logger.success(f"Repository valid: {repo_path.name}")
        if verbose:
            logger.debug(f"Detected languages: {', '.join(f'{lang} ({count} files)' for lang, count in languages)}")

        # Step 4: Validate output directory
        logger.step("Validating output directory...", 4, 5)

        if output:
            output_dir = Path(output).expanduser().resolve()
        else:
            output_dir = input_path_obj

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

        # Step 5: Generate documentation
        logger.step("Generating documentation...", 5, 5)

        # Parse selective modules
        selective_modules = parse_patterns(modules) if modules else None
        force_regenerate = force

        # Validate --force usage
        if force_regenerate and not selective_modules:
            logger.warning(
                "--force flag has no effect without --modules. "
                "To regenerate all modules, remove existing documentation first."
            )
            force_regenerate = False

        if verbose and selective_modules:
            logger.debug(f"Selective modules: {selective_modules}")
            logger.debug(f"Force regenerate: {force_regenerate}")

        # Set CLI context
        set_cli_context(True)

        # Convert dependency graph components to Node objects
        from codewiki.src.be.dependency_analyzer.models.core import Node

        components = {}
        for comp_id, comp_data in dependency_graph.get("components", {}).items():
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

        leaf_nodes = dependency_graph.get("leaf_nodes", [])

        # Ensure module_tree.json exists (copy from first_module_tree if needed)
        if not module_tree_path.exists():
            with open(module_tree_path, 'w', encoding='utf-8') as f:
                json.dump(module_tree, f, indent=2)

        # Create backend config
        backend_config = Config(
            repo_path=str(repo_path),
            output_dir=str(output_dir / "temp"),
            dependency_graph_dir=str(input_path_obj),
            docs_dir=str(output_dir),
            max_depth=config.max_depth if config else 2,
            llm_base_url=config.base_url if config else "",
            llm_api_key=api_key if api_key else "",
            main_model=config.main_model if config else "",
            cluster_model=config.cluster_model if config else "",
            use_claude_code=use_claude_code,
            use_gemini_code=use_gemini_code,
            selective_modules=selective_modules,
            force_regenerate=force_regenerate,
        )

        # Run documentation generation
        from codewiki.src.be.documentation_generator import DocumentationGenerator

        doc_generator = DocumentationGenerator(backend_config)

        try:
            asyncio.run(doc_generator.generate_module_documentation(components, leaf_nodes))
            doc_generator.create_documentation_metadata(str(output_dir), components, len(leaf_nodes))
        except Exception as e:
            raise APIError(f"Documentation generation failed: {e}")

        # Count generated files
        md_files = list(output_dir.glob("*.md"))
        json_files = list(output_dir.glob("*.json"))

        logger.success(f"Documentation generated: {len(md_files)} markdown files")

        # Optional: Generate HTML
        if github_pages:
            from codewiki.cli.html_generator import HTMLGenerator

            html_generator = HTMLGenerator()
            repo_info = html_generator.detect_repository_info(repo_path)

            output_html = output_dir / "index.html"
            html_generator.generate(
                output_path=output_html,
                title=repo_info['name'],
                repository_url=repo_info['url'],
                github_pages_url=repo_info['github_pages_url'],
                docs_dir=output_dir
            )
            logger.success("HTML viewer generated: index.html")

        # Summary
        click.echo()
        click.secho("Documentation Complete", fg="green", bold=True)
        click.echo(f"  Markdown files: {len(md_files)}")
        click.echo(f"  Output: {output_dir}")

        if github_pages:
            click.echo(f"  HTML viewer: {output_dir / 'index.html'}")

        if verbose:
            click.echo("\n  Generated files:")
            for md_file in sorted(md_files)[:10]:
                click.echo(f"    {md_file.name}")
            if len(md_files) > 10:
                click.echo(f"    ... and {len(md_files) - 10} more")

        sys.exit(EXIT_SUCCESS)

    except ConfigurationError as e:
        logger.error(e.message)
        sys.exit(e.exit_code)
    except RepositoryError as e:
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
