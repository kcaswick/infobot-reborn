# AGENTS.md: Guide for Infobot Reborn

## Build & Run Commands
- Create/update virtualenv: `uv venv`
- Install dependencies: `uv sync`
- Install with dev dependencies: `uv sync --group dev`
- Add new dependency: `uv add <package-name>`
- Add new dev dependency: `uv add --group dev <package-name>`
- Run locally: `python src/main.py`
- Deploy to Modal: `modal deploy src/modal.py`
- Register Discord commands: `modal run src/modal.py::register_commands`
- Format code: `black src/ tests/`
- Lint code: `ruff check src/ tests/`
- Type check: `mypy src/ tests/`
- Run all tests: `pytest tests/`
- Run single test: `pytest tests/test_file.py::test_function -v`
- Run with test coverage: `pytest --cov=src tests/`
- Generate coverage report: `pytest --cov=src --cov-report=html tests/`
- Scan dependencies for security vulnerabilities: `safety check`

## Local Development Prerequisites
- **Python 3.11+** (managed via `.python-version`)
- **uv** for dependency management
- **ollama** for local LLM inference (provides OpenAI-compatible endpoint)
  - Install: https://ollama.com
  - Pull a small model for dev: `ollama pull qwen3:1.7b`
  - The bot connects to ollama at `http://localhost:11434/v1` by default

## Human Setup Docs
- `README.md` is the canonical human-facing setup and deployment guide.
- Keep local Discord setup, environment-variable docs, and Modal deployment
  steps in `README.md`, not here.
- Add to `AGENTS.md` only when the note is specific to coding agents,
  automation, or repository coordination.

## Module Structure
```
src/infobot/              # Main package (importable as `infobot`)
  __init__.py             # Package root, __version__
  config.py               # Settings loaded from env vars
  db/                     # SQLite database layer (aiosqlite)
  kb/                     # Knowledge base — factoid CRUD
  nlu/                    # Question parser + intent detector
  formatter/              # Response formatting (<reply>, variables, etc.)
src/main.py               # CLI entry point
tests/                    # pytest test suite
```

## Code Style Guidelines
- **Architecture**: Modal-specific code only in modal.py; core logic should be hosting-agnostic
- **Formatting**: Black with 88 character line length
- **Imports**: Grouped by standard library, third-party, local; alphabetized within groups
- **Type Hints**: Use throughout; prefer explicit over implicit types
- **Modern Python Features**:
  - Use data classes (`@dataclass`) for data containers
  - Always use f-strings for string formatting
  - Leverage pattern matching (`match/case`) where appropriate
  - Use the walrus operator (`:=`) for assignment expressions
  - Prefer typed dictionaries and `TypedDict` over raw dicts
  - Use structural pattern matching for complex conditionals
- **Asynchronous Code**:
  - Use `asyncio` for asynchronous operations
  - Prefer `async/await` syntax over callbacks
  - Mark I/O-bound functions as `async`
  - Use `asyncio.gather` for parallel execution
  - Add proper exception handling in async code
- **Security**:
  - Scan dependencies regularly with `safety check`
  - Use semver ranges for dependencies (e.g., >=1.2.3,<2.0.0) to allow security patches
  - Review security advisories for dependencies
  - Use environment variables for sensitive values (never hardcode)
  - Validate all user inputs before processing
  - Follow OWASP guidelines for web applications
- **Testing**:
  - Write pytest tests with descriptive names
  - Follow a strict TDD/BDD approach: Red → Green → Refactor
  - Aim for high test coverage (>80%)
  - Use fixtures and parametrization 
  - Test both success and error cases
  - Mock external dependencies
  - **CRITICAL**: Tests must FAIL when the implementation is broken. Never write tests that pass with broken implementations.
  - **CRITICAL**: Tests are NOT documentation of current behavior - they verify CORRECT behavior.
  - **CRITICAL**: If implementation has bugs, tests must expect the CORRECT behavior, not document the buggy behavior.
  - **NEVER**: Write tests that pass when implementation is broken - this provides false confidence and hides real problems.
  - **NEVER**: Write mock-only tests that can't catch real implementation bugs - prefer testing actual logic or skip until real testing is possible.
- **Naming**: 
  - Functions/variables: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
