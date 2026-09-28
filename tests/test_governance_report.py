"""Tests for the governance report layer."""

import json

from src.governance_report import (
    build_governance_report,
    load_coverage_metric,
    render_governance_report_markdown,
)


def _passing_metrics(**overrides) -> dict:
    """Demonstration inputs. These are not SonarQube scan results."""
    metrics = {
        "coverage": 85,
        "bugs": {"critical": 0, "major": 0},
        "vulnerabilities": {"critical": 0, "high": 0},
        "duplicated_lines": 1.0,
        "code_smells": 2,
    }
    metrics.update(overrides)
    return metrics


def test_current_baseline_coverage_fails_the_policy():
    report = build_governance_report({"coverage": 79.81})
    assert report["coverage"] == 79.81
    assert report["quality_gate"] == "FAIL"
    assert report["release_readiness"] == "NOT_READY"
    assert report["risk"] == "MEDIUM"
    assert report["failed_conditions"] == ["coverage"]


def test_passing_metrics_are_ready():
    report = build_governance_report(_passing_metrics())
    assert report["quality_gate"] == "PASS"
    assert report["release_readiness"] == "READY"
    assert report["failed_conditions"] == []
    assert report["unavailable_conditions"] == []


def test_missing_sonar_metrics_stay_unavailable():
    report = build_governance_report(
        {
            "coverage": 85,
            "bugs": None,
            "vulnerabilities": None,
            "duplicated_lines": None,
            "code_smells": None,
        }
    )
    assert report["bugs"] == {"critical": None, "major": None}
    assert report["vulnerabilities"] == {"critical": None, "high": None}
    assert report["duplicated_lines"] is None
    assert report["code_smells"] is None
    assert report["bugs"] != {"critical": 0, "major": 0}
    assert report["vulnerabilities"] != {"critical": 0, "high": 0}
    assert set(report["unavailable_conditions"]) == {
        "bugs.critical",
        "bugs.major",
        "vulnerabilities.critical",
        "vulnerabilities.high",
        "duplication",
    }
    assert "bugs.critical" not in report["failed_conditions"]


def test_critical_vulnerability_sets_critical_risk():
    report = build_governance_report(
        _passing_metrics(vulnerabilities={"critical": 1, "high": 0})
    )
    assert report["quality_gate"] == "FAIL"
    assert report["release_readiness"] == "NOT_READY"
    assert report["risk"] == "CRITICAL"
    assert "vulnerabilities.critical" in report["failed_conditions"]


def test_multiple_failed_conditions_are_preserved():
    report = build_governance_report(
        _passing_metrics(
            coverage=79.81,
            vulnerabilities={"critical": 1, "high": 0},
            duplicated_lines=9,
        )
    )
    assert report["failed_conditions"] == [
        "coverage",
        "vulnerabilities.critical",
        "duplication",
    ]
    assert report["quality_gate"] == "FAIL"
    assert report["release_readiness"] == "NOT_READY"


def test_current_coverage_passes_but_missing_sonar_evidence_is_not_ready():
    report = build_governance_report({"coverage": 81.69})
    assert report["coverage"] == 81.69
    assert report["quality_gate"] == "FAIL"
    assert report["release_readiness"] == "NOT_READY"
    assert report["risk"] is None
    assert report["conditions"][0]["status"] == "PASSED"
    assert set(report["unavailable_conditions"]) == {
        "bugs.critical",
        "bugs.major",
        "vulnerabilities.critical",
        "vulnerabilities.high",
        "duplication",
    }


def test_markdown_shows_gate_coverage_and_unavailable_evidence():
    report = build_governance_report({"coverage": 79.81})
    markdown = render_governance_report_markdown(report)
    for text in (
        "Quality Gate",
        "Release Readiness",
        "Risk",
        "Coverage",
        "79.81",
        "UNAVAILABLE",
        "NOT_READY",
        "SonarQube scan has not yet been executed.",
    ):
        assert text in markdown
    assert "Production release is blocked" not in markdown


def test_report_serializes_to_json():
    report = build_governance_report({"coverage": 79.81})
    encoded = json.dumps(report)
    decoded = json.loads(encoded)
    assert decoded["quality_gate"] == "FAIL"
    assert decoded["bugs"]["critical"] is None
    assert decoded["vulnerabilities"]["high"] is None
    assert decoded["duplicated_lines"] is None
    assert decoded["code_smells"] is None


def test_load_coverage_metric_uses_the_xml_ratio(tmp_path):
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<?xml version="1.0" ?>'
        '<coverage lines-valid="312" lines-covered="249" line-rate="0.7981"></coverage>',
        encoding="utf-8",
    )
    metric = load_coverage_metric(report)
    assert metric["coverage"] == round(249 / 312 * 100, 2)
    assert metric["statements_covered"] == 249
    assert metric["statements_valid"] == 312


def test_missing_coverage_file_is_not_zero(tmp_path):
    metric = load_coverage_metric(tmp_path / "missing.xml")
    assert metric["coverage"] is None
    report = build_governance_report(coverage_path=tmp_path / "missing.xml")
    assert report["coverage"] is None
    assert "coverage" in report["unavailable_conditions"]
    assert report["coverage"] != 0
