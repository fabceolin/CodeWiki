# Story: Affected Modules Detection for Incremental Documentation Updates

## Status

**Done**

---

## Story

**As a** CodeWiki user managing a large codebase,
**I want** to detect which modules were affected between two code versions by comparing their AST dependency graphs,
**so that** I can selectively regenerate documentation only for changed modules instead of the entire repository.

---

## Story Context

**Existing System Integration:**

- Integrates with: CLI (`codewiki/cli/commands/`), Dependency Analyzer (`codewiki/src/be/dependency_analyzer/`)
- Technology: Python, Click CLI framework, Pydantic models, JSON serialization
- Follows pattern: Existing CLI command structure in `generate.py`, comma-separated list patterns from `--focus`
- Touch points: `module_tree.json`, `dependency_graph.json`

**Input Files (two versions to compare):**

```
OLD version:
  ./temp/dependency_graphs/{repo}_dependency_graph.json

NEW version:
  ./temp/dependency_graphs/{repo}_dependency_graph.json
  ./module_tree.json  (only NEW needed for output mapping)
```

**Output Format:**

```json
["backend/auth/login", "backend/auth/logout", "utils/validation", "api/handlers"]
```

This format directly maps to CodeWiki's internal `module_key = "/".join(module_path)` used in `documentation_generator.py:154`, enabling seamless integration with a future `--modules` parameter.

---

## Acceptance Criteria

**Functional Requirements:**

1. New CLI command `codewiki affected-modules` accepts:
   - `--old-graph PATH` - Path to old dependency graph JSON
   - `--new-graph PATH` - Path to new dependency graph JSON
   - `--module-tree PATH` - Path to new module_tree.json (for mapping components to modules)
   - OR `--old-dir PATH --new-dir PATH` for directory-based convention

2. Command parses and compares dependency graphs to detect:
   - Added components (new IDs in new graph)
   - Removed components (IDs missing from new graph)
   - Modified components (same ID with different `source_code` hash or `depends_on` set)

3. Command identifies dependents up to N hops (default: 2, configurable via `--depth N`)

4. Command maps affected component IDs to module tree paths using slash-separated format

5. Output is a JSON array of affected module paths to stdout, compatible with future `--modules` parameter

6. Command outputs a human-readable summary to stderr:
   ```
   Changes detected: 3 added, 2 modified, 1 removed
   Affected components: 12 (including 2-hop dependents)
   Affected modules: 5
   ```

**Integration Requirements:**

7. Command follows existing Click CLI patterns from `generate.py`

8. Uses existing `Node` model structure for parsing (no new models required)

9. Default paths use `./temp/dependency_graphs/` convention

10. Exit code 0 on success; exit code 1 on error with message to stderr

**Quality Requirements:**

11. Unit tests cover: graph comparison, N-hop dependent detection, module path mapping

12. Handles edge cases: missing files, empty graphs, identical graphs (returns empty list `[]`)

13. Verbose mode (`-v`) logs component-level change details

---

## Tasks / Subtasks

- [x] **Task 1: Create graph diff utility module** (AC: 2, 3, 4)
  - [x] Create `codewiki/src/be/graph_diff.py`
  - [x] Implement `DiffResult` dataclass with `added`, `removed`, `modified` sets
  - [x] Implement `compare_dependency_graphs(old_graph: dict, new_graph: dict) -> DiffResult`
  - [x] Implement `build_reverse_dependency_map(graph: dict) -> Dict[str, Set[str]]`
  - [x] Implement `get_affected_components(changed: Set[str], graph: dict, depth: int = 2) -> Set[str]`
  - [x] Implement `map_components_to_modules(components: Set[str], module_tree: dict) -> List[str]`

- [x] **Task 2: Create CLI command** (AC: 1, 5, 6, 7, 10)
  - [x] Create `codewiki/cli/commands/affected.py`
  - [x] Implement `affected_modules` Click command with arguments:
    - `--old-graph` / `--old-dir`
    - `--new-graph` / `--new-dir`
    - `--module-tree` (optional if using `--new-dir`)
    - `--depth` (default: 2)
    - `--verbose` / `-v`
  - [x] Output JSON array to stdout
  - [x] Output summary to stderr
  - [x] Register command in `codewiki/cli/main.py`

- [x] **Task 3: Implement file loading and validation** (AC: 8, 9, 12)
  - [x] Load dependency graph JSON with error handling
  - [x] Load module_tree.json with error handling
  - [x] Validate required fields exist in graphs
  - [x] Handle missing files with clear error messages
  - [x] Handle identical graphs (return `[]` with summary showing 0 changes)

- [x] **Task 4: Write unit tests** (AC: 11, 12)
  - [x] Create `tests/test_graph_diff.py`
  - [x] Test `compare_dependency_graphs` with added/removed/modified components
  - [x] Test `get_affected_components` with 1-hop, 2-hop, and 3-hop scenarios
  - [x] Test `map_components_to_modules` with flat and nested module trees
  - [x] Test edge cases: empty graphs, identical graphs, missing dependencies
  - [x] Create `tests/cli/test_affected_command.py` for CLI integration tests

---

## Dev Notes

### Key Data Structures

**Dependency Graph JSON** (from `./temp/dependency_graphs/{repo}_dependency_graph.json`):

```python
{
    "module.ClassName.method_name": {
        "id": "module.ClassName.method_name",
        "name": "method_name",
        "component_type": "method",  # "function", "class", "method", "interface"
        "file_path": "/absolute/path/to/file.py",
        "relative_path": "src/module/file.py",
        "source_code": "def method_name(self, arg): ...",
        "depends_on": ["other.module.function", "utils.helper"],
        "start_line": 45,
        "end_line": 67,
        "parameters": ["self", "arg"],
        "class_name": "ClassName"  # if method
    },
    // ... more components
}
```

