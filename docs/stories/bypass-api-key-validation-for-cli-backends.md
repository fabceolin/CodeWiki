# Story: Bypass API Key Validation for CLI Backend Modes

## Status

Ready for Review

## Story

**As a** user wanting to generate documentation using Claude Code or Gemini CLI,
**I want** to run `codewiki generate --use-claude-code` or `--use-gemini-code` without configuring an API key,
**so that** I can use the CLI backends which handle their own authentication instead of direct API calls.

## Story Context

**Existing System Integration:**

- Integrates with: `codewiki/cli/commands/generate.py` validation flow
- Technology: Python, Click CLI framework
- Follows pattern: Conditional validation similar to `--create-branch` git repository check
- Touch points: `generate_command()` function lines 266-311

**Root Cause Analysis:**

The current validation order in `generate_command()`:
1. Line 271-284: Loads and validates configuration including API key requirement
2. Line 299-326: Checks for Claude/Gemini CLI availability (AFTER API key validation fails)

When `--use-claude-code` or `--use-gemini-code` is set, the API key is not needed because:
- Claude Code CLI uses its own authentication mechanism
- Gemini CLI uses its own authentication mechanism
- Direct API calls (requiring the API key) are bypassed entirely

## Acceptance Criteria

**Functional Requirements:**

1. When `--use-claude-code` flag is provided, skip API key validation in `is_configured()` check
2. When `--use-gemini-code` flag is provided, skip API key validation in `is_configured()` check
3. When neither CLI flag is provided, maintain current behavior requiring API key configuration

**Integration Requirements:**

4. Existing direct API mode continues to require API key as before
5. `config_manager.load()` still called to get model settings (can use defaults if not configured)
6. CLI binary validation (`shutil.which("claude")` / `shutil.which("gemini")`) continues to work

**Quality Requirements:**

7. Change is covered by appropriate tests
8. No regression in existing API key validation for direct mode
9. Error messages remain clear when CLI binary is not found

## Technical Notes

- **Integration Approach:** Reorder validation logic to check CLI flags before `is_configured()` call, or make `is_configured()` conditional on backend mode
- **Existing Pattern Reference:** See lines 292-296 for mutual exclusivity validation pattern
- **Key Constraints:**
  - Must still load config for model names and other settings
  - `config_manager.load()` should not fail if config file doesn't exist when using CLI mode
  - May need to provide sensible defaults when config is missing in CLI mode

**Recommended Implementation:**

Option A (Minimal change - recommended):
```python
# Move CLI flag checks BEFORE is_configured() check
# Only require is_configured() when NOT using CLI backends
if not (use_claude_code or use_gemini_code):
    if not config_manager.is_configured():
        raise ConfigurationError(...)
```

Option B (More extensive):
- Add parameter to `is_configured()` to skip API key check
- Requires changes to `config_manager.py`

## Definition of Done

- [x] Functional requirements met
- [x] Integration requirements verified
- [x] Existing functionality regression tested
- [x] Code follows existing patterns and standards
- [x] Tests pass (existing and new)
- [x] Documentation updated if applicable

## Risk and Compatibility Check

**Minimal Risk Assessment:**

- **Primary Risk:** Users in CLI mode without any config file may encounter unexpected behavior for model settings
- **Mitigation:** Provide sensible defaults or skip model config when CLI backend handles it
- **Rollback:** Revert single file change in `generate.py`

**Compatibility Verification:**

- [x] No breaking changes to existing API mode
- [x] No database changes
- [x] UI changes follow existing design patterns (N/A - CLI only)
- [x] Performance impact is negligible

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - No debug issues encountered.

### Completion Notes

- Implemented Option A (minimal change) as recommended in Technical Notes
- Reordered validation logic to check CLI backend flags before configuration validation
- Added default Configuration creation for CLI backend mode when no config file exists
- All 118 tests pass (13 new + 105 existing)

### File List

| File | Action | Description |
|------|--------|-------------|
| `codewiki/cli/commands/generate.py` | Modified | Reordered validation to bypass API key check for CLI backends |
| `tests/cli/test_cli_backend_bypass_validation.py` | Created | 13 new tests covering CLI backend bypass validation |

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Initial draft | Sarah (PO Agent) |
| 2026-01-27 | 1.1 | Implementation complete | James (Dev Agent) |
