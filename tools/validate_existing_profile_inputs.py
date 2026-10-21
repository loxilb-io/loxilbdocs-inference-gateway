#!/usr/bin/env python3
"""Validate the existing-profile reproduction package; static inputs do not certify a runtime."""
import argparse
import ast
import hashlib
import ipaddress
import json
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import yaml


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def validate(root, checksums):
    manifest, models = read(root / 'manifest.json'), read(root / 'model-identities.json')
    require(len(models) == manifest['sourceProfiles'] == 13, 'all 13 exact identities')
    require(manifest['releaseQualification'] is False and manifest['sourceCatalogPromotion'] is False, 'qualification boundaries')
    require(manifest['gatewaySourceCommit'].startswith('UNVERIFIED'), 'binary source provenance limit')
    require(not manifest['modelWeightsIncluded'] and not manifest['tokenizerTemplateBytesIncluded']
            and not manifest['privateDeploymentInspectionIncluded'], 'public distribution boundary')
    ids, profiles, fixtures = set(), {}, 0
    for model in models:
        pid = model['profileId']
        require(pid not in ids and re.fullmatch('[a-z0-9-]+', pid), 'unique profile ID')
        ids.add(pid)
        require(re.fullmatch('[0-9a-f]{40}', model['revision']), 'full immutable revision')
        for field in ['tokenizerSha256', 'templateSha256', 'weightsIndexSha256']:
            require(re.fullmatch('[0-9a-f]{64}', model[field]), field)
        original = yaml.safe_load((root / 'source-definitions' / (pid + '.yaml')).read_text())
        require(original['profileId'] == pid and original['baseModel'] == model['repo'], 'source profile identity')
        source_index=(root / 'weights' / (pid + '.source-index')).read_bytes()
        require(hashlib.sha256(source_index).hexdigest() == model['weightsIndexSha256'], 'original full source-index bytes')
        indexed = [line.split(' ',2) for line in source_index.decode().splitlines()]
        if model['templateSource'] is None:
            require(pid in ['gemma3-1b-it-v1', 'llama32-1b-v1'], 'only known gated metadata missing')
            require(not (root / 'weights' / (pid + '.sha256')).exists(), 'no verified recipe for inaccessible weights')
            continue
        require(model['templateSource'] in ['chat_template.jinja', 'tokenizer_config.json:chat_template'], 'exact template extraction route')
        names = []
        for line in (root / model['weightChecksums']).read_text().splitlines():
            digest, name = line.split('  ', 1)
            require(re.fullmatch('[0-9a-f]{64}', digest) and '..' not in pathlib.PurePosixPath(name).parts
                    and not pathlib.PurePosixPath(name).is_absolute(), 'safe complete weight checksums')
            names.append(name)
        require(names == [line[2] for line in indexed], 'full original index filename coverage')
        sha_map={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (root / model['weightChecksums']).read_text().splitlines()}
        require(sha_map['tokenizer.json'] == model['tokenizerSha256'], 'tokenizer identity also bound by full source index')
        if model['templateSource']=='chat_template.jinja':require(sha_map['chat_template.jinja'] == model['templateSha256'], 'standalone template identity bound by source index')
        require(all(not algo.startswith('sha256:') or sha_map[name] == algo[7:] for algo,size,name in indexed), 'original LFS SHA256 preserved')
        require(len(names) == len(set(names)) and any(name.endswith('.safetensors') for name in names), 'weight filenames')
        for engine, version in manifest['engineVersions'].items():
            registry = root / ('registry-' + engine)
            profile = yaml.safe_load((registry / (pid + '.yaml')).read_text())
            native = yaml.safe_load((registry / 'manifests' / (pid + '.yaml')).read_text())
            require(profile == original and (registry / (pid + '.yaml')).read_bytes() == (root / 'source-definitions' / (pid + '.yaml')).read_bytes(), 'original source profile bytes preserved')
            require(profile['tokenizerRevision'] == model['revision'], 'profile revision')
            require(native['profileId'] == pid and native['engineVersion'] == version
                    and native['modelRevision'] == model['revision'], 'isolated engine manifest identity')
            digests = {'vllm': 'a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b', 'sglang': '37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262', 'trtllm': 'e9dab9fccc550dcc04356962ff152908d692e0e47ba143f57402a24a4ad64b77'}
            require(native['imageDigest'] == 'sha256:' + digests[engine], 'pinned image digest')
            for field, artifact in [('tokenizerSha256', 'tokenizerArtifact'), ('templateSha256', 'templateArtifact')]:
                require(profile[field] == model[field] and profile[artifact] == 'sha256/' + model[field], 'profile artifact binding')
            profiles[engine, pid] = profile
            for request in (registry / 'probefixtures' / pid).rglob('*.request.json'):
                expected = read(request.with_name(request.name.replace('.request.json', '.expect.json')))
                raw = request.read_bytes()
                require(hashlib.sha256(raw).hexdigest() == expected['requestSha256'], 'probe input bytes')
                require(read(request)['model'] == model['repo'] and expected['expectedTokenIds'], 'original fixture identity/tokens')
                fixtures += 1
    require(len(profiles) == 33, '11 independently pinned metadata sets x3 engines')
    rules = 0
    for path in (root / 'rules').glob('*.json'):
        rule = read(path)
        a = rule['serviceArguments']
        pd, engine = a['pd_disagg_mode'], a['kvEngineType']
        require(a['mode'] == 4 and a['sel'] == 0 and a['kvExactMode'] in ([0, 1] if pd else [0, 3]), 'topology-specific routing mode')
        if a['kvExactMode']:
            profile = profiles[engine, a['kvModelProfile']]
            require(profile['baseModel'] == a['model_name'] and a['kvBlockSize'] == 16
                    and a['kvExactApiMode'] == 'chat', 'Exact model/profile/geometry')
        for address in [a['externalIP'], a['host']] + [e['endpointIP'] for e in rule['endpoints']]:
            require(ipaddress.ip_address(address) in ipaddress.ip_network('192.0.2.0/24'), 'documentation addresses only')
        require(all(e['targetPort'] == a['probeport'] == 18301 for e in rule['endpoints']), 'independent receipt endpoint')
        if pd:
            require({e['ep_role'] for e in rule['endpoints']} == {1, 2}
                    and sum(e['ep_role'] == 2 for e in rule['endpoints']) == 1, 'P/D roles')
            if engine == 'vllm':
                require(all(e['nixl_port'] == 5600 for e in rule['endpoints']), 'NIXL side channel')
            elif engine == 'sglang':
                require(a['pdBootstrapPort'] == 18998, 'Mooncake bootstrap')
        rules += 1
    for path in (root / 'settings').glob('*.env'):
        subprocess.run(['bash', '-n', str(path)], check=True, capture_output=True)
    for path in root.rglob('*'):
        if not path.is_file() or path.name == 'SHA256SUMS':
            continue
        if path.suffix == '.py':
            ast.parse(path.read_text())
        elif path.suffix == '.json':
            read(path)
        elif path.suffix == '.yaml':
            yaml.safe_load(path.read_text())
        require(path.suffix not in ['.safetensors', '.bin', '.tgz', '.log', '.key', '.pem'], 'no private/model payload')
        text = path.read_text()
        require(not re.search(r'\b10\.0\.0\.\d+\b|/root/igw-|/Use[r]s/|GF_SECURITY_ADMIN_PASSWORD|"Env"\s*:', text), 'no private deployment metadata')
    if checksums:
        listed = set()
        for line in (root / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            require(not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts, 'checksum path')
            require(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, 'checksum ' + name)
            listed.add(name)
        actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS' and '__pycache__' not in p.parts}
        require(listed == actual, 'all public files covered by checksums')
    return dict(verdict='PASS_STATIC_REPRODUCTION_INPUTS_ONLY', models=len(models),
                engineMetadataSets=len(profiles), fixtures=fixtures, rules=rules)


def extract_archive(archive, destination):
    """Verify the sidecar before extracting only regular payload files safely."""
    sidecar = archive.with_name(archive.name + '.sha256')
    expected = sidecar.read_text().strip().split('  ')
    require(len(expected) == 2 and expected[1] == archive.name
            and re.fullmatch('[0-9a-f]{64}', expected[0]), 'archive checksum format')
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == expected[0], 'archive checksum mismatch')
    seen = set()
    with tarfile.open(archive, 'r:gz') as handle:
        for member in handle:
            name = pathlib.PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts
                    and name.parts and name.parts[0] == 'existing-profiles', 'unsafe archive path')
            require(name.as_posix() not in seen, 'duplicate archive member')
            seen.add(name.as_posix())
            require(member.isdir() or member.isfile(), 'non-regular archive member')
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.extractfile(member) as source, target.open('wb') as output:
                    import shutil
                    shutil.copyfileobj(source, output)
    return destination / 'existing-profiles'