**Module Tree JSON** (from `./module_tree.json`):

```python
{
    "backend": {
        "components": ["backend.main", "backend.config"],
        "children": {
            "auth": {
                "components": ["backend.auth.login", "backend.auth.logout"],
                "children": {}
            },
            "api": {
                "components": ["backend.api.routes"],
                "children": {
                    "handlers": {
                        "components": ["backend.api.handlers.user"],
                        "children": {}
                    }
                }
            }
        }
    }
}
```

**Output Format** (to stdout):

```json
["backend/auth", "backend/api/handlers", "utils/validation"]
```

**Summary Format** (to stderr):

```
Changes detected: 3 added, 2 modified, 1 removed
Affected components: 12 (including 2-hop dependents)
Affected modules: 3
```

---

### Core Algorithm Implementation

**Graph Comparison:**

```python
from dataclasses import dataclass
from typing import Dict, Set

@dataclass
class DiffResult:
    added: Set[str]
    removed: Set[str]
    modified: Set[str]

    @property
    def all_changed(self) -> Set[str]:
        return self.added | self.removed | self.modified

def compare_dependency_graphs(old: dict, new: dict) -> DiffResult:
    old_ids = set(old.keys())
    new_ids = set(new.keys())

    added = new_ids - old_ids
    removed = old_ids - new_ids

    modified = set()
    for cid in old_ids & new_ids:
        old_node, new_node = old[cid], new[cid]
        if (hash(old_node.get("source_code", "")) != hash(new_node.get("source_code", ""))
            or set(old_node.get("depends_on", [])) != set(new_node.get("depends_on", []))
            or old_node.get("parameters") != new_node.get("parameters")
            or old_node.get("file_path") != new_node.get("file_path")):
            modified.add(cid)

    return DiffResult(added=added, removed=removed, modified=modified)
```

**N-Hop Dependent Detection:**

```python
from collections import defaultdict

def build_reverse_dependency_map(graph: dict) -> Dict[str, Set[str]]:
    """Build map: component_id -> set of components that depend on it."""
    reverse_deps = defaultdict(set)
    for cid, node in graph.items():
        for dep in node.get("depends_on", []):
            reverse_deps[dep].add(cid)
    return reverse_deps

def get_affected_components(
    changed: Set[str],
    graph: dict,
    depth: int = 2
) -> Set[str]:
    """Get changed components + N-hop dependents."""
    reverse_deps = build_reverse_dependency_map(graph)

    affected = set(changed)
    frontier = set(changed)

    for _ in range(depth):
        next_frontier = set()
        for cid in frontier:
            dependents = reverse_deps.get(cid, set())
            new_dependents = dependents - affected
            next_frontier.update(new_dependents)

        if not next_frontier:
            break

        affected.update(next_frontier)
        frontier = next_frontier

    return affected
```

**Module Path Mapping:**

```python
def map_components_to_modules(
    components: Set[str],
    module_tree: dict
) -> List[str]:
    """Map component IDs to module paths (slash-separated)."""
    affected_modules = set()

    def traverse(tree: dict, path: List[str]):
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
    return sorted(affected_modules)  # Deterministic output
```

---

### CLI Command Structure

```python
# codewiki/cli/commands/affected.py
import click
import json
import sys

@click.command("affected-modules")
@click.option("--old-graph", type=click.Path(exists=True), help="Path to old dependency graph JSON")
@click.option("--new-graph", type=click.Path(exists=True), help="Path to new dependency graph JSON")
@click.option("--module-tree", type=click.Path(exists=True), help="Path to module_tree.json")
@click.option("--old-dir", type=click.Path(exists=True), help="Directory containing old graph")
@click.option("--new-dir", type=click.Path(exists=True), help="Directory containing new graph")
@click.option("--depth", default=2, type=int, help="Dependency traversal depth (default: 2)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed change information")
def affected_modules(old_graph, new_graph, module_tree, old_dir, new_dir, depth, verbose):
    """Detect modules affected by changes between two dependency graphs."""
    # ... implementation

    # Output JSON to stdout
    click.echo(json.dumps(affected_module_paths))

    # Output summary to stderr
    click.echo(f"Changes detected: {len(diff.added)} added, {len(diff.modified)} modified, {len(diff.removed)} removed", err=True)
    click.echo(f"Affected components: {len(affected_components)} (including {depth}-hop dependents)", err=True)
    click.echo(f"Affected modules: {len(affected_module_paths)}", err=True)
```

---

### Source Files Reference

| File | Purpose |
|------|---------|
| `codewiki/cli/commands/generate.py` | CLI pattern reference, `--focus` comma pattern |
| `codewiki/src/be/dependency_analyzer/models/core.py` | `Node` model structure |
| `codewiki/src/be/cluster_modules.py` | Module tree structure |
| `codewiki/src/be/documentation_generator.py:154` | `module_key = "/".join(module_path)` format |
| `codewiki/src/config.py` | Configuration patterns |

### Testing

- Test location: `tests/test_graph_diff.py`, `tests/cli/test_affected_command.py`
- Framework: pytest
- Fixtures: Create sample graph JSON files in `tests/fixtures/graphs/`

---

## Technical Notes

- **Integration Approach**: New standalone command, prepares output for future `--modules` parameter
- **Existing Pattern Reference**: Follow `generate.py` Click structure; output format matches internal `module_key`
- **Key Constraints**:
  - Output must be deterministic (sorted module paths)
  - JSON to stdout, summary to stderr (enables piping: `codewiki affected-modules ... | codewiki generate --modules -`)
  - Default depth=2 balances coverage vs. over-regeneration

---

