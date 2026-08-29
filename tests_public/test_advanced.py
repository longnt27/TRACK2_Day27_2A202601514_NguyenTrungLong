from pathlib import Path

import pandas as pd

from student_api import (
    column_downstream,
    detect_distribution,
    detect_metric,
    multiwindow_burn,
    rag_embedding_shift,
    validate_orders,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "orders_contract.yaml"


def _orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order_id": 1,
                "customer_id": "C1",
                "amount": 10.0,
                "currency": "USD",
                "status": "completed",
                "created_at": "2026-08-28T10:00:00Z",
                "updated_at": "2026-08-28T10:05:00Z",
            },
            {
                "order_id": 2,
                "customer_id": "C2",
                "amount": 20.0,
                "currency": "USD",
                "status": "pending",
                "created_at": "2026-08-28T10:01:00Z",
                "updated_at": "2026-08-28T10:06:00Z",
            },
        ]
    )


def test_type_drift_and_explicit_freshness_are_detected():
    df = _orders()
    df["order_id"] = df["order_id"].astype(str)
    df.attrs["reference_time"] = "2026-08-28T11:00:00Z"
    failed = [issue for issue in validate_orders(df, CONTRACT) if not issue["passed"]]
    assert any(issue["check"] == "type" and issue["column"] == "order_id" for issue in failed)
    assert any(issue["check"] == "freshness" for issue in failed)


def test_auto_anomaly_uses_same_segment_history():
    result = detect_metric(
        430,
        [1000, 1020, 990, 1010, 1005, 420, 430],
        method="auto",
        context={"day_of_week": 6, "same_segment_history": [400, 410, 420, 430, 440, 415]},
    )
    assert result["is_anomaly"] is False
    assert "segment" in result["method"]


def test_zero_variance_baseline_still_detects_departure():
    assert detect_metric(800, [100, 100, 100, 100, 100], method="auto")["is_anomaly"] is True


def test_distribution_shape_shift_with_similar_mean_is_detected():
    baseline = [0, 0, 0, 0, 0, 0]
    current = [-10, -10, -10, 10, 10, 10]
    assert detect_distribution(current, baseline)["is_anomaly"] is True


def test_multiwindow_burn_ignores_spike_but_pages_sustained_burn():
    assert multiwindow_burn(20, 1)["page"] is False
    assert multiwindow_burn(20, 8)["page"] is True


def test_column_lineage_is_transitive_and_cycle_safe():
    graph = {"a.x": ["b.x"], "b.x": ["c.x"], "c.x": ["a.x", "d.x"]}
    assert column_downstream(graph, "a.x") == ["b.x", "c.x", "d.x"]


def test_embedding_norm_shift_is_detected():
    result = rag_embedding_shift(
        [2.0, 2.1, 1.9, 2.05, 1.95],
        [1.0, 1.01, 0.99, 1.02, 0.98],
    )
    assert result["is_anomaly"] is True
    assert result["method"].startswith("embedding_norm:")
