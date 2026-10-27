# Verification To-do: Every Model, Engine and Routing Mode

<!-- example-status-default: illustrative-only -->

Every unverified RR or Exact selection in [model and engine selection](matrix-manual.md)
is a **qualification task to complete**. Providing both modes is a documentation
deliverable; proving them on the actual model/engine/Gateway tuple is a separate
runtime deliverable. This public checklist states the current gaps, prerequisites
and acceptance evidence so operators know what remains before adoption.

**Reviewed 2026-10-20.** The original five-model campaign now has separate
runtime verdicts for all 30 mode cases. See the [operator manual and result table](results.md#matrix-results)
and [sanitized evidence summary](../../assets/model-engine-standard/matrix-results.json).
The results distinguish bounded functional PASS from native architecture blockers;
none closes production/release or load/fault qualification.

## Before you start

Start from the retained result ledger and choose a concrete missing acceptance gate.

**Focus of this page:** Identify the topology, stimulus and independent observation needed to close that gate.

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

### Original five cards: completed functional checks and open gates

The current evaluation profiles/manifests/fixtures are supplied separately from
the upstream catalog. The earlier “publish missing profile” prerequisite is now
resolved for this QA package; it is not a catalog promotion. The matrix uses
vLLM 0.31.0, SGLang 0.5.19 and TRT rc29/PyTorch. Each RR/Exact result remains
independent. Historical recommendation/reference classes are retained separately.

For every functional PASS, remaining work includes:

- Capacity, long-output/concurrent traffic and application SLO on the intended GPU.
- Owned worker loss, survivor receipts, immediate/later recovery and redistribution.
- Cancellation, resource return and long-running leak/handle observations.
- Fault-injected RR→Exact→RR switching, retained-state rollback and repeatable clean replay; the recorded fault-free mode checks remain bounded PASS.
- Approved release image, actual host data plane and HA qualification where applicable.
- Independent rerun and formal release-catalog promotion by the product owners.

For TRT Gemma2 and EXAONE3.5, the pinned PyTorch executor rejects the native
architecture before loading weights. Close this blocker only with a separately
supported backend/image/checkpoint tuple and fresh native **and** Gateway RR/Exact
evidence. Changing a profile name or bypassing strict mode cannot fix a native
loader. Other TRT backends are unqualified here, not declared universally unsupported.

Gemma's original normal-completion load RED remains open. Preserve failed raw
runs and successful-subset accounting; low-concurrency functional PASS does not
resolve its capacity/root-cause question. Product findings are handed to the
internal development team; QA does not patch engine or Gateway code to pass.

### Separate development request: SGLang tagged-map events

The [SGLang compatibility note](sglang-compatibility.md) records the preserved
0.5.21 wire/Exact failure and development acceptance criteria. The current
operator baseline is the verified **0.5.19 tagged-array** tuple.
A future tagged-map implementation requires its own product candidate and fresh
QA; it is not a prerequisite for following the compatible-version manual.

### Separate public-catalog example: six additional cases

The [R1 1.5B evidence archive](routing-choice.md) retains separately scoped
results and old paired inputs, not the current setup procedure for the 7B row above.
Candidate source status is unchanged by retaining these examples.

| Framework | RR case | Exact case |
|---|---|---|
| vLLM 0.31.0 | Bounded GPU QA: 12/12 completed, four receipts per worker; lifecycle checks executed | Separate evaluation manifest: READY, 12/12 prewarmed-worker receipts and cache-hit delta 12; full qualification still open |
| SGLang v0.5.18 | Not run on this documentation deployment; qualify paired RR body | Not run; stage candidate profile, prove rank/event/hash/token parity and READY |
| TRT 1.3.0rc24 | Matching image provisioning required before runtime | Same image prerequisite, then single-consumer HTTP events, READY and traffic engagement |

A backend/image prerequisite must stay visible. In particular, TRT's installer
`SKIP_NO_PULLABLE_IMAGE` is not a successful engine start. Do not substitute an
rc29 image and retain an rc24 success label.

### Execution order and closure criteria

For each model/engine, qualify RR and Exact as separately labeled runs on the
same immutable tuple and workload wherever possible. Keep the engine's native
prefix cache/block reuse enabled in both arms. Record case mode, topology,
images/revisions, source, effective arguments and host/GPU/runtime inventory.

1. **Resolve prerequisites.** Obtain model access, artifact/image identity,
   supported backend, adequate allocation and a reproducible launch. For Exact,
   obtain published matching model profile, engine manifest, tokenizer/template
   hashes, probe fixtures and event configuration. Never turn a missing asset
   into a pass or silently change the model/engine version.
2. **Verify engine serving.** On every worker require health after loading,
   exact model identity, direct completed chat/SSE and worker-owned correlated
   request receipts. A listener, `/v1/models` or container `Up` alone is insufficient.
3. **Verify selected routing.** RR must store `kvExactMode:0` without strict
   profile fields and actually deliver fresh requests to eligible workers.
   Exact must bind the correct model/profile/generation/API, reach `READY` with
   unfenced enforcement, ingest compatible events and select cached workers on
   repeated-prefix traffic. Use an uncached-prefix control and independent
   endpoint receipts; successful fallback is not Exact proof.
4. **Verify completion and rejection.** Require full content/reasoning,
   terminal semantics and exactly one DONE for normal SSE; match all offered
   requests and attempts to receipts. Check invalid configuration leaves state
   unchanged and invalid/unsupported requests are explicitly rejected. Preserve
   partial/error/timeout streams as failures, not successful subsets.
5. **Verify negative, loss and recovery.** On an explicitly allocated isolated
   service, exercise owned worker loss, new requests on survivors, immediate and
   later recovery, endpoint redistribution, cancellation and resource return.
   Preserve original Gemma/stream/resource failures. Use
   [Fail-over tuning and limits](failover-tuning.md); completed new requests do
   not prove ongoing-stream continuation or lossless fail-over.
6. **Verify switch and rollback.** RR→Exact→RR requires explicit keyed replacement,
   exact readback, the selected mode's readiness/traffic proof, and restoration
   of the original create JSON and effective environment. Changing framework or
   registry also requires its own staging/recreate checks.
7. **Verify deletion and clean replay.** Delete only owned model/host/VIP/port
   identities, prove absence and retained Gateway readiness, preserve unrelated
   resources and receipts, then recreate from retained inputs and recheck.

Close **functional qualification** only with the completed evidence above and
an explicit result for every required gate. If a gate is blocked, skipped or fails,
retain it as such with reproduction, impact, cause status, verification limits
and the evidence required to close it. A documentation/schema test does not
close a GPU case. A functional pass also does not promote a catalog row; product
support promotion is a separate reviewed process.

### Capacity and performance remain additional tasks

After functional acceptance, run the [paired QA methodology](validation.md)
against the application's workload and completion/SLO targets. Retain all failed
conditions and repeat clean pairs before a numerical claim. RR/Exact functional
success does not establish optimum settings, sustained throughput or production
availability. Converged qualification does not qualify a P/D topology.

The [machine-readable matrix](../../assets/model-engine-standard/qualification-matrix.json)
in the configuration ZIP tracks all **36 mode cases**, current prerequisites and
required evidence. It records this documentation edition's state, not a live test
service or a claim that the work has been executed.

### Required core integration: catalog and installer

[Catalog and Installer Alignment](catalog-installer.md) records the five-profile
registration proposal: 13 candidate tuples and two TRT architecture-blocked
tuples. Preserve old profiles/version evidence and the SGLang 0.5.19 guide baseline.
The metadata proposal passes Python modelctl render/check; it is not ready for
core integration until these reproduced gates close:

- engine-version-contract: update core-owned version selectors and regenerate/check Go/C trust artifacts.
- selected-tuple-image: image pulls must follow selected tuples, including old/new version coexistence.
- blocked-selection-side-effects: blocked-only selections must perform no image pull or registry writes.
- manifest-identity-validation: refuse wrong engine version/digest/revision before modifying install roots.

After the core team provides a fixed immutable candidate, repeat isolated
installation, rejected/no-mutation cases, discovery/READY and complete RR/Exact
traffic using the newly installed registry. Current Linux staging checks and
prior GPU functional PASS do not close this new installed-candidate gate.

## Check your result

Record NOT_RUN, FAIL and BLOCKED honestly; this page does not execute or close them.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
