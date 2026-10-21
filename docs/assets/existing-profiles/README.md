# Existing-profile settings and reproduction package

This package covers the 13 requested source profile identities. Consult
`runtime-matrix.json` for each model, engine, topology and routing surface.
Blocked access, missing image/storage, native failure, rejected Exact admission,
partial one-prefill engagement and successful traffic are distinct outcomes.
An `IN_PROGRESS_NOT_FINAL` matrix is a preparation artifact, not delivery.

The source profiles and original probe requests/expected token IDs are preserved.
The three candidate registries have separate engine-version manifests. They do
not promote the historical catalog, whose tuple states are recorded separately
in `model-identities.json`. The reused Gateway binary is identified by SHA256;
its source commit was not established. This is not release qualification.

## Repository and archive layout

This repository keeps editable settings, profile metadata, source-index checksums,
routing examples, summary metadata, and verification tools. Raw response bodies,
receipt ledgers, result indices and original token probe fixtures are distributed
**only inside `../existing-profiles-evaluation.tgz`**. Do not run the result
verifiers or launch procedures from this partial repository directory. Download
and extract the complete archive into a new directory first.

The archive is unchanged and contains 14,049 files. Its SHA-256 is
`616be523283bfe3d33823faa316e42bf2fe579dc8e0addc6ec8a418c08560ee7`.
The repository `SHA256SUMS` covers only files retained in this directory; the
archive has its own original `SHA256SUMS` covering the complete extracted payload.
The repository README explains this distribution split; its archived counterpart
remains the original full-package guide. Other retained files match archive bytes.

## Complete archive contents

| Path | Meaning |
|---|---|
| `manifest.json` | Distribution, engine-version and qualification boundaries |
| `model-identities.json`, `models/` | Exact repositories, revisions, artifact hashes and template source |
| `source-definitions/` | Original source profiles |
| `registry-vllm/`, `registry-sglang/`, `registry-trtllm/` | Isolated candidate metadata and original probes; presence is not runtime success |
| `weights/*.source-index` | Original full index bytes bound by the profile's index SHA256 |
| `weights/*.sha256` | Expected file checksums derived from the original full index and verified small metadata for 11 accessible snapshots; absent for gated unrun models |
| `recipes.json`, `settings/` | Literal parameters from independently reviewed native/RR cases, with their exact scope |
| `rules/` | Editable examples using documentation addresses; accepted modes only |
| `runtime-matrix.json` | Latest terminated surface outcomes, including all explicit blockers |
| `results/converged-index.json` | All retained functional attempts, including legacy setup failures and capped answers |
| `results/converged/` | Original synthetic client body bytes, complete whitelisted receipt ledgers, control bodies and reviewed scope |
| `results/settings-index.json` | Complete independently reviewed bounded comparisons, including rejected candidates |
| `results/settings/` | All 144 main and 108 separate warm samples per comparison, request/response body hashes, recorded client timings, GPU snapshots and decisions |
| `results/incomplete-settings-index.json` | Every offered row in unqualified comparisons, including main batches saved before an audit abort |
| `results/pd-index.json` | Reviewed native P/D summaries and retained failed-attempt reason codes |
| `receipt-proxy.py` | HTTP/1.1 body recorder used for isolated synthetic QA; not a product component |
| `verify-results.py` | Independent setting arithmetic, normal-answer, token-volume and receipt verification |
| `verify-incomplete-results.py` | Independent accounting of all unqualified offers; never selects a setting |
| `verify-converged.py` | Raw functional classifications, full receipt matching and accepted routing scope |
| `SHA256SUMS` | In the archive: every extracted payload file except this manifest; in the repository: retained files only |

Model weights, tokenizer/template bytes, credentials, Docker inspections,
private worker addresses, native transfer session state and the Gateway binary
are excluded. Obtain model artifacts from the exact official revision using
existing authorized access. A tokenizer/template hash identifies expected bytes;
it does not grant access or redistribute those bytes.
The checksum manifests alone do not prove that every weight was downloaded or
that inference succeeded. Runtime rows and the reviewed recipe scope provide
the separate execution evidence.

## Verify before using