## Risk and Compatibility Check

**Minimal Risk Assessment:**

- **Primary Risk**: Incorrect depth could miss affected modules or include too many
- **Mitigation**: Default depth=2 is conservative; `--depth` flag allows adjustment; verbose mode for debugging
- **Rollback**: Command is purely additive; remove from CLI registration to disable

**Compatibility Verification:**

- [x] No breaking changes to existing APIs
- [x] No database changes
- [x] No UI changes
- [x] Performance: O(n) graph comparison, O(n*d) dependent traversal where d=depth

---

## Definition of Done

- [x] CLI command `codewiki affected-modules` works with both file paths and directory conventions
- [x] Returns JSON array of affected module paths to stdout
- [x] Outputs human-readable summary to stderr
- [x] Changed components + N-hop dependents (default 2) are included
- [x] Unit tests pass with >90% coverage on new code
- [x] Verbose mode shows detailed change breakdown
- [x] Command registered and appears in `codewiki --help`
- [x] Works with existing `./temp/dependency_graphs/` convention

---

## Future Integration Notes

This story prepares for a follow-up story that will add `--modules` parameter to `codewiki generate`:

```bash
# Future usage pattern (not in this story's scope):
AFFECTED=$(codewiki affected-modules --old-dir ./v1 --new-dir ./v2)
codewiki generate --modules "$AFFECTED" --force
```

The `--modules` parameter will filter the processing loop in `documentation_generator.py` using the existing `module_key` matching logic.

---

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-26 | 0.1 | Initial draft | Sarah (PO) |
| 2026-01-26 | 0.2 | Updated with 2-hop default, summary output, temp directory convention, confirmed output format compatibility | Sarah (PO) |
| 2026-01-26 | 1.0 | Implementation complete - all tasks done, 56 tests passing | James (Dev) |

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - No blocking issues encountered

### Completion Notes

1. Created `codewiki/src/be/graph_diff.py` with:
   - `DiffResult` dataclass with `added`, `removed`, `modified` sets
   - `compare_dependency_graphs()` - detects added/removed/modified components by comparing source hash, deps, params, file path
   - `build_reverse_dependency_map()` - builds reverse dependency lookup
   - `get_affected_components()` - N-hop traversal with circular dependency handling
   - `map_components_to_modules()` - maps component IDs to module paths

2. Created `codewiki/cli/commands/affected.py` with:
   - Click command supporting `--old-graph/--new-graph/--module-tree` explicit paths
   - Alternative `--old-dir/--new-dir` directory convention mode
   - `--depth` option (default 2) for N-hop traversal
   - `--verbose/-v` flag for detailed output
   - JSON array to stdout, summary to stderr
   - Comprehensive error handling for missing/malformed files

3. Registered command in `codewiki/cli/main.py`

4. Created comprehensive test suite:
   - `tests/test_graph_diff.py` - 35 unit tests covering all functions and edge cases
   - `tests/cli/test_affected_command.py` - 21 integration tests for CLI
   - Test fixtures in `tests/fixtures/graphs/`

5. All 56 tests pass

### File List

**New Files:**
- `codewiki/src/be/graph_diff.py` - Core graph diff utility module
- `codewiki/cli/commands/affected.py` - CLI command implementation
- `tests/__init__.py` - Tests package init
- `tests/test_graph_diff.py` - Unit tests for graph_diff module
- `tests/cli/__init__.py` - CLI tests package init
- `tests/cli/test_affected_command.py` - CLI integration tests
- `tests/fixtures/graphs/minimal_graph_old.json` - Test fixture
- `tests/fixtures/graphs/minimal_graph_new.json` - Test fixture
- `tests/fixtures/graphs/circular_graph.json` - Test fixture for circular deps
- `tests/fixtures/graphs/deep_hierarchy_graph.json` - Test fixture for depth testing
- `tests/fixtures/graphs/module_tree_simple.json` - Test fixture
- `tests/fixtures/graphs/module_tree_nested.json` - Test fixture

**Modified Files:**
- `codewiki/cli/main.py` - Added affected_modules command registration

---

## QA Notes - Risk Profile

**Date:** 2026-01-26
**Reviewer:** Quinn (Test Architect)
**Mode:** YOLO (Rapid Assessment)

### Risk Level: CONCERNS

**Overall Risk Score:** 73/100

### Risk Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 1 |
| Medium | 3 |
| Low | 2 |

### Identified Risks

| ID | Risk | Score | Priority |
|----|------|-------|----------|
| TECH-001 | N-hop depth miscalculation (over/under-inclusion of modules) | 6 | **High** |
| DATA-001 | Hash comparison false positives from whitespace changes | 4 | Medium |
| TECH-002 | Module tree/graph component ID mismatch | 4 | Medium |
| DATA-002 | Malformed JSON files cause cryptic errors | 4 | Medium |
| OPS-001 | Memory pressure on large graphs | 3 | Low |
| TECH-003 | CLI argument mutual exclusion edge cases | 2 | Low |

### Key Mitigations Required

**Must Fix (before production):**
1. Add unit tests for circular dependency handling in N-hop traversal
2. Implement verbose traversal logging for debugging depth calculations
3. Add JSON validation with clear error messages for malformed input
4. Warn when >10% of affected components can't map to modules

**Monitor (post-deployment):**
1. Track unmapped component percentage in verbose mode
2. Profile memory usage on repositories with 50K+ components

### Testing Priorities

1. **Priority 1 (High Risk):** N-hop traversal edge cases - circular deps, depth boundaries, disconnected graphs
2. **Priority 2 (Medium Risk):** JSON parsing errors, component ID mapping variations, whitespace-only changes
3. **Priority 3 (Standard):** CLI argument validation, output format, exit codes

### Gate Decision

