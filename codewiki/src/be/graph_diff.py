"""
Module for comparing dependency graphs and identifying affected components.

This module provides functionality to:
1. Load dependency graphs from JSON/GZIP files
2. Compare two graphs to identify added, removed, and modified components
3. Propagate changes through dependencies to find affected components
4. Map components to module paths

Implements IMP.3.2 story requirements.
"""

import gzip
import json
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, List, Dict, Any, Union


# Constants for validation
MIN_DEPTH = 1
MAX_DEPTH = 20


@dataclass
class DiffResult:
    """
    Result of comparing two dependency graphs.

    Attributes:
        added: Component IDs only in the new graph
        removed: Component IDs only in the old graph
        modified: Component IDs with source_code changes
    """
    added: Set[str] = field(default_factory=set)
    removed: Set[str] = field(default_factory=set)
    modified: Set[str] = field(default_factory=set)

    @property
    def changed_components(self) -> Set[str]:
        """Components that were added or modified (relevant for regeneration)."""
        return self.added | self.modified

    @property
    def all_changed(self) -> Set[str]:
        """All changed components (added, removed, and modified)."""
        return self.added | self.removed | self.modified

    @property
    def is_empty(self) -> bool:
        """True if no changes detected."""
        return not self.added and not self.removed and not self.modified


def _normalize_source(source: str) -> str:
    """
    Normalize source code for comparison.

    Handles:
    - CRLF -> LF conversion
    - CR -> LF conversion
    - Tab normalization to single space
    - Trailing whitespace removal per line
    - Multiple blank lines to single blank line
    - Leading/trailing whitespace from entire string

    Args:
        source: Raw source code string

    Returns:
        Normalized source code string
    """
    if not source:
        return ""

    # Normalize line endings: CRLF and CR to LF
    normalized = source.replace('\r\n', '\n').replace('\r', '\n')

    # Process line by line
    lines = normalized.split('\n')

    # Remove trailing whitespace from each line
    lines = [line.rstrip() for line in lines]

    # Replace tabs with single space
    lines = [line.replace('\t', ' ') for line in lines]

    # Join and collapse multiple blank lines
    result = '\n'.join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # Strip leading/trailing whitespace from entire string
    return result.strip()


def _is_modified(old_comp: Dict[str, Any], new_comp: Dict[str, Any]) -> bool:
    """
    Check if a component has been modified based on source_code.

    Args:
        old_comp: Component data from old graph
        new_comp: Component data from new graph

    Returns:
        True if the component's source_code differs after normalization
    """
    old_source = _normalize_source(old_comp.get('source_code', ''))
    new_source = _normalize_source(new_comp.get('source_code', ''))
    return old_source != new_source


def load_graph(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load a dependency graph from a JSON or gzipped JSON file.

    Supports:
    - .json files (plain JSON)
    - .json.gz files (gzipped JSON)

    Args:
        path: Path to the graph file

    Returns:
        Parsed dependency graph as a dictionary

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If the file is corrupt, invalid JSON, or not a dict
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Graph file not found: {path}")

    try:
        if path.suffix == '.gz' or path.name.endswith('.json.gz'):
            # Handle gzipped JSON
            try:
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
            except (gzip.BadGzipFile, EOFError, OSError, zlib.error) as e:
                raise ValueError(
                    f"Corrupt or invalid gzip file: {path}. "
                    f"The file may be truncated or not a valid gzip archive. "
                    f"Error: {type(e).__name__}: {e}"
                )
        else:
            # Handle plain JSON
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in file: {path}. "
            f"Parse error at line {e.lineno}, column {e.colno}: {e.msg}"
        )

    if not isinstance(data, dict):
        raise ValueError(
            f"Graph file must contain a JSON object (dict), "
            f"got {type(data).__name__}: {path}"
        )

    return data


def compare_dependency_graphs(
    old_graph: Dict[str, Any],
    new_graph: Dict[str, Any]
) -> DiffResult:
    """
    Compare two dependency graphs and identify changes.

    Detects:
    - Added components (only in new_graph)
    - Removed components (only in old_graph)
    - Modified components (source_code differs)

    Args:
        old_graph: Previous version of the dependency graph
        new_graph: Current version of the dependency graph

    Returns:
        DiffResult containing added, removed, and modified component sets
    """
    old_ids = set(old_graph.keys())
    new_ids = set(new_graph.keys())

    # Components only in new graph
    added = new_ids - old_ids

    # Components only in old graph
    removed = old_ids - new_ids

    # Components in both - check for modifications
    common_ids = old_ids & new_ids
    modified = {
        comp_id for comp_id in common_ids
        if _is_modified(old_graph[comp_id], new_graph[comp_id])
    }

    return DiffResult(added=added, removed=removed, modified=modified)


