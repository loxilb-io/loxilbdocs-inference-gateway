#!/usr/bin/env python3
"""Verify exported functional answers and independent receipt hashes, including RED rows."""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import tempfile
import sys

sys.dont_write_bytecode = True


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def verify(root):
    spec = importlib.util.spec_from_file_location('raw_answers', root / 'verify-incomplete-results.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results, ids = [], set()
    for entry in load(root / 'results/converged-index.json'):
        case = load(root / entry['samples'])
        good, matched = 0, 0
        ledger=load(root / case['allReceipts'])
        for control in case['controls']:
            if 'response' in control:
                require(hashlib.sha256((root / control['response']).read_bytes()).hexdigest() == control['responseSha256'], 'CONTROL_RESPONSE_HASH')
        require(len(case['rows']) == case['offeredInferences'] == entry['offeredInferences'], 'complete offered denominator')
        for row in case['rows']:
            require(row['requestId'] not in ids, 'unique offered request ID')
            ids.add(row['requestId'])
            raw, body = (root / row['request']).read_bytes(), (root / row['response']).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == row['requestSha256'], 'RAW_REQUEST_HASH')
            require(hashlib.sha256(body).hexdigest() == row['responseSha256'], 'RAW_RESPONSE_HASH')
            request = json.loads(raw)
            parsed_normal = row['status'] == 200 and module.normal(body, request.get('stream', False), case['profileId'], require_keywords=False)
            require(parsed_normal == row['normal'], 'raw normal-answer classification')
            good += parsed_normal
            found=[z for z in ledger if z['requestId']==row['requestId']]
            for receipt in row['receipts']:
                require(receipt['requestId'] == row['requestId'] and receipt['worker'] in case['hardware'], 'receipt identity')
                require(receipt['requestSha256'] == row['requestSha256']
                        and receipt['responseSha256'] == row['responseSha256'], 'RAW_RECEIPT_HASH')
                require(receipt['requestBytes'] == len(raw) and receipt['responseBytes'] == len(body), 'wire length')
                require(receipt['httpStatus'] == row['status'], 'native status')
            require(found == row['receipts'], 'all observed receipts retained')
            if parsed_normal and len(row['receipts']) == 1 and row['receipts'][0]['upstreamComplete']:
                matched += 1
        require(good == case['sourceNormalInferences'] == entry['sourceNormalInferences'], 'all normal and RED rows retained')
        review = case['independentReview']
        if review:
            require(case['gpuReturnedAtLeastInitial'] and review['gpuReturned'], 'GPU release')
            accepted = review.get('acceptedModes', ['rr', 'exact'])
            claimed = review.get('sourceClaimedModes', accepted)
            require(set(accepted) <= set(claimed), 'review cannot introduce an unclaimed accepted mode')
            rejected = {item['mode']: item for item in review.get('rejectedClaimedModes', [])}
            for mode in set(claimed) - set(accepted):
                require(mode in rejected, 'whole rejected mode retained')
                failed = sorted(row['name'] for row in case['rows'] if row['name'].startswith(mode+'-') and not row['normal'])
                require(bool(failed) and failed == sorted(item['name'] for item in rejected[mode]['failedOffered']), 'rejected-mode failures derived from raw bodies')
                require(rejected[mode]['reason']=='INDEPENDENT_ALL_OFFERED_NORMAL_GATE_FAILED', 'explicit all-offer rejection')
            qualified = [row for row in case['rows'] if row['name'].startswith('native-')
                         or any(row['name'].startswith(mode + '-') for mode in accepted)]
            require(len(qualified) == review['normalFullWireMatched'] and all(row['normal'] for row in qualified), 'reviewed accepted scope')
            for mode in accepted:
                route = next(row for row in case['routing'] if row['mode'] == mode)
                for phase, count, field in [('main', 6, 'workerCounts'), ('recovery', 4, 'recoveryCounts')]:
                    rows = [row for row in qualified if row['name'].startswith(mode + '-' + phase + '-')
                            and '-warm-' not in row['name']]
                    require(len(rows) == count, 'routing phase denominator')
                    workers = {worker: sum(row['receipts'][0]['worker'] == worker for row in rows)
                               for worker in case['hardware']}
                    require(workers == route[field], 'native receipt routing distribution')
                unknown=next(z for z in case['controls'] if z['name']==mode+'-unknown')
                invalid=next(z for z in case['controls'] if z['name']==mode+'-invalid')
                require(unknown['status']==503 and invalid['status']==422 and not any(z['requestId']==unknown['requestId'] for z in ledger), 'actual negative statuses and zero native dispatch')
                require(route['unknownNoDispatch'] and route['invalidStatus'] == 422
                        and route['noConfigChange'] and route['deletedAndAbsent'], 'reviewed negative and deletion controls')
        results.append(dict(case=entry['case'], offered=len(case['rows']), normal=good,
                            nativeReceiptMatched=matched, RED=len(case['rows']) - good,
                            independentNativeReview=bool(review),
                            independentlyQualifiedRoutingModes=review.get('acceptedModes', ['rr','exact']) if review else [],
                            independentFunctionalReview=bool(review and review.get('acceptedModes', ['rr','exact']))))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument('--mutation-control', action='store_true')
    args = parser.parse_args()
    result = dict(verdict='PASS_RAW_FUNCTIONAL_ACCOUNTING', cases=verify(args.root))
    if args.mutation_control:
        with tempfile.TemporaryDirectory(prefix='functional-mutation-') as temporary:
            target = pathlib.Path(temporary) / 'copy'
            shutil.copytree(args.root, target)
            entry = next(row for row in load(target / 'results/converged-index.json') if row['offeredInferences'])
            path = target / entry['samples']
            case = load(path)
            next(row for row in case['rows'] if row['receipts'])['receipts'][0]['responseSha256'] = '0' * 64
            path.write_text(json.dumps(case))
            try:
                verify(target)
            except ValueError as exc:
                require(str(exc) == 'RAW_RECEIPT_HASH', 'actual receipt verifier rejected mutation')
            else:
                raise ValueError('Corrupt receipt accepted')
        result['corruptReceiptRejectedByVerifier'] = True
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
