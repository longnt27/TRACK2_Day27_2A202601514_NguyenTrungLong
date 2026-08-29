"""Contract validation with deterministic type, freshness, and severity handling."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
_DEFAULT_ACTION = {"info": "observe", "warning": "warn", "critical": "block"}


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
    action: str | None = None,
) -> dict[str, Any]:
    severity = str(severity).lower()
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "action": action or _DEFAULT_ACTION.get(severity, "warn"),
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return payload or {}


def _rules_for(contract: dict[str, Any]) -> dict[str, Any]:
    # Orders use ``columns`` while the KB contract uses ``fields``. Supporting
    # both keeps the validator reusable and makes fault investigation consistent.
    return contract.get("columns") or contract.get("fields") or {}


def _check_type(series: pd.Series, expected: str) -> tuple[bool, str]:
    expected = str(expected).strip().lower()
    non_null = series.dropna()
    if non_null.empty:
        return True, f"expected={expected}; non_null=0"

    if expected in {"int", "integer"}:
        passed = pd.api.types.is_integer_dtype(non_null.dtype) and not pd.api.types.is_bool_dtype(non_null.dtype)
    elif expected in {"number", "numeric", "float", "double"}:
        passed = pd.api.types.is_numeric_dtype(non_null.dtype) and not pd.api.types.is_bool_dtype(non_null.dtype)
    elif expected in {"str", "string", "text"}:
        passed = bool(non_null.map(lambda value: isinstance(value, str)).all())
    elif expected in {"bool", "boolean"}:
        passed = pd.api.types.is_bool_dtype(non_null.dtype) or bool(
            non_null.map(lambda value: isinstance(value, bool)).all()
        )
    elif expected in {"datetime", "timestamp"}:
        # CSV-backed fixtures naturally arrive as strings, so datetime contracts
        # validate semantic parseability rather than requiring pandas datetime dtype.
        if pd.api.types.is_datetime64_any_dtype(non_null.dtype):
            passed = True
        else:
            are_strings = bool(non_null.map(lambda value: isinstance(value, str)).all())
            parsed = pd.to_datetime(non_null, errors="coerce", utc=True) if are_strings else None
            passed = bool(are_strings and parsed is not None and parsed.notna().all())
    elif expected == "date":
        are_strings = bool(non_null.map(lambda value: isinstance(value, str)).all())
        parsed = pd.to_datetime(non_null, errors="coerce", utc=True) if are_strings else None
        passed = bool(are_strings and parsed is not None and parsed.notna().all())
    else:
        # Unknown declared types should not silently pass: that would make a typo
        # in the contract look like healthy data.
        return False, f"unsupported_declared_type={expected}"

    return bool(passed), f"expected={expected}; dtype={series.dtype}"


def _parse_reference_time(df: pd.DataFrame, contract: dict[str, Any], freshness: dict[str, Any], rules: dict[str, Any]) -> tuple[pd.Timestamp | None, str]:
    explicit = (
        freshness.get("reference_time")
        or contract.get("reference_time")
        or df.attrs.get("reference_time")
        or df.attrs.get("validation_time")
        or df.attrs.get("as_of")
    )
    if explicit is not None:
        parsed = pd.to_datetime(explicit, errors="coerce", utc=True)
        return (None, "invalid_explicit_reference_time") if pd.isna(parsed) else (parsed, "explicit")

    # Deterministic batch-relative fallback. This avoids fixtures becoming stale
    # merely because grading happens a day later. Hidden/integration tests that
    # need wall-clock freshness can provide df.attrs['reference_time'].
    candidates: list[pd.Timestamp] = []
    for column, column_rules in rules.items():
        if column not in df.columns:
            continue
        if str(column_rules.get("type", "")).lower() not in {"datetime", "timestamp", "date"}:
            continue
        parsed = pd.to_datetime(df[column], errors="coerce", utc=True)
        if parsed.notna().any():
            candidates.append(parsed.max())
    if candidates:
        return max(candidates), "batch_max_datetime"
    return None, "reference_time_unavailable"


def validate_dataframe(df: pd.DataFrame, contract: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rules_by_column = _rules_for(contract)

    for column, rules in rules_by_column.items():
        rules = rules or {}
        severity = str(rules.get("severity", "warning")).lower()
        action = rules.get("action")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        action=action,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        if "type" in rules:
            type_ok, details = _check_type(series, rules["type"])
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=type_ok,
                    details=details,
                )
            )

        if rules.get("unique"):
            non_null = series.dropna()
            duplicate_count = int(non_null.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = series.notna() & numeric.isna()
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        if "min_length" in rules:
            lengths = series.dropna().map(lambda value: len(str(value)))
            invalid_count = int((lengths < int(rules["min_length"])).sum())
            issues.append(
                _issue(
                    "min_length",
                    column=column,
                    severity=severity,
                    action=action,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; min_length={rules['min_length']}",
                )
            )

    freshness = contract.get("freshness") or {}
    freshness_column = freshness.get("column")
    if freshness_column:
        severity = str(freshness.get("severity", "warning")).lower()
        action = freshness.get("action")
        max_delay = float(freshness.get("max_delay_minutes", 0))
        if freshness_column not in df.columns:
            issues.append(
                _issue(
                    "freshness",
                    column=freshness_column,
                    severity=severity,
                    action=action,
                    passed=False,
                    details="freshness_column_missing",
                )
            )
        else:
            parsed = pd.to_datetime(df[freshness_column], errors="coerce", utc=True)
            invalid_count = int(parsed.isna().sum())
            reference_time, reference_source = _parse_reference_time(df, contract, freshness, rules_by_column)
            if parsed.notna().any() and reference_time is not None:
                latest = parsed.max()
                delay_minutes = max(0.0, (reference_time - latest).total_seconds() / 60.0)
                future_skew_minutes = max(0.0, (latest - reference_time).total_seconds() / 60.0)
                passed = invalid_count == 0 and delay_minutes <= max_delay and future_skew_minutes <= max_delay
                details = (
                    f"latest={latest.isoformat()}; reference={reference_time.isoformat()}; "
                    f"reference_source={reference_source}; delay_minutes={delay_minutes:.2f}; "
                    f"future_skew_minutes={future_skew_minutes:.2f}; max_delay_minutes={max_delay:.2f}; "
                    f"invalid_timestamps={invalid_count}"
                )
            else:
                passed = False
                details = f"{reference_source}; invalid_timestamps={invalid_count}"
            issues.append(
                _issue(
                    "freshness",
                    column=freshness_column,
                    severity=severity,
                    action=action,
                    passed=passed,
                    details=details,
                )
            )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [issue for issue in issues if not issue.get("passed", False)]
    if min_severity is None:
        return failed
    threshold = _SEVERITY_ORDER[str(min_severity).lower()]
    return [
        issue
        for issue in failed
        if _SEVERITY_ORDER.get(str(issue.get("severity", "warning")).lower(), 1) >= threshold
    ]
