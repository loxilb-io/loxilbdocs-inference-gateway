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
   mkdocs build --strict
   ```
4. Open a pull request and fill in the template.

The full workflow and style conventions are in
[CONTRIBUTING.md](https://github.com/loxilb-io/loxilbdocs-inference-gateway/blob/main/CONTRIBUTING.md).

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
