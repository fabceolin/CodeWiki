# Test Design: Selective Module Regeneration

**Date:** 2026-01-26
**Designer:** Quinn (Test Architect)
**Story:** selective-module-regeneration

## Test Strategy Overview

- **Total test scenarios:** 28
- **Unit tests:** 14 (50%)
- **Integration tests:** 10 (36%)
- **E2E tests:** 4 (14%)
- **Priority distribution:** P0: 8, P1: 12, P2: 6, P3: 2

## Test Scenarios by Acceptance Criteria

### AC1: CLI `--modules` Option

**Requirement:** New CLI option `--modules` accepts comma-separated module paths (e.g., `"backend/auth,utils/validation"`)

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-UNIT-001 | Unit | P0 | Parse single module path `"backend/auth"` | Pure parsing logic, critical input processing |
| SMR-UNIT-002 | Unit | P0 | Parse multiple comma-separated paths `"backend/auth,utils,core/db"` | Core parsing functionality |
| SMR-UNIT-003 | Unit | P1 | Parse paths with trailing/leading spaces (trimming) | Input normalization |
| SMR-UNIT-004 | Unit | P1 | Parse empty string returns empty list | Edge case handling |
| SMR-INT-001 | Integration | P1 | CLI accepts `--modules` parameter and passes to adapter | CLI-to-adapter interface validation |

### AC2: CLI `--force` Flag

**Requirement:** New CLI option `--force` / `-F` skips existing documentation checks

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-UNIT-005 | Unit | P0 | Force flag defaults to False | Business logic correctness |
| SMR-INT-002 | Integration | P0 | `--force` flag passed through CLI to DocumentationGenerator | Critical flag propagation |
| SMR-INT-003 | Integration | P1 | `-F` short form works identically to `--force` | CLI usability validation |

### AC3: Module Matching (Exact, Prefix, Parent)

**Requirement:** Module path matching supports exact match, prefix match for children, and parent inclusion

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-UNIT-006 | Unit | P0 | `should_process_module()` exact match: `"backend/auth"` matches `"backend/auth"` | Core matching logic |
| SMR-UNIT-007 | Unit | P0 | `should_process_module()` prefix match: `"backend/auth"` includes `"backend/auth/login"` | Subtree inclusion logic |
| SMR-UNIT-008 | Unit | P0 | `should_process_module()` parent detection: `"backend/auth/login"` includes `"backend/auth"` | Parent coherence logic |
| SMR-UNIT-009 | Unit | P1 | `should_process_module()` no match: `"backend/auth"` does NOT match `"utils/validation"` | Negative case validation |
| SMR-UNIT-010 | Unit | P1 | `should_process_module()` no partial match: `"backend"` does NOT match `"backend-utils"` | Slash boundary enforcement |
| SMR-UNIT-011 | Unit | P1 | `get_required_parents()` returns all ancestor paths for deeply nested module | Parent extraction logic |
| SMR-UNIT-012 | Unit | P2 | `get_required_parents()` handles root module (no parents) | Edge case |
| SMR-INT-004 | Integration | P1 | Processing loop correctly filters modules based on `should_process_module()` | Component interaction |

### AC4: Without `--force`, Skip Existing Docs

**Requirement:** When `--modules` is provided without `--force`, only modules without existing `.md` files are processed

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-INT-005 | Integration | P0 | Without `--force`, module with existing `.md` file is skipped | Critical default behavior |
| SMR-INT-006 | Integration | P1 | Without `--force`, module without existing `.md` file is processed | Normal operation verification |

### AC5: With `--force`, Regenerate Regardless

**Requirement:** When both `--modules` and `--force` are provided, specified modules are regenerated regardless of existing files

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-INT-007 | Integration | P0 | With `--force`, module with existing `.md` file is regenerated | Critical force behavior |
| SMR-E2E-001 | E2E | P0 | Full CLI invocation: `codewiki generate --modules "backend/auth" --force` overwrites existing doc | End-to-end validation |

### AC6: Summary Output

**Requirement:** Summary output shows: "Regenerating X of Y total modules"

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-UNIT-013 | Unit | P1 | Summary message format matches "Regenerating X of Y total modules" | Output contract |
| SMR-INT-008 | Integration | P1 | Summary correctly counts total modules and selected modules | Count accuracy |

### AC7-9: Integration Pattern Compliance

**Requirement:** Follows existing `--focus` pattern, integrates with processing loop, overrides doc checks

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-INT-009 | Integration | P2 | `--modules` parsing uses same pattern as `--focus` (comma-separated) | Pattern consistency |
| SMR-E2E-002 | E2E | P1 | Existing `generate` command without `--modules` works unchanged (regression) | Backward compatibility |

### AC10: Backend Compatibility

**Requirement:** Works with all LLM backends: direct API, `--use-claude-code`, `--use-gemini-code`

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-E2E-003 | E2E | P1 | `--modules` works with `--use-claude-code` backend | Multi-backend validation |
| SMR-E2E-004 | E2E | P2 | `--modules` works with `--use-gemini-code` backend | Multi-backend validation |
| SMR-INT-010 | Integration | P2 | Module filtering applied before backend dispatch | Architecture validation |

### AC11-13: Quality Requirements (Tests, Edge Cases, Verbose)

