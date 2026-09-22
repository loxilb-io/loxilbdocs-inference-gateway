# Model Profiles and KV-Exact Readiness

Use a published model profile to bind a KV-exact rule to one verified tokenizer/template
identity, then verify what the data plane actually enforces. A successful rule `POST` or a
matching `GET` response is not the final readiness signal.

!!! info "Current-main contract"
    Model-profile discovery, `kvModelProfile`, `kvExactApiMode`, and `kvexactstatus` are
    implemented on Gateway `main` at the contract snapshot used by this site. They are absent
    from Gateway `v0.9.8.9-rc.1`. Check the installed Gateway identity before using these
    routes; CLI `v0.9.8.9-rc.2` does not make an older Gateway implement them.

## What each surface answers

| Surface | Question it answers | Authority boundary |
|---|---|---|
| `GET /config/ai/model-profiles` | Which operator-published profiles are discoverable now? | Read-only cache of the current registry generation; rule admission revalidates at `POST` time. |
| `GET /config/ai/model-profiles/{profile_id}` | What exact tokenizer, template, aliases, and API surfaces does one profile declare? | Same schema as a list entry; artifact paths are deliberately not exposed. |
| `kvModelProfile` | Which one published profile should this rule bind? | REST-only create/replace field; scalar and normally immutable. |
| `kvExactApiMode` | Which request surfaces should exact hashing serve: `completions`, `chat`, or `both`? | REST-only create/replace field; scalar and immutable. |
| `GET .../kvexactstatus` | Which composed profile/engine binding is desired and actually enforced? | Dedicated read model; never replay it as load-balancer configuration. |

`setDigest` identifies the whole published profile set. `bindingDigest` identifies one rule's
composed model-profile and engine-contract binding. They identify different objects and must not
be compared with each other.

## Discover a profile before creating the rule

Prepare a protected management header file once:

```bash
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

List the published generation and retain the identity used for the decision:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/ai/model-profiles" \
  > model-profiles.json

jq '{registryGeneration, setDigest, profiles: [.profiles[] | {
  profileId, gen, baseModel, aliasPolicy, allowedAliases,
  supportedApis, tokenizerSha256, templateSha256
}]}' model-profiles.json
```

`registryGeneration: 0` with an empty `profiles` array means that no registry is published. It is
a valid legacy-mode discovery response, not readiness for a strict rule. A detail lookup returns
`404` when the profile is absent from the currently published generation:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/ai/model-profiles/example-profile" \
  | jq .
```

Choose a profile only when:

- `baseModel` or `allowedAliases` admits the rule's exact `model_name`;
- `supportedApis` contains every surface the rule will declare;
- a chat profile exposes a verified template identity; and
- the engine tuple is appropriate for the topology in the
  [Engine Capability Matrix](../concepts/engine-capability-matrix.md).

## Create a strict KV-exact rule with REST

The example is a single-pool vLLM shape. Replace `example-profile` with an ID returned by
discovery and make the block/hash settings match the deployed engine. For vLLM, first require
`kv_exact_vllm.ready=true` from `GET /status/capabilities`.

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/loadbalancer" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data-binary '{
    "serviceArguments": {
      "externalIP": "192.0.2.10",
      "port": 8080,
      "protocol": "tcp",
      "mode": 4,
      "sel": 0,
      "model_name": "Qwen/Qwen3-0.6B",
      "kvExactMode": 3,
      "kvEngineType": "vllm",
      "kvBlockSize": 16,
      "kvHashAlgo": "sha256_cbor",
      "kvModelProfile": "example-profile",
      "kvExactApiMode": "both"
    },
    "endpoints": [
      {"endpointIP": "198.51.100.11", "targetPort": 8000, "weight": 1},
      {"endpointIP": "198.51.100.12", "targetPort": 8000, "weight": 1}
    ]
  }'
```

`kvModelProfile` and `kvExactApiMode` have no corresponding `loxicmd create lb` flags in the
current CLI. Model-profile discovery and resolved status also have no dedicated CLI commands.
Use REST for this strict workflow; do not invent flags or infer strict readiness from
`loxicmd get kvinventory`.

## Verify the binding and enforcement

