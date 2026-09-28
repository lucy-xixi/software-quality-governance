# Software Quality Governance Report

## Project

- Name: Software Quality and Governance Dashboard
- Key: software-quality-governance

## Executive Summary

Release readiness is NOT_READY under the project governance policy.
This report evaluates the project-level governance policy. It does not replace the SonarQube server-side quality gate.

## Quality Gate

Quality Gate: FAIL

## Release Readiness

Release Readiness: NOT_READY

## Risk Summary

Risk: UNASSESSED

No measured policy failure currently has an assigned risk level. SonarQube-derived evidence remains unavailable.

## Quality Metrics

- Coverage: 81.69% (policy minimum 80%); 357 of 437 statements
- Bugs: UNAVAILABLE
- Vulnerabilities: UNAVAILABLE
- Duplication: UNAVAILABLE
- Code Smells: UNAVAILABLE

SonarQube scan has not yet been executed.

## Policy Conditions

| Metric | Status | Actual | Threshold | Risk |
| --- | --- | --- | --- | --- |
| coverage | PASSED | 81.69 | 80 | None |
| bugs.critical | UNAVAILABLE | UNAVAILABLE | 0 | None |
| bugs.major | UNAVAILABLE | UNAVAILABLE | 0 | None |
| vulnerabilities.critical | UNAVAILABLE | UNAVAILABLE | 0 | None |
| vulnerabilities.high | UNAVAILABLE | UNAVAILABLE | 0 | None |
| duplication | UNAVAILABLE | UNAVAILABLE | 5 | None |

## Failed Conditions

None.

## Unavailable Evidence

These conditions are unavailable because the required evidence does not exist yet. They are not measured defects, and they are not zero.

- bugs.critical
- bugs.major
- vulnerabilities.critical
- vulnerabilities.high
- duplication

## Recommended Actions

- Run a SonarQube analysis to obtain static-analysis and duplication metrics.
- Review the SonarQube server-side quality gate before release evaluation.
