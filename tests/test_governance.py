"""Tests for dataset governance metrics and the quality-gate policy engine."""

import pandas as pd

from src.data_processor import ProcessingResult, ValidationIssue
from src.governance import (
    calculate_module_governance_metrics,
    evaluate_quality_gate,
    load_quality_policy,
)


def test_policy_rates_for_a_small_set():
    # Coverage of 70 and bug density of 5.0 meet the module-level analytical
    # policy. Values outside fail. This is not the project quality gate.
    records = pd.DataFrame(
        [
            {
                "module_name": "A",
                "has_owner": True,
                "review_status": "reviewed",
                "coverage_percent": 80.0,
                "bug_density": 1.0,
            },
            {
                "module_name": "B",
                "has_owner": False,
                "review_status": "pending",
                "coverage_percent": 50.0,
                "bug_density": 1.0,
            },
            {
                "module_name": "C",
                "has_owner": True,
                "review_status": "reviewed",
                "coverage_percent": 90.0,
                "bug_density": 9.0,
            },
            {
                "module_name": "D",
                "has_owner": True,
                "review_status": "reviewed",
                "coverage_percent": 70.0,
                "bug_density": 5.0,
            },
        ]
    )
    result = ProcessingResult(
        records=records,
        rejected=pd.DataFrame(),
        issues=[ValidationIssue(4, "recorded_on", "recorded_on must be YYYY-MM-DD")],
    )
    metrics = calculate_module_governance_metrics(result)
    assert metrics.ownership_rate == 0.75
    assert metrics.review_completion_rate == 0.75
    assert metrics.policy_breach_count == 2
    assert metrics.policy_conformance_rate == 0.5
    assert metrics.open_validation_issues == 1


def test_sample_governance_metrics(processed_sample):
    """Seven of nine modules have an owner. Four miss the module-level analytical policy."""
    metrics = calculate_module_governance_metrics(processed_sample)
    assert metrics.ownership_rate == round(7 / 9, 4)
    assert metrics.review_completion_rate == round(5 / 9, 4)
    assert metrics.policy_breach_count == 4
    assert metrics.policy_conformance_rate == round(5 / 9, 4)
    assert metrics.open_validation_issues == 4


def _metrics(**overrides) -> dict:
    """Demonstration inputs. These are not SonarQube scan results."""
    metrics = {
        "coverage": 90.0,
        "bugs": {"critical": 0, "major": 0},
        "vulnerabilities": {"critical": 0, "high": 0},
        "duplicated_lines": 1.0,
        "code_smells": 3,
    }
    metrics.update(overrides)
    return metrics


def _condition(result: dict, metric: str) -> dict:
    return next(item for item in result["conditions"] if item["metric"] == metric)


def test_policy_is_loaded_from_yaml():
    policy = load_quality_policy()
    assert policy["coverage"]["minimum"] == 80
    assert policy["bugs"] == {"critical": 0, "major": 0}
    assert policy["vulnerabilities"] == {"critical": 0, "high": 0}
    assert policy["duplication"]["maximum"] == 5
    assert policy["quality_gate"]["required"] is True


def test_thresholds_come_from_the_policy_argument():
    policy = load_quality_policy()
    policy["coverage"]["minimum"] = 70
    result = evaluate_quality_gate(_metrics(coverage=75), policy)
    assert _condition(result, "coverage")["status"] == "PASSED"
    assert _condition(result, "coverage")["threshold"] == 70


def test_all_conditions_pass():
    result = evaluate_quality_gate(_metrics())
    assert result["quality_gate"] == "PASS"
    assert result["release_readiness"] == "READY"
    assert result["failed_conditions"] == []
    assert result["unavailable_conditions"] == []
    assert result["risk"] is None
    assert result["coverage"] == 90.0
    assert result["code_smells"] == 3


def test_coverage_below_threshold_fails_the_gate():
    result = evaluate_quality_gate(_metrics(coverage=75))
    assert _condition(result, "coverage")["status"] == "FAILED"
    assert _condition(result, "coverage")["actual"] == 75
    assert _condition(result, "coverage")["threshold"] == 80
    assert result["failed_conditions"] == ["coverage"]
    assert result["quality_gate"] == "FAIL"
    assert result["release_readiness"] == "NOT_READY"
    assert result["risk"] == "MEDIUM"


