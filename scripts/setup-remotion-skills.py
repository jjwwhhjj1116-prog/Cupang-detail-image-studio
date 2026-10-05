"""Install/check the pinned official Remotion skills with Codex's skill installer."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from studio import digest, read_json, require


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
        require(installer.is_file(), "Codex skill-installer helper is missing; provide --installer")
        subprocess.run([sys.executable, str(installer), "--repo", lock["repository"], "--ref", lock["commit"],
                        "--dest", str(destination), "--path", *missing], check=True)
        return install(lock_path, destination, installer, True)
    return {"status": "installed_and_checked", "skills": len(lock["skills"]), "commit": lock["commit"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(Path(__file__).resolve().parents[1] / "config/remotion-skills.lock.json"))
    parser.add_argument("--dest"); parser.add_argument("--installer"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(install(args.lock, args.dest, args.installer, args.check))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")
