"""Load, validate, clean, and transform module quality records."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "module_id",
    "module_name",
    "team",
    "lines_of_code",
    "bug_count",
    "coverage_percent",
    "review_status",
    "owner",
    "recorded_on",
]

RESULT_COLUMNS = REQUIRED_COLUMNS + ["bug_density", "coverage_band", "has_owner"]

# Accepted review labels, including a few common aliases from source exports.
STATUS_ALIASES = {
    "reviewed": "reviewed",
    "review": "reviewed",
    "pending": "pending",
    "in review": "pending",
    "waived": "waived",
    "n/a": "waived",
}

HIGH_COVERAGE = 80.0
MEDIUM_COVERAGE = 60.0


@dataclass(frozen=True)
class ValidationIssue:
    """One field problem on a source row. Row numbers match the CSV file."""

    row_number: int
    column: str
    message: str


@dataclass(frozen=True)
class ProcessingResult:
    """Accepted records, rejected source rows, and the validation issues."""

    records: pd.DataFrame
    rejected: pd.DataFrame
    issues: list[ValidationIssue]


def load_records(path: str | Path) -> pd.DataFrame:
    """Read a module quality CSV. All values are kept as text for validation."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Quality data file not found: {file_path}")
    if file_path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file, got: {file_path.name}")
    frame = pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    return frame.loc[:, REQUIRED_COLUMNS].reset_index(drop=True)


def validate_records(frame: pd.DataFrame) -> list[ValidationIssue]:
    """Return every validation issue in the frame, including duplicate ids."""
    issues = _duplicate_issues(frame)
    for index, row in frame.iterrows():
        issues.extend(validate_row(row, int(index) + 2))
    return issues


def validate_row(row: pd.Series, row_number: int) -> list[ValidationIssue]:
    """Validate one source row. An empty list means the row is acceptable."""
    issues: list[ValidationIssue] = []

    if not _text(row.get("module_id")):
        issues.append(ValidationIssue(row_number, "module_id", "module_id is required"))
    if not _text(row.get("module_name")):
        issues.append(ValidationIssue(row_number, "module_name", "module_name is required"))
    if not _text(row.get("team")):
        issues.append(ValidationIssue(row_number, "team", "team is required"))

    lines_of_code = _parse_int(row.get("lines_of_code"))
    if lines_of_code is None:
        issues.append(
            ValidationIssue(row_number, "lines_of_code", "lines_of_code must be a whole number")
        )
    elif lines_of_code < 1:
        issues.append(
            ValidationIssue(row_number, "lines_of_code", "lines_of_code must be at least 1")
        )

    bug_count = _parse_int(row.get("bug_count"))
    if bug_count is None:
        issues.append(ValidationIssue(row_number, "bug_count", "bug_count must be a whole number"))
    elif bug_count < 0:
        issues.append(ValidationIssue(row_number, "bug_count", "bug_count cannot be negative"))

    coverage = _parse_float(row.get("coverage_percent"))
    if coverage is None:
        issues.append(
            ValidationIssue(row_number, "coverage_percent", "coverage_percent must be a number")
        )
    elif coverage < 0 or coverage > 100:
        issues.append(
            ValidationIssue(
                row_number,
                "coverage_percent",
                "coverage_percent must be between 0 and 100",
            )
        )

    if _normalize_status(row.get("review_status")) is None:
        issues.append(
            ValidationIssue(row_number, "review_status", "review_status is not recognized")
        )

    if _parse_date(row.get("recorded_on")) is None:
        issues.append(
            ValidationIssue(row_number, "recorded_on", "recorded_on must be YYYY-MM-DD")
        )

    return issues


def clean_records(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim text, normalize review status, and parse numbers and dates."""
    return pd.DataFrame(
        {
            "module_id": frame["module_id"].map(_text),
            "module_name": frame["module_name"].map(_text),
            "team": frame["team"].map(_text),
            "lines_of_code": frame["lines_of_code"].map(_parse_int),
            "bug_count": frame["bug_count"].map(_parse_int),
            "coverage_percent": frame["coverage_percent"].map(_parse_float),
            "review_status": frame["review_status"].map(_normalize_status),
            "owner": frame["owner"].map(_text),
            "recorded_on": frame["recorded_on"].map(_normalize_date),
        }
    )


def transform_records(frame: pd.DataFrame) -> pd.DataFrame:
    """Add bug density, a coverage band, and an ownership flag."""
    transformed = frame.copy()
    transformed["bug_density"] = [
        _bug_density(lines_of_code, bug_count)
        for lines_of_code, bug_count in zip(
            transformed["lines_of_code"],
            transformed["bug_count"],
            strict=True,
        )
    ]
    transformed["coverage_band"] = transformed["coverage_percent"].map(_coverage_band)
    transformed["has_owner"] = transformed["owner"].map(lambda owner: bool(_text(owner)))
    return transformed.loc[:, RESULT_COLUMNS].reset_index(drop=True)


def process_quality_data(path: str | Path) -> ProcessingResult:
    """Load a CSV and return cleaned records plus the rows that failed validation."""
    raw = load_records(path)
    issues = validate_records(raw)
    rejected_rows = {issue.row_number for issue in issues}
    row_numbers = raw.index.to_series().add(2)
    rejected_mask = row_numbers.isin(rejected_rows)
    rejected = raw.loc[rejected_mask].reset_index(drop=True)
    accepted = raw.loc[~rejected_mask].reset_index(drop=True)
    if accepted.empty:
        return ProcessingResult(_empty_records(), rejected, issues)
    return ProcessingResult(transform_records(clean_records(accepted)), rejected, issues)


def summarize_validation_issues(issues: list[ValidationIssue]) -> dict[str, int]:
    """Count validation issues by column for a governance report."""
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.column] = counts.get(issue.column, 0) + 1
    return dict(sorted(counts.items()))


def _duplicate_issues(frame: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    first_seen: dict[str, int] = {}
    for index, row in frame.iterrows():
        module_id = _text(row.get("module_id"))
        if not module_id:
            continue
        row_number = int(index) + 2
        if module_id in first_seen:
            issues.append(
                ValidationIssue(
                    row_number,
                    "module_id",
                    f"duplicate module_id '{module_id}'",
                )
            )
        else:
            first_seen[module_id] = row_number
    return issues


def _empty_records() -> pd.DataFrame:
    return pd.DataFrame(columns=RESULT_COLUMNS)


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _parse_int(value: object) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer():
        return None
    return int(number)


def _parse_float(value: object) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_status(value: object) -> str | None:
    key = _text(value).lower()
    if not key:
        return None
    return STATUS_ALIASES.get(key)


def _parse_date(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def _normalize_date(value: object) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return ""
    return parsed.strftime("%Y-%m-%d")


def _bug_density(lines_of_code: object, bug_count: object) -> float | None:
    if pd.isna(lines_of_code) or pd.isna(bug_count):
        return None
    lines = int(lines_of_code)
    bugs = int(bug_count)
    if lines <= 0:
        return None
    return round(bugs / lines * 1000, 2)


def _coverage_band(coverage: object) -> str:
    if pd.isna(coverage):
        return "unknown"
    value = float(coverage)
    if value >= HIGH_COVERAGE:
        return "high"
    if value >= MEDIUM_COVERAGE:
        return "medium"
    return "low"
