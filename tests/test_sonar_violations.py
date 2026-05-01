import json
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest
import requests

import sonar_violations as sv


def _urlencode(s: str) -> str:
    return urllib.parse.quote(s, safe="")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "sonarqube_url": "https://sonarcloud.io",
    "project_key": "twilio_twilio-java",
}

SAMPLE_VIOLATIONS = [
    {
        "key": "a1",
        "rule": "java:S1858",
        "severity": "CRITICAL",
        "component": "org:myproject/src/A.java",
        "line": 47,
        "message": "first issue message",
        "type": "BUG",
    },
    {
        "key": "b1",
        "rule": "python:S111",
        "severity": "MINOR",
        "component": "org:myproject/src/B.py",
        "line": 12,
        "message": "second issue message, this one is a code smell",
        "type": "CODE_SMELL",
    },
    {
        "key": "c1",
        "rule": "java:S2259",
        "severity": "MAJOR",
        "component": "org:myproject/src/C.java",
        "line": 99,
        "message": "third issue",
        "type": "VULNERABILITY",
    },
    {
        "key": "d1",
        "rule": "java:S100",
        "severity": "INFO",
        "component": "org:myproject/src/D.java",
        "line": 1,
        "message": "info level issue",
        "type": "CODE_SMELL",
    },
    {
        "key": "e1",
        "rule": "java:S999",
        "severity": "BLOCKER",
        "component": "org:myproject/src/E.java",
        "line": 200,
        "message": "blocker issue",
        "type": "BUG",
    },
]

BRANCHES_RESPONSE = {
    "projectBranches": [
        {"name": "develop", "isMain": False},
        {"name": "main", "isMain": True},
        {"name": "feature/foo", "isMain": False},
    ]
}

ISSUES_INITIAL_RESPONSE = {
    "paging": {"total": 5, "pageIndex": 1, "pageSize": 2, "totalPages": 3},
    "issues": [SAMPLE_VIOLATIONS[0], SAMPLE_VIOLATIONS[1]],
}

ISSUES_SECOND_RESPONSE = {
    "paging": {"total": 5, "pageIndex": 2, "pageSize": 2, "totalPages": 3},
    "issues": [SAMPLE_VIOLATIONS[2], SAMPLE_VIOLATIONS[3]],
}

