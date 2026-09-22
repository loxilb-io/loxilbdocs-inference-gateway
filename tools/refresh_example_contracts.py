#!/usr/bin/env python3
"""Refresh frozen Gateway API, metric, engine, and scenario contracts."""

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
GATEWAY_PUBLIC_SCHEMA_BASELINE_REF = "47803fb660ed54cd1f180b616db628461ad85d1a"
GATEWAY_RELEASE_TAG = "v0.9.8.9-rc.1"
GATEWAY_RELEASE_TAG_OBJECT = "db28353e50f7031157187fdd2250d1098c97963a"
GATEWAY_RELEASE_REF = "f08b18beda587217265c9ba6419159119914795c"
CLI_MAIN_REF = "27d6717438abf4dcdb605d7036cf5173e40c5e59"
CLI_RELEASE_REF = "5dd978c25c967b8192c5fe9cd448783e1e74be7c"
CLI_RELEASE_TAG = "v0.9.8.9-rc.2"
CLI_RELEASE_TAG_OBJECT = "2dd7dbe215982859c2ee5cfc836fe34ac4e54a37"

GATEWAY_FILES = ("api/swagger.yml", "api/swagger-extras.yml")
SUPPORT_CATALOG_FILE = "engine-contracts/support-catalog.yaml"
METRIC_MANIFEST_FILE = "deploy/monitoring/manifest/metric-manifest.json"
EBPF_SUBMODULE_PATH = "loxilb-ebpf"
ENGINE_SCENARIO_PATHS = (
    "cicd/kv-mixed-version",
    "cicd/kv-profile-admission",
    "cicd/kv-sglang-attest",
    "cicd/sockmap-fullproxy",
    "cicd/vllm-kvcache-routing-cpu",
    "cicd/vllm-pd-admission-cpu",
)
ENGINE_CONTRACT_WORKFLOW = ".github/workflows/engine-contracts-ci.yml"
COMPLETION_GOLDEN = "cmd/goldens/testdata/completion-bash.golden"

METRIC_LABEL_ENUMS = {
    "loxilb_ai_requests_total": {
        "outcome": ["completed", "denied"],
    },
    "loxilb_ai_tokens_consumed_total": {
        "kind": ["prompt", "completion"],
    },
    "loxilb_ai_jwks_refresh_total": {
        "outcome": ["success", "failure"],
    },
    "loxilb_ai_pd_requests_total": {
        "phase": ["complete", "prefill", "decode", "unknown"],
        "status": ["success", "timeout", "error", "rejected"],
    },
    "loxilb_ai_pd_tier_selected_total": {
        "tier": ["tier0", "tier1", "tier15", "tier2"],
    },
    "loxilb_ai_worker_scrape_total": {
        "result": [
            "ok", "unreachable", "http_error", "body_error",
            "unparseable", "bad_request", "unknown",
        ],
    },
}

# Public claim evidence is intentionally compact. Object IDs prove which public
# source was reviewed; the raw upstream evidence prose is not copied because it
# can contain local host names, internal work-package labels, and one-off run
# details that do not belong in this repository.
CLAIM_EVIDENCE = (
    {
        "claim": "jwt-policy-and-token-accounting",
        "scenario_path": "cicd/ai-jwtauth",
        "validation_path": "cicd/ai-jwtauth/validation.sh",
        "workflow_path": ".github/workflows/ai-gateway-sanity.yml",
        "case_ids": ["G2", "M4", "U1", "U2", "UH1", "UH2", "UE", "UE3"],
    },
    {
        "claim": "qos-ha-and-scope-metrics",
        "scenario_path": "cicd/ai-qos-ha-sync",
        "validation_path": "cicd/ai-qos-ha-sync/validation.sh",
        "workflow_path": None,
        "case_ids": [
            "SYNC-1", "SYNC-2", "QOS-METRIC-1", "QOS-METRIC-2",
            "QOS-HA-013", "QOS-HA-014",
        ],
    },
    {
        "claim": "pd-and-worker-scrape-metrics",
        "scenario_path": "cicd/vllm-pd-disagg",
        "validation_path": "cicd/vllm-pd-disagg/validation.sh",
        "workflow_path": ".github/workflows/ai-gateway-sanity.yml",
        "case_ids": [
            "TH1", "TH2", "TH3", "TH4", "TH5a", "TM1b", "TM2d",
            "TN1", "TN2b", "TN3b", "TN4b", "TN5a", "TN6b",
        ],
    },
    {
        "claim": "sockmap-observability",
        "scenario_path": "cicd/sockmap-fullproxy",
        "validation_path": "cicd/sockmap-fullproxy/validation_observability.sh",
        "workflow_path": None,
        "case_ids": ["O-1", "O-2", "O-3", "O-5", "O-6"],
    },
    {
        "claim": "monitoring-stack",
        "scenario_path": "cicd/monitoring",
        "validation_path": "cicd/monitoring/validation.sh",
        "workflow_path": ".github/workflows/monitoring-e2e.yml",
        "case_ids": [],
    },
)

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


