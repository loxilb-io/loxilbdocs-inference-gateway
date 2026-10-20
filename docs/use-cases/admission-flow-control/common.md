# Common API conventions and rollback semantics

Read field scope and effective state before changing a policy. These conventions apply to every chapter in the admission lab.

## Prerequisites

Complete [preparation](setup.md), preserve original configuration and prove the baseline receipt. Each mutation is part of the multi-page lab lifecycle; the [Quickstart](../../getting-started/quickstart.md) is the site's canonical standalone mutation workflow. Commands and expected results are conditional on the selected deployment contract.

## Units and purpose

| Control | Unit | What it bounds | Verification |
|---|---|---|---|
| `rps` | Requests/second | User or tenant admission rate | Typed 429 and independent receipt0; refill recovery |
| User `burst_size` | Requests | RPS bucket depth, not sustained rate | Back-to-back burst and a denied next request |
| `tokens_per_min` | Input+output tokens/minute | Token admission/accounting budget | Reservation, usage delta and isolated probes |
| Tenant `burst_pct` | Percent of TPM | Token bucket capacity | Effective bucket and timed quota probes |
| Request `max_tokens` | Completion tokens | Declared output ceiling used with prompt estimate for reservation | Held claim plus blocked/released probe |
| Response `usage` | Actual reported tokens | Settlement after backend processing | Per-request consumed/missing/estimated deltas |
| `fc_max_outstanding` / `fc_ep_max_inflight` | Executing requests | Model pool / endpoint capacity | Live inflight and released permit |
| `fc_max_queue_depth` | Waiting requests | Bounded H1 waiting population | queued plus waiter receipt0 |
| `fc_max_queue_wait_ms` | Milliseconds | Maximum wait before dispatch | 504 timeout and receipt0 |
| Byte QoS / backpressure | Bytes, bytes/second (API policy CIR uses Mbps) | Forwarding pace/buffer pressure | Directional traffic and park/resume observations |

`model_limits` in the user and tenant payloads on this guide contains TPM limits only; it has no per-model RPS field. User and tenant aggregate RPS are the demonstrated request-rate controls. Do not add an invented rps property to a model-limit item.

Do not call all these TPS. Continuous TPM refill is not an RPS burst, GPU memory capacity or a reset at the next minute. A zero usage metric alone proves neither claim return nor a free execution permit. See [byte QoS](../../operations/ai-qos.md) for policy attachment, units and rate measurements; small SSE responses in this lab are insufficient to prove watermark backpressure.

## Common curl and inference fields

| Option / field | Required / example | Meaning and change coupling |
|---|---|---|
| `$API` | Lab management URL through /netlox/v1 | Configuration only, not inference |
| `-sS`, `-i`, `-D`, `-o`, `-w` | Observation options | Show errors, save headers/body, record status/version separately from curl exit |
| `-X`, `Content-Type`, `--data-binary @file` | Per operation; JSON configuration | Check exact method and inspect the complete body before POST |
| `--config <identity>.curl` | Required for protected inference | Host file containing private Bearer header; refresh before expiry |
| `--cacert`, `--cert`, `--key` | Required for respective TLS verification/mTLS | Host-side client trust/identity; distinct from Gateway backend registry IDs |
| `--http1.1`, `--http2` | Version controls | Record actual VERSION; H2 option alone is not negotiation proof |
| `--max-time` | Seconds | Client bound, independent of Gateway queue/stream timeout |
| `-N`, `--limit-rate` | SSE observation / bytes per second | Does not configure a Gateway token budget |
| Inference `model`, `messages` | Required by the fixture request | Exact allowed model and raw prompt; changing bytes can change reservation estimate |
| `X-Test-Nonce`, `nonce` query | Fixture-only unique case identifier | Independent receipt; not a production policy API field |
| Fixture hold/release/delay/usage options | Scenario-specific | Synthetic backend behavior; never add these to Gateway policy JSON |

## Load-balancer request versus response

POST /config/loadbalancer accepts `serviceArguments` and `endpoints[]`. Use the complete downloadable JSON for a chapter. GET /config/loadbalancer/all returns `lbAttr[]`.

