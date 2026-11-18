import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts" / "install-hadi-skill.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(SHELL, "PowerShell is required")
class SkillInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hadi skill install ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "studio source"
        self.skill = self.repo / ".agents" / "skills" / "detail-page-production"
        (self.skill / "agents").mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("---\nname: detail-page-production\ndescription: fixture\n---\n", encoding="utf-8")
        (self.skill / "agents" / "openai.yaml").write_text("interface:\n  display_name: Hadi\n", encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("fixture", encoding="utf-8")
        self.dest = self.root / "skills with spaces" / "detail-page-production"

    def install(self, destination=None):
        return subprocess.run(
            [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(INSTALLER),
             "-StudioRoot", str(self.repo), "-Destination", str(destination or self.dest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )

    def test_fresh_install_registers_real_repo_and_ui_metadata(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        marker = json.loads((self.dest / "repo-location.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(Path(marker["repository_root"]), self.repo.resolve())
        self.assertEqual(marker["skill_name"], "detail-page-production")
        self.assertTrue((self.dest / "agents" / "openai.yaml").is_file())
        self.assertFalse((self.skill / "repo-location.json").exists())

    def test_managed_upgrade_keeps_backup_and_removes_stale_skill_files(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        (self.dest / "previous-only.txt").write_text("old", encoding="utf-8")
        (self.skill / "SKILL.md").write_text("updated skill", encoding="utf-8")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.dest / "SKILL.md").read_text(encoding="utf-8"), "updated skill")
        self.assertFalse((self.dest / "previous-only.txt").exists())
        backups = list((self.dest.parent.parent / "skill-install-backups").glob("detail-page-production-*"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(backups[0].is_relative_to(self.dest.parent))
        self.assertEqual(list(self.dest.parent.rglob("SKILL.md")), [self.dest / "SKILL.md"])
        self.assertEqual((backups[0] / "previous-only.txt").read_text(), "old")

    def test_unmanaged_existing_skill_is_preserved(self):
        self.dest.mkdir(parents=True)
        mine = self.dest / "SKILL.md"
        mine.write_text("my own skill", encoding="utf-8")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mine.read_text(), "my own skill")
        self.assertFalse((self.dest / "repo-location.json").exists())

    def test_repository_source_cannot_be_used_as_destination(self):
        result = self.install(self.skill)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.skill / "SKILL.md").exists())
        self.assertFalse((self.skill / "repo-location.json").exists())

    def test_update_rolls_back_if_stage_promotion_fails(self):
        # A managed installation must remain usable when the final rename fails.
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        old = (self.dest / "SKILL.md").read_bytes()
        (self.skill / "SKILL.md").write_text("replacement", encoding="utf-8")
        harness = self.root / "fail-promotion.ps1"
        harness.write_text(
            "function Move-Item {\n"
            "  [CmdletBinding()] param([string]$LiteralPath, [string]$Destination)\n"
            "  if ($LiteralPath -like '*.stage-*') { throw 'promotion blocked by fixture' }\n"
            "  Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination\n"
            "}\n"
            f"& '{str(INSTALLER).replace(chr(39), chr(39) * 2)}' "
            f"-StudioRoot '{str(self.repo).replace(chr(39), chr(39) * 2)}' "
            f"-Destination '{str(self.dest).replace(chr(39), chr(39) * 2)}'\n",
            encoding="utf-8",
        )
        result = subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                                capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.dest / "SKILL.md").read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
