# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_compiler.py

# Run a specific test
pytest tests/test_compiler.py::test_write_summary

# Run with verbose output
pytest -v
```

No linter or formatter is configured — `pyproject.toml` only defines pytest settings.

## Architecture

OpenKB is a CLI tool (`openkb`) that compiles documents into a wiki-style knowledge base using LLMs. The entry point is `openkb/cli.py` → `openkb.cli:cli` (Click group).

### Document Pipeline (add command)

```
src file
  ↓ converter.py: hash-check, copy to raw/, convert to Markdown
  ↓
  ├─ Short doc (< pageindex_threshold pages)
  │    └─ agent/compiler.py: compile_short_doc()
  │         Step 1: LLM → summary page
  │         Step 2: LLM → concepts plan (create/update/related)
  │         Step 3: concurrent async LLM calls → new/updated concept pages
  │         Step 4: code → backlinks, index.md update
  │
  └─ Long PDF (≥ pageindex_threshold pages, default 20)
       └─ indexer.py: PageIndex tree index
       └─ agent/compiler.py: compile_long_doc()
            (same Steps 2-4 as above, but uses PageIndex summary as input)
```

### Query/Chat Agents

`agent/query.py` and `agent/chat.py` both use the **OpenAI Agents SDK** (`openai-agents`) with LiteLLM as the model provider (model name prefixed with `litellm/`). The agent's tools are plain functions defined in `agent/tools.py` and decorated with `@function_tool` at agent build time — **not** at definition time — so they can be tested in isolation without the runtime.

The compiler (`compiler.py`) uses **LiteLLM directly** (not the Agents SDK) for its multi-step pipeline with prompt caching.

### Key Files

| File | Role |
|---|---|
| `cli.py` | Click commands; `add_single_file()` orchestrates the pipeline |
| `converter.py` | Hash dedup, file-to-markdown conversion (markitdown/pymupdf) |
| `indexer.py` | PageIndex integration for long PDFs |
| `agent/compiler.py` | LLM wiki compilation pipeline (summary → concepts → index) |
| `agent/query.py` | Q&A agent using Agents SDK + wiki tools |
| `agent/chat.py` | Interactive REPL chat with slash-command support |
| `agent/chat_session.py` | Session persistence under `.openkb/chats/` |
| `agent/linter.py` | LLM-based knowledge lint agent |
| `agent/tools.py` | Pure tool functions (no decorators) for wiki file I/O |
| `lint.py` | Structural (non-LLM) lint checks |
| `schema.py` | `AGENTS_MD` constant and `get_agents_md()` (reads `wiki/AGENTS.md` from disk) |
| `state.py` | `HashRegistry` — SHA-256 dedup via `.openkb/hashes.json` |
| `config.py` | `load_config()`, global config at `~/.config/openkb/global.yaml` |
| `images.py` | Image extraction from PDF and markitdown output |
| `tree_renderer.py` | PageIndex tree → Markdown rendering |

### KB Directory Structure at Runtime

```
<kb_dir>/
  .openkb/
    config.yaml       # model, language, pageindex_threshold
    hashes.json       # SHA-256 → {name, type} dedup registry
    chats/            # chat session JSON files
  raw/                # original source files (copied here on add)
  wiki/
    AGENTS.md         # LLM wiki schema (read at runtime, editable by user)
    index.md          # auto-maintained document/concept index
    log.md            # operations log
    sources/          # converted markdown + images
    summaries/        # per-document summary pages (with YAML frontmatter)
    concepts/         # cross-document synthesis pages (with YAML frontmatter)
    explorations/     # saved query results
    reports/          # lint reports
```

### YAML Frontmatter Conventions

- **Summary pages**: `doc_type: short|pageindex`, `full_text: sources/<name>.md|json`
- **Concept pages**: `sources: [<source_file>]`, `brief: <one-line description>`
- The `brief:` field is used by the compiler's concepts-plan step to build a compact listing of existing concepts sent to the LLM.

### LLM Integration

All LLM calls go through **LiteLLM** using the `provider/model` format (e.g., `anthropic/claude-sonnet-4-6`). OpenAI models can omit the prefix. The Agents SDK wraps LiteLLM by prefixing models with `litellm/`.

API keys are resolved in order: system env → KB-local `.env` → global `~/.config/openkb/.env`. The generic `LLM_API_KEY` is propagated to `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `GEMINI_API_KEY`.

### Testing

Tests use `pytest` with `pytest-asyncio`. Run tests via `uv`:

```bash
# Install dev dependencies
uv sync --extra dev

# Run all tests
uv run python -m pytest

# Run with verbose output
uv run python -m pytest -v
```

The `conftest.py` provides two fixtures:
- `kb_dir(tmp_path)` — full KB directory structure in a temp dir
- `sample_tree` — PageIndex tree dict for tree-rendering tests

Tests mock LLM calls directly rather than using a test double framework.

---

## Project Agents

Reusable sub-agents are defined in `.claude/agents/` and available via `/agents`:

| Agent | Model | Purpose |
|---|---|---|
| `test-runner` | haiku | Run `pytest` and report pass/fail. Use after any code change. |
| `batch-implementer` | sonnet | Implement phases of `OPTIMIZATION_PLAN.md` (parallelization + LLM token savings). |
| `compiler-expert` | sonnet | Debug/review `agent/compiler.py` — pipeline steps, prompt caching, concept management. |

### Batch Parallelization (OPTIMIZATION_PLAN.md)

`openkb add <folder>` now processes multiple documents in parallel using asyncio:

- **`openkb/batch_state.py`** — `BatchState` class: shared asyncio locks, in-memory concept_briefs cache, pending_hashes buffer, batch semaphore
- **`_read_concept_briefs_as_dict(wiki_dir)`** in `compiler.py` — reads all concept briefs once at batch start (eliminates O(N²) disk reads)
- **`add_single_file_async` / `_run_batch_async`** in `cli.py` — async batch loop; single-file path (`add_single_file`) unchanged for watcher compatibility
- **`batch_concurrency`** in `.openkb/config.yaml` — controls max parallel docs (default: 3)

All `compile_short_doc` / `compile_long_doc` / `_compile_concepts` accept `batch_state: BatchState | None = None`; `None` path is identical to pre-optimization behaviour.
