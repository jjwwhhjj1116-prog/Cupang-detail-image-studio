#!/usr/bin/env python3
"""Add local Remotion typography to an already edited, verified clean five-second MP4."""
import argparse
import copy
import shutil
import subprocess
import uuid
from pathlib import Path

from media import check_video, probe, rendered_srt
from studio import CAPTION_MODES, caption_mode, digest, read_json, require, srt, validate, write_json
from typography import fullbleed_design, gmarket_font

ROOT = Path(__file__).resolve().parents[1]


def prepare(job, lead_id, clean_source, requested_caption_mode=None):
    validate(job)
    mode = caption_mode(job, requested_caption_mode)
    lead = next(item for item in job["leads"] if item["id"] == lead_id)
    clean_source = Path(clean_source).resolve()
    require(clean_source.is_file(), "Clean edited source MP4 is missing")
    sources, metadata = read_json(clean_source.with_suffix(".sources.json")), read_json(clean_source.with_suffix(".probe.json"))
    fingerprint = digest(clean_source)
    require(sources.get("artifact_sha256") == metadata.get("artifact_sha256") == fingerprint,
            "Clean source sidecars do not match the actual MP4")
    require(metadata.get("caption_mode") == "without-captions" and metadata.get("subtitles_burned_in") is False,
            "Remotion requires a clean source rendered without captions")
    require(metadata.get("caption_band_px") == 0 and metadata.get("full_bleed") is True,
            "Clean source must have full-bleed footage and no caption band")
    check_video(metadata["metadata"], 150, 1280, 720)
    require(clean_source.with_suffix(".source-captions.srt").read_text(encoding="utf-8-sig") == srt(lead),
            "Clean source original captions do not match this lead")
    require(sources.get("lead_id") == lead_id, "Clean source belongs to a different lead")
    design = fullbleed_design(lead, 1280, 720, mode)
    return lead, mode, design, copy.deepcopy(sources), fingerprint


