"""Bind approved canonical model portraits to a job, without generating a new face."""
import argparse
import copy
from pathlib import Path

from studio import digest, read_json, relative_path, require, validate, write_json

MODEL_IDS = {"female-f01", "male-m01"}


def profiles(repo):
    repo = Path(repo).resolve()
    config = read_json(repo / "config/models.json")
    require(config.get("policy") == "fixed-pair", "Unknown model policy")
    models = config.get("models", [])
    require({m.get("id") for m in models} == MODEL_IDS and len(models) == 2, "The fixed pair must contain F01 and M01")
    result = {}
    for model in models:
        require((model.get("adult") is True or model.get("fictional_adult") is True) and model.get("concept_age", 0) >= 20, "Use the configured adult models")
        require(model.get("selection_status") in {"candidate", "locked_by_user"}, "Invalid selection status")
        source = relative_path(model["reference_file"], repo)
        require(source.is_file(), f"Missing canonical portrait for {model['id']}: restore the private model assets")
        require(digest(source) == model["sha256"], f"Canonical portrait changed for {model['id']}; create and select a new revision")
        for field, label in (("character_sheet", "Character sheet"), ("expression_sheet", "Expression sheet")):
            sheet = model.get(field)
            if sheet is not None:
                require(isinstance(sheet, dict) and type(sheet.get("revision")) is int and sheet["revision"] > 0,
                        f"{label} requires a positive revision")
                sheet_path = relative_path(sheet.get("file"), repo)
                require(sheet_path.is_file() and digest(sheet_path) == sheet.get("sha256"),
                        f"{label} changed or is missing for {model['id']}")
        result[model["id"]] = (model, source)
    return config, result


def bind(job_path, workspace, output, repo=None, model_ids=None):
    repo = Path(repo or Path(__file__).resolve().parents[1]).resolve()
    root, dest = Path(workspace).resolve(), Path(output).resolve()
    require(dest.is_relative_to(root) and dest != root, "Output job must stay inside the job workspace")
    require(not dest.exists(), "Use a new job revision; preserve previous jobs and QA")
    job = validate(read_json(job_path), root)
    config, available = profiles(repo)
    ids = model_ids or ["female-f01", "male-m01"]
    require(isinstance(ids, list) and ids and len(set(ids)) == len(ids) and set(ids) <= MODEL_IDS, "Select only F01/M01 without duplicates")
    require(job["brand"] in config["brands"], "Brand is not configured for these models")
    pending, records = [], []
    for model_id in ids:
        model, source = available[model_id]
        require(model["selection_status"] == "locked_by_user", f"{model_id} is a candidate: confirm the chosen face before production")
        relative = f"input/models/{model_id}-v{model['revision']}.png"
        target = relative_path(relative, root)
        require(not target.exists() or digest(target) == model["sha256"], "A job portrait changed; preserve the old binding")
        pending.append((source, target))
        records.append({"id": model_id, "gender": model["gender"], "file": relative,
                        "sha256": model["sha256"], "revision": model["revision"]})
        for field, suffix in (("character_sheet", "sheet"), ("expression_sheet", "expressions")):
            sheet = model.get(field)
            require(sheet is not None or not config.get(f"require_{field}_for_new_binding"),
                    f"Restore the fixed {field.replace('_', ' ')} for {model_id} before new production")
            if sheet is not None:
                sheet_relative = f"input/models/{model_id}-{suffix}-v{sheet['revision']}.png"
                sheet_target = relative_path(sheet_relative, root)
                require(not sheet_target.exists() or digest(sheet_target) == sheet["sha256"],
                        f"A job {field.replace('_', ' ')} changed; preserve the old binding")
                pending.append((relative_path(sheet["file"], repo), sheet_target))
                records[-1][field] = {"file": sheet_relative, "sha256": sheet["sha256"], "revision": sheet["revision"]}
    assignment = config["default_wearing_assignment"] if len(ids) == 2 else {"lead-1": ids[0], "lead-2": ids[0]}
    updated = copy.deepcopy(job)
    updated["model_binding"] = {"policy": "fixed-pair", "profiles": records,
                               "wearing_assignment": assignment, "identity_review_required": True}
    for source, target in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            import shutil
            shutil.copyfile(source, target)
    validate(updated, root)
    write_json(dest, updated)
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    binding = sub.add_parser("bind")
    binding.add_argument("job"); binding.add_argument("--workspace", required=True)
    binding.add_argument("--output", required=True); binding.add_argument("--repo")
    binding.add_argument("--model-ids", nargs="+", choices=sorted(MODEL_IDS))
    args = parser.parse_args()
    try:
        if args.command == "status":
            _, models = profiles(args.repo)
            for model_id, (model, _) in models.items():
                print(f"{model_id}: {model['selection_status']}, revision={model['revision']}, portrait hash verified")
        else:
            print(bind(args.job, args.workspace, args.output, args.repo, args.model_ids))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
