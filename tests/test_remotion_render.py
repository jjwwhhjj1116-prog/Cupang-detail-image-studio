import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import remotion_render
import studio


class RemotionPreparationTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'work/test-runtime'
        parent.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.job = studio.read_json(ROOT / 'examples/demo-job.json')
        self.source = self.root / 'clean.mp4'
        self.source.write_bytes(b'unit fixture only, not rendered media')
        self.fingerprint = studio.digest(self.source)
        self.metadata = {'artifact_sha256':self.fingerprint, 'caption_mode':'without-captions',
            'subtitles_burned_in':False, 'caption_band_px':0, 'full_bleed':True,
            'metadata':{'streams':[{'nb_read_frames':'150','avg_frame_rate':'30/1','width':1280,'height':720}],
                        'format':{'duration':'5.000'}}}
        self.sources = {'artifact_sha256':self.fingerprint, 'lead_id':'lead-1', 'unique_source_files':2,
            'sources':[{'file':'prior-product.mp4','sha256':'a'*64}, {'file':'new-fashion.mp4','sha256':'b'*64}]}
        studio.write_json(self.source.with_suffix('.probe.json'), self.metadata)
        studio.write_json(self.source.with_suffix('.sources.json'), self.sources)
        self.source.with_suffix('.source-captions.srt').write_text(studio.srt(self.job['leads'][0]), encoding='utf-8')

    def test_preserves_original_composite_provenance_and_modes(self):
        for mode in ('with-captions','without-captions'):
            _, actual, design, original, fingerprint = remotion_render.prepare(self.job,'lead-1',self.source,mode)
            self.assertEqual(actual,mode)
            self.assertEqual(original,self.sources)
            self.assertEqual(original['unique_source_files'],2)
            self.assertEqual(fingerprint,self.fingerprint)
            self.assertEqual(design['caption_mode'],mode)

    def test_rejects_baked_text_wrong_dimensions_or_unbound_metadata(self):
        for change in ({'caption_mode':'with-captions'}, {'subtitles_burned_in':True},
                       {'caption_band_px':76}, {'artifact_sha256':'c'*64}, {'full_bleed':False}):
            studio.write_json(self.source.with_suffix('.probe.json'), dict(self.metadata,**change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                remotion_render.prepare(self.job,'lead-1',self.source)
        metadata = copy.deepcopy(self.metadata)
        metadata['metadata']['streams'][0]['width']=768
        studio.write_json(self.source.with_suffix('.probe.json'), metadata)
        with self.assertRaises(ValueError): remotion_render.prepare(self.job,'lead-1',self.source)


if __name__ == '__main__': unittest.main()
