"""Presentation tests for the governance dashboard.

These tests load and format the governance report. They do not evaluate policy.
"""

import json

import pytest

from dashboard.presentation import (
    INVALID_REPORT_MESSAGE,
    MISSING_REPORT_MESSAGE,
    ReportLoadError,
    condition_rows,
    coverage_panel,
    decision_flow,
    default_report_path,
    gate_label,
    load_governance_report,
    project_fields,
    readiness_label,
    recommended_actions,
    release_explanation,
    risk_explanation,
    risk_label,
    sonar_rows,
)


def test_loads_the_current_governance_report():
    report = load_governance_report(default_report_path())
    panel = coverage_panel(report)
    evidence = {row["Metric"]: row["Status"] for row in sonar_rows(report)}

    assert panel["coverage"] == 81.69
    assert panel["coverage_text"] == "81.69%"
    assert panel["policy_minimum"] == 80
    assert panel["status"] == "PASSED"
    assert panel["statements_text"] == "357 / 437 statements"
    assert gate_label(report) == "FAIL"
    assert readiness_label(report) == "NOT_READY"
    assert risk_label(report) == "UNASSESSED"
    assert evidence == {
        "Bugs": "UNAVAILABLE",
        "Vulnerabilities": "UNAVAILABLE",
        "Duplication": "UNAVAILABLE",
        "Code Smells": "UNAVAILABLE",
    }
    assert "0" not in evidence.values()
    assert recommended_actions(report) == [
        "Run a SonarQube analysis to obtain static-analysis and duplication metrics.",
        "Review the SonarQube server-side quality gate before release evaluation.",
    ]
    assert project_fields(report)["key"] == "software-quality-governance"


def test_missing_report_has_a_dashboard_message(tmp_path):
    with pytest.raises(ReportLoadError, match=MISSING_REPORT_MESSAGE):
        load_governance_report(tmp_path / "governance_report.json")


def test_invalid_json_has_a_dashboard_message(tmp_path):
    path = tmp_path / "governance_report.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportLoadError, match=INVALID_REPORT_MESSAGE):
        load_governance_report(path)


def test_non_object_json_is_rejected(tmp_path):
    path = tmp_path / "governance_report.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ReportLoadError, match=INVALID_REPORT_MESSAGE):
        load_governance_report(path)


def test_unavailable_metrics_are_not_shown_as_zero():
    report = {
        "bugs": {"critical": None, "major": None},
        "vulnerabilities": None,
        "conditions": [
            {
                "metric": "bugs.critical",
                "status": "UNAVAILABLE",
                "actual": None,
                "threshold": 0,
                "risk": None,
            }
        ],
    }
    evidence = {row["Metric"]: row["Status"] for row in sonar_rows(report)}
    assert evidence["Bugs"] == "UNAVAILABLE"
    assert evidence["Vulnerabilities"] == "UNAVAILABLE"
    assert evidence["Code Smells"] == "UNAVAILABLE"
    row = condition_rows(report)[0]
    assert row["Actual"] == "UNAVAILABLE"
    assert row["Threshold"] == "0"
    assert row["Risk"] == "N/A"
    assert "None" not in row.values()


def test_missing_code_smells_field_is_unavailable():
    evidence = {row["Metric"]: row["Status"] for row in sonar_rows({})}
    assert evidence["Code Smells"] == "UNAVAILABLE"


def test_measured_zero_stays_zero():
    report = {"vulnerabilities": {"critical": 0, "high": 0}}
    evidence = {row["Metric"]: row["Status"] for row in sonar_rows(report)}
    assert evidence["Vulnerabilities"] == "critical 0, high 0"


def test_risk_label_presents_the_report_without_relabeling_unavailable_evidence():
    assert risk_label({"risk": "CRITICAL", "unavailable_conditions": []}) == "CRITICAL"
    assert risk_label({"risk": "HIGH"}) == "HIGH"
    assert risk_label({"risk": None, "unavailable_conditions": ["duplication"]}) == "UNASSESSED"
    explanation = risk_explanation(
        {"risk": None, "unavailable_conditions": ["bugs.critical"]}
    )
    assert "No measured policy failure currently has an assigned risk level." in explanation
    assert "CRITICAL" not in explanation


def test_not_ready_explanation_distinguishes_unavailable_evidence():
    report = load_governance_report(default_report_path())
    text = release_explanation(report)
    assert text == (
        "Release readiness is NOT_READY because required SonarQube-derived "
        "governance evidence is currently unavailable."
    )
    flow = decision_flow(report)
    assert "PASSED" in flow
    assert "UNAVAILABLE" in flow
    assert "FAIL" in flow
    assert "NOT_READY" in flow


def test_project_fields_come_from_the_report():
    fields = project_fields({"project": {"name": "Example", "key": "example"}})
    assert fields == {"name": "Example", "key": "example"}


def test_round_trip_actions_are_not_rewritten(tmp_path):
    path = tmp_path / "governance_report.json"
    report = {
        "quality_gate": "FAIL",
        "release_readiness": "NOT_READY",
        "risk": None,
        "recommended_actions": ["Collect the missing scan."],
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    loaded = load_governance_report(path)
    assert recommended_actions(loaded) == ["Collect the missing scan."]
    assert gate_label(loaded) == "FAIL"
    assert readiness_label(loaded) == "NOT_READY"
