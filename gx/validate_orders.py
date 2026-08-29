#!/usr/bin/env python3
"""Great Expectations Suite -> ValidationDefinition -> Checkpoint example."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_checkpoint(context):
    data_source = context.data_sources.add_pandas("orders_pandas")
    asset = data_source.add_dataframe_asset(name="orders_dataframe")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_orders")

    suite = context.suites.add(gx.ExpectationSuite(name="orders_contract_suite"))
    for expectation in [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id", severity="critical"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id", severity="critical"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id", severity="critical"),
        gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0, severity="critical"),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="currency", value_set=["USD", "VND"], severity="critical"
        ),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
            severity="warning",
        ),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="updated_at", severity="critical"),
    ]:
        suite.add_expectation(expectation)

    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="orders_validation",
            data=batch_definition,
            suite=suite,
        )
    )

    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="orders_checkpoint",
            validation_definitions=[validation_definition],
            actions=[
                gx.checkpoint.actions.UpdateDataDocsAction(name="update_all_data_docs")
            ],
            result_format="SUMMARY",
        )
    )
    return checkpoint


def main() -> None:
    df = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")
    context = gx.get_context()
    checkpoint = build_checkpoint(context)
    result = checkpoint.run(batch_parameters={"dataframe": df})

    print(result.describe())
    print("\nGX checkpoint result:", "PASS" if result.success else "FAIL")
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
