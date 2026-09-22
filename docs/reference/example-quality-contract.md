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
6. require the expected metric delta on the isolated path;
7. run key-scoped cleanup; and
8. prove absence and readiness after cleanup.

HTTP success and management readback are not independent delivery oracles.
Likewise, checking only the client response cannot prove that a rejected
request did not reach a backend. The canonical quickstart therefore uses a
backend-owned nonce log, an exact metric delta, an invalid-mutation state
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