def test_critical_bug_fails_the_gate():
    result = evaluate_quality_gate(_metrics(bugs={"critical": 1, "major": 0}))
    assert _condition(result, "bugs.critical")["status"] == "FAILED"
    assert _condition(result, "bugs.major")["status"] == "PASSED"
    assert result["quality_gate"] == "FAIL"
    assert result["release_readiness"] == "NOT_READY"
    assert result["risk"] == "CRITICAL"


def test_major_bug_fails_the_gate():
    result = evaluate_quality_gate(_metrics(bugs={"critical": 0, "major": 2}))
    assert _condition(result, "bugs.major")["status"] == "FAILED"
    assert _condition(result, "bugs.critical")["status"] == "PASSED"
    assert result["quality_gate"] == "FAIL"
    assert result["risk"] == "HIGH"


def test_critical_vulnerability_fails_the_gate():
    result = evaluate_quality_gate(_metrics(vulnerabilities={"critical": 1, "high": 0}))
    assert _condition(result, "vulnerabilities.critical")["status"] == "FAILED"
    assert result["vulnerabilities"]["critical"] == 1
    assert result["quality_gate"] == "FAIL"
    assert result["risk"] == "CRITICAL"


def test_high_vulnerability_fails_the_gate():
    result = evaluate_quality_gate(_metrics(vulnerabilities={"critical": 0, "high": 1}))
    assert _condition(result, "vulnerabilities.high")["status"] == "FAILED"
    assert _condition(result, "vulnerabilities.critical")["status"] == "PASSED"
    assert result["quality_gate"] == "FAIL"
    assert result["risk"] == "HIGH"


def test_duplication_above_threshold_fails_the_gate():
    result = evaluate_quality_gate(_metrics(duplicated_lines=6))
    assert _condition(result, "duplication")["status"] == "FAILED"
    assert _condition(result, "duplication")["threshold"] == 5
    assert result["failed_conditions"] == ["duplication"]
    assert result["quality_gate"] == "FAIL"
    assert result["risk"] == "LOW"


def test_multiple_failed_conditions_are_listed():
    result = evaluate_quality_gate(
        _metrics(
            coverage=75,
            bugs={"critical": 1, "major": 2},
            duplicated_lines=9,
        )
    )
    assert result["failed_conditions"] == [
        "coverage",
        "bugs.critical",
        "bugs.major",
        "duplication",
    ]
    assert result["quality_gate"] == "FAIL"
    assert result["release_readiness"] == "NOT_READY"


def test_missing_metric_is_unavailable_and_not_zero():
    metrics = _metrics()
    del metrics["vulnerabilities"]
    result = evaluate_quality_gate(metrics)
    critical = _condition(result, "vulnerabilities.critical")
    high = _condition(result, "vulnerabilities.high")
    assert critical["status"] == "UNAVAILABLE"
    assert high["status"] == "UNAVAILABLE"
    assert critical["actual"] is None
    assert result["vulnerabilities"] == {"critical": None, "high": None}
    assert "vulnerabilities.critical" not in result["failed_conditions"]
    assert "vulnerabilities.high" not in result["failed_conditions"]
    assert result["unavailable_conditions"] == [
        "vulnerabilities.critical",
        "vulnerabilities.high",
    ]
    assert _condition(result, "coverage")["status"] == "PASSED"
    assert result["quality_gate"] == "FAIL"
    assert result["release_readiness"] == "NOT_READY"
    assert result["risk"] is None


def test_release_readiness_follows_the_gate():
    passed = evaluate_quality_gate(_metrics())
    failed = evaluate_quality_gate(_metrics(coverage=75))
    assert passed["quality_gate"] == "PASS"
    assert passed["release_readiness"] == "READY"
    assert failed["quality_gate"] == "FAIL"
    assert failed["release_readiness"] == "NOT_READY"


def test_risk_is_the_highest_failed_condition():
    result = evaluate_quality_gate(
        _metrics(
            coverage=75,
            vulnerabilities={"critical": 1, "high": 0},
            duplicated_lines=8,
        )
    )
    assert _condition(result, "coverage")["risk"] == "MEDIUM"
    assert _condition(result, "vulnerabilities.critical")["risk"] == "CRITICAL"
    assert _condition(result, "duplication")["risk"] == "LOW"
    assert result["risk"] == "CRITICAL"
