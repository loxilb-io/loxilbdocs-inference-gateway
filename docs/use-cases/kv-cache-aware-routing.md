# KV Routing: Updated Locations

This page has been consolidated. Continue to the [current documentation](../concepts/kv-routing.md).

## Before you start

Choose an engine/profile hash contract and a complete deployment runbook first.

**Focus of this page:** Distinguish Gateway prefix-based selection from native engine cache reuse.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/llm-reference.md"

This reference diagram locates the client, Gateway and engine evidence. It does not prescribe a replica count or promote historical results to a new topology. Use the exact worker count, roles, ports and artifact identities from the selected runbook or retained result; do not mix that tuple with another guide.

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Reading path and reference

### Previous section links

<a id="kv-cache-aware-routing"></a>

[Continue: kv cache aware routing](../concepts/kv-routing.md)

<a id="1-what-it-is-and-where-it-sits"></a>

[Continue: 1 what it is and where it sits](../concepts/kv-routing.md)

<a id="2-architecture-inventory-in-go-decision-in-c"></a>

[Continue: 2 architecture inventory in go decision in c](../concepts/kv-routing.md)

<a id="3-what-exactly-is-synced-and-why-it-is-tiny"></a>

[Continue: 3 what exactly is synced and why it is tiny](../concepts/kv-routing.md)

<a id="consistency-model"></a>

[Continue: consistency model](../concepts/kv-routing.md)

<a id="4-end-to-end-call-flow"></a>

[Continue: 4 end to end call flow](../concepts/kv-routing.md)

<a id="worked-example-two-prompts-end-to-end"></a>

[Continue: worked example two prompts end to end](../concepts/kv-routing.md)

<a id="5-the-vllm-block-hash-parity-contract"></a>

[Continue: 5 the vllm block hash parity contract](../ai-gateway/engine-contracts.md)

<a id="6-parity-preflight-inspect-what-is-actually-running"></a>

[Continue: 6 parity preflight inspect what is actually running](../ai-gateway/engine-contracts.md)

<a id="61-the-parity-triad-as-an-operational-checklist"></a>

[Continue: 61 the parity triad as an operational checklist](../concepts/kv-routing.md)

<a id="62-the-read-only-preflight-read-the-live-container-not-the-script"></a>

[Continue: 62 the read only preflight read the live container not the script](../concepts/kv-routing.md)

<a id="63-tested-artifact-rule"></a>

[Continue: 63 tested artifact rule](../concepts/kv-routing.md)

<a id="64-vllm-metric-families-the-collector-needs"></a>

[Continue: 64 vllm metric families the collector needs](../concepts/kv-routing.md)

<a id="65-loxilb-runtime-env-worth-setting-explicitly"></a>

[Continue: 65 loxilb runtime env worth setting explicitly](../concepts/kv-routing.md)

<a id="7-guard-ladder-miss-reasons"></a>

[Continue: 7 guard ladder miss reasons](../operations/kv-routing-verification.md)

<a id="8-configuration"></a>

[Continue: 8 configuration](model-engine-standard/matrix-manual.md)

<a id="81-rest-the-load-balancer-rule"></a>

[Continue: 81 rest the load balancer rule](../concepts/kv-routing.md)

<a id="82-environment-variables-loxilb-process"></a>

[Continue: 82 environment variables loxilb process](../concepts/kv-routing.md)

<a id="83-tokenizer-staging"></a>

[Continue: 83 tokenizer staging](../concepts/kv-routing.md)

<a id="84-vllm-side-must-match-the-rule"></a>

[Continue: 84 vllm side must match the rule](../concepts/kv-routing.md)

<a id="85-onboarding-a-new-model-one-model-per-rule"></a>

[Continue: 85 onboarding a new model one model per rule](../concepts/kv-routing.md)

<a id="9-verify-it-actually-fired-the-mandatory-post-config-check"></a>

[Continue: 9 verify it actually fired the mandatory post config check](../operations/kv-routing-verification.md)

<a id="91-step-1-the-engagement-assertion-on-get-netloxv1metrics"></a>

[Continue: 91 step 1 the engagement assertion on get netloxv1metrics](../concepts/kv-routing.md)

<a id="92-step-2-inventory-check"></a>

[Continue: 92 step 2 inventory check](../concepts/kv-routing.md)

<a id="93-step-3-subscriber-count"></a>

[Continue: 93 step 3 subscriber count](../concepts/kv-routing.md)

<a id="94-step-4-publisher-side-sanity-on-the-engine-host"></a>

[Continue: 94 step 4 publisher side sanity on the engine host](../concepts/kv-routing.md)

<a id="10-verify-inventory-metrics-reference"></a>

[Continue: 10 verify inventory metrics reference](../operations/kv-routing-verification.md)

<a id="101-inspect-the-live-inventory"></a>

[Continue: 101 inspect the live inventory](../concepts/kv-routing.md)

<a id="102-prometheus-metrics"></a>

[Continue: 102 prometheus metrics](../concepts/kv-routing.md)

<a id="103-healthy-warm-route-signature"></a>

[Continue: 103 healthy warm route signature](../concepts/kv-routing.md)

<a id="11-troubleshoot"></a>

[Continue: 11 troubleshoot](../operations/kv-routing-verification.md)

<a id="12-known-limits"></a>

[Continue: 12 known limits](../operations/kv-routing-verification.md)

<a id="load-blind-argmax-capacity-weighted-blend"></a>

[Continue: load blind argmax capacity weighted blend](../concepts/kv-routing.md)

<a id="13-advanced-ai-controller-experimental"></a>

[Continue: 13 advanced ai controller experimental](advanced-cache-integrations.md)

<a id="14-advanced-lmcache-tiered-cache"></a>

[Continue: 14 advanced lmcache tiered cache](advanced-cache-integrations.md)

<a id="related"></a>

[Continue: related](../concepts/kv-routing.md)

## Check your result

Validate metadata readiness, actual endpoint placement and engine-side reuse separately.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](model-engine-standard/lifecycle.md) when ending the run.
