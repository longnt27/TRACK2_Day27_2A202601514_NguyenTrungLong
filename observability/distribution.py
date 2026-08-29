from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _finite(values: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    return arr[np.isfinite(arr)]


def _ks_distance(a: np.ndarray, b: np.ndarray) -> float:
    points = np.sort(np.unique(np.concatenate([a, b])))
    if points.size == 0:
        return 0.0
    a_sorted = np.sort(a)
    b_sorted = np.sort(b)
    cdf_a = np.searchsorted(a_sorted, points, side="right") / a_sorted.size
    cdf_b = np.searchsorted(b_sorted, points, side="right") / b_sorted.size
    return float(np.max(np.abs(cdf_a - cdf_b)))


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect location and shape drift without a SciPy dependency."""
    cur = _finite(current_values)
    base = _finite(baseline_values)
    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "ks_robust", "reason": "empty_or_nonfinite_input"}

    ks = _ks_distance(cur, base)
    ks_critical = min(1.0, 1.36 * np.sqrt((cur.size + base.size) / (cur.size * base.size)))
    ks_ratio = ks / ks_critical if ks_critical > 0 else 0.0

    base_median = float(np.median(base))
    cur_median = float(np.median(cur))
    base_mad = float(np.median(np.abs(base - base_median)))
    scale = 1.4826 * base_mad
    if np.isclose(scale, 0.0):
        scale = float(np.std(base))
    if np.isclose(scale, 0.0):
        scale = max(abs(base_median) * 0.01, 1e-9)

    median_effect = abs(cur_median - base_median) / scale
    base_q = np.quantile(base, [0.1, 0.9])
    cur_q = np.quantile(cur, [0.1, 0.9])
    quantile_effect = float(np.max(np.abs(cur_q - base_q)) / scale)

    shifted = (ks > ks_critical) or (median_effect >= ratio_threshold) or (quantile_effect >= ratio_threshold)
    score = max(ks_ratio, median_effect, quantile_effect)
    return {
        "is_anomaly": bool(shifted),
        "score": float(score),
        "method": "ks_robust",
        "reason": (
            f"ks={ks:.4f}, ks_critical={ks_critical:.4f}, "
            f"median_effect={median_effect:.3f}, quantile_effect={quantile_effect:.3f}, "
            f"baseline_n={base.size}, current_n={cur.size}"
        ),
    }
