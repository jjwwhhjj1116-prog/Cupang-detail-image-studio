"""Synthetic local fixtures validate the delivery contract, not a live Hadi/Figma run."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import static_delivery


class StaticDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / "delivery"
        self.dest.mkdir()
        (self.root / "prompt").mkdir()
        (self.root / "prompt/hadi-final.md").write_text("Synthetic Hadi fixture", encoding="utf-8")
        for name, size, color in [
            ("representative.png", (400, 400), "white"),
            ("detail-page.png", (780, 1200), "#dddddd"),
            ("product-information.png", (780, 400), "#eeeeee")]:
            Image.new("RGB", size, color).save(self.dest / name)
        def asset(name):
            return {"file": name, "sha256": static_delivery.sha(self.dest / name)}
        self.manifest = {
            "schema_version": 1, "profile": "hadi-four-set",
            "job_id": "20261118-pc-test-product", "brand": "유앤채", "type": 2,
            "template_width": 780,
            "prompt": {"file": "prompt/hadi-final.md",
                       "sha256": static_delivery.sha(self.root / "prompt/hadi-final.md"),
                       "source": "hadi-gpt"},
            "figma": {"url": "https://www.figma.com/design/TestKey/?node-id=100-2",
                      "file_key": "TestKey", "node_id": "100:2",
                      "product_info_node_id": "100:3"},
            "representatives": [asset("representative.png")],
            "detail": asset("detail-page.png"), "label": asset("product-information.png")}
        hashes = [self.manifest["representatives"][0]["sha256"],
                  self.manifest["detail"]["sha256"], self.manifest["label"]["sha256"]]
        self.qa = {"artifacts": hashes,
                   "checks": [{"name": name, "status": "passed",
                               "evidence": "Synthetic fixture evidence, not live service proof"}
                              for name in static_delivery.REQUIRED_CHECKS]}

    def validate(self):
        qa_path = self.root / "qa.json"
        qa_path.write_text(json.dumps(self.qa), encoding="utf-8")
        self.manifest["qa"] = {"file": "qa.json", "sha256": static_delivery.sha(qa_path)}
        path = self.dest / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return static_delivery.validate(path, self.root)

    def test_valid_four_set(self):
        report = self.validate()
        self.assertEqual(report["file_checks"], "passed")
        self.assertFalse(report["live_services_verified_by_script"])
        self.assertEqual(len(report["pngs"]), 3)

    def test_missing_representative_and_wrong_width(self):
        self.manifest["representatives"] = []
        with self.assertRaises(ValueError):
            self.validate()
        self.setUp()
        self.manifest["template_width"] = 900
        with self.assertRaises(ValueError):
            self.validate()

    def test_figma_node_and_file_must_match_url(self):
        for field, value in (("node_id", "100:99"), ("file_key", "WrongKey"),
                             ("url", "https://figma.com.evil.test/design/TestKey/?node-id=100-2")):
            with self.subTest(field=field):
                original = self.manifest["figma"][field]
                self.manifest["figma"][field] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.manifest["figma"][field] = original

    def test_stale_qa_and_empty_evidence_rejected(self):
        self.qa["artifacts"] = []
        with self.assertRaises(ValueError):
            self.validate()
        self.setUp()
        self.qa["checks"][0]["evidence"] = ""
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_detail_label_rejected(self):
        self.manifest["label"] = self.manifest["detail"].copy()
        with self.assertRaises(ValueError):
            self.validate()

    def test_path_escape_and_disguised_png_rejected(self):
        self.manifest["representatives"][0]["file"] = "../outside.png"
        with self.assertRaises(ValueError):
            self.validate()
        self.setUp()
        path = self.dest / "representative.png"
        path.write_bytes(b"this is not PNG")
        self.manifest["representatives"][0]["sha256"] = static_delivery.sha(path)
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
