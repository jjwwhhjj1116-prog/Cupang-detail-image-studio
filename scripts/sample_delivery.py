"""Package two finished lead MP4s as a portable review page, without completing a job."""
import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from delivery import check, check_entry, file_at, read, sha
from media import check_video
from studio import srt, validate, video_mode, SINGLE_VIDEO, LEGACY_VIDEO, VIDEO_MODES


def checked_video(entry, root):
    video = check_entry(entry["video"], root)
    with video.open("rb") as stream:
        check(video.suffix.lower() == ".mp4" and stream.read(8)[4:8] == b"ftyp", "Lead must be MP4")
    evidence = read(check_entry(entry["probe"], root))
    check(evidence.get("artifact_sha256") == sha(video), "Probe refers to different footage")
    streams = evidence["metadata"].get("streams", [])
    check(len(streams) == 1, "One video stream is required")
    width, height = streams[0]["width"], streams[0]["height"]
    check(type(width) is int and type(height) is int and width > 0 and height > 0, "Invalid dimensions")
    check_video(evidence["metadata"], 150, width, height)
    subtitle = check_entry(entry["subtitle"], root).read_text(encoding="utf-8-sig")
    single = entry.get("video_mode", LEGACY_VIDEO) == SINGLE_VIDEO
    check(subtitle.replace("\r\n", "\n") == srt({"seconds": entry["seconds"]}, display=single), "Subtitles must exactly match approved job display captions")
    if single:
        original = check_entry(entry["source_subtitle"], root).read_text(encoding="utf-8-sig")
        check(original.replace("\r\n", "\n") == srt({"seconds": entry["seconds"]}), "Original source captions must remain unchanged")
    return evidence


def validate_package(path):
    """Check copied files and exact timelines, not product/visual QA or AE execution."""
    manifest, root = read(path), Path(path).resolve().parent
    check(manifest.get("video_mode", LEGACY_VIDEO) in VIDEO_MODES, "Unsupported sample video mode")
    check(manifest.get("schema_version") == 1 and manifest.get("scope") == "lead-sample", "Invalid sample manifest")
    check(manifest.get("page_complete") is False and manifest.get("status") == "sample_packaged", "Sample cannot complete the detail page")
    check([lead.get("id") for lead in manifest["leads"]] == ["lead-1", "lead-2"], "Both leads must be ordered")
    for lead in manifest["leads"]:
        check(lead.get("video_mode", LEGACY_VIDEO) == manifest.get("video_mode", LEGACY_VIDEO), "Sample lead mode differs from its manifest")
        check([shot.get("second") for shot in lead["seconds"]] == [1, 2, 3, 4, 5], "Invalid five-second timeline")
        check(all(isinstance(s.get("caption"), str) and s["caption"].strip() for s in lead["seconds"]), "Empty caption")
        checked_video(lead, root)
    image = check_entry(manifest["template_preview"], root)
    from PIL import Image
    with Image.open(image) as decoded:
        decoded.verify()
    check_entry(manifest["preview"], root)
    return manifest


def render_page(manifest):
    esc = html.escape
    cards = []
    for number, lead in enumerate(manifest["leads"], 1):
        from typography import display_caption
        single = lead.get("video_mode", LEGACY_VIDEO) == SINGLE_VIDEO
        timeline = "".join(f'<li><span>{shot["second"] - 1}–{shot["second"]}초</span><p>{esc((display_caption(shot) or "타이포 없는 장면") if single else shot["caption"])}</p></li>' for shot in lead["seconds"])
        original_link = f'<a download href="{lead["source_subtitle"]["file"]}">원문 SRT ↗</a>' if single else ""
        cards.append(f'''<section class="lead" id="{lead['id']}">
<div class="section-label"><span>LEAD 0{number}</span><span>{esc(lead['section_id'])} · 5초</span></div>
<h2>{esc(lead['headline'])}</h2>
<div class="screen"><video autoplay muted loop playsinline controls preload="metadata" aria-label="리드 {number}: {esc(lead['headline'], quote=True)}" src="{lead['video']['file']}"></video></div>
<div class="asset-links"><span>5장면 × 1초 · 30fps</span><a download href="{lead['video']['file']}">MP4 저장 ↗</a><a download href="{lead['subtitle']['file']}">표시 SRT ↗</a>{original_link}</div>
<details class="timing"><summary>초별 자막 보기 <span>00:00 — 00:05</span></summary><ol>{timeline}</ol></details>
</section>''')
    figma = (f'<a class="figma-link" href="{esc(manifest["figma_url"], quote=True)}" target="_blank" rel="noopener noreferrer">Figma 작업 사본 열기 ↗</a>' if manifest.get("figma_url") else "")
    page = Path(__file__).with_name("templates").joinpath("sample_preview.html").read_text(encoding="utf-8")
    values = {
        "TITLE": esc(f'{manifest["brand"]} · 리드 영상 샘플'), "BRAND": esc(manifest["brand"]),
        "TYPE": str(manifest["type"]), "CARDS": "\n".join(cards), "FIGMA_LINK": figma,
        "TEMPLATE_SRC": manifest["template_preview"]["file"], "TEMPLATE_NOTE": esc(manifest["template_note"]),
    }
    for key, value in values.items():
        page = page.replace("{{" + key + "}}", value)
    return page


