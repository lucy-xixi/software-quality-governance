"""Two separate governance controls.

Module-level analytical quality policy: rules for rows in the sample dataset.
Project-level software quality gate policy: config/quality_policy.yaml, used
for coverage, bugs, vulnerabilities, duplication, and release readiness.
The project gate does not replace the SonarQube server gate.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from src.data_processor import ProcessingResult

# Module-level analytical quality policy for records in the sample dataset.
# This is not the project-level quality gate in config/quality_policy.yaml.
MODULE_MIN_COVERAGE_PERCENT = 70.0
MODULE_MAX_BUG_DENSITY_PER_KLOC = 5.0


@dataclass(frozen=True)
class ModuleGovernanceMetrics:
    """Analytical conformance of accepted module records, plus validation issues."""

    ownership_rate: float | None
    review_completion_rate: float | None
    policy_breach_count: int
    policy_conformance_rate: float | None
    open_validation_issues: int


def calculate_module_governance_metrics(result: ProcessingResult) -> ModuleGovernanceMetrics:
    """Measure ownership, completed reviews, and the module-level analytical policy.

    A module meets that policy when its coverage is at least 70% and its bug
    density is at most 5 per KLOC. Those limits are not the project quality gate.
    Rates are None when there are no accepted records. Rates are rounded to 4
    decimal places. Thresholds are inclusive.
    """
    open_validation_issues = len(result.issues)
    records = result.records
    if records.empty:
        return ModuleGovernanceMetrics(
            ownership_rate=None,
            review_completion_rate=None,
            policy_breach_count=0,
            policy_conformance_rate=None,
            open_validation_issues=open_validation_issues,
        )

    meets_policy = records.apply(_meets_module_quality_policy, axis=1)
    return ModuleGovernanceMetrics(
        ownership_rate=round(float(records["has_owner"].mean()), 4),
        review_completion_rate=round(float((records["review_status"] == "reviewed").mean()), 4),
        policy_breach_count=int((~meets_policy).sum()),
        policy_conformance_rate=round(float(meets_policy.mean()), 4),
        open_validation_issues=open_validation_issues,
    )


def explain_module_policy_breaches(records: pd.DataFrame) -> list[str]:
    """Describe each module-level coverage or bug-density breach."""
    if records.empty:
        return []
    notes: list[str] = []
    for _, row in records.iterrows():
        module_name = row["module_name"]
        coverage = row["coverage_percent"]
        density = row["bug_density"]
        if _module_coverage_breach(coverage):
            shown = "missing" if pd.isna(coverage) else f"{float(coverage):.1f}%"
            notes.append(
                f"{module_name} coverage {shown} is below {MODULE_MIN_COVERAGE_PERCENT:.0f}%"
            )
        if _module_density_breach(density):
            shown = "missing" if pd.isna(density) else f"{float(density):.2f}"
            notes.append(
                f"{module_name} bug density {shown} is above "
                f"{MODULE_MAX_BUG_DENSITY_PER_KLOC:.1f} per KLOC"
            )
    return notes


def _meets_module_quality_policy(row: pd.Series) -> bool:
    return not _module_coverage_breach(row["coverage_percent"]) and not _module_density_breach(
        row["bug_density"]
    )


def _module_coverage_breach(coverage: object) -> bool:
    if pd.isna(coverage):
        return True
    return float(coverage) < MODULE_MIN_COVERAGE_PERCENT


def _module_density_breach(density: object) -> bool:
    if pd.isna(density):
        return True
    return float(density) > MODULE_MAX_BUG_DENSITY_PER_KLOC


@dataclass(frozen=True)
class _GateCondition:
    """One comparison. The threshold is read from the policy, not stored here."""

    metric: str
    actual_path: tuple[str, ...]
    threshold_path: tuple[str, ...]
    comparator: str
    failure_risk: str


# Risk label used when that condition fails. Numeric limits stay in the policy file.
_GATE_CONDITIONS = (
    _GateCondition("coverage", ("coverage",), ("coverage", "minimum"), ">=", "MEDIUM"),
    _GateCondition("bugs.critical", ("bugs", "critical"), ("bugs", "critical"), "<=", "CRITICAL"),
    _GateCondition("bugs.major", ("bugs", "major"), ("bugs", "major"), "<=", "HIGH"),
    _GateCondition(
        "vulnerabilities.critical",
        ("vulnerabilities", "critical"),
        ("vulnerabilities", "critical"),
        "<=",
        "CRITICAL",
    ),
    _GateCondition(
        "vulnerabilities.high",
        ("vulnerabilities", "high"),
        ("vulnerabilities", "high"),
        "<=",
        "HIGH",
    ),
    _GateCondition("duplication", ("duplicated_lines",), ("duplication", "maximum"), "<=", "LOW"),
)

_RISK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_MISSING = object()


def load_quality_policy(path: str | Path | None = None) -> dict:
    """Load the quality_policy mapping from YAML."""
    policy_path = Path(path) if path is not None else _default_policy_path()
    with policy_path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict) or not isinstance(document.get("quality_policy"), dict):
        raise ValueError("Policy file must contain a quality_policy mapping")
    return document["quality_policy"]


def evaluate_quality_gate(metrics: dict | None, policy: dict | None = None) -> dict:
    """Compare project metrics with the governance policy.

    A condition is PASSED only when the metric is present and within its limit.
    A missing metric is UNAVAILABLE. It is not treated as zero, and it does not
    pass. When quality_gate.required is true, any FAILED or UNAVAILABLE
    condition makes the gate FAIL and release readiness NOT_READY.

    Risk is the highest label among FAILED conditions. An unavailable metric
    is a missing measurement, not a confirmed finding, so it has no risk label.
    This is a portfolio control. It is not an enterprise release approval.
    """
    metrics = metrics or {}
    active_policy = policy if policy is not None else load_quality_policy()
    conditions = [_evaluate_condition(spec, metrics, active_policy) for spec in _GATE_CONDITIONS]
    failed = [item["metric"] for item in conditions if item["status"] == "FAILED"]
    unavailable = [item["metric"] for item in conditions if item["status"] == "UNAVAILABLE"]
    required = bool(_lookup(active_policy, ("quality_gate", "required"), default=True))
    if not required:
        gate = "NOT_REQUIRED"
        readiness = "READY"
    elif failed or unavailable:
        gate = "FAIL"
        readiness = "NOT_READY"
    else:
        gate = "PASS"
        readiness = "READY"

    return {
        "quality_gate": gate,
        "release_readiness": readiness,
        "risk": _highest_risk(conditions),
        "coverage": _present(metrics, ("coverage",)),
        "bugs": {
            "critical": _present(metrics, ("bugs", "critical")),
            "major": _present(metrics, ("bugs", "major")),
        },
        "vulnerabilities": {
            "critical": _present(metrics, ("vulnerabilities", "critical")),
            "high": _present(metrics, ("vulnerabilities", "high")),
        },
        "code_smells": _present(metrics, ("code_smells",)),
        "duplicated_lines": _present(metrics, ("duplicated_lines",)),
        "conditions": conditions,
        "failed_conditions": failed,
        "unavailable_conditions": unavailable,
    }


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "quality_policy.yaml"


def _evaluate_condition(spec: _GateCondition, metrics: dict, policy: dict) -> dict:
    threshold = _lookup(policy, spec.threshold_path)
    if threshold is _MISSING:
        raise ValueError(f"Policy is missing a threshold for {spec.metric}")
    actual = _lookup(metrics, spec.actual_path)
    if actual is _MISSING or actual is None:
        status = "UNAVAILABLE"
        actual_value = None
        risk = None
    elif _within_limit(actual, threshold, spec.comparator):
        status = "PASSED"
        actual_value = actual
        risk = None
    else:
        status = "FAILED"
        actual_value = actual
        risk = spec.failure_risk
    return {
        "metric": spec.metric,
        "status": status,
        "actual": actual_value,
        "threshold": threshold,
        "risk": risk,
    }


def _within_limit(actual: object, threshold: object, comparator: str) -> bool:
    if comparator == ">=":
        return actual >= threshold
    if comparator == "<=":
        return actual <= threshold
    raise ValueError(f"Unsupported comparator: {comparator}")


def _lookup(mapping: dict, path: tuple[str, ...], default: object = _MISSING) -> object:
    current: object = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _present(metrics: dict, path: tuple[str, ...]) -> object:
    value = _lookup(metrics, path)
    if value is _MISSING:
        return None
    return value


def _highest_risk(conditions: list[dict]) -> str | None:
    failed_risks = [item["risk"] for item in conditions if item["status"] == "FAILED"]
    if not failed_risks:
        return None
    return max(failed_risks, key=_RISK_RANK.__getitem__)
