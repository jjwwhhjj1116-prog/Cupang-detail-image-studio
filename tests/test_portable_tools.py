"""Exercise the Windows installer trust boundaries with real ZIP/cache files."""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/setup-portable-tools.ps1'


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), 'Windows PowerShell required')
class PortableToolsTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work/test-runtime'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        def cleanup():
            resolved = Path(self.temp.name).resolve()
            resolved.relative_to(parent.resolve())  # Verify the recursive cleanup boundary.
            if resolved.exists():
                shutil.rmtree('\\\\?\\' + str(resolved))
            self.temp.cleanup()
        self.addCleanup(cleanup)
        self.repo = Path(self.temp.name) / '한글 PC 작업실'
        self.repo.mkdir()

    def run_ps(self, body):
        code = ("$ErrorActionPreference = 'Stop'; "
                "$OutputEncoding = [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false); "
                f". {ps_quote(SCRIPT)} -FunctionsOnly; " + body)
        encoded = base64.b64encode(code.encode('utf-16le')).decode('ascii')
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
            capture_output=True, text=True, encoding='utf-8', timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_verified_cache_reused_offline_with_unicode_paths(self):
        cache = self.repo / '.tools/downloads'
        cache.mkdir(parents=True)
        contents = b'cached official download fixture'
        digest = hashlib.sha256(contents).hexdigest()
        path = cache / (digest[:12] + '-package.zip')
        path.write_bytes(contents)
        result = self.run_ps(
            "$spec = [pscustomobject]@{filename='package.zip'; url='https://example.com/package.zip'; "
            f"sha256={ps_quote(digest)}}}; "
            f"$found = Get-StudioArchive $spec {ps_quote(self.repo)} -Offline; "
            "@{path=$found;hash=(Get-StudioHash $found)} | ConvertTo-Json -Compress"
        )
        self.assertEqual(Path(result['path']), path)
        self.assertEqual(result['hash'], digest)

    def test_corrupt_cache_is_preserved_and_never_used_offline(self):
        cache = self.repo / '.tools/downloads'
        cache.mkdir(parents=True)
        digest = hashlib.sha256(b'expected archive bytes').hexdigest()
        path = cache / (digest[:12] + '-package.zip')
        path.write_bytes(b'corrupt bytes')
        result = self.run_ps(
            "$spec = [pscustomobject]@{filename='package.zip'; url='https://example.com/package.zip'; "
            f"sha256={ps_quote(digest)}}}; "
            f"try {{ Get-StudioArchive $spec {ps_quote(self.repo)} -Offline; throw 'Unexpected success' }} "
            "catch { @{error=$_.Exception.Message} | ConvertTo-Json -Compress }"
        )
        self.assertIn('Offline:', result['error'])
        self.assertFalse(path.exists())
        invalid = list(cache.glob('*.invalid-*'))
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0].read_bytes(), b'corrupt bytes')

    def test_zip_traversal_rejected_before_any_extraction(self):
        archive = self.repo / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('safe.txt', 'safe')
            zipped.writestr('../escape.txt', 'unsafe')
        destination = self.repo / '.tools/stage'
        result = self.run_ps(
            f"try {{ Expand-StudioSafeZip {ps_quote(archive)} {ps_quote(destination)} {ps_quote(self.repo)}; throw 'Unexpected success' }} "
            "catch { @{error=$_.Exception.Message} | ConvertTo-Json -Compress }"
        )
        self.assertIn('Unsafe ZIP entry', result['error'])
        self.assertFalse(destination.exists())
        self.assertFalse((destination.parent / 'escape.txt').exists())

    def test_safe_zip_extracts_paths_longer_than_legacy_windows_limit(self):
        archive = self.repo / 'long.zip'
        relative = ('a' * 70) + '/' + ('b' * 70) + '/' + ('c' * 70) + '/proof.txt'
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr(relative, 'long path preserved')
        destination = self.repo / '.tools/long-stage'
        result = self.run_ps(
            f"Expand-StudioSafeZip {ps_quote(archive)} {ps_quote(destination)} {ps_quote(self.repo)}; "
            f"@{{hash=(Get-StudioHash {ps_quote(destination / relative)})}} | ConvertTo-Json -Compress"
        )
        self.assertGreater(len(str(destination / relative)), 260)
        self.assertEqual(result['hash'], hashlib.sha256(b'long path preserved').hexdigest())
        self.assertEqual(Path('\\\\?\\' + str(destination / relative)).read_text(), 'long path preserved')

    def test_similar_prefix_path_cannot_be_moved_outside_workspace(self):
        outside = self.repo.with_name(self.repo.name + '-outside') / 'target'
        result = self.run_ps(
            f"try {{ Assert-StudioChildPath {ps_quote(outside)} {ps_quote(self.repo)}; throw 'Unexpected success' }} "
            "catch { @{error=$_.Exception.Message} | ConvertTo-Json -Compress }"
        )
        self.assertIn('inside the intended workspace', result['error'])
        self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