**CONCERNS** - High risk (TECH-001) requires focused testing on the N-hop traversal algorithm. Story is implementable but needs explicit test coverage for depth calculation edge cases before deployment.

---

*Risk profile generated by Quinn (QA Agent) - BMAD Framework*

---

## QA Notes - NFR Assessment

**Date:** 2026-01-26
**Reviewer:** Quinn (Test Architect)
**Mode:** YOLO (Rapid Assessment)

### NFR Coverage Summary

| NFR | Status | Quality Score Impact |
|-----|--------|---------------------|
| Security | CONCERNS | -10 |
| Performance | CONCERNS | -10 |
| Reliability | PASS | 0 |
| Maintainability | PASS | 0 |

**Overall Quality Score:** 80/100

### Security Assessment

**Status: CONCERNS**

- **Issue 1:** CLI accepts arbitrary file paths (`--old-graph`, `--new-graph`, `--module-tree`) without explicit path validation
- **Issue 2:** No symlink handling policy defined
- **Issue 3:** JSON parsing could be vulnerable to DoS from maliciously crafted large/nested files

**Mitigation Needed:**
- Add path validation using `pathlib.Path.resolve()` to prevent path traversal
- Implement file size limits before loading JSON into memory
- Consider restricting file access to expected directories

### Performance Assessment

**Status: CONCERNS**

- **Positive:** Algorithm complexity documented (O(n) comparison, O(n*d) traversal)
- **Gap 1:** No explicit response time targets defined
- **Gap 2:** Memory pressure risk on large repositories (50K+ components) noted in risk profile but no mitigation in acceptance criteria
- **Gap 3:** No streaming/chunked processing for very large JSON files

**Thresholds Needed (Recommended):**
- Response time: <5s for repositories up to 10K components
- Memory: Warning at >100MB graph file
- Add execution time logging in verbose mode

### Reliability Assessment

**Status: PASS**

- Error handling explicitly defined (AC: 10 - exit codes)
- Edge cases documented (AC: 12 - missing files, empty graphs, identical graphs)
- Verbose mode provides debugging capabilities (AC: 13)
- Graceful degradation for edge cases

### Maintainability Assessment

**Status: PASS**

- Test coverage target: >90% on new code (DoD)
- Clean module separation: `graph_diff.py` (core logic), `affected.py` (CLI)
- Comprehensive Dev Notes with code examples and data structures
- Uses existing patterns and models (Node model, Click CLI)

### Missing NFR Considerations

1. **Usability:** No mention of progress indicators for long-running operations on large graphs
2. **Compatibility:** No mention of JSON schema versioning for future graph format changes
3. **Portability:** No explicit mention of cross-platform path handling (Windows vs Unix)

### Test Recommendations

**Security Tests (Add to Task 4):**
1. Test path traversal prevention with `../` sequences in file arguments
2. Test symlink handling behavior
3. Test with malformed/deeply nested JSON files
4. Test maximum file size handling

**Performance Tests (Add to Task 4):**
1. Profile memory usage with synthetic 50K component graph
2. Benchmark execution time at various graph sizes (1K, 10K, 50K components)
3. Test with graph files exceeding 100MB

**Reliability Tests (Existing coverage adequate):**
- Edge cases well covered in story definition

### Recommended Acceptance Criteria Additions

```markdown
14. Input file paths are validated to be readable files (not directories, symlinks to outside locations, or non-existent)

15. Warning logged if graph file exceeds 100MB (configurable via --max-file-size)

16. Verbose mode includes execution time for each phase (load, compare, traverse, map)
```

### Gate Integration

NFR validation block ready for gate file:

```yaml
nfr_validation:
  _assessed: [security, performance, reliability, maintainability]
  security:
    status: CONCERNS
    notes: 'Path traversal risk; JSON DoS potential - needs input validation'
  performance:
    status: CONCERNS
    notes: 'No response time targets; memory risk on 50K+ components'
  reliability:
    status: PASS
    notes: 'Error handling and edge cases well documented'
  maintainability:
    status: PASS
    notes: '>90% test coverage target; clean architecture'
```

**Full Assessment Report:** docs/qa/assessments/incremental-doc-update-affected-modules-nfr-20260126.md

---

*NFR assessment generated by Quinn (QA Agent) - BMAD Framework*

---

## QA Notes - Test Design

**Date:** 2026-01-26
**Designer:** Quinn (Test Architect)
**Mode:** YOLO (Rapid Design)

### Test Strategy Overview

| Metric | Value |
|--------|-------|
| Total test scenarios | 34 |
| Unit tests | 18 (53%) |
| Integration tests | 12 (35%) |
| E2E tests | 4 (12%) |
| Priority distribution | P0: 12, P1: 14, P2: 6, P3: 2 |

### Test Coverage Matrix

| AC | Unit | Integration | E2E | Total Coverage |
|----|------|-------------|-----|----------------|
| AC1 (CLI arguments) | - | 3 | 2 | ✅ Full |
| AC2 (diff detection) | 6 | 1 | - | ✅ Full |
| AC3 (N-hop traversal) | 5 | 1 | 1 | ✅ Full |
| AC4 (module mapping) | 4 | 1 | - | ✅ Full |
| AC5 (JSON output) | - | 2 | 1 | ✅ Full |
| AC6 (summary output) | - | 2 | 1 | ✅ Full |
| AC7-9 (CLI patterns) | - | - | - | By design |
| AC10 (exit codes) | - | 2 | - | ✅ Full |
| AC11-12 (edge cases) | 3 | 1 | - | ✅ Full |
| AC13 (verbose mode) | - | 2 | - | ✅ Full |

---

### Test Scenarios by Acceptance Criteria

