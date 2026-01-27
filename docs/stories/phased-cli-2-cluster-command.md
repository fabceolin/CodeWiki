# Story: Create `cluster` CLI Command

## Status

Ready for Review

## Story

**As a** developer using CodeWiki,
**I want** to run module clustering independently with `codewiki cluster`,
**so that** I can customize clustering parameters, review module organization before documentation, or re-cluster without re-analyzing.

## Acceptance Criteria

1. `codewiki cluster` command reads `dependency_graph.json` and clusters components into modules
2. Requires `--input` flag pointing to dependency graph file (or directory containing it)
3. Outputs `first_module_tree.json` and `module_tree.json` to output directory
4. Supports `--use-claude-code`, `--use-gemini-code` for LLM backend selection
5. Supports `--verbose`, `--output` flags
6. Returns exit code 0 on success, non-zero on failure
7. Works with API key OR CLI backend (same bypass logic as generate)
8. Validates input file exists and has correct schema before processing
9. Command help text (`--help`) is comprehensive

## Tasks / Subtasks

- [x] Create `codewiki/cli/commands/cluster.py` (AC: 1, 2, 3, 4, 5)
  - [x] Define Click command with options
  - [x] Implement `--input` flag for dependency graph path
  - [x] Implement `--output` flag for output directory
  - [x] Implement `--use-claude-code` and `--use-gemini-code` flags
  - [x] Implement `--verbose` flag
  - [x] Load and validate input JSON schema
  - [x] Call appropriate clustering function based on backend
  - [x] Save `first_module_tree.json` and `module_tree.json`
- [x] Implement configuration and validation (AC: 7, 8)
  - [x] Reuse API key bypass logic from generate.py
  - [x] Validate CLI binary availability when using CLI backends
  - [x] Validate input file schema
- [x] Register command in `codewiki/cli/main.py` (AC: 1)
  - [x] Import and add to CLI group
- [x] Implement error handling (AC: 6, 8)
  - [x] Handle missing input file
  - [x] Handle invalid input schema
  - [x] Handle LLM/CLI failures
- [x] Write tests (AC: all)
  - [x] Unit tests for command parsing
  - [x] Integration test with sample dependency graph
  - [x] Test CLI backend bypass logic
  - [x] Test error cases
- [x] Update CLI help text (AC: 9)

## Dev Notes

**Relevant Source Files:**
- `codewiki/cli/commands/generate.py` - Reference for CLI backend bypass logic (lines 270-344)
- `codewiki/cli/main.py` - CLI entry point
- `codewiki/src/be/cluster_modules.py` - `cluster_modules()` function
- `codewiki/src/be/claude_code_adapter.py` - `claude_code_cluster()` function
- `codewiki/src/be/gemini_code_adapter.py` - `gemini_code_cluster()` function
- `codewiki/cli/adapters/doc_generator.py` - Lines 231-246 show clustering invocation pattern

**Key Implementation Details:**
- Clustering requires: `leaf_nodes` list, `components` dict, and `Config` object
- For CLI backends, config only needs `max_token_per_module`, `max_depth`, etc.
- For direct API: needs `base_url`, `api_key`, `cluster_model`
- Output files are identical to what `generate` currently produces

**Input Schema (dependency_graph.json):**
```json
{
  "metadata": { ... },
  "components": { ... },
  "leaf_nodes": ["..."]
}
```

**Output Schema (first_module_tree.json):**
```json
{
  "module_name": {
    "components": ["comp1", "comp2"],
    "children": { ... }
  }
}
```

## Testing

**Test File Location:** `tests/cli/test_cluster_command.py`

**Test Standards:**
- Use `click.testing.CliRunner` for CLI tests
- Mock LLM calls to avoid actual API usage in tests
- Use pytest fixtures for sample dependency graph

**Test Cases:**
1. Basic execution with valid dependency graph
2. Custom output directory with `--output`
3. CLI backend bypass (no API key required)
4. Verbose mode output
5. Error handling for missing input file
6. Error handling for invalid input schema
7. CLI binary not found error

## Definition of Done

- [x] Command implemented and registered
- [x] All acceptance criteria verified
- [x] Tests pass (new and existing)
- [x] CLI help text complete
- [x] No regressions in existing commands

## Dev Agent Record

### Agent Model Used
Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References
None - implementation completed without issues

### Completion Notes
- Created `codewiki/cli/commands/cluster.py` with full CLI implementation
- Supports reading dependency graph from file path or directory
- Validates input JSON schema (requires 'components' dict and 'leaf_nodes' list)
- Supports all three backends: direct API, Claude Code CLI, Gemini CLI
- API key bypass logic implemented - CLI backends don't require API configuration
- Outputs both `first_module_tree.json` and `module_tree.json`
- Added comprehensive test suite in `tests/cli/test_cluster_command.py` (27 tests)
- All 168 tests pass (27 new + 141 existing)

### File List
**New Files:**
- `codewiki/cli/commands/cluster.py` - Main cluster command implementation
- `tests/cli/test_cluster_command.py` - Test suite for cluster command

**Modified Files:**
- `codewiki/cli/main.py` - Added cluster_command import and registration

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Story created from epic | Sarah (PO Agent) |
| 2026-01-27 | 1.1 | Implementation complete - all tasks done | James (Dev Agent) |

## QA Results

### Review Date: 2026-01-27

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

Excellent implementation with proper API key bypass logic for CLI backends. The schema validation function is well-isolated and testable. The command correctly handles the three backend options (API, Claude Code CLI, Gemini CLI) and provides graceful fallback when clustering returns empty results.

### Refactoring Performed

No refactoring was necessary - the implementation is clean and well-organized.

### Compliance Check

- Coding Standards: [check] Proper error handling, type hints, clear function names
- Project Structure: [check] Command properly placed and registered
- Testing Strategy: [check] 27 tests with good coverage including schema validation and CLI backend tests
- All ACs Met: [check] All 9 acceptance criteria verified

### Improvements Checklist

- [x] Input path accepts both file and directory
- [x] Schema validation with clear error messages
- [x] CLI backend mutual exclusivity check
- [x] CLI binary availability validation
- [x] Default output to same directory as input
- [x] Graceful handling of empty clustering results
- [ ] Consider adding timeout configuration for CLI backend calls (future enhancement)

### Security Review

API key bypass logic is correctly implemented - CLI backends handle their own authentication. No sensitive data exposure risks identified.

### Performance Considerations

The clustering operation performance depends on the chosen backend. All three backends are properly supported without performance regressions.

### Files Modified During Review

None - no modifications required.

### Gate Status

Gate: PASS -> docs/qa/gates/phased-cli-2-cluster-command.yml

### Recommended Status

[check] Ready for Done
