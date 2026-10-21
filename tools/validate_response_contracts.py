#!/usr/bin/env python3
"""Assert exact status, response schema and no-mutation evidence from a Linux run."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from jsonschema import Draft4Validator

def validate(expectation, observation):
    errors=[]
    if observation.get('status')!=expectation['status']:
        errors.append('unexpected HTTP status')
    errors.extend('response '+error.message for error in Draft4Validator(expectation['schema']).iter_errors(observation.get('body')))
    if 'receipt_delta' in expectation and observation.get('receipt_delta')!=expectation['receipt_delta']:
        errors.append('unexpected independent backend receipt delta')
    if expectation.get('unchanged') and observation.get('before')!=observation.get('after'):
        errors.append('material configuration changed')
    if not observation.get('executed',False): errors.append('observation is not executed evidence')
    return errors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expectations',type=Path,default=Path(__file__).resolve().parents[1]/'tests/contracts/docs_examples/response-expectations.json')
    parser.add_argument('--observations',type=Path,required=True)
    args=parser.parse_args();expected=json.loads(args.expectations.read_text());observed=json.loads(args.observations.read_text())
    errors=[]
    for name,expectation in expected['cases'].items():
        if name not in observed: errors.append(name+': missing observation');continue
        errors.extend(name+': '+error for error in validate(expectation,observed[name]))
    for error in errors:print(error)
    print(f'cases={len(expected["cases"])} errors={len(errors)}')
    return bool(errors)
if __name__=='__main__':raise SystemExit(main())
