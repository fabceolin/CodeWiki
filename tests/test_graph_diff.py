"""
Unit tests for the graph_diff module.

Tests cover all acceptance criteria from IMP.3.2:
- AC1: compare_dependency_graphs() returns structured diff
- AC2: Diff includes added, removed, modified components
- AC3: get_affected_components() propagation
- AC4: map_components_to_modules() mapping
- AC5: .json.gz compressed input support

Risk mitigations tested:
- TECH-001: Whitespace normalization
- TECH-002: Circular dependency protection
- TECH-003: Depth parameter validation
- DATA-001: Corrupt input handling
"""

import gzip
import json
import pytest
from pathlib import Path
import sys

# Insert the codewiki package path for import
CODEWIKI_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CODEWIKI_ROOT))

# Direct import from the module file to avoid triggering __init__.py issues
# This is necessary because the main codewiki __init__.py has broken imports
import importlib.util
spec = importlib.util.spec_from_file_location(
    "graph_diff",
    CODEWIKI_ROOT / "codewiki" / "src" / "be" / "graph_diff.py"
)
graph_diff_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph_diff_module)

# Import all needed symbols from the loaded module
DiffResult = graph_diff_module.DiffResult
compare_dependency_graphs = graph_diff_module.compare_dependency_graphs
get_affected_components = graph_diff_module.get_affected_components
map_components_to_modules = graph_diff_module.map_components_to_modules
load_graph = graph_diff_module.load_graph
_normalize_source = graph_diff_module._normalize_source
_is_modified = graph_diff_module._is_modified
_build_reverse_deps = graph_diff_module._build_reverse_deps
MIN_DEPTH = graph_diff_module.MIN_DEPTH
MAX_DEPTH = graph_diff_module.MAX_DEPTH


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDiffResult:
    """Tests for the DiffResult dataclass."""

    def test_empty_diff_result(self):
        """3.2-UNIT-001: Empty graphs produce empty DiffResult."""
        result = DiffResult()
        assert result.added == set()
        assert result.removed == set()
        assert result.modified == set()
        assert result.is_empty
        assert result.changed_components == set()
        assert result.all_changed == set()

    def test_diff_result_with_added(self):
        """3.2-UNIT-002: New components in new graph."""
        result = DiffResult(added={"comp1", "comp2"})
        assert result.added == {"comp1", "comp2"}
        assert not result.is_empty
        assert result.changed_components == {"comp1", "comp2"}
        assert result.all_changed == {"comp1", "comp2"}

    def test_diff_result_with_removed(self):
        """3.2-UNIT-003: Components only in old graph."""
        result = DiffResult(removed={"old_comp"})
        assert result.removed == {"old_comp"}
        assert not result.is_empty
        # changed_components doesn't include removed (they're not in new graph)
        assert result.changed_components == set()
        assert result.all_changed == {"old_comp"}

    def test_diff_result_with_modified(self):
        """3.2-UNIT-005: Components with source_code changes."""
        result = DiffResult(modified={"changed"})
        assert result.modified == {"changed"}
        assert not result.is_empty
        assert result.changed_components == {"changed"}

    def test_diff_result_combined(self):
        """DiffResult with all change types."""
        result = DiffResult(
            added={"new1", "new2"},
            removed={"old1"},
            modified={"mod1", "mod2", "mod3"}
        )
        assert result.changed_components == {"new1", "new2", "mod1", "mod2", "mod3"}
        assert result.all_changed == {"new1", "new2", "old1", "mod1", "mod2", "mod3"}


class TestNormalizeSource:
    """Tests for whitespace normalization (TECH-001 mitigation)."""

    def test_empty_string(self):
        """Empty string returns empty."""
        assert _normalize_source("") == ""

    def test_no_changes_needed(self):
        """Clean source remains unchanged."""
        assert _normalize_source("def foo(): pass") == "def foo(): pass"

    def test_crlf_to_lf(self):
        """CRLF line endings convert to LF."""
        assert _normalize_source("line1\r\nline2") == "line1\nline2"

    def test_cr_to_lf(self):
        """CR line endings convert to LF."""
        assert _normalize_source("line1\rline2") == "line1\nline2"

    def test_trailing_whitespace(self):
        """Trailing whitespace is removed per line."""
        assert _normalize_source("line1   \nline2\t") == "line1\nline2"

    def test_tabs_to_spaces(self):
        """Tabs are converted to single space."""
        assert _normalize_source("hello\tworld") == "hello world"

    def test_multiple_blank_lines(self):
        """Multiple blank lines collapse to one."""
        assert _normalize_source("a\n\n\n\nb") == "a\n\nb"

    def test_leading_trailing_strip(self):
        """Leading and trailing whitespace stripped from whole string."""
        assert _normalize_source("  \n  code  \n  ") == "code"

    def test_complex_normalization(self):
        """Complex case with multiple normalizations."""
        source = "def foo():  \r\n\treturn 42\r\n\r\n\r\n"
        expected = "def foo():\n return 42"
        assert _normalize_source(source) == expected


