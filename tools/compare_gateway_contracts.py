#!/usr/bin/env python3
"""Report drift between two compact Gateway documentation contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXPECTED_SOURCES = {"api/swagger.yml", "api/swagger-extras.yml"}


@dataclass
class SpecDrift:
    source_path: str
    baseline_sha256: str = ""
    candidate_sha256: str = ""
    added_operations: list[str] = field(default_factory=list)
    removed_operations: list[str] = field(default_factory=list)
    changed_operations: list[str] = field(default_factory=list)
    added_definitions: list[str] = field(default_factory=list)
    removed_definitions: list[str] = field(default_factory=list)
    changed_definitions: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.baseline_sha256 != self.candidate_sha256 or any(
            (
                self.added_operations,
                self.removed_operations,
                self.changed_operations,
                self.added_definitions,
                self.removed_definitions,
                self.changed_definitions,
            )
        )


@dataclass
class ContractComparison:
    baseline_commit: str
    candidate_commit: str
    errors: list[str] = field(default_factory=list)
    specs: list[SpecDrift] = field(default_factory=list)
    baseline_catalog_sha256: str = ""
    candidate_catalog_sha256: str = ""
    catalog_changed: bool = False
    baseline_metric_sha256: str = ""
    candidate_metric_sha256: str = ""
    metric_manifest_changed: bool = False
    claim_evidence_changed: bool = False
    release_snapshot_changed: bool = False
    source_ebpf_changed: bool = False
    scenario_evidence_changed: bool = False
    schema_relevance_changed: bool = False

    @property
    def changed(self) -> bool:
        return (
            bool(self.errors)
            or self.catalog_changed
            or self.metric_manifest_changed
            or self.claim_evidence_changed
            or self.release_snapshot_changed
            or self.source_ebpf_changed
            or self.scenario_evidence_changed
            or self.schema_relevance_changed
            or any(spec.changed for spec in self.specs)
        )


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def specs_by_source(contract: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    result: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for spec in contract.get("specs", []):
        source_path = spec.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            errors.append("contract contains a spec without source_path")
            continue
        if source_path in result:
            errors.append(f"contract contains duplicate spec source: {source_path}")
            continue
        result[source_path] = spec
    missing = sorted(EXPECTED_SOURCES - set(result))
    unexpected = sorted(set(result) - EXPECTED_SOURCES)
    if missing:
        errors.append(f"contract is missing required Swagger sources: {', '.join(missing)}")
    if unexpected:
        errors.append(f"contract contains unexpected Swagger sources: {', '.join(unexpected)}")
    return result, errors


def operations(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{method.upper()} {path}": operation
        for path, path_item in spec.get("paths", {}).items()
        for method, operation in path_item.items()
    }


def changed_keys(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(key for key in left.keys() & right.keys() if left[key] != right[key])


def compare_contracts(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> ContractComparison:
    baseline_specs, baseline_errors = specs_by_source(baseline)
    candidate_specs, candidate_errors = specs_by_source(candidate)
    comparison = ContractComparison(
        baseline_commit=str(baseline.get("source", {}).get("commit", "unknown")),
        candidate_commit=str(candidate.get("source", {}).get("commit", "unknown")),
        errors=[
            *(f"baseline: {error}" for error in baseline_errors),
            *(f"candidate: {error}" for error in candidate_errors),
        ],
        baseline_catalog_sha256=str(
            baseline.get("support_catalog", {}).get("sha256", "")
        ),
        candidate_catalog_sha256=str(
            candidate.get("support_catalog", {}).get("sha256", "")
        ),
        catalog_changed=(
            baseline.get("support_catalog") != candidate.get("support_catalog")
        ),
        baseline_metric_sha256=str(
            baseline.get("metric_manifest", {}).get("sha256", "")
        ),
        candidate_metric_sha256=str(
            candidate.get("metric_manifest", {}).get("sha256", "")
        ),
        metric_manifest_changed=(
            baseline.get("metric_manifest") != candidate.get("metric_manifest")
        ),
        claim_evidence_changed=(
            baseline.get("claim_evidence") != candidate.get("claim_evidence")
        ),
        release_snapshot_changed=(
            baseline.get("release_snapshot") != candidate.get("release_snapshot")
        ),
        source_ebpf_changed=(
            baseline.get("source", {}).get("ebpf_submodule_commit")
            != candidate.get("source", {}).get("ebpf_submodule_commit")
        ),
        scenario_evidence_changed=(
            baseline.get("scenario_evidence") != candidate.get("scenario_evidence")
        ),
        schema_relevance_changed=(
            baseline.get("schema_relevance") != candidate.get("schema_relevance")
        ),
    )
    for source_path in sorted(EXPECTED_SOURCES & baseline_specs.keys() & candidate_specs.keys()):
        left = baseline_specs[source_path]
        right = candidate_specs[source_path]
        left_operations = operations(left)
        right_operations = operations(right)
        left_definitions = left.get("definitions", {})
        right_definitions = right.get("definitions", {})
        comparison.specs.append(
            SpecDrift(
                source_path=source_path,
                baseline_sha256=str(left.get("sha256", "")),
                candidate_sha256=str(right.get("sha256", "")),
                added_operations=sorted(right_operations.keys() - left_operations.keys()),
                removed_operations=sorted(left_operations.keys() - right_operations.keys()),
                changed_operations=changed_keys(left_operations, right_operations),
                added_definitions=sorted(right_definitions.keys() - left_definitions.keys()),
                removed_definitions=sorted(left_definitions.keys() - right_definitions.keys()),
                changed_definitions=changed_keys(left_definitions, right_definitions),
            )
        )
    return comparison


def abbreviated(values: list[str], limit: int = 20) -> str:
    if not values:
        return "none"
    displayed = values[:limit]
    suffix = f"; plus {len(values) - limit} more" if len(values) > limit else ""
    return ", ".join(f"`{value}`" for value in displayed) + suffix


def markdown_report(comparison: ContractComparison) -> str:
    lines = [
        "## Gateway documentation contract drift",
        "",
        f"- Tracked contract commit: `{comparison.baseline_commit}`",
        f"- Candidate Gateway commit: `{comparison.candidate_commit}`",
    ]
    if comparison.errors:
        lines.extend(["", "### Contract errors", ""])
        lines.extend(f"- {error}" for error in comparison.errors)
    lines.extend(
        [
            "",
            "### `engine-contracts/support-catalog.yaml`: "
            + ("CHANGED" if comparison.catalog_changed else "unchanged"),
            "",
            f"- Raw SHA-256: `{comparison.baseline_catalog_sha256}` -> "
            f"`{comparison.candidate_catalog_sha256}`",
            "- Frozen scenario evidence: "
            + ("CHANGED" if comparison.scenario_evidence_changed else "unchanged"),
            "- Public schema-relevance delta: "
            + ("CHANGED" if comparison.schema_relevance_changed else "unchanged"),
            "",
            "### `deploy/monitoring/manifest/metric-manifest.json`: "
            + ("CHANGED" if comparison.metric_manifest_changed else "unchanged"),
            "",
            f"- Raw SHA-256: `{comparison.baseline_metric_sha256}` -> "
            f"`{comparison.candidate_metric_sha256}`",
            "- Frozen public claim evidence: "
            + ("CHANGED" if comparison.claim_evidence_changed else "unchanged"),
            "- Frozen comparison release: "
            + ("CHANGED" if comparison.release_snapshot_changed else "unchanged"),
            "- Gateway eBPF submodule pin: "
            + ("CHANGED" if comparison.source_ebpf_changed else "unchanged"),
        ]
    )
    for spec in comparison.specs:
        state = "CHANGED" if spec.changed else "unchanged"
        lines.extend(
            [
                "",
                f"### `{spec.source_path}`: {state}",
                "",
                f"- Raw SHA-256: `{spec.baseline_sha256}` -> `{spec.candidate_sha256}`",
            ]
        )
        if spec.changed:
            lines.extend(
                [
                    f"- Added operations: {abbreviated(spec.added_operations)}",
                    f"- Removed operations: {abbreviated(spec.removed_operations)}",
                    f"- Changed operation schemas: {abbreviated(spec.changed_operations)}",
                    f"- Added definitions: {abbreviated(spec.added_definitions)}",
                    f"- Removed definitions: {abbreviated(spec.removed_definitions)}",
                    f"- Changed definitions: {abbreviated(spec.changed_definitions)}",
                ]
            )
            if not any(
                (
                    spec.added_operations,
                    spec.removed_operations,
                    spec.changed_operations,
                    spec.added_definitions,
                    spec.removed_definitions,
                    spec.changed_definitions,
                )
            ):
                lines.append(
                    "- Compact request schemas are unchanged; descriptions or other raw Swagger content changed."
                )
    lines.extend(
        [
            "",
            "**RESULT: " + ("DRIFT" if comparison.changed else "NO DRIFT") + "**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--markdown-summary",
        type=Path,
        help="append the report to a GitHub step-summary compatible file",
    )
    args = parser.parse_args()
    comparison = compare_contracts(
        load_contract(args.baseline), load_contract(args.candidate)
    )
    report = markdown_report(comparison)
    print(report)
    if args.markdown_summary:
        with args.markdown_summary.open("a") as summary:
            summary.write(report)
    return 1 if comparison.changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
