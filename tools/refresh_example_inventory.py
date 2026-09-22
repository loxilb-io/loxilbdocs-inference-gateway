#!/usr/bin/env python3
"""Refresh the deterministic classification inventory for public examples."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from validate_examples import collect_public_blocks


STATUS_MARKER = re.compile(
    r"<!--\s*example-status(?:-default)?:\s*"
    r"(?P<status>verified|blocked|illustrative-only)\s*-->",
    re.IGNORECASE,
)


def explicit_status(root: Path, path: Path, line: int) -> str | None:
    lines = (root / path).read_text(encoding="utf-8").splitlines()
    prefix = "\n".join(lines[: max(0, line - 1)])
    markers = list(STATUS_MARKER.finditer(prefix))
    return markers[-1].group("status").lower() if markers else None


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


def classify(root: Path, block, quality: dict[str, bool]) -> tuple[str, str]:
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
    entries = []
    for identity, block, digest in collect_public_blocks(root):
        quality = quality_contract(root, block)
        status, evidence = classify(root, block, quality)
        entries.append(
            {
                "id": identity,
                "path": block.path.as_posix(),
                "line": block.line,
                "language": block.language or "plain",
                "sha256": digest,
                "status": status,
                "evidence": evidence,
                "quality_contract": quality,
            }
        )
    return {
        "schema_version": 1,
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