class TestIsModified:
    """Tests for modification detection."""

    def test_identical_components(self):
        """Identical source_code is not modified."""
        old = {"source_code": "def foo(): pass"}
        new = {"source_code": "def foo(): pass"}
        assert not _is_modified(old, new)

    def test_different_source(self):
        """Different source_code is modified."""
        old = {"source_code": "def foo(): pass"}
        new = {"source_code": "def foo(): return 42"}
        assert _is_modified(old, new)

    def test_whitespace_only_difference(self):
        """Whitespace-only difference is not modified after normalization."""
        old = {"source_code": "def foo():\r\n    pass"}
        new = {"source_code": "def foo():\n    pass"}
        assert not _is_modified(old, new)

    def test_missing_source_code(self):
        """Missing source_code treated as empty."""
        old = {"id": "comp1"}
        new = {"id": "comp1", "source_code": ""}
        assert not _is_modified(old, new)

    def test_one_side_missing(self):
        """One side with source, other without."""
        old = {"source_code": "code"}
        new = {}
        assert _is_modified(old, new)


class TestCompareDependencyGraphs:
    """Tests for AC1 and AC2: Graph comparison."""

    def test_empty_graphs(self):
        """3.2-UNIT-001: Empty graphs produce empty diff."""
        result = compare_dependency_graphs({}, {})
        assert result.is_empty

    def test_added_component(self):
        """3.2-UNIT-002: New component only in new graph."""
        old = {}
        new = {"comp1": {"source_code": "pass"}}
        result = compare_dependency_graphs(old, new)
        assert result.added == {"comp1"}
        assert result.removed == set()
        assert result.modified == set()

    def test_removed_component(self):
        """3.2-UNIT-003: Component only in old graph."""
        old = {"comp1": {"source_code": "pass"}}
        new = {}
        result = compare_dependency_graphs(old, new)
        assert result.added == set()
        assert result.removed == {"comp1"}
        assert result.modified == set()

    def test_unchanged_component(self):
        """3.2-UNIT-004: Unchanged component not in any diff set."""
        old = {"comp1": {"source_code": "pass"}}
        new = {"comp1": {"source_code": "pass"}}
        result = compare_dependency_graphs(old, new)
        assert result.is_empty

    def test_modified_component(self):
        """3.2-UNIT-005: Component with changed source_code."""
        old = {"comp1": {"source_code": "pass"}}
        new = {"comp1": {"source_code": "return 42"}}
        result = compare_dependency_graphs(old, new)
        assert result.modified == {"comp1"}
        assert result.added == set()
        assert result.removed == set()

    def test_combined_changes(self):
        """Multiple change types in one diff."""
        old = {
            "unchanged": {"source_code": "a"},
            "modified": {"source_code": "b"},
            "removed": {"source_code": "c"},
        }
        new = {
            "unchanged": {"source_code": "a"},
            "modified": {"source_code": "B"},
            "added": {"source_code": "d"},
        }
        result = compare_dependency_graphs(old, new)
        assert result.added == {"added"}
        assert result.removed == {"removed"}
        assert result.modified == {"modified"}

    def test_fixture_old_vs_new(self):
        """3.2-UNIT-005: Test with story fixtures."""
        old = load_graph(FIXTURES_DIR / "graph_old.json")
        new = load_graph(FIXTURES_DIR / "graph_new.json")
        result = compare_dependency_graphs(old, new)

        # method1 was modified (pass -> return 42)
        assert result.modified == {"module.ClassA.method1"}
        assert result.added == set()
        assert result.removed == set()


class TestBuildReverseDeps:
    """Tests for reverse dependency mapping."""

    def test_empty_graph(self):
        """Empty graph has no reverse deps."""
        assert _build_reverse_deps({}) == {}

    def test_simple_dependency(self):
        """A depends on B -> B has A as reverse dep."""
        graph = {
            "A": {"depends_on": ["B"]},
            "B": {"depends_on": []},
        }
        reverse = _build_reverse_deps(graph)
        assert "A" in reverse["B"]
        assert "A" not in reverse.get("A", set())

    def test_multiple_dependents(self):
        """Multiple components depend on one."""
        graph = {
            "A": {"depends_on": ["C"]},
            "B": {"depends_on": ["C"]},
            "C": {"depends_on": []},
        }
        reverse = _build_reverse_deps(graph)
        assert reverse["C"] == {"A", "B"}


