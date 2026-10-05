"""Portable bundle integrity tests; signature-only MP4 fixtures do not prove playback."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from PIL import Image
import sample_delivery
import studio


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.nodes = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


class SampleDeliveryTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "work/test-runtime"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = studio.read_json(ROOT / "examples/demo-job.json")
        photo = self.root / self.job["product"]["photos"][0]
        photo.parent.mkdir(parents=True)
        Image.new("RGB", (100, 200), "white").save(photo)
        self.job_path = self.root / "job.json"
        studio.write_json(self.job_path, self.job)
        self.layout = {"leads": [], "template_preview": photo.relative_to(self.root).as_posix(),
                       "template_note": "합성 테스트용 정지 미리보기입니다. 영상은 포함되지 않습니다."}
        for index, lead in enumerate(self.job["leads"], 1):
            # Explicit synthetic fixture, only enough to exercise metadata/hash checks.
            video = self.root / f'원본 영상 {index}.mp4'
            video.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + bytes([index]))
            subtitle = video.with_suffix(".srt")
            subtitle.write_text(studio.srt(lead), encoding="utf-8")
            probe = video.with_suffix(".probe.json")
            studio.write_json(probe, {"artifact_sha256": studio.digest(video), "renderer": "synthetic_fixture",
                "after_effects_render": False, "metadata": {
                    "streams": [{"nb_read_frames": "150", "avg_frame_rate": "30/1", "width": 768, "height": 500}],
                    "format": {"duration": "5.000000"}}})
            self.layout["leads"].append({"id": lead["id"], "video": video.name,
                                         "subtitle": subtitle.name, "probe": probe.name})
        self.layout_path = self.root / "layout.json"
        studio.write_json(self.layout_path, self.layout)

    def build(self):
        studio.write_json(self.layout_path, self.layout)
        return sample_delivery.build(self.job_path, self.layout_path, self.root, self.root / "sample")

    def test_copied_bundle_has_portable_sources_and_full_player_controls(self):
        path = self.build()
        manifest = sample_delivery.validate_package(path)
        self.assertFalse(manifest["page_complete"])
        self.assertEqual(manifest["scope"], "lead-sample")
        page = (path.parent / "preview.html").read_text(encoding="utf8")
        nodes = Markup(page).nodes
        videos = [attrs for tag, attrs in nodes if tag == "video"]
        self.assertEqual(len(videos), 2)
        for attrs in videos:
            self.assertTrue({"autoplay", "muted", "loop", "playsinline", "controls"} <= attrs.keys())
        for tag, attrs in nodes:
            for key in ("src", "href"):
                ref = attrs.get(key, "")
                if ref and not ref.startswith("#"):
                    self.assertFalse(ref.startswith(("http:", "https:", "file:", "/", "..")))
                    self.assertTrue((path.parent / ref).is_file(), ref)
        self.assertIn("전체 상세페이지 제작 완료본은 아닙니다", page)
        self.assertNotIn(str(self.root), page)
        moved = self.root / "portable"
        shutil.copytree(path.parent, moved)
        self.assertEqual(sample_delivery.validate_package(moved / path.name)["job_id"], self.job["job_id"])

    def test_changed_video_or_srt_blocks_output_before_creation(self):
        video = self.root / self.layout["leads"][0]["video"]
        video.write_bytes(video.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "different footage"):
            self.build()
        self.assertFalse((self.root / "sample").exists())
        probe = self.root / self.layout["leads"][0]["probe"]
        evidence = studio.read_json(probe)
        evidence["artifact_sha256"] = studio.digest(video)
        studio.write_json(probe, evidence)
        subtitle = self.root / self.layout["leads"][0]["subtitle"]
        subtitle.write_text(subtitle.read_text(encoding="utf8").replace("00:00:01,000", "00:00:01,001", 1), encoding="utf8")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.build()
        self.assertFalse((self.root / "sample").exists())

    def test_markup_is_escaped_and_source_paths_cannot_escape(self):
        self.job["sections"][0]["text"] = '<img src=x onerror="alert(1)">'
        studio.write_json(self.job_path, self.job)
        self.layout["template_note"] = "<script>unsafe()</script>"
        path = self.build()
        page = (path.parent / "preview.html").read_text(encoding="utf8")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertEqual(sum(tag == "img" for tag, _ in Markup(page).nodes), 1)
        self.layout["leads"][0]["video"] = "../outside.mp4"
        studio.write_json(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, "Unsafe delivery path"):
            sample_delivery.build(self.job_path, self.layout_path, self.root, self.root / "new")

    def test_copied_asset_tampering_and_false_completion_are_rejected(self):
        path = self.build()
        manifest = studio.read_json(path)
        wrong = copy.deepcopy(manifest)
        wrong["page_complete"] = True
        studio.write_json(path, wrong)
        with self.assertRaisesRegex(ValueError, "cannot complete"):
            sample_delivery.validate_package(path)
        studio.write_json(path, manifest)
        subtitle = path.parent / manifest["leads"][0]["subtitle"]["file"]
        subtitle.write_text("changed", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "File changed"):
            sample_delivery.validate_package(path)


if __name__ == "__main__":
    unittest.main()
