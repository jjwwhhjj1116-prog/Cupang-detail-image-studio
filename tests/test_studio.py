import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import studio
import media


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.job = studio.read_json(ROOT / "examples" / "demo-job.json")
        temp_root = ROOT / "work" / "test-runtime"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        photo = self.root / self.job["product"]["photos"][0]
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b"test reference placeholder; not a real photo")
        self.job_path = self.root / "job.json"
        studio.write_json(self.job_path, self.job)

    def test_valid_schema_and_exact_timeline(self):
        state_path = studio.plan(self.job_path, self.root, self.root / "plan")
        timeline = studio.read_json(self.root / "plan/timeline.json")
        self.assertEqual(len(timeline["tasks"]), 10)
        self.assertEqual([(s["start_frame"], s["end_frame"]) for s in timeline["tasks"][:5]],
                         [(0, 30), (30, 60), (60, 90), (90, 120), (120, 150)])
        self.assertEqual(len(studio.read_json(state_path)["artifacts"]), 14)
        self.assertIn("00:00:04,000 --> 00:00:05,000", (self.root / "plan/lead-1.srt").read_text(encoding="utf-8"))

    def test_reject_invalid_brands_types_and_ids(self):
        for key, value in [("brand", "other"), ("type", True), ("type", 8), ("type", 1.0), ("job_id", "../escape")]:
            job = copy.deepcopy(self.job)
            job[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                studio.validate(job)

    def test_reject_missing_duplicate_reordered_seconds(self):
        for values in [[1, 2, 3, 4], [1, 2, 3, 4, 4], [2, 1, 3, 4, 5], [True, 2, 3, 4, 5]]:
            job = copy.deepcopy(self.job)
            job["leads"][0]["seconds"] = [dict(job["leads"][0]["seconds"][0], second=n) for n in values]
            with self.subTest(values=values), self.assertRaises(ValueError):
                studio.validate(job)

    def test_reject_empty_captions_and_missing_lead(self):
        self.job["leads"][0]["seconds"][0]["caption"] = " "
        with self.assertRaises(ValueError): studio.validate(self.job)
        self.job["leads"].pop()
        with self.assertRaises(ValueError): studio.validate(self.job)

    def test_reject_duplicate_sections_and_reserved_assets(self):
        self.job["sections"].append(copy.deepcopy(self.job["sections"][0]))
        with self.assertRaises(ValueError): studio.validate(self.job)
        self.job["sections"].pop()
        self.job["sections"][-1]["asset_id"] = "detail-page"
        with self.assertRaises(ValueError): studio.validate(self.job)

    def test_multi_image_sections_plan_every_slot_and_block_missing_assets(self):
        self.job["sections"].append({"id": "6-8", "kind": "image", "text": "가상 활용 이미지 다섯 개", "assets": [
            {"asset_id": f"usage-{n}", "image_prompt": f"확인 사진에 근거한 활용 {n}", "slot_id": f"123:{n}"}
            for n in range(1, 6)]})
        studio.write_json(self.job_path, self.job)
        path = studio.plan(self.job_path, self.root, self.root / "plan")
        state = studio.read_json(path)
        self.assertEqual(len(state["artifacts"]), 19)
        self.assertTrue({f"usage-{n}" for n in range(1, 6)} <= {item["id"] for item in state["artifacts"]})
        tasks = studio.read_json(self.root / "plan/image-tasks.json")
        self.assertEqual([item["slot_id"] for item in tasks if item["section_id"] == "6-8"], [f"123:{n}" for n in range(1, 6)])
        for n in range(1, 6):
            self.assertTrue((self.root / f"plan/prompts/usage-{n}.txt").is_file())
        state["artifacts"] = [item for item in state["artifacts"] if item["id"] != "usage-5"]
        studio.write_json(path, state)
        with self.assertRaises(ValueError): studio.complete(path)

    def test_multi_image_asset_ids_slots_and_prompts_must_be_valid(self):
        base = {"id": "6-8", "kind": "image", "text": "가상 활용", "assets": [
            {"asset_id": "usage-a", "image_prompt": "이미지 A", "slot_id": "123:1"},
            {"asset_id": "usage-b", "image_prompt": "이미지 B", "slot_id": "123:2"}]}
        cases = []
        for key, value in [("asset_id", "usage-a"), ("asset_id", "hero"), ("asset_id", "lead-1"),
                           ("image_prompt", ""), ("slot_id", "123:1")]:
            section = copy.deepcopy(base)
            section["assets"][1][key] = value
            cases.append(section)
        cases.extend([dict(base, assets=[]), dict(base, asset_id="ambiguous")])
        for section in cases:
            job = copy.deepcopy(self.job)
            job["sections"].append(section)
            with self.subTest(section=section), self.assertRaises(ValueError): studio.validate(job)

    def test_paths_stay_inside_workspace(self):
        for path in ["../secret", "a/../../secret", "/tmp/secret", "C:\\secret", "\\\\server\\share", "https://example.com/x"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                studio.relative_path(path, self.root)
        self.assertEqual(studio.relative_path("input\\photo.png"), "input/photo.png")

    def test_missing_reference_blocks_plan(self):
        (self.root / self.job["product"]["photos"][0]).unlink()
        with self.assertRaises(ValueError): studio.plan(self.job_path, self.root, self.root / "plan")

    def test_ingest_preserves_source_and_does_not_pretend_ready(self):
        source = "원문 앞부분\n## 6-1) 리드\n1. 동작\n2. 동작\n\n6-2) 리드2\n내용\n6-18) 제품정보\n정보"
        path = self.root / "prompt.txt"
        path.write_text(source, encoding="utf-8")
        output = self.root / "draft.json"
        studio.ingest(path, output, "demo", "와이홉", 6)
        draft = studio.read_json(output)
        self.assertEqual(draft["source_prompt"], source)
        self.assertEqual([s["id"] for s in draft["sections"]], ["6-1", "6-2", "6-18"])
        with self.assertRaises(ValueError): studio.validate(draft)

    def test_plan_is_resumable_and_rejects_changed_job(self):
        path = studio.plan(self.job_path, self.root, self.root / "plan")
        self.assertEqual(path, studio.plan(self.job_path, self.root, self.root / "plan"))
        self.job["brand"] = "유앤채"
        studio.write_json(self.job_path, self.job)
        with self.assertRaises(ValueError): studio.plan(self.job_path, self.root, self.root / "plan")

    def test_missing_assets_cannot_complete(self):
        path = studio.plan(self.job_path, self.root, self.root / "plan")
        with self.assertRaises(ValueError): studio.complete(path)

    def test_modified_reference_photo_invalidates_plan(self):
        path = studio.plan(self.job_path, self.root, self.root / "plan")
        (self.root / self.job["product"]["photos"][0]).write_bytes(b"different product reference")
        with self.assertRaises(ValueError): studio.load_state(path)

    def test_completion_requires_hash_bound_qa_and_detects_later_edits(self):
        # Delivery content validation has its own tests; isolate state integrity here.
        identity = {key: self.job[key] for key in ("job_id", "brand", "type")}
        bundle_validator = Mock(return_value=identity)
        stub = SimpleNamespace(validate_manifest=bundle_validator)
        self.enterContext(patch.dict(sys.modules, {"delivery": stub}))
        path = studio.plan(self.job_path, self.root, self.root / "plan")
        for item in studio.read_json(path)["artifacts"]:
            artifact = f"assets/{item['id']}.bin"
            target = self.root / artifact
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(item["id"].encode())
            qa_file = f"qa/{item['id']}.json"
            studio.write_json(self.root / qa_file, {"artifact_sha256": studio.digest(target), "checks": [
                {"name": name, "status": "pass", "evidence": "Synthetic unit-test evidence only"}
                for name in studio.CHECKS[item["kind"]]]})
            studio.record(path, item["id"], artifact, qa_file)
        studio.complete(path)
        self.assertEqual(bundle_validator.call_count, 2)
        self.assertEqual(bundle_validator.call_args.kwargs["expected_job"], self.job)
        self.assertEqual(studio.read_json(path)["status"], "complete")
        (self.root / "assets/hero.bin").write_bytes(b"changed")
        with self.assertRaises(ValueError): studio.complete(path)
        self.assertEqual(studio.read_json(path)["status"], "needs_review")

    def test_delivery_from_other_job_is_rejected(self):
        target = self.root / "manifest.json"
        target.write_text("{}", encoding="utf-8")
        (self.root / "qa.json").write_text("{}", encoding="utf-8")
        stub = SimpleNamespace(validate_manifest=lambda path, root, expected_job=None: {"job_id": "another"})
        with patch.dict(sys.modules, {"delivery": stub}), self.assertRaises(ValueError):
            studio.verify_evidence(self.root, {"kind": "export"}, "manifest.json", "qa.json", {"job_id": "expected"})

    def test_failed_or_incomplete_qa_rejected(self):
        target = self.root / "result.png"
        target.write_bytes(b"placeholder")
        for checks in [[], [{"name": "product_fidelity", "status": "fail", "evidence": "bad"}],
                       [{"name": "product_fidelity", "status": "pass", "evidence": "partial"}]]:
            studio.write_json(self.root / "qa.json", {"artifact_sha256": studio.digest(target), "checks": checks})
            with self.assertRaises(ValueError):
                studio.verify_evidence(self.root, {"kind": "image"}, "result.png", "qa.json")

    def test_video_metadata_is_exact(self):
        good = {"streams": [{"nb_read_frames": "150", "avg_frame_rate": "30/1", "width": 780, "height": 780}],
                "format": {"duration": "5.000"}}
        media.check_video(good, 150, 780, 780)
        for field, value in [("nb_read_frames", "149"), ("avg_frame_rate", "30000/1001"), ("width", 781)]:
            bad = copy.deepcopy(good)
            bad["streams"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): media.check_video(bad, 150, 780, 780)
        good["format"]["duration"] = "8.000"
        with self.assertRaises(ValueError): media.check_video(good, 150, 780, 780)

    def test_subtitle_boundaries_and_korean_font(self):
        output = media.ass(self.job["leads"][0], 780, 780)
        self.assertEqual(output.count("Dialogue:"), 5)
        self.assertIn("0:00:04.00,0:00:05.00", output)
        self.assertIn("Malgun Gothic", output)
        self.assertIn("\\{", media.ass_escape("{tag}"))


if __name__ == "__main__":
    unittest.main()
