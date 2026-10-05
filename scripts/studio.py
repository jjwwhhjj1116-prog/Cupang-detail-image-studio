#!/usr/bin/env python3
"""Local planning and evidence tracking. Providers are operated by the Codex skill."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

BRANDS = {"와이홉", "유앤채"}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LEGACY_VIDEO = "legacy-five-source-v1"
SINGLE_VIDEO = "single-source-v2"
VIDEO_MODES = {LEGACY_VIDEO, SINGLE_VIDEO}
WITH_CAPTIONS = "with-captions"
WITHOUT_CAPTIONS = "without-captions"
CAPTION_MODES = {WITH_CAPTIONS, WITHOUT_CAPTIONS}
REMOTION_ROOT = Path(__file__).resolve().parents[1] / "remotion"
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


def video_mode(job, requested=None):
    mode = requested or job.get("video_mode", SINGLE_VIDEO)
    require(mode in VIDEO_MODES, "Unknown video mode")
    return mode


def caption_mode(job, override=None):
    """Absent fields preserve the historical captioned-video behavior."""
    mode = job.get("caption_mode", WITH_CAPTIONS) if override is None else override
    require(mode in CAPTION_MODES, "caption_mode must be with-captions or without-captions")
    return mode


def lead_references(job, lead):
    references = lead.get("reference_images", job["product"]["photos"][:5])
    require(isinstance(references, list) and 1 <= len(references) <= 5, "Each lead requires 1 to 5 reusable reference images")
    normalized = [relative_path(path) for path in references]
    require(len(set(normalized)) == len(normalized), "Lead reference images must be unique")
    return normalized


def reference_records(job, workspace):
    return [{"lead_id": lead["id"], "images": [{"file": path, "sha256": digest(relative_path(path, workspace))}
            for path in lead_references(job, lead)]} for lead in job["leads"]]


def validate_model_binding(binding, workspace=None):
    require(isinstance(binding, dict) and binding.get("policy") == "fixed-pair", "Model binding must use the fixed-pair policy")
    profiles = binding.get("profiles")
    require(isinstance(profiles, list) and 1 <= len(profiles) <= 2, "Model binding requires one or two active fixed model profiles")
    genders = {"female-f01": "female", "male-m01": "male"}
    profile_ids = {profile.get("id") for profile in profiles if isinstance(profile, dict)}
    require(len(profile_ids) == len(profiles) and profile_ids <= set(genders), "Use only unique fixed female-f01 and male-m01 profiles")
    for profile in profiles:
        require(profile.get("gender") == genders[profile["id"]], "Fixed model gender differs from its profile")
        require(isinstance(profile.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", profile["sha256"]), "Fixed model reference requires SHA-256")
        reference = relative_path(profile.get("file"), workspace)
        if workspace is not None:
            require(reference.is_file() and digest(reference) == profile["sha256"], "Fixed model reference changed or is missing")
        for field in ("character_sheet", "expression_sheet"):
            if field not in profile:
                continue
            sheet = profile[field]
            require(isinstance(sheet, dict) and type(sheet.get("revision")) is int and sheet["revision"] > 0,
                    f"Fixed {field.replace('_', ' ')} requires a positive revision")
            require(isinstance(sheet.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", sheet["sha256"]),
                    f"Fixed {field.replace('_', ' ')} requires SHA-256")
            sheet_path = relative_path(sheet.get("file"), workspace)
            if workspace is not None:
                require(sheet_path.is_file() and digest(sheet_path) == sheet["sha256"],
                        f"Fixed {field.replace('_', ' ')} changed or is missing")
    assignment = binding.get("wearing_assignment")
    require(isinstance(assignment, dict) and set(assignment) == {"lead-1", "lead-2"}
            and all(value in profile_ids for value in assignment.values()), "Assign an included active fixed model to each lead")
    require(binding.get("identity_review_required") is True, "Fixed-model identity review is required")


def validate(job, workspace=None):
    require(isinstance(job, dict), "Job must be a JSON object")
    require(type(job.get("schema_version")) is int and job["schema_version"] == 1, "schema_version must be 1")
    video_mode(job)
    caption_mode(job)
    if "model_binding" in job:
        validate_model_binding(job["model_binding"], workspace)
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
        for reference in lead_references(job, lead):
            if workspace is not None:
                path = relative_path(reference, workspace)
                require(path.is_file() and path.stat().st_size > 0, f"Missing lead reference image: {reference}")
        if "storyboard_prompt" in lead:
            nonempty(lead["storyboard_prompt"], "storyboard_prompt")
        require(type(lead.get("fps")) is int and lead["fps"] == 30, "Lead fps must be 30")
        seconds = lead.get("seconds")
        require(isinstance(seconds, list) and len(seconds) == 5, "Each lead requires exactly five seconds")
        require(all(isinstance(shot, dict) and type(shot.get("second")) is int for shot in seconds), "Invalid second")
        require([shot["second"] for shot in seconds] == [1, 2, 3, 4, 5], "Seconds must be ordered 1 through 5")
        for shot in seconds:
            for key in ("action", "caption", "image_prompt", "video_prompt"):
                nonempty(shot.get(key), f"{lead['id']} second {shot['second']} {key}")
            require(isinstance(shot.get("overlay", {}), dict), "Caption overlay must be an object")
            if shot.get("overlay", {}).get("mode") == "editorial":
                from typography import display_caption
                display_caption(shot)  # Explicit copy changes require validated text and a reason.
    sections = job.get("sections")
    require(isinstance(sections, list) and sections, "sections must be a nonempty array")
    ids, image_ids, slot_ids, video_ids = set(), set(), set(), []
    reserved = {"detail-page", "lead-1", "lead-2"} | {
        f"lead-{lead}-{kind}-{second:02d}" for lead in (1, 2) for kind in ("frame", "source") for second in range(1, 6)} | {
        "lead-1-subtitles", "lead-2-subtitles", "lead-1-source", "lead-2-source"}
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


def artifacts(job, scope="full", mode=None):
    require(scope in {"full", "lead-sample"}, "Scope must be full or lead-sample")
    items = [{"id": asset["asset_id"], "kind": "image"} for asset in image_assets(job)] if scope == "full" else []
    mode = video_mode(job, mode)
    captions = caption_mode(job)
    for lead in job["leads"]:
        if mode == SINGLE_VIDEO:
            items.append({"id": f"{lead['id']}-source", "kind": "source-video", "lead_id": lead["id"], "video_mode": mode})
            if captions == WITH_CAPTIONS:
                items.append({"id": f"{lead['id']}-subtitles", "kind": "subtitle", "lead_id": lead["id"]})
            items.append({"id": lead["id"], "kind": "video", "video_mode": mode})
            continue
        items.extend({"id": f"{lead['id']}-frame-{shot['second']:02d}", "kind": "image"} for shot in lead["seconds"])
        if scope == "lead-sample":
            items.extend({"id": f"{lead['id']}-source-{shot['second']:02d}", "kind": "source-video"} for shot in lead["seconds"])
            if captions == WITH_CAPTIONS:
                items.append({"id": f"{lead['id']}-subtitles", "kind": "subtitle", "lead_id": lead["id"]})
        items.append({"id": lead["id"], "kind": "video"})
    return items + ([{"id": "detail-page", "kind": "export"}] if scope == "full" else [])


def srt(lead, display=False):
    from typography import display_caption
    blocks = []
    for shot in lead["seconds"]:
        caption = display_caption(shot) if display else shot["caption"]
        if caption:
            n = shot["second"]
            blocks.append(f"{n}\n00:00:{n-1:02d},000 --> 00:00:{n:02d},000\n{caption}")
    return "\n\n".join(blocks) + "\n"


def ingest(prompt_path, output, job_id, brand, selected_type, requested_caption_mode=None):
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
    write_json(output, {"schema_version": 1, "video_mode": SINGLE_VIDEO,
                        "caption_mode": caption_mode({}, requested_caption_mode), "job_id": job_id, "brand": brand, "type": selected_type,
                        "status": "draft", "source_prompt": source, "product": {"photos": [], "confirmed_facts": []},
                        "sections": sections, "leads": []})


def plan(job_path, workspace, output, scope="full", reuse_sample=None, mode=None, requested_caption_mode=None, reuse_source_plan=None):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    require(output.is_relative_to(workspace), "Plan directory must be inside workspace")
    job = validate(read_json(job_path), workspace)
    captions = caption_mode(job, requested_caption_mode)
    require(scope in {"full", "lead-sample"}, "Scope must be full or lead-sample")
    require(not reuse_sample or scope == "full", "Only full plans can reuse a verified lead sample")
    require(not (reuse_sample and reuse_source_plan), "Choose sample reuse or source-plan reuse, not both")
    state_path = output / "state.json"
    if state_path.exists():
        state = load_state(state_path)
        expected_input = state.get("input_job_sha256", state["job_sha256"])
        require(digest(job_path) in {expected_input, state["job_sha256"]}, "Plan already exists for different job content")
        require(state.get("scope", "full") == scope, "Plan exists for a different scope; use another plan folder")
        require(mode is None or mode == state.get("video_mode", LEGACY_VIDEO), "Existing plan uses a different video mode; preserve it and choose a new folder")
        require(requested_caption_mode is None or captions == caption_mode(state), "Existing plan uses a different caption mode; choose a new plan and output folder")
        return state_path
    if requested_caption_mode is not None:
        job = dict(job, caption_mode=captions)
    reused = None
    reuse_path = reuse_sample or reuse_source_plan
    if reuse_path:
        reused = load_state(reuse_path)
        reuse_mode = reused.get("video_mode", LEGACY_VIDEO)
        require(mode is None or mode == reuse_mode, "Cannot reuse sample across video modes")
        mode = reuse_mode
        if reuse_sample:
            require(reused.get("scope") == "lead-sample" and reused["status"] == "sample_verified", "Sample has not been verified")
        else:
            require(mode == SINGLE_VIDEO, "Source-plan reuse requires single-source-v2")
        require(Path(reused["workspace"]).resolve() == workspace, "Sample and full plan must share a workspace")
        original = read_json(reused["job_path"])
        require(all(job[key] == original[key] for key in ("job_id", "brand", "type", "leads")), "Sample identity or lead script changed")
        require(job["product"]["photos"] == original["product"]["photos"], "Sample reference photos changed")
        require(job.get("model_binding") == original.get("model_binding"), "Sample fixed-model identity changed")
        if reuse_sample:
            complete(reuse_sample)
            reused = load_state(reuse_sample)
        else:
            original = dict(original, video_mode=mode)
            for item in reused["artifacts"]:
                if item["kind"] == "source-video" and item.get("status") == "verified":
                    proof = verify_evidence(workspace, item, item["file"], item["qa_file"], reused["job_identity"], original, reused)
                    require(all(item.get(k) == v for k, v in proof.items()), f"Reusable source/evidence changed: {item['id']}")
    mode = video_mode(job, mode)
    # A CLI selection is saved in a scoped job copy, keeping existing job hashes intact.
    input_job_path = Path(job_path).resolve()
    input_job_sha256 = digest(input_job_path)
    if requested_caption_mode is not None:
        selected_job_path = output / "job.json"
        require(not selected_job_path.exists() or selected_job_path.resolve() == input_job_path,
                "Plan job copy exists; choose a new output folder")
        write_json(selected_job_path, job)
        job_path = selected_job_path
    (output / "prompts").mkdir(parents=True, exist_ok=True)
    tasks = []
    planned_images = image_assets(job) if scope == "full" else []
    for asset in planned_images:
        (output / "prompts" / f"{asset['asset_id']}.txt").write_text(asset["image_prompt"], encoding="utf-8")
    write_json(output / "image-tasks.json", planned_images)
    flow_tasks = []
    for lead in job["leads"]:
        if captions == WITH_CAPTIONS:
            (output / f"{lead['id']}.srt").write_text(srt(lead, display=mode == SINGLE_VIDEO), encoding="utf-8")
        (output / f"{lead['id']}.source-captions.srt").write_text(srt(lead), encoding="utf-8")
        if mode == SINGLE_VIDEO:
            storyboard = lead.get("storyboard_prompt") or ("Create ONE video containing the following five-scene storyboard. "
                "Use one output (x1). No generated text/subtitles. Preserve the referenced product. "
                "Final delivery is five seconds; if the UI only supports another duration, create ONE supported-length source for local editing.\n\n" +
                "\n\n".join(f"{shot['second']-1}–{shot['second']}s: {shot['action']}\n{shot['video_prompt']}" for shot in lead["seconds"]))
            (output / "prompts" / f"{lead['id']}-storyboard.txt").write_text(storyboard, encoding="utf-8")
            flow_tasks.append({"lead_id": lead["id"], "request_id": f"{lead['id']}-generation-01", "max_submissions": 1,
                "output_count": 1, "source_asset_id": f"{lead['id']}-source", "final_asset_id": lead["id"],
                "reference_images": lead_references(job, lead), "prompt_file": f"prompts/{lead['id']}-storyboard.txt",
                "requested_final_seconds": 5, "source_duration_policy": "one_current_ui_supported_duration",
                "ui_cost_evidence_required": True, "automatic_per_scene_generation": False,
                "requires_state_check_before_submission": True})
        for shot in lead["seconds"]:
            if mode == SINGLE_VIDEO:
                tasks.append(dict(shot, lead_id=lead["id"], source_asset_id=f"{lead['id']}-source",
                                  start_frame=(shot["second"] - 1) * 30, end_frame=shot["second"] * 30))
                continue
            aid = f"{lead['id']}-frame-{shot['second']:02d}"
            (output / "prompts" / f"{aid}.txt").write_text(shot["image_prompt"], encoding="utf-8")
            tasks.append(dict(shot, lead_id=lead["id"], image_asset_id=aid,
                              start_frame=(shot["second"] - 1) * 30, end_frame=shot["second"] * 30))
    write_json(output / "timeline.json", {"fps": 30, "frames_per_lead": 150, "end_frame_exclusive": True, "caption_mode": captions, "tasks": tasks})
    if mode == SINGLE_VIDEO:
        write_json(output / "flow-tasks.json", {"video_mode": mode, "tasks": flow_tasks})
    items = [dict(item, status="pending") for item in artifacts(job, scope, mode)]
    if reused:
        reusable = {item["id"]: item for item in reused["artifacts"]}
        if reuse_source_plan:
            reusable = {aid: item for aid, item in reusable.items() if item["kind"] == "source-video" and item.get("status") == "verified"}
        elif caption_mode(reused) != captions:
            reusable = {aid: item for aid, item in reusable.items() if item["kind"] not in {"video", "subtitle", "export"}}
        items = [dict(reusable[item["id"]]) if item["id"] in reusable else item for item in items]
    state = {"schema_version": 2 if mode == SINGLE_VIDEO else 1, "video_mode": mode, "caption_mode": captions,
                           "status": "in_progress" if reused else "planned", "scope": scope,
                           "page_complete": False, "workspace": str(workspace),
                           "job_path": str(Path(job_path).resolve()), "job_sha256": digest(job_path),
                           "job_identity": {key: job[key] for key in ("job_id", "brand", "type")},
                           "reference_sha256": [{"file": path, "sha256": digest(relative_path(path, workspace))}
                                                for path in job["product"]["photos"]],
                           "reused_sample": str(Path(reuse_sample).resolve()) if reuse_sample else None,
                           "artifacts": items}
    if Path(job_path).resolve() != input_job_path:
        state.update(input_job_path=str(input_job_path), input_job_sha256=input_job_sha256)
    if reuse_source_plan:
        state["reused_source_plan"] = str(Path(reuse_source_plan).resolve())
    if "model_binding" in job:
        state["model_binding"] = job["model_binding"]
    if mode == SINGLE_VIDEO:
        state["lead_reference_sha256"] = reference_records(job, workspace)
        state["generation_requests"] = reused["generation_requests"] if reused else [
            {"lead_id": lead["id"], "request_id": f"{lead['id']}-generation-01", "status": "not_submitted",
             "max_submissions": 1, "output_count": 1} for lead in job["leads"]]
    write_json(state_path, state)
    return state_path


def load_state(path):
    state = read_json(path)
    require(digest(state["job_path"]) == state["job_sha256"], "Source job changed; create a new plan")
    if "input_job_path" in state:
        require(digest(state["input_job_path"]) == state["input_job_sha256"], "Original input job changed; create a new plan")
    job = validate(read_json(state["job_path"]), state["workspace"])
    require(caption_mode(state) == caption_mode(job), "State caption mode differs from its source job")
    require(state.get("model_binding") == job.get("model_binding"), "State fixed-model binding differs from its source job")
    mode = video_mode(job, state.get("video_mode", LEGACY_VIDEO))
    require(state.get("job_identity") == {key: job[key] for key in ("job_id", "brand", "type")}, "State job identity changed")
    references = [{"file": path, "sha256": digest(relative_path(path, state["workspace"]))} for path in job["product"]["photos"]]
    require(state.get("reference_sha256") == references, "Reference photo changed; create a new plan")
    require([(a["id"], a["kind"]) for a in state["artifacts"]] == [(a["id"], a["kind"]) for a in artifacts(job, state.get("scope", "full"), mode)],
            "State artifact set does not match source job")
    if mode == SINGLE_VIDEO:
        for item, spec in zip(state["artifacts"], artifacts(job, state.get("scope", "full"), mode)):
            require(all(item.get(k) == v for k, v in spec.items()), "State artifact policy changed")
        require(state.get("schema_version") == 2, "Single-source plans require state schema 2")
        require(state.get("lead_reference_sha256") == reference_records(job, state["workspace"]), "Lead reference image changed")
        requests = state.get("generation_requests", [])
        require([r.get("lead_id") for r in requests] == ["lead-1", "lead-2"], "Exactly two generation request slots are allowed")
        for request in requests:
            require(request.get("request_id") == f"{request['lead_id']}-generation-01" and request.get("max_submissions") == 1
                    and request.get("output_count") == 1, "Each lead allows one request with output x1")
            require(request.get("status") in {"not_submitted", "reserved", "source_verified"}, "Unknown generation request state")
            if request["status"] != "not_submitted":
                validate_generation_evidence(state["workspace"], request)
    require(state.get("scope") != "lead-sample" or (state["status"] != "complete" and not state.get("page_complete")),
            "A lead sample cannot be a completed detail page")
    return state


def validate_generation_evidence(workspace, request):
    path = relative_path(request["evidence_file"], workspace)
    require(path.is_file() and digest(path) == request["evidence_sha256"], "Flow settings evidence changed")
    proof = read_json(path)
    require(proof.get("provider") == "Google Flow", "Generation provider must be Google Flow")
    require(type(proof.get("output_count")) is int and proof["output_count"] == 1, "Flow output count must be x1")
    for key in ("model", "credit_cost_ui"):
        nonempty(proof.get(key), f"Flow UI {key}")
    duration = proof.get("source_duration_seconds")
    require(type(duration) in (int, float) and math.isfinite(duration) and duration > 0, "Record the supported Flow source duration")
    screenshot = relative_path(proof["ui_evidence_file"], workspace)
    require(screenshot.is_file() and digest(screenshot) == proof.get("ui_evidence_sha256"), "Flow UI screenshot changed or is missing")
    return proof


def generation_start(state_path, lead_id, evidence_file):
    """Reserve before clicking Generate. Unknown outcomes stay reserved, never auto-retried."""
    state = load_state(state_path)
    require(state.get("video_mode") == SINGLE_VIDEO, "Generation reservations apply to single-source-v2")
    request = next((r for r in state["generation_requests"] if r["lead_id"] == lead_id), None)
    require(request is not None, "Unknown lead")
    require(request["status"] == "not_submitted", "Request already reserved/submitted; reconcile its existing Flow result instead of generating again")
    # Caption variants share the original request slot, including slots not yet used.
    # Reserving in the origin first prevents sibling plans from each paying for a clip.
    if state.get("reused_source_plan"):
        origin_path = state["reused_source_plan"]
        origin = load_state(origin_path)
        inherited = next(r for r in origin["generation_requests"] if r["lead_id"] == lead_id)
        if inherited["status"] != "not_submitted":
            request.update(inherited)
            state.update(status="in_progress", page_complete=False)
            write_json(state_path, state)
            raise ValueError("Request already reserved/submitted in the source plan; reconcile its existing Flow result instead of generating again")
        generation_start(origin_path, lead_id, evidence_file)
        inherited = next(r for r in load_state(origin_path)["generation_requests"] if r["lead_id"] == lead_id)
        request.update(inherited)
        state.update(status="in_progress", page_complete=False)
        write_json(state_path, state)
        return
    proof = {**request, "evidence_file": relative_path(evidence_file),
             "evidence_sha256": digest(relative_path(evidence_file, state["workspace"]))}
    validate_generation_evidence(state["workspace"], proof)
    request.update(proof, status="reserved")
    state.update(status="in_progress", page_complete=False)
    write_json(state_path, state)


def verify_caption_render(probe, selected_caption_mode, workspace=None, artifact=None, expected_lead=None):
    require(caption_mode(probe) == selected_caption_mode, "Rendered caption mode differs from the selected job mode")
    if probe.get("renderer") == "remotion":
        require(probe.get("subtitles_burned_in") is (selected_caption_mode == WITH_CAPTIONS)
                and probe.get("caption_band_px") == 0 and probe.get("full_bleed") is True
                and isinstance(probe.get("remotion_report_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", probe["remotion_report_sha256"]),
                "Remotion caption policy requires explicit text flags and an output-bound render report")
        if artifact is not None:
            verify_remotion_render(artifact, probe, read_json(Path(artifact).with_suffix(".sources.json")), expected_lead)
        return
    if selected_caption_mode == WITHOUT_CAPTIONS:
        require(probe.get("caption_mode") == WITHOUT_CAPTIONS and probe.get("subtitles_burned_in") is False
                and probe.get("renderer") == "ffmpeg_without_text" and probe.get("caption_band_px") == 0,
                "No-caption video requires explicit renderer evidence of no baked subtitles and no caption band")


def verify_remotion_render(artifact, probe, sources, expected_lead, source_job_path=None):
    """Bind a successful local render to its inputs, props, executable sources and font."""
    artifact = Path(artifact).resolve()
    require(expected_lead is not None, "Remotion verification requires the approved lead script")
    paths = {name: artifact.with_suffix(suffix) for name, suffix in (
        ("remotion", ".remotion.json"), ("remotion_props", ".remotion-props.json"), ("remotion_log", ".remotion.log"))}
    require(all(path.is_file() for path in paths.values()), "Remotion render evidence is missing")
    report, props = read_json(paths["remotion"]), read_json(paths["remotion_props"])
    selected = caption_mode(probe)
    require(probe.get("remotion_report_sha256") == digest(paths["remotion"]), "Remotion render report changed")
    require(report.get("renderer") == "remotion" and report.get("status") == "rendered_visual_review_required"
            and report.get("output_sha256") == probe.get("artifact_sha256") == digest(artifact)
            and report.get("caption_mode") == selected and report.get("source_provenance_preserved") is True
            and type(report.get("generation_requests_submitted")) is int and report["generation_requests_submitted"] == 0,
            "Remotion report does not identify this completed local render")
    require(report.get("props_sha256") == digest(paths["remotion_props"])
            and report.get("render_log_sha256") == digest(paths["remotion_log"]), "Remotion props or render log changed")
    job_path = Path(report.get("source_job_file", "")).resolve()
    require(job_path.is_file() and report.get("source_job_sha256") == digest(job_path), "Remotion source job changed or is missing")
    if source_job_path is not None:
        require(digest(source_job_path) == report["source_job_sha256"], "Remotion was rendered for a different selected job")
    rendered_job = read_json(job_path)
    rendered_lead = next((lead for lead in rendered_job.get("leads", []) if lead.get("id") == expected_lead.get("id")), None)
    require(rendered_lead == expected_lead and report.get("lead_id") == expected_lead["id"]
            and caption_mode(rendered_job) == selected, "Remotion lead script or selected caption mode differs from the approved job")
    expected_files = {"src/index.ts", "src/Root.tsx", "src/Composition.tsx", "remotion.config.ts", "package.json"}
    code = report.get("project_sources")
    require(isinstance(code, dict) and expected_files <= set(code), "Remotion executable-source hashes are incomplete")
    for relative, sha in code.items():
        path = relative_path(relative, REMOTION_ROOT)
        require(path.is_file() and digest(path) == sha, "Remotion executable source changed")
    lock = REMOTION_ROOT / "package-lock.json"
    require(lock.is_file() and report.get("dependency_lock_sha256") == digest(lock), "Remotion dependency lock changed")
    package = read_json(REMOTION_ROOT / "package.json")
    version = report.get("version")
    require(version == package.get("dependencies", {}).get("remotion")
            == read_json(REMOTION_ROOT / "node_modules/remotion/package.json").get("version"),
            "Remotion runtime version differs from the pinned project")
    clean = sources.get("clean_edit")
    require(isinstance(clean, dict), "Remotion clean-edit provenance is missing")
    clean_path = Path(clean.get("file", "")).resolve()
    require(clean_path.is_file() and clean_path != artifact and clean.get("sha256") == report.get("clean_edit_sha256")
            == probe.get("clean_edit_sha256") == digest(clean_path), "Remotion clean edit changed or was overwritten")
    clean_probe_path, clean_sources_path = clean_path.with_suffix(".probe.json"), clean_path.with_suffix(".sources.json")
    require(report.get("clean_probe_sha256") == digest(clean_probe_path)
            and report.get("clean_sources_sha256") == digest(clean_sources_path), "Remotion clean-edit evidence changed")
    clean_probe, clean_sources = read_json(clean_probe_path), read_json(clean_sources_path)
    require(clean_probe.get("artifact_sha256") == clean_sources.get("artifact_sha256") == digest(clean_path)
            and clean_probe.get("caption_mode") == WITHOUT_CAPTIONS and clean_probe.get("subtitles_burned_in") is False
            and clean_probe.get("caption_band_px") == 0 and clean_probe.get("full_bleed") is True
            and clean_sources.get("lead_id") == expected_lead["id"], "Remotion input is not the recorded clean five-second edit")
    from media import check_video
    check_video(clean_probe["metadata"], 150, 1280, 720)
    require(sources.get("sources") == clean_sources.get("sources")
            and sources.get("unique_source_files") == clean_sources.get("unique_source_files"),
            "Remotion changed the preserved original Flow edit intervals")
    clean_original = clean_path.with_suffix(".source-captions.srt")
    require(clean_original.is_file() and clean_original.read_text(encoding="utf-8-sig") == srt(expected_lead), "Remotion clean-edit original captions changed")
    copied_source = relative_path(props.get("sourceFile"), REMOTION_ROOT / "public")
    require(copied_source.is_file() and digest(copied_source) == digest(clean_path), "Remotion copied input footage changed")
    from typography import fullbleed_design, gmarket_font
    expected_design = fullbleed_design(expected_lead, 1280, 720, selected)
    require(props.get("captionMode") == selected and props.get("design") == probe.get("overlay_design") == expected_design,
            "Remotion typography props differ from the approved lead design")
    if selected == WITH_CAPTIONS:
        font_path = relative_path(props.get("fontFile"), REMOTION_ROOT / "public")
        require(font_path.is_file(), "Remotion copied Gmarket font is missing")
        font_metadata = gmarket_font(font_path)
        font_proof = read_json(artifact.with_suffix(".font.json"))
        require(font_metadata["postscript"] == font_proof.get("font_postscript") == probe.get("font_postscript") == "GmarketSansTTFBold"
                and font_proof.get("renderer") == "remotion" and font_proof.get("output_sha256") == digest(artifact)
                and font_proof.get("font_sha256") == report.get("font_sha256") == digest(font_path)
                and font_proof.get("browser_font_face_load_verified") is True, "Remotion actual Gmarket font-load evidence is missing")
    else:
        require(props.get("fontFile") is None and report.get("font_sha256") is None and probe.get("font_postscript") is None,
                "No-caption Remotion output must not load typography")
        require(artifact.with_suffix(".srt").is_file() and not artifact.with_suffix(".srt").read_text(encoding="utf-8-sig").strip(),
                "No-caption Remotion display SRT must be empty")
    return {f"{name}_sha256": digest(path) for name, path in paths.items()}


def verify_single_source_media(workspace, item, artifact, state):
    """Verify renderer provenance; visual product/typography QA is still independently required."""
    require(state is not None, "Single-source video requires plan context")
    source = next(a for a in state["artifacts"] if a["id"] == f"{item['id']}-source")
    require(source.get("status") == "verified", "Verify the original Flow source before the final MP4")
    source_path = relative_path(source["file"], workspace)
    require(digest(source_path) == source["sha256"] and source_path != artifact, "Original source changed or was overwritten by final MP4")
    captions = caption_mode(state)
    names = ("probe", "sources", "font") if captions == WITH_CAPTIONS else ("probe", "sources")
    sidecars = {name: artifact.with_suffix(f".{name}.json") for name in names}
    data = {name: read_json(path) for name, path in sidecars.items()}
    probe, sources = data["probe"], data["sources"]
    verify_caption_render(probe, captions)
    require(probe.get("artifact_sha256") == digest(artifact) and probe.get("full_bleed") is True
            and probe.get("caption_band_px") == 0 and probe.get("style") == "fullbleed-motion",
            "Final video must use full-bleed motion without a caption band")
    if captions == WITH_CAPTIONS:
        require(probe.get("font_postscript") == "GmarketSansTTFBold", "Captioned video must use Gmarket Sans Bold")
    else:
        require(sources.get("caption_mode") == WITHOUT_CAPTIONS, "Source record must identify the no-caption edit")
    require(sources.get("artifact_sha256") == digest(artifact) and sources.get("unique_source_files") == 1,
            "Final video must derive from one original Flow source")
    shots = sources.get("sources", [])
    require([s.get("second") for s in shots] == [1, 2, 3, 4, 5], "Five ordered local edit segments are required")
    require(all(Path(s["file"]).resolve() == source_path and s.get("sha256") == source["sha256"] for s in shots),
            "Edit source does not match the verified original Flow clip")
    if captions == WITH_CAPTIONS:
        font = data["font"]
        if probe.get("renderer") != "remotion":
            require(font.get("font_postscript") == "GmarketSansTTFBold" and font.get("fontselect")
                    and all("GmarketSansTTFBold" in line for line in font["fontselect"]), "Actual renderer font evidence is missing")
    proof = {f"{name}_sha256": digest(path) for name, path in sidecars.items()}
    if probe.get("renderer") == "remotion":
        lead = next(lead for lead in read_json(state["job_path"])["leads"] if lead["id"] == item["id"])
        proof.update(verify_remotion_render(artifact, probe, sources, lead, state["job_path"]))
    return proof


def verify_evidence(workspace, item, file, qa_file, expected=None, expected_job=None, state=None):
    artifact, qa_path = relative_path(file, workspace), relative_path(qa_file, workspace)
    require(artifact.is_file() and artifact.stat().st_size > 0, f"Missing/empty artifact: {file}")
    require(qa_path.is_file(), f"Missing QA evidence: {qa_file}")
    if item["kind"] == "source-video":
        with artifact.open("rb") as stream:
            require(b"ftyp" in stream.read(32), "Flow source must be an actual MP4 container")
    extra = {}
    if item["kind"] == "subtitle":
        require(expected_job is not None, "Subtitle verification requires the source job")
        lead_id = item["id"].removesuffix("-subtitles")
        lead = next(lead for lead in expected_job["leads"] if lead["id"] == lead_id)
        single = expected_job.get("video_mode") == SINGLE_VIDEO
        require(artifact.read_text(encoding="utf-8-sig") == srt(lead, display=single), "Subtitles do not exactly match the approved one-second display captions")
        if single:
            original = artifact.with_suffix(".source-captions.srt")
            require(original.is_file() and original.read_text(encoding="utf-8-sig") == srt(lead), "Original source captions must be preserved beside display subtitles")
            extra["source_captions_sha256"] = digest(original)
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
    required = CHECKS[item["kind"]]
    if expected_job and expected_job.get("model_binding") and item["kind"] in {"image", "video", "source-video"}:
        required = required | {"model_identity"}
    captions = caption_mode(expected_job or state or {})
    if item["kind"] == "video" and captions == WITHOUT_CAPTIONS:
        required = (required - {"subtitle_timing"}) | {"caption_absence"}
        probe_path = artifact.with_suffix(".probe.json")
        probe = read_json(probe_path)
        require(probe.get("artifact_sha256") == sha, "No-caption probe refers to different footage")
        verify_caption_render(probe, captions)
        original = artifact.with_suffix(".source-captions.srt")
        lead = next(lead for lead in expected_job["leads"] if lead["id"] == item["id"])
        require(original.is_file() and original.read_text(encoding="utf-8-sig") == srt(lead), "Original source captions must remain as data for no-caption video")
        extra.update(probe_sha256=digest(probe_path), source_captions_sha256=digest(original))
    if item.get("video_mode") == SINGLE_VIDEO:
        if item["kind"] == "source-video":
            require(state is not None, "Single-source evidence requires plan context")
            request = next(r for r in state["generation_requests"] if r["lead_id"] == item["lead_id"])
            require(request["status"] in {"reserved", "source_verified"}, "Reserve the single Flow request before generation")
            require(qa.get("generation_request_id") == request["request_id"] and type(qa.get("request_count")) is int
                    and qa["request_count"] == 1 and type(qa.get("output_count")) is int and qa["output_count"] == 1,
                    "Source QA must identify exactly one request and one output")
            nonempty(qa.get("provider_result_id"), "Actual Flow result identifier")
        elif item["kind"] == "video":
            required = required | ({"full_bleed", "font", "overlay_product_clear", "source_storyboard"} if captions == WITH_CAPTIONS
                                   else {"full_bleed", "source_storyboard"})
            extra.update(verify_single_source_media(workspace, item, artifact, state))
    require(required <= {check["name"] for check in checks}, "Required QA checks missing")
    return {"file": relative_path(file), "sha256": sha, "qa_file": relative_path(qa_file), "qa_sha256": digest(qa_path), **extra}


def record(state_path, asset_id, file, qa_file):
    state = load_state(state_path)
    item = next((a for a in state["artifacts"] if a["id"] == asset_id), None)
    require(item is not None, f"Unknown asset: {asset_id}")
    job = dict(read_json(state["job_path"]), video_mode=state.get("video_mode", LEGACY_VIDEO))
    proof = verify_evidence(state["workspace"], item, file, qa_file, state["job_identity"], job, state)
    item.update(proof, status="verified")
    if state.get("video_mode") == SINGLE_VIDEO and item["kind"] == "source-video":
        next(r for r in state["generation_requests"] if r["lead_id"] == item["lead_id"])["status"] = "source_verified"
    state["status"] = "in_progress"
    state["page_complete"] = False
    write_json(state_path, state)


def complete(state_path):
    state = load_state(state_path)
    job = dict(read_json(state["job_path"]), video_mode=state.get("video_mode", LEGACY_VIDEO))
    try:
        for item in state["artifacts"]:
            require(item.get("status") == "verified", f"Artifact not verified: {item['id']}")
            proof = verify_evidence(state["workspace"], item, item["file"], item["qa_file"], state["job_identity"], job, state)
            require(all(item.get(k) == v for k, v in proof.items()), f"Recorded artifact/evidence changed: {item['id']}")
        if state.get("scope") == "lead-sample" or state.get("video_mode") == SINGLE_VIDEO:
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
    p.add_argument("--caption-mode", choices=sorted(CAPTION_MODES), default=WITH_CAPTIONS)
    p = commands.add_parser("validate"); p.add_argument("job"); p.add_argument("--workspace")
    p = commands.add_parser("plan"); p.add_argument("job"); p.add_argument("--workspace", required=True); p.add_argument("--output", required=True)
    p.add_argument("--scope", choices=["full", "lead-sample"], default="full"); p.add_argument("--reuse-sample")
    p.add_argument("--video-mode", choices=sorted(VIDEO_MODES))
    p.add_argument("--caption-mode", choices=sorted(CAPTION_MODES), help="Save the selected caption mode in a new scoped job copy")
    p.add_argument("--reuse-source-plan", help="Reuse existing request reservations and verified original sources; re-edit locally without extra Flow generation")
    p = commands.add_parser("generation-start"); p.add_argument("state"); p.add_argument("lead_id"); p.add_argument("evidence_file")
    p = commands.add_parser("record"); p.add_argument("state"); p.add_argument("asset_id"); p.add_argument("file"); p.add_argument("qa_file")
    p = commands.add_parser("complete"); p.add_argument("state")
    args = parser.parse_args()
    try:
        if args.command == "ingest": ingest(args.prompt, args.output, args.job_id, args.brand, args.type, args.caption_mode)
        elif args.command == "validate": validate(read_json(args.job), args.workspace)
        elif args.command == "plan": print(plan(args.job, args.workspace, args.output, args.scope, args.reuse_sample, args.video_mode, args.caption_mode, args.reuse_source_plan))
        elif args.command == "generation-start": generation_start(args.state, args.lead_id, args.evidence_file)
        elif args.command == "record": record(args.state, args.asset_id, args.file, args.qa_file)
        elif args.command == "complete": complete(args.state)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
