#!/usr/bin/env python3
"""Map every public fence and API operation without promoting static checks to execution."""
import argparse
import json
from pathlib import Path
from validate_examples import ExampleValidator, collect_public_blocks, extract_shell_commands, shell_tokens

OUTPUT='tests/contracts/docs_examples/coverage-ledger.json'
def document(root):
    validator=ExampleValidator(root,False)
    api={f'{method.upper()} {path}':[] for spec in validator.gateway_contract['specs']
         for path,methods in spec['paths'].items() for method in methods}
    commands={name:[] for name,contract in validator.cli_contract['commands'].items() if contract['main']['available']}
    examples=[]
    for identity,block,digest in collect_public_blocks(root):
        operations=[];cli=[]
        for command in extract_shell_commands(block.text,'curl'):
            method,url,_=validator._curl_details(command);route=validator._management_route(url)
            if route is None:continue
            for spec in validator.gateway_contract['specs']:
                for path,methods in spec['paths'].items():
                    name=f'{method.upper()} {path}'
                    if method.lower() in methods and validator._template_regex(path).match(route):
                        if name not in operations:operations.append(name);api[name].append(identity)
        for command in extract_shell_commands(block.text,'loxicmd'):
            tokens=shell_tokens(command)[1:]
            name=next((name for name in sorted(commands,key=lambda n:-len(n.split())) if tokens[:len(name.split())]==name.split()),None)
            if name:cli.append(name);commands[name].append(identity)
        examples.append({'id':identity,'path':block.path.as_posix(),'line':block.line,
            'sha256':digest,'operations':sorted(operations),'commands':sorted(set(cli)),
            'runtime':'no-public-execution-attestation'})
    return {'schema_version':1,'gateway_commit':validator.gateway_contract['source']['commit'],
        'cli_commit':validator.cli_contract['source']['main_commit'],
        'operations':dict(sorted(api.items())),'commands':dict(sorted(commands.items())),
        'examples':examples,'summary':{'fences':len(examples),'operations':len(api),
            'operations_with_direct_examples':sum(bool(ids) for ids in api.values()),
            'operations_without_direct_examples':sum(not ids for ids in api.values())},
        'scope':'Direct examples are static source mappings; missing examples are not implementation failures. Runtime and release qualification are separate.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check',action='store_true');args=parser.parse_args();root=args.root.resolve()
    value=document(root);text=json.dumps(value,indent=2,sort_keys=True)+'\n';output=root/OUTPUT
    if args.check:
        if not output.exists() or output.read_text()!=text:parser.exit(1,'FAIL: coverage ledger is stale\n')
    else:output.write_text(text)
    print(json.dumps(value['summary']))
if __name__=='__main__':main()