#### AC2: Component Diff Detection

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-UNIT-001 | Unit | P0 | compare_dependency_graphs detects added components | Pure logic - new IDs in new graph | TECH-002 |
| IDU-UNIT-002 | Unit | P0 | compare_dependency_graphs detects removed components | Pure logic - IDs missing from new graph | TECH-002 |
| IDU-UNIT-003 | Unit | P0 | compare_dependency_graphs detects modified source_code | Critical diff detection | DATA-001 |
| IDU-UNIT-004 | Unit | P0 | compare_dependency_graphs detects modified depends_on | Critical dependency change detection | TECH-001 |
| IDU-UNIT-005 | Unit | P1 | compare_dependency_graphs detects modified parameters | Secondary modification signal | - |
| IDU-UNIT-006 | Unit | P1 | compare_dependency_graphs detects modified file_path | File relocation detection | - |
| IDU-INT-001 | Integration | P0 | End-to-end diff with realistic graph structures | Validates full diff pipeline | TECH-002 |

**Expected Results:**
- IDU-UNIT-001: Returns DiffResult with added={new_component_id}, removed=∅, modified=∅
- IDU-UNIT-002: Returns DiffResult with added=∅, removed={old_component_id}, modified=∅
- IDU-UNIT-003: source_code change triggers modified set inclusion
- IDU-UNIT-004: depends_on set difference triggers modified set inclusion

---

#### AC3: N-Hop Dependent Detection

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-UNIT-007 | Unit | P0 | get_affected_components returns changed + 1-hop dependents | Core algorithm validation | TECH-001 |
| IDU-UNIT-008 | Unit | P0 | get_affected_components returns changed + 2-hop dependents (default) | Default behavior critical | TECH-001 |
| IDU-UNIT-009 | Unit | P0 | get_affected_components stops at depth boundary | Prevents over-inclusion | TECH-001 |
| IDU-UNIT-010 | Unit | P0 | get_affected_components handles circular dependencies | **Critical** - prevents infinite loops | TECH-001 |
| IDU-UNIT-011 | Unit | P1 | build_reverse_dependency_map correctly inverts graph | Algorithm dependency | TECH-001 |
| IDU-INT-002 | Integration | P1 | N-hop traversal with complex interconnected graph | Real-world scenario | TECH-001 |
| IDU-E2E-001 | E2E | P1 | --depth 3 includes 3-hop dependents in output | CLI-to-algorithm integration | - |

**Expected Results:**
- IDU-UNIT-007: depth=1 returns {changed, immediate_dependents}
- IDU-UNIT-008: depth=2 returns {changed, 1-hop, 2-hop}
- IDU-UNIT-009: depth=2 with 3-hop available returns only up to 2-hop
- IDU-UNIT-010: Circular A→B→C→A terminates without infinite loop

**Test Data (IDU-UNIT-010 - Circular Dependency):**
```python
circular_graph = {
    "A": {"id": "A", "depends_on": ["B"]},
    "B": {"id": "B", "depends_on": ["C"]},
    "C": {"id": "C", "depends_on": ["A"]},  # circular back to A
    "D": {"id": "D", "depends_on": ["B"]}
}
# Changed: {"C"}, depth=2
# Expected: {"C", "A", "B", "D"} - D depends on B which depends on C
```

---

#### AC4: Module Path Mapping

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-UNIT-012 | Unit | P0 | map_components_to_modules maps flat module tree | Basic functionality | TECH-002 |
| IDU-UNIT-013 | Unit | P0 | map_components_to_modules maps nested module tree | Hierarchy handling | TECH-002 |
| IDU-UNIT-014 | Unit | P1 | map_components_to_modules returns sorted output | Deterministic output | - |
| IDU-UNIT-015 | Unit | P1 | map_components_to_modules handles unmapped components | **Graceful degradation** | TECH-002 |
| IDU-INT-003 | Integration | P0 | Full pipeline: diff → traverse → map produces correct module list | End-to-end data flow | TECH-002 |

**Expected Results:**
- IDU-UNIT-012: Single-level tree maps correctly
- IDU-UNIT-013: "backend/auth/login" → "backend/auth" module path
- IDU-UNIT-014: Output alphabetically sorted
- IDU-UNIT-015: Components not in module tree are skipped (logged in verbose)

---

#### AC1, AC5, AC6, AC10: CLI Command Behavior

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-INT-004 | Integration | P0 | CLI accepts --old-graph --new-graph --module-tree | Primary input mode | - |
| IDU-INT-005 | Integration | P1 | CLI accepts --old-dir --new-dir (directory mode) | Alternative input mode | - |
| IDU-INT-006 | Integration | P0 | CLI outputs valid JSON array to stdout | Integration contract | - |
| IDU-INT-007 | Integration | P0 | CLI outputs summary to stderr (not mixed with stdout) | Output separation critical | - |
| IDU-INT-008 | Integration | P0 | CLI returns exit code 0 on success | Error handling contract | - |
| IDU-INT-009 | Integration | P0 | CLI returns exit code 1 on error with message to stderr | Error handling contract | DATA-002 |
| IDU-E2E-002 | E2E | P0 | Piping: `codewiki affected-modules ... \| jq .` succeeds | Real-world usage | - |
| IDU-E2E-003 | E2E | P1 | Output matches `module_key` format from documentation_generator | Integration compatibility | - |

**Expected Results:**
- IDU-INT-006: `["backend/auth", "utils/validation"]` valid JSON array
- IDU-INT-007: Summary lines appear only in stderr, not stdout
- IDU-E2E-002: jq can parse output without errors

---

