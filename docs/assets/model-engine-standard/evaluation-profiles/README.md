# Five-model QA evaluation profiles

These definitions and independent expected-token fixtures are evaluation inputs
for the 30-case manual. They do not add validated rows to the upstream catalog.
The vLLM definitions were retained from the earlier five-model QA package.
SGLang/TRT manifests declare the exact new evaluation image and version; their
engine-specific fixture directories retain the pre-existing expected tokens,
not expectations generated from an observed engine response.

Obtain each pinned tokenizer and tokenizer_config from the official model
repository under its license/access terms. No model weights, tokenizer files,
chat template copies, credentials, private hostnames or raw receipts are included.
Extract the template with `jq -j .chat_template` and require the profile's exact
hash before installation. See the 30-case manual for owner permissions, read-only
mounts, per-engine manifest selection, actual case results and rollback. A supplied
configuration is not a passed engine or Exact test.

Use `definitions-vllm/`, `definitions-sglang/` or `definitions-trtllm/` with the
matching engine. The common `definitions/` preserves the original baseline.
R1/SGLang records `completionsBos: true` for the existing contract because native
SGLang restores the model's BOS policy; raw Transformers v5 encoding alone omits
it. Official tokenizer/template bytes and independent probe fixtures are unchanged.
A declared API in a profile is not a complete end-user API qualification.

Unicode parity fixtures intentionally contain multiple languages. Their request
bytes and expected token IDs are preserved as verification inputs; they are not
operator documentation and must not be translated.
