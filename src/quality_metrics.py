"""Descriptive quality metrics for a processed module dataset."""

from dataclasses import dataclass

import pandas as pd

from src.data_processor import ProcessingResult


@dataclass(frozen=True)
class QualityMetrics:
    """Summary of the accepted module records and how many rows were rejected."""

    accepted_count: int
    rejected_count: int
    validity_rate: float
    mean_coverage: float | None
    mean_bug_density: float | None
    low_coverage_count: int


def calculate_quality_metrics(result: ProcessingResult) -> QualityMetrics:
    """Calculate dataset quality metrics from a processing result.

    Rates are rounded to 4 decimal places. Means are rounded to 2.
    """
    accepted = result.records
    accepted_count = int(len(accepted))
    rejected_count = int(len(result.rejected))
    total = accepted_count + rejected_count
    validity_rate = round((accepted_count / total) if total else 0.0, 4)

    if accepted_count == 0:
        return QualityMetrics(
            accepted_count=0,
            rejected_count=rejected_count,
            validity_rate=validity_rate,
            mean_coverage=None,
            mean_bug_density=None,
            low_coverage_count=0,
        )

    return QualityMetrics(
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        validity_rate=validity_rate,
        mean_coverage=round(float(accepted["coverage_percent"].mean()), 2),
        mean_bug_density=round(float(accepted["bug_density"].mean()), 2),
        low_coverage_count=int((accepted["coverage_band"] == "low").sum()),
    )


def highest_bug_density(records: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    """Return the modules with the highest bug density."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if records.empty:
        return records.copy()
    if "bug_density" not in records.columns or "module_id" not in records.columns:
        raise ValueError("records must include module_id and bug_density")
    ranked = records.sort_values(
        by=["bug_density", "module_id"],
        ascending=[False, True],
        kind="mergesort",
    )
    return ranked.head(limit).reset_index(drop=True)
