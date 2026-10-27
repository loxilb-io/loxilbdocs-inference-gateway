# Performance Methodology

How to benchmark **your own** LoxiLB inference deployment reproducibly — a method for
producing a defensible routing number that survives peer review, not a table of results. This
page defines the metric, the measurement flow, and the statistical gates. Every rate, SLO, host,
and threshold below is a **placeholder you fill from your own fleet** — substitute the values you
measure, never a number quoted from elsewhere.

!!! note "This is a method, not a benchmark"
    Nothing here reports how fast any deployment is. It tells you how to *measure* your own
    deployment so the resulting number is honest, stable, and reproducible. Run it against your
    hardware, your model, and your trace, and derive your own SLOs from your own baseline.

---

## Before you start

Begin only after direct and Gateway functional checks pass for the chosen tuple.

**Focus of this page:** Keep client load, Gateway routing, worker execution and measurement collection distinguishable.

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

## Walkthrough

### 1. The metric: goodput@SLO

The headline metric is **goodput@SLO**, defined exactly as DistServe defines it. It rests on two
per-request latency measures:

- **TTFT** — time to first token.
- **TPOT** — time per output token (inter-token latency).

A request is **good** if and only if:

```
TTFT ≤ TTFT_SLO  AND  TPOT ≤ TPOT_SLO
```

This is a **conjunction** — *both* SLOs, not either. Two rules make the definition honest:

- **Failed = miss, not dropped.** A request that errors, times out, or never completes cleanly is
  **not good** and still **counts against the denominator**. It is never discarded from the
  attempted count.
- **good-fraction** at a fixed offered load = good requests ÷ attempted requests.

**goodput@SLO** is then the good-throughput at the **knee**: sweep the offered load upward and find
the highest rate at which the good-fraction still clears your chosen target (conventionally 90%).
The published scalar is the achieved good-throughput per accelerator at that knee, reported
alongside the knee's offered request rate.

!!! warning "Why conjunction, and why failed counts as a miss"
    Both choices exist to prevent a flattering result:

    - An **OR** definition would score a request that blew its TPOT SLO as "good" merely because
      its TTFT was fine.
    - **Dropping failures** would let a mode that errors on half its requests look fast on the
      survivors.

    Both are load-bearing. If you relax either, your number is no longer comparable to a
    DistServe-style goodput and should not be called one.

The measurement itself is a controlled **trace replay**: replay the *same* real prompt trace
through each routing configuration at the *same* offered load, capture per-request TTFT and TPOT,
compute good-fraction, and compare configurations with a statistical verdict.

---

### 2. The five-phase flow

Every reproducible run walks the same five phases. Skipping any phase invalidates the number.

```
Phase 0  Health      → fleet confirmed serving before any data is collected
Phase 1  Calibrate   → per-endpoint saturation capacity + a fair operating rate
Phase 2  Probe       → confirm the routing mechanism is mechanically engaged
Phase 3  Replay      → per-arm, per-request TTFT/TPOT under controlled load
Phase 4  Analyze     → good-fraction, goodput@SLO, and a statistical verdict
Phase 5  Verify      → validity + stability + integrity gates → PUBLISHABLE or ADD_REPLICATES
```

The phases are ordered by dependency: calibration needs a healthy fleet, the operating rate comes
from calibration, the replay needs the probe's confirmation, and the verdict is only trustworthy
once the verify gates pass.

---

### 3. Phase 0 — pre-run health

Run a read-only readiness check before **every** measurement. A run started on a half-warm or
partially-serving fleet is invalid data, not a slow result.

The check should gate on a real, end-to-end request — a genuine `POST /v1/chat/completions`
through the VIP returning `200` — not merely a port being open. Confirm, in order:

1. The LoxiLB container is up and any prefill-timeout environment is set high enough that
   long-context prefills complete rather than time out.
2. Every backend endpoint answers its model-list probe and advertises the context length you
   expect.
3. Each VIP returns `200` to a real chat completion, and (for disaggregated deployments) the
   response carries the prefill/decode handoff receipt so you can confirm disaggregation actually
   fired.

