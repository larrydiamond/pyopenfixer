import json
import os
import subprocess
import urllib.parse
import requests
import sys
from pathlib import Path
from typing import Optional


def _urlencode_value(value: str) -> str:
    """Percent-encode a string value for use as a SonarQube API query parameter.

    Uses ``urllib.parse.quote`` with ``safe=""`` so all special characters
    (including ``-`` and ``.`` which are normally left unencoded) are URL-encoded.
    """
    return urllib.parse.quote(value, safe="")


def load_config(config_path: str = "config.json") -> dict:
    """Load configuration from a JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print("config.json is not valid JSON")
        sys.exit(1)
    for key in ("sonarqube_url", "project_key"):
        if key not in config:
            print(f"Missing required config key: {key}")
            sys.exit(1)
    return config


def get_current_branch(repo_path: str = ".") -> str:
    """Return the name of the current git branch.

    Runs ``git rev-parse --abbrev-ref HEAD`` inside *repo_path*.
    Falls back to ``"HEAD"`` when the command fails (e.g. not a git repo
    or detached HEAD).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path,
        )
        branch = result.stdout.strip()
        return branch if branch else "HEAD"
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("warning: could not determine current git branch, defaulting to 'HEAD'")
        return "HEAD"


def is_branch_main(current_branch: str, main_branch: str) -> bool:
    """Return True if *current_branch* matches the repository's main branch."""
    return current_branch == main_branch


def get_main_branch_name(session: requests.Session, base_url: str, project_key: str) -> str:
    """Discover the main branch name by querying the project_branches/list endpoint.

    Calls ``GET /api/project_branches/list?project={project_key}`` which returns
    an array of branch objects, each with an ``isMain`` boolean flag.
    The branch where ``isMain`` is ``True`` is returned.
    Falls back to ``"main"`` if no branch is flagged as main.
    """
    url = f"{base_url}/api/project_branches/list"
    resp = session.get(url, params={"project": _urlencode_value(project_key)})
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
    page_size: int = 500,
) -> list[dict]:
    """Fetch all violations/issues for the given project/branch using pagination.

    Calls the SonarCloud/SonarQube Issues API endpoint:
        GET /api/issues/search?projectKeys={project_key}&branch={branch}&ps={page_size}&p=1&statuses=OPEN,CONFIRMED&types=CODE_SMELL,BUG,VULNERABILITY
    """
    url = f"{base_url}/api/issues/search"
    params = {
        "projectKeys": _urlencode_value(project_key),
        "branch": _urlencode_value(branch),
        "ps": page_size,
        "p": 1,
        "statuses": "OPEN,CONFIRMED",
        "types": "CODE_SMELL,BUG,VULNERABILITY",
    }

    all_violations: list[dict] = []
    while ((params["p"] - 1) * page_size < 10000):
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        all_violations.extend(issues)
        if len(all_violations) >= data.get("paging", {}).get("total", 0):
            break
        params["p"] += 1

    return all_violations


def fetch_coverage(session: requests.Session, base_url: str, project_key: str, branch: str) -> dict:
    """Fetch coverage data for the given project/branch from SonarQube.

    Calls ``GET /api/measures/component?component={project_key}&branch={branch}&metricKeys=coverage``.
    Returns the response as a dict, or ``{"error": ...}`` on failure.
    """
    url = f"{base_url}/api/measures/component"
    params = {
        "component": _urlencode_value(project_key),
        "branch": _urlencode_value(branch),
        "metricKeys": "coverage",
    }
    try:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"warning: could not fetch coverage data: {e}")
        return {"error": str(e)}


def _extract_issue_id(v: dict) -> str:
    """Return a unique identifier for a SonarQube issue."""
    return v.get("key", "")


def _branch_only_violations(violations: list[dict], main_keys: set[str]) -> list[dict]:
    """Return violations whose IDs are not present in the main branch issue set."""
    return [v for v in violations if _extract_issue_id(v) not in main_keys]


def _violation_sort_key(v: dict):
    """Return a sort key so violations are ordered:

    code smells -> bugs -> vulnerabilities,
    and within each type: minor -> major -> critical -> blocker.
    """
    type_order = {"CODE_SMELL": 0, "BUG": 1, "VULNERABILITY": 2}
    severity_order = {"INFO": 0, "MINOR": 1, "MAJOR": 2, "CRITICAL": 3, "BLOCKER": 4}
    return (
        type_order.get(v.get("type"), 99),
        severity_order.get(v.get("severity"), 99),
        v.get("rule", ""),
        v.get("line", 0),
    )


def _print_violations(label: str, violations: list[dict]):
    """Print a list of violations with summary."""
    if not violations:
        return
    sorted_violations = sorted(violations, key=_violation_sort_key)
    for v in sorted_violations:
        print(
            f"[{v.get('severity', '?')}] {v.get('type', '?')} - "
            f"{v.get('component', '')} ({v.get('rule', '')}) "
            f"at line {v.get('line', '?')}: "
            f"{v.get('message', '')[:80]}"
        )


