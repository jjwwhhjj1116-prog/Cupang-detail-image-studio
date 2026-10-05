"""Cost/resume and provenance tests. Fixtures are synthetic, never provider QA."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import studio


class SingleSourceTests(unittest.TestCase):
    def setUp(self):
        temp = ROOT / "work/test-runtime"
        temp.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = studio.read_json(ROOT / "examples/demo-job.json")
        self.job.pop("video_mode", None)  # An unspecified NEW plan must use v2.
        self.job_path = self.root / "job.json"
        for photo in self.job["product"]["photos"]:
            self.put(photo, b"synthetic reference")
        studio.write_json(self.job_path, self.job)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def plan(self):
        return studio.plan(self.job_path, self.root, self.root / "plan", scope="lead-sample")

    def reserve(self, path, lead):
        ui = self.put(f"qa/{lead}-settings.png", b"synthetic settings screenshot")
        evidence = f"qa/{lead}-settings.json"
        studio.write_json(self.root / evidence, {
            "provider": "Google Flow", "model": "Synthetic model fixture", "output_count": 1,
            "source_duration_seconds": 8, "credit_cost_ui": "Synthetic cost fixture",
            "ui_evidence_file": ui.relative_to(self.root).as_posix(), "ui_evidence_sha256": studio.digest(ui)})
        studio.generation_start(path, lead, evidence)
        return evidence

    def record_fixture(self, path, item):
        suffix = ".srt" if item["kind"] == "subtitle" else ".mp4"
        name = f"assets/{item['id']}{suffix}"
        if item["kind"] == "subtitle":
            lead = next(x for x in self.job["leads"] if x["id"] == item["lead_id"])
            target = self.put(name, studio.srt(lead, display=True).encode("utf8"))
            target.with_suffix(".source-captions.srt").write_text(studio.srt(lead), encoding="utf8")
        else:
            target = self.put(name, b"\x00\x00\x00\x18ftypisom" + item["id"].encode())
        checks = studio.CHECKS[item["kind"]]
        qa = {"artifact_sha256": studio.digest(target)}
        if item["kind"] == "source-video":
            qa.update(generation_request_id=f"{item['lead_id']}-generation-01", provider_result_id="synthetic-result",
                      request_count=1, output_count=1)
        if item["kind"] == "video":
            checks = checks | {"full_bleed", "font", "overlay_product_clear", "source_storyboard"}
            source = self.root / f"assets/{item['id']}-source.mp4"
            studio.write_json(target.with_suffix(".probe.json"), {
                "artifact_sha256": studio.digest(target), "full_bleed": True, "caption_band_px": 0,
                "style": "fullbleed-motion", "font_postscript": "GmarketSansTTFBold"})
            studio.write_json(target.with_suffix(".sources.json"), {
                "artifact_sha256": studio.digest(target), "unique_source_files": 1,
                "sources": [{"second": i, "file": str(source), "sha256": studio.digest(source)} for i in range(1, 6)]})
            studio.write_json(target.with_suffix(".font.json"), {
                "font_postscript": "GmarketSansTTFBold", "fontselect": ["Synthetic GmarketSansTTFBold fixture"]})
        qa["checks"] = [{"name": x, "status": "pass", "evidence": "Synthetic state test only"} for x in sorted(checks)]
        qa_file = f"qa/{item['id']}.json"
        studio.write_json(self.root / qa_file, qa)
        studio.record(path, item["id"], name, qa_file)

    def verified_sample(self):
        path = self.plan()
        for lead in ("lead-1", "lead-2"):
            self.reserve(path, lead)
        for item in studio.read_json(path)["artifacts"]:
            self.record_fixture(path, item)
        with patch.object(studio, "inspect_sample_video", return_value={"synthetic": True}):
            studio.complete(path)
        return path

    def test_default_plan_has_two_request_slots_and_two_distinct_source_final_pairs(self):
        path = self.plan()
        state = studio.load_state(path)
        self.assertEqual(state["video_mode"], studio.SINGLE_VIDEO)
        self.assertEqual([x["id"] for x in state["artifacts"]],
                         ["lead-1-source", "lead-1-subtitles", "lead-1", "lead-2-source", "lead-2-subtitles", "lead-2"])
        tasks = studio.read_json(path.parent / "flow-tasks.json")["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(x["max_submissions"] == x["output_count"] == 1 for x in tasks))
        self.assertTrue(all(x["source_asset_id"] != x["final_asset_id"] for x in tasks))
        self.assertEqual(len(list((path.parent / "prompts").glob("*.txt"))), 2)
        timeline = studio.read_json(path.parent / "timeline.json")["tasks"]
        self.assertEqual({x["source_asset_id"] for x in timeline}, {"lead-1-source", "lead-2-source"})
        self.assertTrue(all("image_asset_id" not in x for x in timeline))

    def test_reserved_unknown_outcome_resumes_without_extra_generation(self):
        path = self.plan()
        evidence = self.reserve(path, "lead-1")
        before = path.read_bytes()
        self.assertEqual(path, self.plan())
        self.assertEqual(before, path.read_bytes())
        with self.assertRaisesRegex(ValueError, "already reserved"):
            studio.generation_start(path, "lead-1", evidence)
        self.assertEqual(len(studio.load_state(path)["generation_requests"]), 2)
        with self.assertRaises(ValueError):
            studio.plan(self.job_path, self.root, path.parent, scope="lead-sample", mode=studio.LEGACY_VIDEO)

    def test_source_cannot_be_registered_without_reservation_or_with_batch_output(self):
        path = self.plan()
        item = studio.read_json(path)["artifacts"][0]
        with self.assertRaisesRegex(ValueError, "Reserve"):
            self.record_fixture(path, item)
        self.reserve(path, "lead-1")
        qa_path = self.root / "qa/lead-1-source.json"
        qa = studio.read_json(qa_path)
        qa["output_count"] = 5
        studio.write_json(qa_path, qa)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            studio.record(path, item["id"], "assets/lead-1-source.mp4", "qa/lead-1-source.json")

    def test_x1_ui_evidence_and_unchanged_screenshot_are_required(self):
        path = self.plan()
        evidence = self.reserve(path, "lead-1")
        self.put("qa/lead-1-settings.png", b"different UI image")
        with self.assertRaisesRegex(ValueError, "screenshot changed"):
            studio.load_state(path)
        proof = studio.read_json(self.root / evidence)
        proof["output_count"] = 4
        studio.write_json(self.root / evidence, proof)
        with self.assertRaises(ValueError):
            studio.validate_generation_evidence(self.root, {"evidence_file": evidence, "evidence_sha256": studio.digest(self.root / evidence)})

    def test_reference_images_are_reusable_max_five_and_hash_bound(self):
        for i in range(1, 8):
            self.put(f"refs/{i}.png", f"synthetic {i}".encode())
        self.job["product"]["photos"] = [f"refs/{i}.png" for i in range(1, 8)]
        self.assertEqual(studio.lead_references(self.job, self.job["leads"][0]), self.job["product"]["photos"][:5])
        self.job["leads"][0]["reference_images"] = ["refs/6.png", "refs/7.png"]
        self.job["leads"][1]["reference_images"] = ["refs/6.png"]
        studio.write_json(self.job_path, self.job)
        path = self.plan()
        self.put("refs/7.png", b"changed product")
        with self.assertRaises(ValueError): studio.load_state(path)
        for bad in [[], ["refs/1.png"] * 2, [f"refs/{i}.png" for i in range(1, 7)], ["../escape.png"]]:
            self.job["leads"][0]["reference_images"] = bad
            with self.subTest(references=bad), self.assertRaises(ValueError): studio.validate(self.job)

    def test_legacy_state_without_mode_resumes_unchanged(self):
        path = studio.plan(self.job_path, self.root, self.root / "old-plan", scope="lead-sample", mode=studio.LEGACY_VIDEO)
        state = studio.read_json(path)
        state.pop("video_mode")
        studio.write_json(path, state)
        before = path.read_bytes()
        studio.plan(self.job_path, self.root, path.parent, scope="lead-sample")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(studio.load_state(path)["artifacts"]), 24)
        self.assertFalse((path.parent / "flow-tasks.json").exists())

    def test_full_resume_reuses_all_six_artifacts_and_consumed_request_slots(self):
        path = self.verified_sample()
        sample = studio.read_json(path)
        self.assertEqual(sample["status"], "sample_verified")
        self.assertFalse(sample["page_complete"])
        with patch.object(studio, "inspect_sample_video", return_value={"synthetic": True}):
            full = studio.plan(self.job_path, self.root, self.root / "full-plan", reuse_sample=path)
        state = studio.load_state(full)
        self.assertEqual(state["generation_requests"], sample["generation_requests"])
        self.assertEqual(sum(x["status"] == "verified" for x in state["artifacts"]), 6)
        self.assertEqual({x["id"] for x in state["artifacts"] if x["status"] == "pending"}, {"hero", "detail-page"})
        with self.assertRaisesRegex(ValueError, "already reserved"):
            studio.generation_start(full, "lead-1", "qa/lead-1-settings.json")

    def test_wrong_font_band_or_different_source_blocks_v2_completion(self):
        path = self.verified_sample()
        probe_path = self.root / "assets/lead-1.probe.json"
        probe = studio.read_json(probe_path)
        for key, value in [("caption_band_px", 76), ("font_postscript", "MalgunGothicBold"), ("full_bleed", False)]:
            studio.write_json(probe_path, {**probe, key: value})
            with self.subTest(field=key), self.assertRaises(ValueError): studio.complete(path)
        studio.write_json(probe_path, probe)
        source_path = self.root / "assets/lead-1.sources.json"
        sources = studio.read_json(source_path)
        sources["sources"][4]["file"] = str(self.root / "assets/lead-2-source.mp4")
        studio.write_json(source_path, sources)
        with self.assertRaisesRegex(ValueError, "does not match"):
            studio.complete(path)

    def test_sidecar_edits_or_policy_removal_cannot_bypass_verification(self):
        path = self.verified_sample()
        font_path = self.root / "assets/lead-1.font.json"
        font = studio.read_json(font_path)
        studio.write_json(font_path, {**font, "changed": True})
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            studio.complete(path)
        state = studio.read_json(path)
        state["artifacts"][0].pop("video_mode")
        studio.write_json(path, state)
        with self.assertRaisesRegex(ValueError, "policy changed"):
            studio.load_state(path)

    def test_editorial_copy_is_explicit_and_original_captions_cannot_be_lost(self):
        self.job["leads"][0]["seconds"][0]["overlay"] = {
            "mode": "editorial", "keyword": "가벼운 시작", "support": "가상 형식 예시",
            "copy_change_reason": "Synthetic authorized editorial copy for unit test; no factual claim."}
        studio.write_json(self.job_path, self.job)
        path = self.plan()
        lead = self.job["leads"][0]
        self.assertIn("가벼운 시작\n가상 형식 예시", (path.parent / "lead-1.srt").read_text(encoding="utf8"))
        self.assertEqual((path.parent / "lead-1.source-captions.srt").read_text(encoding="utf8"), studio.srt(lead))
        item = next(x for x in studio.read_json(path)["artifacts"] if x["id"] == "lead-1-subtitles")
        self.record_fixture(path, item)
        source = self.root / "assets/lead-1-subtitles.source-captions.srt"
        source.write_text("lost original", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "Original source captions"):
            studio.record(path, item["id"], "assets/lead-1-subtitles.srt", "qa/lead-1-subtitles.json")


if __name__ == "__main__":
    unittest.main()