Use the versioned archive and checksum links in the [launch guide](../../use-cases/model-engine-standard/existing-profiles-launch.md#select-and-save), and save both into a new working directory. A Git clone or a GitHub source ZIP contains only the partial repository layout and is not the complete reproduction package:


```bash
sha256sum -c existing-profiles-evaluation.tgz.sha256 || exit 1
test ! -e existing-profiles || exit 1
tar -xzf existing-profiles-evaluation.tgz || exit 1
cd existing-profiles || exit 1
sha256sum -c SHA256SUMS || exit 1
python3 verify-results.py --mutation-control
python3 verify-incomplete-results.py --mutation-control
python3 verify-converged.py --mutation-control
```

The three Python verifiers use the standard library. Each mutation control
changes a receipt hash in a temporary copy and calls the real verifier, which
must reject it. Do not put model downloads, private receipts or other execution
outputs inside this package: keep the immutable package separate from the
working directories used by the operator manual.

## Reading results correctly

A complete setting comparison uses the same two GPUs, fixed JSON main body,
temperature and output budget, concurrency 8, 24 main requests per arm and three
paired repetitions in A/B, B/A, A/B order. Each arm separately offers one native
JSON warmup per worker and 16 concurrent RR warmups, requiring 8 per worker.
All main samples and the 108 separate warm samples remain present. An aborted
comparison retains all offers, even a batch not appended to an aggregate.

TTFT is the first nonempty `delta.content` observed by the client. It can include
whitespace or reasoning carried in content; separate reasoning fields do not
start this clock. It is not time to the final answer. Nearest-rank p95 is
computed within each 24-request arm. Untimed SSE cannot reconstruct client
arrival times; those times and arm wall times are recorded measurements.
The GPU allocation snapshot is taken after native JSON warmup, **before** RR
load warmup. It is not peak request memory or a long idle-capacity measurement.

Output-token totals must differ by no more than 5% in every paired repetition.
A lower memory setting additionally requires at least 30% lower recorded
allocation on each GPU in each pair and no p95 regression above 5% in any pair.
Changing the sequence cap 2→4 requires improvement in all three p95 pairs and
at least 10% median relative improvement. Failing any gate retains the baseline.
The selected combination still needs a separate functional requalification.
Native P/D retains its separately tested sequence cap and memory/KV geometry.

`performanceComparisonQualified:false` is not an accepted latency improvement.
An incomplete comparison is not repaired by pooling successful subsets. Client timeouts retain client bytes and independently recorded incomplete upstream bytes separately. An upstream partial is never counted as a complete client response; the incomplete verifier checks its own hash and rejects actual partial-body mutation when present.
Functional success, verified arithmetic and a bounded operational recipe do
not establish a global optimum, engine ranking, Korean task accuracy, long
context/concurrency capacity, active-stream continuity, engine-crash recovery,
native transfer bandwidth or an SLA.

Dates can change native rendered inputs without changing the API body. For
date-sensitive executed comparisons (including GPT-OSS) the evidence includes UTC image timezone,
a constant comparison date and matching native token IDs across workers/arms.
No model template is rewritten to force this condition.

## Privacy and verification limits

Functional client bodies are synthetic and original. Worker identifiers are
aliased in receipt metadata; container names and model-directory mounts are
normalized in published launch arguments. Original argument hashes remain
provenance references. Controls containing deployment details are withheld
with an explicit reason and original body hash. The complete private evidence
was retained separately and is not part of this archive.

The public P/D data is a reviewed summary. Qualified cases were reviewed for both-role
body hashes, preserved state/bootstrap identity, native Decode transfer
counters, negatives, recovery and cleanup. Failed attempts retain only their
actually completed checks; they do not inherit the qualified cases' proof. Private session bytes and effective
deployment configurations are not redistributed, so the public verifiers do
not independently reconstruct those P/D or configuration-state proofs.
One-prefill Exact proves engagement only, with no prefill-selection benefit.

Before using an environment file, inspect it and match its case, engine and
accepted routing modes. The rule addresses must be replaced with allocated QA
addresses. Use an isolated Gateway and dedicated workers; delete only the
reviewed test rule and stop only the named owned containers. Preserve original
caches, workloads and evidence.

## Follow the operator guides

Start with the public **Existing profiles: integration results and operating
settings** page to choose one model, engine, and permitted mode. Follow
**Prepare, launch, and verify** for the normal two-worker RR procedure; Exact
is an optional separate run. **Native P/D launch and verification** has its
own permitted-mode table, role topology, and settings. **Bounded tuning and
result verification** explains the recorded comparison data.

Gemma 3 and Llama 3.2 remain user-deferred with no runtime recipe. Metadata
presence does not authorize access retries or establish tested settings.
Context 4096 and per-request output budgets are campaign settings, not model
maximums or evidence of 1M-token support. All run outputs and private role
receipts belong outside this immutable package.

## Repository maintenance check

From the documentation repository root, with its requirements installed, run:

```bash
python3 tools/validate_existing_profile_inputs.py docs/assets/existing-profiles-evaluation.tgz --source-root docs/assets/existing-profiles --verify-results
```

This verifies the archive checksum, rejects unsafe archive members, extracts into
a temporary directory, verifies every payload checksum and reproduction input,
compares retained settings/tools with archive bytes, and runs all three real
result verifiers with mutation controls. It does not start a Gateway, download a
model, or qualify a new runtime.
