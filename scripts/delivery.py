"""Build a local playable preview and verify the entire delivery bundle. No publishing."""
import argparse
import hashlib
import html
import json
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

REQUIRED_QA = {"product_identity", "claims", "subtitle_timing", "figma_render", "template_residue", "image_provider_spec"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def file_at(workspace, relative):
    check(isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative, "Use a relative POSIX file path")
    part = PurePosixPath(relative)
    check(not part.is_absolute() and ".." not in part.parts, "Unsafe delivery path")
    root = Path(workspace).resolve()
    path = (root / relative).resolve()
    check(path.is_relative_to(root) and path.is_file() and path.stat().st_size > 0, f"Missing/unsafe file: {relative}")
    return path


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def check_entry(entry, workspace):
    path = file_at(workspace, entry["file"])
    check(sha(path) == entry["sha256"], f"File changed: {entry['file']}")
    return path


def validate_manifest(path, workspace, expected_job=None):
    manifest = read(path)
    from studio import LEGACY_VIDEO, SINGLE_VIDEO, VIDEO_MODES, WITHOUT_CAPTIONS, caption_mode, srt, verify_caption_render
    mode = manifest.get("video_mode", LEGACY_VIDEO)
    captions = caption_mode(manifest)
    check(mode in VIDEO_MODES, "Unsupported delivery video mode")
    check(manifest.get("schema_version") == 1, "Unsupported delivery schema")
    check(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", manifest.get("job_id", ""))), "Invalid job ID")
    check(manifest.get("brand") in {"와이홉", "유앤채"}, "Unsupported brand")
    check(type(manifest.get("type")) is int and 1 <= manifest["type"] <= 7, "Invalid TYPE")
    check(type(manifest.get("width")) is int and manifest["width"] > 0, "Invalid output width")
    url = urlparse(manifest.get("figma_url", ""))
    check(url.scheme == "https" and url.hostname in {"figma.com", "www.figma.com"}
          and re.match(r"^/design/[A-Za-z0-9]+(?:/|$)", url.path), "An actual Figma design link is required")
    items = manifest.get("items", [])
    check(isinstance(items, list) and items, "No detail-page sections")
    check(all(isinstance(x.get("id"), str) and x["id"] for x in items), "Every item requires an ID")
    check(len({x["id"] for x in items}) == len(items), "Duplicate section ID")
    check(len({x["file"] for x in items}) == len(items), "Duplicate section file")
    check(any(x.get("kind") == "image" for x in items), "Missing static detail-page sections")
    videos = [x for x in items if x.get("kind") == "video"]
    check([x["id"] for x in videos] == ["lead-1", "lead-2"], "Both lead videos must be present in order")
    if expected_job is not None:
        check(captions == caption_mode(expected_job), "Delivery caption mode differs from the selected job")
        check("video_mode" not in expected_job or expected_job["video_mode"] == mode, "Delivery video mode differs from the plan")
        check(all(manifest.get(k) == expected_job.get(k) for k in ("job_id", "brand", "type")), "Delivery belongs to a different job")
        expected_sections = {x["id"] for x in expected_job["sections"]}
        covered = []
        for item in items:
            ids = item.get("section_ids", [])
            check(isinstance(ids, list) and all(isinstance(x, str) for x in ids), "Invalid section coverage")
            covered.extend(ids)
        check(set(covered) == expected_sections, "Delivery is missing planned sections or includes unknown sections")
        from studio import artifacts
        expected_assets = {x["id"] for x in artifacts(expected_job, mode=mode) if x["kind"] == "image"}
        composed = manifest.get("composition_assets", [])
        check(isinstance(composed, list) and all(isinstance(x, str) for x in composed), "Invalid composition asset IDs")
        check(len(composed) == len(set(composed)) and set(composed) == expected_assets, "Composition does not cover every planned image asset")
    for item in items:
        asset = check_entry(item, workspace)
        with asset.open("rb") as stream:
            head = stream.read(32)
        if item["kind"] == "image":
            check(asset.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}, "Unsupported image format")
            check(head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a"))
                  or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"), "Image signature mismatch")
            from PIL import Image
            with Image.open(asset) as decoded:
                check(decoded.width == manifest["width"], "Exported image width differs from the template")
                decoded.verify()
        elif item["kind"] == "video":
            check(asset.suffix.lower() == ".mp4" and head[4:8] == b"ftyp", "Lead is not an MP4")
            probe_path = check_entry(item["probe"], workspace)
            probe = read(probe_path)
            check(probe.get("artifact_sha256") == item["sha256"], "Video probe refers to different footage")
            verify_caption_render(probe, captions)
            from media import check_video
            check_video(probe["metadata"], 150, item["width"], item["height"])
        else:
            raise ValueError("Unknown delivery item kind")
    subs = manifest.get("subtitles", [])
    if captions == WITHOUT_CAPTIONS:
        check(subs == [], "No-caption delivery must not list display subtitles")
        originals = manifest.get("source_captions", [])
        check([x.get("lead_id") for x in originals] == ["lead-1", "lead-2"], "Both original caption-data files are required")
        check(expected_job is not None, "Original caption-data verification requires the source job")
        for entry in originals:
            lead = next(lead for lead in expected_job["leads"] if lead["id"] == entry["lead_id"])
            original = check_entry(entry, workspace).read_text(encoding="utf-8-sig")
            check(original.replace("\r\n", "\n") == srt(lead), "Original source captions changed")
    else:
        check([x.get("lead_id") for x in subs] == ["lead-1", "lead-2"], "Both timed subtitle files are required")
    expected = [(f"00:00:0{i},000", f"00:00:0{i+1},000") for i in range(5)]
    for entry in subs:
        subpath = check_entry(entry, workspace)
        text = subpath.read_text(encoding="utf-8-sig")
        if mode == SINGLE_VIDEO:
            check(expected_job is not None, "Single-source delivery requires the original job for copy verification")
            lead = next(lead for lead in expected_job["leads"] if lead["id"] == entry["lead_id"])
            check(text.replace("\r\n", "\n") == srt(lead, display=True), "Display subtitles differ from approved job copy")
            original = check_entry(entry["source_subtitle"], workspace).read_text(encoding="utf-8-sig")
            check(original.replace("\r\n", "\n") == srt(lead), "Original source captions changed")
            continue
        check(re.findall(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", text) == expected, "Subtitle timing must be exactly five one-second intervals")
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
        check(len(blocks) == 5, "Exactly five subtitle blocks are required")
        for number, block in enumerate(blocks, 1):
            lines = block.splitlines()
            check(len(lines) >= 3 and lines[0] == str(number) and "\n".join(lines[2:]).strip(), "Subtitle caption is empty or malformed")
    qa = read(check_entry(manifest["qa"], workspace))
    checks = qa.get("checks", [])
    check(isinstance(checks, list) and all(isinstance(x, dict) and x.get("status") == "pass" and isinstance(x.get("evidence"), str) and x["evidence"].strip() for x in checks), "Unresolved QA checks")
    required_qa = (REQUIRED_QA - {"subtitle_timing"}) | {"caption_absence"} if captions == WITHOUT_CAPTIONS else REQUIRED_QA
    check(required_qa <= {x.get("name") for x in checks}, "Required production QA evidence is missing")
    preview = check_entry(manifest["preview"], workspace)
    check(preview.suffix.lower() == ".html", "Missing playable HTML preview")
    return manifest


def build(layout_path, workspace, output, expected_job=None):
    root, dest = Path(workspace).resolve(), Path(output).resolve()
    check(dest.is_relative_to(root), "Delivery must stay within the job workspace")
    layout = read(layout_path)
    dest.mkdir(parents=True, exist_ok=True)
    preview = dest / "preview.html"
    manifest_path = dest / "delivery-manifest.json"
    check(not preview.exists() and not manifest_path.exists(), "Choose a new delivery folder to preserve existing outputs")
    manifest = {k: layout[k] for k in ("job_id", "brand", "type", "figma_url", "width")}
    from studio import video_mode, caption_mode, WITHOUT_CAPTIONS
    manifest["video_mode"] = video_mode(expected_job or {}, layout.get("video_mode"))
    manifest["caption_mode"] = caption_mode(expected_job or {}, layout.get("caption_mode"))
    manifest.update(schema_version=1, items=[], subtitles=[])
    manifest["composition_assets"] = layout.get("composition_assets", [])
    def entry(relative):
        path = file_at(root, relative)
        return {"file": relative, "sha256": sha(path)}
    blocks = []
    for item in layout["items"]:
        result = {**item, **entry(item["file"])}
        if item["kind"] == "video":
            result["probe"] = entry(item["probe_file"])
            result.pop("probe_file", None)
        manifest["items"].append(result)
        src = html.escape(quote(os.path.relpath(file_at(root, item["file"]), dest).replace("\\", "/"), safe="/"), quote=True)
        title = html.escape(item["id"], quote=True)
        if item["kind"] == "video":
            blocks.append(f'<video controls playsinline preload="metadata" aria-label="{title}" src="{src}"></video>')
        else:
            blocks.append(f'<img src="{src}" alt="{title}" loading="lazy">')
    if manifest["caption_mode"] == WITHOUT_CAPTIONS:
        check(not layout.get("subtitles"), "No-caption layout must not list display subtitles")
        originals = layout.get("source_captions", [{"lead_id": item["id"], "file": str(Path(item["file"]).with_suffix(".source-captions.srt")).replace("\\", "/")}
                                                  for item in layout["items"] if item["kind"] == "video"])
        manifest["source_captions"] = [{"lead_id": sub["lead_id"], **entry(sub["file"])} for sub in originals]
    for sub in layout.get("subtitles", []):
        result = {"lead_id": sub["lead_id"], **entry(sub["file"])}
        from studio import SINGLE_VIDEO
        if manifest["video_mode"] == SINGLE_VIDEO:
            original = sub.get("source_subtitle_file", str(Path(sub["file"]).with_suffix(".source-captions.srt")).replace("\\", "/"))
            result["source_subtitle"] = entry(original)
        manifest["subtitles"].append(result)
    manifest["qa"] = entry(layout["qa_file"])
    title = html.escape(f'{layout["brand"]} · {layout["job_id"]}')
    width = int(layout["width"])
    check(width > 0, "Invalid width")
    page = f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{margin:0;background:#eee}}main{{max-width:{width}px;margin:auto;background:white}}img,video{{display:block;width:100%;height:auto}}</style><main>' + "".join(blocks) + "</main></html>"
    preview.write_text(page, encoding="utf-8")
    manifest["preview"] = entry(preview.relative_to(root).as_posix())
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validate_manifest(manifest_path, root, expected_job=expected_job)
    return manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "validate"])
    parser.add_argument("input"); parser.add_argument("--workspace", required=True)
    parser.add_argument("--output")
    parser.add_argument("--job", required=True, help="Validated source job, for complete section and image coverage")
    args = parser.parse_args()
    try:
        from studio import validate
        expected_job = validate(read(args.job), args.workspace)
        if args.mode == "build":
            check(args.output is not None, "--output is required")
            print(build(args.input, args.workspace, args.output, expected_job=expected_job))
        else:
            validate_manifest(args.input, args.workspace, expected_job=expected_job)
            print("Delivery files and evidence verified")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")
