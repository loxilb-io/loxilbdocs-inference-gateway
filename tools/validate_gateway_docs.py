#!/usr/bin/env python3
"""Validate public docs against a selected Gateway Git ref and report drift."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from compare_gateway_contracts import compare_contracts, load_contract, markdown_report
from refresh_example_contracts import build_gateway_contract, write_json
from render_metrics_reference import render as render_metrics_reference
from render_schema_reference import render as render_schema_reference
from validate_examples import ExampleValidator, print_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-repo", type=Path, required=True)
    parser.add_argument("--gateway-ref", default="HEAD")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--allow-missing-tools",
        action="store_true",
        help="skip external bash/jq/yq checks when a command is unavailable",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    tracked_dir = root / "tests/contracts/docs_examples"

    with tempfile.TemporaryDirectory(prefix="gateway-doc-contract-") as temporary:
        candidate_dir = Path(temporary)
        candidate_path = candidate_dir / "gateway-api.json"
        write_json(
            candidate_path,
            build_gateway_contract(args.gateway_repo.resolve(), args.gateway_ref),
        )
        shutil.copy2(tracked_dir / "cli.json", candidate_dir / "cli.json")

        validator = ExampleValidator(
            root,
            not args.allow_missing_tools,
            candidate_dir,
        )
        validation = validator.validate_repository()
        print_report(validation)

        comparison = compare_contracts(
            load_contract(tracked_dir / "gateway-api.json"),
            load_contract(candidate_path),
        )
        print()
        print(markdown_report(comparison))
        rendered_metrics_match = (
            (root / "docs/reference/metrics.md").read_text()
            == render_metrics_reference(load_contract(candidate_path))
        )
        print(
            "Generated metric reference: "
            + ("up to date" if rendered_metrics_match else "STALE")
        )
        rendered_schema_match = (
            (root / "docs/reference/api-schema-models.md").read_text()
            == render_schema_reference(load_contract(candidate_path))
        )
        print(
            "Generated API schema reference: "
            + ("up to date" if rendered_schema_match else "STALE")
        )
        return 1 if (
            validation.errors
            or comparison.changed
            or not rendered_metrics_match
            or not rendered_schema_match
        ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
