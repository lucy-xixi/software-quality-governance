"""Format a governance report from the project-level quality gate.

This module does not decide pass or fail. evaluate_quality_gate does that.
SonarQube bug, vulnerability, duplication, and code-smell values are included
only when a caller supplies them. They are not invented here.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from src.governance import evaluate_quality_gate

_SONAR_CONDITIONS = (
    "bugs.critical",
    "bugs.major",
    "vulnerabilities.critical",
    "vulnerabilities.high",
    "duplication",
)


def load_coverage_metric(path: str | Path) -> dict:
    """Read a coverage.py Cobertura XML file.

    The percentage is lines-covered / lines-valid. A missing file, or a file
    with no valid lines, returns coverage None. That is unavailable, not zero.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {"coverage": None, "statements_covered": None, "statements_valid": None}
    root = ET.parse(file_path).getroot()
    covered = int(root.get("lines-covered") or 0)
    valid = int(root.get("lines-valid") or 0)
    if valid == 0:
        return {"coverage": None, "statements_covered": covered, "statements_valid": valid}
    return {
        "coverage": round(covered / valid * 100, 2),
        "statements_covered": covered,
        "statements_valid": valid,
    }


def build_governance_report(
    metrics: dict | None = None,
    policy: dict | None = None,
    coverage_path: str | Path | None = None,
) -> dict:
    """Collect metrics, evaluate the YAML policy, and return a serializable report.

    Coverage is taken from metrics when that key is present. Otherwise it is
    read from coverage.xml. Other metrics stay absent unless the caller
    supplies them.
    """
    supplied = dict(metrics or {})
    measurement = {"statements_covered": None, "statements_valid": None}
    if "coverage" not in supplied:
        loaded = load_coverage_metric(
            Path(coverage_path) if coverage_path is not None else _default_coverage_path()
        )
        supplied["coverage"] = loaded["coverage"]
        measurement = loaded

    evaluation = evaluate_quality_gate(supplied, policy)
    return {
        "project": _project_identity(),
        "quality_gate": evaluation["quality_gate"],
        "release_readiness": evaluation["release_readiness"],
        "risk": evaluation["risk"],
        "coverage": evaluation["coverage"],
        "statements_covered": measurement["statements_covered"],
        "statements_valid": measurement["statements_valid"],
        "bugs": evaluation["bugs"],
        "vulnerabilities": evaluation["vulnerabilities"],
        "duplicated_lines": evaluation["duplicated_lines"],
        "code_smells": evaluation["code_smells"],
        "conditions": evaluation["conditions"],
        "failed_conditions": evaluation["failed_conditions"],
        "unavailable_conditions": evaluation["unavailable_conditions"],
        "recommended_actions": _recommended_actions(evaluation),
    }


