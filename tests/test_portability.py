import copy
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import models
import setup_portability
import studio
import doctor

spec = importlib.util.spec_from_file_location('install_remotion_skills', ROOT / 'scripts/setup-remotion-skills.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work/test-runtime'
        parent.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.folder.cleanup)
        self.repo = Path(self.folder.name) / '새 PC 작업실'
        self.repo.mkdir()
        for name in ('studio-portability.json', 'connections.example.json'):
            target = self.repo / 'config' / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / 'config' / name, target)

    def test_fresh_pc_uses_cloud_master_without_copying_current_accounts(self):
        result = setup_portability.initialize(self.repo)
        data = studio.read_json(self.repo / '.local/connections.json')
        self.assertEqual(data['figma']['file_key'], 'mPb3wKOgVWcT7odiyd2WBc')
        self.assertFalse(data['figma']['edit_access_verified'])
        self.assertIsNone(data['flow']['expected_account_email'])
        self.assertFalse(result['credentials_copied'])

    def test_repeated_setup_preserves_machine_and_existing_connection_bytes(self):
        first = setup_portability.initialize(self.repo)
        private = self.repo / '.local/connections.json'
        private.write_text('{"existing_private_connection":true}', encoding='utf-8')
        before = private.read_bytes()
        second = setup_portability.initialize(self.repo)
        self.assertEqual(first['machine_id'], second['machine_id'])
        self.assertEqual(private.read_bytes(), before)

    def test_separate_pc_workspaces_receive_distinct_job_namespaces(self):
        first = setup_portability.initialize(self.repo)
        other = self.repo.parent / 'another-pc'
        shutil.copytree(self.repo / 'config', other / 'config')
        second = setup_portability.initialize(other)
        self.assertNotEqual(first['machine_id'], second['machine_id'])

    def test_approved_faces_and_sheets_work_without_private_local_directory(self):
        shutil.copyfile(ROOT / 'config/models.json', self.repo / 'config/models.json')
        shutil.copytree(ROOT / 'assets/models', self.repo / 'assets/models')
        _, available = models.profiles(self.repo)
        self.assertEqual(set(available), {'female-f01', 'male-m01'})
        self.assertFalse((self.repo / '.local').exists())

    def test_missing_runtime_does_not_claim_live_or_local_production_ready(self):
        result = doctor.inspect(self.repo)
        self.assertEqual(result['status'], 'local_setup_incomplete')
        self.assertFalse(result['production_ready'])
        self.assertFalse(result['production_generation_started'])
        self.assertIn('runtime_manifest', result['failed_checks'])

    def test_missing_pillow_reports_failure_instead_of_crashing_doctor(self):
        shutil.copyfile(ROOT / 'config/models.json', self.repo / 'config/models.json')
        shutil.copytree(ROOT / 'assets/models', self.repo / 'assets/models')
        real_import = __import__

        def missing_pillow(name, *args, **kwargs):
            if name == 'PIL':
                raise ModuleNotFoundError('No module named PIL')
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=missing_pillow):
            report = doctor.inspect(self.repo)
        self.assertIn('fixed_models', report['failed_checks'])
        self.assertFalse(report['production_ready'])


class MissingSkillInstallerTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work/test-runtime'
        parent.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.body = b'---\nname: remotion-create\ndescription: fixture\n---\n'
        self.lock = {'repository': 'remotion-dev/skills', 'commit': 'a' * 40,
                     'skills': [{'name': 'remotion-create', 'path': 'skills/remotion-create',
                                 'skill_sha256': __import__('hashlib').sha256(self.body).hexdigest()}]}
        self.lock_path = self.root / 'lock.json'
        studio.write_json(self.lock_path, self.lock)

    def archive(self, malicious=False, body=None):
        memory = io.BytesIO()
        prefix = f"skills-{self.lock['commit']}/skills/remotion-create/"
        with zipfile.ZipFile(memory, 'w') as archive:
            archive.writestr(prefix + 'SKILL.md', self.body if body is None else body)
            archive.writestr(prefix + ('../../escaped.txt' if malicious else 'references/example.md'), b'reference fixture')
        return io.BytesIO(memory.getvalue())

    def test_helperless_install_has_references_is_pinned_and_is_idempotent(self):
        dest = self.root / 'skills'
        with patch.object(installer.urllib.request, 'urlopen', return_value=self.archive()) as download:
            result = installer.install(self.lock_path, dest, self.root / 'missing-helper.py')
        self.assertEqual(result['skills'], 1)
        self.assertTrue((dest / 'remotion-create/references/example.md').is_file())
        self.assertIn(self.lock['commit'], download.call_args.args[0])
        with patch.object(installer.urllib.request, 'urlopen', side_effect=AssertionError('must not redownload')):
            installer.install(self.lock_path, dest, self.root / 'missing-helper.py')

    def test_archive_traversal_is_rejected_before_installing(self):
        dest = self.root / 'skills'
        with patch.object(installer.urllib.request, 'urlopen', return_value=self.archive(malicious=True)):
            with self.assertRaisesRegex(ValueError, 'escapes'):
                installer.install(self.lock_path, dest, self.root / 'missing-helper.py')
        self.assertFalse((dest / 'remotion-create').exists())
        self.assertFalse((dest / 'escaped.txt').exists())

    def test_hash_mismatch_is_rejected(self):
        with patch.object(installer.urllib.request, 'urlopen', return_value=self.archive(body=b'wrong skill')):
            with self.assertRaisesRegex(ValueError, 'differs'):
                installer.install(self.lock_path, self.root / 'skills', self.root / 'missing-helper.py')

    def test_existing_different_skill_is_preserved(self):
        path = self.root / 'skills/remotion-create/SKILL.md'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'existing user version')
        with self.assertRaisesRegex(ValueError, 'differs'):
            installer.install(self.lock_path, path.parent.parent, self.root / 'missing-helper.py')
        self.assertEqual(path.read_bytes(), b'existing user version')


if __name__ == '__main__':
    unittest.main()
