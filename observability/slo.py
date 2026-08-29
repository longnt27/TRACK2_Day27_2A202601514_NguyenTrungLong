from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")

    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }

    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    remaining = max(0.0, 1.0 - burn_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": remaining,
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre",
) -> dict[str, Any]:
    """Evaluate a compact multi-window SRE burn-rate policy."""
    short = float(short_window_burn)
    long = float(long_window_burn)
    if short < 0 or long < 0:
        raise ValueError("burn rates must be non-negative")

    if short >= 14.4 and long >= 6.0:
        page, severity, reason = True, "critical", "sustained_fast_burn"
    elif short >= 6.0 and long >= 3.0:
        page, severity, reason = True, "warning", "sustained_elevated_burn"
    elif short >= 14.4 and long < 3.0:
        page, severity, reason = False, "info", "transient_short_window_spike"
    elif long >= 6.0 and short < 3.0:
        page, severity, reason = False, "info", "long_window_burn_recovering"
    else:
        page, severity, reason = False, "info", "burn_within_page_policy"

    return {
        "page": page,
        "severity": severity,
        "reason": reason,
        "short_window_burn": short,
        "long_window_burn": long,
        "policy": policy,
        "thresholds": {
            "critical_short": 14.4,
            "critical_long": 6.0,
            "warning_short": 6.0,
            "warning_long": 3.0,
        },
    }
