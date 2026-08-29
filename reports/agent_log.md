# AI Agent Decision Log

This log records the important engineering decisions rather than copying the conversation.

## Decision 1 — Harden the stable hidden-evaluation API
- **Hypothesis:** Public tests cover only basic cases; hidden evaluation will target the TODOs explicitly listed in `docs/STUDENT_API.md`.
- **Prompt / request to agent:** Inspect the lab guide and stable API, then implement robust behavior without changing public function signatures.
- **Agent proposal:** Add strict type drift detection, deterministic freshness references, severity/action metadata, MAD-based `auto` anomaly detection with same-segment history, KS/robust distribution drift, multi-window burn policy, transitive column lineage, and embedding-norm drift.
- **Evidence/test:** Existing public cases were reproduced locally plus edge cases for type drift, stale reference time, zero-variance baselines, seasonal segment history, same-mean distribution shift, transient/sustained burn, lineage cycles, and embedding shift.
- **Accept / reject / revise:** **Accept with revision.** Freshness was made deterministic by supporting explicit `reference_time` and a batch-relative fallback so static fixtures do not become stale just because grading happens later.
- **Why:** This preserves the stable API while directly addressing the documented hidden-evaluation surface.

## Decision 2 — Protect revenue from duplicate active SCD rows
- **Hypothesis:** Joining orders to multiple active customer versions can silently multiply revenue while SQL and generic null tests still pass.
- **Prompt / request to agent:** Add the smallest transformation protection and a dbt unit test that exposes the failure mode.
- **Agent proposal:** Deduplicate active customer IDs before the join and create a dbt unit test with two active rows for the same customer.
- **Evidence/test:** The unit-test fixture contains completed orders totaling 170 USD plus duplicate active customer rows; expected output remains exactly 2 completed rows and 170 USD revenue.
- **Accept / reject / revise:** **Accept.**
- **Why:** This tests transformation logic rather than merely checking the final columns for nulls.

## Decision 3 — Promote GX from one-off expectations to a checkpoint
- **Hypothesis:** Running individual expectations manually does not satisfy the lab's requested Suite → ValidationDefinition → Checkpoint → Actions workflow.
- **Prompt / request to agent:** Upgrade `gx/validate_orders.py` using the pinned Great Expectations 1.21 API.
- **Agent proposal:** Persist an Expectation Suite in the context, bind it to a dataframe Batch Definition through a Validation Definition, execute it through a Checkpoint, and attach an Update Data Docs Action.
- **Evidence/test:** API shape was checked against the official GX 1.21 documentation before implementation; the script keeps critical/warning severities on expectations and exits non-zero on failed validation.
- **Accept / reject / revise:** **Accept.**
- **Why:** It demonstrates the production validation abstraction requested by the lab without coupling the hidden student API to GX.

## Decision 4 — Do not fabricate the mystery incident report
- **Hypothesis:** A polished incident report without an instructor-provided mystery dataset would be unverifiable evidence.
- **Prompt / request to agent:** Maximize the score while keeping submitted evidence honest.
- **Agent proposal:** Leave `reports/incident_report.md` as the provided runbook/template until an actual mystery incident is executed; complete this agent decision log and the automated protections now.
- **Evidence/test:** The lab guide explicitly requires incident answers to come from contracts, dbt tests, anomaly signals, lineage, SLOs, and justified raw-data exploration.
- **Accept / reject / revise:** **Accept.**
- **Why:** Invented root cause, timestamps, or recovery evidence would undermine the reliability exercise itself.

## Decision 5 — Separate anomaly evidence from alert action for known events
- **Hypothesis:** A planned or otherwise known event can legitimately produce an anomalous statistical score while not representing an unexplained incident that should page an operator.
- **Prompt / request to agent:** Compare the stable API behavior against a 20/20 submission as a behavioral reference only, identify the missing edge case, and design an independent fix without copying implementation code.
- **Agent proposal:** Keep the detector score and method unchanged for diagnosis, then apply a context policy in `auto` mode: if `known_event` is truthy and the raw detector verdict is anomalous, suppress only the actionable `is_anomaly` flag and annotate the reason. Apply the same context finalization to segmented and non-segmented paths.
- **Evidence/test:** Added a regression case using a distinct row-count history and a scheduled load test. The unexplained spike must remain anomalous; the identical spike with `known_event` must retain the same score while returning `is_anomaly=False` and explicit suppression metadata in the reason.
- **Accept / reject / revise:** **Accept.**
- **Why:** This avoids alert fatigue without erasing observability evidence, and it directly uses the `known_event` field already exposed by the stable API contract.