def _print_severity_summary(violations: list[dict]):
    """Print a summary count of violations by severity level."""
    severity_counts: dict[str, int] = {}
    for v in violations:
        sev = v.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    print("\nSeverity summary:")
    for s in ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]:
        if s in severity_counts:
            print(f" {s}: {severity_counts[s]}")


def _print_coverage(api_response: dict):
    """Print a summary of coverage data from the SonarQube measures API response."""
    if "error" in api_response:
        return
    component = api_response.get("component", {})
    measures = component.get("measures", [])
    coverage = None
    for m in measures:
        if m.get("metric") == "coverage":
            coverage = m.get("value")
            break
    branch_name = component.get("name", component.get("key", ""))
    print(f"\nCode coverage summary for {branch_name}:")
    if coverage is not None:
        print(f" overall: {coverage}%")
    else:
        print(" coverage data not available")


def main():
    config = load_config()
    base_url = config["sonarqube_url"].rstrip("/")
    project_key = config["project_key"]
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        print("Environment variable SONAR_TOKEN is not set.")
        sys.exit(1)

    fix_rule = sys.argv[2] if len(sys.argv) > 2 else None

    current_branch = get_current_branch()
    print(f"current git branch: {current_branch}")

    session = requests.Session()
    if (token != "None"):
        session.headers.update({"Authorization": f"Bearer {token}"})

    main_branch = get_main_branch_name(session, base_url, project_key)
    print(f"main branch: {main_branch}")

    if is_branch_main(current_branch, main_branch):
        violations = fetch_violations(session, base_url, project_key, main_branch)

        print(f"\non main branch - {len(violations)} violations from {project_key} on branch '{main_branch}':")
        _print_violations("", violations)
        _print_severity_summary(violations)

        print(f"\nTotal violations on '{main_branch}': {len(violations)}")

        print("\nFetching code coverage data...")
        coverage_data = fetch_coverage(session, base_url, project_key, main_branch)
        _print_coverage(coverage_data)

        print(f"\nTotal violations on '{main_branch}': {len(violations)}")
        violations_to_fix = violations
    else:
        branch_violations = fetch_violations(session, base_url, project_key, current_branch)
        main_violations = fetch_violations(session, base_url, project_key, main_branch)

        main_keys: set[str] = set(_extract_issue_id(v) for v in main_violations)
        branch_only = _branch_only_violations(branch_violations, main_keys)

        print(f"\non branch '{current_branch}' (not '{main_branch}'):")
        print(f" Total violations on '{current_branch}': {len(branch_violations)}")
        print(f" Total violations on '{main_branch}': {len(main_violations)}")
        print(f" Violations on '{current_branch}' but NOT on '{main_branch}': {len(branch_only)}")

        if (len(main_violations) > 0) and (len(branch_violations) == 0):
            print(f"\nNo violations found on '{current_branch}' but '{main_branch}' has {len(main_violations)} issues - this can happen on free installations of SonarQube or free accounts on SonarCloud.")

        if branch_only:
            print(f"\nNew violations on '{current_branch}' not in '{main_branch}':")
            _print_violations("", branch_only)
            _print_severity_summary(branch_only)

        violations_to_fix = branch_only

        print("\nFetching code coverage data...")
        _print_coverage(fetch_coverage(session, base_url, project_key, current_branch))
        _print_coverage(fetch_coverage(session, base_url, project_key, main_branch))

    if fix_rule != None:
        print(f"\nAttempting to fix issues with PyOpenFixer 1.0.1... {fix_rule}")
    for v in violations_to_fix:
        if fix_rule and (v.get('rule') == fix_rule):
            print(f"\n[OPENCODE] Attempting to fix {v.get('component', '')}:{v.get('line', '?')} ({v.get('rule', '')})")
            message = v.get("message", "unknown issue")
            component = v.get("component", "unknown")
            line = v.get("line", "?")
            fix_prompt = "fix the problem " + message + " in " + component + " on line " + str(line)

            try:
                result = subprocess.run(
                    ["opencode", "run", fix_prompt],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                print(f"\n[OPENCODE] Fixed: {component}:{line} ({v.get('rule', '')})")
                if result.stdout:
                    print(result.stdout)
            except FileNotFoundError:
                print(f"\n[OPENCODE] opencode not found in PATH - skipped {component}:{line}")
            except subprocess.CalledProcessError as e:
                print(f"\n[OPENCODE] Command failed for {component}:{line}: {e}")

    print(f"\nThank you for pushing PyOpenFixer 1.0.1")
    return violations_to_fix


if __name__ == "__main__":
    violations = main()
