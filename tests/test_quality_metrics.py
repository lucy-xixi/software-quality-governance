"""Tests for descriptive quality metrics."""

import pandas as pd

from src.data_processor import ProcessingResult
from src.quality_metrics import calculate_quality_metrics


def test_metrics_for_a_small_set():
    records = pd.DataFrame(
        [
            {"coverage_percent": 80.0, "bug_density": 1.0, "coverage_band": "high"},
            {"coverage_percent": 50.0, "bug_density": 4.0, "coverage_band": "low"},
            {"coverage_percent": 70.0, "bug_density": 2.5, "coverage_band": "medium"},
        ]
    )
    result = ProcessingResult(
        records=records,
        rejected=pd.DataFrame({"module_id": ["bad-1", "bad-2"]}),
        issues=[],
    )
    metrics = calculate_quality_metrics(result)
    assert metrics.accepted_count == 3
    assert metrics.rejected_count == 2
    assert metrics.validity_rate == round(3 / 5, 4)
    assert metrics.mean_coverage == 66.67
    assert metrics.mean_bug_density == 2.5
    assert metrics.low_coverage_count == 1


def test_sample_quality_metrics(processed_sample):
    metrics = calculate_quality_metrics(processed_sample)
    assert metrics.accepted_count == 9
    assert metrics.rejected_count == 4
    assert metrics.validity_rate == round(9 / 13, 4)
    assert metrics.mean_coverage == 76.0
    assert metrics.mean_bug_density == 2.69
    assert metrics.low_coverage_count == 1