#### AC12: Edge Cases

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-UNIT-016 | Unit | P0 | compare_dependency_graphs with empty old graph | Edge case - all added | - |
| IDU-UNIT-017 | Unit | P0 | compare_dependency_graphs with empty new graph | Edge case - all removed | - |
| IDU-UNIT-018 | Unit | P1 | compare_dependency_graphs with identical graphs | Edge case - returns empty | - |
| IDU-INT-010 | Integration | P1 | CLI handles missing file with clear error message | Error UX | DATA-002 |

**Expected Results:**
- IDU-UNIT-016: DiffResult with added=all_new_ids
- IDU-UNIT-017: DiffResult with removed=all_old_ids
- IDU-UNIT-018: DiffResult with all sets empty, output `[]`

---

#### AC13: Verbose Mode

| ID | Level | Priority | Test Scenario | Justification | Mitigates |
|----|-------|----------|---------------|---------------|-----------|
| IDU-INT-011 | Integration | P2 | -v flag logs component-level changes | Debug capability | - |
| IDU-INT-012 | Integration | P2 | Verbose logs traversal at each hop depth | TECH-001 mitigation | TECH-001 |
| IDU-E2E-004 | E2E | P2 | Verbose output shows execution phases | User debugging | - |

---

### Risk Coverage Matrix

| Risk ID | Risk Description | Test Coverage |
|---------|------------------|---------------|
| TECH-001 | N-hop depth miscalculation | IDU-UNIT-007 through IDU-UNIT-011, IDU-INT-002, IDU-INT-012 |
| DATA-001 | Hash comparison false positives | IDU-UNIT-003 |
| TECH-002 | Module tree/graph ID mismatch | IDU-UNIT-012 through IDU-UNIT-015, IDU-INT-003 |
| DATA-002 | Malformed JSON errors | IDU-INT-009, IDU-INT-010 |
| OPS-001 | Memory pressure on large graphs | (P3 - manual performance testing recommended) |
| TECH-003 | CLI argument edge cases | IDU-INT-004, IDU-INT-005 |

---

### Test Data Requirements

**Fixture Files (tests/fixtures/graphs/):**

1. **minimal_graph_old.json** - 5 components, simple chain dependency
2. **minimal_graph_new.json** - Same 5 components with 1 modified, 1 added, 1 removed
3. **circular_graph.json** - 4 components with circular dependency A→B→C→A
4. **deep_hierarchy_graph.json** - 20 components, 5 levels deep
5. **module_tree_simple.json** - Flat module tree (no nesting)
6. **module_tree_nested.json** - 3-level nested module tree

**Sample Test Fixture (minimal_graph_old.json):**
```json
{
    "backend.auth.login": {
        "id": "backend.auth.login",
        "name": "login",
        "source_code": "def login(user, pwd): ...",
        "depends_on": ["backend.auth.validate", "backend.db.users"]
    },
    "backend.auth.validate": {
        "id": "backend.auth.validate",
        "name": "validate",
        "source_code": "def validate(token): ...",
        "depends_on": []
    },
    "backend.db.users": {
        "id": "backend.db.users",
        "name": "users",
        "source_code": "class Users: ...",
        "depends_on": ["backend.db.connection"]
    },
    "backend.db.connection": {
        "id": "backend.db.connection",
        "name": "connection",
        "source_code": "def get_connection(): ...",
        "depends_on": []
    },
    "utils.helpers": {
        "id": "utils.helpers",
        "name": "helpers",
        "source_code": "def helper(): ...",
        "depends_on": []
    }
}
```

---

### Test Environment Requirements

| Requirement | Details |
|-------------|---------|
| Python Version | 3.12+ |
| Test Framework | pytest |
| Fixtures Location | tests/fixtures/graphs/ |
| Coverage Tool | pytest-cov |
| Coverage Target | >90% on new code |
| Mock Requirements | None (pure logic functions) |
| External Dependencies | None (file I/O only) |
| CI Integration | Standard pytest execution |

---

### Recommended Execution Order

1. **P0 Unit tests** (fail fast on core logic)
   - IDU-UNIT-001 through IDU-UNIT-004 (diff detection)
   - IDU-UNIT-007 through IDU-UNIT-010 (N-hop traversal)
   - IDU-UNIT-012, IDU-UNIT-013 (module mapping)

2. **P0 Integration tests** (component interaction)
   - IDU-INT-001 (realistic diff)
   - IDU-INT-003 (full pipeline)
   - IDU-INT-006 through IDU-INT-009 (CLI contract)

3. **P0 E2E tests** (critical paths)
   - IDU-E2E-002 (piping works)

4. **P1 tests in order**

5. **P2+ as time permits**

---

### Gate YAML Block

```yaml
test_design:
  date: '2026-01-26'
  designer: Quinn
  scenarios_total: 34
  by_level:
    unit: 18
    integration: 12
    e2e: 4
  by_priority:
    p0: 12
    p1: 14
    p2: 6
    p3: 2
  coverage_gaps: []
  risk_coverage:
    TECH-001: 7 scenarios
    DATA-001: 1 scenario
    TECH-002: 5 scenarios
    DATA-002: 2 scenarios
    OPS-001: 0 scenarios (manual)
    TECH-003: 2 scenarios
  critical_tests:
    - IDU-UNIT-010  # Circular dependency handling
    - IDU-INT-003   # Full pipeline integration
    - IDU-E2E-002   # Piping compatibility
```

---

### Quality Checklist

- [x] Every AC has test coverage
- [x] Test levels are appropriate (shift-left applied)
- [x] No duplicate coverage across levels
- [x] Priorities align with business risk
- [x] Test IDs follow naming convention (IDU-{LEVEL}-{SEQ})
- [x] Scenarios are atomic and independent
- [x] All identified risks have test mitigations
- [x] Edge cases covered (empty, identical, circular)
- [x] Test data requirements documented
- [x] Execution order optimized for fail-fast

