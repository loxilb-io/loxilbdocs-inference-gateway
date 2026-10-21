"""Regression checks for documentation contracts; execute on Linux QA runners."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from refresh_example_contracts import compact_swagger, completion_contract
from validate_examples import ExampleValidator
from compare_gateway_contracts import compare_contracts


class DocumentationGapRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = ExampleValidator(ROOT)

    def test_unknown_short_option_rejected(self):
        self.assertTrue(self.validator.validate_cli_command('loxicmd get ready -Z'))

    def test_missing_option_value_rejected(self):
        self.assertTrue(self.validator.validate_cli_command('loxicmd create lb 192.0.2.10 --mode'))
        self.assertTrue(self.validator.validate_cli_command('loxicmd get ready --apiserver'))

    def test_persistent_flags_before_command_accepted(self):
        self.assertEqual([], self.validator.validate_cli_command(
            'loxicmd --apiserver gateway.example.com --port 443 --protocol https get ready'))
        self.assertEqual([], self.validator.validate_cli_command('loxicmd -s gateway.example.com get ready'))

    def test_management_variable_routes_fail_closed(self):
        for prefix in ('$CONTROL_API', '${CONTROL_API}', '$GATEWAY_API', '${GATEWAY_API}'):
            route = self.validator._management_route(prefix + '/config/not-real')
            self.assertEqual('/config/not-real', route)
            self.assertTrue(self.validator.validate_route('GET', route))

    def test_response_and_security_retained_without_raw_hash_oracle(self):
        spec = b'''swagger: '2.0'
security:
  - bearer: []
paths:
  /status/ready:
    get:
      responses:
        200:
          description: Ready
          schema: {type: object}
        default:
          description: Failure
'''
        compact = compact_swagger(spec, 'api/swagger.yml')
        operation = compact['paths']['/status/ready']['get']
        self.assertEqual({'type': 'object'}, operation['responses']['200']['schema'])
        self.assertEqual([{'bearer': []}], operation['security'])
        changed = compact_swagger(spec.replace(b'type: object', b'type: string'), 'api/swagger.yml')
        self.assertNotEqual(operation, changed['paths']['/status/ready']['get'])

    def test_verification_page_matches_frozen_tuple_and_count(self):
        gateway = json.loads((ROOT / 'tests/contracts/docs_examples/gateway-api.json').read_text())
        cli = json.loads((ROOT / 'tests/contracts/docs_examples/cli.json').read_text())
        page = (ROOT / 'docs/reference/verification-status.md').read_text()
        self.assertIn(gateway['source']['commit'], page)
        self.assertIn(gateway['source']['ebpf_submodule_commit'], page)
        self.assertIn(cli['source']['main_commit'], page)
        count = len(gateway['metric_manifest']['families'])
        self.assertIn(f'all {count} families', page)

    def test_schema_defaults_preserve_object_values(self):
        from refresh_example_contracts import compact_schema
        self.assertEqual({'default': {'custom': 1}, 'x-nullable': True},
            compact_schema({'default': {'custom': 1}, 'x-nullable': True}))
