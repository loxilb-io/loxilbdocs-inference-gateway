"""Keep operator navigation, visible topology and readable command steps aligned."""
from pathlib import Path
import sys
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from validate_examples import markdown_blocks

FAMILIES = (
    'Traffic Governance Use-Cases',
    'Shared Inference Use-Cases',
    'Edge Cloud Security Use-Cases',
    'LLM Integration Use-Cases',
)
PHASES = ['1. Overview & Topology', '2. Preparation', '3. Walkthroughs', '4. Verification & Cleanup']


class UseCaseReadabilityTests(unittest.TestCase):
    def test_every_family_uses_the_same_reading_phases(self):
        config = yaml.load((ROOT / 'mkdocs.yml').read_text(), Loader=yaml.BaseLoader)
        nav = {key: value for item in config['nav'] for key, value in item.items()}
        for family in FAMILIES:
            with self.subTest(family=family):
                self.assertEqual(PHASES, [key for item in nav[family] for key in item])
                overview = nav[family][0][PHASES[0]]
                self.assertTrue((ROOT / 'docs' / overview).is_file())
                self.assertIn('Topology and execution locations', (ROOT / 'docs' / overview).read_text())

    def test_operator_chapters_show_execution_locations_and_exit_path(self):
        pages = [p for family in ['admission-flow-control', 'shared-inference', 'edge-cloud-security']
                 for p in (ROOT / 'docs/use-cases' / family).glob('*.md')]
        pages += [ROOT / 'docs/use-cases/model-engine-standard' / (name + '.md')
                  for name in ['select', 'prepare', 'launch', 'configure', 'verify', 'lifecycle']]
        for page in pages:
            with self.subTest(page=page.name):
                source = page.read_text()
                for heading in ['Before you start', 'Topology and execution locations', 'Check your result', 'Next steps and cleanup']:
                    self.assertIn('## ' + heading, source)
                diagrams = any(block.language == 'mermaid' for block in markdown_blocks(page))
                for target in re.findall(r'--8<-- "([^"]+)"', source):
                    snippet = ROOT / target
                    self.assertTrue(snippet.is_file(), target)
                    diagrams = diagrams or any(block.language == 'mermaid' for block in markdown_blocks(snippet))
                self.assertTrue(diagrams, 'The chapter needs a local or canonical topology diagram.')

    def test_use_case_shell_boxes_remain_small(self):
        for page in (ROOT / 'docs/use-cases').rglob('*.md'):
            for block in markdown_blocks(page):
                if block.language == 'bash':
                    with self.subTest(page=page.name, line=block.line):
                        self.assertLessEqual(len(block.text.splitlines()), 50,
                            'Explain and split at complete command boundaries; keep a compound statement intact.')


if __name__ == '__main__':
    unittest.main()
