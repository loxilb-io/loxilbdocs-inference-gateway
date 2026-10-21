#!/usr/bin/env python3
"""Account for every exported incomplete-comparison offer without selecting settings."""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import shutil
import tempfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def _normal(body, stream, profile, require_keywords=True):
    text, reasoning, reasons, usage = '', '', [], None
    if stream:
        if body.count(b'data: [DONE]') != 1:
            return False
        chunks = [json.loads(line[5:].strip()) for line in body.splitlines()
                  if line.startswith(b'data:') and line[5:].strip() not in (b'', b'[DONE]')]
    else:
        chunks = [json.loads(body)]
    for chunk in chunks:
        if chunk.get('error'):
            return False
        usage = chunk.get('usage') or usage
        for choice in chunk.get('choices', []):
            text += choice.get('delta' if stream else 'message', {}).get('content') or ''
            message = choice.get('delta' if stream else 'message', {})
            reasoning += message.get('reasoning_content') or message.get('reasoning') or ''
            if choice.get('finish_reason'):
                reasons.append(choice['finish_reason'])
    if profile == 'r1-distill-qwen-15b-v1' and '</think>' not in text:
        return False
    if (profile.startswith(('qwen36-', 'qwen38-')) or profile=='granite42-3b-v1') and not ('</think>' in text or reasoning):
        return False
    for begin, end in [('<think>', '</think>'), ('◁think▷', '◁/think▷')]:
        if begin in text and end not in text:
            return False
        text = text.rsplit(end, 1)[-1]
    return bool(reasons and all(x == 'stop' for x in reasons) and usage
                and usage.get('prompt_tokens', 0) > 0 and usage.get('completion_tokens', 0) > 0
                and len(re.findall(r'[A-Za-z]{2,}', text)) >= 3
                and (not require_keywords or any(x in text.lower() for x in ['water', 'health']))
                and not any(x in text for x in ['Ġ', 'Ċ', '�', '<|channel|>', '<|message|>', '<|im_start|>']))


def normal(body, stream, profile, require_keywords=True):
    try:
        return _normal(body, stream, profile, require_keywords)
    except (ValueError, KeyError, TypeError, UnicodeError):
        return False


