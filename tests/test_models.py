import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import models
import studio


class ModelBindingTests(unittest.TestCase):
    def setUp(self):
        runtime = ROOT / 'work/test-runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=runtime)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.workspace = self.root / 'job'
        self.workspace.mkdir()
        self.job = studio.read_json(ROOT / 'examples/demo-job.json')
        photo = self.workspace / self.job['product']['photos'][0]
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b'product fixture')
        self.job_path = self.workspace / 'job.json'
        studio.write_json(self.job_path, self.job)
        self.config = {'policy': 'fixed-pair', 'brands': ['와이홉', '유앤채'],
                       'default_wearing_assignment': {'lead-1': 'female-f01', 'lead-2': 'male-m01'}, 'models': []}
        for model_id, gender, status in [('female-f01', 'female', 'locked_by_user'), ('male-m01', 'male', 'candidate')]:
            source = self.repo / f'.local/{model_id}.png'
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(model_id.encode())
            self.config['models'].append({'id': model_id, 'gender': gender, 'revision': 1,
                'fictional_adult': True, 'concept_age': 25, 'selection_status': status,
                'reference_file': str(source.relative_to(self.repo)), 'sha256': studio.digest(source)})
        self.save_config()

    def save_config(self):
        studio.write_json(self.repo / 'config/models.json', self.config)

    def test_approved_subset_binds_exact_portrait_and_both_leads(self):
        result = models.bind(self.job_path, self.workspace, self.workspace / 'female.json', self.repo, ['female-f01'])
        binding = studio.read_json(result)['model_binding']
        self.assertEqual(binding['wearing_assignment'], {'lead-1': 'female-f01', 'lead-2': 'female-f01'})
        record = binding['profiles'][0]
        self.assertEqual(studio.digest(self.workspace / record['file']), self.config['models'][0]['sha256'])
        self.assertNotIn('model_binding', studio.read_json(self.job_path))

    def test_candidate_cannot_become_production_model_implicitly(self):
        with self.assertRaisesRegex(ValueError, 'candidate'):
            models.bind(self.job_path, self.workspace, self.workspace / 'pair.json', self.repo)
        self.assertFalse((self.workspace / 'pair.json').exists())

    def test_replaced_canonical_face_is_rejected(self):
        (self.repo / self.config['models'][0]['reference_file']).write_bytes(b'changed face')
        with self.assertRaisesRegex(ValueError, 'changed'):
            models.bind(self.job_path, self.workspace, self.workspace / 'pair.json', self.repo, ['female-f01'])

    def test_approved_pair_uses_correct_assignment_and_preserves_versions(self):
        self.config['models'][1]['selection_status'] = 'locked_by_user'
        self.save_config()
        output = self.workspace / 'pair.json'
        models.bind(self.job_path, self.workspace, output, self.repo)
        self.assertEqual(len(studio.read_json(output)['model_binding']['profiles']), 2)
        with self.assertRaisesRegex(ValueError, 'new job revision'):
            models.bind(self.job_path, self.workspace, output, self.repo)

    def test_output_cannot_escape_job_workspace(self):
        with self.assertRaisesRegex(ValueError, 'inside'):
            models.bind(self.job_path, self.workspace, self.root / 'outside.json', self.repo, ['female-f01'])


if __name__ == '__main__':
    unittest.main()
