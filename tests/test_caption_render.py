"""Optional real-render regression: the clean mode must contain no burned text or band."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import media
import studio


class CaptionRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = ROOT / ".tools/media-tools.json"
        cls.font = ROOT / ".tools/fonts/gmarket-sans/GmarketSansTTFBold.ttf"
        if not config.is_file() or not cls.font.is_file():
            raise unittest.SkipTest("Local FFmpeg and official Gmarket Bold fixtures are not installed")
        tools = studio.read_json(config)
        cls.ffmpeg, cls.ffprobe = tools["ffmpeg"], tools["ffprobe"]
        if not all(Path(path).is_file() for path in (cls.ffmpeg, cls.ffprobe)):
            raise unittest.SkipTest("Configured media tools are unavailable on this PC")

    def test_real_with_and_without_captions_preserve_copy_and_change_only_display(self):
        parent = ROOT / "work/test-runtime"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="caption-render-", dir=parent) as folder:
            workspace = Path(folder)
            source = workspace / "blue-source.mp4"
            media.run([self.ffmpeg, "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                       "color=c=0x14285A:s=384x216:r=30:d=5", "-an", "-c:v", "libx264",
                       "-pix_fmt", "yuv420p", source])
            lead = copy.deepcopy(studio.read_json(ROOT / "examples/demo-job.json")["leads"][0])
            for shot in lead["seconds"]:
                shot["overlay"] = {"anchor": "top-center", "font_size": 26}
            results = {}
            for mode in ("with-captions", "without-captions"):
                output = workspace / f"{mode}.mp4"
                media.assemble(lead, [source] * 5, output, 384, 216,
                               ffmpeg=self.ffmpeg, ffprobe=self.ffprobe,
                               style="fullbleed-motion", caption_band=0 if mode == "with-captions" else 76,
                               font_path=self.font if mode == "with-captions" else workspace / "missing.ttf",
                               caption_mode=mode)
                report = studio.read_json(output.with_suffix(".probe.json"))
                self.assertEqual(report["caption_mode"], mode)
                self.assertEqual(report["subtitles_burned_in"], mode == "with-captions")
                self.assertTrue(report["full_bleed"])
                self.assertEqual(report["caption_band_px"], 0)
                self.assertEqual(output.with_suffix(".source-captions.srt").read_text(encoding="utf-8"), studio.srt(lead))
                self.assertEqual(studio.read_json(output.with_suffix(".sources.json"))["caption_mode"], mode)
                self.assertEqual(output.with_suffix(".font.json").is_file(), mode == "with-captions")
                if mode == "without-captions":
                    self.assertEqual(output.with_suffix(".srt").read_text(encoding="utf-8"), "")
                    self.assertNotIn("Dialogue:", output.with_suffix(".ass").read_text(encoding="utf-8-sig"))
                    self.assertEqual(report["renderer"], "ffmpeg_without_text")
                    self.assertIsNone(report["font_postscript"])
                else:
                    self.assertTrue(studio.read_json(output.with_suffix(".font.json"))["fontselect"])
                frame = subprocess.run([self.ffmpeg, "-v", "error", "-ss", "0.5", "-i", str(output),
                                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                       check=True, capture_output=True).stdout
                self.assertEqual(len(frame), 384 * 216 * 3)
                pixels = [frame[i:i+3] for i in range(0, len(frame), 3)]
                results[mode] = {"bright": sum(min(p) > 180 for p in pixels),
                                 "black": sum(max(p) < 8 for p in pixels),
                                 "frame": frame}
            # A uniform blue input has neither white glyphs nor a black lower bar.
            self.assertEqual(results["without-captions"]["bright"], 0)
            self.assertEqual(results["without-captions"]["black"], 0)
            self.assertGreater(results["with-captions"]["bright"], 100)
            self.assertNotEqual(results["with-captions"]["frame"], results["without-captions"]["frame"])
            # The ordinary CLI must inherit the job's selection without a --font or mode override.
            job = studio.read_json(ROOT / "examples/demo-job.json")
            job["caption_mode"] = "without-captions"
            job_file, edit_map, inherited = workspace / "job.json", workspace / "edit-map.json", workspace / "inherited.mp4"
            studio.write_json(job_file, job)
            studio.write_json(edit_map, {"segments": [{"second": n, "start_seconds": n - 1} for n in range(1, 6)]})
            media.run([sys.executable, "-X", "utf8", ROOT / "scripts/media.py", job_file,
                       "--lead", "lead-1", "--source", source, "--edit-map", edit_map,
                       "--output", inherited, "--width", "384", "--height", "216",
                       "--style", "fullbleed-motion", "--mute", "--ffmpeg", self.ffmpeg, "--ffprobe", self.ffprobe])
            self.assertEqual(studio.read_json(inherited.with_suffix(".probe.json"))["caption_mode"], "without-captions")
            self.assertEqual(inherited.with_suffix(".srt").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
