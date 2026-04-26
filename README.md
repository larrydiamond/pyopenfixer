# pyopenfixer

A lightweight Python utility for retrieving SonarQube code quality violations (bugs, vulnerabilities, code smells) from any branch of a SonarQube project.

## Overview

`pyopenfixer` connects to your SonarQube server, discovers the main branch, and fetches all open/confirmed violations using the SonarQube Issues API with automatic pagination. The violations are returned as a list of dictionaries, making them easy to filter, transform, or export.

## Features

- **Automatic branch discovery** — Queries the SonarQube meta API to find the main branch instead of hardcoding a branch name
- **Full pagination support** — Handles projects with thousands of issues
- **Three issue types** — Fetches `BUG`, `VULNERABILITY`, and `CODE_SMELL` issues
- **Filterable results** — All fields from the SonarQube Issue object are preserved (severity, rule, line, message, status, assignee, etc.)
- **Importable** — The `main()` function returns violations as a list, so you can import it into other scripts
- **No external dependencies** — Only requires the standard `requests` library

## Installation

### Prerequisites

- Python 3.10+ (uses dictionary type hints with `list[dict]`)
- `requests` library
- `SONAR_TOKEN` environment variable set to your SonarQube user token with `read_issues` permission

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

| Field                | Description                                                               | Required |
|---------------------|--------------------------------------------------------------------------|----------|
| `sonarqube_url`     | Base URL of your SonarQube/SonarCloud instance (no trailing slash needed) | Yes       |
| `project_key`        | The exact project key as shown in SonarQube/SonarCloud (e.g., `org:project`) | Yes       |

### Setting Your SonarQube Token

The token is loaded from the `SONAR_TOKEN` environment variable — it is **not** stored in any file.

1. Log in to SonarQube / SonarCloud
2. Go to **My Account** → **Security**
3. Click **Generate Token**
4. Name it (e.g., `pyopenfixer`)
5. Leave scopes at default (read-only access to issues is enough)
6. Set the environment variable:
   ```bash
   export SONAR_TOKEN="sqp_a1b2c3d4e5f6g7h8i9j0"
   ```

On Windows:
   ```bash
   set SONAR_TOKEN=sqp_a1b2c3d4e5f6g7h8i9j0
   ```

In CI/CD pipelines, set `SONAR_TOKEN` as a secret environment variable in your pipeline settings.

## Usage

### Run as a script

```bash
python sonar_violations.py
```

Output:
```
discovered main branch: main
loaded 142 violations from my-company:my-project on branch 'main'
   [MAJOR] BUG - src/utils.py (python:S125) at line 42: Variable name "x" is too short
   [CRITICAL] VULNERABILITY - src/auth.py (python:S2009) at line 101: "os.system" is a security risk
   ...
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

| Field             | Example Value                        | Description                          |
|-------------------|---------------------------------------|--------------------------------------|
| `key`            | `"AAAABCDe12345"`                     | Unique issue ID                      |
| `rule`           | `"python:S125"`                       | SonarQube rule identifier            |
| `severity`       | `"MAJOR"`                             | Severity: `INFO`, `MINOR`, `MAJOR`, `CRITICAL`, `BLOCKER` |
| `type`           | `"BUG"`                               | Issue type: `BUG`, `VULNERABILITY`, `CODE_SMELL` |
| `message`        | `"Replace this use of 'eval'."`       | Rule description / violation message |
| `component`      | `"src/auth.py"`                       | Source file path                     |
| `lines`          | `["42", "43"]`                        | Lines affected (list)                |
| `status`         | `"OPEN"`                              | Issue status: `OPEN`, `CONFIRMED`, `REOPENED`, `CLOSED`, `ACCEPTED` |
| `assignee`       | `"jdoe"`                              | Assigned developer                   |
| `author`         | `"jdoe"`                              | Who created the issue                |
| `tags`           | `["cert", "cwe-79"]`                  | Rule tags (CWE, OWASP, etc.)         |
| `creationDate`   | `"2024-01-15T10:30:00+0000"`         | When the issue was created           |
| `updateDate`     | `"2024-03-20T14:00:00+0000"`         | When the issue was last updated      |
| `effort`         | `"30min"`                             | Suggested fix effort                 |
| `comments`       | `[...]`                               | List of comments on the issue        |
| `attachments`    | `[...]`                               | Attached screenshots/documents       |

See the [SonarQube Issues API docs](https://docs.sonarsource.com/sonarqube/latest/developer-guide/api-components/#issue) for the full schema.

## Project Structure

```
├── config.json.example    # Sample configuration (safe to commit)
├── config.json            # Your actual config (gitignored — contains your token)
├── sonar_violations.py    # Main application logic
├── .gitignore             # Prevents committing secrets
├── README.md              # This file
└── AGENTS.md              # Instructions for AI coding agents
```

## API Endpoints Used

| Endpoint                       | Purpose                          |
|--------------------------------|----------------------------------|
| `GET /api/meta`                | Discover main branch name        |
| `GET /api/measures/component`  | Fallback for branch resolution   |
| `GET /api/issues/search`      | Fetch paginated list of issues   |

## Error Handling

| Scenario                        | Behavior                                    |
|---------------------------------|---------------------------------------------|
| `config.json` missing            | Prints error, exits with code 1              |
| Missing config keys              | Prints which key is missing, exits 1         |
| `SONAR_TOKEN` not set            | Prints error, exits with code 1              |
| Invalid SonarQube URL            | `requests` raises `ConnectionError`          |
| Invalid token                    | SonarQube returns 401 — raises `HTTPError`   |
| Invalid project key              | SonarQube returns 404 — raises `HTTPError`   |
| Network timeout                  | `requests` raises `Timeout`                  |

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

## License

MIT
