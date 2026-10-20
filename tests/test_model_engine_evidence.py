"""Test-only evidence examples exercise the runtime gates without running a GPU."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_model_engine_evidence import validate_runtime_evidence, validate_registration_plan
from package_model_engine_examples import package


class ModelEngineEvidenceTests(unittest.TestCase):
    def pending(self):
        return {
            "runtimeEvidencePublication": {"scope": "standard-card", "status": "pending",
                "summary": "matrix-results.json", "requestLedger": "matrix-request-ledger.json"},
            "entries": [{"scope": "standard-card", "modelKey": "example", "engine": "vllm",
                         "mode": "rr", "currentPublicTupleRuntime": "not-run"}],
        }

    def published(self, mode="rr"):
        # This data is a validator unit-test fixture, never exported as QA evidence.
        matrix = self.pending()
        matrix["runtimeEvidencePublication"]["status"] = "published"
        entry = matrix["entries"][0]
        entry.update(mode=mode, currentPublicTupleRuntime="PASS_BOUNDED_FUNCTIONAL",
                     evidenceSummary="matrix-results.json", blockers=[])
        case = "example-vllm-" + mode
        row = {"caseId": case, "modelKey": "example", "engine": "vllm", "mode": mode,
               "configuration": f"matrix-configurations/{case}.json",
               "result": "PASS_BOUNDED_FUNCTIONAL", "rawResultSha256": "a" * 64,
               "engineImageDigest": "sha256:" + "b" * 64, "engineVersion": "test-only",
               "remainingGates": ["release-qualification"], "normal": 1, "offered": 1,
               "workerReceipts": {"workerA": 1}, "receiptHashAudit": "pass",
               "invalidMutationNoChange": True, "configuredServiceAndEndpointsUnchanged": True,
               "scopedRuleDeletion": "absent"}
        sample = {"caseId": case, "sample": "main-0", "requestId": "unit-test-main",
                  "stream": True, "normalCompletion": True, "sseDoneCount": 1,
                  "worker": "workerA", "requestSha256": "c" * 64,
                  "backendRequestSha256": "c" * 64, "responseSha256": "d" * 64,
                  "backendResponseSha256": "d" * 64, "backendUpstreamComplete": True}
        records = [sample]
        if mode == "exact":
            row.update(enforcedState="READY", reasonCodes=[], goFenced=False,
                       cacheHitDelta=1, coldNormal=1, coldReceiptHashAudit="pass")
            records.append(dict(sample, sample="cold-0", requestId="unit-test-cold"))
        summary = {"catalogPromotion": False, "historicalGemmaLoadFailure": "open",
                   "counts": {"PASS_BOUNDED_FUNCTIONAL": 1}, "cases": [row]}
        ledger = {"counts": {case: len(records)}, "records": records}
        return matrix, summary, ledger

    def test_pending_requires_explicit_unrun_state_and_no_result_files(self):
        matrix = self.pending()
        validate_runtime_evidence(matrix, None, None)
        for verdict in ("PASS_BOUNDED_FUNCTIONAL", "BLOCKED_NATIVE_ARCHITECTURE", "unknown"):
            changed = copy.deepcopy(matrix)
            changed["entries"][0]["currentPublicTupleRuntime"] = verdict
            with self.subTest(verdict=verdict), self.assertRaises(ValueError):
                validate_runtime_evidence(changed, None, None)
        with self.assertRaises(ValueError):
            validate_runtime_evidence(matrix, {}, None)
        with self.assertRaises(ValueError):
            validate_runtime_evidence(matrix, None, {})

    def test_missing_published_evidence_is_rejected(self):
        matrix, summary, ledger = self.published()
        for s, l in ((None, None), (summary, None), (None, ledger)):
            with self.subTest(summary=s is not None, ledger=l is not None):
                with self.assertRaises(ValueError):
                    validate_runtime_evidence(matrix, s, l)

    def test_rr_and_exact_success_gates_are_exercised(self):
        for mode in ("rr", "exact"):
            with self.subTest(mode=mode):
                validate_runtime_evidence(*self.published(mode))

    def test_receipt_hash_completion_counts_and_worker_mutations_fail(self):
        for field, value in (("backendResponseSha256", "0" * 64),
                             ("backendRequestSha256", "0" * 64),
                             ("normalCompletion", False), ("backendUpstreamComplete", False),
                             ("sseDoneCount", 0), ("sseDoneCount", 2), ("worker", "workerB")):
            matrix, summary, ledger = self.published()
            ledger["records"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_runtime_evidence(matrix, summary, ledger)
        matrix, summary, ledger = self.published()
        ledger["records"] = []
        ledger["counts"] = {}
        with self.assertRaises(ValueError):
            validate_runtime_evidence(matrix, summary, ledger)

    def test_incomplete_workload_and_exact_fallback_cannot_pass(self):
        for field, value in (("offered", 2), ("normal", 0), ("goFenced", True),
                             ("enforcedState", "PROFILE_VALIDATED"),
                             ("reasonCodes", ["identity_mismatch"]), ("cacheHitDelta", 0),
                             ("coldNormal", 0), ("invalidMutationNoChange", False),
                             ("configuredServiceAndEndpointsUnchanged", False),
                             ("scopedRuleDeletion", "present")):
            matrix, summary, ledger = self.published("exact")
            summary["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_runtime_evidence(matrix, summary, ledger)

    def test_unrun_row_cannot_inherit_pass_metrics(self):
        matrix, summary, ledger = self.published()
        matrix["entries"][0]["currentPublicTupleRuntime"] = "NOT_RUN"
        summary["cases"][0].update(result="NOT_RUN", inferenceAttempted=False)
        summary["counts"] = {"NOT_RUN": 1}
        with self.assertRaises(ValueError):
            validate_runtime_evidence(matrix, summary, ledger)
        row = summary["cases"][0]
        summary["cases"][0] = {k: v for k, v in row.items() if k in
                              ("caseId", "modelKey", "engine", "mode", "configuration",
                               "result", "inferenceAttempted", "remainingGates")}
        ledger = {"counts": {}, "records": []}
        validate_runtime_evidence(matrix, summary, ledger)

    def test_matrix_count_and_support_promotions_fail(self):
        for target, field, value in (("summary", "catalogPromotion", True),
                                     ("summary", "counts", {}),
                                     ("summary", "historicalGemmaLoadFailure", "closed"),
                                     ("ledger", "counts", {})):
            matrix, summary, ledger = self.published()
            (summary if target == "summary" else ledger)[field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                validate_runtime_evidence(matrix, summary, ledger)

    def test_package_rebuild_is_deterministic_and_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            assets = Path(temp) / "examples"
            assets.mkdir()
            (assets / "qualification-matrix.json").write_text(json.dumps(self.pending()))
            source = assets / "example.json"
            source.write_text("{}\n")
            package(assets)
            before = assets.with_suffix(".zip").read_bytes()
            package(assets)
            self.assertEqual(assets.with_suffix(".zip").read_bytes(), before)
            package(assets, check=True)
            source.write_text('{"changed":true}\n')
            with self.assertRaises(ValueError):
                package(assets, check=True)
            package(assets)
            package(assets, check=True)

    def test_package_rejects_unreviewed_result_file_and_extra_archive_member(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            assets = Path(temp) / "examples"
            assets.mkdir()
            (assets / "qualification-matrix.json").write_text(json.dumps(self.pending()))
            package(assets)
            with zipfile.ZipFile(assets.with_suffix(".zip"), "a") as archive:
                archive.writestr("unreviewed.txt", "unexpected")
            with self.assertRaises(ValueError):
                package(assets, check=True)
            (assets / "matrix-results.json").write_text("{}")
            with self.assertRaises(ValueError):
                package(assets)

    def test_public_artifact_hash_exception_does_not_allow_credentials(self):
        root = Path(__file__).resolve().parents[1]
        config = tomllib.loads((root / ".gitleaks.toml").read_text())
        rule = next(r for r in config["rules"] if r["id"] == "generic-api-key")
        allow = rule["allowlists"][0]
        self.assertEqual(allow["condition"], "AND")
        self.assertEqual(allow["regexTarget"], "match")
        path = "docs/assets/model-engine-standard/evaluation-profiles/definitions/example.yaml"
        def allowed(path, line):
            return any(re.search(p, path) for p in allow["paths"]) and any(
                re.search(p, line) for p in allow["regexes"])
        self.assertTrue(allowed(path, "tokenizerRevision: " + "a" * 40))
        self.assertTrue(allowed(path, "tokenizerSha256: " + "a" * 64))
        self.assertTrue(allowed(path, 'tokenizerRevision": "' + "a" * 40 + '"'))
        self.assertFalse(allowed(path, "api_key: " + "a" * 40))
        self.assertFalse(allowed(path, "tokenizerRevision: not-a-model-revision"))
        self.assertFalse(allowed("docs/internal/example.yaml", "tokenizerRevision: " + "a" * 40))
        allow = rule["allowlists"][1]
        catalog = "docs/assets/model-engine-standard/catalog-registration.json"
        self.assertTrue(allowed(catalog, 'tokenizerSha256": "' + "a" * 64 + '"'))
        self.assertFalse(allowed(catalog, "api_key: " + "a" * 64))
        self.assertFalse(allowed(catalog, "tokenizerSha256: not-a-content-hash"))
        self.assertFalse(allowed("docs/internal/catalog-registration.json", "tokenizerSha256: " + "a" * 64))



class CatalogRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.assets = Path(__file__).resolve().parents[1] / "docs/assets/model-engine-standard"
        self.plan = json.loads((self.assets / "catalog-registration.json").read_text())
        self.summary = json.loads((self.assets / "matrix-results.json").read_text())

    def test_registration_matches_current_models_versions_and_limits(self):
        validate_registration_plan(self.assets, self.plan, self.summary)

    def test_proposal_cannot_silently_promote_or_become_installable(self):
        for change in ("state", "availability"):
            plan = copy.deepcopy(self.plan)
            if change == "state":
                next(t for m in plan["models"] for t in m["tuples"]
                     if t["state"] == "candidate")["state"] = "validated"
            else:
                plan["canUsePublicInstallerNow"] = True
            with self.assertRaises(ValueError):
                validate_registration_plan(self.assets, plan, self.summary)

    def test_identity_drift_and_successful_subset_are_rejected(self):
        for change in ("version", "counts", "finding"):
            plan = copy.deepcopy(self.plan)
            if change == "version":
                plan["models"][0]["tuples"][0]["engineVersion"] = "0.28.0"
            elif change == "counts":
                plan["installerValidation"]["successfulInstalls"] -= 1
            else:
                plan["integrationFindings"].pop()
            with self.assertRaises(ValueError):
                validate_registration_plan(self.assets, plan, self.summary)


if __name__ == "__main__":
    unittest.main()