def render(job_path, lead_id, clean_source, output, requested_caption_mode=None, font_path=None,
           ffprobe="ffprobe", node="node"):
    job, output, clean_source = read_json(job_path), Path(output).resolve(), Path(clean_source).resolve()
    lead, mode, design, sources, fingerprint = prepare(job, lead_id, clean_source, requested_caption_mode)
    check_video(probe(clean_source, ffprobe), 150, 1280, 720)
    require(output.suffix.lower() == ".mp4" and not output.exists(), "Choose a new MP4 output path")
    require(output != clean_source, "Output cannot replace the clean source")
    project = ROOT / "remotion"
    cli = project / "node_modules/@remotion/cli/remotion-cli.js"
    require(cli.is_file(), "Install the local Remotion runtime with scripts/setup-remotion.ps1 first")
    font = gmarket_font(font_path) if mode == "with-captions" else None
    asset_id = "render-" + uuid.uuid4().hex
    assets = project / "public" / asset_id
    assets.mkdir(parents=True)
    shutil.copyfile(clean_source, assets / "clean.mp4")
    if font:
        shutil.copyfile(font["path"], assets / "GmarketSansTTFBold.ttf")
    props = {"sourceFile": f"{asset_id}/clean.mp4", "captionMode": mode, "design": design,
             "fontFile": f"{asset_id}/GmarketSansTTFBold.ttf" if font else None}
    props_file = assets / "props.json"
    write_json(props_file, props)
    output.parent.mkdir(parents=True, exist_ok=True)
    selected_job_path = Path(job_path).resolve()
    if caption_mode(job) != mode:
        # Preserve the supplied job while binding an explicit CLI override to a scoped copy.
        selected_job_path = output.with_suffix(".render-job.json")
        scoped_job = copy.deepcopy(job)
        scoped_job["caption_mode"] = mode
        write_json(selected_job_path, scoped_job)
    argv = [node, str(cli), "render", "src/index.ts", "DetailLead", str(output),
            "--props", str(props_file), "--codec", "h264", "--pixel-format", "yuv420p", "--concurrency", "2"]
    execution = subprocess.run(argv, cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output.with_suffix(".remotion.log").write_text(execution.stdout + execution.stderr, encoding="utf-8")
    require(execution.returncode == 0, f"Remotion failed; inspect {output.with_suffix('.remotion.log')}")
    metadata = probe(output, ffprobe)
    check_video(metadata, 150, 1280, 720)
    output.with_suffix(".source-captions.srt").write_text(srt(lead), encoding="utf-8")
    output.with_suffix(".srt").write_text(rendered_srt(lead, design, mode), encoding="utf-8")
    shutil.copyfile(props_file, output.with_suffix(".remotion-props.json"))
    sources.update(artifact_sha256=digest(output), caption_mode=mode, renderer="remotion",
                   clean_edit={"file": str(clean_source), "sha256": fingerprint})
    write_json(output.with_suffix(".sources.json"), sources)
    write_json(output.with_suffix(".probe.json"), {
        "artifact_sha256": digest(output), "metadata": metadata, "renderer": "remotion", "style":"fullbleed-motion",
        "caption_mode": mode, "subtitles_burned_in": mode == "with-captions", "caption_band_px": 0,
        "full_bleed": True, "font_postscript": font["postscript"] if font else None,
        "overlay_design": design, "after_effects_render": False,
        "mechanical_checks": {"duration":"pass", "frame_count":"pass", "fps":"pass", "dimensions":"pass"},
        "visual_review_required": ["product_fidelity", "text_layout" if font else "no_text_overlay"],
        "clean_edit_sha256": fingerprint})
    write_json(output.with_suffix(".remotion.json"), {
        "status":"rendered_visual_review_required", "renderer":"remotion", "caption_mode":mode,
        "lead_id":lead_id,
        "version": read_json(project / "node_modules/remotion/package.json")["version"],
        "output_sha256":digest(output), "clean_edit_sha256":fingerprint,
        "source_provenance_preserved":True, "generation_requests_submitted":0,
        "source_job_sha256":digest(selected_job_path), "source_job_file":str(selected_job_path),
        "supplied_job_file":str(Path(job_path).resolve()), "supplied_job_sha256":digest(job_path),
        "font_sha256":digest(font["path"]) if font else None,
        "props_sha256":digest(output.with_suffix(".remotion-props.json")),
        "render_log_sha256":digest(output.with_suffix(".remotion.log")),
        "dependency_lock_sha256":digest(project / "package-lock.json"),
        "project_sources":{name:digest(project / name) for name in ("src/index.ts","src/Root.tsx","src/Composition.tsx","remotion.config.ts","package.json")},
        "clean_probe_sha256":digest(clean_source.with_suffix(".probe.json")),
        "clean_sources_sha256":digest(clean_source.with_suffix(".sources.json")),
        "studio_preview_verified":False})
    if font:
        write_json(output.with_suffix(".font.json"), {"renderer":"remotion", "font_postscript":font["postscript"],
                   "font_sha256":digest(font["path"]), "artifact_sha256":digest(output), "output_sha256":digest(output),
                   "browser_font_face_family":"GmarketLocalBold", "browser_font_face_load_verified":True,
                   "load_verification":"@remotion/fonts loadFont resolves and document.fonts.check succeeds; render cancels on failure"})
    bound_probe = read_json(output.with_suffix(".probe.json"))
    bound_probe["remotion_report_sha256"] = digest(output.with_suffix(".remotion.json"))
    write_json(output.with_suffix(".probe.json"), bound_probe)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job"); parser.add_argument("--lead", choices=["lead-1","lead-2"], required=True)
    parser.add_argument("--clean-source", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--caption-mode", choices=sorted(CAPTION_MODES)); parser.add_argument("--font")
    parser.add_argument("--ffprobe", default="ffprobe"); parser.add_argument("--node", default="node")
    args = parser.parse_args()
    try:
        print(render(args.job,args.lead,args.clean_source,args.output,args.caption_mode,args.font,args.ffprobe,args.node))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        parser.exit(2,f"Error: {error}\n")


if __name__ == "__main__":
    main()