!!! example "Initial completion probe (replace placeholders)"
    ```bash
    curl -fsS --max-time 180 \
      -X POST "http://<VIP>:<PORT>/v1/chat/completions" \
      -H 'Content-Type: application/json' \
      -d '{"model":"<your-model>","messages":[{"role":"user","content":"ping"}],"max_tokens":32}' \
      > capacity-preflight-chat.json
    jq -e '.usage.completion_tokens>0 and
      (.choices[0].finish_reason=="stop" or .choices[0].finish_reason=="length") and
      (((.choices[0].message.content // "")|length)>0 or
       ((.choices[0].message.reasoning_content // "")|length)>0)' capacity-preflight-chat.json
    ```

    Add the service's protected client header/TLS settings when applicable.
    Retain the response and independent backend receipt. This initial generation
    check is insufficient for measurement acceptance: also verify complete SSE,
    Exact READY/unfenced state when selected, cache engagement and full offered-load
    accounting. HTTP 200 alone is not a readiness or performance verdict.

!!! tip "KV-events precheck (KV-exact / cache-aware arms only)"
    A read-only health probe confirms the *data path* is serving, but does not by itself prove the
    KV-events plane is feeding the router. If you are measuring a KV-exact or cache-aware routing
    arm, separately confirm the KV-event publishers are up on every backend and that the gateway's
    subscribers are connected — otherwise the arm silently degrades to a coarser fallback tier and
    you understate the very routing you set out to measure. Confirm a cache-hit counter *advances*
    on a warm-route probe before trusting any run.

---

### 4. Phase 1 — per-endpoint capacity calibration

Before you can pick a *fair* offered rate, you must know each endpoint's actual saturation
throughput. **Never assume it** — measured capacity routinely differs from the configured prior by
a large margin, and calibrating rather than assuming is the whole point of this phase.

Calibrate by driving **one endpoint directly** — never the VIP or router. A calibration must
measure a backend, not the balancer; a sweep target that points at the load balancer is measuring
the wrong thing and should be refused.

#### 4.1 The protocol (pre-register it — do not tune mid-run)

Fix the calibration parameters *before* the run and hold them constant. The shape of the protocol:

| Parameter | Method (fill your own values) |
|---|---|
| Start rate | Begin well **under** expected capacity. |
| Ramp | **Geometric** — each step multiplies the offered rate by a fixed factor, so the offered rate grows by a fixed percentage every step. |
| Warmup | A fixed, **discardable** warmup at the start of each step. |
| Hold | Hold each step until the **longer** of a minimum duration and a minimum request count. |
| Plateau rule | Saturation is declared when the **last two consecutive throughput gains are both below a small fixed percentage** while the offered rate still grew by the full ramp step. |
| Backstop | A maximum step count so the sweep always terminates. |

**Capacity** is the mean delivered throughput across the plateau steps — prompt tokens/sec for a
prefill role, output tokens/sec for a decode role.

#### 4.2 The client-bottleneck cross-check

A plateau alone is not proof the *endpoint* saturated — your load generator may have hit its own
ceiling first. Guard against this with a **queue-divergence cross-check**: sample the backend's
in-flight/waiting-queue depth throughout the sweep.

- A plateau **with** a diverging backend queue → the **endpoint** is genuinely saturated. Trust it.
- A plateau **without** a diverging queue → the **client** (your driver) is the bottleneck, not the
  endpoint. Flag the step **SUSPECT** and re-run it once.

This is what stops you from accidentally calibrating your own load generator and reporting it as
backend capacity.

#### 4.3 Pick a fair operating rate

Take the **lowest-capacity member** of a role as the reference. Run the A/B (Phase 3) at rates that
are:

- In the **unsaturated** regime for the baseline arm — so the comparison is about *routing
  quality*, not about who saturates first; and
- Near the **knee** — so a bounded-load routing policy actually has work to do.

Sweeping a small ladder of rates (an unsaturated point, a moderate point, and a saturated point) is
what later lets you report goodput@SLO as a capacity, not just a single-rate snapshot.

---

### 5. Phase 2 — mechanism probe

Before trusting any goodput delta, prove the routing configuration is *mechanically* doing what it
claims — that a spreading policy actually spreads load and a concentrating one actually
concentrates it.

Burst cache-keyed traffic through the gateway and sample each backend's in-flight load once per
interval, then compute a **concentration ratio = peak ÷ mean** across backends:

- A concentrating (blind) policy should show one backend hot — a **high** peak-to-mean.
- A bounded-load spreading policy should flatten toward **≈1** — load bounded near the average.

If a policy you *intended* to be spreading looks like the concentrating one, the mode **did not
engage**. Stop and fix the wiring before spending a measurement on it — a silent fallback to a
default policy is the single most common way a "multi-mode comparison" quietly becomes one mode
measured several times.

