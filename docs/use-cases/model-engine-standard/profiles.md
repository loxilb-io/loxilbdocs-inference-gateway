# Model Profile Catalog and Discovery

<!-- example-status-default: illustrative-only -->

The [five model cards](index.md#1-select-a-model-and-engine) now include paired
RR/Exact evaluation configurations and separately supplied QA profiles. Their
older recommendation labels are historical installation baselines. The Gateway's strict KV-exact profile catalog is a
separate list. A model name, a profile in a source checkout, a supported engine
row, a published runtime profile and a ready rule answer different questions.

## Which list should I use?

| List or surface | What it tells you | What it does not prove |
|---|---|---|
| Engine support catalog / capability matrix | Engine event/hash/probe contract and exact engine identity promotion | A model-profile row is validated or a newer card engine is interchangeable |
| Five standard model cards | Historical model/engine settings and operating limitations | Installed release support or registry membership |
| Release `docs/SUPPORTED-MODELS.md` / `install-models.sh --list` | Profile IDs, exact revisions, engine tuples, qualification state and required launch arguments | The profile is installed on this Gateway |
| `GET /config/ai/model-profiles` | Profiles currently published in the running registry generation | A discovered profile's source tuple has been promoted to supported |
| Profile detail | Model/alias policy, API surfaces, tokenizer/template identity | Rule admission or enforced Exact readiness |
| Rule `kvexactstatus` | The requested binding and its actual attestation/enforcement state | Capacity, fail-over or sustained latency qualification |

Only a source-catalog tuple with **`state: validated`** is supported under that
catalog's contract. `candidate` means evidence exists but promotion is incomplete;
`blocked` means that model/engine pair is refused for a named reason. Discovery
has no authority to promote either state. Follow the catalog matching the installed
Gateway release, not an unrelated checkout or the newest engine tag.

An engine-contract profile (for example `sglang-kv-rank-v1` or
`trtllm-kv-http-preview-v1`) describes how Gateway integrates with that engine.
A model profile (for example `r1-distill-qwen-15b-v1`) pins the model's tokenizer,
chat template and model identity. The former can be validated while a particular
model-engine tuple in the latter catalog is still candidate. An **engine**
`validated` label must not be used to promote a **model** row. See
[framework capability versus card verification](index.md#does-startup-reference-mean-the-framework-cannot-run-exact).

## Historical card profiles are not public catalog rows

The original cards and the committed catalog were compared by **exact profile ID,
model repository/revision and engine version**, not by model family name.
All five card IDs are absent from this catalog snapshot:

| Historical card | Historical profile ID | Membership in reviewed public catalog | Different catalog model in the same family |
|---|---|---|---|
| Gemma2 9B | `gemma2-9b-it-v1` | Absent | Gemma-3 1B / Gemma-4 E2B |
| Qwen2.5 7B | `qwen25-7b-instruct-v1` | Absent | Qwen3.6 / Qwen3.8 27B FP8 |
| Llama3.1 8B | `llama31-8b-instruct-v1` | Absent | Llama-3.2 1B |
| R1 Distill Qwen 7B | `r1-distill-qwen-7b-v1` | Absent | R1 Distill Qwen 1.5B |
| EXAONE3.5 7.8B | `exaone35-78b-instruct-v1` | Absent | EXAONE-4.0 1.2B |

**Absent, candidate and blocked are different states.** Absent means that this
catalog supplies no definition/installable tuple for that ID. Candidate means a
definition exists but has not been promoted to supported. Blocked is an explicit
refusal for a listed tuple. The four old "recommended" cards describe observations
on a different candidate runtime, not any of those source-catalog states.
Gemma's historical limited card does not become supported through its profile ID.

For example, `r1-distill-qwen-7b-v1` and `r1-distill-qwen-15b-v1` refer to
**7B and 1.5B** models, respectively; `15b` in that catalog ID must not be read
as a substitute for the 7B card. The Llama, EXAONE, Qwen and Gemma families also
have different model generations/sizes/revisions here. A family match is not a
valid alias, tokenizer/template match, engine contract or migration path.

`--include-candidates` opts into existing candidate rows only. It does not add
the five missing definitions, install the old private registry assets or promote
any tuple. Even seeing a historically named profile in an independently supplied
runtime registry would prove only discovery; support requires a matching release
catalog tuple and its qualification state.

Use the [five-model manual](matrix-manual.ko.md) for the separately supplied
`evaluation-profiles/` definitions, pinned manifests, independent token fixtures
and both routing modes. These assets are not installed by `--include-candidates`
and do not alter the catalog snapshot. The [result table](matrix-manual.ko.md#matrix-results)
distinguishes functional evidence from native architecture blockers. The separate
[R1 1.5B guide](routing-choice.md) remains a different evaluation tuple.
Supported Exact still requires a matching validated release tuple; this catalog
snapshot offers none. `READY` and profile discovery do not promote support.

## Additional source-catalog profiles

The following snapshot was reviewed on **2026-10-20** from the committed
[Gateway supported-model manifest](https://github.com/loxilb-io/loxilb-inference-gateway/blob/1d51393773e4974b5e356377496c9d677dba9f9c/scripts/models/validated-models.yaml).
This is a **historical source snapshot**, retained without rewriting its
qualification claims. All executable vLLM instructions in this use case now
select **0.31.0**. The snapshot is not a 0.31 compatibility list; matching new
manifest/fixture/runtime evidence is required. Its engine columns refer to **vLLM v0.28.0**, **SGLang v0.5.18** and
**TensorRT-LLM 1.3.0rc24**, respectively. The current five-model evaluation uses vLLM 0.31.0, TRT rc29 and SGLang 0.5.19, which retains tagged-array events and includes the native tokenize
integer-bound fix. The five
model profiles remain separate from these catalog rows. Do not mix a profile from
one tuple with a card's engine version.

| Model repository | Profile ID | vLLM | SGLang | TRT / PyTorch |
|---|---|---|---|---|
| `allenai/OLMo-2-0425-1B-Instruct` | `olmo2-0425-1b-v1` | candidate | candidate | blocked · `architecture_unsupported` |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` | `r1-distill-qwen-15b-v1` | candidate | candidate | candidate |
| `google/gemma-3-1b-it` | `gemma3-1b-it-v1` | candidate | candidate | candidate |
| `google/gemma-4-E2B-it` | `gemma4-e2b-it-v1` | candidate | candidate | blocked · `hardware_unsupported` |
| `meta-llama/Llama-3.2-1B-Instruct` | `llama32-1b-v1` | candidate | candidate | candidate |
| `LGAI-EXAONE/EXAONE-4.0-1.2B` | `exaone4-12b-v1` | candidate | candidate | candidate |
| `microsoft/Phi-4-mini-instruct` | `phi4-mini-instruct-v1` | candidate | candidate | candidate |
| `ibm-granite/granite-4.2-3b` | `granite42-3b-v1` | candidate | candidate | blocked · `architecture_unsupported` |
| `mistralai/Ministral-3-3B-Instruct-2512` | `ministral3-3b-v1` | blocked · `engine_renderer` | blocked · `engine_renderer` | blocked · `checkpoint_format` |
| `skt/A.X-3.1-Light` | `ax31-light-v1` | candidate | candidate | candidate |
| `Qwen/Qwen3.6-27B-FP8` | `qwen36-27b-fp8-v1` | candidate | candidate | candidate |
| `Qwen/Qwen3.8-27B-FP8` | `qwen38-27b-fp8-v1` | candidate | candidate | candidate |
| `openai/gpt-oss-20b` | `gptoss-20b-v1` | blocked · `engine_renderer` | candidate | blocked · `engine_renderer` |

This snapshot contains **13 profiles / 39 model-engine tuples: 31 candidate,
8 blocked, 0 validated**. It is a catalog of available definitions and limitations,
not a list of 39 production-supported choices. The normal installer must not be
assumed to install candidates by default. `--include-candidates` is an explicit
evaluation opt-in; it does not change support state.

The full revisions, engine versions and declared mode/API coverage are in the
[public catalog snapshot JSON](../../assets/model-engine-standard/profiles/catalog-snapshot.json)
and the [configuration ZIP](../../assets/model-engine-standard.zip).
The snapshot omits internal evidence locations and runtime credentials. Always
recheck the [upstream supported-model page](https://github.com/loxilb-io/loxilb-inference-gateway/blob/main/docs/SUPPORTED-MODELS.md)
for the exact release you install.

### Read the blocked reasons and mode limits

- `architecture_unsupported`: that pinned engine has no usable model implementation.
- `hardware_unsupported`: the tested hardware/backend combination is blocked;
  this does not assert that every GPU is unsupported.
- `engine_renderer`: the engine's renderer/tokenizer differs from the strict
  profile's verified template contract; do not bypass it by editing the template.
- `checkpoint_format`: the pinned loader cannot consume that official checkpoint format.

TRT entries in this snapshot cover converged chat only; P/D or completions must
not be inferred. Even candidate vLLM/SGLang entries can have incomplete evidence
for a declared API surface. Read the qualification columns and required launch
arguments in the release catalog. For example, a hybrid or sliding-window model
can have different cache groups and block/chunk geometry; copying Qwen's block
settings is not a registration procedure. llama.cpp has no strict KV-exact rows
in this catalog and uses its [ordinary integration path](../../ai-gateway/llamacpp-integration.md).

## Inspect the release catalog locally

Run these commands **from the approved Gateway source checkout matching your
installed image**, not from the extracted configuration package:

```bash
scripts/models/install-models.sh --list
scripts/models/install-models.sh --dry-run --engine vllm --models olmo2-0425-1b-v1
```

The first command lists definitions; the second previews installation without
writing files. With only candidate/blocked rows, a preview can skip/refuse the
requested model under normal support policy. That is not an installation failure
to work around silently. For an approved evaluation, add `--include-candidates`
explicitly and retain the unpromoted state. Obtain appropriate model access for
gated repositories. Full installation, artifact verification, registry mounts
and reload are covered by [Prepare a Supported Model](../../getting-started/prepare-supported-model.md).
The public model-registration tool is the only script dependency in this path;
there is no new profile-generation script in this package.

## Discover what this Gateway has published

On the controller, use `CONTROL_API`, `RUN` and the protected management header
from [Gateway prerequisites](operations.md#prerequisites):

```bash
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/ai/model-profiles" > "$RUN/model-profiles-live.json"
jq '{registryGeneration,setDigest,profiles:[.profiles[] | {
  profileId,gen,baseModel,aliasPolicy,allowedAliases,supportedApis,
  tokenizerSha256,templateSha256
}]}' "$RUN/model-profiles-live.json"
```

Expected: the published generation and zero or more entries. Generation `0` with
an empty array means no published registry, not a ready strict model. A populated
array is only runtime discovery. Match an entry to a **validated release tuple**
before calling it supported. The five historical card profile IDs may be absent;
never substitute an unrelated profile just because its model has a similar name.

Choose an exact ID returned by that list. The following example ID is usable
only if it appeared in your discovery response and is permitted by your release
or explicitly authorized candidate-evaluation policy:

```bash
export PROFILE_ID=olmo2-0425-1b-v1
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/ai/model-profiles/$PROFILE_ID" > "$RUN/model-profile-detail.json"
jq '{profileId,gen,baseModel,aliasPolicy,allowedAliases,supportedApis,
  tokenizerSha256,templateSha256}' "$RUN/model-profile-detail.json"
```

Expected: detail matches the selected published profile; an absent profile returns
404. Use `profileId`, not repository name, in `kvModelProfile`. Confirm that
`model_name` is admitted by `baseModel`/alias policy, `chat` is in `supportedApis`,
the engine tuple and tokenizer/template are exact matches, and the final
[rule binding](operations.md#enable-conditional-vllm-exact) reaches `READY` with
the matching generation and unfenced enforcement. Retain `setDigest` and
`bindingDigest` separately: one identifies the published set, the other the rule's
binding. Never replay discovery or status JSON as a create body.

## Missing or changed profiles

If a profile is absent, mismatched, blocked or still candidate, keep that state
visible and stop the supported Exact path. Use a separately qualified RR service
if appropriate. New model support requires a published profile and engine contract,
verified tokenizer/template/artifacts and the release's qualification/promotion
process; an operator cannot create support by changing `model_name` in a JSON file.
Registry upgrades also require rule migration/readiness and chat/SSE rechecks.
