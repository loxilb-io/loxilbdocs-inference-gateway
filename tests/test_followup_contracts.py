from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from refresh_body_bindings import load_bound_bodies, OUTPUT, CONFIGURE
from validate_response_contracts import validate
from refresh_coverage_ledger import document
from validate_examples import ExampleValidator

class FollowupContracts(unittest.TestCase):
    def test_response_red_twins(self):
        expected={'status':422,'schema':{'type':'object','required':['code'],
            'properties':{'code':{'enum':[606]}}},'unchanged':True,'receipt_delta':0}
        good={'status':422,'body':{'code':606},'before':[1],'after':[1],
              'receipt_delta':0,'executed':True}
        self.assertEqual([],validate(expected,good))
        for change in ({'status':400},{'body':{'code':400}},{'after':[]},
                       {'receipt_delta':1},{'executed':False}):
            self.assertTrue(validate(expected,{**good,**change}))

    def test_exact_body_path_and_all_assets(self):
        bodies=load_bound_bodies(ROOT,Path(CONFIGURE),'@$RUN/model-engine-gateway.json')
        self.assertEqual(30,len(bodies))
        with self.assertRaisesRegex(ValueError,'unbound'):
            load_bound_bodies(ROOT,Path(CONFIGURE),'@/unrelated/model-engine-gateway.json')

    def test_changed_producer_asset_or_body_fails(self):
        from shutil import copy2
        baseline=json.loads((ROOT/OUTPUT).read_text())
        for target in ('producer','asset','body'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                for producer in baseline['producers'].values():
                    file=root/producer['page'];file.parent.mkdir(parents=True,exist_ok=True)
                    copy2(ROOT/producer['page'],file)
                for row in baseline['records']:
                    file=root/row['asset'];file.parent.mkdir(parents=True,exist_ok=True)
                    copy2(ROOT/row['asset'],file)
                current=copy.deepcopy(baseline)
                if target=='producer':
                    path=root/CONFIGURE;path.write_text(path.read_text().replace('jq --arg v','jq --arg wrong'))
                elif target=='asset':(root/current['records'][0]['asset']).write_text('{}')
                else:current['records'][0]['bodies']['model-engine-gateway.json']['body']={}
                path=root/OUTPUT;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(current))
                with self.assertRaises(ValueError):load_bound_bodies(root,Path(CONFIGURE),'@$RUN/model-engine-gateway.json')

    def test_coverage_matches_every_fence_and_records_missing_operations(self):
        value=document(ROOT)
        self.assertEqual(244,len(value['operations']))
        self.assertTrue(value['summary']['operations_without_direct_examples']>0)
        self.assertEqual(value['summary']['fences'],len(value['examples']))
        self.assertTrue(all(row['runtime']=='no-public-execution-attestation' for row in value['examples']))

    def test_relative_token_path_is_rejected(self):
        errors=ExampleValidator(ROOT,False).validate_cli_command('loxicmd get ready --token-file ./gateway.token')
        self.assertTrue(any('absolute' in error for error in errors))
