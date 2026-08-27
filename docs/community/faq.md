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

The Gateway accepts **vLLM**, **SGLang**, **TensorRT-LLM**, and **llama.cpp** rule types, but
their advanced capabilities differ. vLLM, SGLang, and TensorRT-LLM support KV-exact routing
and engine-specific P/D paths. llama.cpp supports fullproxy load balancing, CHWBL, and session
affinity, but not the Gateway's KV-event or P/D controls. Start with
[Choose an Inference Engine](../getting-started/choose-your-engine.md) and verify the exact
combination in the [Engine Capability Matrix](../concepts/engine-capability-matrix.md).

## Do I need a GPU to run the gateway?

No — the gateway itself runs on a CPU host. GPUs are needed only for the serving engines
(such as vLLM, SGLang, or TensorRT-LLM) behind it. A llama.cpp fleet may use CPU or GPU
acceleration according to its own deployment. The load balancer's control and data planes do
not require a GPU.

## Which load-balancer mode do AI features need?

`mode: 4` (**fullproxy**). AI routing inspects request headers and bodies, which requires the
userspace HTTP proxy path. See [Running Modes](../concepts/running-modes.md).

## Is there a `loxicmd` CLI for AI features?

Yes. `loxicmd` includes AI-aware load-balancer controls and subcommands for API keys, tenant
limits, metrics, GPU state, OPA, SNI, and KV inventory. The **REST API** remains the complete
contract, and **`loxilb-mcp`** provides role-scoped tools for MCP clients. See the
[CLI reference](../reference/cli.md) and confirm a command is present in the installed client
before scripting it.

## Are API-key authentication and rate limiting enforced at the gateway?

Yes, but only on a `mode: 4` rule that also enables `sse_mode` or
`pd_disagg_mode`, and only when the independent AI-key store is configured. A
plain `mode: 4` rule is keyless even with a healthy store. The gated path
enforces API-key validity (`401`), allowed-model policy (`403`), request-rate
limits, and tenant/model token quotas (`429`); the per-key `tokens_per_min`
field is persisted but is not currently enforced. With no `--aikey-db-host`,
the gated path also admits keyless requests, so a missing-key `401` probe is a
required deployment gate. These controls do not depend on the management user
service and remain independent from network byte-rate QoS. Follow
[AI Traffic Governance](../ai-gateway/ai-traffic-governance.md) to configure each control and
verify the corresponding denial safely.

## Does basic SGLang P/D require KV-exact routing?

No. A SGLang P/D rule requires fullproxy, P/D mode, and prefill/decode endpoint roles. Adding
`kvExactMode: 1` is optional and enables a cache-event-informed prefill selection layer. Do not
use `kvExactMode: 3` with P/D; mode 3 is for a single role-less pool. See
[SGLang P/D Disaggregation](../ai-gateway/sglang-pd-disaggregation.md).

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