First verify the stored declaration, then query the dedicated status resource:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" \
  | jq '.lbAttr[] | select(.serviceArguments.port == 8080) |
    .serviceArguments | {
      model_name, kvExactMode, kvEngineType, kvModelProfile, kvExactApiMode
    }'

curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/kvexactstatus?model_name=Qwen%2FQwen3-0.6B" \
  > kv-status.json

jq '.kvExactStatusAttr[] | {
  ruleIdentity, modelName, engineFamily, apiMode,
  modelProfileId, modelProfileGen,
  engineContractId, engineContractGen,
  bindingGen, bindingDigest, requiredEvidenceLevel,
  desiredState, enforcedState, reasonCodes,
  enforcement
}' kv-status.json
```

Treat these states conservatively:

| `enforcedState` | Operator interpretation |
|---|---|
| `READY` | Strict binding is attested and enforced under the normal identity trust contract. |
| `READY_FUNCTIONAL_ONLY` | Functionally attested under an explicit limited-trust opt-in; do not report it as `READY`. |
| `PROFILE_VALIDATED`, `PENDING_DATAPLANE_CONTRACT`, `TOKEN_PARITY_VERIFIED`, `ENGINE_HASH_ATTESTED` | A ladder step or transition, not final readiness. |
| `DEGRADING`, `DEGRADED`, `ENFORCEMENT_FAULT`, `REQUIRES_MIGRATION` | Exact routing is fenced or requires operator action. Inspect `reasonCodes`, `enforcement.enforced`, and `enforcement.goFenced`. |
| `LEGACY_ACTIVE_UNATTESTED` | Profile-less legacy operation. Active does not mean strict or attested. |
| Unknown value | Render it unchanged and treat it as not ready/in transition. The vocabulary is open. |

For a strict rule, require the selected `profileId`/generation to equal
`modelProfileId`/`modelProfileGen`, retain `bindingDigest` as the binding identity proof, require
the intended `apiMode`, and check `enforcement.goFenced` independently. Inventory and hit metrics
are still needed to prove event ingestion and traffic engagement.

## Rejections are no-mutation results

The Gateway rejects unsupported declarations before rule state changes. Important examples are:

| Rejected declaration | Why |
|---|---|
| `kvExactApiMode` or `kvModelProfile` without `kvExactMode: 1` or `3` | The fields are meaningless without an exact-routing tier. |
| `kvExactMode: 1` without P/D, or `kvExactMode: 3` with P/D | The topology and exact mode disagree. |
| API surface not contained in the profile, or chat without a validated renderer | The Gateway refuses silent fallback to an untemplated or unsupported hash. |
| Unknown profile, alias mismatch, artifact mismatch, or unavailable engine-contract registry | Strict admission fails closed. |
| Changing `kvExactApiMode`, dropping a profile, or changing one bound profile to another | These identities are immutable; delete and recreate the rule. |

The one migration exception attaches a profile to an existing profile-less KV-exact rule. It
must preserve the raw `kvExactApiMode` declaration exactly. A refused attach leaves the rule and
data plane unchanged. After every rejected create or replace, independently read the rule and
`kvexactstatus`; HTTP status alone is not the no-mutation oracle.

## Evidence boundary

The documentation contract freezes both Swagger files, the support catalog, unit-test schemas,
and the committed engine scenarios. That proves current static contracts and reproducible
scenario definitions. It does not rerun Linux, GPU, HA, or production qualification. Exact
real-engine support remains limited to the immutable tuples marked `validated` in the
[Engine Capability Matrix](../concepts/engine-capability-matrix.md).

## Cleanup

```bash
curl --fail-with-body --silent --show-error \
  --request DELETE --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/hosturl/192.0.2.10/externalipaddress/192.0.2.10/port/8080/protocol/tcp?model_name=Qwen%2FQwen3-0.6B"

rm -f ./control-plane.headers ./model-profiles.json ./kv-status.json
unset CONTROL_PLANE_TOKEN CONTROL_API
```

## See also

- [KV-Cache-Aware Routing](kv-caching.md)
- [Engine Capability Matrix](../concepts/engine-capability-matrix.md)
- [Troubleshooting](../operations/troubleshooting.md)
- [Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md)
