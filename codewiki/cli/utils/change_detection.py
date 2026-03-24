"""
Change detection utilities for incremental documentation updates.

Provides functions to detect changed files via git diff and invalidate
affected module documentation for selective regeneration.

Extracted from generate.py to be shared between `generate` and `document` commands.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List

import git

logger = logging.getLogger(__name__)


def detect_changed_files(
    repo_path: Path,
    output_dir: Path,
    cli_logger=None,
    verbose: bool = False,
    base_commit: Optional[str] = None,
) -> Optional[List[str]]:
    """
    Detect files changed since the last documentation generation.

    When base_commit is provided, uses it directly as the diff base.
    Otherwise, reads the commit_id from metadata.json and compares with
    current HEAD using git diff.

    Args:
        repo_path: Path to the git repository.
        output_dir: Path to the documentation output directory (contains metadata.json).
        cli_logger: Optional CLI logger for user-facing messages.
        verbose: Whether to show detailed debug output.
        base_commit: Optional commit SHA to use as the diff base, overriding metadata.json.

    Returns:
        List of changed file paths, empty list if no changes, or None if unable
        to determine (e.g., no metadata and no base_commit, not a git repo).
    """
    log = cli_logger or logger

    # Resolve the base commit: explicit override or metadata.json
    prev_commit = base_commit

    if prev_commit is None:
        metadata_path = output_dir / "metadata.json"
        if not metadata_path.exists():
            if verbose:
                log.debug("No metadata.json found — cannot detect changes, running full generation.")
            return None

        try:
            metadata = json.loads(metadata_path.read_text())
            prev_commit = metadata.get("generation_info", {}).get("commit_id")
            if not prev_commit:
                if verbose:
                    log.debug("No commit_id in metadata — running full generation.")
                return None
        except (json.JSONDecodeError, OSError):
            return None

    # Get current HEAD commit
    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
        current_commit = repo.head.commit.hexsha
    except Exception:
        if verbose:
            log.debug("Cannot access git repo — running full generation.")
        return None

    if prev_commit == current_commit:
        if verbose:
            log.debug(f"HEAD is still at {current_commit[:8]} — no changes.")
        return []

    # Get changed files between previous and current commit
    try:
        diff_index = repo.commit(prev_commit).diff(current_commit)
        changed = []
        for diff in diff_index:
            if diff.a_path:
                changed.append(diff.a_path)
            if diff.b_path and diff.b_path != diff.a_path:
                changed.append(diff.b_path)

        if verbose:
            log.debug(f"Changes between {prev_commit[:8]} and {current_commit[:8]}:")
            for f in changed[:10]:
                log.debug(f"  {f}")
            if len(changed) > 10:
                log.debug(f"  ... and {len(changed) - 10} more")

        return changed
    except Exception as e:
        if verbose:
            log.debug(f"Git diff failed: {e} — running full generation.")
        return None


def invalidate_affected_modules(
    output_dir: Path,
    changed_files: List[str],
    cli_logger=None,
    verbose: bool = False,
) -> List[str]:
    """
    Remove cached module documentation for modules that contain changed files.

    Reads module_tree.json to find which modules contain changed files,
    then deletes their .md files so they get regenerated.

    Args:
        output_dir: Path to the documentation output directory.
        changed_files: List of changed file paths from git diff.
        cli_logger: Optional CLI logger for user-facing messages.
        verbose: Whether to show detailed debug output.

    Returns:
        List of invalidated module names.
    """
    log = cli_logger or logger

    module_tree_path = output_dir / "module_tree.json"
    if not module_tree_path.exists():
        return []

    try:
        module_tree = json.loads(module_tree_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    changed_index = _build_changed_files_index(set(changed_files))
    modules_to_invalidate = set()

    def _find_affected(tree, parent_names=None):
        if parent_names is None:
            parent_names = []
        for mod_name, mod_info in tree.items():
            components = mod_info.get("components", [])
            # Check if any component path overlaps with changed files
            # Use pre-computed index for O(1) lookups instead of O(n) iteration
            for comp in components:
                if _path_matches_changed_files(comp, changed_index):
                    modules_to_invalidate.add(mod_name)
                    # Also invalidate parent modules
                    for parent in parent_names:
                        modules_to_invalidate.add(parent)
                    break

            children = mod_info.get("children", {})
            if isinstance(children, dict) and children:
                _find_affected(children, parent_names + [mod_name])

    _find_affected(module_tree)

    # Also remove overview.md since it depends on child docs
    if modules_to_invalidate:
        modules_to_invalidate.add("overview")

    # Delete affected module docs
    for mod_name in modules_to_invalidate:
        doc_path = output_dir / f"{mod_name}.md"
        if doc_path.exists():
            doc_path.unlink()
            if verbose:
                log.debug(f"Invalidated: {doc_path.name}")

    if verbose:
        log.debug(f"Invalidated {len(modules_to_invalidate)} modules for regeneration.")

    return sorted(modules_to_invalidate)


def prune_removed_modules(
    output_dir: Path,
    repo_path: Path,
    invalidated_modules: List[str],
    cli_logger=None,
    verbose: bool = False,
) -> List[str]:
    """
    Remove modules from module_tree.json whose source components no longer
    exist in the repository.

    When source files are deleted, ``invalidate_affected_modules`` correctly
    detects them and removes the cached ``.md`` docs, but the module entry
    remains in ``module_tree.json``.  The generator then tries to regenerate
    documentation for code that no longer exists.

    This function checks each invalidated module's components against the
    filesystem and removes modules where **no** component source file can be
    found, preventing useless (or broken) regeneration attempts.

    Args:
        output_dir: Documentation output directory (contains module_tree.json).
        repo_path: Root of the source repository.
        invalidated_modules: Module names returned by ``invalidate_affected_modules``.
        cli_logger: Optional CLI logger.
        verbose: Show detailed output.

    Returns:
        List of module names that were pruned (removed from tree).
    """
    log = cli_logger or logger

    module_tree_path = output_dir / "module_tree.json"
    if not module_tree_path.exists():
        return []

    try:
        module_tree = json.loads(module_tree_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    pruned = []

    for mod_name in invalidated_modules:
        if mod_name == "overview":
            continue
        mod_info = module_tree.get(mod_name)
        if mod_info is None:
            continue

        components = mod_info.get("components", [])
        if not components:
            # Sub-doc children registered by _register_sub_docs have empty
            # components — they are cleaned up when their parent is pruned.
            continue

        # Check if at least one component's source file still exists
        has_live_source = False
        for comp in components:
            source_path = _resolve_component_path(comp, repo_path)
            if source_path and source_path.exists():
                has_live_source = True
                break

        if not has_live_source:
            # Remove module and its children docs from disk
            _remove_module_docs(mod_name, mod_info, output_dir, log, verbose)
            # Remove from tree
            del module_tree[mod_name]
            pruned.append(mod_name)
            if verbose:
                log.debug(f"Pruned removed module: {mod_name} (no source files found)")

    if pruned:
        module_tree_path.write_text(json.dumps(module_tree, indent=2))
        log.info(f"Pruned {len(pruned)} removed modules from module_tree.json")

    return pruned


def _remove_module_docs(
    mod_name: str,
    mod_info: dict,
    output_dir: Path,
    log,
    verbose: bool,
) -> None:
    """Delete .md files for a module and all its children recursively."""
    doc_path = output_dir / f"{mod_name}.md"
    if doc_path.exists():
        doc_path.unlink()
        if verbose:
            log.debug(f"Removed doc: {doc_path.name}")

    for child_name, child_info in mod_info.get("children", {}).items():
        _remove_module_docs(child_name, child_info, output_dir, log, verbose)


def _resolve_component_path(component: str, repo_path: Path) -> Optional[Path]:
    """
    Try to resolve a component ID to a file path on disk.

    Component IDs can be:
    - File paths: "app/Services/Auth/AuthService.php"
    - Dot-separated: "App.Services.Auth.AuthService.getUser"
    """
    # If it looks like a file path, try directly
    if "/" in component:
        candidate = repo_path / component
        if candidate.suffix:  # has file extension
            return candidate

    # Dot-separated class name → try converting to path
    if "." in component and "/" not in component:
        parts = component.split(".")
        # Strip trailing method name (camelCase)
        path_parts = []
        for part in parts:
            path_parts.append(part)
            if len(path_parts) > 1 and part[0:1].isupper():
                idx = parts.index(part) if parts.count(part) == 1 else -1
                if idx >= 0 and idx + 1 < len(parts) and parts[idx + 1][0:1].islower():
                    break

        # Try common extensions
        base = "/".join(path_parts)
        for ext in (".php", ".py", ".js", ".ts", ".java", ".cs"):
            candidate = repo_path / (base + ext)
            if candidate.exists():
                return candidate
            # Also try lowercase first segment (app/ instead of App/)
            alt_base = path_parts[0].lower() + "/" + "/".join(path_parts[1:])
            candidate = repo_path / (alt_base + ext)
            if candidate.exists():
                return candidate

    return None


def _build_changed_files_index(changed_files: set) -> dict:
    """
    Pre-compute lookup structures from changed files for O(1) path matching.

    Reduces matching complexity from O(components * changed_files) to
    O(components * path_depth + changed_files * path_depth), which is
    effectively O(n + m) since path_depth is bounded (~5-10).

    Returns a dict with:
        exact: set of original file paths (for exact match)
        normalized: set of lowercase paths without extensions
        basenames: set of lowercase basenames without extensions
        suffixes: set of all path suffixes (lowercase, no ext) for endswith matching
    """
    exact = changed_files
    normalized = set()
    basenames = set()
    suffixes = set()

    for f in changed_files:
        # Strip file extension for comparison
        basename_part = f.rsplit("/", 1)[-1]
        no_ext = f.rsplit(".", 1)[0] if "." in basename_part else f
        lower = no_ext.lower()
        normalized.add(lower)

        # Basename without extension, lowercase
        bn = no_ext.rsplit("/", 1)[-1].lower()
        basenames.add(bn)

        # All path suffixes for "file endswith component" matching
        parts = lower.split("/")
        for i in range(1, len(parts)):
            suffixes.add("/".join(parts[i:]))

    return {
        "exact": exact,
        "normalized": normalized,
        "basenames": basenames,
        "suffixes": suffixes,
    }


# Module-level constant — avoids re-creating per call
_FILE_EXTENSIONS = frozenset({
    '.php', '.py', '.js', '.ts', '.jsx', '.tsx', '.cs', '.java', '.kt',
    '.c', '.h', '.cpp', '.hpp', '.cc', '.cxx', '.rb', '.go', '.rs',
})


def _normalize_component(component: str) -> str:
    """
    Normalize a component ID to a path-like string for comparison.

    Converts dot-separated class names like "App.Services.Auth.AuthService.getUser"
    to path-like "App/Services/Auth/AuthService", stripping trailing method names.

    Naming-convention heuristic (PascalCase / camelCase):
      This logic assumes PascalCase segments are class or namespace names (kept as path
      segments) while a trailing camelCase segment (first char lowercase) is a method
      name and should be stripped.  This works for PHP (Laravel), Java, C#, and similar
      PascalCase-namespace languages.  It will NOT correctly distinguish namespace vs
      method for languages that use snake_case namespaces (Python, Ruby) or all-lowercase
      packages (Go, Java packages).  For those, the fallback to basename matching
      usually still produces a correct result.
    """
    has_file_ext = any(component.endswith(ext) for ext in _FILE_EXTENSIONS)

    if "." in component and "/" not in component and not has_file_ext:
        parts = component.split(".")
        path_parts = []
        for part in parts:
            path_parts.append(part)
            if len(path_parts) > 1 and part[0:1].isupper() and path_parts[-1] == part:
                idx = parts.index(part) if parts.count(part) == 1 else -1
                if idx >= 0 and idx + 1 < len(parts) and parts[idx + 1][0:1].islower():
                    break
        return "/".join(path_parts)

    return component


def _path_matches_changed_files(component: str, changed_files_index: dict) -> bool:
    """
    Check if a component ID matches any changed file using pre-computed index.

    Component IDs may be in different formats:
    - Dot-separated class names: "App.Services.Auth.AuthService" or
      "App.Services.Auth.AuthService.getUser"
    - File paths: "app/Services/Auth/AuthService.php"
    - Bare names: "AuthService"

    Changed files are always forward-slash paths like "app/Services/Auth/AuthService.php".

    Uses the pre-computed index from _build_changed_files_index() for O(1)
    set lookups instead of iterating over all changed files.

    Args:
        component: Component ID (may be a dot-separated class name or file path).
        changed_files_index: Pre-computed index dict from _build_changed_files_index().

    Returns:
        True if there is a match.
    """
    # Exact match — O(1)
    if component in changed_files_index["exact"]:
        return True

    comp_normalized = _normalize_component(component)
    comp_lower = comp_normalized.lower()

    # Full normalized match (case-insensitive, no extension) — O(1)
    if comp_lower in changed_files_index["normalized"]:
        return True

    # Component is a suffix of a changed file path — O(1)
    if comp_lower in changed_files_index["suffixes"]:
        return True

    # Changed file is a suffix of the component — O(path_depth)
    comp_parts = comp_lower.split("/")
    for i in range(1, len(comp_parts)):
        suffix = "/".join(comp_parts[i:])
        if suffix in changed_files_index["normalized"]:
            return True

    # Basename match for bare component names — O(1)
    if "/" not in comp_normalized:
        comp_stem = comp_normalized.rsplit(".", 1)[0].lower() if "." in comp_normalized else comp_lower
        if comp_lower in changed_files_index["basenames"] or comp_stem in changed_files_index["basenames"]:
            return True

    return False
