"""Cost/resume and provenance tests. Fixtures are synthetic, never provider QA."""
import copy
import shutil
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
            captions = studio.caption_mode(studio.read_json(path))
            checks = checks | {"full_bleed", "font", "overlay_product_clear", "source_storyboard"}
            source = self.root / f"assets/{item['id']}-source.mp4"
            probe = {
                "artifact_sha256": studio.digest(target), "full_bleed": True, "caption_band_px": 0,
                "style": "fullbleed-motion", "font_postscript": "GmarketSansTTFBold"}
            if captions == studio.WITHOUT_CAPTIONS:
                checks = (checks - {"subtitle_timing", "font", "overlay_product_clear"}) | {"caption_absence"}
                probe.update(caption_mode=captions, subtitles_burned_in=False, renderer="ffmpeg_without_text")
                probe.pop("font_postscript")
                lead = next(x for x in self.job["leads"] if x["id"] == item["id"])
                target.with_suffix(".source-captions.srt").write_text(studio.srt(lead), encoding="utf8")
            studio.write_json(target.with_suffix(".probe.json"), probe)
            studio.write_json(target.with_suffix(".sources.json"), {
                "artifact_sha256": studio.digest(target), "unique_source_files": 1, "caption_mode": captions,
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

    def test_no_caption_plan_persists_selection_without_mutating_input_and_rejects_drift(self):
        before = self.job_path.read_bytes()
        path = studio.plan(self.job_path, self.root, self.root / "without", scope="lead-sample",
                           requested_caption_mode=studio.WITHOUT_CAPTIONS)
        state = studio.load_state(path)
        self.assertEqual(self.job_path.read_bytes(), before)
        self.assertEqual(studio.read_json(state["job_path"])["caption_mode"], studio.WITHOUT_CAPTIONS)
        self.assertEqual([x["id"] for x in state["artifacts"]], ["lead-1-source", "lead-1", "lead-2-source", "lead-2"])
        self.assertFalse((path.parent / "lead-1.srt").exists())
        self.assertEqual((path.parent / "lead-1.source-captions.srt").read_text(encoding="utf8"), studio.srt(self.job["leads"][0]))
        self.assertEqual(path, studio.plan(self.job_path, self.root, path.parent, scope="lead-sample",
                                         requested_caption_mode=studio.WITHOUT_CAPTIONS))
        with self.assertRaisesRegex(ValueError, "different caption mode"):
            studio.plan(self.job_path, self.root, path.parent, scope="lead-sample", requested_caption_mode=studio.WITH_CAPTIONS)
        state["caption_mode"] = studio.WITH_CAPTIONS
        studio.write_json(path, state)
        with self.assertRaisesRegex(ValueError, "caption mode differs"):
            studio.load_state(path)

    def test_caption_variant_reuses_generation_slots_and_sources_but_requires_new_final_qa(self):
        sample_path = self.verified_sample()
        original = studio.load_state(sample_path)
        with patch.object(studio, "inspect_sample_video", return_value={"synthetic": True}):
            variant_path = studio.plan(self.job_path, self.root, self.root / "without-full", reuse_sample=sample_path,
                                       requested_caption_mode=studio.WITHOUT_CAPTIONS)
        variant = studio.load_state(variant_path)
        self.assertEqual(variant["generation_requests"], original["generation_requests"])
        self.assertEqual({x["id"] for x in variant["artifacts"] if x["status"] == "verified"}, {"lead-1-source", "lead-2-source"})
        self.assertFalse(any(x["kind"] == "subtitle" for x in variant["artifacts"]))
        with self.assertRaisesRegex(ValueError, "already reserved"):
            studio.generation_start(variant_path, "lead-1", "qa/lead-1-settings.json")
        with self.assertRaisesRegex(ValueError, "Artifact not verified"):
            studio.complete(variant_path)

    def test_unfinished_source_plan_variant_reuses_reserved_requests_without_new_paid_slots(self):
        original_path = self.plan()
        self.reserve(original_path, "lead-1")
        self.record_fixture(original_path, studio.load_state(original_path)["artifacts"][0])
        self.reserve(original_path, "lead-2")  # Result not yet reconciled; reservation must survive.
        original = studio.load_state(original_path)
        before = original_path.read_bytes()
        variant_path = studio.plan(self.job_path, self.root, self.root / "without-sample", scope="lead-sample",
                                   requested_caption_mode=studio.WITHOUT_CAPTIONS, reuse_source_plan=original_path)
        variant = studio.load_state(variant_path)
        self.assertEqual(before, original_path.read_bytes())
        self.assertEqual(variant["generation_requests"], original["generation_requests"])
        self.assertEqual({x["id"] for x in variant["artifacts"] if x["status"] == "verified"}, {"lead-1-source"})
        for lead in ("lead-1", "lead-2"):
            with self.subTest(lead=lead), self.assertRaisesRegex(ValueError, "already reserved"):
                studio.generation_start(variant_path, lead, f"qa/{lead}-settings.json")
        source = self.root / "assets/lead-1-source.mp4"
        source.write_bytes(source.read_bytes() + b"changed source")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            studio.plan(self.job_path, self.root, self.root / "bad-variant", scope="lead-sample", reuse_source_plan=original_path)

    def test_caption_variants_share_unsubmitted_origin_slots_and_cannot_duplicate_generation(self):
        original_path = self.plan()
        variants = [studio.plan(self.job_path, self.root, self.root / name, scope="lead-sample",
                                requested_caption_mode=studio.WITHOUT_CAPTIONS, reuse_source_plan=original_path)
                    for name in ("variant-a", "variant-b")]
        evidence = self.reserve(variants[0], "lead-1")
        self.assertEqual(studio.load_state(original_path)["generation_requests"][0]["status"], "reserved")
        with self.assertRaisesRegex(ValueError, "already reserved"):
            studio.generation_start(original_path, "lead-1", evidence)
        with self.assertRaisesRegex(ValueError, "already reserved"):
            studio.generation_start(variants[1], "lead-1", evidence)
        self.assertEqual(studio.load_state(variants[1])["generation_requests"][0]["status"], "reserved")

    def test_no_caption_completion_requires_renderer_absence_evidence_and_original_data(self):
        self.job["caption_mode"] = studio.WITHOUT_CAPTIONS
        studio.write_json(self.job_path, self.job)
        path = self.verified_sample()
        self.assertEqual(studio.load_state(path)["status"], "sample_verified")
        probe_path = self.root / "assets/lead-1.probe.json"
        probe = studio.read_json(probe_path)
        for changes in [{"subtitles_burned_in": True}, {"caption_mode": studio.WITH_CAPTIONS}, {"caption_band_px": 76}, {"renderer": "synthetic_no_proof"}]:
            studio.write_json(probe_path, {**probe, **changes})
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                studio.complete(path)
        studio.write_json(probe_path, probe)
        (self.root / "assets/lead-1.source-captions.srt").write_text("lost original", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "Original source captions"):
            studio.complete(path)

    def test_fixed_model_reference_and_state_binding_cannot_drift(self):
        profiles = []
        for model_id, gender in [("female-f01", "female"), ("male-m01", "male")]:
            ref = self.put(f"input/models/{model_id}.png", model_id.encode())
            profiles.append({"id": model_id, "gender": gender, "file": ref.relative_to(self.root).as_posix(), "sha256": studio.digest(ref)})
        self.job["model_binding"] = {"policy": "fixed-pair", "profiles": profiles,
                                     "wearing_assignment": {"lead-1": "female-f01", "lead-2": "male-m01"}, "identity_review_required": True}
        studio.write_json(self.job_path, self.job)
        path = self.plan()
        state = studio.load_state(path)
        self.assertEqual(state["model_binding"], self.job["model_binding"])
        state["model_binding"]["wearing_assignment"]["lead-1"] = "male-m01"
        studio.write_json(path, state)
        with self.assertRaisesRegex(ValueError, "fixed-model binding"):
            studio.load_state(path)
        studio.write_json(path, {**state, "model_binding": self.job["model_binding"]})
        self.put(profiles[0]["file"], b"different identity")
        with self.assertRaisesRegex(ValueError, "model reference changed"):
            studio.load_state(path)

    def remotion_fixture(self, state_path, lead_id):
        """Synthetic receipts exercise integrity only; they do not prove a real render."""
        from typography import fullbleed_design
        renderer = self.root / "renderer"
        files = ["src/index.ts", "src/Root.tsx", "src/Composition.tsx", "remotion.config.ts"]
        for name in files:
            self.put(f"renderer/{name}", b"Synthetic executable receipt fixture")
        studio.write_json(renderer / "package.json", {"dependencies": {"remotion": "99.0.1"}})
        studio.write_json(renderer / "node_modules/remotion/package.json", {"version": "99.0.1"})
        self.put("renderer/package-lock.json", b"Synthetic locked dependencies")
        state = studio.load_state(state_path)
        job = studio.read_json(state["job_path"])
        lead = next(x for x in job["leads"] if x["id"] == lead_id)
        captions = studio.caption_mode(job)
        output = self.root / f"assets/{lead_id}.mp4"
        sources = studio.read_json(output.with_suffix(".sources.json"))
        clean = self.put(f"assets/{lead_id}-clean.mp4", b"\x00\x00\x00\x18ftypisom Synthetic clean render fixture")
        clean_probe = {"artifact_sha256": studio.digest(clean), "caption_mode": studio.WITHOUT_CAPTIONS,
                       "subtitles_burned_in": False, "caption_band_px": 0, "full_bleed": True, "metadata": {
                           "streams": [{"width": 1280, "height": 720, "avg_frame_rate": "30/1", "nb_read_frames": "150"}],
                           "format": {"duration": "5.000000"}}}
        studio.write_json(clean.with_suffix(".probe.json"), clean_probe)
        studio.write_json(clean.with_suffix(".sources.json"), {**sources, "lead_id": lead_id, "artifact_sha256": studio.digest(clean)})
        clean.with_suffix(".source-captions.srt").write_text(studio.srt(lead), encoding="utf8")
        copied = renderer / f"public/{lead_id}/clean.mp4"
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(clean, copied)
        font = None
        if captions == studio.WITH_CAPTIONS:
            font = self.put(f"renderer/public/{lead_id}/GmarketSansTTFBold.ttf", b"Synthetic font fixture, font metadata explicitly mocked")
            studio.write_json(output.with_suffix(".font.json"), {
                "renderer": "remotion", "output_sha256": studio.digest(output), "font_postscript": "GmarketSansTTFBold",
                "font_sha256": studio.digest(font), "browser_font_face_load_verified": True})
        design = fullbleed_design(lead, 1280, 720, captions)
        props = {"sourceFile": f"{lead_id}/clean.mp4", "fontFile": f"{lead_id}/GmarketSansTTFBold.ttf" if font else None,
                 "captionMode": captions, "design": design}
        studio.write_json(output.with_suffix(".remotion-props.json"), props)
        output.with_suffix(".remotion.log").write_text("Synthetic successful render log, not actual execution", encoding="utf8")
        report = {"status": "rendered_visual_review_required", "renderer": "remotion", "caption_mode": captions,
                  "version": "99.0.1", "output_sha256": studio.digest(output), "clean_edit_sha256": studio.digest(clean),
                  "source_provenance_preserved": True, "generation_requests_submitted": 0,
                  "source_job_file": state["job_path"], "source_job_sha256": studio.digest(state["job_path"]), "lead_id": lead_id,
                  "props_sha256": studio.digest(output.with_suffix(".remotion-props.json")),
                  "render_log_sha256": studio.digest(output.with_suffix(".remotion.log")),
                  "clean_probe_sha256": studio.digest(clean.with_suffix(".probe.json")),
                  "clean_sources_sha256": studio.digest(clean.with_suffix(".sources.json")),
                  "project_sources": {name: studio.digest(renderer / name) for name in files + ["package.json"]},
                  "dependency_lock_sha256": studio.digest(renderer / "package-lock.json"),
                  "font_sha256": studio.digest(font) if font else None}
        studio.write_json(output.with_suffix(".remotion.json"), report)
        probe = studio.read_json(output.with_suffix(".probe.json"))
        probe.update(renderer="remotion", caption_mode=captions, subtitles_burned_in=captions == studio.WITH_CAPTIONS,
                     font_postscript="GmarketSansTTFBold" if font else None, clean_edit_sha256=studio.digest(clean),
                     overlay_design=design, remotion_report_sha256=studio.digest(output.with_suffix(".remotion.json")))
        studio.write_json(output.with_suffix(".probe.json"), probe)
        sources.update(renderer="remotion", clean_edit={"file": str(clean), "sha256": studio.digest(clean)})
        studio.write_json(output.with_suffix(".sources.json"), sources)
        output.with_suffix(".srt").write_text(studio.srt(lead, display=True) if captions == studio.WITH_CAPTIONS else "", encoding="utf8")
        return output, renderer

    def test_remotion_completion_requires_output_bound_execution_props_source_and_font_evidence(self):
        for captions in [studio.WITH_CAPTIONS, studio.WITHOUT_CAPTIONS]:
            with self.subTest(caption_mode=captions):
                self.job["caption_mode"] = captions
                studio.write_json(self.job_path, self.job)
                plan = studio.plan(self.job_path, self.root, self.root / captions, scope="lead-sample")
                for lead in ("lead-1", "lead-2"):
                    self.reserve(plan, lead)
                for item in studio.load_state(plan)["artifacts"]:
                    self.record_fixture(plan, item)
                fixtures = [self.remotion_fixture(plan, lead) for lead in ("lead-1", "lead-2")]
                with patch.object(studio, "REMOTION_ROOT", fixtures[0][1]), \
                        patch("typography.gmarket_font", return_value={"postscript": "GmarketSansTTFBold"}), \
                        patch.object(studio, "inspect_sample_video", return_value={"synthetic": True}):
                    for lead in ("lead-1", "lead-2"):
                        studio.record(plan, lead, f"assets/{lead}.mp4", f"qa/{lead}.json")
                    studio.complete(plan)
                    self.assertEqual(studio.load_state(plan)["status"], "sample_verified")
                    recorded = next(x for x in studio.load_state(plan)["artifacts"] if x["id"] == "lead-1")
                    self.assertIn("remotion_sha256", recorded)
                    output, renderer = fixtures[0]
                    # Even refreshed props/report hashes cannot alter approved typography.
                    props_path = output.with_suffix(".remotion-props.json")
                    props = studio.read_json(props_path)
                    props["design"]["shots"][0]["display_caption"] = "Unauthorized change"
                    studio.write_json(props_path, props)
                    report_path = output.with_suffix(".remotion.json")
                    report = studio.read_json(report_path)
                    report["props_sha256"] = studio.digest(props_path)
                    studio.write_json(report_path, report)
                    probe_path = output.with_suffix(".probe.json")
                    probe = studio.read_json(probe_path)
                    probe["remotion_report_sha256"] = studio.digest(report_path)
                    studio.write_json(probe_path, probe)
                    with self.assertRaisesRegex(ValueError, "typography props differ"):
                        studio.complete(plan)

    def test_renderer_name_alone_cannot_approve_remotion_without_real_receipt_files(self):
        self.job["caption_mode"] = studio.WITHOUT_CAPTIONS
        studio.write_json(self.job_path, self.job)
        plan = self.verified_sample()
        output = self.root / "assets/lead-1.mp4"
        probe_path = output.with_suffix(".probe.json")
        probe = studio.read_json(probe_path)
        probe.update(renderer="remotion", remotion_report_sha256="0" * 64)
        studio.write_json(probe_path, probe)
        with self.assertRaisesRegex(ValueError, "render evidence is missing"):
            studio.complete(plan)


if __name__ == "__main__":
    unittest.main()
