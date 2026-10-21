"""Freeze current recorder labels and reject stale enums or impossible selectors."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from refresh_example_contracts import extract_ai_metric_labels
from validate_examples import ExampleValidator

SOURCE = b'''const (
 AIOutcomeCompleted = "completed"
 AIOutcomeDenied = "denied"
 AIOutcomeAborted = "aborted"
 AICauseClient = "client"
 AICauseEngine = "engine"
 AICauseGateway = "gateway"
)
func pdPhaseLabels(errorPhase int) (phase, status string) {
 switch errorPhase {
 case 0:
  phase = "complete"
  status = "success"
 default:
  phase = "unknown"
  status = "error"
 }
 return phase, status
}
var pdFallbackReasons = map[int]string{
 1: "origin_5xx",
 6: "other",
}
'''


class MetricContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = ExampleValidator(ROOT, False)

    def test_current_request_outcomes_and_causes(self):
        for outcome, cause in (("completed", ""), ("denied", ""),
                               ("aborted", "client"), ("aborted", "engine"),
                               ("aborted", "gateway")):
            with self.subTest(outcome=outcome, cause=cause):
                query = f'loxilb_ai_requests_total{{outcome="{outcome}",cause="{cause}"}}'
                self.assertEqual([], self.validator.validate_promql(query))

    def test_current_pd_pairs_and_new_metric_families(self):
        pairs = (("complete", "success"), ("prefill", "timeout"), ("prefill", "error"),
                 ("prefill", "rejected"), ("decode", "error"), ("decode", "timeout"),
                 ("decode", "rejected"), ("decode", "unknown"), ("decode", "truncated"),
                 ("aborted", "client"), ("unknown", "error"))
        for phase, status in pairs:
            query = f'loxilb_ai_pd_requests_total{{phase="{phase}",status="{status}"}}'
            with self.subTest(query=query):
                self.assertEqual([], self.validator.validate_promql(query))
        self.assertEqual([], self.validator.validate_promql(
            'loxilb_ai_pd_decode_duration_seconds_count'))
        for reason in ("origin_5xx", "origin_408", "origin_429", "no_status", "truncated", "other"):
            self.assertEqual([], self.validator.validate_promql(
                f'loxilb_ai_pd_prefill_fallback_total{{reason="{reason}"}}'))

    def test_invalid_values_and_impossible_pairs_are_rejected(self):
        for query in (
            'loxilb_ai_requests_total{outcome="invented"}',
            'loxilb_ai_requests_total{cause="invented"}',
            'loxilb_ai_requests_total{outcome="completed",cause="engine"}',
            'loxilb_ai_requests_total{outcome="denied",cause="client"}',
            'loxilb_ai_requests_total{outcome="aborted",cause=""}',
            'loxilb_ai_pd_requests_total{phase="complete",status="error"}',
            'loxilb_ai_pd_requests_total{phase="aborted",status="success"}',
            'loxilb_ai_pd_prefill_fallback_total{reason="invented"}',
        ):
            with self.subTest(query=query):
                self.assertTrue(self.validator.validate_promql(query))

    def test_partial_negative_and_regex_selectors_keep_valid_combinations(self):
        for query in (
            'loxilb_ai_requests_total{cause="engine"}',
            'loxilb_ai_requests_total{outcome!="completed",cause="engine"}',
            'loxilb_ai_requests_total{outcome="aborted",cause=~"engine|gateway"}',
            'loxilb_ai_pd_requests_total{phase="decode",status!~"success|client"}',
        ):
            self.assertEqual([], self.validator.validate_promql(query))
        self.assertTrue(self.validator.validate_promql(
            'loxilb_ai_requests_total{outcome="completed",cause=~"engine|gateway"}'))
        self.assertTrue(self.validator.validate_promql(
            'loxilb_ai_pd_requests_total{status=~"["}'))

    def test_extractor_uses_source_and_records_its_identity(self):
        result = extract_ai_metric_labels(SOURCE)
        self.assertEqual(["", "client", "engine", "gateway"],
                         result["label_enums"]["loxilb_ai_requests_total"]["cause"])
        self.assertEqual(["origin_5xx", "other"],
                         result["label_enums"]["loxilb_ai_pd_prefill_fallback_total"]["reason"])
        changed = extract_ai_metric_labels(SOURCE.replace(b'"origin_5xx"', b'"new_reason"'))
        self.assertIn("new_reason", changed["label_enums"]["loxilb_ai_pd_prefill_fallback_total"]["reason"])
        self.assertNotEqual(result["label_source"]["sha256"], changed["label_source"]["sha256"])

    def test_changed_declaration_shapes_fail_closed(self):
        for source in (
            SOURCE.replace(b'AIOutcomeAborted', b'AnotherOutcome'),
            SOURCE.replace(b'status = "error"', b'status = computedStatus()'),
            SOURCE.replace(b'1: "origin_5xx"', b'1: computedReason()'),
            SOURCE.replace(b'func pdPhaseLabels', b'func renamedLabels'),
        ):
            with self.assertRaises(ValueError):
                extract_ai_metric_labels(source)

    def test_current_endpoint_annotation_is_not_a_new_operation(self):
        specs = self.validator.gateway_contract["specs"]
        main = next(spec for spec in specs if spec["source_path"] == "api/swagger.yml")
        endpoint = main["definitions"]["EndPointHostState"]["properties"]["epPort"]
        self.assertEqual("integer", endpoint["type"])
        self.assertIs(False, endpoint["x-nullable"])
        self.assertEqual((0, 65535), (endpoint["minimum"], endpoint["maximum"]))
