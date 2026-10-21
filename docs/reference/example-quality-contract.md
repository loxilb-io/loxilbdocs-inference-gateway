# Example quality contract

Public examples are classified as `verified`, `blocked`, or
`illustrative-only` in the generated [example inventory](example-inventory.md).
That classification is about the named documentation gate. It is not a claim
that a command ran on your deployment.

## Mutating example contract

A command that uses `POST`, `PUT`, `PATCH`, or `DELETE` on the management API,
or a mutating `loxicmd` verb, must be treated as one of two things:

- a **standalone workflow** that supplies the complete lifecycle below; or
- an **illustrative fragment** that must not be executed as a standalone
  procedure and instead links to the canonical
  [quickstart workflow](../getting-started/quickstart.md).

The documentation gate discovers these commands from their syntax. A new
mutation cannot silently inherit a page-level `verified` label.

The complete lifecycle is:

1. prove readiness and take the relevant pre-change readback;
2. apply the exact create or update;
3. read back the exact key and compare material fields;
4. send positive traffic and prove delivery with a backend-owned receipt;
5. send a negative request or invalid mutation and prove the backend receipt
   or management state did not change;
6. verify metric activation and authenticated scrape; require a delta only
   for a family whose update semantics count the controlled stimulus;
7. run key-scoped cleanup; and
8. prove absence and readiness after cleanup.

HTTP success and management readback are not independent delivery oracles.
Likewise, checking only the client response cannot prove that a rejected
request did not reach a backend. The canonical quickstart therefore uses a
backend-owned nonce log, an authenticated scrape, an invalid-mutation state
comparison, and post-cleanup absence/readiness checks.

## Address and secret hygiene

Use RFC 5737 IPv4 documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`,
and `203.0.113.0/24`) or RFC 3849 IPv6 addresses in public examples. The three
RFC 1918 network names may be mentioned when explaining policy, but RFC 1918
host addresses are rejected by the example gate. Credentials belong in
permission-restricted files; do not put bearer tokens or API keys in command
arguments.

## Evidence boundary

The example gate proves classification, syntax, frozen API/CLI membership,
request-schema compatibility, mutation-contract coverage, and address
hygiene. Linux data-plane behavior, GPU execution, HA behavior, current CI
results, immutable release artifacts, and publication approval remain
separate evidence lanes.


## Static coverage limits

`verified` means the named static documentation checks passed. It does not mean
that every fenced example was executed. The inventory also retains blocked
and illustrative examples; neither category counts as a runtime pass.

The CLI fixture now records the selected source revision, short aliases, and
value-taking flags. The parser rejects unknown short options and missing values
and accepts persistent options before a command. This is a completion-based
check, not a replacement for the Linux binary's typed argument validation.

Both Swagger responses and effective security requirements are retained in the
frozen contract. Drift detects changes to them; it does not automatically assert
that a documented HTTP response matches the running handler or generated binder.
The quickstart records the observed invalid-protocol response separately.

File-backed management examples are bound by exact documentation path and file
reference in `tests/contracts/docs_examples/body-bindings.json`. The Linux gate
executes the documented jq producers against all 30 public model/engine input
assets, checks their hashes, and validates the actual generated bodies. An
unknown path, changed producer, changed asset, or altered body fails the gate;
there is no basename-based representative substitution. Deployment-owned secret
files are not supplied as executable documentation examples.

`tests/contracts/docs_examples/coverage-ledger.json` maps every public fence to
its direct API operations and CLI commands, and lists operations with no direct
example. Those mappings are static coverage. They do not attest runtime or
release results. The Linux-only `tools/validate_cli_runtime.py` checks a chosen
binary's explicitly listed parsing and wire cases against a loopback fixture.
It does not promise that every invalid enum or cross-field combination is rejected. The response
gate `tools/validate_response_contracts.py` checks exact statuses, response
schemas, receipt deltas and unchanged state for the selected Quickstart cases.
Its expected-case list is deliberately finite and asserts only the listed fields;
it does not validate every Swagger response property or promise full API coverage.

For candidate validation, provide both repositories and exact source refs to
`tools/validate_gateway_docs.py --gateway-repo ... --gateway-ref ...
--cli-repo ... --cli-ref ...`. The gate regenerates both candidates; a frozen CLI
fixture is no longer substituted for the selected CLI source.

Request outcome/cause, P/D phase/status and prefill-fallback reason enums are
extracted from the selected Gateway's `api/prometheus/ai_metrics.go`. The
contract records that file's hash and allowed outcome/cause and phase/status
combinations. A changed declaration shape fails extraction for review.
`validate_examples.py` rejects unknown exact closed values and selectors that
match no source-declared combination, including regex and negative filters.
This is a finite selector check, not a full PromQL parser or runtime scrape.
The metric contract tests cover valid values, impossible pairs, and declaration
mutations; refreshing the fixture cannot substitute for those checks.
