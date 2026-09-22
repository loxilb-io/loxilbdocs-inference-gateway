#!/usr/bin/env python3
"""Refresh the deterministic classification inventory for public examples."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from validate_examples import (
    CANONICAL_MUTATION_WORKFLOW,
    MUTATION_POLICY_PATH,
    ExampleValidator,
    collect_public_blocks,
)


STATUS_MARKER = re.compile(
    r"<!--\s*example-status(?:-default)?:\s*"
    r"(?P<status>verified|blocked|illustrative-only)\s*-->",
    re.IGNORECASE,
)
WORKFLOW_MARKER = re.compile(
    r"<!--\s*mutation-workflow:\s*(?P<workflow>[a-z0-9-]+)\s*-->",
    re.IGNORECASE,
)
CANONICAL_WORKFLOW_ID = "quickstart-model-route"


def explicit_status(root: Path, path: Path, line: int) -> str | None:
    lines = (root / path).read_text(encoding="utf-8").splitlines()
    prefix = "\n".join(lines[: max(0, line - 1)])
    markers = list(STATUS_MARKER.finditer(prefix))
    return markers[-1].group("status").lower() if markers else None


def explicit_workflow(root: Path, path: Path, line: int) -> str | None:
    lines = (root / path).read_text(encoding="utf-8").splitlines()
    prefix = "\n".join(lines[: max(0, line - 1)])
    markers = list(WORKFLOW_MARKER.finditer(prefix))
    return markers[-1].group("workflow").lower() if markers else None


def canonical_mutation_requirements(root: Path) -> dict[str, bool]:
    sources = "\n".join(
        (root / "snippets/getting-started" / name).read_text(encoding="utf-8")
        for name in ("04-create.md", "05-traffic.md", "06-metrics.md", "07-cleanup.md")
    )
    return {
        "independent_oracle": all(
            token in sources for token in ("BACKEND_RECEIPT_LOG", "receipt_count")
        ),
        "negative_no_mutation": all(
            token in sources
            for token in ("rules-before-invalid.json", "rules-after-invalid.json", "cmp --silent")
        ),
        "active_path": all(
            token in sources for token in ("positive_receipts_before", "positive_receipts_after")
        ),
        "cleanup": bool(re.search(r"--request\s+DELETE|loxicmd\s+delete", sources)),
        "cleanup_verification": all(
            token in sources for token in ("rules-after-cleanup.json", "ready-after-cleanup.json")
        ),
    }


def quality_contract(root: Path, block) -> dict[str, bool]:
    source = (root / block.path).read_text(encoding="utf-8")
    heading = lambda pattern: bool(  # noqa: E731 - compact deterministic map
        re.search(rf"^#{{2,6}}\s+.*(?:{pattern})", source, re.IGNORECASE | re.MULTILINE)
    )
    return {
        "prerequisites": heading(r"prerequisite|before you start"),
        "exact_command": block.language in {"bash", "sh", "shell", "json", "yaml", "yml", "promql"},
        "expected_result": heading(r"expected|interpret.*response|result"),
        "validation": heading(r"validate|verify|verification"),
        "cleanup": heading(r"cleanup|clean up|remove"),
        "diagnosis": heading(r"diagnos|troubleshoot"),
    }


def classify(
    root: Path,
    block,
    quality: dict[str, bool],
    operations: list[str],
    workflow: str | None,
) -> tuple[str, str]:
    if operations and workflow != CANONICAL_WORKFLOW_ID:
        return "illustrative-only", "non-standalone-mutation-fragment"
    marked = explicit_status(root, block.path, block.line)
    if marked:
        evidence = "explicit-public-classification"
        return marked, evidence
    text = block.text
    if block.language == "mermaid":
        return "illustrative-only", "visual-explanation"
    if block.language == "promql":
        status = "verified" if all(quality.values()) else "illustrative-only"
        return status, "metric-manifest-static"
    if re.search(r"(?<![A-Za-z0-9_.-])loxicmd(?=\s)", text):
        status = "verified" if all(quality.values()) else "illustrative-only"
        return status, "cli-contract-static"
    if re.search(r"(?<![A-Za-z0-9_.-])curl(?=\s)", text) and (
        "/netlox/v1" in text or "$CONTROL_API" in text or "${CONTROL_API}" in text
    ):
        status = "verified" if all(quality.values()) else "illustrative-only"
        return status, "swagger-union-static"
    if block.language in {"json", "yaml", "yml"}:
        return "illustrative-only", "syntax-only"
    if block.language in {"bash", "sh", "shell"}:
        return "illustrative-only", "shell-syntax-only"
    return "illustrative-only", "unexecuted-example"


def document(root: Path) -> dict:
    validator = ExampleValidator(root, require_external_tools=False)
    mutation_requirements = canonical_mutation_requirements(root)
    entries = []
    for identity, block, digest in collect_public_blocks(root):
        quality = quality_contract(root, block)
        operations = validator.mutation_operations(block)
        workflow = explicit_workflow(root, block.path, block.line)
        status, evidence = classify(root, block, quality, operations, workflow)
        if operations:
            mutation_contract = {
                "detected": True,
                "mode": (
                    "standalone-workflow"
                    if workflow == CANONICAL_WORKFLOW_ID
                    else "illustrative-fragment"
                ),
                "operations": operations,
                "workflow": CANONICAL_MUTATION_WORKFLOW,
                **mutation_requirements,
            }
        entry = {
            "id": identity,
            "path": block.path.as_posix(),
            "line": block.line,
            "language": block.language or "plain",
            "sha256": digest,
            "status": status,
            "evidence": evidence,
            "quality_contract": quality,
        }
        if operations:
            entry["mutation_contract"] = mutation_contract
        entries.append(entry)
    return {
        "schema_version": 2,
        "mutation_policy": MUTATION_POLICY_PATH,
        "status_definitions": {
            "verified": "Passes the named public static, contract, or manifest gate; runtime is not implied.",
            "blocked": "Must not be followed until the documented contract or evidence blocker is resolved.",
            "illustrative-only": "Explains shape or intent and is not represented as an executed workflow.",
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/contracts/docs_examples/example-inventory.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    rendered = json.dumps(document(root), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            print(f"example inventory is stale: {output}")
            return 1
        print(f"example inventory is current: {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
