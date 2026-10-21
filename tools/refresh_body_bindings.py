#!/usr/bin/env python3
"""Bind documented file bodies to actual public assets and jq producer commands."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from validate_examples import markdown_blocks, extract_shell_commands

CONFIGURE = 'docs/use-cases/model-engine-standard/configure.md'
VERIFY = 'docs/use-cases/model-engine-standard/verify.md'
LIFECYCLE = 'docs/use-cases/model-engine-standard/lifecycle.md'
OUTPUT = 'tests/contracts/docs_examples/body-bindings.json'

def digest(raw): return hashlib.sha256(raw).hexdigest()

def producer(root, page, output):
    matches = [(block, command) for block in markdown_blocks(root/page)
        for command in extract_shell_commands(block.text, 'jq') if '> ' + output in command]
    if len(matches) != 1: raise ValueError(f'expected one jq producer for {page}:{output}')
    block, command = matches[0]
    return {'page':page, 'block_sha256':digest(block.text.encode()), 'command':command}

def document(root):
    valid = producer(root, CONFIGURE, '"$RUN/model-engine-gateway.json"')
    invalid = producer(root, VERIFY, '"$RUN/invalid-model-engine-rule.json"')
    assets=root/'docs/assets/model-engine-standard'
    records=[]
    with tempfile.TemporaryDirectory(prefix='docs-body-binding-') as temporary:
        run=Path(temporary)
        for asset in sorted((assets/'matrix-configurations').glob('*.json')):
            model, engine, mode = asset.stem.split('-')
            env={**os.environ,'RUN':str(run),'PACKAGE':str(assets),'MODEL_KEY':model,
                'ENGINE':engine,'ROUTING_MODE':mode,'VIP':'192.0.2.10','PORT':'2020',
                'WORKER1':'198.51.100.11','WORKER2':'198.51.100.12','WORKER3':'198.51.100.13',
                'BACKEND_PORT':'8080'}
            for item in (valid,invalid):
                subprocess.run(['bash','-euo','pipefail','-c',item['command']],env=env,
                    check=True,capture_output=True,text=True,timeout=10)
            bodies={}
            for name in ('model-engine-gateway.json','invalid-model-engine-rule.json'):
                raw=(run/name).read_bytes()
                bodies[name]={'produced_sha256':digest(raw),
                    'sha256':digest(json.dumps(json.loads(raw),sort_keys=True).encode()),'body':json.loads(raw)}
            records.append({'asset':asset.relative_to(root).as_posix(),
                'asset_sha256':digest(asset.read_bytes()),'bodies':bodies})
    if len(records)!=30: raise ValueError('expected all 30 model/engine input assets')
    return {'schema_version':1,'producers':{'model-engine-gateway.json':valid,
        'invalid-model-engine-rule.json':invalid},'records':records,
        'bindings':{CONFIGURE+'|@$RUN/model-engine-gateway.json':'model-engine-gateway.json',
            LIFECYCLE+'|@$RUN/model-engine-gateway.json':'model-engine-gateway.json',
            VERIFY+'|@$RUN/invalid-model-engine-rule.json':'invalid-model-engine-rule.json'},
        'scope':'Exact public assets and extracted jq producers; no engine runtime qualification'}

def load_bound_bodies(root, page, reference):
    path=root/OUTPUT
    if not path.exists(): raise ValueError('body bindings missing; regenerate them on the Linux runner')
    binding=json.loads(path.read_text())
    key=page.as_posix()+'|'+reference
    if key not in binding['bindings']: raise ValueError(f'unbound file body: {key}')
    name=binding['bindings'][key]
    for producer in binding['producers'].values():
        blocks=list(markdown_blocks(root/producer['page']))
        if not any(digest(block.text.encode())==producer['block_sha256'] for block in blocks):
            raise ValueError('body producer changed; refresh bindings')
    bodies=[]
    for record in binding['records']:
        asset=root/record['asset']
        if not asset.is_file() or digest(asset.read_bytes())!=record['asset_sha256']:
            raise ValueError('body input asset changed: '+record['asset'])
        value=record['bodies'][name]
        if digest(json.dumps(value['body'],sort_keys=True).encode())!=value['sha256']:
            raise ValueError('bound body content hash mismatch')
        bodies.append(value['body'])
    return bodies

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    rendered=json.dumps(document(root),indent=2,sort_keys=True)+'\n';path=root/OUTPUT
    if args.check:
        if not path.exists() or path.read_text()!=rendered: parser.exit(1,'FAIL: file body bindings are stale\n')
    else: path.write_text(rendered)
    print('PASS: all 30 real assets and both extracted jq producers match file body bindings')
if __name__=='__main__': main()
