#!/usr/bin/env python3
"""Refresh frozen public contracts used by the documentation example validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


DEFAULT_GATEWAY_REF = "HEAD"
CLI_MAIN_REF = "27d6717438abf4dcdb605d7036cf5173e40c5e59"
CLI_RELEASE_REF = "5dd978c25c967b8192c5fe9cd448783e1e74be7c"
CLI_RELEASE_TAG = "v0.9.8.9-rc.2"

GATEWAY_FILES = ("api/swagger.yml", "api/swagger-extras.yml")
COMPLETION_GOLDEN = "cmd/goldens/testdata/completion-bash.golden"

# Only command leaves used by the public Markdown are retained. The completion
# golden remains the authority for command paths and flags.
CLI_FUNCTIONS = {
    "appliance backup create": "_loxicmd_appliance_backup_create",
    "appliance backup key-create": "_loxicmd_appliance_backup_key-create",
    "appliance backup verify": "_loxicmd_appliance_backup_verify",
    "appliance diagnostics create": "_loxicmd_appliance_diagnostics_create",
    "appliance factory-reset execute": "_loxicmd_appliance_factory-reset_execute",
    "appliance factory-reset plan": "_loxicmd_appliance_factory-reset_plan",
    "appliance network validate": "_loxicmd_appliance_network_validate",
    "appliance restore execute": "_loxicmd_appliance_restore_execute",
    "appliance restore plan": "_loxicmd_appliance_restore_plan",
    "appliance rollback execute": "_loxicmd_appliance_rollback_execute",
    "appliance rollback plan": "_loxicmd_appliance_rollback_plan",
    "appliance rollback status": "_loxicmd_appliance_rollback_status",
    "appliance status": "_loxicmd_appliance_status",
    "appliance update execute": "_loxicmd_appliance_update_execute",
    "appliance update plan": "_loxicmd_appliance_update_plan",
    "appliance update status": "_loxicmd_appliance_update_status",
    "create apikey": "_loxicmd_create_apikey",
    "create lb": "_loxicmd_create_lb",
    "create persist": "_loxicmd_create_persist",
    "create restore": "_loxicmd_create_restore",
    "delete lb": "_loxicmd_delete_lb",
    "get diagnostics": "_loxicmd_get_diagnostics",
    "get kvinventory": "_loxicmd_get_kvinventory",
    "get lb": "_loxicmd_get_loadbalancer",
    "get maintenance": "_loxicmd_get_maintenance",
    "get metrics": "_loxicmd_get_metrics",
    "get ready": "_loxicmd_get_ready",
    "get snapshot": "_loxicmd_get_snapshot",
    "set maintenance": "_loxicmd_set_maintenance",
    "set metrics": "_loxicmd_set_metrics",
}

# Cobra's generated completion golden records flags but not enum candidates for
# these string flags. The values below come from the same frozen source tree's
# explicit conversion and validation functions.
CLI_ENUMS = {
    "create lb": {
        "--api-key-auth": ["disabled", "required"],
        "--backend-protocol": ["http1", "http2", "both"],
        "--ep-role": ["normal", "prefill", "decode", "0", "1", "2"],
        "--kv-engine-type": ["vllm", "sglang", "trtllm", "llamacpp"],
        "--kv-exact-mode": ["0", "1", "3"],
        "--kv-hash-algo": [
            "sha256_cbor",
            "xxhash_cbor",
            "sha256_sglang",
            "blockhash_trtllm",
        ],
        "--mode": ["onearm", "fullnat", "dsr", "fullproxy", "hostonearm"],
        "--path-match-mode": ["disabled", "prefix", "exact"],
        "--security": ["none", "https", "tls", "e2ehttps", "e2etls"],
        "--select": [
            "rr",
            "hash",
            "priority",
            "persist",
            "lc",
            "n2",
            "n3",
            "chwbl",
            "gpuaware",
            "wrr-hash",
            "chwbl-wrr",
        ],
        "--sockmap-mode": ["off", "request", "response", "both"],
    },
    "delete lb": {
        "--path-match-mode": ["disabled", "prefix", "exact"],
    },
}

SCHEMA_KEYS = {
    "$ref",
    "type",
    "format",
    "required",
    "enum",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "additionalProperties",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "items",
    "properties",
}


def git_show(repo: Path, ref: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        stderr=subprocess.PIPE,
    )


def resolve_ref(repo: Path, ref: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{ref}^{{commit}}"],
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [compact_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    compact: dict[str, Any] = {}
    for key, item in value.items():
        if key not in SCHEMA_KEYS:
            continue
        if key == "properties":
            compact[key] = {name: compact_schema(schema) for name, schema in item.items()}
        elif key == "additionalProperties" and isinstance(item, dict):
            compact[key] = compact_schema(item)
        else:
            compact[key] = compact_schema(item)
    return compact


def compact_parameter(parameter: dict[str, Any]) -> dict[str, Any] | None:
    if "$ref" in parameter:
        return {"$ref": parameter["$ref"]}
    if parameter.get("in") != "body":
        return None
    return {
        "name": parameter.get("name", "body"),
        "in": "body",
        "required": parameter.get("required", False),
        "schema": compact_schema(parameter.get("schema", {})),
    }


def compact_swagger(raw: bytes, source_path: str) -> dict[str, Any]:
    spec = yaml.safe_load(raw)
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    paths: dict[str, Any] = {}
    for path, path_item in spec.get("paths", {}).items():
        operations: dict[str, Any] = {}
        for method, operation in path_item.items():
            if method.lower() not in methods:
                continue
            parameters = [
                compact
                for parameter in operation.get("parameters", [])
                if (compact := compact_parameter(parameter)) is not None
            ]
            operations[method.lower()] = {
                "parameters": parameters,
            }
        if operations:
            paths[path] = operations
    return {
        "source_path": source_path,
        "sha256": sha256(raw),
        "basePath": spec.get("basePath", ""),
        "paths": paths,
        "parameters": {
            name: compact
            for name, parameter in spec.get("parameters", {}).items()
            if (compact := compact_parameter(parameter)) is not None
        },
        "definitions": {
            name: compact_schema(schema)
            for name, schema in spec.get("definitions", {}).items()
        },
    }


def function_body(completion: str, function_name: str) -> str | None:
    match = re.search(
        rf"(?ms)^{re.escape(function_name)}\(\)\n\{{\n(?P<body>.*?)^\}}\n",
        completion,
    )
    return match.group("body") if match else None


def completion_contract(completion: str) -> dict[str, Any]:
    commands: dict[str, Any] = {}
    for command, function_name in CLI_FUNCTIONS.items():
        body = function_body(completion, function_name)
        if body is None:
            commands[command] = {"available": False, "flags": [], "aliases": []}
            continue
        flags = {
            value.rstrip("=")
            for value in re.findall(r'^\s*flags\+\=\("([^" ]+)"\)', body, re.MULTILINE)
            if value.startswith("--")
        }
        aliases = re.findall(
            r'^\s*command_aliases\+\=\("([^" ]+)"\)', body, re.MULTILINE
        )
        commands[command] = {
            "available": True,
            "flags": sorted(flags),
            "aliases": sorted(set(aliases)),
        }
    return commands


def build_cli_contract(cli_repo: Path) -> dict[str, Any]:
    main_raw = git_show(cli_repo, CLI_MAIN_REF, COMPLETION_GOLDEN)
    release_raw = git_show(cli_repo, CLI_RELEASE_REF, COMPLETION_GOLDEN)
    main_commands = completion_contract(main_raw.decode())
    release_commands = completion_contract(release_raw.decode())
    commands: dict[str, Any] = {}
    for command in CLI_FUNCTIONS:
        commands[command] = {
            "main": main_commands[command],
            "release": release_commands[command],
            "enums": CLI_ENUMS.get(command, {}),
        }
    return {
        "contract_version": 1,
        "source": {
            "repository": "https://github.com/loxilb-io/loxicmd-inference-gateway",
            "main_commit": CLI_MAIN_REF,
            "release_tag": CLI_RELEASE_TAG,
            "release_commit": CLI_RELEASE_REF,
            "golden_path": COMPLETION_GOLDEN,
            "main_golden_sha256": sha256(main_raw),
            "release_golden_sha256": sha256(release_raw),
            "enum_evidence": "frozen command conversion and validation functions",
        },
        "commands": commands,
    }


def build_gateway_contract(
    gateway_repo: Path, gateway_ref: str = DEFAULT_GATEWAY_REF
) -> dict[str, Any]:
    resolved_ref = resolve_ref(gateway_repo, gateway_ref)
    specs = []
    for source_path in GATEWAY_FILES:
        raw = git_show(gateway_repo, resolved_ref, source_path)
        specs.append(compact_swagger(raw, source_path))
    return {
        "contract_version": 1,
        "source": {
            "repository": "https://github.com/loxilb-io/loxilb-inference-gateway",
            "commit": resolved_ref,
        },
        "specs": specs,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-repo", type=Path)
    parser.add_argument("--gateway-ref", default=DEFAULT_GATEWAY_REF)
    parser.add_argument("--cli-repo", type=Path)
    parser.add_argument(
        "--only",
        choices=("all", "gateway", "cli"),
        default="all",
        help="refresh both contracts or only one repository's contract",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/contracts/docs_examples"),
    )
    args = parser.parse_args()

    if args.only in {"all", "gateway"}:
        if args.gateway_repo is None:
            parser.error("--gateway-repo is required when refreshing the gateway contract")
        write_json(
            args.output_dir / "gateway-api.json",
            build_gateway_contract(args.gateway_repo, args.gateway_ref),
        )
    if args.only in {"all", "cli"}:
        if args.cli_repo is None:
            parser.error("--cli-repo is required when refreshing the CLI contract")
        write_json(args.output_dir / "cli.json", build_cli_contract(args.cli_repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
