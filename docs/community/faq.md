# FAQ

## What is the LoxiLB Inference Gateway?

An inference-aware L4/L7 load balancer for LLM serving fleets. It is a fork of
[loxilb](https://github.com/loxilb-io/loxilb) that adds model-aware routing, KV-cache-aware
routing, prefill/decode disaggregation, OpenAI-compatible SSE streaming, and an MCP gateway on top
of loxilb's GoLang/eBPF data path.

## How is it different from upstream loxilb?

It is a fully functional loxilb with inference routing added. **Every AI capability is opt-in per
load-balancer rule**, and with none enabled the binary behaves exactly like upstream loxilb. If you
only need a cloud-native load balancer, use [upstream loxilb](https://github.com/loxilb-io/loxilb);
if you operate an LLM serving fleet, this project gives you the same load balancer with
inference-aware routing built in.

## Which serving engines are supported?

**vLLM** and **SGLang** for KV-cache-aware routing. Both integrate through their native KV-event
contracts — see [KV-Cache Routing](../ai-gateway/kv-caching.md) and the
[use-case guides](../use-cases/kv-cache-aware-routing.md).

## Do I need a GPU to run the gateway?

No — the gateway itself runs on a CPU host. GPUs are needed only for the serving engines
(vLLM/SGLang) behind it. KV-cache-aware and GPU-aware routing require GPU-backed engines, but the
load balancer's control and data planes do not.

## Which load-balancer mode do AI features need?

`mode: 4` (**fullproxy**). AI routing inspects request headers and bodies, which requires the
userspace HTTP proxy path. See [Running Modes](../concepts/running-modes.md).

## Is there a `loxicmd` CLI for AI features?

Not yet. The current management surface is the **REST API** (`http://<host>:11111/netlox/v1/...`)
and **`loxilb-mcp`** (a Model Context Protocol server with a large tool catalog). First-class
`loxicmd` AI subcommands are on the [roadmap](roadmap.md). See the [CLI reference](../reference/cli.md).

## Are API-key authentication and rate limiting enforced at the gateway?

Today they are **control-plane CRUD only** — the gateway manages keys and tenant limits, but does
not yet reject requests (401/403/429) in the data path. Data-plane enforcement is on the
[roadmap](roadmap.md). SSE stream lifecycle and token accounting **are** wired. See
[API Key Management](../ai-gateway/api-key-management.md).

## My KV-cache routing isn't improving hit rates. Why?

Almost always a broken parity leg — the block/page size, hash algorithm, hash seed, ZMQ port, or
tokenizer directory does not match between the engine and the gateway, so routing **silently** falls
back to round-robin. Run the "verify it fired" recipe: `loxilb_pd_kv_tier15_hits_total` must advance
after the first request. See [Troubleshooting](../operations/troubleshooting.md) and the
[KV-cache-aware routing guide](../use-cases/kv-cache-aware-routing.md).

## What license is it under?

[Apache License 2.0](https://github.com/loxilb-io/loxilbdocs-inference-gateway/blob/main/LICENSE).

## Where is the source code and how do I report a bug?

The gateway source, API spec, and CI scenarios live in
[loxilb-io/loxilb-inference-gateway](https://github.com/loxilb-io/loxilb-inference-gateway). Report
gateway bugs there; report documentation problems in the
[docs repository](https://github.com/loxilb-io/loxilbdocs-inference-gateway). Questions are welcome
on [Slack](https://www.loxilb.io/members).
