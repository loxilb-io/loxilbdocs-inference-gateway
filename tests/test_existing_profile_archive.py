"""Negative controls for public reproduction-archive extraction."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'profile_inputs', Path(__file__).resolve().parents[1] / 'tools/validate_existing_profile_inputs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ArchiveExtractionTests(unittest.TestCase):
    def archive(self, folder, entries):
        archive = folder / 'evaluation.tgz'
        with tarfile.open(archive, 'w:gz') as handle:
            for name, kind in entries:
                item = tarfile.TarInfo(name)
                if kind == 'link':
                    item.type = tarfile.SYMTYPE
                    item.linkname = '/etc/passwd'
                    handle.addfile(item)
                else:
                    item.size = 4
                    handle.addfile(item, io.BytesIO(b'test'))
        archive.with_name(archive.name + '.sha256').write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
        return archive

    def test_valid_regular_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            archive = self.archive(folder, [('existing-profiles/file.json', 'file')])
            root = module.extract_archive(archive, folder / 'out')
            self.assertEqual(b'test', (root / 'file.json').read_bytes())

    def test_corruption_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            archive = self.archive(folder, [('existing-profiles/file.json', 'file')])
            archive.write_bytes(archive.read_bytes() + b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                module.extract_archive(archive, folder / 'out')
            self.assertFalse((folder / 'out').exists())

    def test_unsafe_or_duplicate_members_rejected(self):
        cases = [
            [('../escape', 'file')],
            [('/absolute', 'file')],
            [('wrong-root/file', 'file')],
            [('existing-profiles/link', 'link')],
            [('existing-profiles/file', 'file'), ('existing-profiles/file', 'file')],
        ]
        for entries in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                archive = self.archive(folder, entries)
                with self.assertRaises(ValueError):
                    module.extract_archive(archive, folder / 'out')

    def test_retained_setting_cannot_diverge_from_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source, complete = folder / 'source', folder / 'complete'
            source.mkdir()
            complete.mkdir()
            (source / 'settings.env').write_bytes(b'changed')
            (complete / 'settings.env').write_bytes(b'original')
            (source / 'SHA256SUMS').write_text(
                hashlib.sha256(b'changed').hexdigest() + '  settings.env\n')
            with self.assertRaisesRegex(ValueError, 'retained/archive mismatch'):
                module.verify_retained(source, complete)
