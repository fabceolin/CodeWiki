"""
Graph diff utility module for comparing dependency graphs and detecting affected modules.

This module provides functions to:
1. Compare two dependency graphs and detect added/removed/modified components
2. Build reverse dependency maps for efficient traversal
3. Get affected components including N-hop dependents
4. Map affected components to module paths
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any
import hashlib


@dataclass
class DiffResult:
    """Result of comparing two dependency graphs."""
    added: Set[str] = field(default_factory=set)
    removed: Set[str] = field(default_factory=set)
    modified: Set[str] = field(default_factory=set)

    @property
    def all_changed(self) -> Set[str]:
        """Return all changed component IDs."""
        return self.added | self.removed | self.modified

    @property
    def is_empty(self) -> bool:
        """Return True if no changes were detected."""
        return not self.added and not self.removed and not self.modified


def _compute_source_hash(source_code: str) -> str:
    """Compute hash of source code for comparison."""
    if source_code is None:
        return ""
    return hashlib.sha256(source_code.encode('utf-8')).hexdigest()


def compare_dependency_graphs(old_graph: Dict[str, Any], new_graph: Dict[str, Any]) -> DiffResult:
    """
    Compare two dependency graphs to detect changes.

    Detects:
    - Added components: IDs present in new graph but not in old
    - Removed components: IDs present in old graph but not in new
    - Modified components: IDs present in both but with different:
      - source_code (by hash comparison)
      - depends_on set
      - parameters
      - file_path (file relocation)

    Args:
        old_graph: The old dependency graph (component_id -> node dict)
        new_graph: The new dependency graph (component_id -> node dict)

    Returns:
        DiffResult with sets of added, removed, and modified component IDs
    """
    old_ids = set(old_graph.keys())
    new_ids = set(new_graph.keys())

    added = new_ids - old_ids
    removed = old_ids - new_ids

    modified = set()
    common_ids = old_ids & new_ids

    for cid in common_ids:
        old_node = old_graph[cid]
        new_node = new_graph[cid]

        # Compare source_code by hash
        old_hash = _compute_source_hash(old_node.get("source_code", ""))
        new_hash = _compute_source_hash(new_node.get("source_code", ""))

        if old_hash != new_hash:
            modified.add(cid)
            continue

        # Compare depends_on sets
        old_deps = set(old_node.get("depends_on", []))
        new_deps = set(new_node.get("depends_on", []))

        if old_deps != new_deps:
            modified.add(cid)
            continue

        # Compare parameters
        old_params = old_node.get("parameters")
        new_params = new_node.get("parameters")

        if old_params != new_params:
            modified.add(cid)
            continue

        # Compare file_path (relocation detection)
        old_path = old_node.get("file_path")
        new_path = new_node.get("file_path")

        if old_path != new_path:
            modified.add(cid)
            continue

    return DiffResult(added=added, removed=removed, modified=modified)


def build_reverse_dependency_map(graph: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    Build a reverse dependency map from the dependency graph.

    The reverse map answers: "What components depend on this component?"

    Args:
        graph: The dependency graph (component_id -> node dict)

    Returns:
        Dict mapping component_id -> set of component IDs that depend on it
    """
    reverse_deps: Dict[str, Set[str]] = defaultdict(set)

    for cid, node in graph.items():
        for dep in node.get("depends_on", []):
            reverse_deps[dep].add(cid)

    return dict(reverse_deps)


def get_affected_components(
    changed: Set[str],
    graph: Dict[str, Any],
    depth: int = 2
) -> Set[str]:
    """
    Get all affected components including N-hop dependents.

    Starting from the changed components, traverses the reverse dependency
    graph up to `depth` hops to find all components that may be affected.

    This handles circular dependencies by tracking visited components
    to prevent infinite loops.

    Args:
        changed: Set of directly changed component IDs
        graph: The dependency graph (used to build reverse deps)
        depth: Maximum number of hops to traverse (default: 2)

    Returns:
        Set of all affected component IDs (changed + dependents)
    """
    if depth < 0:
        depth = 0

    reverse_deps = build_reverse_dependency_map(graph)

    # Start with all changed components
    affected = set(changed)
    frontier = set(changed)

    for _ in range(depth):
        next_frontier = set()

        for cid in frontier:
            # Get components that depend on this one
            dependents = reverse_deps.get(cid, set())
            # Only add new dependents (handles circular deps)
            new_dependents = dependents - affected
            next_frontier.update(new_dependents)

        if not next_frontier:
            break

        affected.update(next_frontier)
        frontier = next_frontier

    return affected


def map_components_to_modules(
    components: Set[str],
    module_tree: Dict[str, Any]
) -> List[str]:
    """
    Map component IDs to module paths (slash-separated).

    Traverses the module tree to find which modules contain the affected
    components, returning a sorted list of module paths.

    Args:
        components: Set of affected component IDs
        module_tree: The module tree structure

    Returns:
        Sorted list of unique module paths (e.g., ["backend/auth", "utils"])
    """
    affected_modules: Set[str] = set()

    def traverse(tree: Dict[str, Any], path: List[str]) -> None:
        for module_name, module_info in tree.items():
            current_path = path + [module_name]
            module_components = set(module_info.get("components", []))

            # Check if any affected component is in this module
            if module_components & components:
                affected_modules.add("/".join(current_path))

            # Recurse into children
            children = module_info.get("children", {})
            if children:
                traverse(children, current_path)

    traverse(module_tree, [])
    return sorted(affected_modules)
