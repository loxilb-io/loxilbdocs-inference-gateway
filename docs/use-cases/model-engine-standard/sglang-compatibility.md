# SGLang Event-Wire Compatibility

<!-- example-status-default: illustrative-only -->

The official reference baseline for this five-model guide is **stock SGLang v0.5.19**, pinned to
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`.
Use the [current case results](results.md#matrix-results) for actual
model/mode acceptance. Source inspection and an old version's PASS are not new
GPU evidence.

## Version selection from the existing history

The [engine capability history](../../concepts/engine-capability-matrix.md)
records v0.5.18 with the `sglang-kv-rank-v1` tagged-array contract and prior live
Qwen3 0.6B integration. The new 0.5.18 trial also observed real tagged-array
`BlockStored` events and passed Qwen2.5/Llama3.1 RR and Exact functional checks.

Two model-specific preparation limits were found. R1's native completions adds
one BOS; its SGLang profile must record the existing `completionsBos:true` policy.
EXAONE's 0.5.18 `/v1/tokenize` returned HTTP 500 because the tokenizer's maximum
length exceeded the response serializer's 64-bit range. RR completed, but Exact
stopped with `probe_schema_mismatch`. Unfinished Gemma 0.5.18 testing is not PASS
or a runtime failure.

The official **0.5.19** source retains tagged-array events in
[KV event definitions](https://github.com/sgl-project/sglang/blob/v0.5.19/python/sglang/srt/disaggregation/kv_events.py)
and uses the configured context length when an oversized tokenizer maximum
cannot be serialized in the [tokenize handler](https://github.com/sgl-project/sglang/blob/v0.5.19/python/sglang/srt/entrypoints/openai/serving_tokenize.py).
This makes it the stock successor selected for fresh five-model qualification.
The guide does not mount a custom native-engine patch. The engine-specific QA
profiles retain official tokenizer/template bytes and independent probe fixtures.
The unchanged source catalog still describes its older tuples; no promotion is
inferred from selecting this version.

The selected 0.5.19 image also emitted a real GPU `BlockStored` packet with
an outer three-element array, tagged-array event entry and rank 0. The recorded
payload SHA256 is `dd260b052f805abb812ae736306b7e5e1cb76ff707aa2359e7e66bad2b993515`.
This is wire evidence; use the per-model result table for routing acceptance.

The [version-selection record](../../assets/model-engine-standard/sglang-version-selection.json)
separates historical wire samples, selected image identity, source evidence and
current runtime results.

## Separate development request: tagged-map events

A separate stock **0.5.21** evaluation used image
`sha256:2dbe4c7f53230b09aaa8fa41891c13c51d9d2e253f486a70822aaf08783fff75`.
Its live packet contained a positional batch and **tagged-map events**, while
this Gateway's SGLang contract expects tagged-array event entries. Qwen2.5 and
Llama3.1 native/RR checks passed, but Exact remained at `TOKEN_PARITY_VERIFIED`
with `challenge_timeout`. Unfinished 0.5.21 models are not counted as passes or failures.

Support for SGLang tagged-map events is recorded as a **separate development
request**. Closure requires a matching versioned wire/rank contract, positive
and rejected fixtures, preserved tagged-array compatibility, and fresh GPU
native/RR/Exact proof. Changing only the mode/profile or claiming SGLang uses the
vLLM contract does not resolve the wire mismatch. The failed 0.5.21 observations
are retained separately from the compatible-version operator guide.

The [catalog and installer integration page](catalog-installer.md) tracks the core-team
registration proposal, successful staging checks and unresolved integration findings.
