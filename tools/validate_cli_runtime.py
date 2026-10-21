#!/usr/bin/env python3
"""Validate a Linux CLI binary against an isolated loopback API; never use a live server."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading

if platform.system() != "Linux":
    raise SystemExit("Linux is required for the CLI execution gate")
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
binary = args.binary.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
captures = []
results = []
ready_status = 200


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def handle_request(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        captures.append({"method": self.command, "path": self.path,
                         "body": json.loads(data) if data else None})
        if self.path.endswith("/status/ready"):
            status = ready_status
            body = {"ready": status == 200,
                    "reasons": [] if status == 200 else ["qa_fixture_not_ready"]}
        else:
            status, body = 200, {"result": "Success"}
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = str(server.server_port)


def probe(name, args, expected_exit, expected_requests=0):
    before = len(captures)
    p = subprocess.run([str(binary), *args], capture_output=True, text=True,
                       timeout=20, env={**os.environ, "LOXICMD_TOKEN_FILE": ""})
    row = {"case": name, "argv": args, "exit_code": p.returncode,
           "expected_exit": expected_exit, "stdout": p.stdout,
           "stderr": p.stderr, "requests": captures[before:],
           "lane": "mock-wire" if expected_requests else "cli-parse"}
    row["verdict"] = "PASS" if p.returncode == expected_exit and len(row["requests"]) == expected_requests else "FAIL"
    results.append(row)
    return row


try:
    for family, leaves in {"restore": ("plan", "execute"), "update": ("plan", "execute", "status"),
                           "rollback": ("plan", "execute", "status"), "factory-reset": ("plan", "execute")}.items():
        for leaf in leaves:
            probe("removed-appliance-" + family + "-" + leaf,
                  ["appliance", family, leaf], 2)
    probe("invalid-short-flag", ["get", "ready", "-Z"], 2)
    probe("missing-mode-value", ["create", "lb", "192.0.2.10", "--mode"], 2)
    probe("global-before-command",
          ["--apiserver", "127.0.0.1", "--port", port,
           "get", "ready", "--output", "json"], 0, 1)
    probe("short-alias-before-command",
          ["-s", "127.0.0.1", "-p", port, "get", "ready", "-o", "json"], 0, 1)
    probe("persistent-between-command-levels",
          ["get", "--apiserver", "127.0.0.1", "--port", port, "ready", "--output", "json"], 0, 1)
    probe("repeated-persistent-last-wins",
          ["--apiserver", "unresolvable.invalid", "--apiserver", "127.0.0.1",
           "--port", port, "get", "ready"], 0, 1)
    probe("invalid-integer-port", ["get", "ready", "--port=not-an-integer"], 2)
    probe("invalid-bool", ["get", "ready", "--insecure=not-a-bool"], 2)
    probe("relative-token-file", ["get", "ready", "--token-file=./gateway.token"], 2)
    ready_status = 503
    r = probe("typed-readiness-503",
              ["get", "ready", "--apiserver", "127.0.0.1", "--port", port,
               "--output", "json"], 7, 1)
    try:
        typed = json.loads(r["stdout"])
        r["typed_body_preserved"] = typed.get("ready") is False
    except ValueError:
        r["typed_body_preserved"] = False
    if not r["typed_body_preserved"]:
        r["verdict"] = "FAIL"
    ready_status = 200
    common = ["create", "lb", "192.0.2.10", "--tcp=2020:8080",
              "--endpoints=198.51.100.11:1", "--mode=fullproxy",
              "--host=192.0.2.10", "--path-prefix=/", "--path-match-mode=prefix",
              "--model-name=llama-70b", "--apiserver", "127.0.0.1", "--port", port]
    incompatible = [value if value != "--mode=fullproxy" else "--mode=onearm" for value in common]
    probe("ai-mode-cross-field", incompatible, 2)
    r = probe("jwt-binding-wire", common + ["--api-key-auth=jwt", "--jwt-auth-profile=qa-docs-profile"], 0, 1)
    if r["requests"]:
        args = r["requests"][0]["body"].get("serviceArguments", {})
        r["mapping_matches"] = args.get("api_key_auth") == "jwt" and args.get("jwt_auth_profile") == "qa-docs-profile"
        if not r["mapping_matches"]:
            r["verdict"] = "FAIL"
    # Current code owns the exact invalid-argument exit contract; record it,
    # while requiring rejection without any management request.
    r = probe("jwt-profile-missing", common + ["--api-key-auth=jwt"], 2)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    summary = {"platform": platform.platform(),
               "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "count": len(results), "passed": sum(r["verdict"] == "PASS" for r in results),
               "failed": sum(r["verdict"] == "FAIL" for r in results),
               "scope": "Real Linux CLI against loopback fake management server; no Gateway runtime claim"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
finally:
    server.shutdown()
    server.server_close()

raise SystemExit(1 if summary["failed"] else 0)
