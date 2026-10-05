"""Install/check the pinned official Remotion skills with Codex's skill installer."""
import argparse
import os
import re
import subprocess
import sys
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from studio import digest, read_json, require


def download_missing(lock, destination, paths):
    """Fallback for Codex builds without the bundled installer helper; public pinned source only."""
    destination.mkdir(parents=True, exist_ok=True)
    # Stage beside the installation under its authorized workspace, using Windows
    # extended paths for upstream's deep references without changing system policy.
    def io_path(path):
        resolved = str(Path(path).resolve())
        if sys.platform == 'win32' and not resolved.startswith('\\\\?\\'):
            resolved = '\\\\?\\' + resolved
        return Path(resolved)

    with tempfile.TemporaryDirectory(prefix="rs-", dir=io_path(destination.parent)) as scratch:
        scratch = Path(scratch)
        archive = scratch / "source.zip"
        url = f"https://codeload.github.com/{lock['repository']}/zip/{lock['commit']}"
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as stream:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                require(total <= 64 * 1024 * 1024, "Skill source archive is unexpectedly large")
                stream.write(chunk)
        with zipfile.ZipFile(archive) as source:
            for skill_path in paths:
                skill = next(item for item in lock['skills'] if item['path'] == skill_path)
                stage = scratch / skill['name']
                stage.mkdir()
                prefix = f"skills-{lock['commit']}/{skill_path}/"
                selected = [entry for entry in source.infolist() if entry.filename.startswith(prefix)]
                require(selected, "Pinned skill directory is missing from upstream archive")
                require(sum(e.file_size for e in selected) <= 32 * 1024 * 1024, "Skill is unexpectedly large")
                for entry in selected:
                    relative = entry.filename[len(prefix):]
                    if not relative or entry.is_dir():
                        continue
                    require('\\' not in relative and not relative.startswith('/'), "Invalid archive path")
                    target = (stage / relative).resolve()
                    require(target.is_relative_to(stage.resolve()), "Skill archive path escapes its directory")
                    require((entry.external_attr >> 16) & 0o170000 != 0o120000, "Skill archive symlinks are unsupported")
                    io_path(target.parent).mkdir(parents=True, exist_ok=True)
                    with source.open(entry) as stream, io_path(target).open('wb') as output:
                        shutil.copyfileobj(stream, output)
                require((stage / 'SKILL.md').is_file() and digest(stage / 'SKILL.md') == skill['skill_sha256'],
                        "Downloaded skill differs from the pinned lock")
                target = destination / skill['name']
                require(not target.exists(), "Preserve an existing skill installation")
                io_path(stage).rename(io_path(target))


def install(lock_path, destination=None, installer=None, check_only=False):
    lock = read_json(lock_path)
    require(lock["repository"] == "remotion-dev/skills", "Only the official Remotion source is supported")
    require(re.fullmatch(r"[a-f0-9]{40}", lock["commit"]), "Expected a pinned upstream commit")
    codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    destination = Path(destination or codex_root / "skills").resolve()
    installer = Path(installer or codex_root / "skills/.system/skill-installer/scripts/install-skill-from-github.py")
    missing = []
    for skill in lock["skills"]:
        name = skill["name"]
        require(re.fullmatch(r"remotion-[a-z]+(?:-[a-z]+)*", name), "Invalid skill name")
        require(skill["path"] == "skills/" + name, "Skill path does not match its name")
        target = destination / name
        require(target.is_relative_to(destination), "Skill target escapes destination")
        if target.exists():
            require((target / "SKILL.md").is_file() and digest(target / "SKILL.md") == skill["skill_sha256"],
                    f"Installed {name} differs from this lock. Preserve it and select a deliberate update version.")
        else:
            missing.append(skill["path"])
    if check_only:
        require(not missing, f"Missing skills: {missing}")
    elif missing:
        if installer.is_file():
            runner = "import pathlib,runpy,sys;p=sys.argv.pop(1);sys.path.insert(0,str(pathlib.Path(p).parent));runpy.run_path(p,run_name='__main__')"
            subprocess.run([sys.executable, '-c', runner, str(installer), "--repo", lock["repository"], "--ref", lock["commit"],
                            "--dest", str(destination), "--path", *missing], check=True)
        else:
            download_missing(lock, destination, missing)
        return install(lock_path, destination, installer, True)
    return {"status": "installed_and_checked", "skills": len(lock["skills"]), "commit": lock["commit"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(Path(__file__).resolve().parents[1] / "config/remotion-skills.lock.json"))
    parser.add_argument("--dest"); parser.add_argument("--installer"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(install(args.lock, args.dest, args.installer, args.check))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")
