"""Initialize PC-specific workspace settings without copying credentials or overwriting connections."""
import argparse
import uuid
from pathlib import Path

from studio import read_json, require, write_json


def initialize(repo):
    repo = Path(repo).resolve()
    common = read_json(repo / 'config/studio-portability.json')
    local = repo / '.local'
    local.mkdir(exist_ok=True)
    machine_path = local / 'machine.json'
    if machine_path.exists():
        machine = read_json(machine_path)
        require(isinstance(machine.get('machine_id'), str) and machine['machine_id'].startswith('pc-'),
                'Invalid existing machine configuration; preserve it for review')
    else:
        machine = {'schema_version': 1, 'machine_id': 'pc-' + uuid.uuid4().hex[:12],
                   'job_id_pattern': 'YYYYMMDD-<machine_id>-<product_slug>',
                   'one_owner_pc_per_active_job': True}
        write_json(machine_path, machine)
    connection_path = local / 'connections.json'
    if not connection_path.exists():
        connections = read_json(repo / 'config/connections.example.json')
        connections['figma'].update({key: common['figma'][key] for key in ('file_key', 'template_page_id', 'url')})
        connections['figma'].update({'edit_access_verified': False, 'local_master_path': None,
                                    'mode': 'reuse_owned_cloud_master_duplicate_per_product',
                                    'do_not_change_source_sharing': True})
        connections['flow'].update({'url': common['connections']['flow_url'], 'account_verified_at': None})
        write_json(connection_path, connections)
    return {'machine_id': machine['machine_id'], 'connections': str(connection_path),
            'credentials_copied': False, 'existing_connections_preserved': True,
            'live_connections_require_verification': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    print(initialize(args.repo))