def render_governance_report_markdown(report: dict) -> str:
    """Render a governance report as Markdown."""
    coverage_condition = _condition(report, "coverage")
    lines = [
        "# Software Quality Governance Report",
        "",
        "## Project",
        "",
        f"- Name: {_text(report['project']['name'])}",
        f"- Key: {_text(report['project']['key'])}",
        "",
        "## Executive Summary",
        "",
        (
            f"Release readiness is {report['release_readiness']} "
            "under the project governance policy."
        ),
        (
            "This report evaluates the project-level governance policy. "
            "It does not replace the SonarQube server-side quality gate."
        ),
        "",
        "## Quality Gate",
        "",
        f"Quality Gate: {report['quality_gate']}",
        "",
        "## Release Readiness",
        "",
        f"Release Readiness: {report['release_readiness']}",
        "",
        "## Risk Summary",
        "",
        (
            f"Risk: {report['risk']}"
            if report["risk"] is not None
            else "Risk: UNASSESSED"
            if report["unavailable_conditions"]
            else "Risk: None"
        ),
        "",
        (
            "No measured policy failure currently has an assigned risk level. "
            "SonarQube-derived evidence remains unavailable."
            if report["risk"] is None and report["unavailable_conditions"]
            else "Risk is assigned only to measured policy failures. "
            "Unavailable evidence is not a confirmed defect and is not given a risk label."
        ),
        "",
        "## Quality Metrics",
        "",
        f"- Coverage: {_coverage_text(report, coverage_condition)}",
        f"- Bugs: {_group_text(report['bugs'])}",
        f"- Vulnerabilities: {_group_text(report['vulnerabilities'])}",
        f"- Duplication: {_text(report['duplicated_lines'], percent=True)}",
        f"- Code Smells: {_text(report['code_smells'])}",
        "",
    ]
    if _sonar_metrics_unavailable(report):
        lines.extend(["SonarQube scan has not yet been executed.", ""])
    lines.extend(
        [
            "## Policy Conditions",
            "",
            "| Metric | Status | Actual | Threshold | Risk |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report["conditions"]:
        lines.append(
            "| {metric} | {status} | {actual} | {threshold} | {risk} |".format(
                metric=item["metric"],
                status=item["status"],
                actual=_text(item["actual"]),
                threshold=_text(item["threshold"]),
                risk=_blank(item["risk"]),
            )
        )
    lines.extend(["", "## Failed Conditions", ""])
    lines.extend(_bullet_list(report["failed_conditions"], "None."))
    lines.extend(["", "## Unavailable Evidence", ""])
    lines.append(
        "These conditions are unavailable because the required evidence does not exist yet. "
        "They are not measured defects, and they are not zero."
    )
    lines.append("")
    lines.extend(_bullet_list(report["unavailable_conditions"], "None."))
    lines.extend(["", "## Recommended Actions", ""])
    lines.extend(_bullet_list(report["recommended_actions"], "None."))
    lines.append("")
    return "\n".join(lines)


def write_governance_reports(report: dict, directory: str | Path) -> None:
    """Write governance_report.json and governance_report.md."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "governance_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    (target / "governance_report.md").write_text(
        render_governance_report_markdown(report),
        encoding="utf-8",
    )


def _recommended_actions(evaluation: dict) -> list[str]:
    by_metric = {item["metric"]: item for item in evaluation["conditions"]}
    actions: list[str] = []
    coverage = by_metric["coverage"]
    if coverage["status"] == "FAILED":
        actions.append(
            "Increase automated test coverage to at least the policy minimum of "
            f"{_format_number(coverage['threshold'])}%."
        )
    elif coverage["status"] == "UNAVAILABLE":
        actions.append(
            "Collect a pytest-cov report before evaluating coverage. Missing coverage is not zero."
        )
    if any(by_metric[name]["status"] == "UNAVAILABLE" for name in _SONAR_CONDITIONS):
        actions.append("Run a SonarQube analysis to obtain static-analysis and duplication metrics.")
        actions.append("Review the SonarQube server-side quality gate before release evaluation.")
    if by_metric["bugs.critical"]["status"] == "FAILED" or by_metric["bugs.major"]["status"] == "FAILED":
        actions.append("Review the measured bug counts against the project policy limits.")
    if (
        by_metric["vulnerabilities.critical"]["status"] == "FAILED"
        or by_metric["vulnerabilities.high"]["status"] == "FAILED"
    ):
        actions.append("Review the measured vulnerability counts against the project policy limits.")
    if by_metric["duplication"]["status"] == "FAILED":
        actions.append(
            "Reduce duplicated lines to at most the policy maximum of "
            f"{_format_number(by_metric['duplication']['threshold'])}%."
        )
    return actions


def _project_identity() -> dict:
    properties = _read_properties(_project_root() / "sonar-project.properties")
    return {
        "name": properties.get("sonar.projectName"),
        "key": properties.get("sonar.projectKey"),
    }


def _read_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _default_coverage_path() -> Path:
    return _project_root() / "coverage.xml"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _condition(report: dict, metric: str) -> dict:
    return next(item for item in report["conditions"] if item["metric"] == metric)


def _sonar_metrics_unavailable(report: dict) -> bool:
    bugs = report["bugs"]
    vulnerabilities = report["vulnerabilities"]
    return (
        all(value is None for value in bugs.values())
        and all(value is None for value in vulnerabilities.values())
        and report["duplicated_lines"] is None
        and report["code_smells"] is None
    )


def _coverage_text(report: dict, condition: dict) -> str:
    if report["coverage"] is None:
        return "UNAVAILABLE"
    text = f"{_format_number(report['coverage'])}%"
    if condition["threshold"] is not None:
        text += f" (policy minimum {_format_number(condition['threshold'])}%)"
    covered = report["statements_covered"]
    valid = report["statements_valid"]
    if covered is not None and valid:
        text += f"; {covered} of {valid} statements"
    return text


def _group_text(values: dict) -> str:
    if all(value is None for value in values.values()):
        return "UNAVAILABLE"
    parts = []
    for key, value in values.items():
        parts.append(f"{key} {_text(value)}")
    return ", ".join(parts)


def _blank(value: object) -> str:
    if value is None:
        return "None"
    return str(value)


def _text(value: object, percent: bool = False) -> str:
    if value is None:
        return "UNAVAILABLE"
    if percent:
        return f"{_format_number(value)}%"
    return _format_number(value)


def _format_number(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _bullet_list(items: list[str], empty: str) -> list[str]:
    if not items:
        return [empty]
    return [f"- {item}" for item in items]
