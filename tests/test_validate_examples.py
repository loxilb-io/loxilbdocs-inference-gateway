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

    def test_release_lifecycle_commands_are_frozen(self) -> None:
        for command in (
            "get snapshot", "create restore", "create persist",
            "get ready", "get diagnostics", "get maintenance",
            "set maintenance", "appliance status",
        ):
            with self.subTest(command=command):
                contract = self.validator.cli_contract["commands"][command]
                self.assertTrue(contract["release"]["available"])
                self.assertTrue(contract["main"]["available"])

    def test_main_only_appliance_lifecycle_needs_marker(self) -> None:
        command = (
            "loxicmd appliance restore plan /var/lib/backup/appliance.tar.age "
            "--key-file /root/backup.key"
        )
        self.assertTrue(self.validator.validate_cli_command(command))
        self.assertEqual(
            [],
            self.validator.validate_cli_command(
                command, "CLI availability: main-only"
            ),
        )

    def test_recovery_operations_are_in_the_swagger_union(self) -> None:
        operations = (
            ("GET", "/config/snapshot"),
            ("POST", "/config/restore"),
            ("POST", "/config/persist"),
            ("GET", "/status/ready"),
            ("GET", "/status/capabilities"),
            ("GET", "/diagnostics"),
            ("GET", "/maintenance"),
            ("PUT", "/maintenance"),
        )
        for method, route in operations:
            with self.subTest(method=method, route=route):
                self.assertEqual([], self.validator.validate_route(method, route))

    def test_engine_kv_and_sockmap_operations_are_in_the_swagger_union(self) -> None:
        operations = (
            ("GET", "/config/ai/model-profiles"),
            ("GET", "/config/ai/model-profiles/example-profile"),
            (
                "GET",
                "/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/kvexactstatus",
            ),
            (
                "POST",
                "/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/sockmapreset",
            ),
        )
        for method, route in operations:
            with self.subTest(method=method, route=route):
                self.assertEqual([], self.validator.validate_route(method, route))

    def test_engine_support_catalog_exact_tuples_are_frozen(self) -> None:
        entries = self.validator.gateway_contract["support_catalog"]["entries"]
        tuples = {
            (
                entry["engine"],
                entry["version"],
                entry.get("revision", ""),
                entry.get("image", {}).get("platformDigest", ""),
                entry["gatewayRelease"],
                entry["profile"],
                entry["promotion"],
            )
            for entry in entries
        }
        self.assertEqual(
            {
                ("vllm", "v0.23.0", "", "", "v0.9.8.9-rc.1", "vllm-kv-array-v1", "candidate"),
                (
                    "vllm", "v0.28.0", "2cf0a6915ce544dc493a0990f2ea38d81601128a",
                    "sha256:61fc8a896b0a4fbbbdc063bc4b0dbc25ce98e02b5050c24aeb7830ac02039b14",
                    "v0.9.8.9-rc.1", "vllm-kv-map-v2", "validated",
                ),
                (
                    "sglang", "v0.5.18", "71de97b264b04dcd514cf904003028aefe9775c8",
                    "sha256:9e148f5ac788e856a06166bd6347a831831eb9fcfab4d1770874823a7c29a1a1",
                    "v0.9.8.9-rc.1", "sglang-kv-rank-v1", "validated",
                ),
                ("trtllm", "v1.2.1", "", "", "v0.9.8.9-rc.1", "trtllm-kv-http-v1", "candidate"),
                (
                    "trtllm", "1.3.0rc24", "1cef02e901be43081b1ba6d4981e94ed3bd9c1e8",
                    "sha256:a867619fd56c85225927dac27e2111ae90ff66e23c59d9c5f8b9f345577cab6d",
                    "v0.9.8.9-rc.1", "trtllm-kv-http-preview-v1", "validated",
                ),
                ("llamacpp", "v0.3.0", "", "", "v0.9.8.9-rc.1", "llamacpp-nokv-v1", "candidate"),
            },
            tuples,
        )

    def test_validated_catalog_tuples_have_real_engine_evidence(self) -> None:
        entries = self.validator.gateway_contract["support_catalog"]["entries"]
        for entry in entries:
            if entry["promotion"] != "validated":
                continue
            with self.subTest(engine=entry["engine"], version=entry["version"]):
                self.assertTrue(entry["revision"])
                self.assertTrue(entry.get("image", {}).get("platformDigest"))
                for capability in entry["capabilities"].values():
                    self.assertEqual("pass", capability["evidence"]["realEngine"])

    def test_required_engine_scenario_sources_are_frozen(self) -> None:
        trees = {
            entry["path"]
            for entry in self.validator.gateway_contract["scenario_evidence"]["trees"]
        }
        self.assertEqual(
            {
                "cicd/kv-mixed-version",
                "cicd/kv-profile-admission",
                "cicd/kv-sglang-attest",
                "cicd/sockmap-fullproxy",
                "cicd/vllm-kvcache-routing-cpu",
                "cicd/vllm-pd-admission-cpu",
            },
            trees,
        )

    def test_strict_kv_fields_are_rest_only(self) -> None:
        flags = set(self.validator.cli_contract["commands"]["create lb"]["main"]["flags"])
        self.assertNotIn("--kv-exact-api-mode", flags)
        self.assertNotIn("--kv-model-profile", flags)

    def test_strict_kv_field_schema_is_frozen(self) -> None:
        spec = self.validator.gateway_contract["specs"][0]
        fields = spec["definitions"]["LoadbalanceEntry"]["properties"][
            "serviceArguments"
        ]["properties"]
        self.assertEqual(
            {"completions", "chat", "both"}, set(fields["kvExactApiMode"]["enum"])
        )
        self.assertEqual("string", fields["kvModelProfile"]["type"])
        self.assertEqual(
            {"off", "both", "request", "response"}, set(fields["sockMapMode"]["enum"])
        )

    def test_red_twin_kv_api_mode_without_exact_is_killed(self) -> None:
        body = {
            "serviceArguments": {
                "externalIP": "192.0.2.10", "port": 8080, "protocol": "tcp",
                "mode": 4, "kvExactApiMode": "chat",
            },
            "endpoints": [],
        }
        self.assertTrue(
            self.validator.validate_contract_semantics("POST", "/config/loadbalancer", body)
        )

    def test_red_twin_sockmap_with_request_rewrite_is_killed(self) -> None:
        for conflicting in (
            {"sse_mode": True},
            {"pd_disagg_mode": True},
            {"api_key_auth": "disabled"},
            {"api_key_auth": "required"},
            {"api_key_auth": "jwt"},
            {"api_key_auth": "apikey-or-jwt"},
        ):
            with self.subTest(conflicting=conflicting):
                body = {
                    "serviceArguments": {
                        "externalIP": "192.0.2.10", "port": 8080,
                        "protocol": "tcp", "mode": 4, "sockMapMode": "both",
                        **conflicting,
                    },
                    "endpoints": [],
                }
                self.assertTrue(
                    self.validator.validate_contract_semantics(
                        "POST", "/config/loadbalancer", body
                    )
                )

    def test_capability_readiness_contract_is_frozen(self) -> None:
        spec = self.validator.gateway_contract["specs"][0]
        capability = spec["definitions"]["CapabilityStatus"]
        self.assertEqual({"name", "ready"}, set(capability["required"]))
        self.assertEqual("string", capability["properties"]["name"]["type"])
        self.assertNotIn("enum", capability["properties"]["name"])

        capability_list = spec["definitions"]["CapabilityStatusList"]
        self.assertEqual({"capabilities"}, set(capability_list["required"]))
        self.assertEqual(
            "#/definitions/CapabilityStatus",
            capability_list["properties"]["capabilities"]["items"]["$ref"],
        )

    def test_maintenance_requires_explicit_enabled_state(self) -> None:
        errors = self.validator.validate_json_body("PUT", "/maintenance", {})
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

    def test_five_state_credential_contract_is_frozen(self) -> None:
        spec = self.validator.gateway_contract["specs"][0]
        field = spec["definitions"]["LoadbalanceEntry"]["properties"][
            "serviceArguments"
        ]["properties"]["api_key_auth"]
        self.assertEqual(
            {"disabled", "required", "jwt", "apikey-or-jwt"},
            set(field["enum"]),
        )
        self.assertNotIn("default", field)

    def test_companion_apikey_patch_contract_has_all_runtime_fields(self) -> None:
        matches = self.validator.matching_operations(
            "PATCH", "/config/ai/apikey/example-key-id"
        )
        self.assertEqual(2, len(matches))
        body_property_sets = []
        for _, operation in matches:
            for parameter in operation.get("parameters", []):
                if parameter.get("in") == "body":
                    body_property_sets.append(
                        set(parameter.get("schema", {}).get("properties", {}))
                    )
        self.assertIn(
            {
                "allowed_models", "enabled", "rate_limit_rps",
                "burst_size", "tokens_per_min",
            },
            body_property_sets,
        )

    def test_red_twin_empty_apikey_patch_is_killed(self) -> None:
        errors = self.validator.validate_json_body(
            "PATCH", "/config/ai/apikey/example-key-id", {}
        )
        self.assertTrue(errors)

    def test_explicit_empty_allowlist_patch_is_not_a_noop(self) -> None:
        errors = self.validator.validate_json_body(
            "PATCH",
            "/config/ai/apikey/example-key-id",
            {"allowed_models": []},
        )
        self.assertEqual([], errors)

    def test_red_twin_jwt_without_profile_is_killed(self) -> None:
        body = {
            "serviceArguments": {"api_key_auth": "jwt"},
            "endpoints": [],
        }
        errors = self.validator.validate_contract_semantics(
            "POST", "/config/loadbalancer", body
        )
        self.assertTrue(errors)

    def test_red_twin_profile_on_required_rule_is_killed(self) -> None:
        body = {
            "serviceArguments": {
                "api_key_auth": "required",
                "jwt_auth_profile": "issuer-a",
            },
            "endpoints": [],
        }
        errors = self.validator.validate_contract_semantics(
            "POST", "/config/loadbalancer", body
        )
        self.assertTrue(errors)

    def test_red_twin_qos_rule_defaults_without_identity_is_killed(self) -> None:
        errors = self.validator.validate_contract_semantics(
            "POST",
            "/config/ai/ratelimit/defaults",
            {"scope": "rule", "default_user_rps": 1},
        )
        self.assertTrue(errors)

    def test_red_twin_empty_user_model_is_killed(self) -> None:
        errors = self.validator.validate_contract_semantics(
            "POST",
            "/config/ai/user/ratelimit",
            {
                "tenant_id": "team-a",
                "user_id": "user-a",
                "model_limits": [{"tokens_per_min": 100}],
            },
        )
        self.assertTrue(errors)

    def test_wrong_limit_type_reports_errors_instead_of_crashing(self) -> None:
        errors = self.validator.validate_json_body(
            "POST",
            "/config/ai/user/ratelimit",
            {
                "tenant_id": "team-a",
                "user_id": "user-a",
                "rps": "not-a-number",
            },
        )
        self.assertTrue(errors)

    def test_red_twin_inline_management_bearer_is_killed(self) -> None:
        errors = self.validator.validate_curl_credential_hygiene(
            "curl -H 'Authorization: Bearer $TOKEN' https://gateway.example.com"
        )
        self.assertTrue(errors)

    def test_red_twin_inline_api_key_is_killed(self) -> None:
        errors = self.validator.validate_curl_credential_hygiene(
            "curl -H 'X-Api-Key: $INFERENCE_API_KEY' https://ai.example.com"
        )
        self.assertTrue(errors)

    def test_protected_header_file_passes_credential_hygiene(self) -> None:
        errors = self.validator.validate_curl_credential_hygiene(
            "curl --header @control-plane.headers https://gateway.example.com"
        )
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
