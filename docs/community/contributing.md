# Contributing

The LoxiLB Inference Gateway is an open-source project and contributions are welcome —
whether you are fixing a typo, improving an example, or documenting a feature that isn't
covered yet.

## Two repositories

| Repository | What it holds | Where to contribute |
|---|---|---|
| [loxilb-inference-gateway](https://github.com/loxilb-io/loxilb-inference-gateway) | The gateway source code, REST API spec (`api/swagger.yml`), and CI scenarios (`cicd/`) | Code, API, and behavior changes |
| [loxilbdocs-inference-gateway](https://github.com/loxilb-io/loxilbdocs-inference-gateway) | This documentation site | Documentation changes |

Report a bug in the gateway itself in the **code** repository; report a documentation problem
(inaccuracy, broken link, missing content) in the **docs** repository.

## Contributing to the docs

1. Fork the docs repository and branch from `main`.
2. Preview locally:
   ```bash
   pip install -r requirements.txt
   mkdocs serve            # http://127.0.0.1:8000
   ```
3. Make sure the strict build passes (this is what CI runs):
   ```bash
   python tools/validate_examples.py
   python tools/refresh_example_inventory.py --check
   python tools/render_metrics_reference.py --check
   python -m unittest discover -s tests -p 'test_*.py' -v
   mkdocs build --strict
   ```
4. Open a pull request and fill in the template.

The full workflow and style conventions are in
[CONTRIBUTING.md](https://github.com/loxilb-io/loxilbdocs-inference-gateway/blob/main/CONTRIBUTING.md).

### Usage-example contracts

The example validator extracts `loxicmd`, `curl`, JSON, YAML, and PromQL from Markdown fenced blocks.
It checks CLI paths, flags, and enums against frozen CLI contracts; REST methods and paths against
the combined primary and supplemental Swagger contracts; inline JSON request bodies against the
matching Swagger request schema; shell syntax with `bash -n`; JSON with `jq`; and YAML with `yq`.
PromQL metric names and selector labels are checked against the frozen
release-scope manifest; documented closed label enums are checked for exact
selectors. Referenced snapshot and bootstrap bodies use public, non-secret fixtures for schema validation.
The unit suite also applies deliberately broken examples and requires the validator to reject route
typos, removed flags, invalid enum values, incorrect JSON field casing, missing required fields,
non-existent metric families, wrong metric labels, and wrong metric enum values.

The tracked snapshots under `tests/contracts/docs_examples/` make the CI check deterministic and
network-independent. Maintainers can refresh them from exact local clones after reviewing an
upstream contract change:

```bash
python tools/refresh_example_contracts.py \
  --gateway-repo ../loxilb-inference-gateway \
  --cli-repo ../loxicmd-inference-gateway
python tools/refresh_example_inventory.py
python tools/refresh_example_inventory.py --check
```

### Validate a Gateway upgrade before refreshing the snapshot

The `Gateway contract drift` workflow checks out a selected Gateway branch,
tag, or commit and performs three independent gates:

1. regenerate the candidate contract from both Swagger files, the engine
   support catalog, the release-scope metric manifest, and selected public
   scenario/workflow evidence;
2. validate documented routes, request bodies, and PromQL against that
   candidate contract;
3. compare Swagger, catalog, metric-manifest, and scenario/claim evidence with
   the tracked contract. Any drift fails until it is reviewed.

Run the same gate locally with one command:

```bash
python tools/validate_gateway_docs.py \
  --gateway-repo ../loxilb-inference-gateway \
  --gateway-ref main
```

After reviewing the report and updating affected pages, refresh only the
Gateway snapshot from the exact accepted commit:

```bash
python tools/refresh_example_contracts.py \
  --only gateway \
  --gateway-repo ../loxilb-inference-gateway \
  --gateway-ref <accepted-gateway-commit>

python tools/validate_examples.py
python tools/refresh_example_inventory.py --check
python tools/render_metrics_reference.py --check
python -m unittest discover -s tests -p 'test_*.py' -v
```

The workflow runs on relevant documentation pull requests, weekly against
Gateway `main`, and on manual dispatch with a selectable `gateway_ref`. It also
accepts a `repository_dispatch` event named `gateway-api-updated`; a Gateway
release workflow can send that event with `client_payload.gateway_ref` set to
the immutable commit or tag. The dispatch token must stay in repository
secrets and must never be placed in the event payload or logs.

These checks establish static command, route, schema, metric, evidence-object, and syntax consistency. They do not execute
the Linux CLI binary, send requests to a running gateway, or qualify GPU, high-availability, or
production behavior.

## Visual and security style

Follow the layout and terminology of neighboring pages. Use Mermaid for request paths, decisions,
state transitions, and component relationships when it improves understanding; keep the same
semantic color palette and explain the diagram in adjacent text or a table. Validate diagrams in
both light and dark themes.

Public pages and diagrams must not contain personal information, private topology, credentials,
internal identifiers, private registry names, or unpublished performance claims. Security and HA
behavior must be traceable to the current source contract and must state operational limitations
instead of implying a guarantee.

## Correctness comes first

Every documented field, default, enum, endpoint, and runnable example must be traceable to the
code repository — `api/swagger.yml` / `api/swagger-extras.yml` for the API contract, or a working
`cicd/` scenario for examples. If a page and the code disagree, the code wins. When a capability
is partial or still on the roadmap, we say so with a status note rather than implying it works.

## Community

- 💬 Slack: [loxilb.io/members](https://www.loxilb.io/members)
- 🧩 Upstream LoxiLB: [github.com/loxilb-io/loxilb](https://github.com/loxilb-io/loxilb)
- 🔒 Security issues: see the [security policy](https://github.com/loxilb-io/loxilbdocs-inference-gateway/blob/main/SECURITY.md) — do not open a public issue.

By participating you agree to the project's
[Code of Conduct](https://github.com/loxilb-io/loxilbdocs-inference-gateway/blob/main/CODE_OF_CONDUCT.md).