def verify_retained(source, complete):
    """The repository is a checksummed subset, not a second full package."""
    listed = set()
    for line in (source / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = pathlib.PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts, 'retained checksum path')
        require(name not in listed and re.fullmatch('[0-9a-f]{64}', digest), 'retained checksum entry')
        listed.add(name)
        payload = (source / name).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == digest, 'retained checksum ' + name)
        require(name == 'README.md' or payload == (complete / name).read_bytes(), 'retained/archive mismatch ' + name)
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()
              and p.name != 'SHA256SUMS' and '__pycache__' not in p.parts}
    require(actual == listed, 'retained checksum coverage')
    require(not (source / 'results').exists()
            and not any(source.glob('registry-*/probefixtures')), 'raw evidence is archive-only')
    return len(listed) + 1


def validate_archive(archive, source_root=None, verify_results=False):
    with tempfile.TemporaryDirectory(prefix='existing-profile-package-') as temp:
        root = extract_archive(archive, pathlib.Path(temp))
        report = validate(root, True)
        if source_root:
            report['retainedFiles'] = verify_retained(source_root, root)
        if verify_results:
            for name in ['verify-results.py', 'verify-incomplete-results.py', 'verify-converged.py']:
                result = subprocess.run([sys.executable, str(root / name), '--mutation-control'],
                                        check=True, capture_output=True, text=True)
                # Keep the CI log concise while executing the real raw-data checks.
                report[name] = json.loads(result.stdout)['verdict']
            report['mutationControls'] = 'all three real verifiers passed'
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=pathlib.Path, help='complete extracted directory or .tgz archive')
    parser.add_argument('--without-checksums', action='store_true', help='directory inputs only')
    parser.add_argument('--source-root', type=pathlib.Path, help='retained repository files to compare with archive')
    parser.add_argument('--verify-results', action='store_true', help='run all raw-result verifiers and mutation controls')
    args = parser.parse_args()
    if args.root.is_file():
        require(not args.without_checksums, 'archive verification always requires checksums')
        report = validate_archive(args.root, args.source_root, args.verify_results)
    else:
        require(not args.source_root and not args.verify_results, 'archive options require an archive file')
        report = validate(args.root, not args.without_checksums)
    print(json.dumps(report, indent=2))
