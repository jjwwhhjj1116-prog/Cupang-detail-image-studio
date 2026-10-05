import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import after_effects
import media
import studio
from typography import kinetic_design


class TypographyTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "work/test-runtime"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = studio.read_json(ROOT / "examples/demo-job.json")
        photo = self.root / self.job["product"]["photos"][0]
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b"synthetic test reference")
        self.job_path = self.root / "job.json"
        studio.write_json(self.job_path, self.job)
        self.mapping = {f"lead-{n}": [{"file": f"source/lead-{n}-{second}.mp4", "start_seconds": .2}
                                      for second in range(1, 6)] for n in (1, 2)}
        self.map_path = self.root / "media-map.json"
        studio.write_json(self.map_path, self.mapping)

    def test_kinetic_keeps_complete_captions_and_exact_blocks(self):
        lead = self.job["leads"][0]
        design = kinetic_design(lead, 768, 500, 76)
        result = media.ass(lead, 768, 500, 76, style="kinetic")
        main_lines = [line for line in result.splitlines() if line.startswith("Dialogue: 1,")]
        self.assertEqual(len(main_lines), 5)
        for index, line in enumerate(main_lines):
            self.assertTrue(line.endswith(lead["seconds"][index]["caption"]))
            self.assertIn(f"0:00:0{index}.00,0:00:0{index+1}.00", line)
            self.assertNotIn("\\fad", line)
            self.assertNotIn("\\move", line)
        self.assertTrue(design["sample_creative_not_brand_standard"])
        self.assertEqual([(shot["start"], shot["end"]) for shot in design["shots"]], [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)])

    def test_kinetic_rejects_invented_keyword_and_missing_band(self):
        lead = copy.deepcopy(self.job["leads"][0])
        with self.assertRaises(ValueError): kinetic_design(lead, 768, 500, 0)
        lead["seconds"][0]["accent_keyword"] = "전혀없는주장"
        with self.assertRaises(ValueError): kinetic_design(lead, 768, 500, 76)

    def test_ae_retime_preserves_selected_source_window_and_offset(self):
        self.mapping["lead-2"][4].update(start_seconds=.25, source_duration=.5)
        studio.write_json(self.map_path, self.mapping)
        result = after_effects.build(self.job_path, self.root, self.map_path, self.root / "retime.jsx", allow_missing=True)
        shot = studio.read_json(result.with_suffix(".ae-plan.json"))["data"]["leads"][1]["shots"][4]
        self.assertEqual(shot["source_duration"], .5)
        self.assertEqual(shot["time_stretch_percent"], 200)
        start_time = shot["start"] - shot["source_start"] / shot["source_duration"]
        self.assertAlmostEqual((shot["start"] - start_time) * .5, .25)
        self.assertLess((shot["end"] - 1 / 30 - start_time) * .5, .75)
        text = result.read_text(encoding="utf8")
        self.assertIn("layer.stretch = shot.time_stretch_percent", text)
        self.assertIn("FrameBlendingType.NO_FRAME_BLEND", text)
        for invalid in (0, -1, float("nan"), float("inf"), .01, 101):
            self.mapping["lead-2"][4]["source_duration"] = invalid
            studio.write_json(self.map_path, self.mapping)
            with self.assertRaisesRegex(ValueError, "Source duration"):
                after_effects.build(self.job_path, self.root, self.map_path, self.root / "bad.jsx", allow_missing=True)

    def test_ae_builder_marks_missing_sources_and_never_claims_execution(self):
        output = self.root / "build.jsx"
        with self.assertRaises(ValueError): after_effects.build(self.job_path, self.root, self.map_path, output)
        self.assertFalse(output.exists())
        after_effects.build(self.job_path, self.root, self.map_path, output, allow_missing=True)
        report = studio.read_json(output.with_suffix(".ae-plan.json"))
        self.assertEqual(len(report["missing_sources"]), 10)
        self.assertEqual(report["comp_count"], 2)
        self.assertFalse(report["after_effects_executed"])
        self.assertFalse(report["aep_created"])
        self.assertFalse(report["after_effects_rendered"])
        self.assertEqual(sum(len(lead["shots"]) for lead in report["data"]["leads"]), 10)
        self.assertFalse(output.with_suffix(".aep").exists())

    def test_ae_payload_preserves_source_offsets_and_full_captions(self):
        for clips in self.mapping.values():
            for entry in clips:
                path = self.root / entry["file"]
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"synthetic unit fixture; not real video")
        output = after_effects.build(self.job_path, self.root, self.map_path, self.root / "build.jsx")
        report = studio.read_json(output.with_suffix(".ae-plan.json"))
        self.assertEqual(report["missing_sources"], [])
        for original, planned in zip(self.job["leads"], report["data"]["leads"]):
            self.assertEqual([s["caption"] for s in original["seconds"]], [s["caption"] for s in planned["shots"]])
            self.assertEqual([s["source_start"] for s in planned["shots"]], [.2] * 5)
        with self.assertRaises(ValueError): after_effects.build(self.job_path, self.root, self.map_path, output)

    def test_ae_rejects_workspace_escape_and_duplicate_lead_map(self):
        self.mapping["lead-1"][0]["file"] = "../private.mp4"
        studio.write_json(self.map_path, self.mapping)
        with self.assertRaises(ValueError): after_effects.build(self.job_path, self.root, self.map_path, self.root / "bad.jsx", allow_missing=True)
        studio.write_json(self.map_path, {"lead-1": self.mapping["lead-1"]})
        with self.assertRaises(ValueError): after_effects.build(self.job_path, self.root, self.map_path, self.root / "bad.jsx", allow_missing=True)


if __name__ == "__main__":
    unittest.main()
