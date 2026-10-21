"""Prevent publication of withdrawn operating controls and stale gate commands."""
from pathlib import Path
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_examples import public_markdown_paths, markdown_blocks, extract_shell_commands

class PublicationScope(unittest.TestCase):
    def test_no_withdrawn_controls_or_product_fix_instructions(self):
        denied=re.compile(r'release[- ]block(?:ed|er)|currently inert|zero placeholders|'
            r'client_ca_cert_data|chwbl_(?:prefix_hash_level|prefix_hash_flags|mean_load_factor|replication|enable_cache_salt)|'
            r'hard-coded.{0,40}(?:admin|key)|exposes stored password',re.I)
        for path in public_markdown_paths(ROOT):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(denied.search(path.read_text()))

    def test_warmup_is_only_removed_from_retained_snapshot(self):
        for path in public_markdown_paths(ROOT):
            for line in path.read_text().splitlines():
                if 'kvWarmupSec' in line:
                    self.assertIn('del(.serviceArguments.kvWarmupSec)',line,str(path))
                self.assertNotIn('--kv-warmup',line,str(path))

    def test_contributor_candidate_gate_requires_both_repositories(self):
        seen=False
        for block in markdown_blocks(ROOT/'docs/community/contributing.md'):
            if 'python tools/validate_gateway_docs.py' in block.text:
                for flag in ('--gateway-repo','--gateway-ref','--cli-repo','--cli-ref'):
                    self.assertIn(flag,block.text)
                seen=True
        self.assertTrue(seen)

    def test_operational_cli_targets_include_tls_and_endpoint(self):
        for name in ('backup-restore.md','readiness-diagnostics-maintenance.md'):
            for block in markdown_blocks(ROOT/'docs/operations'/name):
                for command in extract_shell_commands(block.text,'loxicmd'):
                    for flag in ('--protocol','--apiserver','--port','--cacert'):
                        self.assertIn(flag,command,f'{name}:{block.line}')

    def test_withdrawn_dpu_operations_are_not_published(self):
        self.assertFalse((ROOT/'docs/operations/dpu-offload.md').exists())
        for directory in ('management', 'operations', 'reference'):
            for path in (ROOT/'docs'/directory).glob('*.md'):
                with self.subTest(path=path.name):
                    self.assertIsNone(re.search(r'DPU Offload|dpu-offload|/config/dpu/|doca_pipe_', path.read_text(), re.I))
        self.assertNotIn('dpu-offload.md', (ROOT/'mkdocs.yml').read_text())

    def test_management_installation_keeps_separate_service_identity(self):
        text = (ROOT/'docs/management/management-plane.md').read_text()
        for required in ('deploy/compose/README.md', 'docker-compose.prod.yml',
                         'config --quiet', 'OAM_GATEWAY_AUTH_MODE=service-token',
                         'OAM_GATEWAY_SERVICE_TOKEN_FILE', 'OAM_INSTANCE_TLS_INSECURE=false',
                         '## Mode 1', '## Mode 2', '## Mode 3',
                         'docker-compose.dev.yml up --build',
                         'scripts/init-converged.sh', 'docker-compose.database.yml',
                         'docker-compose.dataplane.yml'):
            self.assertIn(required, text)
        for path in (ROOT/'docs/management').glob('*.md'):
            self.assertIsNone(re.search(r'forwards? the (?:caller.s|request.s) [`]?Authorization', path.read_text(), re.I))

    def test_cli_reference_does_not_publish_unqualified_mcp_tools(self):
        text = (ROOT/'docs/reference/cli.md').read_text()
        for withdrawn in ('ai_apikey_create', 'diagnose_', 'confirm-token', 'MCP (available today)'):
            self.assertNotIn(withdrawn, text)