def verify(root):
    results, ids = [], set()
    for entry in load(root / 'results/incomplete-settings-index.json'):
        summary = load(root / entry['summary'])
        require(summary['candidatePerformanceRecommendation'] is False, 'no recommendation from incomplete data')
        require(summary['routing']=='converged-rr' and len(summary['mainBodySha256s'])<=1, 'fixed main body and route retained')
        phases, good, matched, offered, partial, timeouts = collections.Counter(), 0, 0, 0, 0, 0
        main_hashes = set()
        for arm in summary['arms']:
            rows = load(root / arm['samples'])
            for launch in arm['launches']:
                args=launch['nativeArguments'];flag='--gpu-memory-utilization' if summary['axis']=='memory' else '--max-num-seqs'
                require(float(args[args.index(flag)+1])==arm['settingValue'], 'actual attempted native setting retained')
            require(len(rows) == arm['offered'], 'arm offered denominator')
            arm_phases = collections.Counter()
            warm_workers = collections.Counter()
            for row in rows:
                require(row['requestId'] not in ids, 'unique offered IDs')
                ids.add(row['requestId'])
                raw, body = (root / row['request']).read_bytes(), (root / row['response']).read_bytes()
                require(hashlib.sha256(raw).hexdigest() == row['requestSha256'], 'RAW_REQUEST_HASH')
                require(hashlib.sha256(body).hexdigest() == row['responseSha256'], 'RAW_RESPONSE_HASH')
                if row['phase'] == 'main':
                    main_hashes.add(hashlib.sha256(raw).hexdigest())
                receipt = row['receipt']
                if receipt:
                    require(receipt['requestId'] == row['requestId'], 'receipt ID')
                    require(receipt['requestSha256'] == row['requestSha256'], 'RAW_RECEIPT_HASH')
                    require(receipt['requestBytes'] == len(raw), 'wire request length')
                    if receipt['responseSha256'] != row['responseSha256']:
                        require(row.get('clientErrorCode') == 'CLIENT_READ_TIMEOUT'
                                and row.get('deliveryEvidence') == 'CLIENT_TIMEOUT_UPSTREAM_PARTIAL'
                                and row['sourceNormal'] is False
                                and receipt['upstreamComplete'] is False,
                                'RAW_RECEIPT_HASH')
                        require(bool(row.get('upstreamPartialResponse')), 'missing upstream partial evidence')
                        upstream = (root / row['upstreamPartialResponse']).read_bytes()
                        require(hashlib.sha256(upstream).hexdigest() == receipt['responseSha256'], 'RAW_UPSTREAM_PARTIAL_HASH')
                        require(len(upstream) == receipt['responseBytes'], 'upstream partial wire length')
                        partial += 1
                    else:
                        require(receipt['responseBytes'] == len(body), 'wire response length')
                        matched += bool(receipt['upstreamComplete'])
                actual_normal = row['status'] == 200 and normal(body, json.loads(raw).get('stream', False), summary['profileId'])
                require(actual_normal == row['sourceNormal'], 'each source-normal flag independently verified')
                good += actual_normal
                timeouts += row.get('clientErrorCode') == 'CLIENT_READ_TIMEOUT'
                offered += 1
                phases[row['phase']] += 1
                arm_phases[row['phase']] += 1
                if row['phase'] == 'load-warm':
                    warm_workers[row['worker']] += 1
            require({p: arm_phases[p] for p in ['main', 'native-warm', 'load-warm']} == arm['phaseCounts'], 'arm phase denominator')
            require({p: warm_workers[p] for p in arm['loadWarmWorkerCounts']} == arm['loadWarmWorkerCounts'], 'actual warm distribution')
        require(sorted(main_hashes) == summary['mainBodySha256s'], 'main body hashes derived from raw offers')
        require(offered == summary['offered'] == entry['offered'], 'all offers retained')
        require({p: phases[p] for p in ['main', 'native-warm', 'load-warm']} == summary['phaseCounts'] == entry['phaseCounts'], 'all phase denominators')
        require(good == summary['sourceNormalCount'], 'independently parsed normal count')
        require(matched == summary['receiptMatchedCount'], 'independent receipt count')
        require(partial == summary.get('upstreamPartialResponseCount', 0), 'all upstream partial responses retained')
        require(timeouts == summary.get('clientReadTimeoutCount', 0), 'all client timeouts retained')
        results.append(dict(profileId=summary['profileId'], axis=summary['axis'], offered=offered,
                            phaseCounts=dict(phases), normal=good, receiptMatched=matched,
                            upstreamPartialResponses=partial, clientReadTimeouts=timeouts,
                            performanceRecommendation=False))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument('--mutation-control', action='store_true')
    args = parser.parse_args()
    result = dict(verdict='PASS_INCOMPLETE_DATA_ACCOUNTING_ONLY', comparisons=verify(args.root))
    if args.mutation_control:
        with tempfile.TemporaryDirectory(prefix='incomplete-mutation-') as directory:
            target = pathlib.Path(directory) / 'copy'
            shutil.copytree(args.root, target)
            summary = load(target / load(target / 'results/incomplete-settings-index.json')[0]['summary'])
            path = target / summary['arms'][0]['samples']
            rows = load(path)
            original_rows = path.read_text()
            rows[0]['receipt']['responseSha256'] = '0' * 64
            path.write_text(json.dumps(rows))
            try:
                verify(target)
            except ValueError as exc:
                require(str(exc) == 'RAW_RECEIPT_HASH', 'actual verifier rejected corrupt receipt')
            else:
                raise ValueError('Corrupt receipt accepted')
            path.write_text(original_rows)
            partial_path = None
            for entry in load(target / 'results/incomplete-settings-index.json'):
                for arm in load(target / entry['summary'])['arms']:
                    for row in load(target / arm['samples']):
                        if row.get('upstreamPartialResponse'):
                            partial_path = target / row['upstreamPartialResponse']
                            break
            if partial_path:
                original = partial_path.read_bytes()
                require(bool(original), 'partial body mutation needs nonempty evidence')
                partial_path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                try:
                    verify(target)
                except ValueError as exc:
                    require(str(exc) == 'RAW_UPSTREAM_PARTIAL_HASH', 'actual verifier rejected corrupt upstream partial')
                else:
                    raise ValueError('Corrupt upstream partial accepted')
                result['corruptUpstreamPartialRejectedByVerifier'] = True
        result['corruptReceiptRejectedByVerifier'] = True
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
