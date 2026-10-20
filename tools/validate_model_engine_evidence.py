#!/usr/bin/env python3
"""Validate publication state separately from model/engine runtime verdicts."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def key(row: dict) -> tuple[str, str, str]:
    return row["modelKey"], row["engine"], row["mode"]


def validate_runtime_evidence(matrix: dict, summary: dict | None,
                              ledger: dict | None) -> None:
    """Pending is valid configuration coverage, never a runtime PASS.

    Published evidence must reconcile verdicts, completed samples and independent
    receipts. Absence is allowed only by the explicit pending publication contract.
    """
    publication = matrix["runtimeEvidencePublication"]
    require(publication["scope"] == "standard-card", "unexpected evidence scope")
    state = publication["status"]
    require(state in ("pending", "published"), "unknown evidence publication state")
    require(publication["summary"] == "matrix-results.json", "unexpected summary path")
    require(publication["requestLedger"] == "matrix-request-ledger.json",
            "unexpected ledger path")
    entries = [e for e in matrix["entries"] if e["scope"] == "standard-card"]
    require(len({key(e) for e in entries}) == len(entries), "duplicate matrix case")
    if state == "pending":
        require(summary is None and ledger is None,
                "pending publication must not include unreviewed result files")
        require(all(e["currentPublicTupleRuntime"] == "not-run" for e in entries),
                "pending publication cannot claim an executed verdict")
        require(all(not e.get("evidenceSummary") for e in entries),
                "pending cases cannot reference runtime evidence")
        return

    require(isinstance(summary, dict) and isinstance(ledger, dict),
            "published evidence requires both summary and request ledger")
    require(summary["catalogPromotion"] is False, "runtime QA cannot promote support")
    require("open" in summary["historicalGemmaLoadFailure"],
            "historical Gemma failure must remain open")
    rows = summary["cases"]
    require(len(rows) == len(entries) and len({key(r) for r in rows}) == len(rows)
            and {key(r) for r in rows} == {key(e) for e in entries},
            "runtime cases must cover each standard-card mode exactly once")
    require(len({r["caseId"] for r in rows}) == len(rows), "duplicate runtime case ID")
    require(summary["counts"] == dict(Counter(r["result"] for r in rows)),
            "verdict counts do not reconcile")
    by_id = {r["caseId"]: r for r in rows}
    indexed = {key(e): e for e in entries}
    observed = {"normal", "offered", "workerReceipts", "rawResultSha256", "engineVersion",
                "engineImageDigest", "receiptHashAudit", "enforcedState", "cacheHitDelta",
                "invalidMutationNoChange", "configuredServiceAndEndpointsUnchanged",
                "scopedRuleDeletion", "coldNormal", "coldReceiptHashAudit", "goFenced"}
    for row in rows:
        case = row["caseId"]
        entry = indexed[key(row)]
        verdict = row["result"]
        require(verdict == entry["currentPublicTupleRuntime"],
                f"{case}: matrix/runtime verdict mismatch")
        require(entry["evidenceSummary"] == publication["summary"],
                f"{case}: matrix must reference the published summary")
        require(row["configuration"] == f"matrix-configurations/{case}.json",
                f"{case}: configuration identity mismatch")
        require(case == "-".join(key(row)), f"{case}: case identity mismatch")
        require(bool(row["remainingGates"]), f"{case}: remaining gates required")
        if verdict == "NOT_RUN":
            require(row["inferenceAttempted"] is False and not observed.intersection(row),
                    f"{case}: unrun case contains observed results")
            continue
        require(verdict in ("PASS_BOUNDED_FUNCTIONAL", "BLOCKED_NATIVE_ARCHITECTURE",
                            "FAIL_TRAFFIC_OR_ROUTING", "FAIL_ATTESTATION"),
                f"{case}: unreviewed runtime verdict")
        require(re.fullmatch(r"[0-9a-f]{64}", row["rawResultSha256"]) is not None,
                f"{case}: raw result hash required")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", row["engineImageDigest"]) is not None,
                f"{case}: immutable engine digest required")
        require(bool(row["engineVersion"]), f"{case}: observed engine version required")
        if verdict == "BLOCKED_NATIVE_ARCHITECTURE":
            require(row["engine"] == "trtllm" and row["modelKey"] in ("gemma2", "exaone35")
                    and row["inferenceAttempted"] is False and "normal" not in row
                    and bool(entry["blockers"]), f"{case}: invalid architecture block")
        elif verdict.startswith("FAIL_"):
            require(bool(row["failureSummary"]), f"{case}: failure explanation required")
        else:
            normal = row["normal"]
            require(type(normal) is int and normal > 0 and type(row["offered"]) is int
                    and row["offered"] == normal, f"{case}: incomplete offered workload")
            counts = row["workerReceipts"]
            require(bool(counts) and all(type(n) is int and n >= 0 for n in counts.values())
                    and sum(counts.values()) == normal, f"{case}: worker count mismatch")
            require(row["receiptHashAudit"] == "pass"
                    and row["invalidMutationNoChange"] is True
                    and row["configuredServiceAndEndpointsUnchanged"] is True
                    and row["scopedRuleDeletion"] == "absent",
                    f"{case}: completion/lifecycle evidence required")
            if row["mode"] == "exact":
                require(row["enforcedState"] == "READY" and row["reasonCodes"] == []
                        and row["goFenced"] is False and row["cacheHitDelta"] >= normal
                        and type(row["coldNormal"]) is int and row["coldNormal"] > 0
                        and row["coldReceiptHashAudit"] == "pass",
                        f"{case}: Exact readiness/cold comparator evidence required")

    records = ledger["records"]
    require(len({r["requestId"] for r in records}) == len(records), "duplicate request ID")
    require(len({(r["caseId"], r["sample"]) for r in records}) == len(records),
            "duplicate case/sample")
    require(ledger["counts"] == dict(Counter(r["caseId"] for r in records)),
            "ledger counts do not reconcile")
    for record in records:
        require(record["caseId"] in by_id
                and by_id[record["caseId"]]["result"] == "PASS_BOUNDED_FUNCTIONAL",
                "normal receipt belongs to an unknown or non-PASS case")
        require(re.fullmatch(r"(?:main|cold)-[0-9]+", record["sample"]) is not None,
                "invalid receipt sample")
        for client, backend in (("requestSha256", "backendRequestSha256"),
                                ("responseSha256", "backendResponseSha256")):
            require(re.fullmatch(r"[0-9a-f]{64}", record[client]) is not None
                    and record[client] == record[backend], "client/backend hash mismatch")
        require(record["normalCompletion"] is True and record["backendUpstreamComplete"] is True,
                "incomplete request/response")
        require(record["worker"] in ("workerA", "workerB", "workerC"), "invalid worker alias")
        require(type(record["stream"]) is bool, "stream must be boolean")
        require((type(record["sseDoneCount"]) is int and record["sseDoneCount"] == 1) if record["stream"]
                else record["sseDoneCount"] is None, "invalid SSE terminal count")
    for row in rows:
        main = [r for r in records if r["caseId"] == row["caseId"]
                and r["sample"].startswith("main-")]
        cold = [r for r in records if r["caseId"] == row["caseId"]
                and r["sample"].startswith("cold-")]
        passed = row["result"] == "PASS_BOUNDED_FUNCTIONAL"
        require(len(main) == (row["normal"] if passed else 0)
                and len(cold) == (row.get("coldNormal", 0) if passed else 0),
                f'{row["caseId"]}: sample counts do not reconcile')
        if passed:
            # Earlier summaries use prewarmedWorkerA for the same sanitized worker alias.
            expected = {k.replace("prewarmedWorker", "worker"): v
                        for k, v in row["workerReceipts"].items() if v}
            require(dict(Counter(r["worker"] for r in main)) == expected,
                    f'{row["caseId"]}: independent worker distribution mismatch')


def validate_package(assets: Path) -> tuple[dict, dict | None, dict | None]:
    matrix = json.loads((assets / "qualification-matrix.json").read_text())
    summary_path = assets / "matrix-results.json"
    ledger_path = assets / "matrix-request-ledger.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else None
    validate_runtime_evidence(matrix, summary, ledger)
    if summary is not None:
        for row in summary["cases"]:
            require((assets / row["configuration"]).is_file(), "missing case configuration")
    return matrix, summary, ledger


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path,
                        default=Path(__file__).resolve().parents[1] / "docs/assets/model-engine-standard")
    args = parser.parse_args()
    try:
        matrix, _, _ = validate_package(args.assets)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f'PASS: evidence publication contract valid ({matrix["runtimeEvidencePublication"]["status"]}); '
          'this does not establish runtime qualification')
