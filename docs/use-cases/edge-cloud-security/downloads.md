# Download and customize the lab inputs

Obtain explicit JSON and a small observation helper without an opaque policy runner.

## Prerequisites and obtaining inputs

Before starting [setup](setup.md), copy this documentation revision's complete
`docs/assets/edge-cloud-security/` directory to a directory named `lab-inputs` on your Linux host.
Preserve `examples/` and all files in the catalog below. Alternatively, download every catalog file
into that same layout. Start setup from the parent directory of `lab-inputs`; setup creates the
sibling `edge-security-lab`, copies the inputs into it and runs `sha256sum -c SHA256SUMS`.

The input directory is required for its checksum manifest and observation helper. You can write the
JSON from the inline commands instead of loading the downloaded JSON: both forms are identical.
Record the docs revision together with the pinned Gateway source and resolved image IDs. No private
host, SSH alias, preconfigured database, archive or issued credential is needed.

## Download catalog

| File | Purpose |
|---|---|
| [fairness-rule.json](../../assets/edge-cloud-security/examples/fairness-rule.json) | Isolated pool-share input |
| [manifest.json](../../assets/edge-cloud-security/manifest.json) | Source/eBPF pin and per-file API method/path |
| [SHA256SUMS](../../assets/edge-cloud-security/SHA256SUMS) | Input integrity, not runtime proof |
| [metric-delta.py](../../assets/edge-cloud-security/metric-delta.py) | Strict counter observation helper |
| [blacklist.json](../../assets/edge-cloud-security/examples/blacklist.json) | POST `/config/ipfilter` input |
| [firewall-drop.json](../../assets/edge-cloud-security/examples/firewall-drop.json) | POST `/config/firewall` input |
| [key-control-create.json](../../assets/edge-cloud-security/examples/key-control-create.json) | POST `/config/ai/apikey` input |
| [key-create.json](../../assets/edge-cloud-security/examples/key-create.json) | POST `/config/ai/apikey` input |
| [key-rate.json](../../assets/edge-cloud-security/examples/key-rate.json) | PATCH `/config/ai/apikey/{key_id}` input |
| [key-second-create.json](../../assets/edge-cloud-security/examples/key-second-create.json) | POST `/config/ai/apikey` input |
| [key-unlimited.json](../../assets/edge-cloud-security/examples/key-unlimited.json) | PATCH `/config/ai/apikey/{key_id}` input |
| [lb-allowed-sources.json](../../assets/edge-cloud-security/examples/lb-allowed-sources.json) | POST `/config/loadbalancer` input |
| [lb-coexistence.json](../../assets/edge-cloud-security/examples/lb-coexistence.json) | POST `/config/loadbalancer` input |
| [model.json](../../assets/edge-cloud-security/examples/model.json) | POST `/config/loadbalancer` input |
| [rate-aggregate.json](../../assets/edge-cloud-security/examples/rate-aggregate.json) | POST `/config/securityrate` input |
| [rate-source.json](../../assets/edge-cloud-security/examples/rate-source.json) | POST `/config/securityrate` input |
| [tenant-rate.json](../../assets/edge-cloud-security/examples/tenant-rate.json) | POST `/config/ai/tenant/ratelimit` input |
| [tenant-unlimited.json](../../assets/edge-cloud-security/examples/tenant-unlimited.json) | POST `/config/ai/tenant/ratelimit` input |

## Existing fixture source and build

Backend H1/h2c/SSE/nonce journal, client curl and private publisher dependencies are built by pinned
[CICD build.sh](https://github.com/loxilb-io/loxilb-inference-gateway/blob/0f78cc3329e23934be4924069b137bfbe557e8f2/cicd/edge-cloud-security/build.sh).
No copied internal fixture is required. The setup address adaptation changes only CICD test inputs,
not product code. Record that diff and image locks; do not run upstream automatic validation after
manual policy changes. Private runtime state is never an asset.

## Customization and expected verification

Change Docker IPAM/routes, source CIDRs, VIP/Host/URL, endpoints, event bind, selectors and DELETE
keys together. Change model/request/allowed_models and tokenizer/hash/block/seed together. Per-file
POST bodies contain writable fields only. Keep fixture controls, effective/read-only output and
product API fields separate. See [common conventions](common.md) for units, omissions and rollback.

## Cleanup and troubleshooting

A checksum mismatch or missing manifest file means stop and recopy the matching revision. Do not
regenerate checksums on unknown inputs just to get PASS. Keep generated raw keys, tokens, snapshot,
DB state, PCAP and raw logs outside the public input directory. No published release qualification
or performance guarantee follows from a successful fixture build.
