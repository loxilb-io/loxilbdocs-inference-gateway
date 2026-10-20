# Verification To-do: Every Model, Engine and Routing Mode

<!-- example-status-default: illustrative-only -->

Every unverified RR or Exact selection in [model and engine selection](index.md)
is a **qualification task to complete**. Providing both modes is a documentation
deliverable; proving them on the actual model/engine/Gateway tuple is a separate
runtime deliverable. This public checklist states the current gaps, prerequisites
and acceptance evidence so operators know what remains before adoption.

**Review in progress, 2026-10-20.** Use the [five-model operator manual](matrix-manual.ko.md)
for current paired RR/Exact inputs. The five QA definitions and fixtures are now
supplied separately from the unchanged upstream catalog.

## Original five cards: 30 mode cases

The current evaluation versions are vLLM 0.31.0, **SGLang 0.5.19** and TRT rc29/PyTorch.
vLLM completed the five-model functional pairs. TRT completed Qwen/Llama/R1 pairs;
its Gemma2/EXAONE native PyTorch architectures are blocked. All five SGLang models
are being re-executed on the stock tagged-array 0.5.19 image with explicit
engine-specific QA profiles. Earlier 0.5.18 results are retained separately.

The 0.5.21 tagged-map trial is a [separate development request](sglang-compatibility.md).
The 0.5.18 EXAONE tokenize API overflow is addressed in upstream stock 0.5.19;
R1's observed native BOS policy is recorded in its SGLang profile. Neither an
old PASS nor an upstream source inspection substitutes for the current runtime gates.
Remaining full qualification includes capacity, cancellation/resource return,
worker loss/recovery, clean replay, release image and host data plane.
Historical Gemma load RED stays open.

## Separate public-catalog example: six additional cases

[Choose RR or Exact](routing-choice.md) supplies both modes for R1 **1.5B**, not
the 7B row above. Candidate source status is unchanged by adding examples.

| Framework | RR case | Exact case |
|---|---|---|
| vLLM 0.31.0 | Bounded GPU QA: 12/12 completed, four receipts per worker; lifecycle checks executed | Separate evaluation manifest: READY, 12/12 prewarmed-worker receipts and cache-hit delta 12; full qualification still open |
| SGLang v0.5.18 | Not run on this documentation deployment; qualify paired RR body | Not run; stage candidate profile, prove rank/event/hash/token parity and READY |
| TRT 1.3.0rc24 | Matching image provisioning required before runtime | Same image prerequisite, then single-consumer HTTP events, READY and traffic engagement |

A backend/image prerequisite must stay visible. In particular, TRT's installer
`SKIP_NO_PULLABLE_IMAGE` is not a successful engine start. Do not substitute an
rc29 image and retain an rc24 success label.

## Execution order and closure criteria

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

## Capacity and performance remain additional tasks

After functional acceptance, run the [paired QA methodology](validation.md)
against the application's workload and completion/SLO targets. Retain all failed
conditions and repeat clean pairs before a numerical claim. RR/Exact functional
success does not establish optimum settings, sustained throughput or production
availability. Converged qualification does not qualify a P/D topology.

The [machine-readable matrix](../../assets/model-engine-standard/qualification-matrix.json)
in the configuration ZIP tracks all **36 mode cases**, current prerequisites and
required evidence. It records this documentation edition's state, not a live test
service or a claim that the work has been executed.
