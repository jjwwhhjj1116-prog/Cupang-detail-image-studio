#!/usr/bin/env python3
"""Generate an editable AE JSX builder; generation is not AE execution or rendering."""
import argparse
import json
import math
from pathlib import Path

from studio import digest, read_json, relative_path, require, validate, write_json
from typography import kinetic_design


def build(job_path, workspace, media_map_path, output, width=768, height=500, caption_band=76,
          audio_mode="preserve", allow_missing=False):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    require(output.is_relative_to(workspace), "JSX output must be inside the job workspace")
    require(output.suffix.lower() == ".jsx" and not output.exists(), "Choose a new .jsx output path")
    require(type(width) is int and type(height) is int and min(width, height) >= 4 and width % 2 == height % 2 == 0,
            "Composition dimensions must be positive even pixels")
    require(audio_mode in {"preserve", "mute"}, "Audio mode must be preserve or mute")
    job = validate(read_json(job_path), workspace)
    mapping = read_json(media_map_path)
    require(set(mapping) == {"lead-1", "lead-2"}, "Media map must contain both leads")
    data = {"schema_version": 1, "job_id": job["job_id"], "brand": job["brand"], "workspace": workspace.as_posix(),
            "width": width, "height": height, "fps": 30, "duration": 5, "caption_band": caption_band,
            "audio_mode": audio_mode, "project_path": output.with_suffix(".aep").as_posix(), "leads": []}
    missing = []
    for lead in job["leads"]:
        clips = mapping[lead["id"]]
        require(isinstance(clips, list) and len(clips) == 5, "Each lead requires five ordered source videos")
        design = kinetic_design(lead, width, height, caption_band)
        shots = []
        for index, entry in enumerate(clips):
            require(isinstance(entry, dict), "Each source entry must be an object")
            path = relative_path(entry.get("file"), workspace)
            require(path.suffix.lower() == ".mp4", "Source videos must be MP4")
            offset = entry.get("start_seconds", 0)
            require(type(offset) in {int, float} and math.isfinite(offset) and offset >= 0, "Invalid source offset")
            duration = entry.get("source_duration", 1)
            require(type(duration) in {int, float} and math.isfinite(duration) and 1 / 99 <= duration <= 100, "Source duration must be from 1/99 to 100 seconds")
            exists = path.is_file() and path.stat().st_size > 0
            if not exists:
                missing.append(relative_path(entry["file"]))
            shots.append(dict(design["shots"][index], file=relative_path(entry["file"]), source_start=offset,
                              source_duration=duration, time_stretch_percent=100 / duration,
                              source_selection_status=entry.get("selection_status", "requires_visual_review"),
                              source_sha256=digest(path) if exists else None))
        data["leads"].append({"id": lead["id"], "design": design, "shots": shots})
    require(allow_missing or not missing, f"Source videos missing: {missing}")
    template = (Path(__file__).parent / "templates/kinetic_leads.jsx").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__JOB_DATA__", json.dumps(data, ensure_ascii=True)), encoding="utf-8")
    report = {"status": "jsx_generated_ae_unverified", "after_effects_executed": False, "aep_created": False,
              "after_effects_rendered": False, "sample_creative_not_brand_standard": True,
              "jsx_file": str(output), "jsx_sha256": digest(output), "source_job_sha256": digest(job_path),
              "comp_count": 2, "frames_per_comp": 150, "missing_sources": missing, "data": data}
    write_json(output.with_suffix(".ae-plan.json"), report)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job"); parser.add_argument("--workspace", required=True)
    parser.add_argument("--media-map", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=768); parser.add_argument("--height", type=int, default=500)
    parser.add_argument("--caption-band", type=int, default=76)
    parser.add_argument("--audio-mode", choices=["preserve", "mute"], default="preserve")
    parser.add_argument("--allow-missing", action="store_true", help="Prepare a clearly incomplete builder before downloads finish")
    args = parser.parse_args()
    try:
        print(build(args.job, args.workspace, args.media_map, args.output, args.width, args.height,
                    args.caption_band, args.audio_mode, args.allow_missing))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