class TestGetAffectedComponents:
    """Tests for AC3: Propagation of changes."""

    def test_no_dependents(self):
        """3.2-UNIT-008: Changed component with no dependents."""
        graph = {"A": {"depends_on": []}}
        affected = get_affected_components({"A"}, graph, depth=2)
        assert affected == {"A"}

    def test_one_dependent(self):
        """3.2-UNIT-009: Changed component with one dependent."""
        graph = {
            "A": {"depends_on": []},
            "B": {"depends_on": ["A"]},
        }
        affected = get_affected_components({"A"}, graph, depth=1)
        assert affected == {"A", "B"}

    def test_chain_depth_2(self):
        """3.2-UNIT-010: Chain A->B->C with depth=2."""
        graph = {
            "A": {"depends_on": []},
            "B": {"depends_on": ["A"]},
            "C": {"depends_on": ["B"]},
        }
        affected = get_affected_components({"A"}, graph, depth=2)
        assert affected == {"A", "B", "C"}

    def test_chain_depth_1(self):
        """3.2-UNIT-011: Chain A->B->C with depth=1."""
        graph = {
            "A": {"depends_on": []},
            "B": {"depends_on": ["A"]},
            "C": {"depends_on": ["B"]},
        }
        affected = get_affected_components({"A"}, graph, depth=1)
        assert affected == {"A", "B"}
        assert "C" not in affected

    def test_depth_validation_zero(self):
        """3.2-UNIT-012: depth=0 raises ValueError."""
        graph = {"A": {"depends_on": []}}
        with pytest.raises(ValueError) as exc_info:
            get_affected_components({"A"}, graph, depth=0)
        assert "at least 1" in str(exc_info.value).lower()

    def test_depth_validation_excessive(self):
        """3.2-UNIT-013: depth=100 raises ValueError."""
        graph = {"A": {"depends_on": []}}
        with pytest.raises(ValueError) as exc_info:
            get_affected_components({"A"}, graph, depth=100)
        assert "at most 20" in str(exc_info.value).lower()

    def test_depth_boundary_min(self):
        """Depth=1 (minimum) works."""
        graph = {"A": {"depends_on": []}, "B": {"depends_on": ["A"]}}
        affected = get_affected_components({"A"}, graph, depth=MIN_DEPTH)
        assert "A" in affected
        assert "B" in affected

    def test_depth_boundary_max(self):
        """Depth=20 (maximum) works."""
        graph = {"A": {"depends_on": []}}
        affected = get_affected_components({"A"}, graph, depth=MAX_DEPTH)
        assert "A" in affected

    def test_circular_deps(self):
        """3.2-UNIT-015: Circular dependencies terminate without loop."""
        graph = load_graph(FIXTURES_DIR / "graph_circular.json")
        # A -> C -> B -> A (circular)
        # This should NOT hang
        affected = get_affected_components({"component.A"}, graph, depth=10)

        # All components should be affected due to circular deps
        assert "component.A" in affected
        assert "component.B" in affected
        assert "component.C" in affected

    def test_deep_chain_fixture(self):
        """Test with deep chain fixture."""
        graph = load_graph(FIXTURES_DIR / "graph_deep_chain.json")

        # Change Root, should affect up to depth levels
        affected = get_affected_components({"level0.Root"}, graph, depth=3)

        assert "level0.Root" in affected
        assert "level1.Child1" in affected
        assert "level2.Child2" in affected
        assert "level3.Child3" in affected
        # depth=3 should stop at level3
        assert "level4.Child4" not in affected

    def test_empty_changed_set(self):
        """Empty changed set returns empty affected set."""
        graph = {"A": {"depends_on": []}}
        affected = get_affected_components(set(), graph, depth=2)
        assert affected == set()


