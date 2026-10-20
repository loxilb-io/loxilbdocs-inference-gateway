"""Validate the security tutorial inputs and observation failure contracts."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from validate_examples import ExampleValidator, markdown_blocks, extract_shell_commands

PAGES = ROOT / 'docs/use-cases/edge-cloud-security'
ASSETS = ROOT / 'docs/assets/edge-cloud-security'


class EdgeSecurityExamplesTests(unittest.TestCase):
    def test_assets_match_schema_and_inline_inputs(self):
        validator = ExampleValidator(ROOT)
        manifest = json.loads((ASSETS / 'manifest.json').read_text())
        self.assertEqual(set(manifest['examples']), {p.name for p in (ASSETS / 'examples').glob('*.json')})
        for name, operation in manifest['examples'].items():
            payload = json.loads((ASSETS / 'examples' / name).read_text())
            route = operation['route'].replace('{key_id}', 'example-key-id')
            self.assertEqual(validator.validate_json_body(operation['method'], route, payload), [], name)
        inline = 0
        for page in PAGES.glob('*.md'):
            source = page.read_text()
            for match in re.finditer(r'cat > "\$LAB/([^"\n]+)" <<\'JSON\'\n(.*?)\nJSON', source, re.S):
                name, text = match.groups()
                self.assertIn(name, manifest['examples'], f'{page.name}: {name}')
                self.assertEqual(json.loads(text), json.loads((ASSETS / 'examples' / name).read_text()))
                inline += 1
        self.assertEqual(inline, len(manifest['examples']))
        bad = json.loads((ASSETS / 'examples/rate-source.json').read_text())
        del bad['synEnabled']
        self.assertTrue(validator.validate_json_body('POST', '/config/securityrate', bad))

    def test_shell_links_address_and_secret_hygiene(self):
        validator = ExampleValidator(ROOT)
        self.assertEqual(len(list(PAGES.glob('*.md'))), 12)
        for page in PAGES.glob('*.md'):
            source = page.read_text()
            self.assertFalse(validator.private_example_addresses(source), page)
            self.assertNotRegex(source, r'/Use[r]s/|ssh\s+loxilb-|docs/intern[a]l/')
            self.assertNotRegex(source, r'-H\s+[\'"](?:Authorization: Bearer|X-Api-Key:)\s*\$')
            for block in markdown_blocks(page):
                if block.language == 'bash':
                    checked = subprocess.run(['bash', '-n'], input=block.text, text=True, capture_output=True)
                    self.assertEqual(checked.returncode, 0, f'{page}:{block.line}: {checked.stderr}')
            for link in re.findall(r'\]\(([^)]+)\)', source):
                if '://' not in link and not link.startswith('#'):
                    self.assertTrue((page.parent / link.split('#', 1)[0]).exists(), f'{page.name}: {link}')

    def test_documented_management_routes(self):
        validator = ExampleValidator(ROOT)
        routes = 0
        for page in PAGES.glob('*.md'):
            for block in markdown_blocks(page):
                if block.language != 'bash':
                    continue
                for command in extract_shell_commands(block.text.replace('$API', '$CONTROL_API'), 'curl'):
                    method, url, body = validator._curl_details(command)
                    route = validator._management_route(url)
                    if route is not None:
                        self.assertEqual(validator.validate_route(method, route), [], f'{page.name}: {route}')
                        routes += 1
        self.assertGreater(routes, 80)

    def test_download_integrity(self):
        import hashlib
        expected = {}
        for line in (ASSETS / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertNotIn('..', Path(name).parts)
            expected[name] = digest
        actual = {str(p.relative_to(ASSETS)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in ASSETS.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
        self.assertEqual(expected, actual)

    def test_counter_helper_rejects_missing_nonfinite_and_reset(self):
        spec = importlib.util.spec_from_file_location('edge_metric_delta', ASSETS / 'metric-delta.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / 'sample.prom'
            file.write_text('counter{source="a"} 2\ncounter{source="b"} 3\nother 9\n')
            self.assertEqual(module.total(file, 'counter'), 5)
            with self.assertRaises(ValueError):
                module.total(file, 'absent')
            for value in ('NaN', '+Inf', '-1'):
                file.write_text(f'counter {value}\n')
                with self.assertRaises(ValueError):
                    module.total(file, 'counter')
            file.write_text('counter{source="a"} 1e308\ncounter{source="b"} 1e308\n')
            with self.assertRaises(ValueError):
                module.total(file, 'counter')
            before, after = Path(temporary) / 'before', Path(temporary) / 'after'
            before.write_text('counter 5\n')
            for value, expected in ((4, 1), (5, 1), (7, 0)):
                after.write_text(f'counter {value}\n')
                result = subprocess.run([sys.executable, str(ASSETS / 'metric-delta.py'), str(before), str(after), 'counter'], capture_output=True)
                self.assertEqual(result.returncode, expected)


if __name__ == '__main__':
    unittest.main()
