# Story: Create `analyze` CLI Command

## Status

Ready for Review

## Story

**As a** developer using CodeWiki,
**I want** to run dependency analysis independently with `codewiki analyze`,
**so that** I can inspect the dependency graph before clustering, debug analysis issues, or integrate with custom tooling.

## Acceptance Criteria

1. `codewiki analyze` command parses source files and builds dependency graph
2. Outputs `dependency_graph.json` to specified output directory (default: `./docs`)
3. Supports `--output`, `--include`, `--exclude`, `--focus`, `--verbose` flags (same as generate)
4. Returns exit code 0 on success, non-zero on failure
5. JSON output format is documented and stable
6. Error messages are clear when repository validation fails
7. Command help text (`--help`) is comprehensive

## Tasks / Subtasks

- [x] Create `codewiki/cli/commands/analyze.py` (AC: 1, 2, 3)
  - [x] Define Click command with options matching generate.py patterns
  - [x] Implement repository validation (reuse from generate.py)
  - [x] Implement configuration loading (no API key required for analyze)
  - [x] Call `DependencyGraphBuilder.build_dependency_graph()`
  - [x] Save output to `dependency_graph.json`
- [x] Register command in `codewiki/cli/main.py` (AC: 1)
  - [x] Import and add to CLI group
- [x] Define output JSON schema (AC: 5)
  - [x] Document schema: `{"components": {...}, "leaf_nodes": [...]}`
  - [x] Include metadata (timestamp, repo path, file count)
- [x] Implement error handling (AC: 4, 6)
  - [x] Handle invalid repository paths
  - [x] Handle permission errors
  - [x] Handle unsupported file types
- [x] Write tests (AC: all)
  - [x] Unit tests for command parsing
  - [x] Integration test with sample repository
  - [x] Test error cases
- [x] Update CLI help text (AC: 7)

## Dev Notes

**Relevant Source Files:**
- `codewiki/cli/commands/generate.py` - Reference for CLI patterns, validation logic
- `codewiki/cli/main.py` - CLI entry point where command is registered
- `codewiki/src/be/dependency_analyzer/__init__.py` - `DependencyGraphBuilder` class
- `codewiki/cli/utils/repo_validator.py` - Repository validation utilities

**Key Implementation Details:**
- `DependencyGraphBuilder` requires a `Config` object but only uses `repo_path`, `include_patterns`, `exclude_patterns`
- No API key or LLM configuration needed for this phase
- Output should preserve component structure from `build_dependency_graph()` return value

**Output JSON Schema:**
```json
{
  "metadata": {
    "generated_at": "ISO timestamp",
    "repo_path": "/path/to/repo",
    "total_components": 123,
    "total_leaf_nodes": 45
  },
  "components": {
    "component_id": {
      "name": "...",
      "type": "function|class|method",
      "file_path": "...",
      "source_code": "...",
      "depends_on": ["..."]
    }
  },
  "leaf_nodes": ["component_id_1", "component_id_2"]
}
```

## Testing

**Test File Location:** `tests/cli/test_analyze_command.py`

**Test Standards:**
- Use `click.testing.CliRunner` for CLI tests
- Mock filesystem operations where appropriate
- Use pytest fixtures for test repository setup

**Test Cases:**
1. Basic execution with valid repository
2. Custom output directory with `--output`
3. Include/exclude patterns filtering
4. Verbose mode output
5. Error handling for invalid paths
6. JSON output schema validation

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
- Created `codewiki/cli/commands/analyze.py` with full CLI implementation
- Registered command in `codewiki/cli/main.py`
- JSON output includes metadata (timestamp, repo_path, total_components, total_leaf_nodes), components dict, and leaf_nodes list
- Added comprehensive test suite in `tests/cli/test_analyze_command.py` (23 tests)
- Created sample repository fixture in `tests/fixtures/sample_repo/`
- All 141 tests pass (23 new + 118 existing)

### File List
**New Files:**
- `codewiki/cli/commands/analyze.py` - Main analyze command implementation
- `tests/cli/test_analyze_command.py` - Test suite for analyze command
- `tests/fixtures/sample_repo/main.py` - Sample repository fixture
- `tests/fixtures/sample_repo/utils/__init__.py` - Sample repository fixture
- `tests/fixtures/sample_repo/utils/helper.py` - Sample repository fixture

**Modified Files:**
- `codewiki/cli/main.py` - Added analyze_command import and registration

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Story created from epic | Sarah (PO Agent) |
| 2026-01-27 | 1.1 | Implementation complete - all tasks done | James (Dev Agent) |

## QA Results

### Review Date: 2026-01-27

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

The implementation is well-structured and follows established CLI patterns. The code properly separates concerns between CLI parsing, validation, and dependency analysis. Error handling is comprehensive with clear, actionable error messages. The JSON output schema is well-documented and includes useful metadata.

### Refactoring Performed

No refactoring was necessary - the implementation is clean and follows project conventions.

### Compliance Check

- Coding Standards: [check] Follows Python 3.12+ patterns, proper type hints
- Project Structure: [check] Command properly placed in `codewiki/cli/commands/`
- Testing Strategy: [check] 23 tests covering all acceptance criteria
- All ACs Met: [check] All 7 acceptance criteria verified

### Improvements Checklist

- [x] Proper exit codes (0 on success, non-zero on failure)
- [x] Comprehensive help text with examples
- [x] JSON schema documented with metadata
- [x] Error messages are clear and actionable
- [x] No API key required (design goal met)
- [ ] Consider adding progress indicator for large repositories (future enhancement)

### Security Review

No security concerns. The command performs read-only operations on the file system and does not require any API credentials.

### Performance Considerations

The dependency analysis performance is inherited from the existing `DependencyGraphBuilder`. No performance issues identified.

### Files Modified During Review

None - no modifications required.

### Gate Status

Gate: PASS -> docs/qa/gates/phased-cli-1-analyze-command.yml

### Recommended Status

[check] Ready for Done