class TestMapComponentsToModules:
    """Tests for AC4: Module mapping."""

    def test_empty_components(self):
        """No components returns empty list."""
        result = map_components_to_modules(set(), {})
        assert result == []

    def test_direct_mapping(self):
        """Components with direct module_tree mapping."""
        module_tree = {
            "backend": {
                "components": ["comp1", "comp2"]
            }
        }
        result = map_components_to_modules({"comp1"}, module_tree)
        assert "backend" in result

    def test_nested_module_tree(self):
        """Nested module tree structure."""
        module_tree = {
            "backend": {
                "auth": {
                    "components": ["backend.auth.login"]
                }
            }
        }
        result = map_components_to_modules({"backend.auth.login"}, module_tree)
        assert "backend/auth" in result

    def test_fixture_module_tree(self):
        """Test with module_tree fixture."""
        module_tree = load_graph(FIXTURES_DIR / "module_tree.json")

        result = map_components_to_modules(
            {"module.ClassA.method1", "module.ClassB.method2"},
            module_tree
        )
        assert "module" in result

    def test_inferred_module_path(self):
        """Module path inferred from component ID when not in tree."""
        # Component not in module_tree
        result = map_components_to_modules(
            {"some/path/file.Class.method"},
            {}
        )
        # Should infer module path from component ID
        assert len(result) >= 1

    def test_sorted_output(self):
        """Output is sorted alphabetically."""
        module_tree = {
            "zebra": {"components": ["z"]},
            "alpha": {"components": ["a"]},
            "beta": {"components": ["b"]},
        }
        result = map_components_to_modules({"z", "a", "b"}, module_tree)
        assert result == sorted(result)

    def test_unique_modules(self):
        """Multiple components in same module produce one entry."""
        module_tree = {
            "module": {"components": ["comp1", "comp2", "comp3"]}
        }
        result = map_components_to_modules({"comp1", "comp2", "comp3"}, module_tree)
        assert result == ["module"]


class TestLoadGraph:
    """Tests for AC5: File loading including .json.gz."""

    def test_load_plain_json(self):
        """Load plain JSON file."""
        graph = load_graph(FIXTURES_DIR / "graph_old.json")
        assert "module.ClassA.method1" in graph
        assert "module.ClassB.method2" in graph

    def test_load_empty_json(self):
        """Load empty JSON file."""
        graph = load_graph(FIXTURES_DIR / "graph_empty.json")
        assert graph == {}

    def test_load_compressed_json(self):
        """3.2-INT-005: Load gzipped JSON file."""
        graph = load_graph(FIXTURES_DIR / "graph_compressed.json.gz")
        assert "compressed.Component" in graph

    def test_file_not_found(self):
        """FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_graph(FIXTURES_DIR / "nonexistent.json")

    def test_corrupt_gzip(self):
        """3.2-INT-007: Corrupt gzip produces clear error message."""
        with pytest.raises(ValueError) as exc_info:
            load_graph(FIXTURES_DIR / "graph_corrupt.json.gz")

        error_msg = str(exc_info.value).lower()
        assert "corrupt" in error_msg or "invalid" in error_msg or "truncated" in error_msg

    def test_invalid_json_type(self):
        """JSON that's not a dict raises ValueError."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('["array", "not", "dict"]')
            f.flush()

            with pytest.raises(ValueError) as exc_info:
                load_graph(f.name)

            assert "dict" in str(exc_info.value).lower() or "object" in str(exc_info.value).lower()


class TestEndToEndScenarios:
    """End-to-end integration scenarios using fixtures."""

    def test_full_workflow_old_vs_new(self):
        """Complete workflow: load, compare, propagate, map."""
        # Load graphs
        old_graph = load_graph(FIXTURES_DIR / "graph_old.json")
        new_graph = load_graph(FIXTURES_DIR / "graph_new.json")
        module_tree = load_graph(FIXTURES_DIR / "module_tree.json")

        # Compare
        diff = compare_dependency_graphs(old_graph, new_graph)
        assert diff.modified == {"module.ClassA.method1"}

        # Get affected (depth=1 means we get the direct dependent too)
        affected = get_affected_components(diff.changed_components, new_graph, depth=1)
        assert "module.ClassA.method1" in affected
        assert "module.ClassB.method2" in affected  # depends on method1

        # Map to modules
        modules = map_components_to_modules(affected, module_tree)
        assert "module" in modules

    def test_identical_graphs_workflow(self):
        """Identical graphs produce empty results."""
        graph = load_graph(FIXTURES_DIR / "graph_old.json")
        module_tree = load_graph(FIXTURES_DIR / "module_tree.json")

        diff = compare_dependency_graphs(graph, graph)
        assert diff.is_empty

        affected = get_affected_components(diff.changed_components, graph, depth=2)
        assert affected == set()

        modules = map_components_to_modules(affected, module_tree)
        assert modules == []
