[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=coverage)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=bugs)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=larrydiamond_pyopenfixer&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=larrydiamond_pyopenfixer)

# pyopenfixer

A lightweight Python utility for retrieving <b>and fixing</b> SonarQube/SonarCloud code quality violations (bugs, vulnerabilities, code smells) from any branch.

## Overview

`pyopenfixer` connects to your SonarQube server, discovers the main branch, and fetches all open/confirmed violations using the SonarQube Issues API with automatic pagination. The violations are returned as a list of dictionaries, making them easy to filter, transform, or export.   You may also pass in a sonarqube rule (python:S1234) and pyopenfixer will use opencode to attempt to fix all the issues for that rule.

## Features

- **Automatic branch discovery** — Queries the SonarCloud Issues API to find the main branch instead of hardcoding a branch name
- **Full pagination support** — Handles projects with thousands of issues
- **Three issue types** — Fetches `BUG`, `VULNERABILITY`, and `CODE_SMELL` issues
- **Filterable results** — All fields from the SonarCloud Issue object are preserved (severity, rule, line, message, status, assignee, etc.)
- **Importable** — The `main()` function returns violations as a list, so you can import it into other scripts
- **No external dependencies** — Only requires the standard `requests` library
- **CI/CD integration** — Automatic SonarCloud analysis on every push and merge via GitHub Actions

## Installation

### Prerequisites

