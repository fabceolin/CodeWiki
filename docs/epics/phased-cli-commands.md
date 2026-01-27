# Epic: Phased CLI Commands - Brownfield Enhancement

## Epic Goal

Enable users to run individual documentation generation phases (`analyze`, `cluster`, `document`) as separate CLI commands, allowing fine-grained control over the pipeline while maintaining the existing `generate` command for end-to-end execution.

## Epic Description

**Existing System Context:**

- Current functionality: `codewiki generate` runs a monolithic 5-stage pipeline (dependency analysis → clustering → documentation → HTML → finalization)
- Technology stack: Python 3.12+, Click CLI framework, async/await, LLM backends (direct API, Claude Code CLI, Gemini CLI)
- Integration points: `CLIDocumentationGenerator` adapter wraps `DocumentationGenerator` backend; intermediate data stored in `first_module_tree.json`, `module_tree.json`, `dependency_graph.json`

**Enhancement Details:**

- What's being added: Three new CLI commands (`analyze`, `cluster`, `document`) that expose pipeline phases independently
- How it integrates: Each command wraps existing backend methods; uses same intermediate file formats for data exchange
- Success criteria:
  1. Users can run `codewiki analyze` → `codewiki cluster` → `codewiki document` sequentially
  2. Intermediate outputs are compatible with subsequent phases
  3. `codewiki generate` continues to work unchanged
  4. Users can resume from any phase using prior outputs

**Pipeline Phase Mapping:**

| Phase | New Command | Input | Output |
|-------|-------------|-------|--------|
| 1. Dependency Analysis | `codewiki analyze` | Source code | `dependency_graph.json` |
| 2. Module Clustering | `codewiki cluster` | `dependency_graph.json` | `first_module_tree.json` |
| 3. Documentation Gen | `codewiki document` | Module tree + source | `*.md` files |
| 4. HTML Generation | (existing `--github-pages`) | `*.md` files | `index.html` |

## Stories

### Story 1: Create `analyze` Command

**Goal:** Extract dependency analysis phase into standalone `codewiki analyze` command.

**Acceptance Criteria:**
1. `codewiki analyze` command parses source files and builds dependency graph
2. Outputs `dependency_graph.json` to specified output directory (default: `./docs`)
3. Supports `--output`, `--include`, `--exclude`, `--focus`, `--verbose` flags (same as generate)
4. Returns exit code 0 on success, non-zero on failure
5. JSON output format is documented and stable

**Technical Notes:**
- Wrap `DependencyGraphBuilder.build_dependency_graph()` from `codewiki/src/be/dependency_analyzer/__init__.py`
- Output format: `{"components": {...}, "leaf_nodes": [...]}`
- Reuse validation logic from `generate.py` (repository validation, config loading)

---

### Story 2: Create `cluster` Command

**Goal:** Extract module clustering phase into standalone `codewiki cluster` command.

**Acceptance Criteria:**
1. `codewiki cluster` command reads `dependency_graph.json` and clusters components into modules
2. Requires `--input` flag pointing to dependency graph file
3. Outputs `first_module_tree.json` and `module_tree.json` to output directory
4. Supports `--use-claude-code`, `--use-gemini-code` for LLM backend selection
5. Supports `--verbose`, `--output` flags
6. Returns exit code 0 on success, non-zero on failure
7. Works with API key OR CLI backend (same bypass logic as generate)

**Technical Notes:**
- Wrap `cluster_modules()` from `codewiki/src/be/cluster_modules.py`
- Also supports Claude/Gemini CLI adapters for clustering
- Validate input file exists and has correct schema

---

### Story 3: Create `document` Command

**Goal:** Extract documentation generation phase into standalone `codewiki document` command.

**Acceptance Criteria:**
1. `codewiki document` command reads module tree and generates documentation
2. Requires `--input` flag pointing to module tree directory (containing `first_module_tree.json`)
3. Generates `*.md` files for all modules plus `overview.md`
4. Supports `--modules`, `--force` for selective regeneration
5. Supports `--use-claude-code`, `--use-gemini-code` for LLM backend selection
6. Supports `--verbose`, `--output` flags
7. Optionally accepts `--github-pages` to generate HTML viewer
8. Returns exit code 0 on success, non-zero on failure

**Technical Notes:**
- Wrap `DocumentationGenerator.generate_module_documentation()` from `codewiki/src/be/documentation_generator.py`
- Reuse selective regeneration logic from existing implementation
- Needs access to source code for component reading (use repo path from config or flag)

---

### Story 4: Refactor `generate` Command for Phase Orchestration

**Goal:** Optionally refactor `generate` to use new phase commands internally and add resume capability.

**Acceptance Criteria:**
1. `codewiki generate` continues to work exactly as before (no breaking changes)
2. Add `--resume-from {analyze|cluster|document}` flag to resume from a specific phase
3. When resuming, validate required input files exist
4. Progress reporting shows phase boundaries clearly
5. All existing flags continue to work

**Technical Notes:**
- This story is optional - can be deferred if direct implementation is simpler
- Consider whether to refactor internally or keep as separate orchestration

## Compatibility Requirements

- [x] Existing `generate` command API unchanged
- [x] No database schema changes (file-based only)
- [x] CLI UX follows existing patterns (`--output`, `--verbose`, etc.)
- [x] Performance: No additional overhead when using `generate` directly

## Risk Mitigation

- **Primary Risk:** Intermediate file format changes could break compatibility between phases
- **Mitigation:** Document and version the JSON schemas; validate on input
- **Rollback Plan:** New commands are additive; remove command files to rollback

## Dependencies Between Stories

```
Story 1 (analyze) ──┐
                    ├──▶ Story 4 (refactor generate) [optional]
Story 2 (cluster) ──┤
                    │
Story 3 (document) ─┘
```

Stories 1-3 can be developed in parallel. Story 4 depends on all three.

## Definition of Done

- [ ] All stories completed with acceptance criteria met
- [ ] Existing `generate` functionality verified through regression tests
- [ ] New commands have unit and integration tests
- [ ] CLI help text is clear and consistent
- [ ] No regression in existing features

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-01-27 | 1.0 | Epic created | Sarah (PO Agent) |
