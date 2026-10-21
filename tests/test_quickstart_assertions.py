"""Run actual documentation assertions against controlled failure twins."""
from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class QuickstartAssertions(unittest.TestCase):
    def test_retry_exhaustion_returns_failure(self):
        source=(ROOT/'docs/getting-started/installation.md').read_text()
        body=next(block for block in re.findall(r'```bash\n(.*?)```',source,re.S)
                  if 'api_live=false' in block)
        body=body.replace("<host>", "127.0.0.1")
        # Stub only external effects; execute the documented loop and assertion.
        stub='curl() { return 22; }; sleep() { :; }; export -f curl sleep\n'
        failed=subprocess.run(['bash','-c',stub+body],capture_output=True,text=True)
        self.assertNotEqual(0,failed.returncode)
        stub='curl() { return 0; }; sleep() { :; }; export -f curl sleep\n'
        passed=subprocess.run(['bash','-c',stub+body],capture_output=True,text=True)
        self.assertEqual(0,passed.returncode,passed.stderr)

    def test_state_comparison_ignores_order_and_counters_but_detects_mutation(self):
        source=(ROOT/'snippets/getting-started/04-create.md').read_text()
        function=re.search(r'canonical_rules\(\) \{\n.*?\n\}',source,re.S).group()
        a={'serviceArguments':{'externalIP':'192.0.2.10','port':2020,'protocol':'tcp','model_name':'llama-70b'},
           'endpoints':[{'endpointIP':'198.51.100.11','targetPort':8080,'weight':1,'counter':1}]}
        b=json.loads(json.dumps(a));b['serviceArguments']['port']=2021
        reordered=json.loads(json.dumps(a));reordered['endpoints'][0]['counter']=99
        changed=json.loads(json.dumps(a));changed['endpoints'][0]['weight']=2
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            values=({'lbAttr':[a,b]}, {'lbAttr':[b,reordered]}, {'lbAttr':[b,changed]})
            outputs=[]
            for i,value in enumerate(values):
                file=path/str(i);file.write_text(json.dumps(value))
                result=subprocess.run(['bash','-c',function+'\ncanonical_rules "$1"','qa',str(file)],
                                      check=True,capture_output=True,text=True)
                outputs.append(result.stdout)
            self.assertEqual(outputs[0],outputs[1])
            self.assertNotEqual(outputs[0],outputs[2])