ISSUES_FINAL_RESPONSE = {
    "paging": {"total": 5, "pageIndex": 3, "pageSize": 2, "totalPages": 3},
    "issues": [SAMPLE_VIOLATIONS[4]],
}


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:

    def test_loads_valid_config(self, tmp_path: Path):
        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump(SAMPLE_CONFIG, f)
        result = sv.load_config(str(config_file))
        assert result == SAMPLE_CONFIG

    def test_defaults_to_config_json_in_cwd(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_CONFIG))):
                result = sv.load_config("config.json")
                assert result == SAMPLE_CONFIG

    def test_exits_when_file_missing(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            sv.load_config("/nonexistent/path/config.json")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Config file not found" in captured.err or captured.out

    def test_exits_when_missing_sonarqube_url(self, tmp_path: Path):
        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump({"project_key": "x"}, f)
        with pytest.raises(SystemExit) as exc_info:
            sv.load_config(str(config_file))
        assert exc_info.value.code == 1

    def test_exits_when_missing_project_key(self, tmp_path: Path):
        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump({"sonarqube_url": "https://x"}, f)
        with pytest.raises(SystemExit) as exc_info:
            sv.load_config(str(config_file))
        assert exc_info.value.code == 1

    def test_exits_on_invalid_json(self, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{ invalid json }")
        with pytest.raises(SystemExit) as exc_info:
            sv.load_config(str(config_file))
        assert exc_info.value.code == 1
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# get_current_branch
# ---------------------------------------------------------------------------

class TestGetCurrentBranch:

    def test_returns_current_branch(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = "feature/my-branch\n"
        mock_result.stderr = ""
        mock_run = MagicMock(return_value=mock_result)
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = sv.get_current_branch()
        assert result == "feature/my-branch"

    def test_returns_head_on_empty_output(self, monkeypatch):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run = MagicMock(return_value=mock_result)
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = sv.get_current_branch()
        assert result == "HEAD"

    def test_returns_head_on_called_process_error(self, monkeypatch):
        mock_run = MagicMock(side_effect=subprocess.CalledProcessError(1, "git"))
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = sv.get_current_branch()
        assert result == "HEAD"

    def test_returns_head_on_file_not_found(self, monkeypatch):
        mock_run = MagicMock(side_effect=FileNotFoundError)
        monkeypatch.setattr(subprocess, "run", mock_run)
        result = sv.get_current_branch()
        assert result == "HEAD"

    def test_uses_repo_path_cwd(self, monkeypatch):
        mock_run = MagicMock(return_value=MagicMock(stdout="main\n", stderr=""))
        monkeypatch.setattr(subprocess, "run", mock_run)
        sv.get_current_branch(repo_path="/some/repo")
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd="/some/repo",
        )


# ---------------------------------------------------------------------------
# is_branch_main
# ---------------------------------------------------------------------------

class TestIsBranchMain:

    def test_matching_branches(self):
        assert sv.is_branch_main("main", "main") is True
        assert sv.is_branch_main("develop", "develop") is True

    def test_non_matching_branches(self):
        assert sv.is_branch_main("feature/foo", "main") is False
        assert sv.is_branch_main("develop", "main") is False

    def test_case_sensitive(self):
        assert sv.is_branch_main("Main", "main") is False


# ---------------------------------------------------------------------------
# get_main_branch_name
# ---------------------------------------------------------------------------

class TestGetMainBranchName:

    def test_returns_main_branch(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = BRANCHES_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = sv.get_main_branch_name(mock_session, "https://sonarcloud.io", "my-project")
        assert result == "main"
        mock_session.get.assert_called_once_with(
            "https://sonarcloud.io/api/project_branches/list?project=my-project"
        )

    def test_falls_back_to_main_when_no_main_branch(self, capsys):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"projectBranches": [{"name": "develop", "isMain": False}]}
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = sv.get_main_branch_name(mock_session, "https://sonarcloud.io", "my-project")
        assert result == "main"
        captured = capsys.readouterr()
        assert "warning: no branch marked as main" in captured.out

    def test_raises_on_http_error(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        mock_session.get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            sv.get_main_branch_name(mock_session, "https://sonarcloud.io", "my-project")


# ---------------------------------------------------------------------------
# fetch_violations
# ---------------------------------------------------------------------------

class TestFetchViolations:

    def test_returns_single_page(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "paging": {"total": 1, "pageIndex": 1, "pageSize": 500, "totalPages": 1},
            "issues": [SAMPLE_VIOLATIONS[0]],
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = sv.fetch_violations(mock_session, "https://sonarcloud.io", "my-project", "main")
        assert len(result) == 1
        assert result[0]["key"] == "a1"

    def test_returns_multi_page_results(self):
        mock_session = MagicMock()
        mock_response_1 = MagicMock()
        mock_response_1.json.return_value = ISSUES_INITIAL_RESPONSE
        mock_response_1.raise_for_status = MagicMock()

        mock_response_2 = MagicMock()
        mock_response_2.json.return_value = ISSUES_SECOND_RESPONSE
        mock_response_2.raise_for_status = MagicMock()

        mock_response_3 = MagicMock()
        mock_response_3.json.return_value = ISSUES_FINAL_RESPONSE
        mock_response_3.raise_for_status = MagicMock()

        mock_session.get.side_effect = [mock_response_1, mock_response_2, mock_response_3]

        result = sv.fetch_violations(mock_session, "https://sonarcloud.io", "my-project", "main")
        assert len(result) == 5
        keys = [v["key"] for v in result]
        assert keys == ["a1", "b1", "c1", "d1", "e1"]

    def test_returns_empty_list(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"paging": {"total": 0}, "issues": []}
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        result = sv.fetch_violations(mock_session, "https://sonarcloud.io", "my-project", "main")
        assert result == []

    def test_raises_on_http_error(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        mock_session.get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            sv.fetch_violations(mock_session, "https://sonarcloud.io", "my-project", "main")


# ---------------------------------------------------------------------------
# _violation_sort_key
# ---------------------------------------------------------------------------

class TestViolationSortKey:

    def test_types_ordered_code_smell_before_bug_before_vulnerability(self):
        smell = {"type": "CODE_SMELL"}
        bug = {"type": "BUG"}
        vuln = {"type": "VULNERABILITY"}

        assert sv._violation_sort_key(smell) < sv._violation_sort_key(bug)
        assert sv._violation_sort_key(bug) < sv._violation_sort_key(vuln)

    def test_severity_ordered_info_before_minor_before_major(self):
        info = {"type": "CODE_SMELL", "severity": "INFO"}
        minor = {"type": "CODE_SMELL", "severity": "MINOR"}
        major = {"type": "CODE_SMELL", "severity": "MAJOR"}
        critical = {"type": "CODE_SMELL", "severity": "CRITICAL"}
        blocker = {"type": "CODE_SMELL", "severity": "BLOCKER"}

        keys = [sv._violation_sort_key(v) for v in [info, minor, major, critical, blocker]]
        assert keys == sorted(keys)

    def test_unknown_type_falls_to_end(self):
        known = {"type": "BUG"}
        unknown = {"type": "UNKNOWN_TYPE"}
        assert sv._violation_sort_key(known) < sv._violation_sort_key(unknown)

    def test_unknown_severity_falls_to_end(self):
        known = {"type": "BUG", "severity": "MAJOR"}
        unknown = {"type": "BUG", "severity": "UNKNOWN_SEV"}
        assert sv._violation_sort_key(known) < sv._violation_sort_key(unknown)

    def test_tiebreaker_by_rule_then_line(self):
        v1 = {"type": "BUG", "severity": "MAJOR", "rule": "java:S100", "line": 10}
        v2 = {"type": "BUG", "severity": "MAJOR", "rule": "java:S200", "line": 5}
        assert sv._violation_sort_key(v1) < sv._violation_sort_key(v2)

    def test_line_as_final_tiebreaker(self):
        v1 = {"type": "BUG", "severity": "MAJOR", "rule": "java:S100", "line": 5}
        v2 = {"type": "BUG", "severity": "MAJOR", "rule": "java:S100", "line": 10}
        assert sv._violation_sort_key(v1) < sv._violation_sort_key(v2)


# ---------------------------------------------------------------------------
# main (integration-style tests with mocked dependencies)
# ---------------------------------------------------------------------------

class TestMain:

    def test_exits_when_sonar_token_not_set(self, monkeypatch, capsys):
        monkeypatch.setenv("SONAR_TOKEN", "")
        with patch("sonar_violations.load_config", return_value=SAMPLE_CONFIG):
            with pytest.raises(SystemExit) as exc_info:
                sv.main()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "SONAR_TOKEN is not set" in captured.out

    def test_returns_violations_on_successful_run(self, monkeypatch, capsys):
        monkeypatch.setenv("SONAR_TOKEN", "fake-token")

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = BRANCHES_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        mock_issues_resp = MagicMock()
        mock_issues_resp.json.return_value = {
            "paging": {"total": 1},
            "issues": [SAMPLE_VIOLATIONS[0]],
        }
        mock_issues_resp.raise_for_status = MagicMock()

        mock_coverage_resp = MagicMock()
        mock_coverage_resp.json.return_value = {
            "component": {
                "key": "twilio_java",
                "name": "twilio_java",
                "measures": [{"metric": "coverage", "value": "82"}],
            },
            "metrics": [{"key": "coverage", "name": "Coverage", "type": "PERCENT"}],
        }
        mock_coverage_resp.raise_for_status = MagicMock()

        mock_session.get.side_effect = [mock_response, mock_issues_resp, mock_coverage_resp]

        with patch("sonar_violations.load_config", return_value=SAMPLE_CONFIG):
            with patch("sonar_violations.get_current_branch", return_value="main"):
                with patch("sonar_violations.requests.Session", return_value=mock_session):
                    result = sv.main()

        assert len(result) == 1
        assert result[0]["key"] == "a1"
        captured = capsys.readouterr()
        assert "current git branch: main" in captured.out
        assert "main branch: main" in captured.out
        assert "on main branch" in captured.out

    def test_skips_printing_on_feature_branch(self, monkeypatch, capsys):
        monkeypatch.setenv("SONAR_TOKEN", "fake-token")

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = BRANCHES_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response

        mock_branch_issues_resp = MagicMock()
        mock_branch_issues_resp.json.return_value = {
             "paging": {"total": 2},
             "issues": [SAMPLE_VIOLATIONS[0], SAMPLE_VIOLATIONS[2]],
        }
        mock_branch_issues_resp.raise_for_status = MagicMock()

        mock_main_issues_resp = MagicMock()
        mock_main_issues_resp.json.return_value = {
            "paging": {"total": 2},
            "issues": [SAMPLE_VIOLATIONS[3], SAMPLE_VIOLATIONS[4]],
        }
        mock_main_issues_resp.raise_for_status = MagicMock()

        mock_branch_coverage_resp = MagicMock()
        mock_branch_coverage_resp.json.return_value = {
              "component": {
                  "key": "twilio_java",
                  "name": "twilio_java:feature-foo",
                  "measures": [{"metric": "coverage", "value": "71"}],
              },
              "metrics": [{"key": "coverage", "name": "Coverage", "type": "PERCENT"}],
          }
        mock_branch_coverage_resp.raise_for_status = MagicMock()

        mock_main_coverage_resp = MagicMock()
        mock_main_coverage_resp.json.return_value = {
              "component": {
                  "key": "twilio_java",
                  "name": "twilio_java:main",
                  "measures": [{"metric": "coverage", "value": "82"}],
              },
              "metrics": [{"key": "coverage", "name": "Coverage", "type": "PERCENT"}],
          }
        mock_main_coverage_resp.raise_for_status = MagicMock()

        mock_session.get.side_effect = [
            mock_response,
            mock_branch_issues_resp,
            mock_main_issues_resp,
            mock_branch_coverage_resp,
            mock_main_coverage_resp,
         ]

        with patch("sonar_violations.load_config", return_value=SAMPLE_CONFIG):
            with patch("sonar_violations.get_current_branch", return_value="feature/foo"):
                with patch("sonar_violations.requests.Session", return_value=mock_session):
                    result = sv.main()

        assert len(result) == 2
        assert result[0]["key"] == "a1"
        captured = capsys.readouterr()
        assert "current git branch: feature/foo" in captured.out
        assert "main branch: main" in captured.out
        assert "on branch 'feature/foo'" in captured.out
        assert "Total violations on 'feature/foo'" in captured.out
        assert "Severity summary:" in captured.out
        assert "Code coverage summary" in captured.out
