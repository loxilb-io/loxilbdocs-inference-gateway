# Example Verification Inventory

Every fenced example in the public pages and canonical snippets has exactly one
status in the machine-checked inventory. This prevents a new command, payload,
query, output sample, or diagram from silently bypassing classification.

## Statuses

| Status | Meaning |
|---|---|
| `verified` | The example passes the named public syntax, CLI, Swagger, schema, or metric-manifest gate. It does not imply Linux, GPU, HA, or production execution. |
| `blocked` | The example must not be followed until its documented contract or evidence blocker is resolved. |
| `illustrative-only` | The example explains shape or intent and is not represented as an executed workflow. |

The machine-readable inventory in `tests/contracts/docs_examples/example-inventory.json`
records the current counts and source digests. `verified` entries belong to the
named static gate; blocked and illustrative entries are never counted as a
Linux execution pass. Prose limitations remain on their canonical pages.

## Enforcement

Each entry records its source path, line, language, content digest, status, and
evidence class. Each mutating entry also records the associated independent-oracle,
negative-no-mutation, active-path, cleanup, and cleanup-verification contract.
The canonical quickstart owns the standalone mutation workflow; other fragments
link to it and remain illustrative.
CI fails closed when a block is added, removed, moved, or changed
without refreshing the inventory, when a status is outside the three allowed
values, when the evidence class is empty, or when a mutation contract is
missing or promoted without a complete workflow.

Exact duplicate fenced blocks are converged into public snippets and included
where needed. The current inventory has zero duplicate content digests, so a
shared command has one canonical source instead of several drifting copies.

`verified` is intentionally evidence-specific. For example, a CLI block may be
verified against the frozen command/flag contract while the corresponding
Gateway behavior remains unrun locally. See [Verification Status](verification-status.md)
for the evidence layers and the [Quickstart](../getting-started/quickstart.md)
for the canonical end-to-end beginner workflow.

The companion `tests/contracts/docs_examples/coverage-ledger.json` lists every
public fence, direct API/CLI mapping, and operation without a direct example.
CI regenerates this ledger; a missing direct example is a coverage gap, not a
claim that the operation is unimplemented. Runtime evidence remains separate.
