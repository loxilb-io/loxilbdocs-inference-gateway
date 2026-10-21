# Verify KV Routing and Diagnose Fallback

Check configuration, effective profile binding, event ingestion, routing
engagement, and backend delivery separately. A successful request or nonempty
inventory does not prove that the intended cache-aware path was used.

## Before measuring

Use the version-pinned [model and engine guide](../use-cases/model-engine-standard/matrix-manual.md)
and the selected [engine contract](../ai-gateway/engine-contracts.md). Compare
actual tokenizer, block geometry, hash/seed inputs, event transport, and
endpoint topology. Do not copy defaults from another engine or release.

For profile-bound services, check [KV-exact readiness](../ai-gateway/model-profiles-kv-readiness.md)
and the expected profile/generation, API mode, reason codes, and enforcement
state. Use [authenticated metric export](monitoring.md#enable-and-scrape-metrics)
for the following observations.

## Observe engagement

| Observation | What it establishes | What to check next |
|---|---|---|
| Subscriber connection count | Transport connections exist | Each required publisher/rank and its actual event delivery |
| `loxilb_pd_kv_blocks` | Gateway has endpoint inventory | Whether it matches the model/profile and repeated prompt blocks |
| Positive `loxilb_pd_kv_tier15_hits_total` delta | Cache-scoring hits were recorded | Independent endpoint receipts and expected routing under controlled traffic |
| Fallthrough and miss-reason deltas | Requests used a fallback path | Correlate the reason with configuration, inventory, and endpoint eligibility |

Observe matching inventory, then send controlled repeated-prefix requests and
compare before/after counters. A first cold request need not produce a hit.
A flat hit counter requires diagnosis and does not identify a single cause.
The expected subscriber count depends on the engine, endpoint roles, and DP
rank topology. Listener presence alone does not prove valid event ingestion.

## Evidence and cleanup

Retain sanitized request outcomes, endpoint receipts, effective binding, and
metric deltas for the same test window. Successful routing evidence does not
establish cache reuse, latency benefit, capacity, or loss-free failover. Include
negative and recovery checks from the [verification guide](../use-cases/model-engine-standard/verify.md#negative-and-recovery-checks).
Remove only owned test resources after checking their identity.
