# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodeWiki is an AI-powered documentation generator for large-scale codebases. It uses hierarchical decomposition and recursive multi-agent processing to generate comprehensive repository-level documentation with visual artifacts (Mermaid diagrams).

Supported languages: Python, Java, JavaScript, TypeScript, C, C++, C#

## Common Commands

```bash
# Install in development mode
pip install -e .

# Run CLI tool
codewiki --version
codewiki config show
codewiki config validate
codewiki generate
codewiki generate --verbose --github-pages

# Run tests
pytest
pytest tests/test_specific.py
pytest --cov=codewiki

# Run web application (Docker)
docker-compose -f docker/docker-compose.yml up -d

# Run web application directly
python codewiki/run_web_app.py --host 0.0.0.0 --port 8000
```

## Architecture

### Core Pipeline

1. **Dependency Analysis** (`src/be/dependency_analyzer/`) - Tree-sitter based AST parsing that builds call graphs and dependency relationships across 7 languages
2. **Module Clustering** (`src/be/cluster_modules.py`) - Hierarchical decomposition using LLM-guided partitioning based on token limits (`MAX_TOKEN_PER_MODULE`)
3. **Agent Orchestration** (`src/be/agent_orchestrator.py`) - Recursive pydantic-ai agents that generate documentation with dynamic delegation for complex modules
4. **Documentation Generation** (`src/be/documentation_generator.py`) - Assembles final markdown output with cross-module references

### Key Components

**CLI Layer** (`codewiki/cli/`):
- `main.py` - Click-based CLI entry point
- `commands/config.py` - API configuration management
- `commands/generate.py` - Documentation generation command
- `config_manager.py` - Config storage (keyring for secrets, JSON for settings)

**Backend** (`codewiki/src/be/`):
- `agent_tools/` - Agent tools: `read_code_components`, `str_replace_editor`, `generate_sub_module_documentations`, `deps`
- `dependency_analyzer/analyzers/` - Language-specific analyzers (python.py, java.py, etc.)
- `llm_services.py` - LiteLLM-based LLM calls with fallback model support
- `prompt_template.py` - System prompts for complex vs leaf modules

**Frontend** (`codewiki/src/fe/`):
- FastAPI web application for GitHub URL-based generation
- `github_processor.py` - Repository cloning and processing
- `background_worker.py` - Async job processing

### Data Flow

Repository → AST Parser → Dependency Graph → Hierarchical Decomposition → Module Tree → Recursive Agent Processing → Documentation + Mermaid Diagrams

### Configuration

- API keys stored in system keyring
- Settings in `~/.codewiki/config.json`
- Environment variables: `MAIN_MODEL`, `CLUSTER_MODEL`, `FALLBACK_MODEL_1`, `LLM_BASE_URL`, `LLM_API_KEY`

## Adding Language Support

1. Create analyzer in `src/be/dependency_analyzer/analyzers/new_language.py` extending `BaseAnalyzer`
2. Register in `src/be/dependency_analyzer/ast_parser.py` LANGUAGE_ANALYZERS dict
3. Add file extensions to configuration

## Code Style

- Python 3.12+
- Line length: 100 (black/ruff)
- Type hints encouraged
- PEP 8 compliant
