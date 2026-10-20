"""Check the public admission lab without a Gateway or private infrastructure.

Resolve file-backed API bodies by evaluating only literal jq filters, never
shell commands. Host paths, subjects and PEM are inert representative values.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from validate_examples import ExampleValidator, extract_shell_commands, markdown_blocks

PAGES = ROOT / 'docs/use-cases/admission-flow-control'
ASSETS = ROOT / 'docs/assets/admission-flow-control'
CONTRACT = Path(os.environ['ADMISSION_CONTRACT_DIR']) if os.environ.get('ADMISSION_CONTRACT_DIR') else None
ORDER = ('setup', 'identity', 'tls', 'quotas', 'defaults', 'outages', 'capacity', 'tls-failures', 'cleanup')


class AdmissionExamplesTests(unittest.TestCase):
    def test_shell_json_addresses_and_asset_schema(self):
        validator = ExampleValidator(ROOT, contract_dir=CONTRACT)
        for page in PAGES.glob('*.md'):
            self.assertFalse(validator.private_example_addresses(page.read_text()), page)
            for block in markdown_blocks(page):
                with self.subTest(page=page.name, line=block.line):
                    if block.language == 'bash':
                        result = subprocess.run(['bash', '-n'], input=block.text, text=True, capture_output=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    elif block.language == 'json':
                        body = json.loads(block.text)
                        self.assertEqual(validator.validate_json_body('POST', '/config/loadbalancer', body), [])
        assets = list((ASSETS / 'examples').glob('*.json'))
        self.assertEqual(len(assets), 19)
        for path in assets:
            body = json.loads(path.read_text())
            if 'serviceArguments' in body:
                self.assertEqual(validator.validate_json_body('POST', '/config/loadbalancer', body), [], path)
                self.assertEqual(body['serviceArguments']['mode'], 4)
                self.assertEqual(body['serviceArguments']['api_key_auth'], 'jwt')
            else:
                self.assertIn(body['model'], ('llama-70b', 'mistral-7b'))
                self.assertIn('messages', body)

    def test_documented_management_routes_and_file_bodies(self):
        validator = ExampleValidator(ROOT, contract_dir=CONTRACT)
        bodies = {p.name: json.loads(p.read_text()) for p in (ASSETS / 'examples').glob('*.json')}
        # These are saved GET bodies, not hand-written new policies.
        bodies['vip-default-before.json'] = {
            'scope': 'rule', 'rule_ident': '192.0.2.254:2061', 'vip_shared_rps': 100, 'vip_shared_tpm': 10}
        bodies['defaults-restore.json'] = {'scope': 'global', 'default_user_rps': 1}
        routes = file_bodies = generated = 0
        for name in ORDER:
            for block in markdown_blocks(PAGES / (name + '.md')):
                if block.language != 'bash':
                    continue
                # jq producers appear before the API call that consumes the file.
                for command in extract_shell_commands(block.text, 'jq'):
                    flat = re.sub(r'\\\n\s*', ' ', command)
                    if not flat.startswith('jq ') or ' > ' not in flat:
                        continue
                    try:
                        tokens = shlex.split(flat)
                    except ValueError:
                        continue
                    if '>' not in tokens:
                        continue
                    end = tokens.index('>')
                    output = Path(tokens[end + 1]).name
                    if not output.endswith('.json') or output.endswith('.claims.json') or '|' in tokens[:end]:
                        continue
                    args = []
                    positional = []
                    index = 1
                    while index < end:
                        token = tokens[index]
                        if token in ('--arg', '--rawfile'):
                            args.extend(['--arg', tokens[index + 1],
                                         'http://idp.example.test/realms/aigw' if tokens[index + 1] == 'iss'
                                         else 'representative-subject-or-pem'])
                            index += 3
                        elif token == '-n':
                            args.append('-n')
                            index += 1
                        elif token.startswith('-'):
                            args.append(token)
                            index += 1
                        else:
                            positional.append(token)
                            index += 1
                    if not positional or positional[0].startswith('$'):
                        continue  # observation, not a producer
                    input_body = None
                    if len(positional) > 1:
                        basename = Path(positional[1]).name
                        self.assertIn(basename, bodies, f'{name}: unresolved jq input {basename}')
                        input_body = json.dumps(bodies[basename])
                    result = subprocess.run(['jq', *args, positional[0]], input=input_body,
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, f'{name}: {result.stderr}')
                    bodies[output] = json.loads(result.stdout)
                    generated += 1
                for command in extract_shell_commands(block.text.replace('$API', '$CONTROL_API'), 'curl'):
                    method, url, body = validator._curl_details(command)
                    route = validator._management_route(url)
                    if route is None:
                        continue
                    # jq command substitutions produce a single path segment;
                    # schema matching must not mistake their source-file slash for a segment.
                    route = re.sub(r'\$\(.*?(?:\)|$)', 'representative-id', route)
                    self.assertEqual(validator.validate_route(method, route), [], f'{name}: {route}')
                    routes += 1
                    if body is None:
                        continue
                    if body.startswith('@'):
                        basename = Path(body[1:]).name
                        self.assertIn(basename, bodies, f'{name}: missing body {basename}')
                        payload = bodies[basename]
                        file_bodies += 1
                    else:
                        payload = json.loads(body)
                    self.assertEqual(validator.validate_json_body(method, route, payload), [],
                                     f'{name}: {method} {route}')
        self.assertGreater(routes, 180)
        self.assertGreater(file_bodies, 45)
        self.assertGreater(generated, 25)

    def test_negative_schema_mutation_is_rejected(self):
        validator = ExampleValidator(ROOT, contract_dir=CONTRACT)
        body = json.loads((ASSETS / 'examples/capacity.json').read_text())
        body['serviceArguments']['fc_max_queue_wait_ms'] = -1
        self.assertTrue(validator.validate_json_body('POST', '/config/loadbalancer', body))

    def test_links_and_no_private_source_dependencies(self):
        for page in PAGES.glob('*.md'):
            text = page.read_text()
            self.assertNotRegex(text, r'/Use[r]s/|/ro[o]t/|docs/intern[a]l/|ssh\s+\S+|loxilb-product-\d')
            for link in re.findall(r'\]\(([^)]+)\)', text):
                if '://' in link or link.startswith('#'):
                    continue
                path = link.split('#', 1)[0]
                self.assertTrue((page.parent / path).exists(), f'{page.name}: {link}')


if __name__ == '__main__':
    unittest.main()
