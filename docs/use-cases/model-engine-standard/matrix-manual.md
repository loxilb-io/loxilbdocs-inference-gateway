# Converged RR and KV-Exact: Five-Model Guide

Use this ordered guide to prepare a three-worker converged service and choose RR
or strict KV-Exact. Every worker performs both prefill and decode. Follow the
steps in order; later pages reuse the variables and evidence directory selected
in Step 1. Commands are individual, editable operator actions.

| Step | Outcome |
|---|---|
| [1. Select a model and check prerequisites](select.md) | Check model access, actual case results, versions, hardware and allocated addresses; initialize one run directory |
| [2. Prepare models and profiles](prepare.md) | Verify snapshot/image integrity; for Exact, stage the engine-specific evaluation registry |
| [3. Launch engine workers](launch.md) | Run one selected engine on each worker and check direct inference |
| [4. Configure Gateway routing](configure.md) | Start the dedicated Gateway, publish the staged registry when selected, then apply/read back one RR/Exact rule |
| [5. Verify requests and routing](verify.md) | Complete chat/SSE, correlate independent receipts and reject invalid changes without mutation |
| [6. Switch modes, clean up and roll back](lifecycle.md) | Drain, replace or delete only owned resources and prove restoration |

The evaluated baseline is **vLLM 0.31.0, SGLang 0.5.19 and TRT 1.3.0rc29/PyTorch**.
Check [functional results](results.md) before selecting a tuple: 26 bounded
functional PASS and four native architecture BLOCKED cases. TRT Gemma2/EXAONE
are blocked on this pinned backend in both modes. Gemma's earlier load failures
remain open. These are source-built, isolated proxy-only observations, not
release, capacity, P/D, host eBPF/HA or full fail-over qualification.

For model-specific identities and exceptions, see [Model Matrix and Notes](models.md).
For catalog membership and the pending registration proposal, see
[Profile Catalog](profiles.md) and [Catalog/Installer Compatibility](catalog-installer.md).
These five QA profiles are not installed by candidate opt-in against the reviewed
source catalog. Download the [configuration ZIP](../../assets/model-engine-standard.zip)
and follow Step 1 to verify it. Historical inputs remain separate from current
`matrix-configurations/` and `evaluation-profiles/` inputs.


<details>
<summary>Links from the previous combined manual</summary>

<a id="matrix-model-selection"></a>

[Continue to this section](select.md#matrix-model-selection).

<a id="matrix-registry-preparation"></a>

[Continue to this section](prepare.md#matrix-registry-preparation).

<a id="matrix-engine-launch"></a>

[Continue to this section](launch.md#matrix-engine-launch).

<a id="matrix-rule-application"></a>

[Continue to this section](configure.md#matrix-rule-application).

<a id="matrix-request-verification"></a>

[Continue to this section](verify.md#matrix-request-verification).

<a id="matrix-lifecycle"></a>

[Continue to this section](lifecycle.md).

<a id="matrix-results"></a>

[Continue to this section](results.md#matrix-results).

<a id="1-versions-and-verification-scope"></a>

[Current section](select.md#versions-and-verification-scope).

<a id="9-remaining-qualification-and-rerun-conditions"></a>

[Current section](qualification-todo.md).




<a id="five-model-rr-and-kv-exact-configuration-and-verification"></a>

[Current section](matrix-manual.md).

</details>
