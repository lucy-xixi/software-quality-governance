"""Shared fixtures for the analytical service tests."""

from pathlib import Path

import pytest

from src.data_processor import process_quality_data

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "module_quality.csv"


@pytest.fixture
def processed_sample():
    """Module quality sample after validation, cleaning, and transformation."""
    return process_quality_data(SAMPLE_PATH)