!!! warning "Confirm the active mode manually"
    Recreating the gateway to switch routing modes does not, by itself, prove the new mode took
    effect. Read the gateway's own log line (or its metrics) and confirm it names the mode you
    intended for **this** arm — do not assume the switch succeeded.

---

### 6. Phase 3 — the trace-replay A/B

Replay the same trace through each arm at the controlled offered load, writing per-request results
so each arm's TTFT/TPOT distribution can be reconstructed. The A/B design is what makes the
comparison fair: identical trace, identical load, one variable changed per arm.

Design rules that keep the replay honest:

- **Streaming is mandatory.** TTFT and TPOT only exist on a streamed response — a non-streamed
  driver cannot measure them.
- **Over-deadline requests are cancelled and recorded as FAILED**, so a dropped stream terminator
  becomes a *defined miss* rather than a silent hang that inflates the survivors.
- **One variable per arm.** When several routing modes share the same VIP, the per-mode behavior
  comes from **recreating the gateway in the target mode before that arm's replay** — not from a
  different URL. Re-confirm the active mode (Phase 2) for every arm, every time.
- **A baseline floor arm** (e.g. a plain round-robin configuration) belongs in every campaign: it
  is how you show routing *earns its keep* over its own naive baseline, independent of any external
  comparison.

!!! note "Placeholder arm layout"
    Define your arms as *your* configurations — for example a baseline floor arm and the routing
    policy under test. Keep each arm's output in its own run directory so the analyzer keys results
    to the right arm. Do not import arm identities, endpoints, or results from any other
    deployment; a benchmark is only meaningful against *your* own baseline.

---

### 7. Phase 4 — analyze

Reduce each arm's raw per-request export into aligned arrays of successful TTFT/TPOT values, plus
bookkeeping the verdict depends on: the usable (paired) count, the attempted total, per-class error
counts, and an **invalid-HTTP-framing count** — the correctness floor (see §9).

From those arrays, compute in order:

1. **good-fraction per repetition** — apply the conjunction good-mask over the **attempted**
   denominator (failed requests padded in as misses).
2. **Noise floor** — the bootstrap-CI half-width of the baseline arm's mean good-fraction. This is
   the smallest difference the run can even resolve, and it needs several baseline repetitions to
   estimate.
3. **Parity via TOST** — when claiming two arms are *equivalent*, use a **Two One-Sided Tests**
   procedure against an equivalence margin **δ**. Declare **EQUIVALENT** only when the CI of the
   difference lies entirely within `[−δ, +δ]`. Report the CI and the TOST result, not a bare
   yes/no.
4. **Win vs the floor** — a difference over the baseline floor arm is a **win only when the whole
   confidence interval sits on the winning side of zero**; otherwise it is *inconclusive*.

!!! warning "Overlapping CIs are not parity"
    "The confidence intervals overlap" or "p > 0.05" is **absence of evidence, not evidence of
    equivalence.** Only a passing **TOST** verdict legitimately claims parity. Never upgrade a
    failed difference test into a parity claim.

#### The knee

The good-fraction above is at one fixed rate. To report **goodput@SLO** as a capacity, run Phase 3
across the rate ladder from §4.3 and take the highest rate whose good-fraction still clears your
target. Report the rate alongside the throughput — goodput@SLO without its rate is not a portable
number.

---

### 8. Phase 5 — verification gates

A performance number is worthless without proving three things: the run was **valid**, the result
is **stable enough to publish**, and the pipeline **computed what it claims**. Enforce these in
code so a noisy or invalid number *cannot* be emitted by eye.

#### 8.1 Validity gate (auto-discard)

Discard an individual (arm, repetition) run **by rule, not judgment**, logging a reason, when any of
these hold:

| Condition | Why it invalidates the run |
|---|---|
| Invalid-HTTP-framing count above zero | A correctness bug — the run is measuring a broken path. |
| A hang or truncation in the error classes | A request never completed cleanly. |
| A backend prefill/processing timeout present | The timeout, not the routing, shaped the result. |
| A VIP was not serving `200` during the run | The fleet was not serving. |
| A backend health check failed | A backend was down. |
| Zero usable paired samples | There is nothing to measure. |

Run the validity filter **first**, before any statistic is computed, so discards happen
automatically.

#### 8.2 Stability gate (publish policy)

Pre-register the stability thresholds and encode them, so publishability is a mechanical verdict:

- **N ≥ 5** repetitions per system-under-test arm, **and**
- **CV ≤ 10%** on the good-fraction across those repetitions.

