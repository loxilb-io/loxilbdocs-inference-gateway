from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "render_schema_reference", ROOT / "tools/render_schema_reference.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SchemaReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "tests/contracts/docs_examples/gateway-api.json").read_text()
        )

    def test_current_delta_is_fully_classified(self) -> None:
        rendered = MODULE.render(self.contract)
        self.assertIn("- Added definitions: **30**", rendered)
        self.assertIn("All added definitions are public-relevant", rendered)

    def test_unclassified_definition_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["schema_relevance"]["specs"][0]["added_definitions"].append(
            "UnclassifiedPublicModel"
        )
        candidate["specs"][0]["definitions"]["UnclassifiedPublicModel"] = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
        }
        with self.assertRaisesRegex(ValueError, "unclassified definitions"):
            MODULE.render(candidate)

    def test_stale_classification_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["schema_relevance"]["specs"][0]["added_definitions"].remove(
            "ReadyStatus"
        )
        with self.assertRaisesRegex(
            ValueError, "notes without a current delta definition"
        ):
            MODULE.render(candidate)


if __name__ == "__main__":
    unittest.main()
