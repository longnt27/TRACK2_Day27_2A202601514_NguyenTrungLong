"""Robust anomaly detection for operational metrics."""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _values(history: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(history), dtype=float)
    return arr[np.isfinite(arr)]


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = _values(history)
    current = float(current)
    if not np.isfinite(current):
        return {"is_anomaly": True, "score": float("inf"), "method": "zscore", "reason": "current_not_finite"}
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if np.isclose(std, 0.0):
        score = float("inf") if not np.isclose(current, mean) else 0.0
    else:
        score = abs(current - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.6g}, std={std:.6g}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    values = _values(history)
    current = float(current)
    if not np.isfinite(current):
        return {"is_anomaly": True, "score": float("inf"), "method": "mad", "reason": "current_not_finite"}
    if values.size < 5:
        result = zscore_detector(current, values, threshold=3.0)
        result["method"] = "mad:fallback_zscore"
        return result

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if np.isclose(mad, 0.0):
        q25, q75 = np.quantile(values, [0.25, 0.75])
        robust_sigma = float((q75 - q25) / 1.349)
        if np.isclose(robust_sigma, 0.0):
            robust_sigma = float(np.std(values))
        if np.isclose(robust_sigma, 0.0):
            robust_sigma = max(abs(median) * 0.01, 1e-9)
        score = abs(current - median) / robust_sigma
        return {
            "is_anomaly": bool(score > threshold),
            "score": float(score),
            "method": "mad:zero_mad_fallback",
            "reason": f"median={median:.6g}, scale={robust_sigma:.6g}, threshold={threshold}",
        }

    modified_z = 0.67448975 * abs(current - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.6g}, mad={mad:.6g}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    method = str(method).lower()
    context = context or {}
    history_values = list(history)

    if method == "zscore":
        return zscore_detector(current, history_values, threshold=threshold)
    if method == "mad":
        return mad_detector(current, history_values)
    if method != "auto":
        raise ValueError(f"Unsupported method: {method}")

    segment_history = context.get("same_segment_history")
    if segment_history is not None:
        segment_values = _values(segment_history)
        if segment_values.size >= 3:
            result = mad_detector(current, segment_values) if segment_values.size >= 5 else zscore_detector(current, segment_values, threshold=threshold)
            result["method"] = f"auto:segment_{result['method']}"
            result["reason"] += f"; segment_n={segment_values.size}"
            if context.get("known_event"):
                result["reason"] += f"; known_event={context['known_event']}"
            return result

    values = _values(history_values)
    if values.size >= 5:
        result = mad_detector(current, values)
        result["method"] = f"auto:{result['method']}"
    else:
        result = zscore_detector(current, values, threshold=threshold)
        result["method"] = "auto:zscore"

    if context.get("day_of_week") is not None:
        result["reason"] += f"; day_of_week={context['day_of_week']}; no_segment_history"
    if context.get("metric_name"):
        result["metric"] = str(context["metric_name"])
    if context.get("known_event"):
        result["reason"] += f"; known_event={context['known_event']}"
    return result
