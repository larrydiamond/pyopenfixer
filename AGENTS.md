# AGENTS.md — Instructions for AI Coding Agents

## Documentation Mandate

**This project must be HEAVILY documented.** Every feature, function, configuration option, API endpoint, and behavior change MUST be documented. Do not skip README updates. Do not assume code is self-explanatory. Add detailed docstrings to every function, include examples wherever possible, and maintain thorough README documentation. Every agent must prioritize documentation before or alongside any code changes.

## Project Context

**pyopenfixer** is a lightweight Python CLI tool / importable library that connects to a SonarQube server, discovers the main branch, and fetches all open violations (bugs, vulnerabilities, code smells) using the SonarQube Issues API. The violations are returned as a list of dictionaries for further processing.

## Tech Stack

- **Python 3.10+** (uses modern type hints like `list[dict]`)
- **requests** — the sole runtime dependency for HTTP calls
- **Standard library only** for everything else (json, pathlib, sys, typing)

## Core Files

| File                    | Purpose                                                                |
|-------------------------|------------------------------------------------------------------------|
| `sonar_violations.py`   | Main application — config loading, API calls, pagination, printing      |
| `config.json`            | User config with SonarQube URL, project key (gitignored)               |
| `config.json.example`   | Safe template for config (committed to repo)                            |
| `tests/`                 | Unit tests using pytest                                                 |
| `README.md`              | User-facing documentation                                              |

## Architecture

The application is organized into four public functions in `sonar_violations.py`:

1. **`load_config(config_path: str = "config.json") → dict`** — Loads and validates the JSON config file.
2. **`get_main_branch_name(session, base_url, project_key) → str`** — Queries `/api/meta` and falls back to `/api/measures/component` to discover the main branch.
3. **`fetch_violations(session, base_url, project_key, branch, page_size=500) → list[dict]`** — Paginates through `/api/issues/search` and returns all violations.
4. **`main() → list[dict]`** — Orchestrates the above and prints a summary. This is the entry point when run as `python sonar_violations.py`.

### Data Flow

```
config.json → load_config()
                        ↓
                session configured with Bearer token
                        ↓
                get_main_branch_name() → branch name
                        ↓
                fetch_violations() with pagination
                        ↓
                list[dict] of violations (returned to caller)
                        ↓
                (optional) printed summary in __main__ block
```

## Coding Conventions

- **Language**: Python 3.10+ (do not use `typing.List`, use `list[dict]`)
- **Docstrings**: Every public function must have a descriptive docstring
- **Style**: 4-space indentation, no comments unless the logic is non-obvious
- **No frameworks**: No Flask, FastAPI, Click, etc. — this is a simple script
- **Imports**: Standard library first, then third-party (`requests`)
- **Error handling**: Use explicit `try/except` in wrapper code; let API errors bubble up in core functions

## Documentation Requirements

### When making any changes:

1. **Update the README** — Describe what changed, any new config keys, new API endpoints, or altered behavior.
2. **No inline comments needed** — The code should be self-explanatory; only add comments for genuinely non-obvious logic.
3. **Keep config.json out of version control** — If you create a new config example, update `config.json.example`.

### README sections to keep current:

- The table of API endpoints (if you add new endpoints)
- The error handling table (if you add new error scenarios)
- The core files table (if you add/remove files)
- The data flow diagram (if the architecture changes)

## How to Add a Feature

Example pattern for adding a new capability (e.g., exporting to CSV):

1. Add the function in `sonar_violations.py`
2. Optionally add a CLI argument or keep it importable
3. Update the README to document the new feature
4. Do NOT modify `config.json` unless a new config key is needed

## Running the Project

```bash
pip install requests
python sonar_violations.py
```

## Testing

Run the full test suite with `pytest`:

```bash
pip install pytest
pytest -v
```

Run a specific test class:

```bash
pytest tests/test_sonar_violations.py::TestLoadConfig -v
```

Run with coverage report:

```bash
pip install pytest-cov
pytest --cov=sonar_violations --cov-report=term-missing
```

### Test Classes

| Class               | Coverage |
|---------------------|----------|
| `TestLoadConfig`         | Config loading, validation, missing files, invalid JSON |
| `TestGetCurrentBranch`   | Git branch detection via `git rev-parse`, error handling |
| `TestIsBranchMain`       | Branch name comparison, case sensitivity |
| `TestGetMainBranchName`  | API call, main branch extraction, fallback, HTTP errors |
| `TestFetchViolations`    | Pagination, single/multi-page results, empty list, params |
| `TestViolationSortKey`   | Type ordering, severity ordering, tiebreaker logic |
| `TestMain`               | Integration: token check, successful run, branch logic |

**Rule**: Every new function or behavior change MUST have corresponding tests.

## Common Tasks for Agents

| Task                         | What to do                                                                 |
|------------------------------|----------------------------------------------------------------------------|
| Bug fix                      | Find the error in `sonar_violations.py`, fix it, update README if behavior changes |
| New API feature              | Add a new function to `sonar_violations.py`, update README docs            |
| Config change                | Update `config.json.example` and document in README                         |
| Dependency update            | Update no requirements file (uses direct import); note in README changelog |
| Refactoring                  | Keep the four public API functions; update README if function signatures change |

## Remember

- This is a **simple, focused tool** — do not add unnecessary complexity
- Always document changes in the README
- Never commit real tokens to `config.json`
- The `__main__` block is for demonstration only; the real value is the importable functions