- **Error Handling**: Use explicit exception types; add context with `raise ... from`
- **Documentation**: Docstrings for all public functions/classes (Google style)
- **Commit Messages**:
  - Format: `<type>(<scope>): <subject>` — subject line max 72 chars
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
  - Scopes: use the module or area being changed (e.g., `kb`, `nlu`, `discord`, `db`, `config`, `modal`)
  - Bead reference: append bead ID on its own line at the end (e.g., `bd-6lc`)
  - Body (optional): explain **why**, not what. Do not restate the diff in English. Keep it to 1-3 sentences if included.
  - Example:
    ```
    feat(kb): add factoid data model

    Factoids are the core knowledge unit inherited from the original
    Infobot — needed before any retrieval or NLU work can begin.

    bd-6lc
    ```

  **AI Agent Authorship**:
  - When commits are mostly or entirely AI-generated, include co-authorship credit in the commit message
  - Use the `Co-authored-by:` trailer format at the end of the commit message body
  - Standard formats (include specific model name and version when known with certainty **and do not guess**; if only the tool/family is known, use that name without a version):
    - GitHub Copilot (underlying model unknown): `Co-authored-by: GitHub Copilot <copilot@github.com>`
    - GitHub Copilot (underlying model and version known): `Co-authored-by: GitHub Copilot (ExampleModel Furious 9.9) <copilot@github.com>`
    - Claude: `Co-authored-by: Claude Haiku 4.5 <claude@anthropic.com>` or `Claude Sonnet 4 <claude@anthropic.com>` etc.
    - Gemini: `Co-authored-by: Gemini 2.0 Flash <gemini@google.com>` or appropriate version
    - Unknown tool/model: `Co-authored-by: AI Assistant <ai@example.com>` (if neither the tool nor model identity can be determined)
  - This maintains transparency about AI contributions and helps track AI-assisted development patterns
  - For pull requests with substantial AI involvement, consider adding an "AI Involvement" section explaining which tools contributed

  **⚠️ REMINDER: Every commit must follow the format above - concise first line (50-72 chars), bullets by importance, AI co-authorship**
- **Commit Granularity**: Commit in reasonable-sized pieces. Each commit should be one logical change — not a giant monolithic dump of an entire feature. For example, "add factoid data model" and "add factoid CRUD operations" are separate commits, not one. This makes review, bisection, and rollback practical.
- **Parallel Work**: When multiple beads are unblocked and can be worked on simultaneously, use `ntm` to spawn agents and assign beads to them. Single-bead work doesn't require ntm.

### Temporary Artifacts & Coordination
- Keep ephemeral scratch artifacts in `temp/` (preferred) or `/tmp/`.
- If another agent must read the artifact, use `temp/` (some agent/tool setups do not reliably read outside the project root).
- Use Agent Mail threads/bodies for cross-agent coordination notes and handoffs.
- Do not put temporary planning/checklist artifacts in `docs/`.
- Never stage or commit scratch artifacts from `temp/` or `/tmp/`.
- Keep canonical assignment/completion state in beads and GitHub PR comments.

### PR Review Thread Resolution
- AI agents may draft and post GitHub review-thread replies with evidence.
- AI agents must not mark GitHub review threads as resolved unless they are acting as the reviewer/thread author who raised the concern, or as the repo owner.
- Review-thread resolution belongs to the reviewer/thread author who raised the concern, or to the repo owner, regardless of whether that actor is human or AI.
- When a thread is addressed or deferred, agents should reply with evidence or the follow-up bead/issue and then leave the thread open for reviewer/repo-owner resolution.

<!-- br-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`/`bd`) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View ready issues (unblocked, not deferred)
br ready              # or: bd ready

# List and search
br list --status=open # All open issues
br show <id>          # Full issue details with dependencies
br search "keyword"   # Full-text search

# Create and update
br create --title="..." --description="..." --type=task --priority=2
br update <id> --status=in_progress
br close <id> --reason="Completed"
br close <id1> <id2>  # Close multiple issues at once

# Sync with git
br sync --flush-only  # Export DB to JSONL
br sync --status      # Check sync status
```

### Workflow Pattern

1. **Start**: Run `br ready` to find actionable work
2. **Claim**: Use `br update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `br close <id>`
5. **Sync**: Always run `br sync --flush-only` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
br sync --flush-only    # Export beads changes to JSONL
git commit -m "..."     # Commit everything
git push                # Push to remote
```

### Best Practices

- Check `br ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always sync before ending session

<!-- end-br-agent-instructions -->