| Input location | Required / lab value | Default / change impact |
|---|---|---|
| `serviceArguments.externalIP`, `port`, `protocol` | Required service key; 192.0.2.254, chapter port, tcp | Change URLs and DELETE key together |
| `mode` | Explicit4 | FullProxy prerequisite for these TLS/JWT/FC exercises |
| `sel` | Explicit0 | Round-robin; changing weights alone does not establish weighted selection |
| `host`, `path_prefix`, `path_match_mode` | Explicit192.0.2.254, /, prefix | Routing and deletion key; independent of backend SNI |
| `model_name` | Explicit llama-70b or mistral-7b | Must match request model and JWT permission |
| `api_key_auth`, `jwt_auth_profile` | jwt, kc | Enables data-plane JWT and references an existing profile |
| `inactiveTimeOut` | Optional30seconds here | Idle connection bound, distinct from stream duration |
| `endpoints[].endpointIP`, `targetPort`, `weight` | Explicit address/port, weight1 | Routing destination; coordinate receipt host, SAN and fixture port |

`backend_tls_effective` and `fc_effective` are **GET-only observations**, not request fields. Read effective values/source/generation, saved IDs and live inflight/queued. Applied means installation, not handshake success. A stored cert ID is not proof of backend peer identity. Only actual response, nonce receipt and peer fingerprint establish the corresponding runtime behavior.

## Zero, omission, empty arrays and DELETE

| Resource | Omission / zero / empty list | Removal and verification |
|---|---|---|
| User quota POST | Whole-row replacement; omitted model_limits or [] clears its model set; zero quota fields can inherit defaults | DELETE tenant/user full key, GET404, then default-aware traffic |
| Tenant quota POST | Aggregate omissions write0; model_limits is per-model upsert; omission/[] preserves old model rows | No tenant DELETE; POST aggregate0 and every removed model TPM0, then GET and traffic |
| Defaults POST | Scope-row upsert, positive fields override per rung; zero falls through; all-zero row rejected | DELETE global/rule scope (rule_ident query for rule); GET404 or restore saved row |
| FC fields on create | Omission/0 resolves process/product defaults | Read effective source |
| FC fields on replace | Omission preserves stored values; 0/inherit resets to defaults; null rejected | Explicit fc_mode=off disables gate, not numeric0 |
| LB rule POST | Same full key may replace; identical no-op can return409 | Full-key DELETE and GET absence; endpoint-only changes may require listener takeover |
| JWT profile | Upsert affects referencing rules | Remove references first; in-use DELETE409, then profile-list absence |
| Certificate registry | PUT replaces same ID; malformed PEM/key must preserve prior identity | Referenced DELETE400; unreferenced DELETE204 / GET404 |

Before editing, retain original **request** payloads as rollback inputs. A GET response can contain read-only fields and must not blindly become a POST. On a partial tenant write failure inspect aggregates and all model rows. Reapply the complete intended state. Deleting a policy row can expose a default, so absence alone does not prove unlimited admission.

## Verification, expected results and cleanup

Each chapter follows pre-change GET→explicit JSON/configure→saved/effective GET→positive and denied requests with independent receipts→resource/accounting evidence→delete or restore→GET and positive recovery. Keep metrics snapshots isolated by tenant/user/model/service and elapsed interval. Capture errors as well as success. A scrape failure, absent receipt server, timeout or unexecuted case is not a zero/PASS.

Rule deletion uses host/VIP/port/protocol **and** path/model query. A final rule can leave a kept socket listener. Before recreating or changing its endpoint, record the matching takeover event count; wait for a new event after POST before fresh traffic. This does not apply to every policy mutation. Refer to [TLS updates](tls-failures.md#verify-endpoint-update-listener-takeover-and-frontend-policy-preservation) and [cleanup](cleanup.md).

## Troubleshooting

For an unexpected denial read the typed error first, then the exact explicit/default policy and effective capacity state. Separate TLS-before-HTTP refusal from an HTTP401/403/429 and backend TLS502/503. Confirm a fresh credential and a successful baseline before attributing a result to the changed policy.
