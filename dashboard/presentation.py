"""Display values for the governance dashboard.

This module reads a governance report and formats it. It does not evaluate
config/quality_policy.yaml and it does not invent SonarQube measures.
"""

import json
from pathlib import Path

MISSING_REPORT_MESSAGE = (
    "Governance report not found. "
    "Run the governance report generation step before opening the dashboard."
)
INVALID_REPORT_MESSAGE = (
    "Governance report could not be parsed. Please regenerate the report."
)

POLICY_SOURCE = "config/quality_policy.yaml"
REPORT_SOURCE = "reports/governance_report.json"
ANALYSIS_SOURCE = "SonarQube"

UNAVAILABLE = "UNAVAILABLE"


class ReportLoadError(Exception):
    """The dashboard cannot read a governance report."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_report_path() -> Path:
    return project_root() / "reports" / "governance_report.json"


def load_governance_report(path: str | Path) -> dict:
    """Load the machine-readable governance report.

    A missing file and invalid JSON raise ReportLoadError. Callers present
    that message instead of a traceback.
    """
    report_path = Path(path)
    if not report_path.is_file():
        raise ReportLoadError(MISSING_REPORT_MESSAGE)
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReportLoadError(INVALID_REPORT_MESSAGE) from error
    if not isinstance(document, dict):
        raise ReportLoadError(INVALID_REPORT_MESSAGE)
    return document


def gate_label(report: dict) -> str:
    return _label(report.get("quality_gate"))


def readiness_label(report: dict) -> str:
    return _label(report.get("release_readiness"))


def risk_label(report: dict) -> str:
    """Present the report risk. Unavailable evidence stays unlabeled.

    A null risk with missing required evidence is shown as UNASSESSED.
    A risk value already in the report is shown as stored.
    """
    risk = report.get("risk")
    if risk:
        return str(risk)
    if report.get("unavailable_conditions"):
        return "UNASSESSED"
    return "N/A"


def risk_explanation(report: dict) -> str:
    if report.get("risk") is None and report.get("unavailable_conditions"):
        return (
            "No measured policy failure currently has an assigned risk level. "
            "Required SonarQube-derived evidence is unavailable."
        )
    if report.get("risk"):
        return (
            f"Risk {report['risk']} is taken from the governance report. "
            "It is the highest label among measured policy failures. "
            "Unavailable evidence is not given a risk label."
        )
    return "No measured policy failure currently has an assigned risk level."


def release_explanation(report: dict) -> str:
    readiness = readiness_label(report)
    failed = report.get("failed_conditions") or []
    unavailable = report.get("unavailable_conditions") or []
    if readiness == "NOT_READY" and unavailable and not failed:
        return (
            f"Release readiness is {readiness} because required SonarQube-derived "
            "governance evidence is currently unavailable."
        )
    if readiness == "NOT_READY" and failed:
        measured = ", ".join(str(name) for name in failed)
        text = (
            f"Release readiness is {readiness} because measured policy conditions "
            f"failed: {measured}."
        )
        if unavailable:
            text += " Unavailable evidence is not a measured defect."
        return text
    if readiness == "READY":
        return (
            f"Release readiness is {readiness}. "
            "Required governance evidence is available and passing."
        )
    return f"Release readiness is {readiness} under the project governance policy."


def coverage_panel(report: dict) -> dict:
    condition = _condition(report, "coverage")
    coverage = report.get("coverage") if "coverage" in report else None
    status = UNAVAILABLE if condition is None else _label(condition.get("status"))
    threshold = None if condition is None else condition.get("threshold")
    return {
        "coverage": coverage,
        "coverage_text": _percent(coverage),
        "policy_minimum": threshold,
        "policy_minimum_text": _percent(threshold) if threshold is not None else UNAVAILABLE,
        "status": status,
        "statements_text": _statements_text(report),
        "release_readiness": readiness_label(report),
        "progress": None if coverage is None else max(0.0, min(float(coverage), 100.0)) / 100.0,
    }


def sonar_rows(report: dict) -> list[dict[str, str]]:
    return [
        {"Metric": "Bugs", "Status": _group_text(report.get("bugs"))},
        {"Metric": "Vulnerabilities", "Status": _group_text(report.get("vulnerabilities"))},
        {"Metric": "Duplication", "Status": _scalar_text(report.get("duplicated_lines"), percent=True)},
        {"Metric": "Code Smells", "Status": _scalar_text(report.get("code_smells"))},
    ]


def sonar_note(report: dict) -> str | None:
    statuses = [row["Status"] for row in sonar_rows(report)]
    if any(UNAVAILABLE in status for status in statuses):
        return (
            "SonarQube-derived evidence has not yet been collected. "
            "Unavailable evidence is not treated as zero."
        )
    return None


def condition_rows(report: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in report.get("conditions") or []:
        if not isinstance(item, dict):
            continue
        status = _label(item.get("status"))
        actual = item.get("actual")
        actual_text = UNAVAILABLE if actual is None or status == UNAVAILABLE else _number(actual)
        threshold = item.get("threshold")
        risk = item.get("risk")
        rows.append(
            {
                "Metric": _label(item.get("metric")),
                "Status": status,
                "Actual": actual_text,
                "Threshold": "N/A" if threshold is None else _number(threshold),
                "Risk": "N/A" if not risk else str(risk),
            }
        )
    return rows


def recommended_actions(report: dict) -> list[str]:
    actions = report.get("recommended_actions")
    if not isinstance(actions, list):
        return []
    return [str(item) for item in actions]


def project_fields(report: dict) -> dict[str, str]:
    project = report.get("project")
    if not isinstance(project, dict):
        project = {}
    return {
        "name": _label(project.get("name")),
        "key": _label(project.get("key")),
    }


def decision_flow(report: dict) -> str:
    panel = coverage_panel(report)
    return "\n".join(
        [
            "Coverage",
            "   ↓",
            panel["status"],
            "   +",
            "Required SonarQube evidence",
            "   ↓",
            _required_evidence_status(report),
            "   ↓",
            "Overall Quality Gate",
            "   ↓",
            gate_label(report),
            "   ↓",
            "Release Readiness",
            "   ↓",
            readiness_label(report),
        ]
    )


def _required_evidence_status(report: dict) -> str:
    conditions = [
        item
        for item in report.get("conditions") or []
        if isinstance(item, dict) and item.get("metric") != "coverage"
    ]
    statuses = {item.get("status") for item in conditions}
    if not statuses or statuses == {UNAVAILABLE}:
        return UNAVAILABLE
    if "FAILED" in statuses:
        return "FAILED"
    if UNAVAILABLE in statuses:
        return UNAVAILABLE
    if statuses == {"PASSED"}:
        return "PASSED"
    return UNAVAILABLE


def _condition(report: dict, metric: str) -> dict | None:
    for item in report.get("conditions") or []:
        if isinstance(item, dict) and item.get("metric") == metric:
            return item
    return None


def _group_text(values: object) -> str:
    if not isinstance(values, dict) or not values or all(value is None for value in values.values()):
        return UNAVAILABLE
    return ", ".join(f"{key} {_scalar_text(value)}" for key, value in values.items())


def _scalar_text(value: object, percent: bool = False) -> str:
    if value is None:
        return UNAVAILABLE
    text = _number(value)
    if percent:
        return f"{text}%"
    return text


def _percent(value: object) -> str:
    if value is None:
        return UNAVAILABLE
    return f"{_number(value)}%"


def _statements_text(report: dict) -> str | None:
    covered = report.get("statements_covered")
    valid = report.get("statements_valid")
    if covered is None or not valid:
        return None
    return f"{covered} / {valid} statements"


def _label(value: object) -> str:
    if value is None or value == "":
        return UNAVAILABLE
    return str(value)


def _number(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