---

*Test design generated by Quinn (QA Agent) - BMAD Framework*

---

## SM Validation

**Date:** 2026-01-26
**Reviewer:** Bob (Scrum Master)
**Mode:** YOLO (Rapid Validation)

### Definition of Ready Checklist

| Category | Status | Issues |
|----------|--------|--------|
| 1. Goal & Context Clarity | ✅ PASS | None - clear user story, business value, and system integration |
| 2. Technical Implementation Guidance | ✅ PASS | None - comprehensive code examples, data structures, CLI design |
| 3. Reference Effectiveness | ✅ PASS | None - specific file references with line numbers |
| 4. Self-Containment Assessment | ✅ PASS | None - complete algorithms and edge cases documented |
| 5. Testing Guidance | ✅ PASS | None - 34 test scenarios with full coverage matrix |

### Definition of Ready Criteria

| Criterion | Status |
|-----------|--------|
| Story has clear title and description | ✅ PASS |
| Acceptance criteria are defined and testable | ✅ PASS (13 ACs) |
| Dependencies are identified | ✅ PASS |
| Technical approach is documented | ✅ PASS |
| Story is properly sized | ✅ PASS (4 tasks) |
| QA Notes - Risk Profile present | ✅ PASS |
| QA Notes - NFR Assessment present | ✅ PASS |
| QA Notes - Test Design present | ✅ PASS |
| No blocking issues or unknowns | ✅ PASS |

### Validation Summary

**Clarity Score:** 9/10

**Strengths:**
- Exceptionally detailed technical documentation with complete algorithm implementations
- Comprehensive test design with 34 scenarios covering all acceptance criteria
- Thorough risk assessment with mitigations identified
- Self-contained with all necessary data structures and code examples
- Clear integration path for future `--modules` parameter

**Minor Observations (non-blocking):**
- NFR assessment noted CONCERNS for security (path validation) and performance (no explicit targets)
- These are documented with recommended mitigations in the NFR section
- Risk profile rated CONCERNS for TECH-001 (N-hop depth) with explicit test coverage

**Final Assessment:** **READY FOR DEVELOPMENT**

This story provides exceptional context for a developer agent to implement successfully. The combination of clear acceptance criteria, complete algorithm implementations, comprehensive test design, and thorough QA assessments makes this story exemplary.

---

*SM Validation completed by Bob (Scrum Master) - BMAD Framework*

---

## Story DoD Checklist (Developer Self-Validation)

**Date:** 2026-01-26
**Developer:** James (Dev Agent)
**Model:** Claude Opus 4.5

### 1. Requirements Met

- [x] All functional requirements specified in the story are implemented.
- [x] All acceptance criteria defined in the story are met.
  - AC1: CLI command with all specified options ✓
  - AC2: Detects added/removed/modified components ✓
  - AC3: N-hop dependent detection (default 2) ✓
  - AC4: Maps components to module paths ✓
  - AC5: JSON array output to stdout ✓
  - AC6: Summary to stderr ✓
  - AC7-9: Follows Click patterns, uses Node model fields, uses temp directory convention ✓
  - AC10: Exit codes 0/1 ✓
  - AC11-12: Unit tests cover all scenarios, edge cases handled ✓
  - AC13: Verbose mode logs details ✓

### 2. Coding Standards & Project Structure

- [x] All new/modified code strictly adheres to `Operational Guidelines`.
- [x] All new/modified code aligns with `Project Structure` (file locations, naming, etc.).
- [x] Adherence to `Tech Stack` for technologies/versions used.
- [x] Basic security best practices applied (input validation, error handling, file size warnings).
- [x] No new linter errors or warnings introduced.
- [x] Code is well-commented where necessary.

### 3. Testing

- [x] All required unit tests implemented (35 tests in test_graph_diff.py).
- [x] All required integration tests implemented (21 tests in test_affected_command.py).
- [x] All tests pass successfully (56 tests passing).
- [x] Test coverage includes all edge cases: empty graphs, identical graphs, circular dependencies.

### 4. Functionality & Verification

- [x] Functionality manually verified:
  - `codewiki --help` shows affected-modules command
  - `codewiki affected-modules --help` shows all options
  - Actual command execution produces correct JSON output
  - Summary appears on stderr
  - Verbose mode shows detailed output
- [x] Edge cases and potential error conditions handled gracefully.

### 5. Story Administration

- [x] All tasks within the story file are marked as complete.
- [x] Story wrap up section completed with notes and changelog.

### 6. Dependencies, Build & Configuration

- [x] Project builds successfully without errors.
- [x] No new dependencies added (uses existing Click, JSON, pathlib).
- [x] No new environment variables or configurations needed.

### 7. Documentation

- [x] Inline code documentation (docstrings) for all public APIs.
- [N/A] User-facing documentation - CLI help is self-documenting.
- [N/A] Technical documentation - No architectural changes.

### Final Confirmation

**Summary of Accomplishments:**
- Implemented `codewiki affected-modules` CLI command
- Created graph diff utility module with 4 core functions
- Comprehensive test suite with 56 tests
- All acceptance criteria met
- Command registered and functional

**Technical Debt:** None identified

**Challenges/Learnings:**
- pytest capture issue required `--capture=no` flag during development
- CliRunner mixes stdout/stderr by default, tests adapted accordingly

- [x] I, the Developer Agent, confirm that all applicable items above have been addressed.

---

*Story DoD validation completed by James (Dev Agent) - BMAD Framework*

---

## QA Results

### Review Date: 2026-01-26

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

**Overall: EXCELLENT**

The implementation demonstrates high-quality software engineering practices:

1. **Clean Architecture**: Clear separation between core logic (`graph_diff.py`) and CLI interface (`affected.py`). The module structure follows the existing codebase patterns.

