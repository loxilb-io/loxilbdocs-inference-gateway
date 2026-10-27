from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "refresh_example_contracts", ROOT / "tools/refresh_example_contracts.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SCENARIO = "cicd/scenario"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def gateway_repo(workflow_body: str) -> tuple[tempfile.TemporaryDirectory, Path]:
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    (repo / SCENARIO).mkdir(parents=True)
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / SCENARIO / "validation.sh").write_text("# case D1\n")
    (repo / SCENARIO / "validation_named.sh").write_text("# case N1\n")
    (repo / SCENARIO / "validation_other.sh").write_text("# case O1\n")
    (repo / ".github/workflows/ci.yml").write_text(workflow_body)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture")
    return tmp, repo


def claim(validation: str, case: str) -> dict:
    return {
        "claim": "fixture",
        "scenario_path": SCENARIO,
        "validation_path": f"{SCENARIO}/{validation}",
        "workflow_path": None,
        "case_ids": [case],
    }


class ClaimEvidenceWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = MODULE.CLAIM_EVIDENCE

    def tearDown(self) -> None:
        MODULE.CLAIM_EVIDENCE = self.original

    def test_another_script_of_the_directory_does_not_wire_a_named_claim(self) -> None:
        tmp, repo = gateway_repo(f"run: cd {SCENARIO} && ./validation_other.sh\n")
        self.addCleanup(tmp.cleanup)
        MODULE.CLAIM_EVIDENCE = (claim("validation_named.sh", "N1"),)
        result = MODULE.build_claim_evidence(repo, "HEAD")["claims"][0]
        self.assertEqual("not-wired", result["workflow_membership"])
        self.assertEqual([], result["matching_workflows"])

    def test_red_twin_a_workflow_running_the_named_script_is_caught(self) -> None:
        tmp, repo = gateway_repo(f"run: cd {SCENARIO} && ./validation_named.sh\n")
        self.addCleanup(tmp.cleanup)
        MODULE.CLAIM_EVIDENCE = (claim("validation_named.sh", "N1"),)
        with self.assertRaisesRegex(ValueError, "unexpectedly wired"):
            MODULE.build_claim_evidence(repo, "HEAD")

    def test_a_default_validation_claim_keeps_the_directory_level_match(self) -> None:
        tmp, repo = gateway_repo(f"run: cd {SCENARIO} && ./validation_other.sh\n")
        self.addCleanup(tmp.cleanup)
        MODULE.CLAIM_EVIDENCE = (claim("validation.sh", "D1"),)
        with self.assertRaisesRegex(ValueError, "unexpectedly wired"):
            MODULE.build_claim_evidence(repo, "HEAD")

    def test_reviewed_workflow_freezes_membership_and_source_objects(self) -> None:
        tmp, repo = gateway_repo(f"run: cd {SCENARIO} && ./validation.sh\n")
        self.addCleanup(tmp.cleanup)
        expected = claim("validation.sh", "D1")
        expected["workflow_path"] = ".github/workflows/ci.yml"
        MODULE.CLAIM_EVIDENCE = (expected,)
        result = MODULE.build_claim_evidence(repo, "HEAD")["claims"][0]
        workflow_oid = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD:.github/workflows/ci.yml"],
            text=True,
        ).strip()
        self.assertEqual("wired", result["workflow_membership"])
        self.assertEqual([expected["workflow_path"]], result["matching_workflows"])
        self.assertEqual(workflow_oid, result["workflow_object_id"])
        self.assertEqual({expected["workflow_path"]: workflow_oid}, result["matching_workflow_objects"])
        self.assertEqual(["D1"], result["case_ids"])

    def test_reviewed_workflow_without_the_scenario_is_rejected(self) -> None:
        tmp, repo = gateway_repo("run: echo unrelated\n")
        self.addCleanup(tmp.cleanup)
        expected = claim("validation.sh", "D1")
        expected["workflow_path"] = ".github/workflows/ci.yml"
        MODULE.CLAIM_EVIDENCE = (expected,)
        with self.assertRaisesRegex(ValueError, "does not invoke"):
            MODULE.build_claim_evidence(repo, "HEAD")

    def test_reviewed_workflow_cannot_hide_a_missing_case(self) -> None:
        tmp, repo = gateway_repo(f"run: cd {SCENARIO} && ./validation.sh\n")
        self.addCleanup(tmp.cleanup)
        expected = claim("validation.sh", "ABSENT")
        expected["workflow_path"] = ".github/workflows/ci.yml"
        MODULE.CLAIM_EVIDENCE = (expected,)
        with self.assertRaisesRegex(ValueError, "missing declared case IDs: ABSENT"):
            MODULE.build_claim_evidence(repo, "HEAD")


if __name__ == "__main__":
    unittest.main()
