#!/usr/bin/env python3
"""Local planning and evidence tracking. Providers are operated by the Codex skill."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

BRANDS = {"와이홉", "유앤채"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
CHECKS = {
    "image": {"product_fidelity", "prompt_match"},
    "video": {"product_fidelity", "duration", "frame_count", "subtitle_timing"},
    "source-video": {"product_fidelity", "scene_action", "source_trace"},
    "subtitle": {"subtitle_timing", "caption_match"},
    "export": {"template_mapping", "product_fidelity", "text_layout", "brand"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative_path(value, root=None):
    require(isinstance(value, str) and bool(value.strip()), "A nonempty relative path is required")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    require(not path.is_absolute() and ":" not in normalized and ".." not in path.parts,
            f"Path must remain inside the workspace: {value}")
    require(path.parts and "\x00" not in value, "Invalid path")
    if root is not None:
        resolved = (Path(root) / Path(*path.parts)).resolve()
        require(resolved.is_relative_to(Path(root).resolve()), f"Path escapes workspace: {value}")
        return resolved
    return path.as_posix()


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text")


def validate(job, workspace=None):
    require(isinstance(job, dict), "Job must be a JSON object")
    require(type(job.get("schema_version")) is int and job["schema_version"] == 1, "schema_version must be 1")
    require(isinstance(job.get("job_id"), str) and SLUG.fullmatch(job["job_id"]), "job_id must be a lowercase slug")
    require(job.get("brand") in BRANDS, "brand must be 와이홉 or 유앤채")
    require(type(job.get("type")) is int and 1 <= job["type"] <= 7, "type must be an integer from 1 to 7")
    product = job.get("product")
    require(isinstance(product, dict), "product must be an object")
    photos = product.get("photos")
    require(isinstance(photos, list) and photos, "product.photos must contain reference photos")
    for photo in photos:
        path = relative_path(photo, workspace)
        if workspace is not None:
            require(path.is_file() and path.stat().st_size > 0, f"Missing reference photo: {photo}")
    facts = product.get("confirmed_facts")
    require(isinstance(facts, list), "product.confirmed_facts must be an array")
    for fact in facts:
        nonempty(fact, "confirmed fact")
    leads = job.get("leads")
    require(isinstance(leads, list) and len(leads) == 2, "Exactly two leads are required")
    require([lead.get("id") for lead in leads if isinstance(lead, dict)] == ["lead-1", "lead-2"],
            "Lead IDs/order must be lead-1, lead-2")
    for lead in leads:
        require(type(lead.get("fps")) is int and lead["fps"] == 30, "Lead fps must be 30")
        seconds = lead.get("seconds")
        require(isinstance(seconds, list) and len(seconds) == 5, "Each lead requires exactly five seconds")
        require(all(isinstance(shot, dict) and type(shot.get("second")) is int for shot in seconds), "Invalid second")
        require([shot["second"] for shot in seconds] == [1, 2, 3, 4, 5], "Seconds must be ordered 1 through 5")
        for shot in seconds:
            for key in ("action", "caption", "image_prompt", "video_prompt"):
                nonempty(shot.get(key), f"{lead['id']} second {shot['second']} {key}")
    sections = job.get("sections")
    require(isinstance(sections, list) and sections, "sections must be a nonempty array")
    ids, image_ids, slot_ids, video_ids = set(), set(), set(), []
    reserved = {"detail-page", "lead-1", "lead-2"} | {
        f"lead-{lead}-{kind}-{second:02d}" for lead in (1, 2) for kind in ("frame", "source") for second in range(1, 6)} | {
        "lead-1-subtitles", "lead-2-subtitles"}
    for section in sections:
        require(isinstance(section, dict), "Section must be an object")
        sid = section.get("id")
        require(isinstance(sid, str) and re.fullmatch(fr"{job['type']}-\d+", sid), "Section ID must match selected type")
        require(sid not in ids, f"Duplicate section: {sid}")
        ids.add(sid)
        nonempty(section.get("text"), f"{sid} text")
        kind = section.get("kind")
        require(kind in {"text", "image", "video"}, f"Invalid kind: {kind}")
        require("assets" not in section or kind == "image", "Only image sections may declare assets")
        if kind == "image":
            if "assets" in section:
                require("asset_id" not in section and "image_prompt" not in section,
                        "Use assets or the single asset_id/image_prompt form, not both")
                require(isinstance(section["assets"], list) and section["assets"], "Image assets must be a nonempty array")
            for asset in section_image_assets(section):
                require(isinstance(asset, dict), "Each image asset must be an object")
                aid = asset.get("asset_id")
                require(isinstance(aid, str) and SLUG.fullmatch(aid), "Image asset_id must be a lowercase slug")
                require(aid not in image_ids | reserved, f"Duplicate/reserved asset_id: {aid}")
                image_ids.add(aid)
                nonempty(asset.get("image_prompt"), f"{sid} {aid} image_prompt")
                if "slot_id" in asset:
                    nonempty(asset["slot_id"], f"{sid} {aid} slot_id")
                    require(asset["slot_id"] not in slot_ids, f"Duplicate image slot_id: {asset['slot_id']}")
                    slot_ids.add(asset["slot_id"])
        if kind == "video":
            video_ids.append(section.get("asset_id"))
    require(sorted(str(x) for x in video_ids) == ["lead-1", "lead-2"], "Sections must map each lead video exactly once")
    return job


def section_image_assets(section):
    return section.get("assets", [section]) if section["kind"] == "image" else []


def image_assets(job):
    return [dict(asset, section_id=section["id"]) for section in job["sections"] for asset in section_image_assets(section)]


def artifacts(job, scope="full"):
    require(scope in {"full", "lead-sample"}, "Scope must be full or lead-sample")
    items = [{"id": asset["asset_id"], "kind": "image"} for asset in image_assets(job)] if scope == "full" else []
    for lead in job["leads"]:
        items.extend({"id": f"{lead['id']}-frame-{shot['second']:02d}", "kind": "image"} for shot in lead["seconds"])
        if scope == "lead-sample":
            items.extend({"id": f"{lead['id']}-source-{shot['second']:02d}", "kind": "source-video"} for shot in lead["seconds"])
            items.append({"id": f"{lead['id']}-subtitles", "kind": "subtitle", "lead_id": lead["id"]})
        items.append({"id": lead["id"], "kind": "video"})
    return items + ([{"id": "detail-page", "kind": "export"}] if scope == "full" else [])


def srt(lead):
    return "\n\n".join(f"{s['second']}\n00:00:{s['second'] - 1:02d},000 --> 00:00:{s['second']:02d},000\n{s['caption']}"
                       for s in lead["seconds"]) + "\n"


def ingest(prompt_path, output, job_id, brand, selected_type):
    """Capture original sections; the skill supplies photos, classification and lead scripts."""
    source = Path(prompt_path).read_text(encoding="utf-8-sig")
    pattern = re.compile(r"(?m)^\s*(?:#{1,6}\s*)?(?:TYPE\s*)?([1-7])-([0-9]+)\s*[).:：]?[^\n]*$")
    matches = list(pattern.finditer(source))
    sections = []
    for index, match in enumerate(matches):
        require(int(match[1]) == selected_type, "Prompt headings disagree with selected type")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        sections.append({"id": f"{match[1]}-{match[2]}", "kind": "text", "text": source[match.start():end].strip()})
    require(sections, "No numbered section headings found; preserve prompt and inspect its format")
    write_json(output, {"schema_version": 1, "job_id": job_id, "brand": brand, "type": selected_type,
                        "status": "draft", "source_prompt": source, "product": {"photos": [], "confirmed_facts": []},
                        "sections": sections, "leads": []})


def plan(job_path, workspace, output, scope="full", reuse_sample=None):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    require(output.is_relative_to(workspace), "Plan directory must be inside workspace")
    job = validate(read_json(job_path), workspace)
    require(scope in {"full", "lead-sample"}, "Scope must be full or lead-sample")
    require(not reuse_sample or scope == "full", "Only full plans can reuse a verified lead sample")
    state_path = output / "state.json"
    if state_path.exists():
        state = load_state(state_path)
        require(state["job_sha256"] == digest(job_path), "Plan already exists for different job content")
        require(state.get("scope", "full") == scope, "Plan exists for a different scope; use another plan folder")
        return state_path
    reused = None
    if reuse_sample:
        reused = load_state(reuse_sample)
        require(reused.get("scope") == "lead-sample" and reused["status"] == "sample_verified", "Sample has not been verified")
        require(Path(reused["workspace"]).resolve() == workspace, "Sample and full plan must share a workspace")
        original = read_json(reused["job_path"])
        require(all(job[key] == original[key] for key in ("job_id", "brand", "type", "leads")), "Sample identity or lead script changed")
        require(job["product"]["photos"] == original["product"]["photos"], "Sample reference photos changed")
        complete(reuse_sample)
        reused = load_state(reuse_sample)
    (output / "prompts").mkdir(parents=True, exist_ok=True)
    tasks = []
    planned_images = image_assets(job) if scope == "full" else []
    for asset in planned_images:
        (output / "prompts" / f"{asset['asset_id']}.txt").write_text(asset["image_prompt"], encoding="utf-8")
    write_json(output / "image-tasks.json", planned_images)
    for lead in job["leads"]:
        (output / f"{lead['id']}.srt").write_text(srt(lead), encoding="utf-8")
        for shot in lead["seconds"]:
            aid = f"{lead['id']}-frame-{shot['second']:02d}"
            (output / "prompts" / f"{aid}.txt").write_text(shot["image_prompt"], encoding="utf-8")
            tasks.append(dict(shot, lead_id=lead["id"], image_asset_id=aid,
                              start_frame=(shot["second"] - 1) * 30, end_frame=shot["second"] * 30))
    write_json(output / "timeline.json", {"fps": 30, "frames_per_lead": 150, "end_frame_exclusive": True, "tasks": tasks})
    items = [dict(item, status="pending") for item in artifacts(job, scope)]
    if reused:
        reusable = {item["id"]: item for item in reused["artifacts"]}
        items = [dict(reusable[item["id"]]) if item["id"] in reusable else item for item in items]
    write_json(state_path, {"schema_version": 1, "status": "in_progress" if reused else "planned", "scope": scope,
                           "page_complete": False, "workspace": str(workspace),
                           "job_path": str(Path(job_path).resolve()), "job_sha256": digest(job_path),
                           "job_identity": {key: job[key] for key in ("job_id", "brand", "type")},
                           "reference_sha256": [{"file": path, "sha256": digest(relative_path(path, workspace))}
                                                for path in job["product"]["photos"]],
                           "reused_sample": str(Path(reuse_sample).resolve()) if reuse_sample else None,
                           "artifacts": items})
    return state_path


def load_state(path):
    state = read_json(path)
    require(digest(state["job_path"]) == state["job_sha256"], "Source job changed; create a new plan")
    job = validate(read_json(state["job_path"]), state["workspace"])
    require(state.get("job_identity") == {key: job[key] for key in ("job_id", "brand", "type")}, "State job identity changed")
    references = [{"file": path, "sha256": digest(relative_path(path, state["workspace"]))} for path in job["product"]["photos"]]
    require(state.get("reference_sha256") == references, "Reference photo changed; create a new plan")
    require([(a["id"], a["kind"]) for a in state["artifacts"]] == [(a["id"], a["kind"]) for a in artifacts(job, state.get("scope", "full"))],
            "State artifact set does not match source job")
    require(state.get("scope") != "lead-sample" or (state["status"] != "complete" and not state.get("page_complete")),
            "A lead sample cannot be a completed detail page")
    return state


def verify_evidence(workspace, item, file, qa_file, expected=None, expected_job=None):
    artifact, qa_path = relative_path(file, workspace), relative_path(qa_file, workspace)
    require(artifact.is_file() and artifact.stat().st_size > 0, f"Missing/empty artifact: {file}")
    require(qa_path.is_file(), f"Missing QA evidence: {qa_file}")
    if item["kind"] == "source-video":
        with artifact.open("rb") as stream:
            require(b"ftyp" in stream.read(32), "Flow source must be an actual MP4 container")
    if item["kind"] == "subtitle":
        require(expected_job is not None, "Subtitle verification requires the source job")
        lead_id = item["id"].removesuffix("-subtitles")
        lead = next(lead for lead in expected_job["leads"] if lead["id"] == lead_id)
        require(artifact.read_text(encoding="utf-8-sig") == srt(lead), "Subtitles do not exactly match the five one-second captions")
    if item["kind"] == "export":
        from delivery import validate_manifest
        manifest = validate_manifest(artifact, workspace, expected_job=expected_job)
        require(isinstance(expected, dict) and all(manifest.get(key) == value for key, value in expected.items()),
                "Delivery manifest must match source job identity")
    sha = digest(artifact)
    qa = read_json(qa_path)
    require(qa.get("artifact_sha256") == sha, "QA evidence must match current artifact SHA-256")
    checks = qa.get("checks")
    require(isinstance(checks, list) and checks, "QA requires checks")
    for check in checks:
        require(isinstance(check, dict) and check.get("status") == "pass", "Every QA check must pass")
        nonempty(check.get("name"), "QA check name")
        nonempty(check.get("evidence"), "QA check evidence")
    require(CHECKS[item["kind"]] <= {check["name"] for check in checks}, "Required QA checks missing")
    return {"file": relative_path(file), "sha256": sha, "qa_file": relative_path(qa_file), "qa_sha256": digest(qa_path)}


def record(state_path, asset_id, file, qa_file):
    state = load_state(state_path)
    item = next((a for a in state["artifacts"] if a["id"] == asset_id), None)
    require(item is not None, f"Unknown asset: {asset_id}")
    proof = verify_evidence(state["workspace"], item, file, qa_file, state["job_identity"], read_json(state["job_path"]))
    item.update(proof, status="verified")
    state["status"] = "in_progress"
    state["page_complete"] = False
    write_json(state_path, state)


def complete(state_path):
    state = load_state(state_path)
    job = read_json(state["job_path"])
    try:
        for item in state["artifacts"]:
            require(item.get("status") == "verified", f"Artifact not verified: {item['id']}")
            proof = verify_evidence(state["workspace"], item, item["file"], item["qa_file"], state["job_identity"], job)
            require(all(item.get(k) == v for k, v in proof.items()), f"Recorded artifact/evidence changed: {item['id']}")
        if state.get("scope") == "lead-sample":
            state["sample_video_metadata"] = {}
            for item in state["artifacts"]:
                if item["kind"] == "video":
                    state["sample_video_metadata"][item["id"]] = inspect_sample_video(relative_path(item["file"], state["workspace"]))
    except (ValueError, OSError, KeyError, TypeError) as error:
        state.update(status="needs_review", page_complete=False, last_error=str(error))
        write_json(state_path, state)
        raise
    state["status"] = "sample_verified" if state.get("scope") == "lead-sample" else "complete"
    state["page_complete"] = state.get("scope", "full") == "full"
    state.pop("last_error", None)
    write_json(state_path, state)


def inspect_sample_video(path):
    from media import probe, check_video
    from subprocess import CalledProcessError
    tools_path = Path(__file__).resolve().parents[1] / ".tools/media-tools.json"
    ffprobe = read_json(tools_path)["ffprobe"] if tools_path.is_file() else "ffprobe"
    try:
        metadata = probe(path, ffprobe)
    except CalledProcessError as error:
        raise ValueError(f"Sample ffprobe verification failed: {path}") from error
    require(metadata.get("streams"), "Sample video stream missing")
    stream = metadata["streams"][0]
    check_video(metadata, 150, stream["width"], stream["height"])
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("ingest")
    p.add_argument("prompt"); p.add_argument("--output", required=True)
    p.add_argument("--job-id", required=True); p.add_argument("--brand", choices=sorted(BRANDS), required=True)
    p.add_argument("--type", type=int, choices=range(1, 8), required=True)
    p = commands.add_parser("validate"); p.add_argument("job"); p.add_argument("--workspace")
    p = commands.add_parser("plan"); p.add_argument("job"); p.add_argument("--workspace", required=True); p.add_argument("--output", required=True)
    p.add_argument("--scope", choices=["full", "lead-sample"], default="full"); p.add_argument("--reuse-sample")
    p = commands.add_parser("record"); p.add_argument("state"); p.add_argument("asset_id"); p.add_argument("file"); p.add_argument("qa_file")
    p = commands.add_parser("complete"); p.add_argument("state")
    args = parser.parse_args()
    try:
        if args.command == "ingest": ingest(args.prompt, args.output, args.job_id, args.brand, args.type)
        elif args.command == "validate": validate(read_json(args.job), args.workspace)
        elif args.command == "plan": print(plan(args.job, args.workspace, args.output, args.scope, args.reuse_sample))
        elif args.command == "record": record(args.state, args.asset_id, args.file, args.qa_file)
        elif args.command == "complete": complete(args.state)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
