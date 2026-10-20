"""Validate the downloadable model/engine configuration contract."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
import zipfile

import yaml
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from validate_examples import ExampleValidator
from validate_model_engine_evidence import validate_package

ASSETS = ROOT / "docs/assets/model-engine-standard"


class ModelEnginePackageTests(unittest.TestCase):
    def test_catalog_evidence_and_rule_coverage(self):
        models = json.loads((ASSETS / "catalog.json").read_text())["models"]
        counts = Counter(status for model in models for status in model["combinations"].values())
        self.assertEqual(counts, {"historical-recommended": 4, "limited": 1,
                                  "reference": 8, "not-provided": 2})
        validator = ExampleValidator(ROOT)
        expected = set()
        historical = set()
        for model in models:
            for engine, status in model["combinations"].items():
                if status == "not-provided":
                    continue
                variants = ["rr", "exact"] if status == "historical-recommended" else ["rr"]
                for variant in variants:
                    name = f'{model["key"]}-{engine}-{variant}.json'
                    directory = "historical-exact" if variant == "exact" else "rules"
                    (historical if variant == "exact" else expected).add(name)
                    body = json.loads((ASSETS / directory / name).read_text())
                    self.assertEqual([], validator.validate_json_body(
                        "POST", "/config/loadbalancer", body), name)
                    args = body["serviceArguments"]
                    self.assertEqual(args["model_name"], model["MODEL"])
                    self.assertFalse(args["pd_disagg_mode"])
                    self.assertEqual(args["kvExactMode"], 3 if variant == "exact" else 0)
                    self.assertEqual(len(body["endpoints"]), 3)
                    self.assertTrue(all(ep["targetPort"] == args["probeport"]
                                        for ep in body["endpoints"]))
                    if variant == "rr":
                        self.assertNotIn("kvModelProfile", args)
                        self.assertNotIn("kvExactApiMode", args)
                    else:
                        self.assertEqual(args["kvModelProfile"], model["PROFILE"])
                        self.assertEqual(args["kvEngineType"], "vllm")
                        self.assertEqual(args["kvBlockSize"], 16)
        self.assertEqual(expected, {p.name for p in (ASSETS / "rules").glob("*.json")})
        self.assertEqual(historical, {p.name for p in (ASSETS / "historical-exact").glob("*.json")})

    def test_selection_does_not_turn_historical_profiles_into_public_support(self):
        cards = json.loads((ASSETS / "catalog.json").read_text())
        public = json.loads((ASSETS / "profiles/catalog-snapshot.json").read_text())
        public_ids = {m["profileId"] for m in public["models"]}
        self.assertEqual(cards["selectionPolicy"]["publicCatalogSourceCommit"],
                         public["sourceCommit"])
        self.assertEqual(cards["selectionPolicy"]["publicCatalogValidatedTuples"],
                         sum(t["state"] == "validated" for m in public["models"]
                             for t in m["tuples"]))
        for model in cards["models"]:
            self.assertNotIn(model["PROFILE"], public_ids)
            self.assertEqual(model["publicCatalogMembership"], "absent")
            self.assertEqual(model["exactAvailability"], "separate-qa-evaluation-profiles-supplied")
            for engine, choice in model["historicalChoices"].items():
                recipe = ASSETS / "rules" / f'{model["key"]}-{engine}-rr.json'
                self.assertEqual(recipe.exists(), choice != "not-provided")
                if recipe.exists():
                    args = json.loads(recipe.read_text())["serviceArguments"]
                    self.assertEqual(args["kvExactMode"], 0)
                    self.assertNotIn("kvModelProfile", args)

    def test_all_frameworks_offer_paired_evaluation_rr_and_exact_rules(self):
        public = json.loads((ASSETS / "profiles/catalog-snapshot.json").read_text())
        model = next(m for m in public["models"]
                     if m["profileId"] == "r1-distill-qwen-15b-v1")
        validator = ExampleValidator(ROOT)
        for engine in ("vllm", "sglang", "trtllm"):
            row = next(t for t in model["tuples"] if t["engine"] == engine)
            self.assertEqual(row["state"], "candidate")
            self.assertIn("converged", row["modes"])
            self.assertIn("chat", row["apis"])
            bodies = {}
            for mode in ("rr", "exact"):
                body = json.loads((ASSETS / f"routing-choice/{engine}-{mode}.json").read_text())
                bodies[mode] = body
                self.assertEqual([], validator.validate_json_body(
                    "POST", "/config/loadbalancer", body))
                args = body["serviceArguments"]
                self.assertEqual(args["kvEngineType"], engine)
                self.assertEqual(args["model_name"], model["repo"])
                self.assertFalse(args["pd_disagg_mode"])
                self.assertEqual(args["kvExactMode"], 0 if mode == "rr" else 3)
                if mode == "exact":
                    self.assertEqual(args["kvModelProfile"], model["profileId"])
                    self.assertEqual(args["kvExactApiMode"], "chat")
                    self.assertEqual(args["kvBlockSize"], 32 if engine == "trtllm" else 16)
                    self.assertEqual("kvZmqPort" in args, engine != "trtllm")
                else:
                    self.assertNotIn("kvModelProfile", args)
            self.assertEqual(bodies["rr"]["endpoints"], bodies["exact"]["endpoints"])
            for key in ("port", "externalIP", "host", "model_name"):
                self.assertEqual(bodies["rr"]["serviceArguments"][key],
                                 bodies["exact"]["serviceArguments"][key])

    def test_executable_vllm_settings_use_stock_031_without_rewriting_source_catalog(self):
        digest = "sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b"
        for relative in ("engines/vllm.env", "routing-choice/vllm.env"):
            settings = (ASSETS / relative).read_text()
            self.assertIn("ENGINE_IMAGE=vllm/vllm-openai@" + digest, settings)
            self.assertNotIn("61fc8a896b0a4fbb", settings)
        snapshot = json.loads((ASSETS / "profiles/catalog-snapshot.json").read_text())
        engine = next(e for e in snapshot["engines"] if e["engine"] == "vllm")
        self.assertEqual(engine["version"], "v0.28.0")
        catalog = json.loads((ASSETS / "catalog.json").read_text())
        self.assertEqual(catalog["routingChoiceExample"]["vllmTargetVersion"], "0.31.0")

    def test_qualification_matrix_keeps_every_mode_and_prerequisite_visible(self):
        matrix = json.loads((ASSETS / "qualification-matrix.json").read_text())
        entries = matrix["entries"]
        self.assertEqual(len(entries), 36)
        self.assertEqual(len({(e["scope"],e["modelKey"],e["engine"],e["mode"])
                              for e in entries}), 36)
        self.assertEqual(Counter(e["scope"] for e in entries),
                         {"standard-card":30, "public-candidate-routing-example":6})
        for entry in entries:
            if entry["scope"] == "standard-card":
                if matrix["runtimeEvidencePublication"]["status"] == "pending":
                    self.assertEqual(entry["currentPublicTupleRuntime"], "not-run")
                    self.assertNotIn("evidenceSummary", entry)
                    self.assertTrue(entry["readinessToExecute"])
                    self.assertTrue(entry["completionEvidence"])
                else:
                    self.assertIn(entry["currentPublicTupleRuntime"],
                                  ("PASS_BOUNDED_FUNCTIONAL", "BLOCKED_NATIVE_ARCHITECTURE",
                                   "NOT_RUN", "FAIL_TRAFFIC_OR_ROUTING", "FAIL_ATTESTATION"))
                    self.assertTrue(entry["remainingGates"])
                    self.assertTrue((ASSETS / entry["evidenceSummary"]).is_file())
            elif entry["engine"] == "vllm" and entry["scope"] == "public-candidate-routing-example":
                self.assertEqual(entry["currentPublicTupleRuntime"], "bounded-gpu-qa-full-qualification-open")
                self.assertTrue(entry["remainingGates"])
                self.assertTrue((ASSETS / entry["evidenceSummary"]).is_file())
            else:
                self.assertEqual(entry["currentPublicTupleRuntime"], "not-run")
            self.assertIn(entry["mode"], ("rr", "exact"))
            self.assertIn("backend-owned-receipts", entry["completionEvidence"])
            if entry["currentPublicTupleRuntime"] == "BLOCKED_NATIVE_ARCHITECTURE":
                self.assertTrue(entry["blockers"])

    def test_thirty_case_rules_match_api_and_model_profile_contracts(self):
        models = json.loads((ASSETS / "catalog.json").read_text())["models"]
        validator = ExampleValidator(ROOT)
        expected = set()
        for model in models:
            for engine in ("vllm", "sglang", "trtllm"):
                for mode in ("rr", "exact"):
                    name = f'{model["key"]}-{engine}-{mode}.json'
                    expected.add(name)
                    body = json.loads((ASSETS / "matrix-configurations" / name).read_text())
                    self.assertEqual([], validator.validate_json_body(
                        "POST", "/config/loadbalancer", body), name)
                    args = body["serviceArguments"]
                    self.assertEqual(args["model_name"], model["MODEL"])
                    self.assertEqual(args["kvEngineType"], engine)
                    self.assertEqual(args["kvExactMode"], 3 if mode == "exact" else 0)
                    self.assertEqual(len(body["endpoints"]), 3)
                    self.assertFalse(args["pd_disagg_mode"])
                    if mode == "exact":
                        self.assertEqual(args["kvModelProfile"], model["PROFILE"])
                        self.assertEqual(args["kvExactApiMode"], "chat")
                        self.assertEqual(args["kvBlockSize"], 32 if engine == "trtllm" else 16)
                        self.assertEqual("kvZmqPort" in args, engine != "trtllm")
                    else:
                        self.assertNotIn("kvModelProfile", args)
                        self.assertNotIn("kvExactApiMode", args)
        self.assertEqual(len(expected), 30)
        self.assertEqual(expected, {p.name for p in
                                   (ASSETS / "matrix-configurations").glob("*.json")})

    def test_evaluation_profiles_keep_fixture_identity_and_exclude_model_artifacts(self):
        models = json.loads((ASSETS / "catalog.json").read_text())["models"]
        directory = ASSETS / "evaluation-profiles"
        versions = {"vllm": "0.31.0", "sglang": "0.5.19", "trtllm": "1.3.0rc29"}
        for model in models:
            profile = yaml.safe_load((directory / "definitions" /
                                      f'{model["PROFILE"]}.yaml').read_text())
            self.assertEqual(profile["profileId"], model["PROFILE"])
            self.assertEqual(profile["baseModel"], model["MODEL"])
            self.assertEqual(profile["tokenizerRevision"], model["REV"])
            self.assertIn("chat", profile["supportedApis"])
            for engine, version in versions.items():
                prepared = yaml.safe_load((directory / f"definitions-{engine}" /
                                           f'{model["PROFILE"]}.yaml').read_text())
                if engine == "sglang" and model["key"] == "r1":
                    self.assertIs(prepared["engineQuirks"]["sglang-kv-rank-v1"]["completionsBos"], True)
                    unchanged = json.loads(json.dumps(prepared))
                    self.assertEqual(unchanged.pop("engineQuirks"),
                                     {"sglang-kv-rank-v1": {"completionsBos": True}})
                    self.assertEqual(unchanged, profile)
                else:
                    self.assertEqual(prepared, profile)
                manifest = yaml.safe_load((directory / f"manifests-{engine}" /
                                           f'{model["PROFILE"]}.yaml').read_text())
                self.assertEqual(manifest["profileId"], profile["profileId"])
                self.assertEqual(manifest["modelRevision"], model["REV"])
                self.assertEqual(manifest["engineVersion"], version)
                self.assertRegex(manifest["imageDigest"], r"^sha256:[0-9a-f]{64}$")
        requests = list((directory / "probefixtures").rglob("*.request.json"))
        self.assertTrue(requests)
        for request in requests:
            expectation = request.with_name(request.name.replace(".request.", ".expect."))
            expected = json.loads(expectation.read_text())
            self.assertEqual(expected["requestSha256"],
                             hashlib.sha256(request.read_bytes()).hexdigest(), str(request))
            self.assertTrue(expected["expectedTokenIds"])
        self.assertFalse(list(directory.rglob("*.safetensors")))
        self.assertFalse(list(directory.rglob("*.gguf")))
        self.assertFalse(list(directory.rglob("tokenizer.json")))
        self.assertFalse(list(directory.rglob("*.jinja")))

    def test_runtime_verdicts_account_for_all_modes_and_do_not_promote_support(self):
        matrix, summary, ledger = validate_package(ASSETS)
        if matrix["runtimeEvidencePublication"]["status"] == "pending":
            self.assertIsNone(summary)
            self.assertIsNone(ledger)
            self.assertEqual(Counter(e["currentPublicTupleRuntime"] for e in matrix["entries"]
                                     if e["scope"] == "standard-card"), {"not-run": 30})
        else:
            self.assertEqual(len(summary["cases"]), 30)
            self.assertIs(summary["catalogPromotion"], False)

    def test_public_receipts_reconcile_counts(self):
        matrix, summary, ledger = validate_package(ASSETS)
        if matrix["runtimeEvidencePublication"]["status"] == "pending":
            self.assertIsNone(ledger)  # No synthetic receipts stand in for an unrun case.
            self.assertIsNone(summary)
        else:
            self.assertEqual(ledger["counts"],
                             dict(Counter(r["caseId"] for r in ledger["records"])))

    def test_requests_match_models_and_stream_contract(self):
        models = json.loads((ASSETS / "catalog.json").read_text())["models"]
        for model in models:
            for variant in ("chat", "stream"):
                body = json.loads((ASSETS / "requests" / f'{model["key"]}-{variant}.json').read_text())
                self.assertEqual(body["model"], model["MODEL"])
                self.assertEqual(body["max_tokens"], 32)
                if variant == "stream":
                    self.assertIs(body["stream"], True)
                    self.assertTrue(body["stream_options"]["include_usage"])
                else:
                    self.assertNotIn("stream", body)

    def test_profile_snapshot_does_not_promote_candidates(self):
        snapshot = json.loads((ASSETS / "profiles/catalog-snapshot.json").read_text())
        models = snapshot["models"]
        self.assertEqual(len(models), 13)
        self.assertEqual(len({m["profileId"] for m in models}), 13)
        self.assertEqual(Counter(t["state"] for m in models for t in m["tuples"]),
                         {"candidate": 31, "blocked": 8})
        for model in models:
            self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
            for row in model["tuples"]:
                if row["state"] == "blocked":
                    self.assertTrue(row["reason"])

    def test_sglang_compatible_baseline_is_separate_from_map_support_request(self):
        choice = json.loads((ASSETS / "sglang-version-selection.json").read_text())
        self.assertEqual(choice["selectedVersion"], "0.5.19")
        self.assertEqual(choice["wire"], "sglang-kv-tagged-array-rank-v1")
        historical = choice["historicalLiveWireObservation"]
        self.assertEqual(historical["eventEncoding"], "tagged-array")
        self.assertEqual(historical["version"], choice["historicalVersion"])
        self.assertRegex(historical["payloadSha256"], r"^[0-9a-f]{64}$")
        current_wire = choice.get("liveWireObservation")
        if current_wire is not None:
            self.assertEqual(current_wire["eventEncoding"], "tagged-array")
            self.assertEqual(current_wire["version"], choice["selectedVersion"])
            self.assertRegex(current_wire["payloadSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(choice["separateDevelopmentRequest"]["version"], "0.5.21")
        self.assertEqual(choice["separateDevelopmentRequest"]["exactResult"], "FAIL_ATTESTATION")
        self.assertIs(choice["catalogPromotion"], False)
        self.assertIn(choice["image"], (ASSETS / "engines/sglang.env").read_text())
        for manifest in (ASSETS / "evaluation-profiles/manifests-sglang").glob("*.yaml"):
            data = yaml.safe_load(manifest.read_text())
            self.assertEqual(data["engineVersion"], choice["selectedVersion"])
            self.assertEqual(data["imageDigest"], choice["image"].split("@", 1)[1])
        matrix, runtime, _ = validate_package(ASSETS)
        if runtime is None:
            self.assertEqual(matrix["runtimeEvidencePublication"]["status"], "pending")
            self.assertIsNone(choice["newFiveModelEvidence"])
            self.assertEqual(choice["newFiveModelEvidencePublication"], "pending")
            self.assertEqual(choice["plannedFiveModelEvidence"], "matrix-results.json")
        else:
            self.assertEqual(choice["newFiveModelEvidence"], "matrix-results.json")
            self.assertEqual(choice["newFiveModelEvidencePublication"], "published")
            self.assertTrue(all(row["engineVersion"] == "0.5.19"
                                for row in runtime["cases"] if row["engine"] == "sglang"
                                and row["result"] != "NOT_RUN"))
            if any(row["engine"] == "sglang" and row["result"] == "PASS_BOUNDED_FUNCTIONAL"
                   for row in runtime["cases"]):
                self.assertIsNotNone(current_wire, "SGLang PASS requires current-version wire evidence")

    def test_failover_reference_is_separate_pd_shape(self):
        rule = json.loads((ASSETS / "failover/qwen25-pd-rule.json").read_text())
        self.assertEqual([], ExampleValidator(ROOT).validate_json_body(
            "POST", "/config/loadbalancer", rule))
        args = rule["serviceArguments"]
        self.assertTrue(args["pd_disagg_mode"])
        self.assertEqual(args["kvExactMode"], 0)
        self.assertFalse(args["pd_cache_aware_mode"])
        self.assertEqual(Counter(e["ep_role"] for e in rule["endpoints"]), {1: 2, 2: 2})
        self.assertEqual(args["pd_prefill_timeout_sec"], 15)
        for role, kv_role in (("prefill", "kv_producer"), ("decode", "kv_consumer")):
            cfg = json.loads((ASSETS / f"failover/engine-{role}-kv.json").read_text())
            self.assertEqual(cfg["kv_role"], kv_role)
            self.assertEqual(cfg["kv_load_failure_policy"], "fail")
            self.assertEqual(cfg["kv_buffer_device"], "cpu")

    def test_archive_and_checksums_match_every_public_file(self):
        files = {p.relative_to(ASSETS).as_posix(): p for p in ASSETS.rglob("*") if p.is_file()}
        checksums = dict(line.split("  ", 1)[::-1]
                         for line in (ASSETS / "SHA256SUMS").read_text().splitlines())
        self.assertEqual(set(files) - {"SHA256SUMS"}, set(checksums))
        for name, digest in checksums.items():
            self.assertEqual(hashlib.sha256(files[name].read_bytes()).hexdigest(), digest)
        with zipfile.ZipFile(ASSETS.with_suffix(".zip")) as archive:
            self.assertEqual(set(files), set(archive.namelist()))
            for name, path in files.items():
                self.assertEqual(path.read_bytes(), archive.read(name))


if __name__ == "__main__":
    unittest.main()
