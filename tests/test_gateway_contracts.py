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
        "source": {"commit": commit},
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


if __name__ == "__main__":
    unittest.main()
