import json
import os
import subprocess
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


def get_current_branch(repo_path: str = ".") -> str:
     """Return the name of the current git branch.

     Runs ``git rev-parse --abbrev-ref HEAD`` inside *repo\_path*.
     Falls back to ``"HEAD"`` when the command fails (e.g. not a git repo
     or detached HEAD).
     """
     try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD"
     except (subprocess.CalledProcessError, FileNotFoundError):
        print("warning: could not determine current git branch, defaulting to 'HEAD'")
        return "HEAD"


def is_branch_main(current_branch: str, main_branch: str) -> bool:
    """Return True if *current\_branch* matches the repository's main branch."""
    return current_branch == main_branch


def get_main_branch_name(session: requests.Session, base_url: str, project_key: str) -> str:
    """Discover the main branch name by querying the project\_branches/list endpoint.

     Calls ``GET /api/project\_branches/list?project={project\_key}`` which returns
     an array of branch objects, each with an ``isMain`` boolean flag.
     The branch where ``isMain`` is ``True`` is returned.
     Falls back to ``"main"`` if no branch is flagged as main.
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
) ->list[dict]:
    """Fetch all violations/issues for the given project/branch using pagination.

     Calls the SonarCloud/SonarQube Issues API endpoint:
     ``GET /api/issues/search?projectKeys={project_key}&branch={branch}...``
     with the standard query parameters ``projectKeys``, ``branch``,
     ``ps`` (page size), ``p`` (page number), and ``statuses``
     (``OPEN,CONFIRMED``).
      """
    url = f"{base_url}/api/issues/search"
    params = {
         "projectKeys": project_key,
         "branch": branch,
         "ps": page_size,
         "p": 1,
         "statuses": "OPEN,CONFIRMED",
         "types": "CODE_SMELL,BUG,VULNERABILITY",
    }

    all_violations: list[dict] = []
    while True:
        resp = session.get(url, params=params)
        # print (f"fetching violations: page {params} (total so far: {len(all_violations)} )")
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        # print (f"fetching violations: page {params} (total so far: {len(all_violations)} {issues})")
        all_violations.extend(issues)
        if len(all_violations) >= data.get("paging", {}).get("total", 0):
            break
        params["p"] += 1

    return all_violations


def _violation_sort_key(v: dict):
    """Return a sort key so violations are ordered:
     code smells → bugs → vulnerabilities,
     and within each type: minor → major → critical → blocker.
      """
    type_order = {"CODE_SMELL": 0, "BUG": 1, "VULNERABILITY": 2}
    severity_order = {"INFO": 0, "MINOR": 1, "MAJOR": 2, "CRITICAL": 3, "BLOCKER": 4}
    return (
        type_order.get(v.get("type"), 99),
        severity_order.get(v.get("severity"), 99),
        v.get("rule", ""),
        v.get("line", 0),
    )


def main():
    config = load_config()
    base_url = config["sonarqube_url"].rstrip("/")
    project_key = config["project_key"]
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        print("Environment variable SONAR_TOKEN is not set.")
        sys.exit(1)

    current_branch = get_current_branch()
    print(f"current git branch: {current_branch}")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    main_branch = get_main_branch_name(session, base_url, project_key)
    print(f"main branch: {main_branch}")

    branch_to_query = main_branch if is_branch_main(current_branch, main_branch) else current_branch

    violations = fetch_violations(session, base_url, project_key, branch_to_query)

    if is_branch_main(current_branch, main_branch):
        print(f"on main branch — {len(violations)} violations from {project_key} on branch '{branch_to_query}':")
        sorted_violations = sorted(violations, key=_violation_sort_key)
        for v in sorted_violations:
            print(
                f"   [{v.get('severity', '?')}] {v.get('type', '?')} - "
                f"{v.get('component', '')} ({v.get('rule', '')}) "
                f"at line {v.get('line', '?')}: "
                f"{v.get('message', '')[:80]}"
               )
    else:
        print(f"on branch '{current_branch}' (not '{main_branch}'), skipping violation output")

    return violations


if __name__ == "__main__":
    violations = main()