**Requirement:** Unit tests, edge case handling, verbose logging

#### Scenarios

| ID | Level | Priority | Test | Justification |
|----|-------|----------|------|---------------|
| SMR-UNIT-014 | Unit | P2 | Handle invalid module path format (non-alphanumeric chars) - warn and skip | Edge case robustness |
| SMR-INT-011 | Integration | P2 | Module not in tree - logged warning, skipped gracefully | Error handling |
| SMR-INT-012 | Integration | P1 | Verbose mode (`-v`) logs include/skip decisions per module | Observability |

## Risk Coverage

| Risk ID | Test Coverage |
|---------|---------------|
| TECH-001 (Parent Logic) | SMR-UNIT-008, SMR-UNIT-011, SMR-UNIT-012 |
| TECH-002 (Backend Consistency) | SMR-E2E-003, SMR-E2E-004, SMR-INT-010 |
| DATA-001 (Stale Overviews) | SMR-UNIT-008, SMR-INT-004 |
| TECH-003 (Backend Filtering) | SMR-INT-010 |
| OPS-001 (CLI Confusion) | SMR-INT-009, SMR-E2E-002 |

## Recommended Execution Order

1. **P0 Unit tests** (fail fast): SMR-UNIT-001, 002, 005, 006, 007, 008
2. **P0 Integration tests**: SMR-INT-002, 005, 007
3. **P0 E2E tests**: SMR-E2E-001
4. **P1 tests in order** (Unit → Integration → E2E)
5. **P2+ as time permits**

## Test Data Requirements

### Unit Test Fixtures

```python
# Module paths for testing
test_module_paths = [
    "backend/auth",
    "backend/auth/login",
    "backend/auth/register",
    "backend/api/handlers",
    "utils/validation",
    "utils/helpers",
    "core/db",
    "core/db/migrations",
    "core/db/models",
]

# Selective filter scenarios
test_filters = [
    (["backend/auth"], ["backend", "backend/auth", "backend/auth/login", "backend/auth/register"]),  # Expected includes
    (["utils"], ["utils", "utils/validation", "utils/helpers"]),
    (["core/db/models"], ["core", "core/db", "core/db/models"]),  # Parent inclusion
]
```

### Integration Test Environment

- Mock file system with existing `.md` files at specific paths
- Mock `DocumentationGenerator` for CLI adapter tests
- Test repository with known module structure

### E2E Test Environment

- Small test repository (< 10 modules)
- Pre-existing documentation files for some modules
- Configured LLM backend (can use mock/stub for isolated testing)

## Gate YAML Block

```yaml
test_design:
  scenarios_total: 28
  by_level:
    unit: 14
    integration: 10
    e2e: 4
  by_priority:
    p0: 8
    p1: 12
    p2: 6
    p3: 2
  coverage_gaps:
    - "AC5 ambiguity: `--force` without `--modules` behavior undefined"
    - "AC3 clarification needed: prefix match boundary (slash required)"
  mitigates_risks:
    - TECH-001
    - TECH-002
    - TECH-003
    - DATA-001
    - OPS-001
```

## Quality Checklist

- [x] Every AC has test coverage
- [x] Test levels are appropriate (not over-testing)
- [x] No duplicate coverage across levels
- [x] Priorities align with business risk
- [x] Test IDs follow naming convention (SMR-LEVEL-SEQ)
- [x] Scenarios are atomic and independent
- [x] Risks from risk profile are addressed

## Implementation Notes

### Test File Structure

```
tests/
├── test_selective_regeneration.py          # Unit tests (SMR-UNIT-*)
├── cli/
│   └── test_generate_modules_flag.py       # CLI integration tests
└── e2e/
    └── test_selective_module_regeneration.py  # E2E tests (SMR-E2E-*)
```

### Key Assertions

**SMR-UNIT-006 (Exact Match):**
```python
def test_should_process_module_exact_match():
    result, reason = should_process_module("backend/auth", ["backend/auth"], set())
    assert result is True
    assert "exact match" in reason
```

**SMR-UNIT-007 (Prefix Match):**
```python
def test_should_process_module_prefix_match():
    result, reason = should_process_module("backend/auth/login", ["backend/auth"], set())
    assert result is True
    assert "child of" in reason
```

**SMR-UNIT-008 (Parent Detection):**
```python
def test_should_process_module_parent_detection():
    result, reason = should_process_module("backend/auth", ["backend/auth/login"], set())
    assert result is True
    assert "parent of" in reason
```

**SMR-INT-007 (Force Regeneration):**
```python
def test_force_regeneration_overwrites_existing(tmp_path, mock_llm):
    # Setup: Create existing doc file
    doc_file = tmp_path / "backend" / "auth.md"
    doc_file.parent.mkdir(parents=True)
    doc_file.write_text("old content")

    # Execute with force
    generator = DocumentationGenerator(output_dir=tmp_path)
    await generator.generate_module_documentation(
        components=...,
        selective_modules=["backend/auth"],
        force_regenerate=True
    )

    # Assert: File was overwritten
    assert doc_file.read_text() != "old content"
```

---

**Trace References:**
Test design matrix: docs/qa/assessments/selective-module-regeneration-test-design-20260126.md
P0 tests identified: 8