def _build_reverse_deps(graph: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    Build a reverse dependency map.

    For each component, finds all components that depend on it.

    Args:
        graph: Dependency graph

    Returns:
        Dict mapping component ID -> set of components that depend on it
    """
    reverse = defaultdict(set)

    for comp_id, comp_data in graph.items():
        if isinstance(comp_data, dict):
            depends_on = comp_data.get('depends_on', [])
            if isinstance(depends_on, list):
                for dep in depends_on:
                    if isinstance(dep, str):
                        reverse[dep].add(comp_id)

    return reverse


def get_affected_components(
    changed_components: Set[str],
    graph: Dict[str, Any],
    depth: int = 2
) -> Set[str]:
    """
    Get all components affected by changes, including transitive dependents.

    Starting from changed components, traverses the dependency graph to find
    all components that depend on them up to `depth` hops.

    Args:
        changed_components: Set of component IDs that changed
        graph: Current dependency graph (used for reverse lookup)
        depth: Maximum traversal depth (1-20, default: 2)

    Returns:
        Set of all affected component IDs (including original changed ones)

    Raises:
        ValueError: If depth is outside valid range (1-20)
    """
    # Validate depth parameter (TECH-003 mitigation)
    if depth < MIN_DEPTH:
        raise ValueError(
            f"Depth must be at least {MIN_DEPTH}, got {depth}. "
            f"Use depth={MIN_DEPTH} for direct dependents only."
        )
    if depth > MAX_DEPTH:
        raise ValueError(
            f"Depth must be at most {MAX_DEPTH}, got {depth}. "
            f"Excessive depth may cause performance issues."
        )

    # Build reverse dependency map
    reverse_deps = _build_reverse_deps(graph)

    # Start with changed components
    affected = set(changed_components)

    # Use visited set to prevent infinite loops (TECH-002 mitigation)
    visited = set()

    # BFS traversal up to depth hops
    current_level = set(changed_components)

    for _ in range(depth):
        next_level = set()

        for comp_id in current_level:
            if comp_id in visited:
                continue
            visited.add(comp_id)

            # Find components that depend on this one
            dependents = reverse_deps.get(comp_id, set())
            for dependent in dependents:
                if dependent not in affected:
                    affected.add(dependent)
                    next_level.add(dependent)

        if not next_level:
            break

        current_level = next_level

    return affected


def map_components_to_modules(
    components: Set[str],
    module_tree: Dict[str, Any]
) -> List[str]:
    """
    Map component IDs to their containing module paths.

    Uses the module_tree to find which module each component belongs to.
    Returns unique module paths, sorted alphabetically.

    Args:
        components: Set of component IDs to map
        module_tree: Module tree structure with component-to-module mappings

    Returns:
        Sorted list of unique module paths
    """
    affected_modules: Set[str] = set()

    # Build component-to-module lookup from module_tree
    component_to_module = _build_component_to_module_map(module_tree)

    for comp_id in components:
        module_path = component_to_module.get(comp_id)
        if module_path:
            affected_modules.add(module_path)
        else:
            # Try to extract module path from component ID
            # Common format: "module/path.Class.method" or "module.Class.method"
            inferred_module = _infer_module_from_component_id(comp_id)
            if inferred_module:
                affected_modules.add(inferred_module)

    return sorted(affected_modules)


def _build_component_to_module_map(
    module_tree: Dict[str, Any],
    current_path: str = ""
) -> Dict[str, str]:
    """
    Build a flat mapping of component ID to module path from module_tree.

    Handles various module_tree structures:
    - Flat: {"module/path": {"components": ["comp1", "comp2"]}}
    - Nested: {"module": {"submodule": {"components": [...]}}}
    - Components as keys: {"module/path": {"comp1": {...}, "comp2": {...}}}

    Args:
        module_tree: Module tree structure
        current_path: Current path in recursion

    Returns:
        Dict mapping component ID -> module path
    """
    component_map: Dict[str, str] = {}

    for key, value in module_tree.items():
        if not isinstance(value, dict):
            continue

        # Determine path for this node
        node_path = f"{current_path}/{key}" if current_path else key

        # Check for explicit components list
        if 'components' in value:
            components = value['components']
            if isinstance(components, list):
                for comp in components:
                    if isinstance(comp, str):
                        component_map[comp] = node_path
                    elif isinstance(comp, dict) and 'id' in comp:
                        component_map[comp['id']] = node_path

        # Check for component IDs as direct keys (common in dependency graphs)
        for sub_key, sub_value in value.items():
            if sub_key in ('components', 'metadata', 'children'):
                continue
            if isinstance(sub_value, dict) and 'id' in sub_value:
                component_map[sub_value['id']] = node_path

        # Recurse into nested modules
        nested_map = _build_component_to_module_map(value, node_path)
        component_map.update(nested_map)

    return component_map


def _infer_module_from_component_id(component_id: str) -> str:
    """
    Infer module path from a component ID when not found in module_tree.

    Handles common naming conventions:
    - "module/path/file.Class.method" -> "module/path/file"
    - "module.submodule.Class.method" -> "module/submodule"
    - "backend/auth/service.AuthService.login" -> "backend/auth/service"

    Args:
        component_id: Component identifier string

    Returns:
        Inferred module path or empty string if cannot be determined
    """
    if not component_id:
        return ""

    # Handle path-style component IDs (module/path/file.Class.method)
    if '/' in component_id:
        # Find the file part (before the class)
        parts = component_id.rsplit('/', 1)
        if len(parts) == 2:
            prefix, suffix = parts
            # Remove class.method from suffix
            file_part = suffix.split('.')[0] if '.' in suffix else suffix
            return f"{prefix}/{file_part}" if file_part else prefix
        return parts[0]

    # Handle dot-style component IDs (module.submodule.Class.method)
    parts = component_id.split('.')
    if len(parts) >= 2:
        # Assume last 1-2 parts are Class.method
        # Return everything before that as module path
        if len(parts) >= 3:
            # Could be module.submodule.Class.method or module.Class.method
            # Heuristic: if third-to-last starts with uppercase, it's a class
            if len(parts) >= 3 and parts[-2][0:1].isupper():
                return '/'.join(parts[:-2])
            elif len(parts) >= 2 and parts[-1][0:1].isupper():
                return '/'.join(parts[:-1])
        return '/'.join(parts[:-1])

    return component_id
