#!/usr/bin/env python3
"""Render or check the public Swagger definition relevance ledger."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# These notes are the human review layer over the machine-derived definition
# delta. render() fails closed when the Gateway adds or removes a definition so
# every new model receives an explicit public relevance decision.
MODEL_NOTES = {
    "AiModelProfileEntry": (
        "direct-operation",
        "One published model profile returned by detail lookup and nested in the registry list.",
        "../ai-gateway/model-profiles-kv-readiness.md",
    ),
    "AiModelProfileRegistry": (
        "direct-operation",
        "Read-only registry generation, set digest, and published profile list.",
        "../ai-gateway/model-profiles-kv-readiness.md",
    ),
    "AutoPersistStatus": (
        "nested-component",
        "Auto-persist failure streak nested in readiness and diagnostics responses.",
        "../operations/backup-restore.md",
    ),
    "BootStatus": (
        "nested-component",
        "Boot replay, quarantine, legacy fallback, and degraded-state evidence.",
        "../operations/backup-restore.md",
    ),
    "CapabilityStatus": (
        "nested-component",
        "One optional capability verdict with a stable reason code and operator-facing reason.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "CapabilityStatusList": (
        "direct-operation",
        "Envelope returned by the optional capability readiness endpoint.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "ConfigOpRecord": (
        "nested-component",
        "Generation, checksum, mode, and time identity for the last successful persist or restore.",
        "../operations/backup-restore.md",
    ),
    "DependencyDiagnostic": (
        "nested-component",
        "Sanitized dependency type, requirement, status, and latency class in diagnostics.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "DiagnosticsStatus": (
        "direct-operation",
        "Bounded diagnostic response covering build, readiness, maintenance, datapath, and dependencies.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "EbpfAttachmentStatus": (
        "nested-component",
        "One observable eBPF hook attachment fact nested in readiness or diagnostics.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "ExternalDependencyStatus": (
        "nested-component",
        "Credential-free identity and disposition of one external recovery dependency.",
        "../operations/backup-restore.md",
    ),
    "FilesystemStatus": (
        "direct-operation",
        "Formal schema for the existing filesystem-status response.",
        "api.md",
    ),
    "JWTAuthProfileEntry": (
        "direct-operation",
        "Named data-plane JWT issuer, JWKS, claim mapping, algorithm, and forwarding policy.",
        "../security/data-plane-jwt-auth.md",
    ),
    "KvExactEnforcement": (
        "nested-component",
        "Desired versus acknowledged KV-exact enforcement and migration-fence state.",
        "../ai-gateway/model-profiles-kv-readiness.md",
    ),
    "KvExactStatusEntry": (
        "direct-operation",
        "Resolved rule, profile, engine-contract, binding, and enforcement readiness status.",
        "../ai-gateway/model-profiles-kv-readiness.md",
    ),
    "MaintenanceRequest": (
        "direct-operation",
        "Requested maintenance state and optional drain timeout.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "MaintenanceStatus": (
        "direct-operation",
        "Observed maintenance, refusal, in-flight stream, deadline, and cancellation state.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "MapUtilization": (
        "nested-component",
        "Bounded datapath-map count and capacity without exposing entry contents.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "OperationResult": (
        "shared-envelope",
        "Common informational result body returned by successful configuration mutations.",
        "api.md",
    ),
    "ProcessStatus": (
        "direct-operation",
        "Formal schema for the existing per-process CPU status response.",
        "api.md",
    ),
    "RateLimitDefaultsEntry": (
        "direct-operation",
        "Stored global or rule-scoped QoS defaults with update metadata.",
        "../operations/ai-qos.md",
    ),
    "RateLimitDefaultsMod": (
        "direct-operation",
        "Replacement request for global or rule-scoped user, tenant, and shared-VIP defaults.",
        "../operations/ai-qos.md",
    ),
    "ReadyStatus": (
        "direct-operation",
        "Configuration-readiness verdict plus boot, dependency, persistence, and eBPF evidence.",
        "../operations/readiness-diagnostics-maintenance.md",
    ),
    "SockMapResetResult": (
        "direct-operation",
        "Count of accelerated live connections closed by a service-scoped reset.",
        "../operations/sockmap-acceleration.md",
    ),
    "UserModelRateLimit": (
        "nested-component",
        "One model-specific token quota nested in a user's QoS row.",
        "../operations/ai-qos.md",
    ),
    "UserRateLimitEntry": (
        "direct-operation",
        "Stored per-user RPS, burst, aggregate TPM, and per-model quota row.",
        "../operations/ai-qos.md",
    ),
    "UserRateLimitMod": (
        "direct-operation",
        "Replacement request for a user's explicit and per-model quota rows.",
        "../operations/ai-qos.md",
    ),
    "UserSummary": (
        "direct-operation",
        "Read-only account identity that excludes password material.",
        "../security/management-api-authentication.md",
    ),
    "ManagementError": (
        "companion-error",
        "Structured management authentication, authorization, and credential-store error for raw handlers.",
        "swagger-extras.md",
    ),
    "RawError": (
        "companion-error",
        "Union-compatible description of the two JSON error envelope shapes used by raw handlers.",
        "swagger-extras.md",
    ),
}


RELEVANCE = {
    "direct-operation": "Direct request, response, or operation envelope",
    "nested-component": "Public component nested in another operation model",
    "shared-envelope": "Shared public wire envelope used by multiple operations",
    "companion-error": "Public error contract in the companion raw-handler specification",
}


def escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def schema_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    value_type = str(schema.get("type", "object"))
    if value_type == "array":
        value_type = f"array<{schema_type(schema.get('items', {}))}>"
    if schema.get("format"):
        value_type += f"({schema['format']})"
    if schema.get("enum"):
        value_type += "{" + "/".join(str(value) for value in schema["enum"]) + "}"
    return value_type


def field_list(names: list[str], properties: dict[str, Any]) -> str:
    return ", ".join(
        f"`{name}:{schema_type(properties[name])}`" for name in names
    ) or "none"


def render(contract: dict[str, Any]) -> str:
    source = contract["source"]
    relevance = contract["schema_relevance"]
    specs = {spec["source_path"]: spec for spec in contract["specs"]}
    deltas = relevance["specs"]
    added = {
        name
        for delta in deltas
        for name in delta.get("added_definitions", [])
    }
    notes = set(MODEL_NOTES)
    if added != notes:
        missing = sorted(added - notes)
        stale = sorted(notes - added)
        details = []
        if missing:
            details.append("unclassified definitions: " + ", ".join(missing))
        if stale:
            details.append("notes without a current delta definition: " + ", ".join(stale))
        raise ValueError("schema relevance ledger is incomplete: " + "; ".join(details))

    counts = Counter(MODEL_NOTES[name][0] for name in added)
    lines = [
        "# Current-main API schema models",
        "",
        "This page classifies every Swagger definition added since the public API",
        "documentation baseline. It is generated from the union of `api/swagger.yml`",
        "and `api/swagger-extras.yml`; a new or removed definition fails the docs gate",
        "until its public relevance is reviewed here.",
        "",
        f"- Public schema baseline: `{relevance['baseline_commit']}`",
        f"- Reviewed Gateway `main`: `{source['commit']}`",
        f"- Added definitions: **{len(added)}**",
        "- Removed definitions: **{}**".format(
            sum(len(delta.get("removed_definitions", [])) for delta in deltas)
        ),
        "- Evidence class: **source/static contract only**",
        "",
        "These models describe the current development-source wire contract. Their",
        "presence does not establish Linux runtime, GPU, HA, release packaging, or",
        "production qualification. Confirm the Swagger served by the exact image you",
        "deploy.",
        "",
        "## Relevance classes",
        "",
        "| Class | Count | Meaning |",
        "| --- | ---: | --- |",
    ]
    for key, meaning in RELEVANCE.items():
        lines.append(f"| `{key}` | {counts[key]} | {meaning} |")
    lines.extend(
        [
            "",
            "Field notation is `name:type`; `array<Model>` identifies an array of",
            "referenced objects, and braces identify a closed enum from Swagger.",
        ]
    )

    for delta in deltas:
        source_path = delta["source_path"]
        source_url = (
            "https://github.com/loxilb-io/loxilb-inference-gateway/blob/"
            f"{source['commit']}/{source_path}"
        )
        lines.extend(
            [
                "",
                f"## `{source_path}`",
                "",
                f"[Open the exact source]({source_url}). Definition count changed from "
                f"**{delta['baseline_definition_count']}** to "
                f"**{delta['candidate_definition_count']}**; "
                f"**{len(delta['added_definitions'])}** definitions were added and "
                f"**{len(delta.get('removed_definitions', []))}** removed.",
                "",
                "| Model | Relevance | Public wire role | Required fields | Other fields | Guide |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        definitions = specs[source_path]["definitions"]
        for name in delta["added_definitions"]:
            schema = definitions[name]
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            optional = [field for field in properties if field not in required]
            relevance_class, purpose, guide = MODEL_NOTES[name]
            required_text = field_list(required, properties)
            optional_text = field_list(optional, properties)
            lines.append(
                f"| `{escape_cell(name)}` | `{relevance_class}` | "
                f"{escape_cell(purpose)} | {required_text} | {optional_text} | "
                f"[Details]({guide}) |"
            )

    lines.extend(
        [
            "",
            "## Review boundary",
            "",
            "All added definitions are public-relevant: each is a direct operation",
            "model, a nested component needed to interpret one, a shared success",
            "envelope, or a companion-spec error contract. None is classified as an",
            "internal-only model. This classification is about API documentation",
            "coverage, not proof that every endpoint is available in the latest release.",
            "",
            "Machine-readable field constraints remain authoritative in the exact",
            "Swagger source. The linked guides explain sequencing, security boundaries,",
            "negative behavior, and release limitations that a schema alone cannot express.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("tests/contracts/docs_examples/gateway-api.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/reference/api-schema-models.md")
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    expected = render(json.loads(args.contract.read_text()))
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected)
        return 0
    if not args.output.exists() or args.output.read_text() != expected:
        print(
            f"{args.output} is stale; run {Path(__file__).name} --write",
            file=sys.stderr,
        )
        return 1
    print(f"{args.output}: up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
