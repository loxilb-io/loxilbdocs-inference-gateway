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

The tracked inventory currently classifies 390 fenced blocks: 20 `verified`,
370 `illustrative-only`, and 0 `blocked`. A zero blocked count means there is no
published fenced example instructing the reader to perform a known-blocked
operation; prose limitations remain documented on their canonical pages.

## Enforcement

Each entry records its source path, line, language, content digest, status, and
evidence class. CI fails closed when a block is added, removed, moved, or
changed without refreshing the inventory, when a status is outside the three
allowed values, or when the evidence class is empty.

Exact duplicate fenced blocks are converged into public snippets and included
where needed. The current inventory has zero duplicate content digests, so a
shared command has one canonical source instead of several drifting copies.

`verified` is intentionally evidence-specific. For example, a CLI block may be
verified against the frozen command/flag contract while the corresponding
Gateway behavior remains unrun locally. See [Verification Status](verification-status.md)
for the evidence layers and the [Quickstart](../getting-started/quickstart.md)
for the canonical end-to-end beginner workflow.
