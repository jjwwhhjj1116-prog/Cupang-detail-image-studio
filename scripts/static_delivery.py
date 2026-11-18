"""Verify the four-set local delivery files and recorded QA. No live service calls."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, UnidentifiedImageError

from delivery import check, check_entry, read, sha

REQUIRED_CHECKS = {
    "representative", "product_identity", "figma_editability",
    "figma_render", "label_consistency", "claims",
}


def check_figma(figma):
    url = urlparse(figma.get("url", ""))
    match = re.fullmatch(r"/design/([A-Za-z0-9]+)(?:/[^/]*)?/?", url.path)
    check(url.scheme == "https" and url.hostname in {"figma.com", "www.figma.com"}
          and not url.username and not url.password and match is not None,
          "Use an actual Figma design URL")
    node = figma.get("node_id", "")
    check(isinstance(node, str) and re.fullmatch(r"\d+:\d+", node) is not None,
          "A concrete Figma work node ID is required")
    check(match.group(1) == figma.get("file_key"), "Figma file key differs from URL")
    query_node = parse_qs(url.query).get("node-id", [""])[0].replace("-", ":")
    check(query_node == node, "Figma node ID differs from URL")
    info = figma.get("product_info_node_id", "")
    check(isinstance(info, str) and re.fullmatch(r"\d+:\d+", info) is not None
          and info != node, "A separate product-information frame ID is required")


def verify_png(entry, folder):
    path = check_entry(entry, folder)
    check(path.suffix.lower() == ".png", "Deliverable must be PNG")
    try:
        with Image.open(path) as image:
            check(image.format == "PNG", "File contents are not PNG")
            width, height = image.size
            check(width > 0 and height > 0, "PNG is empty")
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(f"Invalid PNG: {entry['file']}") from error
    return {"file": entry["file"], "sha256": entry["sha256"],
            "width": width, "height": height}


def validate(manifest_path, job_root):
    manifest_path = Path(manifest_path).resolve()
    folder = manifest_path.parent
    root = Path(job_root).resolve()
    check(manifest_path.is_relative_to(root), "Manifest must be inside the job")
    manifest = read(manifest_path)
    check(manifest.get("schema_version") == 1
          and manifest.get("profile") == "hadi-four-set", "Wrong delivery profile")
    check(isinstance(manifest.get("job_id"), str)
          and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,100}", manifest["job_id"]),
          "Invalid job ID")
    check(manifest.get("brand") in {"와이홉", "유앤채"}, "Unsupported brand")
    check(type(manifest.get("type")) is int and 1 <= manifest["type"] <= 7,
          "TYPE must be 1 through 7")
    width = manifest.get("template_width")
    check(type(width) is int and width > 0, "Template width is required")
    check_figma(manifest.get("figma", {}))
    prompt = manifest["prompt"]
    check(prompt.get("source") in {"hadi-gpt", "seller-approved-local"},
          "Record the actual prompt source")
    check_entry(prompt, root)
    representatives = manifest.get("representatives")
    check(isinstance(representatives, list) and representatives,
          "At least one product-only representative is required")
    entries = representatives + [manifest["detail"], manifest["label"]]
    paths = [str((folder / item["file"]).resolve()) for item in entries]
    check(len(set(paths)) == len(paths), "Deliverables must be separate files")
    pngs = [verify_png(item, folder) for item in entries]
    check(pngs[-2]["width"] == width and pngs[-1]["width"] == width,
          "Detail and label widths must match the actual template")
    qa_path = check_entry(manifest["qa"], root)
    qa = read(qa_path)
    artifacts = qa.get("artifacts", [])
    check(isinstance(artifacts, list)
          and all(item["sha256"] in artifacts for item in entries),
          "QA must reference every current PNG hash")
    checks = qa.get("checks", [])
    check(isinstance(checks, list), "QA checks must be a list")
    for name in REQUIRED_CHECKS:
        matches = [item for item in checks if item.get("name") == name]
        check(len(matches) == 1 and matches[0].get("status") == "passed"
              and isinstance(matches[0].get("evidence"), str)
              and bool(matches[0]["evidence"].strip()),
              f"Actual QA evidence required for {name}")
    return {
        "job_id": manifest["job_id"], "file_checks": "passed",
        "figma_url": manifest["figma"]["url"], "pngs": pngs,
        "live_services_verified_by_script": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--job-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.manifest, args.job_root), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Delivery check failed: {error}\n")


if __name__ == "__main__":
    main()