def resolve_object(repo: Path, ref: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{ref}:{path}"],
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def object_exists(repo: Path, ref: str, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def workflow_sources(repo: Path, ref: str) -> dict[str, str]:
    paths = subprocess.check_output(
        [
            "git", "-C", str(repo), "ls-tree", "-r", "--name-only",
            ref, ".github/workflows",
        ],
        text=True,
        stderr=subprocess.PIPE,
    ).splitlines()
    return {
        path: git_show(repo, ref, path).decode(errors="replace")
        for path in paths
        if path.endswith((".yml", ".yaml"))
    }


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


def compact_support_catalog(raw: bytes) -> dict[str, Any]:
    catalog = yaml.safe_load(raw)
    return {
        "source_path": SUPPORT_CATALOG_FILE,
        "sha256": sha256(raw),
        "schemaVersion": catalog.get("schemaVersion", ""),
        "entries": catalog.get("entries", []),
    }


def compact_metric_manifest(raw: bytes) -> dict[str, Any]:
    manifest = json.loads(raw)
    families = []
    for family in manifest.get("families", []):
        if family.get("release_scope") != "release":
            continue
        writers = family.get("writer_sources", [])
        evidence = family.get("verification_evidence", "")
        families.append(
            {
                "name": family.get("name", ""),
                "type": family.get("type", ""),
                "labels": family.get("labels", []),
                "activation": family.get("activation", ""),
                "release_scope": family.get("release_scope", ""),
                "runtime_scope": family.get("runtime_scope", ""),
                "implementation_status": family.get("implementation_status", ""),
                "writer_present": bool(writers),
                "evidence_present": bool(evidence),
            }
        )
    return {
        "source_path": METRIC_MANIFEST_FILE,
        "sha256": sha256(raw),
        "schema_version": manifest.get("schema_version"),
        "provenance": manifest.get("provenance", {}),
        "coverage": manifest.get("coverage", {}),
        "label_enums": METRIC_LABEL_ENUMS,
        "families": families,
    }


def build_claim_evidence(repo: Path, ref: str) -> dict[str, Any]:
    claims = []
    workflows = workflow_sources(repo, ref)
    for entry in CLAIM_EVIDENCE:
        validation_path = str(entry["validation_path"])
        validation = git_show(repo, ref, validation_path).decode(errors="replace")
        missing = [
            case
            for case in entry["case_ids"]
            if re.search(
                rf"(?<![A-Za-z0-9]){re.escape(str(case))}(?![A-Za-z0-9])",
                validation,
            ) is None
        ]
        if missing:
            raise ValueError(
                f"{validation_path} is missing declared case IDs: {', '.join(missing)}"
            )

        workflow_path = entry["workflow_path"]
        matching_workflows = sorted(
            path
            for path, source in workflows.items()
            if str(entry["scenario_path"]) in source
        )
        membership = "wired" if matching_workflows else "not-wired"
        workflow_object_id = None
        if workflow_path:
            if workflow_path not in matching_workflows:
                raise ValueError(
                    f"{workflow_path} does not invoke {entry['scenario_path']}"
                )
            workflow_object_id = resolve_object(repo, ref, str(workflow_path))
        elif matching_workflows:
            raise ValueError(
                f"{entry['scenario_path']} is unexpectedly wired by: "
                + ", ".join(matching_workflows)
            )

        claims.append(
            {
                "claim": entry["claim"],
                "scenario_path": entry["scenario_path"],
                "scenario_object_id": resolve_object(
                    repo, ref, str(entry["scenario_path"])
                ),
                "validation_path": validation_path,
                "validation_object_id": resolve_object(repo, ref, validation_path),
                "workflow_path": workflow_path,
                "workflow_object_id": workflow_object_id,
                "workflow_membership": membership,
                "matching_workflows": matching_workflows,
                "matching_workflow_objects": {
                    path: resolve_object(repo, ref, path)
                    for path in matching_workflows
                },
                "case_ids": entry["case_ids"],
            }
        )
    return {"claims": claims}


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
            "release_tag_object": CLI_RELEASE_TAG_OBJECT,
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
    schema_baseline_ref = resolve_ref(
        gateway_repo, GATEWAY_PUBLIC_SCHEMA_BASELINE_REF
    )
    schema_baseline_specs = {
        source_path: compact_swagger(
            git_show(gateway_repo, schema_baseline_ref, source_path), source_path
        )
        for source_path in GATEWAY_FILES
    }
    schema_delta = []
    for spec in specs:
        source_path = spec["source_path"]
        baseline_definitions = schema_baseline_specs[source_path]["definitions"]
        candidate_definitions = spec["definitions"]
        schema_delta.append(
            {
                "source_path": source_path,
                "baseline_definition_count": len(baseline_definitions),
                "candidate_definition_count": len(candidate_definitions),
                "added_definitions": sorted(
                    candidate_definitions.keys() - baseline_definitions.keys()
                ),
                "removed_definitions": sorted(
                    baseline_definitions.keys() - candidate_definitions.keys()
                ),
            }
        )
    catalog_raw = git_show(gateway_repo, resolved_ref, SUPPORT_CATALOG_FILE)
    metric_manifest_raw = git_show(gateway_repo, resolved_ref, METRIC_MANIFEST_FILE)
    release_commit = resolve_ref(gateway_repo, GATEWAY_RELEASE_REF)
    return {
        "contract_version": 1,
        "source": {
            "repository": "https://github.com/loxilb-io/loxilb-inference-gateway",
            "commit": resolved_ref,
            "ebpf_submodule_commit": resolve_object(
                gateway_repo, resolved_ref, EBPF_SUBMODULE_PATH
            ),
            "release_tag": GATEWAY_RELEASE_TAG,
            "release_tag_object": GATEWAY_RELEASE_TAG_OBJECT,
            "release_commit": release_commit,
        },
        "schema_relevance": {
            "baseline_commit": schema_baseline_ref,
            "specs": schema_delta,
        },
        "release_snapshot": {
            "tag": GATEWAY_RELEASE_TAG,
            "tag_object": GATEWAY_RELEASE_TAG_OBJECT,
            "commit": release_commit,
            "ebpf_submodule_commit": resolve_object(
                gateway_repo, release_commit, EBPF_SUBMODULE_PATH
            ),
            "spec_sha256": {
                source_path: sha256(git_show(gateway_repo, release_commit, source_path))
                for source_path in GATEWAY_FILES
            },
            "metric_manifest_available": object_exists(
                gateway_repo, release_commit, METRIC_MANIFEST_FILE
            ),
        },
        "specs": specs,
        "support_catalog": compact_support_catalog(catalog_raw),
        "metric_manifest": compact_metric_manifest(metric_manifest_raw),
        "claim_evidence": build_claim_evidence(gateway_repo, resolved_ref),
        "scenario_evidence": {
            "workflow": {
                "path": ENGINE_CONTRACT_WORKFLOW,
                "object_id": resolve_object(
                    gateway_repo, resolved_ref, ENGINE_CONTRACT_WORKFLOW
                ),
            },
            "trees": [
                {
                    "path": path,
                    "object_id": resolve_object(gateway_repo, resolved_ref, path),
                }
                for path in ENGINE_SCENARIO_PATHS
            ],
        },
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
