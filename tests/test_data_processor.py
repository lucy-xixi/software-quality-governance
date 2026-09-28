"""Tests for loading, validating, cleaning, and transforming module records."""

import pandas as pd

from src.data_processor import clean_records, transform_records


def test_sample_splits_valid_and_rejected_rows(processed_sample):
    assert list(processed_sample.records["module_id"]) == [
        "billing-api",
        "billing-ui",
        "ledger",
        "notify",
        "auth",
        "search",
        "exports",
        "catalog",
        "invoicing",
    ]
    assert list(processed_sample.rejected["module_name"]) == [
        "Ghost",
        "Pricing",
        "Recs",
        "Admin",
    ]
    assert {(issue.column, issue.row_number, issue.message) for issue in processed_sample.issues} == {
        ("module_id", 11, "module_id is required"),
        ("lines_of_code", 12, "lines_of_code must be at least 1"),
        ("coverage_percent", 13, "coverage_percent must be between 0 and 100"),
        ("recorded_on", 14, "recorded_on must be YYYY-MM-DD"),
    }


def test_sample_cleans_text_and_review_status(processed_sample):
    rows = processed_sample.records.set_index("module_id")
    assert rows.loc["billing-api", "team"] == "payments"
    assert rows.loc["billing-ui", "module_name"] == "Billing UI"
    assert rows.loc["billing-ui", "review_status"] == "reviewed"
    assert rows.loc["search", "review_status"] == "pending"
    assert rows.loc["exports", "review_status"] == "waived"
    assert rows.loc["notify", "recorded_on"] == "2026-09-10"


def test_sample_adds_density_band_and_owner_flag(processed_sample):
    rows = processed_sample.records.set_index("module_id")
    assert rows.loc["billing-api", "bug_density"] == 1.43
    assert rows.loc["invoicing", "bug_density"] == 11.25
    assert rows.loc["exports", "bug_density"] == 0.67
    assert rows.loc["notify", "coverage_band"] == "high"
    assert rows.loc["billing-ui", "coverage_band"] == "medium"
    assert rows.loc["auth", "coverage_band"] == "low"
    assert bool(rows.loc["billing-ui", "has_owner"]) is False
    assert bool(rows.loc["notify", "has_owner"]) is True


def test_clean_and_transform_one_row():
    raw = pd.DataFrame(
        [
            {
                "module_id": " mod-1 ",
                "module_name": " Payments ",
                "team": " core ",
                "lines_of_code": "1000",
                "bug_count": "2",
                "coverage_percent": "80",
                "review_status": "In Review",
                "owner": "  ",
                "recorded_on": "2026-09-01",
            }
        ]
    )
    row = transform_records(clean_records(raw)).iloc[0]
    assert row["module_id"] == "mod-1"
    assert row["team"] == "core"
    assert row["review_status"] == "pending"
    assert row["lines_of_code"] == 1000
    assert row["bug_density"] == 2.0
    assert row["coverage_band"] == "high"
    assert bool(row["has_owner"]) is False
