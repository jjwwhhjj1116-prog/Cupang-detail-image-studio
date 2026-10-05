"""Check reproducible local setup; never infer live Figma/Flow login or production completion."""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from models import profiles
from studio import digest, read_json, require, write_json
from typography import gmarket_font


def command(executable, *args):
    result = subprocess.run([str(executable), *args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=40)
    require(result.returncode == 0, f'Command failed: {Path(executable).name}')
    return result.stdout.strip()


def inspect(repo, runtime_path=None):
    repo = Path(repo).resolve()
    checks = []

    def check(name, operation):
        try:
            details = operation()
            checks.append({'name': name, 'status': 'pass', 'details': details})
        except (ValueError, OSError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
            checks.append({'name': name, 'status': 'fail', 'details': str(error)})

    runtime = {}
    toolchain = {}

    def load_runtime():
        source = read_json(runtime_path or repo / '.local/runtime.json')
        toolchain.update(read_json(repo / 'config/toolchain.lock.json'))
        require(Path(source['studio_root']).resolve() == repo, 'Runtime belongs to another PC workspace; run setup in this copy')
        require(source['toolchain_lock_sha256'] == digest(repo / 'config/toolchain.lock.json'),
                'Toolchain lock changed since setup; rerun setup-studio.ps1')
        runtime.update({'python': source['python']['path'], 'node': source['node']['path'],
                        'npm': source['node']['npm'], 'ffmpeg': source['ffmpeg']['path'],
                        'ffprobe': source['ffmpeg']['ffprobe'], 'font': source['font']['path']})
        require(all(runtime.get(key) for key in ('python', 'node', 'npm', 'ffmpeg', 'ffprobe', 'font')),
                'Run scripts/setup-studio.ps1 to create the local runtime manifest')
        return 'PC-specific paths loaded'

    check('runtime_manifest', load_runtime)
    check('python_and_pillow', lambda: command(runtime['python'], '-c',
          f"import sys,PIL; assert sys.version_info >= (3,11); assert PIL.__version__ == {toolchain['pillow']['version']!r}; print(sys.version.split()[0], PIL.__version__)"))
    check('node', lambda: command(runtime['node'], '-e',
          f'if(Number(process.versions.node.split(".")[0])<{int(toolchain["node"]["minimum_existing_major"])})process.exit(2);console.log(process.version)'))

    def media(tool):
        require(digest(runtime[tool]) == toolchain['ffmpeg'][tool + '_sha256'], f'Pinned {tool} binary changed')
        return command(runtime[tool], '-version').splitlines()[0]

    check('ffmpeg', lambda: media('ffmpeg'))
    check('ffprobe', lambda: media('ffprobe'))
    def font():
        verified = gmarket_font(runtime['font'])
        fingerprint = digest(verified['path'])
        require(fingerprint == 'ff7c354dd1a324e4cecc1223c4f71e74fa81be7027e0c7f6324c475909cacefc',
                'Gmarket Bold font differs from the approved version')
        return fingerprint

    check('gmarket_sans_bold', font)

    def model_assets():
        _, available = profiles(repo)
        from PIL import Image
        for model, portrait in available.values():
            for path in (portrait, repo / model['character_sheet']['file'], repo / model['expression_sheet']['file']):
                with Image.open(path) as image:
                    image.verify()
        return 'Six approved portrait/angle/expression images verified by SHA256 and image decode'

    check('fixed_models', model_assets)

    def skills():
        lock = read_json(repo / 'config/remotion-skills.lock.json')
        from studio import digest
        for skill in lock['skills']:
            path = repo / '.agents/skills' / skill['name'] / 'SKILL.md'
            require(path.is_file() and digest(path) == skill['skill_sha256'], f"Missing or changed skill: {skill['name']}")
        require((repo / '.agents/skills/detail-page-production/SKILL.md').is_file(), 'Missing production skill')
        return f"{len(lock['skills'])} official pinned Remotion skills plus the production skill"

    check('repository_skills', skills)

    def agents():
        names = read_json(repo / 'config/studio-portability.json')['agent_names']
        config = tomllib.loads((repo / '.codex/config.toml').read_text(encoding='utf-8-sig'))
        require(config['agents']['enabled'] is True, 'Project agents are disabled')
        for name in names:
            path = repo / '.codex/agents' / (name + '.toml')
            agent = tomllib.loads(path.read_text(encoding='utf-8-sig'))
            require(agent['name'] == name and agent['description'] and agent['developer_instructions'], 'Invalid agent definition')
        return {'definitions': names, 'activation': 'Open this repository in a new local Codex chat; client support verified there'}

    check('repository_agents', agents)

    def remotion():
        desired = read_json(repo / 'remotion/package.json')['dependencies']
        for name, version in desired.items():
            installed = read_json(repo / 'remotion/node_modules' / name / 'package.json')['version']
            require(installed == version, f'Remotion dependency version mismatch: {name}')
        require((repo / 'remotion/node_modules/@remotion/cli/remotion-cli.js').is_file(), 'Missing rendering CLI')
        return {'remotion': desired['remotion'], 'react': desired['react']}

    check('remotion_runtime', remotion)

    def browser():
        # This internal path is inspected against the repository's pinned Remotion version.
        # It checks the installed revision without triggering a download during doctor.
        script = ("const p=require('path');const f=require(p.join(p.dirname(require.resolve('@remotion/renderer')),'browser/BrowserFetcher.js'));"
                  "const r=f.getRevisionInfo('headless-shell');if(f.readVersionFile('headless-shell')!==f.TESTED_VERSION)process.exit(2);"
                  "console.log(r.executablePath);")
        result = subprocess.run([runtime['node'], '-e', script], cwd=repo / 'remotion',
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        require(result.returncode == 0, 'Remotion rendering browser is not installed; run setup-studio.ps1')
        executable = result.stdout.strip()
        require(Path(executable).is_file(), 'Rendering browser binary is missing')
        return 'Local Remotion rendering browser present'

    check('rendering_browser', browser)

    def local_connections():
        data = read_json(repo / '.local/connections.json')
        require(data['figma']['file_key'] and data['figma']['template_page_id'], 'Missing owned master binding')
        machine = read_json(repo / '.local/machine.json')
        require(machine['machine_id'].startswith('pc-'), 'Missing PC job namespace')
        return {'machine_id': machine['machine_id'], 'live_authentication_checked': False}

    check('workspace_binding', local_connections)
    failures = [item['name'] for item in checks if item['status'] == 'fail']
    return {'schema_version': 1, 'status': 'local_setup_ready' if not failures else 'local_setup_incomplete',
            'checks': checks, 'failed_checks': failures, 'production_ready': False,
            'live_verification_required': ['Codex built-in image generation tool', 'Figma plugin and master edit access',
                                           'Flow signed-in account and available credits', 'browser upload capability'],
            'production_generation_started': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--runtime')
    parser.add_argument('--output')
    args = parser.parse_args()
    report = inspect(args.repo, args.runtime)
    if args.output:
        output = Path(args.output).resolve()
        require(output.is_relative_to(Path(args.repo).resolve() / '.local'), 'Doctor report belongs in the ignored .local directory')
        write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['status'] == 'local_setup_ready' else 2)
