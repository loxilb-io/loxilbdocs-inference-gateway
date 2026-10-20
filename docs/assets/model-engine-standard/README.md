# Model and engine standard configuration files

These files accompany the Model & Engine Standard Setup use case. Extract the
ZIP into a new working directory and run commands individually from the guide.
There is no automatic deployment script. All examples require site adaptation.

**Runtime evidence publication is pending for the thirty standard-card cases.**
Their `currentPublicTupleRuntime` values remain `not-run`. This edition includes
configuration inputs and required evidence, but no `matrix-results.json` or
`matrix-request-ledger.json`. Missing results do not establish a pass, a native
architecture verdict or support promotion. The separate R1 1.5B candidate
example's bounded vLLM summary retains its own scope and open gates.

- `models/`: five official model revisions, dtype and model-specific arguments.
- `engines/`: three current evaluation engine references, pinned by digest.
- `rules/`: 13 original-card RR startup shapes for local evaluation.
- `routing-choice/`: six paired RR/Exact JSON files for the public-catalog R1
  1.5B evaluation on vLLM 0.31/SGLang/TRT, with engine settings and requests.
  vLLM includes a separate 0.31 Exact evaluation manifest and a sanitized bounded
  GPU QA summary; old 0.28 catalog qualification is not inherited.
  TRT needs a separately provisioned matching rc24 image; none is fetched by
  the public installer. These remain evaluations with explicit open qualification gates.
- `sglang-version-selection.json`: compatible tagged-array baseline and separate tagged-map development request.
- `qualification-matrix.json`: all 30 original-card mode cases and six separate
  candidate-example mode cases, prerequisites and required closure evidence.
- `historical-exact/`: four old vLLM Exact shapes, reference only; not inputs to
  the current workflow. Use the new `matrix-configurations/` and separate
  `evaluation-profiles/` together; historical runtime support is not inherited.
- `requests/`: model-specific chat and streaming request bodies.
- `trtllm.yaml`: PyTorch backend cache-reuse/memory configuration.
- `profiles/catalog-snapshot.json`: additional strict-profile definitions, engine tuple
  states and source identity; not an installed or promoted model list.
- `failover/`: separate historical P/D ENV, rule and role-specific engine KV JSON.
  These inputs are illustrative and must not be applied to the converged pool.
- `catalog.json`: all 15 combinations and their evidence classifications.
- `verification/`: one optional QA receipt collector, with use and cleanup instructions; no deployment automation.
- `SHA256SUMS`: integrity of this configuration package, not a runtime attestation.

Replace documentation VIP/host `192.0.2.10` and worker addresses
`192.0.2.20`, `192.0.2.21`, `192.0.2.22` with allocated reachable addresses.
The example ports are service `28180`, engine/probe `8000`, vLLM events `5557`.
Keep `host` and `externalIP` consistent with the guide's IP-hosted service.

Current five-model evaluation inputs:

- `matrix-configurations/`: all 30 model/engine/RR-or-Exact bodies. Native
  architecture-blocked cases are configuration references, not working recipes.
- `evaluation-profiles/`: five QA definitions, per-engine versioned manifests,
  independent expected-token fixtures and pinned weight checksum indexes.
  Obtain licensed tokenizer/template files from the official model repository;
  the operator manual checks hashes and permissions before registry publication.

RR omits strict profile binding. Exact requires the matching evaluation registry,
engine contract, READY/unfenced state and traffic evidence. These QA profiles are
separate from the unchanged upstream catalog (31 candidate, eight blocked, zero
validated); all five IDs are absent from that snapshot. Candidate opt-in does not
install these definitions or promote their support state. Historical recommendation
and reference classes remain in `catalog.json` for comparison with earlier evidence.

No Gateway binary, weights, tokenizer/template copies, credentials or private
receipts are distributed. Small independent token fixtures are included; they
are evaluation inputs, not model weights or generated acceptance results.
Use the five-model manual's current engine launch arguments and case verdicts.
Older `rules/` and `historical-exact/` files retain earlier settings. Gemma2 and
EXAONE3.5 are native architecture-blocked on the pinned TRT PyTorch image;
other backends require separate qualification. A pinned digest does not promise
pull access or compatibility on a different GPU/runtime.

Follow the guide for readiness, deployment, readback, completed chat/SSE,
negative cases, owned-resource cleanup and rollback. Commands remain illustrative
until independently qualified on your deployment. Do not source files from an
untrusted origin or run them without reviewing their contents.
