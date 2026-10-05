import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import after_effects
import media
import studio
from typography import kinetic_design, fullbleed_design, display_caption


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

    def test_fullbleed_keeps_all_captions_without_band_and_requires_exact_font(self):
        lead = copy.deepcopy(self.job["leads"][0])
        lead["seconds"][0]["overlay"] = {"anchor": "bottom-left", "display_caption": "정면을\n확인해요"}
        result = media.ass(lead, 768, 432, style="fullbleed-motion")
        events = [line for line in result.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(events), 5)
        self.assertIn("G마켓 산스 TTF Bold", result)
        self.assertNotIn("Malgun Gothic", result)
        self.assertNotIn("\\p1", result)
        self.assertFalse(fullbleed_design(lead, 768, 432)["background_box"])
        self.assertTrue(events[0].endswith(r"정면을\N확인해요"))
        for index, line in enumerate(events):
            self.assertIn(f"0:00:0{index}.00,0:00:0{index+1}.00", line)
            self.assertNotIn("\\fad", line)
        with self.assertRaises(ValueError): media.ass(lead, 768, 432, 76, "fullbleed-motion")
        lead["seconds"][0]["overlay"]["display_caption"] = "새로운 판매 주장"
        with self.assertRaises(ValueError): fullbleed_design(lead, 768, 432)

    def test_single_source_segments_preserve_original_and_reject_overlap(self):
        lead = self.job["leads"][0]
        segments = [{"second": n, "start_seconds": (n-1)*1.5, "source_duration": 1.5,
                     "motion": "zoom-in" if n == 1 else "none"} for n in range(1, 6)]
        edited, starts, durations = media.single_source_plan(lead, segments)
        self.assertEqual(starts, [0, 1.5, 3, 4.5, 6])
        self.assertEqual(durations, [1.5] * 5)
        self.assertEqual([s["caption"] for s in edited["seconds"]], [s["caption"] for s in lead["seconds"]])
        self.assertNotIn("motion", lead["seconds"][0])
        segments[1]["start_seconds"] = 1
        with self.assertRaises(ValueError): media.single_source_plan(lead, segments)

    def test_editorial_has_two_independent_layers_and_retains_original_copy(self):
        lead = copy.deepcopy(self.job["leads"][0])
        original = lead["seconds"][0]["caption"]
        lead["seconds"][0]["overlay"] = {"mode": "editorial", "keyword": "와이홉", "support": "매일의 캡",
            "anchor": "top-left", "position": [.08,.2], "keyword_font_size": 70, "support_font_size": 20,
            "copy_change_reason": "User authorized fashion editorial copy; original preserved."}
        design = fullbleed_design(lead, 768, 432)
        shot = design["shots"][0]
        self.assertEqual(shot["caption"], original)
        self.assertEqual(display_caption(lead["seconds"][0]), "와이홉\n매일의 캡")
        self.assertEqual(lead["seconds"][0]["caption"], original)
        key, support = shot["text_layers"]
        self.assertLess(support["font_size"], key["font_size"])
        self.assertGreater(support["start"], key["start"])
        self.assertEqual(key["end"], support["end"])
        result = media.ass(lead, 768, 432, style="fullbleed-motion")
        self.assertIn("Dialogue: 2,0:00:00.00,0:00:01.00", result)
        self.assertIn("Dialogue: 3,0:00:00.06,0:00:01.00", result)
        self.assertIn(r"\bord0.45", result)
        self.assertNotIn("\\p1", result)
        self.assertIn("와이홉", media.rendered_srt(lead, design))
        self.assertIn(original, studio.srt(lead))

    def test_editorial_copy_changes_require_reason_and_valid_hierarchy(self):
        lead = copy.deepcopy(self.job["leads"][0])
        overlay = {"mode":"editorial", "keyword":"제품", "support":"설명"}
        lead["seconds"][0]["overlay"] = overlay
        with self.assertRaisesRegex(ValueError, "copy_change_reason"): display_caption(lead["seconds"][0])
        overlay["copy_change_reason"] = "Explicit edit"
        for bad in ({"position":[float("nan"), .1]}, {"position":[.1, .99]},
                    {"keyword_font_size":400}, {"keyword_font_size":60,"support_font_size":50},
                    {"color":"neon"}, {"enabled":"false"}, {"support": []}):
            lead["seconds"][0]["overlay"] = dict(overlay, **bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError): fullbleed_design(lead,768,432)

    def test_editorial_disabled_shot_does_not_silently_show_original(self):
        lead = copy.deepcopy(self.job["leads"][0])
        lead["seconds"][0]["overlay"] = {"mode":"editorial", "keyword":"제품", "support":"",
            "enabled":False, "copy_change_reason":"No safe background; preserve product view."}
        design = fullbleed_design(lead,768,432)
        self.assertEqual(design["shots"][0]["text_layers"], [])
        self.assertEqual(display_caption(lead["seconds"][0]), "")
        self.assertEqual(media.ass(lead,768,432,style="fullbleed-motion").count("Dialogue:"), 4)

    def test_editorial_text_is_escaped_and_ae_retains_independent_layers(self):
        lead = self.job["leads"][0]
        lead["seconds"][0]["overlay"] = {"mode":"editorial", "keyword":r"캡{\pos(0,0)}", "support":"확인",
            "copy_change_reason":"Synthetic escaping fixture", "keyword_font_size":28, "support_font_size":12}
        result = media.ass(lead,768,432,style="fullbleed-motion")
        self.assertIn(media.ass_escape(lead["seconds"][0]["overlay"]["keyword"]), result)
        studio.write_json(self.job_path, self.job)
        fake_font = self.root / "font.ttf"; fake_font.write_bytes(b"unit test only")
        with patch("after_effects.gmarket_font", return_value={"path":fake_font}):
            output = after_effects.build(self.job_path,self.root,self.map_path,self.root/"editorial.jsx",
                width=768,height=432,caption_band=0,allow_missing=True,style="fullbleed-motion",font_path=fake_font)
        report = studio.read_json(output.with_suffix(".ae-plan.json"))
        self.assertFalse(report["after_effects_rendered"])
        self.assertEqual(len(report["data"]["leads"][0]["shots"][0]["text_layers"]),2)
        self.assertIn("editorialText(comp",output.read_text(encoding="utf-8"))

    def test_fullbleed_ae_uses_one_source_per_lead_and_never_claims_render(self):
        mapping = {f"lead-{n}": {"source_file": f"source/lead-{n}-storyboard.mp4", "segments": [
            {"second": s, "start_seconds": (s-1)*1.5, "source_duration": 1.5} for s in range(1, 6)]} for n in (1, 2)}
        studio.write_json(self.map_path, mapping)
        fake_font = self.root / "font.ttf"
        fake_font.write_bytes(b"explicit unit-test fixture, not a real font")
        with patch("after_effects.gmarket_font", return_value={"path": fake_font}):
            output = after_effects.build(self.job_path, self.root, self.map_path, self.root / "v2.jsx",
                width=768, height=432, caption_band=0, allow_missing=True, style="fullbleed-motion", font_path=fake_font)
        report = studio.read_json(output.with_suffix(".ae-plan.json"))
        self.assertFalse(report["after_effects_rendered"])
        for lead in report["data"]["leads"]:
            self.assertEqual(len({shot["file"] for shot in lead["shots"]}), 1)
            self.assertEqual(lead["design"]["font_postscript"], "GmarketSansTTFBold")
        self.assertNotIn("addSolid", output.read_text(encoding="utf8"))

    def test_without_captions_has_no_events_font_or_caption_band(self):
        lead = copy.deepcopy(self.job["leads"][0])
        lead["caption_mode"] = "without-captions"
        lead["seconds"][0]["motion"] = "zoom-in"
        for style in ("plain", "kinetic", "fullbleed-motion"):
            script = media.ass(lead, 768, 432, 76, style)
            self.assertNotIn("Dialogue:", script)
            self.assertNotIn("Fontname", script)
        self.assertEqual(media.rendered_srt(lead), "")
        design = fullbleed_design(lead, 768, 432)
        self.assertIsNone(design["font_postscript"])
        self.assertEqual(design["caption_band"], 0)
        self.assertEqual(design["shots"][0]["motion"], "zoom-in")
        self.assertTrue(all(s["text_layers"] == [] for s in design["shots"]))
        # Explicit overrides take priority over inherited mode.
        self.assertIn("Dialogue:", media.ass(lead, 768, 432, style="fullbleed-motion", caption_mode="with-captions"))

    def test_without_captions_ae_uses_job_setting_and_does_not_read_font(self):
        self.job["caption_mode"] = "without-captions"
        studio.write_json(self.job_path, self.job)
        with patch("after_effects.gmarket_font", side_effect=AssertionError("Font must not be read")):
            output = after_effects.build(self.job_path, self.root, self.map_path, self.root / "clean.jsx",
                width=768, height=432, caption_band=76, allow_missing=True, style="fullbleed-motion",
                font_path=self.root / "nonexistent.ttf")
        report = studio.read_json(output.with_suffix(".ae-plan.json"))
        self.assertEqual(report["caption_mode"], "without-captions")
        self.assertFalse(report["after_effects_executed"])
        data = report["data"]
        self.assertFalse(data["text_layers_enabled"])
        self.assertNotIn("font_file", data)
        self.assertEqual(data["caption_band"], 0)
        for planned in data["leads"]:
            self.assertIsNone(planned["design"]["font_postscript"])
            self.assertTrue(all(s["text_layers"] == [] and s["display_caption"] == "" for s in planned["shots"]))
        self.assertIn('if (data.caption_mode === "without-captions") { continue; }', output.read_text(encoding="utf-8"))

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
