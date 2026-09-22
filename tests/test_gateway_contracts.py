from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_gateway_contracts", ROOT / "tools/compare_gateway_contracts.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def contract(*, commit: str = "a", description_hash: str = "same") -> dict:
    return {
        "contract_version": 1,
        "source": {"commit": commit, "ebpf_submodule_commit": "ebpf-main"},
        "schema_relevance": {
            "baseline_commit": "baseline",
            "specs": [],
        },
        "specs": [
            {
                "source_path": "api/swagger.yml",
                "sha256": description_hash,
                "paths": {
                    "/config/example": {
                        "post": {"parameters": []},
                    }
                },
                "definitions": {
                    "Example": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    }
                },
            },
            {
                "source_path": "api/swagger-extras.yml",
                "sha256": "extras",
                "paths": {},
                "definitions": {},
            },
        ],
        "support_catalog": {
            "source_path": "engine-contracts/support-catalog.yaml",
            "sha256": "catalog",
            "schemaVersion": "engine-support.loxilb.io/v1alpha1",
            "entries": [],
        },
        "metric_manifest": {
            "source_path": "deploy/monitoring/manifest/metric-manifest.json",
            "sha256": "metrics",
            "families": [],
        },
        "release_snapshot": {
            "tag": "v1",
            "tag_object": "tag-object",
            "commit": "release-commit",
            "ebpf_submodule_commit": "ebpf-release",
            "metric_manifest_available": False,
            "spec_sha256": {"api/swagger.yml": "release"},
        },
        "claim_evidence": {"claims": []},
        "scenario_evidence": {
            "workflow": {"path": "workflow", "object_id": "workflow-object"},
            "trees": [],
        },
    }


class GatewayContractComparisonTests(unittest.TestCase):
    def test_commit_only_change_is_not_contract_drift(self) -> None:
        comparison = MODULE.compare_contracts(
            contract(commit="old"), contract(commit="new")
        )
        self.assertFalse(comparison.changed)

    def test_raw_description_change_is_contract_drift(self) -> None:
        comparison = MODULE.compare_contracts(
            contract(description_hash="old"), contract(description_hash="new")
        )
        self.assertTrue(comparison.changed)
        self.assertIn(
            "descriptions or other raw Swagger content changed",
            MODULE.markdown_report(comparison),
        )

    def test_removed_operation_is_reported(self) -> None:
        candidate = contract()
        candidate["specs"][0]["sha256"] = "new"
        candidate["specs"][0]["paths"] = {}
        comparison = MODULE.compare_contracts(contract(), candidate)
        swagger = next(
            spec for spec in comparison.specs
            if spec.source_path == "api/swagger.yml"
        )
        self.assertEqual(
            ["POST /config/example"], swagger.removed_operations
        )

    def test_missing_companion_swagger_is_an_error(self) -> None:
        candidate = contract()
        candidate["specs"] = candidate["specs"][:1]
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(
            any("swagger-extras.yml" in error for error in comparison.errors)
        )

    def test_support_catalog_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["support_catalog"]["sha256"] = "new-catalog"
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.catalog_changed)

    def test_engine_scenario_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["scenario_evidence"]["trees"] = [
            {"path": "cicd/example", "object_id": "tree"}
        ]
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.scenario_evidence_changed)

    def test_metric_manifest_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["metric_manifest"]["sha256"] = "new-metrics"
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.metric_manifest_changed)

    def test_claim_evidence_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["claim_evidence"]["claims"] = [{"claim": "new"}]
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.claim_evidence_changed)

    def test_release_snapshot_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["release_snapshot"]["metric_manifest_available"] = True
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.release_snapshot_changed)

    def test_ebpf_submodule_pin_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["source"]["ebpf_submodule_commit"] = "new-ebpf-main"
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.source_ebpf_changed)

    def test_schema_relevance_change_is_contract_drift(self) -> None:
        candidate = contract()
        candidate["schema_relevance"]["specs"] = [
            {
                "source_path": "api/swagger.yml",
                "added_definitions": ["NewPublicModel"],
            }
        ]
        comparison = MODULE.compare_contracts(contract(), candidate)
        self.assertTrue(comparison.changed)
        self.assertTrue(comparison.schema_relevance_changed)


if __name__ == "__main__":
    unittest.main()
