# Story: Create `document` CLI Command

## Status

Ready for Review

## Story

**As a** developer using CodeWiki,
**I want** to run documentation generation independently with `codewiki document`,
**so that** I can regenerate docs without re-clustering, use custom module trees, or integrate documentation into CI/CD pipelines.

## Acceptance Criteria

1. `codewiki document` command reads module tree and generates documentation
2. Requires `--input` flag pointing to directory containing `first_module_tree.json`
3. Generates `*.md` files for all modules plus `overview.md`
4. Supports `--modules`, `--force` for selective regeneration (same as generate)
5. Supports `--use-claude-code`, `--use-gemini-code` for LLM backend selection
6. Supports `--verbose`, `--output` flags
7. Optionally accepts `--github-pages` to generate HTML viewer
8. Returns exit code 0 on success, non-zero on failure
9. Works with API key OR CLI backend (same bypass logic as generate)
10. Validates input files exist and have correct schema before processing
11. Requires access to source repository (via `--repo` flag or current directory)

## Tasks / Subtasks

- [x] Create `codewiki/cli/commands/document.py` (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] Define Click command with options
  - [x] Implement `--input` flag for module tree directory
  - [x] Implement `--repo` flag for source repository path (default: cwd)
  - [x] Implement `--output` flag for documentation output directory
  - [x] Implement `--modules` and `--force` flags for selective regeneration
  - [x] Implement `--use-claude-code` and `--use-gemini-code` flags
  - [x] Implement `--verbose` and `--github-pages` flags
  - [x] Load and validate module tree JSON
  - [x] Load dependency graph for component access
  - [x] Call `DocumentationGenerator.generate_module_documentation()`
  - [x] Optionally run HTML generation
- [x] Implement configuration and validation (AC: 9, 10, 11)
  - [x] Reuse API key bypass logic from generate.py
  - [x] Validate CLI binary availability when using CLI backends
  - [x] Validate input file schemas
  - [x] Validate repository path
- [x] Register command in `codewiki/cli/main.py` (AC: 1)
  - [x] Import and add to CLI group
- [x] Implement error handling (AC: 8, 10)
  - [x] Handle missing input files
  - [x] Handle invalid input schemas
  - [x] Handle missing repository
  - [x] Handle LLM/CLI failures
- [x] Write tests (AC: all)
  - [x] Unit tests for command parsing
  - [x] Integration test with sample module tree
  - [x] Test selective regeneration (--modules, --force)
  - [x] Test CLI backend bypass logic
  - [x] Test error cases
- [x] Update CLI help text

## Dev Notes

**Relevant Source Files:**
- `codewiki/cli/commands/generate.py` - Reference for CLI patterns, selective regeneration
- `codewiki/cli/adapters/doc_generator.py` - Lines 258-281 show documentation generation invocation
- `codewiki/src/be/documentation_generator.py` - `DocumentationGenerator` class
- `codewiki/cli/html_generator.py` - HTML generation for `--github-pages`

**Key Implementation Details:**
- Documentation generation requires: `components`, `leaf_nodes`, and `Config` object
- Must load `dependency_graph.json` to get components (or rebuild from repo)
- `first_module_tree.json` defines processing order
- `module_tree.json` is updated during generation
- Selective regeneration uses `should_process_module()` function

**Input Files Required:**
- `first_module_tree.json` - Module tree structure
- `dependency_graph.json` - Component data (or access to source repo)

**Output Files:**
- `*.md` - One markdown file per module
- `overview.md` - Repository overview
- `metadata.json` - Generation metadata
- `index.html` - (optional) HTML viewer

**Design Decision:**
If `dependency_graph.json` is not present, the command should either:
- A) Require it and fail with clear error
- B) Rebuild it automatically from `--repo` path

Recommendation: Option A for phase separation purity; Option B for convenience.

## Testing

**Test File Location:** `tests/cli/test_document_command.py`

**Test Standards:**
- Use `click.testing.CliRunner` for CLI tests
- Mock LLM calls to avoid actual API usage in tests
- Use pytest fixtures for sample module tree and components

**Test Cases:**
1. Basic execution with valid module tree
2. Custom output directory with `--output`
3. Selective regeneration with `--modules`
4. Force regeneration with `--modules --force`
5. CLI backend bypass (no API key required)
6. HTML generation with `--github-pages`
7. Verbose mode output
8. Error handling for missing input files
9. Error handling for missing repository

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
- Created `codewiki/cli/commands/document.py` with full CLI implementation
- Requires input directory with both `first_module_tree.json` and `dependency_graph.json`
- Supports all three backends: direct API, Claude Code CLI, Gemini CLI
- Implements selective regeneration with `--modules` and `--force` flags
- Supports `--github-pages` for HTML viewer generation
- Validates repository path (defaults to current directory)
- Design decision: Requires `dependency_graph.json` (Option A - phase separation purity)
- Added comprehensive test suite in `tests/cli/test_document_command.py` (19 tests)
- All 187 tests pass (19 new + 168 existing)

### File List
**New Files:**
- `codewiki/cli/commands/document.py` - Main document command implementation
- `tests/cli/test_document_command.py` - Test suite for document command

**Modified Files:**
- `codewiki/cli/main.py` - Added document_command import and registration

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Story created from epic | Sarah (PO Agent) |
| 2026-01-27 | 1.1 | Implementation complete - all tasks done | James (Dev Agent) |

## QA Results

### Review Date: 2026-01-27

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

Well-designed implementation that maintains phase separation purity (Option A design decision). The command properly validates all required input files before processing and provides clear error messages. Selective regeneration with `--modules` and `--force` is correctly implemented with appropriate warnings.

### Refactoring Performed

No refactoring was necessary - the implementation follows established patterns.

### Compliance Check

- Coding Standards: [check] Consistent with project style, proper async handling
- Project Structure: [check] Command properly placed and registered
- Testing Strategy: [check] 19 tests covering input validation, backend selection, and selective regeneration
- All ACs Met: [check] All 11 acceptance criteria verified

### Improvements Checklist

- [x] Requires directory as input (not file)
- [x] Validates both first_module_tree.json and dependency_graph.json
- [x] Repository path defaults to current directory
- [x] Selective regeneration with --modules
- [x] Warning when --force used without --modules
- [x] GitHub Pages HTML generation support
- [x] Proper module tree schema validation
- [ ] Consider adding dry-run mode to preview which modules would be regenerated (future enhancement)

### Security Review

API key bypass logic properly implemented for CLI backends. Repository path validation prevents path traversal issues.

### Performance Considerations

Selective regeneration feature significantly reduces processing time when only specific modules need updates.

### Files Modified During Review

None - no modifications required.

### Gate Status

Gate: PASS -> docs/qa/gates/phased-cli-3-document-command.yml

### Recommended Status

[check] Ready for Done
