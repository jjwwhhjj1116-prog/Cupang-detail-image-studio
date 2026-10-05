"""Delivery contract tests with synthetic assets, not provider/media quality tests."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import delivery
import media
import studio


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "work" / "test-runtime"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        (self.root / "qa").mkdir()
        # A small but valid 780px-wide PNG; no image-generation quality claim.
        self.image = "assets/상품 이미지.png"
        def chunk(kind,data):
            return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
        png=(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",780,1,8,2,0,0,0))
             +chunk(b"IDAT",zlib.compress(b"\x00"+b"\xff\xff\xff"*780))+chunk(b"IEND",b""))
        (self.root / self.image).write_bytes(png)
        self.lead = {"seconds": [{"second":i,"caption":f"한글 자막 {i}"} for i in range(1,6)]}
        videos, subtitles = [], []
        for n in (1,2):
            name=f"lead-{n}"
            # Deliberately a signature-only MP4 fixture: no claim of decoding or playback.
            video=f"assets/{name}.mp4"
            (self.root / video).write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"+bytes([n]))
            probe=f"assets/{name}.probe.json"
            self.write(probe,{"artifact_sha256":delivery.sha(self.root/video),"metadata":{
                "streams":[{"nb_read_frames":"150","avg_frame_rate":"30/1","width":688,"height":400}],
                "format":{"duration":"5.0"}}})
            videos.append({"id":name,"kind":"video","file":video,"probe_file":probe,"width":688,"height":400,"section_ids":[]})
            subtitle=f"assets/{name}.srt"
            (self.root/subtitle).write_text(studio.srt(self.lead),encoding="utf8")
            subtitles.append({"lead_id":name,"file":subtitle})
        self.qa={"checks":[{"name":name,"status":"pass","evidence":"Synthetic test fixture; not actual production review"}
                            for name in sorted(delivery.REQUIRED_QA)]}
        self.write("qa/bundle.json",self.qa)
        self.expected_job=studio.read_json(ROOT/"examples/demo-job.json")
        self.expected_job.update(job_id="delivery-test",brand="와이홉",type=6,video_mode=studio.LEGACY_VIDEO)
        self.expected_job["product"]={"photos":[self.image],"confirmed_facts":["두 가지 색상"]}
        self.expected_job["sections"].extend([
            {"id":"6-16","kind":"image","text":"두 가지 색상. 실측 정보 미제공.","assets":[
                {"asset_id":"color-black","image_prompt":"제공된 검정색 제품 보존"},
                {"asset_id":"color-white","image_prompt":"제공된 흰색 제품 보존"}]},
            {"id":"6-17","kind":"text","text":"확인된 사실에 기반한 다섯 문답"},
            {"id":"6-18","kind":"text","text":"6-17 프레임 내부 제품 정보"}])
        studio.validate(self.expected_job,self.root)
        self.layout={"job_id":"delivery-test","brand":"와이홉","type":6,"width":780,
                     "figma_url":"https://www.figma.com/design/Abcd1234/Synthetic",
                     "items":[videos[0],videos[1],{"id":"6-7","kind":"image","file":self.image,
                       "section_ids":[s["id"] for s in self.expected_job["sections"]]}],
                     "subtitles":subtitles,"qa_file":"qa/bundle.json",
                     "composition_assets":["hero","color-black","color-white"]+
                       [f"lead-{lead}-frame-{second:02d}" for lead in (1,2) for second in range(1,6)]}
        self.layout_path=self.write("layout.json",self.layout)

    def write(self, relative, data):
        path=self.root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
        return path

    def build(self):
        self.write("layout.json",self.layout)
        return delivery.build(self.layout_path,self.root,self.root/"delivery",expected_job=self.expected_job)

    def rewrite_manifest(self, path, manifest):
        path.write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf8")

    def test_complete_manifest_integrity_and_playable_markup(self):
        path=self.build()
        manifest=delivery.validate_manifest(path,self.root,expected_job=self.expected_job)
        self.assertEqual([x["id"] for x in manifest["items"]],["lead-1","lead-2","6-7"])
        self.assertEqual([x["lead_id"] for x in manifest["subtitles"]],["lead-1","lead-2"])
        html=(self.root/manifest["preview"]["file"]).read_text(encoding="utf8")
        self.assertEqual(html.count("<video "),2)
        self.assertEqual(html.count("<img "),1)
        self.assertIn("controls playsinline",html)
        self.assertIn("%20",html)
        self.assertTrue(all(len(x["sha256"])==64 for x in manifest["items"]))

    def test_complete_section_and_multi_asset_coverage_required(self):
        path=self.build();good=delivery.read(path)
        self.assertEqual(len(good["composition_assets"]),13)
        missing_section=copy.deepcopy(good);missing_section["items"][-1]["section_ids"].remove("6-18")
        unknown_section=copy.deepcopy(good);unknown_section["items"][-1]["section_ids"].append("6-99")
        missing_color=copy.deepcopy(good);missing_color["composition_assets"].remove("color-white")
        missing_still=copy.deepcopy(good);missing_still["composition_assets"].remove("lead-2-frame-05")
        duplicate_asset=copy.deepcopy(good);duplicate_asset["composition_assets"].append("hero")
        for bad in [missing_section,unknown_section,missing_color,missing_still,duplicate_asset]:
            with self.subTest(manifest=bad):
                self.rewrite_manifest(path,bad)
                with self.assertRaises(ValueError):
                    delivery.validate_manifest(path,self.root,expected_job=self.expected_job)

    def test_incomplete_leads_subtitles_or_static_sections_are_rejected(self):
        path=self.build();good=delivery.read(path)
        bads=[]
        no_video=copy.deepcopy(good);no_video["items"].pop(1);bads.append(no_video)
        no_static=copy.deepcopy(good);no_static["items"]=[x for x in no_static["items"] if x["kind"]=="video"];bads.append(no_static)
        no_subs=copy.deepcopy(good);no_subs["subtitles"].pop();bads.append(no_subs)
        backwards=copy.deepcopy(good);backwards["items"][:2]=reversed(backwards["items"][:2]);bads.append(backwards)
        for bad in bads:
            with self.subTest(items=[x["id"] for x in bad["items"]],subs=len(bad["subtitles"])):
                self.rewrite_manifest(path,bad)
                with self.assertRaises(ValueError):delivery.validate_manifest(path,self.root)

    def test_changed_media_and_mismatched_probe_cannot_reuse_evidence(self):
        path=self.build();manifest=delivery.read(path)
        video=manifest["items"][0];clip=self.root/video["file"]
        clip.write_bytes(clip.read_bytes()+b"mutated")
        with self.assertRaisesRegex(ValueError,"File changed"):
            delivery.validate_manifest(path,self.root)
        # Refreshing only the asset hash cannot reuse the old footage's probe.
        video["sha256"]=delivery.sha(clip);self.rewrite_manifest(path,manifest)
        with self.assertRaisesRegex(ValueError,"different footage"):
            delivery.validate_manifest(path,self.root)

    def test_subtitle_boundaries_and_path_escape_rejected(self):
        path=self.build();manifest=delivery.read(path)
        sub=manifest["subtitles"][0];subtitle=self.root/sub["file"]
        subtitle.write_text(studio.srt(self.lead).replace("00:00:01,000","00:00:01,050",1),encoding="utf8")
        sub["sha256"]=delivery.sha(subtitle);self.rewrite_manifest(path,manifest)
        with self.assertRaisesRegex(ValueError,"five one-second"):
            delivery.validate_manifest(path,self.root)
        sub["file"]="../outside.srt";self.rewrite_manifest(path,manifest)
        with self.assertRaisesRegex(ValueError,"Unsafe delivery path"):
            delivery.validate_manifest(path,self.root)

    def test_failed_missing_or_empty_qa_is_rejected_even_with_fresh_hash(self):
        path=self.build();manifest=delivery.read(path)
        cases=[]
        missing=copy.deepcopy(self.qa);missing["checks"].pop();cases.append(missing)
        failed=copy.deepcopy(self.qa);failed["checks"][0]["status"]="fail";cases.append(failed)
        empty=copy.deepcopy(self.qa);empty["checks"][0]["evidence"]="  ";cases.append(empty)
        cases.append({"checks":[None]})
        for qa in cases:
            with self.subTest(qa=qa):
                qpath=self.write("qa/bundle.json",qa)
                manifest["qa"]["sha256"]=delivery.sha(qpath);self.rewrite_manifest(path,manifest)
                with self.assertRaises(ValueError):delivery.validate_manifest(path,self.root)

    def test_empty_subtitles_and_wrong_image_width_are_rejected(self):
        path=self.build();manifest=delivery.read(path)
        subtitle=manifest["subtitles"][0]
        source=self.root/subtitle["file"]
        source.write_text("\n\n".join(f"{i}\n00:00:0{i-1},000 --> 00:00:0{i},000" for i in range(1,6)),encoding="utf8")
        subtitle["sha256"]=delivery.sha(source);self.rewrite_manifest(path,manifest)
        with self.assertRaisesRegex(ValueError,"caption is empty"):
            delivery.validate_manifest(path,self.root)
        source.write_text(studio.srt(self.lead),encoding="utf8")
        subtitle["sha256"]=delivery.sha(source)
        manifest["width"]=781;self.rewrite_manifest(path,manifest)
        with self.assertRaisesRegex(ValueError,"width differs"):
            delivery.validate_manifest(path,self.root)

    def test_caption_and_html_content_cannot_create_extra_instructions(self):
        # Caption line breaks must stay inside one ASS event, even if text looks like one.
        lead=copy.deepcopy(self.lead)
        lead["seconds"][0]["caption"]="제품 {\\an8}\nDialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,주입"
        ass=media.ass(lead,688,400)
        events=[line for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertEqual(len(events),5)
        self.assertIn(r"\NDialogue:",events[0])
        self.assertNotIn(r"{\an8}",events[0])
        self.layout["items"][2]["id"]='<script>alert("x")</script>'
        manifest=delivery.read(self.build())
        html=(self.root/manifest["preview"]["file"]).read_text(encoding="utf8")
        self.assertNotIn("<script>",html)
        self.assertIn("&lt;script&gt;",html)
        self.assertIn("&quot;",html)

    def test_v2_composition_does_not_require_ten_generated_stills(self):
        self.expected_job["video_mode"] = studio.SINGLE_VIDEO
        self.expected_job["leads"][0]["seconds"][0]["overlay"] = {
            "mode": "editorial", "keyword": "형식 예시", "support": "", "copy_change_reason": "Synthetic approved copy"}
        self.layout["composition_assets"] = ["hero", "color-black", "color-white"]
        for lead, sub in zip(self.expected_job["leads"], self.layout["subtitles"]):
            path = self.root / sub["file"]
            path.write_text(studio.srt(lead, display=True), encoding="utf8")
            path.with_suffix(".source-captions.srt").write_text(studio.srt(lead), encoding="utf8")
        path = self.build()
        manifest = delivery.validate_manifest(path, self.root, expected_job=self.expected_job)
        self.assertEqual(manifest["video_mode"], studio.SINGLE_VIDEO)
        self.assertEqual(manifest["composition_assets"], ["hero", "color-black", "color-white"])
        original = self.root / manifest["subtitles"][0]["source_subtitle"]["file"]
        original.write_text("changed original", encoding="utf8")
        manifest["subtitles"][0]["source_subtitle"]["sha256"] = studio.digest(original)
        self.rewrite_manifest(path, manifest)
        with self.assertRaisesRegex(ValueError, "source captions"):
            delivery.validate_manifest(path, self.root, expected_job=self.expected_job)


if __name__=="__main__":unittest.main()
