# Optional functional-QA receipt collector

`receipt-collector.py` is the small standard-library collector used for this
campaign's TRT/SGLang phases. The vLLM phase used the earlier collector variant
with the same forwarding/hash checks but without request-body files. It is optional test instrumentation, not a deployment script or a
production proxy. It buffers short responses to hash them and records raw prompts
and responses locally. Use only an isolated, allocated test service with test
inputs; keep the output private and apply your evidence-retention policy.

Run it on each worker, substituting the worker's allocated address:

```bash
python3 verification/receipt-collector.py --bind 192.0.2.20 --port 8102 \
  --upstream-port 8000 --directory "$RUN/receipts"
```

Leave this foreground process running in its own terminal. Native engines stay
on 8000. For this instrumented run only, edit each selected Gateway endpoint's
`targetPort` to 8102; leave native `probeport: 8000` and event ports unchanged.
Use a unique `X-ModeQA-Request-ID` header for every request and compare the
client's exact request/response byte hashes with `receipts.jsonl`. HTTP success
and the Gateway's own counters do not replace this independent comparison.
`upstreamComplete` proves transport read completion; separately parse chat/SSE
content, finish reason and DONE count. When published, the public ledger must
contain sanitized hashes/counts and worker aliases, never the collector's private
raw files. The thirty-case result summary and sanitized ledger are published as
`matrix-results.json` and `matrix-request-ledger.json` in the package root.
The collector alone does not establish that a new deployment has passed.

After deleting the owned rule and draining traffic, stop this exact foreground
process with Ctrl-C. Use the ordinary native 8000 configuration for the normal
manual path. The two network paths have different overhead; no performance
comparison is established by this collector.