2. **Well-Documented Code**: Comprehensive docstrings on all public functions with clear explanations of Args/Returns. Module-level documentation explains purpose and capabilities.

3. **Type Annotations**: Proper use of Python 3.12+ type hints throughout (`Dict[str, Any]`, `Set[str]`, `List[str]`). Return type annotations present on all functions.

4. **Error Handling**: Robust error handling with `click.ClickException` for user-friendly messages. File validation covers existence, type, JSON parsing, and schema validation.

5. **Algorithm Quality**:
   - `graph_diff.py:35-39`: Good hash-based comparison using SHA-256
   - `graph_diff.py:131-178`: N-hop traversal correctly handles circular dependencies via visited set tracking
   - `graph_diff.py:200-214`: Recursive traversal properly handles nested module trees

6. **CLI Design**: Follows Click best practices with clear help text, mutually exclusive option groups, and comprehensive examples in docstring.

### Refactoring Performed

None required. Code quality is high and meets all requirements without modification.

### Compliance Check

- Coding Standards: ✓ Code follows Python PEP 8 style, proper type hints, comprehensive docstrings
- Project Structure: ✓ Files placed in correct locations (`codewiki/src/be/`, `codewiki/cli/commands/`, `tests/`)
- Testing Strategy: ✓ 56 tests covering unit (35), integration (21), with test IDs matching test design
- All ACs Met: ✓ All 13 acceptance criteria implemented and verified

### Improvements Checklist

- [x] Core algorithm handles circular dependencies correctly (`graph_diff.py:162-170`)
- [x] File size warning implemented for files > 100MB (`affected.py:44-51`)
- [x] Path resolution uses `pathlib.Path.resolve()` for security (`affected.py:104-108`)
- [x] Verbose mode includes execution timing for all phases (`affected.py:279-337`)
- [x] JSON validation rejects non-object inputs (`affected.py:61-65`)
- [ ] **Suggestion**: Consider adding `--max-file-size` configurable option (currently hardcoded at 100MB)
- [ ] **Suggestion**: Add symlink handling policy (currently allows symlinks - may want to document or restrict)
- [ ] **Suggestion**: Consider streaming JSON parsing for very large graphs (> 500MB)

### Security Review

**Status: PASS with Advisory**

**Positive Findings:**
- Path resolution uses `Path.resolve()` which normalizes paths and resolves `..` components
- File size warning prevents DoS from extremely large files
- JSON validation rejects unexpected data structures

**Advisory (not blocking):**
- Symlinks are followed without restriction - acceptable for development tool, but document behavior
- No explicit path sandboxing - acceptable since this is a CLI tool run by the user

### Performance Considerations

**Status: PASS**

**Verified:**
- Algorithm complexity documented: O(n) comparison, O(n*d) traversal
- Verbose mode includes timing for each phase (load, compare, traverse, map)
- File size warning at 100MB boundary

**Benchmark (verified via code review):**
- Graph comparison: Single pass through both graphs
- N-hop traversal: Breadth-first with visited tracking prevents redundant work
- Module mapping: Single tree traversal

### Files Modified During Review

None. No modifications were necessary.

### Gate Status

**Gate: PASS** → docs/qa/gates/incremental-doc-update-affected-modules.yml

### Evidence Summary

| Metric | Value |
|--------|-------|
| Tests Reviewed | 56 |
| Test Coverage | Comprehensive (all ACs covered) |
| Risks Identified | 6 (from risk profile) |
| High/Critical Risks | 0 Critical, 1 High (TECH-001 - mitigated by tests) |
| Code Files | 3 new files, 1 modified |
| Lines of Code | ~600 (implementation + tests) |

### Requirements Traceability

| AC | Test Coverage | Status |
|----|--------------|--------|
| AC1: CLI arguments | IDU-INT-004, IDU-INT-005 | ✓ |
| AC2: Diff detection | IDU-UNIT-001 to IDU-UNIT-006, IDU-INT-001 | ✓ |
| AC3: N-hop traversal | IDU-UNIT-007 to IDU-UNIT-011, IDU-INT-002, IDU-E2E-001 | ✓ |
| AC4: Module mapping | IDU-UNIT-012 to IDU-UNIT-015, IDU-INT-003 | ✓ |
| AC5: JSON output | IDU-INT-006, IDU-E2E-002, IDU-E2E-003 | ✓ |
| AC6: Summary output | IDU-INT-007 | ✓ |
| AC7-9: CLI patterns | By design (follows existing patterns) | ✓ |
| AC10: Exit codes | IDU-INT-008, IDU-INT-009 | ✓ |
| AC11-12: Edge cases | IDU-UNIT-016 to IDU-UNIT-018, IDU-INT-010 | ✓ |
| AC13: Verbose mode | IDU-INT-011, IDU-INT-012, IDU-E2E-004 | ✓ |

### NFR Validation Summary

| NFR | Status | Notes |
|-----|--------|-------|
| Security | PASS | Path validation implemented, file size warnings |
| Performance | PASS | O(n) complexity, timing in verbose mode |
| Reliability | PASS | Comprehensive error handling, edge cases covered |
| Maintainability | PASS | Clean architecture, comprehensive tests |

### Recommended Status

✓ **Ready for Done**

This story is complete with high-quality implementation. All acceptance criteria are met, comprehensive test coverage is in place, and the code follows established patterns. The implementation is well-documented and handles edge cases properly.

Minor suggestions (not blocking):
1. Document symlink behavior in CLI help or README
2. Consider adding `--max-file-size` option for configurability
3. Future consideration: streaming JSON for very large repositories

---

*QA Review completed by Quinn (Test Architect) - BMAD Framework*
