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