| Situation | Verdict |
|---|---|
| Fewer than the repetition floor | **ADD_REPLICATES** — never "ship the noisy number." |
| At/above the floor **and** CV within bound | **PUBLISHABLE** |
| At the repetition cap but CV still over bound | **PUBLISHABLE_WITH_FOOTNOTE** (residual variance footnoted) |
| At/above the floor but CV over bound (below cap) | **ADD_REPLICATES** |

!!! note "The baseline-repetition minimum is a separate thing"
    The handful of **baseline** repetitions the noise-floor δ needs (§7 step 2) is *not* the
    publish gate. Meeting the δ-floor lets you *resolve* a difference; only **N ≥ 5 / CV ≤ 10%** on
    the system-under-test arm makes a result **publishable**. Do not conflate them.

#### 8.3 Independent integrity cross-check

Re-derive goodput@SLO with an **independent** implementation that does not import the main
analyzer's modules, and audit the pipeline end-to-end. It should confirm: the denominator matches
the attempted count; paired + single-token + errors sum to the total (no lost requests); latency
values are in the expected unit; an independent good/total recompute matches the analyzer; and a
cluster-robust per-repetition interval agrees with the pooled bootstrap. A green cross-check is your
evidence the analyzer is not fooling itself.

#### 8.4 BCa bootstrap and self-checks

Use **BCa** (bias-corrected and accelerated) bootstrap confidence intervals for the reported
medians and tail percentiles — they are more honest than normal-theory intervals on the skewed
latency distributions typical of inference. Ship each statistics module with a self-check that
asserts its logic against known vectors on a bare host, so you can prove the conjunction good-mask,
the TOST/δ resolution, and the stability thresholds behave *before* trusting them on real data.

#### 8.5 The dual-proof: decision vs delivery

A good goodput number can still be measuring the wrong thing. Cross-check the routing **decision**
against the **delivery**:

- **Decision proof (metrics):** the gateway's cache-hit / routing counters advanced for the arms
  that should route by cache, and the miss-reason counters did *not* climb request-for-request
  (which would mean the gateway silently fell back to round-robin — you measured the fallback, not
  the routing).
- **Delivery proof (receipt):** the responses carried the expected handoff receipt (for
  disaggregated deployments) confirming the intended data path actually served the request.

A result where the routing counters never moved is a baseline measurement mislabeled as
cache-aware routing. **Discard it.**

---

### 9. The honest caveats

Read these before quoting any verdict. Each protects the number from a common, self-flattering
mistake.

1. **Derive the SLO from your own baseline.** An SLO borrowed from a *direct-endpoint* latency can
   be one your full routed path — especially a disaggregated prefill→decode path — structurally
   cannot meet, no matter how good the routing. Measure your **own** unloaded baseline **on the same
   path you are scoring**, and set the SLO as a fixed multiple of that baseline. State the SLO and
   its origin up front. An SLO the deployment cannot physically satisfy produces a meaningless
   goodput.
2. **Disaggregation is apples-to-oranges.** If one arm runs prefill/decode disaggregated and another
   runs aggregated (one server doing both), the TTFT gap mixes disaggregation overhead with routing
   quality. For a clean comparison, drive every arm through the **same** serving topology, or
   reframe the claim to name the difference.
3. **The correctness floor is absolute.** The invalid-HTTP-framing count **must be zero** on every
   published run. A fast number over a subtly broken path is not a performance result.
4. **Routing knobs are load-dependent.** A policy that wins at one offered rate can lose at another.
   Always report the **rate**, and prefer a load-adaptive policy when you need a single setting
   across a range.

---

### 10. The tuning loop

Performance measurement feeds configuration — it is not a one-shot report:

1. **Baseline** — measure your default routing policy against the floor arm at your operating rates
   (§4–§7).
2. **Sweep** — if the default does not win by enough, vary one routing knob at a time. **Each
   candidate is a full Phase 0–5 cycle:** health → calibrate (only if the fleet changed) → probe →
   replay → analyze → verify.
3. **Decide by the gate, not the eye** — only a **PUBLISHABLE** win over the floor, or a **TOST
   parity** verdict against a comparator, justifies a configuration change.
4. **Re-calibrate on a topology change** — if your fleet's total capacity differs from the fleet you
   calibrated on, Phase 1's numbers are stale; recalibrate before trusting any load-keyed policy.

---

### Related pages

