from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_examples", ROOT / "tools/validate_examples.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
ExampleValidator = MODULE.ExampleValidator


class DocumentationExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = ExampleValidator(ROOT)

    def test_all_normal_fixtures_pass(self) -> None:
        report = self.validator.validate_repository()
        self.assertEqual([], report.errors, "\n".join(report.errors))

    def test_red_twin_route_typo_is_killed(self) -> None:
        errors = self.validator.validate_route("POST", "/config/workre/metrics")
        self.assertTrue(errors)

    def test_red_twin_removed_flag_is_killed(self) -> None:
        errors = self.validator.validate_cli_command(
            "loxicmd create lb 192.0.2.10 --tcp=8080:8000 "
            "--endpoints=198.51.100.11:1 --removed-flag=true"
        )
        self.assertTrue(errors)

    def test_red_twin_wrong_enum_is_killed(self) -> None:
        errors = self.validator.validate_cli_command(
            "loxicmd create lb 192.0.2.10 --tcp=8080:8000 "
            "--endpoints=198.51.100.11:1 --mode=sideways"
        )
        self.assertTrue(errors)

    def test_red_twin_wrong_json_field_casing_is_killed(self) -> None:
        body = {
            "endpointIP": "198.51.100.11:8000",
            "queued_requests": 1,
            "kv_cache_usage_perc": 50,
        }
        errors = self.validator.validate_json_body(
            "POST", "/config/worker/metrics", body
        )
        self.assertTrue(errors)

    def test_red_twin_missing_required_field_is_killed(self) -> None:
        body = {
            "endpoint_ip": "198.51.100.11:8000",
            "kv_cache_usage_perc": 50,
        }
        errors = self.validator.validate_json_body(
            "POST", "/config/worker/metrics", body
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
