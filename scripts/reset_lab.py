#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "baseline"
INCOMING = ROOT / "data" / "incoming"


def _batch_shift(
    df: pd.DataFrame,
    columns: list[str],
    target_age_minutes: int = 5,
) -> tuple[pd.DataFrame, pd.Timedelta]:
    """Re-anchor a fixture while preserving its original weekday.

    The synthetic history intentionally models lower weekend traffic. Moving a
    Friday batch to Saturday without changing its row count makes the supposedly
    healthy baseline look anomalous. We therefore move the batch to the most
    recent occurrence of its original weekday, retaining all relative timestamps.
    """
    parsed: list[pd.Series] = []
    for col in columns:
        if col in df.columns:
            parsed.append(pd.to_datetime(df[col], utc=True, errors="coerce"))
    valid = [series for series in parsed if series.notna().any()]
    if not valid:
        return df, pd.Timedelta(0)

    latest = max(series.max() for series in valid)
    now = pd.Timestamp(datetime.now(timezone.utc) - timedelta(minutes=target_age_minutes))
    days_back = (now.weekday() - latest.weekday()) % 7
    target = now - pd.Timedelta(days=days_back)
    delta = target - latest

    for col in columns:
        if col in df.columns:
            series = pd.to_datetime(df[col], utc=True, errors="coerce")
            df[col] = (series + delta).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return df, delta


def main() -> None:
    INCOMING.mkdir(parents=True, exist_ok=True)

    orders = pd.read_csv(BASE / "orders.csv")
    orders, batch_delta = _batch_shift(
        orders,
        ["created_at", "updated_at"],
        target_age_minutes=5,
    )
    orders.to_csv(INCOMING / "orders.csv", index=False)

    shutil.copy2(BASE / "customers.csv", INCOMING / "customers.csv")

    docs = []
    with open(BASE / "kb_documents.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                docs.append(json.loads(line))

    # Apply the same temporal shift as the order batch. This keeps the healthy KB
    # publication lag deterministic and makes stale_kb (-3h) a real fault rather
    # than an artifact of whichever day the lab is executed.
    for doc in docs:
        published = pd.to_datetime(doc.get("published_at"), utc=True, errors="coerce")
        if not pd.isna(published):
            doc["published_at"] = (published + batch_delta).isoformat()

    with open(INCOMING / "kb_documents.jsonl", "w", encoding="utf-8") as f:
        for row in docs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Keep dbt seeds synchronized with current incoming data.
    seeds = ROOT / "dbt_project" / "seeds"
    seeds.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INCOMING / "orders.csv", seeds / "orders.csv")
    shutil.copy2(INCOMING / "customers.csv", seeds / "customers.csv")

    metrics = ROOT / "reports" / "latest_metrics.json"
    if metrics.exists():
        metrics.unlink()
    print("Lab reset to a healthy baseline.")


if __name__ == "__main__":
    main()
