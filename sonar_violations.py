import json
import os
import requests
import sys
from pathlib import Path
from typing import Optional


def load_config(config_path: str = "config.json") -> dict:
    """Load configuration from a JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)
    with open(path) as f:
        config = json.load(f)
    for key in ("sonarqube_url", "project_key"):
        if key not in config:
            print(f"Missing required config key: {key}")
            sys.exit(1)
    return config


def get_main_branch_name(session: requests.Session, base_url: str, project_key: str) -> str:
    """Discover the main branch name by querying the project_branches/list endpoint.

    Calls `GET /api/project_branches/list?project={project_key}` which returns
    an array of branch objects, each with an ``isMain`` boolean flag.  The
    branch where ``isMain`` is ``True`` is returned.  If no branch is
    flagged as main the function falls back to ``"main"``.
    """
    url = f"{base_url}/api/project_branches/list"
    resp = session.get(url, params={"project": project_key})
    resp.raise_for_status()
    data = resp.json()
    for branch in data.get("projectBranches", []):
        if branch.get("isMain"):
            return branch["name"]
    print("warning: no branch marked as main, defaulting to 'main'")
    return "main"


def fetch_violations(
    session: requests.Session,
    base_url: str,
    project_key: str,
    branch: str,
    page_size: int = 500
) -> list[dict]:
    """Fetch all violations/issues for the given project/branch using pagination."""
    url = f"{base_url}/api/issues/search"
    params = {
        "projectKeys": project_key,
        "branch": branch,
        "types": "BUG,VULNERABILITY,CODE_SMELL",
        "severity": "CRITICAL,MAJOR,MINOR,HIGH,MEDIUM,LOW",
        "statuses": "OPEN,CONFIRMED",
        "ps": page_size,
        "p": 1,
    }

    all_violations: list[dict] = []
    while True:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        all_violations.extend(issues)
        if len(all_violations) >= data.get("paging", {}).get("total", 0):
            break
        params["p"] += 1

    return all_violations


def main():
    config = load_config()
    base_url = config["sonarqube_url"].rstrip("/")
    project_key = config["project_key"]
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        print("Environment variable SONAR_TOKEN is not set.")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    main_branch = get_main_branch_name(session, base_url, project_key)
    print(f"discovered main branch: {main_branch}")

    violations = fetch_violations(session, base_url, project_key, main_branch)
    print(f"loaded {len(violations)} violations from {project_key} on branch '{main_branch}'")
    return violations


if __name__ == "__main__":
    violations = main()
    # examples of printing violation details
    for v in violations:
        print(
            f"  [{v.get('severity', '?')}] {v.get('type', '?')} - "
            f"{v.get('component', '')} ({v.get('rule', '')}) "
            f"at line {v.get('lines', ['?'])[0] if v.get('lines') else '?'}: "
            f"{v.get('message', '')[:80]}"
        )
