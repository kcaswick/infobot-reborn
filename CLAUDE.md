# CLAUDE.md: Guide for Infobot Reborn

## Build & Run Commands
- Install dependencies: `uv pip install -r requirements.txt`
- Create/update virtualenv: `uv venv`
- Install dev dependencies: `uv pip install -e ".[dev]"`
- Run locally: `python src/main.py`
- Run on Modal: `modal serve src/modal.py`
- Deploy to Modal: `modal deploy src/modal.py`
- Format code: `black src/ tests/`
- Lint code: `ruff check src/ tests/`
- Type check: `mypy src/ tests/`
- Run all tests: `pytest tests/`
- Run single test: `pytest tests/test_file.py::test_function -v`

## Code Style Guidelines
- **Architecture**: Modal-specific code only in modal.py; core logic should be hosting-agnostic
- **Formatting**: Black with 88 character line length
- **Imports**: Grouped by standard library, third-party, local; alphabetized within groups
- **Type Hints**: Use throughout; prefer explicit over implicit types
- **Naming**: 
  - Functions/variables: snake_case
  - Classes: PascalCase
  - Constants: UPPER_SNAKE_CASE
- **Error Handling**: Use explicit exception types; add context with `raise ... from`
- **Documentation**: Docstrings for all public functions/classes (Google style)
- **Testing**: Pytest with descriptive test names