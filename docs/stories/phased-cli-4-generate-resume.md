# Story: Add Resume Capability to `generate` Command

## Status

Ready for Review

## Story

**As a** developer using CodeWiki,
**I want** to resume a failed or interrupted `generate` run from a specific phase,
**so that** I don't have to re-run completed phases when troubleshooting or recovering from failures.

## Acceptance Criteria

1. `codewiki generate` continues to work exactly as before (no breaking changes)
2. Add `--resume-from {analyze|cluster|document}` flag to resume from a specific phase
3. When resuming from `cluster`: validates `dependency_graph.json` exists
4. When resuming from `document`: validates `first_module_tree.json` exists
5. Progress reporting shows phase boundaries clearly (e.g., "Phase 1/3: Analyzing...")
6. All existing flags continue to work with `--resume-from`
7. Clear error messages when resume prerequisites are not met
8. `--resume-from` is incompatible with `--file` (single file mode)

## Tasks / Subtasks

- [x] Add `--resume-from` option to generate command (AC: 2)
  - [x] Define Click option with choices: analyze, cluster, document
  - [x] Default to None (full run)
- [x] Implement resume validation (AC: 3, 4, 7)
  - [x] Check for required input files based on resume point
  - [x] Provide clear error if prerequisites missing
- [x] Implement phase skipping logic (AC: 2, 3, 4)
  - [x] When resuming from `cluster`: skip dependency analysis, load existing graph
  - [x] When resuming from `document`: skip analysis and clustering, load existing trees
- [x] Update progress reporting (AC: 5)
  - [x] Show "Phase X/Y" in progress output
  - [x] Show "Skipping Phase X (resuming)" when applicable
- [x] Validate flag combinations (AC: 6, 8)
  - [x] Ensure `--resume-from` works with all other flags
  - [x] Error if combined with `--file`
- [x] Write tests (AC: all)
  - [x] Test full generation still works
  - [x] Test resume from cluster phase
  - [x] Test resume from document phase
  - [x] Test error when prerequisites missing
  - [x] Test incompatibility with --file
- [x] Update CLI help text

## Dev Notes

**Relevant Source Files:**
- `codewiki/cli/commands/generate.py` - Main command to modify
- `codewiki/cli/adapters/doc_generator.py` - `_run_backend_generation()` method contains phases

**Key Implementation Details:**
- Phase detection points in `_run_backend_generation()`:
  - Lines 181-203: Stage 1 - Dependency Analysis
  - Lines 205-256: Stage 2 - Module Clustering
  - Lines 258-281: Stage 3 - Documentation Generation
- When resuming, need to load existing files instead of generating:
  - `dependency_graph.json` for resume from cluster
  - `first_module_tree.json` + `module_tree.json` for resume from document
- May need to refactor `_run_backend_generation()` to accept resume point parameter

**File Locations for Resume Validation:**
```python
# Resume from cluster requires:
dependency_graph_path = output_dir / "dependency_graph.json"

# Resume from document requires:
first_module_tree_path = output_dir / "first_module_tree.json"
module_tree_path = output_dir / "module_tree.json"
```

**Progress Phases (with resume):**
| Phase | Name | Skipped When Resuming From |
|-------|------|----------------------------|
| 1 | Dependency Analysis | cluster, document |
| 2 | Module Clustering | document |
| 3 | Documentation Generation | never |
| 4 | HTML Generation (optional) | never |
| 5 | Finalization | never |

## Testing

**Test File Location:** `tests/cli/test_generate_resume.py`

**Test Standards:**
- Use `click.testing.CliRunner` for CLI tests
- Create fixture that generates intermediate files for resume testing
- Mock LLM calls to avoid actual API usage

**Test Cases:**
1. Full generation without `--resume-from` (regression)
2. Resume from cluster with valid `dependency_graph.json`
3. Resume from document with valid module trees
4. Error when resuming from cluster without dependency graph
5. Error when resuming from document without module trees
6. Error when combining `--resume-from` with `--file`
7. Resume works with `--use-claude-code`
8. Resume works with `--modules --force`

## Definition of Done

- [x] `--resume-from` flag implemented
- [x] All acceptance criteria verified
- [x] Tests pass (new and existing)
- [x] CLI help text updated
- [x] No regressions in existing generate functionality

## Dev Agent Record

### Agent Model Used
Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References
None - implementation completed without issues

### Completion Notes
- Added `--resume-from` flag with choices: analyze, cluster, document
- Validation checks for required files based on resume point:
  - Resume from cluster: requires `dependency_graph.json`
  - Resume from document: requires `dependency_graph.json` and `first_module_tree.json`
- Phase skipping implemented in `_run_backend_generation()`:
  - Loads existing dependency graph when resuming
  - Loads existing module tree when resuming from document
- Progress reporting shows "Phase X/Y" labels
- Shows "(skipped - resuming)" for skipped phases in verbose mode
- Incompatibility with `--file` enforced with clear error message
- Full generation saves `dependency_graph.json` for future resume capability
- Added comprehensive test suite in `tests/cli/test_generate_resume.py` (15 tests)
- All 202 tests pass (15 new + 187 existing)

### File List
**New Files:**
- `tests/cli/test_generate_resume.py` - Test suite for --resume-from functionality

**Modified Files:**
- `codewiki/cli/commands/generate.py` - Added --resume-from option and validation
- `codewiki/cli/adapters/doc_generator.py` - Added phase skipping logic for resume

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Story created from epic | Sarah (PO Agent) |
| 2026-01-27 | 1.1 | Implementation complete - all tasks done | James (Dev Agent) |

## QA Results

### Review Date: 2026-01-27

### Reviewed By: Quinn (Test Architect)

### Code Quality Assessment

The resume functionality is well-integrated into the existing generate command without breaking changes. The implementation properly validates prerequisites based on the resume point and provides clear, actionable error messages when files are missing. The phase skipping logic in `_run_backend_generation()` is clean and maintains proper progress reporting.

### Refactoring Performed

No refactoring was necessary - the implementation is clean and backward compatible.

### Compliance Check

- Coding Standards: [check] Consistent with existing generate command style
- Project Structure: [check] Properly modifies generate.py and doc_generator.py
- Testing Strategy: [check] 15 tests covering resume validation, flag combinations, and error cases
- All ACs Met: [check] All 8 acceptance criteria verified

### Improvements Checklist

- [x] Full generation works unchanged (backward compatible)
- [x] --resume-from accepts analyze, cluster, document
- [x] Validates dependency_graph.json for cluster resume
- [x] Validates first_module_tree.json for document resume
- [x] Phase progress shows "Phase X/Y" labels
- [x] Skipped phases shown in verbose mode
- [x] --resume-from incompatible with --file (clear error)
- [x] Full generation saves dependency_graph.json for future resume
- [x] All existing flags work with --resume-from
- [ ] Consider auto-detecting last successful phase (future enhancement)

### Security Review

No security implications from resume functionality. File operations use existing validated paths.

### Performance Considerations

Resume capability significantly improves recovery time after failures or interruptions by skipping completed phases.

### Files Modified During Review

None - no modifications required.

### Gate Status

Gate: PASS -> docs/qa/gates/phased-cli-4-generate-resume.yml

### Recommended Status

[check] Ready for Done
