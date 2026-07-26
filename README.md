# LoxiLB Inference Gateway — Documentation

[![Docs](https://img.shields.io/badge/docs-live-blue)](https://loxilb-io.github.io/loxilbdocs-inference-gateway/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Slack](https://img.shields.io/badge/community-join%20slack-blue)](https://www.loxilb.io/members)

Source for the documentation site of the **[LoxiLB Inference Gateway](https://github.com/loxilb-io/loxilb-inference-gateway)** —
an inference-aware L4/L7 load balancer for LLM serving fleets (vLLM, SGLang), forked from
[loxilb](https://github.com/loxilb-io/loxilb). It adds model-aware routing, KV-cache-aware
routing, prefill/decode disaggregation, OpenAI-compatible SSE streaming, and an MCP gateway on
top of loxilb's GoLang/eBPF data path.

The rendered site is built with [MkDocs](https://www.mkdocs.org/) +
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) and published to GitHub Pages.

> 📖 **Read the docs:** https://loxilb-io.github.io/loxilbdocs-inference-gateway/

## What's here

```
docs/            Documentation content (Markdown)
mkdocs.yml       Site configuration and navigation
requirements.txt Pinned build dependencies
.github/         Issue/PR templates and CI workflows
```

This repository contains **documentation only**. The gateway's source code, API
specification, and CI scenarios live in the
[loxilb-inference-gateway](https://github.com/loxilb-io/loxilb-inference-gateway) repository,
which is the authoritative source for every API field, default, and example documented here.

## Build the docs locally

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdocs serve          # live preview at http://127.0.0.1:8000
mkdocs build --strict # production build; fails on warnings/broken links
```

## Contributing

Documentation improvements are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the
workflow, style conventions, and how examples are kept in sync with the code. By participating
you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).

## Community

- 💬 Slack: [loxilb.io/members](https://www.loxilb.io/members)
- 🧩 Core load balancer: [loxilb-io/loxilb](https://github.com/loxilb-io/loxilb)
- 🌐 Website: [loxilb.io](https://www.loxilb.io)

## License

Documentation is licensed under the [Apache License 2.0](LICENSE).