def build(job_path, layout_path, workspace, output, mode=None):
    root, dest = Path(workspace).resolve(), Path(output).resolve()
    check(dest.is_relative_to(root) and dest != root, "Sample output must be inside the job workspace")
    check(not dest.exists(), "Choose a new output folder to preserve previous samples")
    job, layout = validate(read(job_path), root), read(layout_path)
    check([entry.get("id") for entry in layout["leads"]] == ["lead-1", "lead-2"], "Layout must provide both leads in order")
    template = file_at(root, layout["template_preview"])
    check(template.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}, "Template preview must be a raster image")
    from PIL import Image
    with Image.open(template) as decoded:
        decoded.verify()
    note = layout.get("template_note")
    check(isinstance(note, str) and note.strip(), "Describe what the static template preview actually contains")
    figma_url = layout.get("figma_url", "")
    if figma_url:
        url = urlparse(figma_url)
        check(url.scheme == "https" and url.hostname in {"www.figma.com", "figma.com"} and url.path.startswith("/design/"), "Invalid Figma design URL")
    manifest = {key: job[key] for key in ("job_id", "brand", "type")}
    mode = video_mode(job, mode)
    manifest["video_mode"] = mode
    manifest.update(schema_version=1, scope="lead-sample", status="sample_packaged", page_complete=False,
                    figma_url=figma_url, template_note=note, leads=[],
                    verification_scope="File hashes, recorded video probe and exact SRT only; job QA state is unchanged.")
    pending = []
    def prepare(relative, target):
        source = file_at(root, relative)
        pending.append((source, target))
        return {"file": target, "sha256": sha(source)}
    for layout_lead, lead in zip(layout["leads"], job["leads"]):
        sections = [s for s in job["sections"] if s.get("asset_id") == lead["id"] and s["kind"] == "video"]
        check(len(sections) == 1, "Each lead needs one video section with its exact headline")
        item = {"id": lead["id"], "section_id": sections[0]["id"], "headline": sections[0]["text"], "video_mode": mode,
                "seconds": [{k: s[k] for k in ("second", "caption", "overlay") if k in s} for s in lead["seconds"]]}
        original = {**item}
        for kind, ext in (("video", "mp4"), ("subtitle", "srt"), ("probe", "probe.json")):
            relative = layout_lead[kind]
            source = file_at(root, relative)
            original[kind] = {"file": relative, "sha256": sha(source)}
            item[kind] = prepare(relative, f'assets/{lead["id"]}.{ext}')
        if mode == SINGLE_VIDEO:
            relative = layout_lead.get("source_subtitle", str(Path(layout_lead["subtitle"]).with_suffix(".source-captions.srt")).replace("\\", "/"))
            original["source_subtitle"] = {"file": relative, "sha256": sha(file_at(root, relative))}
            item["source_subtitle"] = prepare(relative, f'assets/{lead["id"]}.source-captions.srt')
        evidence = checked_video(original, root)
        item["renderer"] = evidence.get("renderer", "unrecorded")
        item["after_effects_render"] = evidence.get("after_effects_render", "unverified")
        manifest["leads"].append(item)
    manifest["template_preview"] = prepare(layout["template_preview"], "assets/template-preview" + template.suffix.lower())
    # All inputs pass before output creation. Input footage and plan state stay unchanged.
    (dest / "assets").mkdir(parents=True)
    for source, target in pending:
        shutil.copyfile(source, dest / target)
        check(sha(dest / target) == sha(source), "Copied file hash differs")
    preview = dest / "preview.html"
    preview.write_text(render_page(manifest), encoding="utf-8")
    manifest["preview"] = {"file": "preview.html", "sha256": sha(preview)}
    result = dest / "sample-manifest.json"
    result.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validate_package(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "validate"])
    parser.add_argument("input", help="Layout JSON for build; sample-manifest.json for validate")
    parser.add_argument("--job"); parser.add_argument("--workspace"); parser.add_argument("--output")
    parser.add_argument("--video-mode", choices=sorted(VIDEO_MODES), help="Explicit mode for rebuilding historical jobs without a video_mode field")
    args = parser.parse_args()
    try:
        if args.mode == "build":
            check(all((args.job, args.workspace, args.output)), "Build requires --job, --workspace and --output")
            print(build(args.job, args.input, args.workspace, args.output, args.video_mode))
        else:
            validate_package(args.input)
            print("Portable sample files and timelines verified; detail page status unchanged")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")
