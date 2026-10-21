#!/usr/bin/env python3
"""Recompute every published bounded setting decision from all raw samples.

Client monotonic arrival measurements are recorded inputs. Untimed SSE cannot
reconstruct those arrival times. Functional/P-D exports are reviewed summaries.
"""
import argparse, collections, copy, hashlib, json, math, pathlib, re, shutil, statistics, tempfile

def require(ok, message):
    if not ok:
        raise ValueError(message)

def load(p):
    return json.loads(p.read_text())

def verify(root):
    result = []
    global_ids = set()
    for entry in load(root / 'results/settings-index.json'):
        s = load(root / entry['summary'])
        axis = s['axis']
        base = s['baseValue']
        candidate = s['candidateValue']
        workers = s['workers']
        require({x['worker'] for x in s['hardware']}==set(workers) and len({(x['gpuModel'],x['gpuTotalMiB'],x['driver']) for x in s['hardware']})==1, 'same two recorded GPU models, VRAM and drivers')
        values = {}
        totals = {}
        require(s['gpuAllocationSnapshotPhase']=='AFTER_NATIVE_JSON_WARM_BEFORE_RR_LOAD_WARM', 'allocation snapshot phase')
        allocated = {}
        hashes = set()
        native = {}
        offered = 0
        rendered_tokens = None
        require([(a['trial'], a['settingValue']) for a in s['arms']] == [(0, base), (0, candidate), (1, candidate), (1, base), (2, base), (2, candidate)], 'AB/BA/AB arm order')
        for a in s['arms']:
            rows = load(root / a['samples'])
            if s['profileId'] in ['gptoss-20b-v1', 'llama32-1b-v1']:
                date = s['dateContext']
                require(date['requiresSameDateAllArms'] and date['noTZOverride'] and date['noHostLocaltimeMount'] and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date['UTCDate']), 'fixed date context')
                require(len(a['renderedNativeInputs']) == 2, 'both native rendered inputs retained')
                for rendered in a['renderedNativeInputs']:
                    require(rendered['imageTimezone'] in ['UTC', 'GMT'] and rendered['status'] == 200, 'native UTC image tokenize control')
                    raw = (root / rendered['request']).read_bytes()
                    body = (root / rendered['response']).read_bytes()
                    require(hashlib.sha256(raw).hexdigest() == rendered['requestSha256'] and hashlib.sha256(body).hexdigest() == rendered['responseSha256'], 'NATIVE_RENDERED_INPUT_HASH')
                    tokens = json.loads(body)['tokens']
                    require(tokens and all(type(t) is int and t >= 0 for t in tokens), 'native rendered token IDs')
                    if rendered_tokens is None:
                        rendered_tokens = tokens
                    require(tokens == rendered_tokens, 'identical native input tokens across all workers and arms')
                    native_payload = json.loads(raw)
                    main_payload = json.loads((root / next(x['request'] for x in rows if x['phase'] == 'main')).read_text())
                    require(native_payload['model'] == main_payload['model'] and native_payload['messages'] == main_payload['messages'] and native_payload['add_generation_prompt'] is True and native_payload['add_special_tokens'] is False, 'native tokenization of actual fixed chat input')
            require(collections.Counter((x['phase'] for x in rows)) == {'main': 24, 'native-warm': 2, 'load-warm': 16}, 'all offered phase denominators')
            counts = collections.defaultdict(collections.Counter)
            times = []
            tokens = 0
            for row in rows:
                require(row['requestId'] not in global_ids, 'unique offered ID')
                global_ids.add(row['requestId'])
                offered += 1
                raw = (root / row['request']).read_bytes()
                body = (root / row['response']).read_bytes()
                receipt = row['receipt']
                for data, field in [(raw, 'requestSha256'), (body, 'responseSha256')]:
                    require(hashlib.sha256(data).hexdigest() == row[field] == receipt[field], 'RAW_RECEIPT_HASH:' + field)
                require(receipt['requestId'] == row['requestId'] and receipt['worker'] == row['worker'] and (row['worker'] in workers), 'independent receipt identity')
                require(receipt['requestBytes'] == len(raw) and receipt['responseBytes'] == len(body), 'wire body lengths')
                require(row['status'] == receipt['httpStatus'] == 200 and receipt['upstreamComplete'], 'native response completed')
                p = json.loads(raw)
                require(p['model'] == s['model'] and p['temperature'] == 0 and (p['max_tokens'] == s['workload']['maxOutput']), 'fixed model, output budget and temperature')
                text = ''
                reasoning = ''
                finish = []
                usage = None
                if p.get('stream', False):
                    require(body.count(b'data: [DONE]') == 1, 'exactly one DONE')
                    for line in body.splitlines():
                        if not line.startswith(b'data:'):
                            continue
                        z = line[5:].strip()
                        if not z or z == b'[DONE]':
                            continue
                        data = json.loads(z)
                        require('error' not in data, 'no in-band error')
                        if data.get('usage'):
                            usage = data['usage']
                        for c in data.get('choices', []):
                            text += c.get('delta', {}).get('content') or ''
                            reasoning += c.get('delta', {}).get('reasoning_content') or c.get('delta', {}).get('reasoning') or ''
                            if c.get('finish_reason'):
                                finish.append(c['finish_reason'])
                else:
                    data = json.loads(body)
                    usage = data.get('usage')
                    for c in data.get('choices', []):
                        text += c.get('message', {}).get('content') or ''
                        reasoning += c.get('message', {}).get('reasoning_content') or c.get('message', {}).get('reasoning') or ''
                        finish.append(c.get('finish_reason'))
                if s['profileId'] == 'r1-distill-qwen-15b-v1':
                    require('</think>' in text, 'R1 reasoning closed')
                if s['profileId'].startswith(('qwen36-', 'qwen38-')) or s['profileId']=='granite42-3b-v1':
                    require('</think>' in text or reasoning, 'Prefilled reasoning closed or separated')
                for begin, end in [('<think>', '</think>'), ('◁think▷', '◁/think▷')]:
                    if begin in text:
                        require(end in text, 'closed reasoning')
                    if end in text:
                        text = text.rsplit(end, 1)[-1]
                require(len(re.findall('[A-Za-z]{2,}', text)) >= 3 and any((x in text.lower() for x in ['water', 'health'])) and (not any((x in text for x in ['Ġ', 'Ċ', '�', '<|channel|>', '<|message|>', '<|im_start|>']))), 'readable final English answer')
                require(finish and all((x == 'stop' for x in finish)), 'normal uncapped answer')
                require(usage and usage['prompt_tokens'] > 0 and (usage['completion_tokens'] > 0) and (usage['prompt_tokens'] + usage['completion_tokens'] <= s['workload']['context']), 'positive usage within configured context')
                counts[row['phase']][row['worker']] += 1
                if row['phase'] == 'main':
                    require(math.isfinite(row['ttft']) and 0 < row['ttft'] <= row['elapsed'], 'recorded client timing')
                    require(row['outputTokens'] == usage['completion_tokens'], 'recomputed output tokens')
                    times.append(row['ttft'])
                    tokens += usage['completion_tokens']
                    hashes.add(row['requestSha256'])
            require(sorted(counts['native-warm'].values()) == [1, 1] and sorted(counts['load-warm'].values()) == [8, 8], 'equal separate warmup')
            require(dict(counts['main']) == a['workerCounts'] and set(counts['main']) == set(workers) and sum(counts['main'].values()) == 24, 'recorded main distribution')
            p95 = sorted(times)[math.ceil(0.95 * 24) - 1]
            require(p95 == a['ttftP95Sec'] and tokens == a['outputTokens'], 'recomputed per-arm aggregates')
            require(math.isfinite(a['wallSec']) and a['wallSec'] > 0 and a['requestsPerSec'] == 24/a['wallSec'], 'recorded wall time throughput arithmetic')
            require(a['offered'] == a['normal'] == a['receiptMatched'] == 24 and a['valid'], 'complete arm')
            key = (a['trial'], a['settingValue'])
            values[key] = p95
            totals[key] = tokens
            allocated[key] = []
            for launch in a['launches']:
                args = launch['nativeArguments'].copy()
                flag = '--gpu-memory-utilization' if axis == 'memory' else '--max-num-seqs'
                expected = str(a['settingValue']) if axis == 'memory' else str(int(a['settingValue']))
                require(args[args.index(flag) + 1] == expected, 'native compared setting')
                require(args[args.index('--max-model-len') + 1] == '4096' and args[args.index('--max-num-batched-tokens') + 1] == '4096', 'fixed context')
                require(args[args.index('--served-model-name') + 1] == s['model'], 'served identity')
                require('sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b' in args, 'pinned image')
                args[args.index(flag) + 1] = 'VALUE'
                require(args == native.setdefault(launch['worker'], args), 'only one launch setting changes')
                allocated[key].append(launch['allocatedAfterNativeWarmMiB'])
        require(offered == 252 and len(hashes) == 1, '144 main and 108 separate warm, fixed main bytes')
        gains = [(values[i, base] - values[i, candidate]) / values[i, base] for i in range(3)]
        token_gate = all((abs(totals[i, base] - totals[i, candidate]) / totals[i, base] <= 0.05 for i in range(3)))
        memory_gate = all((all(((old - new) / old >= 0.3 for old, new in zip(allocated[i, base], allocated[i, candidate]))) for i in range(3)))
        choose = token_gate and (all((x >= -0.05 for x in gains)) and memory_gate if axis == 'memory' else all((x > 0 for x in gains)) and statistics.median(gains) >= 0.1)
        selected = candidate if choose else base
        require(gains == s['improvementFractions'] and token_gate == s['tokenTotalsWithin5Percent'] and (memory_gate == s['memoryReductionGate']) and (selected == s['selectedValue'] == entry['selectedValue']), 'recomputed decision')
        result.append(dict(profileId=s['profileId'], axis=axis, mainNormalReceiptMatched=144, separateWarmNormalReceiptMatched=108, relativeP95Gains=gains, performanceComparisonQualified=token_gate, candidateAdopted=choose, tokenGate=token_gate, allocatedMemoryReductionGate=memory_gate, selectedValue=selected))
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    p.add_argument('--mutation-control', action='store_true')
    a = p.parse_args()
    result = dict(verdict='PASS_RECOMPUTED_BOUNDED_SETTINGS', comparisons=verify(a.root), timingLimit='Recorded client measurements; untimed SSE cannot reconstruct arrival times')
    if a.mutation_control:
        with tempfile.TemporaryDirectory(prefix='settings-mutation-') as tmp:
            target = pathlib.Path(tmp) / 'copy'
            shutil.copytree(a.root, target)
            entry = load(target / 'results/settings-index.json')[0]
            s = load(target / entry['summary'])
            samples = target / s['arms'][0]['samples']
            rows = load(samples)
            rows[0]['receipt']['responseSha256'] = '0' * 64
            samples.write_text(json.dumps(rows))
            try:
                verify(target)
            except ValueError as exc:
                require('RAW_RECEIPT_HASH:responseSha256' in str(exc), 'mutation rejected by actual receipt-hash gate')
            else:
                raise ValueError('Corrupt native receipt was accepted')
        result['corruptReceiptRejectedByVerifier'] = True
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    main()