- [KV-Cache-Aware Routing](../concepts/kv-routing.md) — the routing this method is designed to
  measure.
- [Routing Hierarchy](routing-hierarchy.md) — the tier ladder a cache-aware run must confirm fired.
- [Configuration & Tuning](configuration-tuning.md) — the knobs the tuning loop sweeps.
- [Monitoring & Metrics](../operations/monitoring.md) — the counters the dual-proof reads.

### Request and receipt accounting

#### Fix the comparison inputs

First record the exact Gateway image digest and runtime flags; model revision,
weights/tokenizer/template checksums; engine image/args; registry generation,
profile and binding digest for Exact; Linux/kernel, GPU, driver, CUDA/runtime and
network. Record missing facts as missing. Do not treat a mutable tag as identity.

Use a dedicated service and owned worker allocation. Retain stock engines and
templates. Keep the same model and prefix-cache settings in both arms. Use the
RR and Exact create bodies from the configuration folder, adapted to your site.
A/B changes only the routing choice unless another variable is explicitly part
of the experiment. A changed manifest or engine also changes the experiment.

| Input to fix before running | What to record |
|---|---|
| Requests | Exact prompt bytes, language, prompt/template token counts, model and input hashes |
| Prefix reuse | Fixed shared prefixes plus a no-sharing control; actual token/block overlap |
| Output | Requested cap and actual completion tokens; reasoning included when present |
| Arrivals | Deterministic seed, open-loop rate or closed-loop concurrency, schedule, sample count and client deadline |
| Connections | HTTP version, keepalive/pool settings and measured connection behavior; a pool option alone is not observed reuse |
| Warm/cold state | Warmup requests, cache reset/retention procedure and separate reporting |
| Completion | Normal stop/length, complete content, exactly one DONE for SSE, no errors and matching backend receipt |
| Measurement interval | Start/end definition for TTFT, total latency, tokens/sec, and metrics samples |

Choose modest output and one arrival at a time for initial qualification, especially
Gemma. Increase only one of rate, concurrency, context or output length per step.
Define SLO, time budget and stop criteria before starting. Avoid unbounded retries
that silently change offered load or erase rejected requests. Interleave/order
arms to control drift and repeat at least three clean pairs before making a
quantitative claim; disclose excluded trials and why.

#### Collect and interpret results

Retain request-level client timing and completion records, backend-owned correlated
receipts, raw SSE or chat, engine access/error logs, Gateway routing metrics,
subscriber/inventory state, engine running/waiting/preemption/KV observations,
and GPU utilization/memory samples. Use
[monitoring](../operations/monitoring.md) and
[performance methodology](performance-methodology.md) for existing surfaces.
Do not read an engine's destructive event queue with a second consumer during
an Exact trial.

Normal completion requires successful transport **and** model-level content and
terminal semantics. Match client IDs to independent backend receipts and account
for every offered request: normal, rejected, timed out, disconnected or invalid.
An HTTP 200, an open TCP probe or a Gateway counter is not an independent receipt.

Only compare full runs after count, completion, latency-population and receipt
checks pass in both arms. Preserve a failed arm as failed. Successful-subset p95
can be shown only as a clearly labeled diagnostic, never as the passing result
for the offered workload. Keep warmup and measurement populations distinct.
Compute TTFT percentiles from retained request rows, and calculate throughput
from actual generated tokens over the explicitly defined interval. Do not divide
one tool's token count by a duration with a different start/end definition.

Use these interpretations:

| Observation | Supported interpretation | Next controlled check |
|---|---|---|
| Less prefill compute, unchanged output rate | Decode or another stage may limit aggregate output | Retain rate/output and inspect engine/GPU/queue data |
| High KV pressure and rising waits | Current workload exceeds a useful operating point | Lower one demand or add capacity; rerun all completion gates |
| Exact cache metrics but no end-to-end improvement | Routing engagement is not sufficient for an SLO gain | Compare identical RR requests and queue/output effects |
| One endpoint receives many requests | Placement imbalance may contribute | Examine per-endpoint receipts/load; do not declare a sole cause from aggregate data |
| Both direct and Gateway requests fail | Failure does not require Gateway on that observed path | Isolate engine/model/resource conditions without changing several variables |
| Clean component or documentation checks | The named bounded check passed | Run the separate deployed service/GPU gate |

## Check your result

Retain every arm, denominator and failure; functional PASS alone is not a latency SLO or cache benefit.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](model-engine-standard/lifecycle.md) when ending the run.