- Python 3.10+ (uses dictionary type hints with `list[dict]`)
- `requests` library
- `SONAR_TOKEN` environment variable set to your SonarCloud user token with `read_issues` permission
- You may need a free SonarCloud account (https://sonarcloud.io)

### Setup

```bash
pip install requests
```

### Configuration

Create (or edit) `config.json` at the project root:

```json
{
     "sonarqube_url": "https://sonarcloud.io",
     "project_key": "my-organization:my-project"
}
```

| Field              | Description                                                                        | Required |
|-------------------|----------------------------------------------------------------------------------|----------|
| `sonarqube_url`   | Base URL of your SonarCloud/SonarQube instance (no trailing slash needed)         | Yes      |
| `project_key`     | The exact project key as shown in SonarCloud/SonarQube (e.g., `org:project`)      | Yes      |

### Generating Your SonarCloud Token

The token is loaded from the `SONAR_TOKEN` environment variable — it is **not** stored in any file.

1. Log in to SonarCloud (https://sonarcloud.io)
2. Click your avatar —> **My Account** —> **Security**
3. Click **Generate Token**
4. Name it (e.g., `pyopenfixer`)
5. Leave scopes at default (read-only access to issues is enough)
6. Copy the token

### Setting the Environment Variable

Once you have your token, set the `SONAR_TOKEN` environment variable:

```bash
export SONAR_TOKEN="sqp_a1b2c3d4e5f6g7h8i9j0"
```

On Windows:

```bash
set SONAR_TOKEN=sqp_a1b2c3d4e5f6g7h8i9j0
```

In CI/CD pipelines, set `SONAR_TOKEN` as a secret environment variable in your pipeline settings.

### Configuring GitHub Actions for SonarCloud Analysis

The repository includes a GitHub Actions workflow (`.github/workflows/sonarcloud.yml`) that automatically analyzes the project in SonarCloud on every push and pull request. To enable it:

1. **Create a SonarCloud project** (if not already created) at https://sonarcloud.io/dashboard
2. Copy the **Project Key** and **Organisation Key**
3. Add them to your `config.json`
4. Navigate to your repository on GitHub.com
5. Go to **Settings** —> **Secrets and variables** —> **Actions**
6. Click **New repository secret**
7. Name the secret `SONAR_TOKEN` and paste the token you generated above
8. Commit your changes

The workflow will trigger on:
- **`push`** to branches `main`, `master`, or `develop`
- **`pull_request`** of any type (`opened`, `synchronize`, `reopened`)

Each workflow run will:
1. Checkout the repository with full history
2. Set up Python 3.10
3. Install dependencies
4. Run the test suite
5. Trigger a SonarCloud scan using the official `SonarSource/sonarcloud-github-action@v3`

No additional configuration is required.

## Usage

### Run as a script

```bash
python sonar_violations.py
```

### Fix a specific rule automatically

Pass a SonarQube rule as the first argument to filter violations to that rule and automatically run `opencode run` on each matching violation:

```bash
python sonar_violations.py java:S1858
```

This will:
1. Fetch all violations from the project and branch
2. Filter to only violations with `rule == "java:S1858"`
3. For each matching violation, run:
   ```bash
   opencode run "fix the problem {message} in {component} on line {line}"
   ```

The `opencode` command receives a prompt built from the violation's `message`, `component`, and `line` fields, allowing AI to automatically remediate the issue.

### Fix with a different rule

```bash
python sonar_violations.py python:S301
```

Output:
```
current git branch: main
main branch: main
on main branch - 142 violations from my-company:my-project on branch 'main':
    [MAJOR] BUG - src/utils.py (python:S125) at line 42: Variable name "x" is too short
    [CRITICAL] VULNERABILITY - src/auth.py (python:S2009) at line 101: "os.system" is a security risk
    ...

Violation summary by severity:
    BLOCKER: 3
    CRITICAL: 5
    MAJOR: 12
    MINOR: 47
    INFO: 75

Total violations on 'main': 142
MAJOR violations: 12

Thank you for pushing PyOpenFixer 1.0
```

### Import as a module

```python
from sonar_violations import main

violations = main()

# Filter by severity
critical = [v for v in violations if v.get("severity") == "CRITICAL"]

# Filter by type
vulnerabilities = [v for v in violations if v.get("type") == "VULNERABILITY"]

# Export to CSV or JSON
import json
with open("violations.json", "w") as f:
    json.dump(violations, f, indent=2)
```

### Programmatic usage without loading config

```python
from sonar_violations import fetch_violations, get_main_branch_name
import os
import requests

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {os.environ['SONAR_TOKEN']}"})

branch = get_main_branch_name(session, "https://sonarcloud.io", "my-key")
violations = fetch_violations(session, "https://sonarcloud.io", "my-key", branch)
```

## What's Included

The violations list contains one dictionary per SonarQube issue. Each dictionary includes all fields from the SonarQube API response, such as:

| Field             | Example Value                        | Description                           |
|-----------------|--------------------------------------|--------------------------------------|
| `key`           | `"AAAABCDe12345"`                     | Unique issue ID                        |
| `rule`          | `"python:S125"`                       | SonarQube rule identifier              |
| `severity`      | `"MAJOR"`                             | Severity: `INFO`, `MINOR`, `MAJOR`, `CRITICAL`, `BLOCKER` |
| `type`          | `"BUG"`                               | Issue type: `BUG`, `VULNERABILITY`, `CODE_SMELL` |
| `message`       | `"Replace this use of 'eval'."`       | Rule description / violation message   |
| `component`     | `"src/auth.py"`                       | Source file path                       |
| `line`          | `47`                                  | Line number where issue is detected    |
| `status`        | `"OPEN"`                              | Issue status: `OPEN`, `CONFIRMED`, `REOPENED`, `CLOSED`, `ACCEPTED` |
| `assignee`      | `"jdoe"`                              | Assigned developer                     |
| `author`        | `"jdoe"`                              | Who created the issue                  |
| `tags`          | `["cert", "cwe-79"]`                  | Rule tags (CWE, OWASP, etc.)           |
| `creationDate`  | `"2024-01-15T10:30:00+0000"`         | When the issue was created             |
| `updateDate`    | `"2024-03-20T14:00:00+0000"`         | When the issue was last updated        |
| `effort`        | `"30min"`                             | Suggested fix effort                   |
| `comments`      | `[...]`                               | List of comments on the issue          |
| `attachments`   | `[...]`                               | Attached screenshots/documents         |

See the [SonarQube Issues API docs](https://docs.sonarsource.com/sonarqube/latest/developer-guide/api-components/#issue) for the full schema.

## Project Structure

```
├── .github/workflows/sonarcloud.yml   # GitHub Actions CI/CD
├── config.json.example                # Sample configuration (safe to commit)
├── config.json                        # Your actual config (gitignored — contains your token)
├── sonar_violations.py                # Main application logic
├── tests/                             # Unit tests (pytest)
│     └── test_sonar_violations.py
├── .gitignore                          # Prevents committing secrets
├── README.md                           # This file
└── AGENTS.md                           # Instructions for AI coding agents
```

## Testing

Tests are written using `pytest` and can be run from the project root:

```bash
pip install pytest
pytest
```

To run with verbose output:

```bash
pytest -v
```

To run a specific test class or file:

```bash
pytest tests/test_sonar_violations.py -v
```

To run a specific test method:

```bash
pytest tests/test_sonar_violations.py::TestLoadConfig::test_loads_valid_config -v
```

To see coverage:

```bash
pip install pytest-cov
pytest --cov=sonar_violations --cov-report=term-missing
```

The test suite covers:
- **`TestLoadConfig`** (6 tests) — valid config, default path, missing file, missing keys, invalid JSON
- **`TestGetCurrentBranch`** (5 tests) — normal branch, empty output, CalledProcessError, FileNotFoundError, custom cwd
- **`TestIsBranchMain`** (3 tests) — matching branches, non-matching, case sensitivity
- **`TestGetMainBranchName`** (3 tests) — returns main branch, fallback to "main", HTTP errors
- **`TestFetchViolations`** (5 tests) — single page, multi-page pagination, empty list, correct params, HTTP errors
- **`TestViolationSortKey`** (6 tests) — type ordering, severity ordering, unknown types/severities, rule/line tiebreakers
- **`TestMain`** (3 tests) — missing token, successful run, skipping output on non-main branch

## API Endpoints Used

| Endpoint                                | Purpose                            |
|----------------------------------------|-----------------------------------|
| `GET /api/project_branches/list`        | Discover main branch name           |
| `GET /api/issues/search`                | Fetch paginated list of issues      |

## Error Handling

| Scenario                        | Behavior                                       |
|--------------------------------|------------------------------------------------|
| `config.json` missing           | Prints error, exits with code 1                 |
| Missing config keys             | Prints which key is missing, exits 1            |
| `SONAR_TOKEN` not set           | Prints error, exits with code 1                 |
| Invalid SonarQube URL           | `requests` raises `ConnectionError`             |
| Invalid token                   | SonarQube returns 401 — raises `HTTPError`      |
| Invalid project key             | SonarQube returns 404 — raises `HTTPError`      |
| Network timeout                 | `requests` raises `Timeout`                     |

You can wrap `main()` in a `try/except` if you want graceful handling:

```python
try:
    violations = main()
except requests.exceptions.HTTPError as e:
    print(f"SonarQube error: {e}")
except requests.exceptions.ConnectionError:
    print("Could not connect to SonarQube. Check the URL in config.json.")
except json.JSONDecodeError:
    print("config.json is not valid JSON.")
```

## GitHub Actions Workflow

The included `.github/workflows/sonarcloud.yml` workflow automatically analyzes your project with SonarCloud on every push and pull request. It will:

1. **Checkout** the repository with full history (`fetch-depth: 0`)
2. **Set up** Python 3.10
3. **Install** dependencies (`requests`, `pytest`)
4. **Run** the full test suite before analysis
5. **Trigger** a SonarCloud scan using `SonarSource/sonarcloud-github-action@v3`

This ensures code quality is assessed on every merge, preventing regressions from being merged into your main branch.

