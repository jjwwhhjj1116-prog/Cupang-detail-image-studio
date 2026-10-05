#!/usr/bin/env python3
"""Assemble five Flow clips into a verified five-second lead; no media generation."""
import argparse
import copy
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from studio import digest, read_json, require, srt, validate, write_json


def run(argv, cwd=None):
    return subprocess.run([str(arg) for arg in argv], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def probe(path, ffprobe="ffprobe"):
    return json.loads(run([ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                           "-show_entries", "stream=nb_read_frames,avg_frame_rate,width,height:format=duration",
                           "-of", "json", Path(path).resolve()]))


def check_video(metadata, frames, width, height):
    streams = metadata.get("streams", [])
    require(len(streams) == 1, "Exactly one video stream is required")
    stream = streams[0]
    require(int(stream.get("nb_read_frames", 0)) == frames, f"Video must contain exactly {frames} frames")
    require(Fraction(stream["avg_frame_rate"]) == 30, "Video must be 30 fps")
    require((stream["width"], stream["height"]) == (width, height), "Video dimensions do not match")
    require(abs(float(metadata["format"]["duration"]) - frames / 30) <= 0.04, "Video duration is out of tolerance")


def ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r", "").replace("\n", "\\N")


def ass(lead, width, height, caption_band=0, style="plain"):
    require(style in {"plain", "kinetic", "fullbleed-motion"}, "Unknown typography style")
    if style == "fullbleed-motion":
        require(caption_band == 0, "Fullbleed motion forbids a caption band")
        return fullbleed_ass(lead, width, height)
    if style == "kinetic":
        return kinetic_ass(lead, width, height, caption_band)
    require(type(caption_band) is int and 0 <= caption_band < height, "Caption band must be nonnegative and smaller than video height")
    font_size = max(18, round(width / 22))
    alignment, margin_v, position = 2, round(height * .07), ""
    if caption_band:
        lines = [line for shot in lead["seconds"] for line in shot["caption"].splitlines()]
        line_count = max(len(shot["caption"].splitlines()) for shot in lead["seconds"])
        font_size = min(font_size, int((caption_band - 12) / (1.5 * line_count)),
                        int((width - 48) / max(len(line) for line in lines)))
        require(font_size >= 14, "Caption band is too small for readable captions")
        alignment, margin_v = 5, 0
        position = f"{{\\an5\\pos({width / 2:g},{height - caption_band / 2:g})}}"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,{alignment},24,24,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(
        f"Dialogue: 0,0:00:0{s['second'] - 1}.00,0:00:0{s['second']}.00,Default,,0,0,0,,{position}{ass_escape(s['caption'])}"
        for s in lead["seconds"]) + "\n"


def kinetic_ass(lead, width, height, caption_band):
    from typography import kinetic_design
    design = kinetic_design(lead, width, height, caption_band)
    base = ass(lead, width, height, caption_band)
    header = base[:base.index("Dialogue:")]
    lines = []
    def event(shot, layer, tags, text):
        return f"Dialogue: {layer},0:00:0{shot['start']}.00,0:00:0{shot['end']}.00,Default,,0,0,0,,{{{tags}}}{text}"
    cx, cy = design["caption_center"]
    ax, ay = design["accent_center"]
    for shot in design["shots"]:
        lines.append(event(shot, 1, f"\\an5\\pos({cx:g},{cy:g})\\fs{design['main_font_size']}\\bord0", ass_escape(shot["caption"])))
        accent = (f"\\an5\\move({ax-10:g},{ay:g},{ax:g},{ay:g},0,120)\\fs16\\bord0"
                  f"\\c{design['lime_ass']}\\fscx88\\fscy88\\t(0,60,\\fscx110\\fscy110)\\t(60,120,\\fscx100\\fscy100)")
        lines.append(event(shot, 2, accent, ass_escape(shot["keyword"])))
        step = (width - 48) / 5
        for index in range(5):
            x, y = 24 + index * step, design["progress_y"]
            bar_width = step - design["progress_gap"]
            color = design["lime_ass"] if index < shot["second"] else "&H333333&"
            tags = f"\\an7\\pos({x:g},{y:g})\\p1\\bord0\\shad0\\c{color}"
            lines.append(event(shot, 0, tags, f"m 0 0 l {bar_width:g} 0 l {bar_width:g} 2 l 0 2"))
    return header + "\n".join(lines) + "\n"


def fullbleed_ass(lead, width, height):
    from typography import fullbleed_design
    design = fullbleed_design(lead, width, height)
    header = ass(lead, width, height).split("Dialogue:", 1)[0]
    header = header.replace("Malgun Gothic", design["font_family"])
    events = []
    for shot in design["shots"]:
        if shot.get("overlay_mode") == "editorial":
            for layer in shot["text_layers"]:
                x, y = layer["position"]
                fill, outline = ("&HFFFFFF&", "&H181818&") if layer["color"] == "white" else ("&H151515&", "&HFFFFFF&")
                entry = round(layer["entry_seconds"] * 1000)
                tags = (f"\\an{layer['alignment']}\\move({x},{y+layer['slide_px']},{x},{y},0,{entry})"
                        f"\\fs{layer['font_size']}\\bord{layer['outline_width']}\\shad{layer['shadow']}\\1c{fill}\\3c{outline}"
                        f"\\fscx{layer['start_scale']}\\fscy{layer['start_scale']}"
                        f"\\t(0,{entry},\\fscx100\\fscy100)")
                events.append(f"Dialogue: {2 if layer['role'] == 'keyword' else 3},{ass_timestamp(layer['start'])},{ass_timestamp(layer['end'])},Default,,0,0,0,,{{{tags}}}{ass_escape(layer['text'])}")
            continue
        x, y = shot["position"]
        fill, outline = ("&HFFFFFF&", "&H181818&") if shot["color"] == "white" else ("&H151515&", "&HFFFFFF&")
        tags = (f"\\an{shot['alignment']}\\move({x},{y+shot['slide_px']},{x},{y},0,160)"
                f"\\fs{shot['font_size']}\\bord1.6\\shad0.6\\1c{fill}\\3c{outline}"
                "\\fscx96\\fscy96\\t(0,160,\\fscx100\\fscy100)")
        # One unchanged full caption remains visible for its entire one-second interval.
        text = ass_escape(shot["display_caption"])
        events.append(f"Dialogue: 1,0:00:0{shot['start']}.00,0:00:0{shot['end']}.00,Default,,0,0,0,,{{{tags}}}{text}")
    return header + "\n".join(events) + "\n"


def ass_timestamp(seconds):
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def rendered_srt(lead, design=None):
    """Plain copy per scene; ASS retains exact independent layer animation timing."""
    if not design or not any(s.get("overlay_mode") == "editorial" for s in design["shots"]):
        return srt(lead)
    return srt(lead, display=True)


def assemble(lead, clips, output, width, height, ffmpeg="ffmpeg", ffprobe="ffprobe", audio=None, starts=None, caption_band=0, style="plain", source_durations=None, font_path=None):
    require(len(clips) == 5, "Exactly five source clips are required, ordered by second")
    starts = starts if starts is not None else [0.0] * 5
    require(len(starts) == 5 and all(isinstance(n, (int, float)) and math.isfinite(n) and n >= 0 for n in starts),
            "Clip start offsets must contain five nonnegative finite seconds")
    source_durations = source_durations if source_durations is not None else [1.0] * 5
    require(len(source_durations) == 5 and all(type(n) in {int, float} and math.isfinite(n) and 1 / 99 <= n <= 100 for n in source_durations),
            "Source durations must contain five finite values from 1/99 to 100 seconds")
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and width % 2 == height % 2 == 0,
            "Video dimensions must be positive even integers")
    caption_script = ass(lead, width, height, caption_band, style)
    font, design = None, None
    if style == "fullbleed-motion":
        from typography import fullbleed_design, gmarket_font
        require(font_path is not None, "Provide the official GmarketSansTTFBold.ttf with --font")
        font, design = gmarket_font(font_path), fullbleed_design(lead, width, height)
    clips = [Path(path).resolve() for path in clips]
    output = Path(output).resolve()
    require(output.suffix.lower() == ".mp4", "Output must be an MP4 file")
    for clip in clips:
        require(clip.is_file(), f"Missing source clip: {clip}")
        require(clip != output, "Output cannot replace a source clip")
    source_metadata = {clip: probe(clip, ffprobe) for clip in set(clips)}
    for clip, begin, duration in zip(clips, starts, source_durations):
        available = float(source_metadata[clip]["format"]["duration"])
        require(begin + duration <= available + .000001, "Approved source window exceeds the source video duration")
    if audio:
        audio = Path(audio).resolve()
        require(audio.is_file() and audio != output, "Invalid audio source")
    require(not output.exists(), "Output exists; choose a new path to preserve the prior version")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lead-render-", dir=output.parent) as temp:
        temp = Path(temp)
        filters = f"fps=30,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        if caption_band:
            content_height = height - caption_band
            filters = (f"fps=30,scale={width}:{content_height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                       f"pad={width}:{height}:(ow-iw)/2:({content_height}-ih)/2:color=black,setsar=1")
        if style == "fullbleed-motion":
            filters = f"fps=30,scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
        for index, clip in enumerate(clips):
            segment = temp / f"segment-{index}.mp4"
            # Trim before retiming/resampling: no frame outside the approved half-open source window can enter.
            duration = source_durations[index]
            timed_filters = (f"trim=start=0:end={duration:.9f},setpts=(PTS-STARTPTS)/{duration:.9f},"
                             f"{filters},tpad=stop_mode=clone:stop_duration=1,trim=end_frame=30")
            if design and design["shots"][index]["motion"] != "none":
                shot = design["shots"][index]
                zoom = f"1+{shot['zoom_amount']}*on/29" if shot["motion"] == "zoom-in" else f"1+{shot['zoom_amount']}*(1-on/29)"
                timed_filters += f",zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30"
            run([ffmpeg, "-v", "error", "-nostdin", "-ss", starts[index], "-i", clip, "-map", "0:v:0", "-an", "-vf", timed_filters,
                 "-frames:v", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", segment])
            check_video(probe(segment, ffprobe), 30, width, height)
        (temp / "segments.txt").write_text("".join(f"file 'segment-{i}.mp4'\n" for i in range(5)), encoding="utf-8")
        (temp / "captions.ass").write_text(caption_script, encoding="utf-8-sig")
        if font:
            (temp / "fonts").mkdir()
            shutil.copyfile(font["path"], temp / "fonts/GmarketSansTTFBold.ttf")
        argv = [ffmpeg, "-v", "error", "-nostdin", "-f", "concat", "-safe", "1", "-i", "segments.txt"]
        if audio:
            argv += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-af", "apad,atrim=duration=5", "-c:a", "aac"]
        else:
            argv += ["-map", "0:v:0", "-an"]
        subtitle_filter = "subtitles=captions.ass:fontsdir=fonts" if font else "subtitles=captions.ass"
        argv += ["-vf", subtitle_filter, "-frames:v", "150", "-t", "5", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", "render.mp4"]
        if font:
            argv[2] = "info"
            execution = subprocess.run([str(arg) for arg in argv], cwd=temp, check=True, capture_output=True,
                                       text=True, encoding="utf-8", errors="replace")
            selected = [line for line in execution.stderr.splitlines() if "fontselect:" in line]
            if not selected or not all("GmarketSansTTFBold" in line.split("->", 1)[-1] for line in selected):
                output.with_suffix(".font-failure.log").write_text(execution.stderr, encoding="utf-8")
            require(selected and all("GmarketSansTTFBold" in line.split("->", 1)[-1] for line in selected),
                    f"Renderer selected a fallback font; fullbleed output is rejected: {selected}")
        else:
            run(argv, cwd=temp)
        metadata = probe(temp / "render.mp4", ffprobe)
        check_video(metadata, 150, width, height)
        shutil.copyfile(temp / "render.mp4", output)
        shutil.copyfile(temp / "captions.ass", output.with_suffix(".ass"))
    output.with_suffix(".srt").write_text(rendered_srt(lead, design), encoding="utf-8")
    if style == "fullbleed-motion":
        output.with_suffix(".source-captions.srt").write_text(srt(lead), encoding="utf-8")
    if design and any(s.get("overlay_mode") == "editorial" for s in design["shots"]):
        write_json(output.with_suffix(".copy-changes.json"), {
            "source_caption_preserved": True, "source_captions_file": output.with_suffix(".source-captions.srt").name,
            "display_captions_file": output.with_suffix(".srt").name,
            "srt_timing_scope": "Plain text per scene. ASS/overlay design contains independent animated layer timing.",
            "changes": [{"second": s["second"], "original_caption": s["caption"],
                         "display_caption": s["display_caption"], "reason": s["copy_change_reason"],
                         "enabled": s["enabled"]} for s in design["shots"] if s.get("overlay_mode") == "editorial"]})
    if font:
        write_json(output.with_suffix(".font.json"), {"font_family": font["family"], "font_postscript": font["postscript"],
                   "font_sha256": digest(font["path"]), "fontselect": selected, "global_install_required_for_ffmpeg": False})
    write_json(output.with_suffix(".sources.json"), {
        "lead_id": lead["id"], "artifact_sha256": digest(output), "caption_band_px": caption_band, "style": style,
        "unique_source_files": len(set(clips)), "sources": [
            {"second": index + 1, "file": str(clip), "sha256": digest(clip), "start_seconds": starts[index],
             "selected_duration_seconds": source_durations[index], "output_duration_seconds": 1,
             "playback_speed": source_durations[index], "time_stretch_percent": 100 / source_durations[index],
             "source_end_seconds_exclusive": starts[index] + source_durations[index],
             "output_start_frame": index * 30, "output_end_frame_exclusive": (index + 1) * 30}
            for index, clip in enumerate(clips)]})
    write_json(output.with_suffix(".probe.json"), {
        "artifact_sha256": digest(output), "metadata": metadata,
        "mechanical_checks": {"duration": "pass", "frame_count": "pass", "fps": "pass", "dimensions": "pass"},
        "visual_review_required": ["product_fidelity", "subtitle_timing", "Korean font rendering", "scene action"],
        "caption_band_px": caption_band, "content_region": {"x": 0, "y": 0, "width": width, "height": height - caption_band},
        "style": style, "renderer": "ffmpeg_libass", "after_effects_render": False,
        "full_bleed": style == "fullbleed-motion", "font_postscript": font["postscript"] if font else "MalgunGothicBold",
        "overlay_design": design,
        "audio_mode": "provided_track" if audio else "mute"})
    return output


def single_source_plan(lead, segments):
    require(isinstance(segments, list) and all(isinstance(s, dict) for s in segments)
            and [s.get("second") for s in segments] == [1, 2, 3, 4, 5],
            "Single-source edit map must have five ordered second entries")
    edited, starts, durations = copy.deepcopy(lead), [], []
    for shot, segment in zip(edited["seconds"], segments):
        begin, duration = segment.get("start_seconds"), segment.get("source_duration", 1)
        require(type(begin) in {int, float} and math.isfinite(begin) and begin >= 0, "Invalid segment start")
        require(type(duration) in {int, float} and math.isfinite(duration) and 1 / 99 <= duration <= 100, "Invalid segment duration")
        require(not starts or begin >= starts[-1] + durations[-1] - .000001, "Source segments must be chronological and non-overlapping")
        starts.append(begin); durations.append(duration)
        for key in ("overlay", "motion", "accent_keyword"):
            if key in segment:
                shot[key] = segment[key]
    return edited, starts, durations


def assemble_single(lead, source, segments, output, width, height, **options):
    """Edit one generated storyboard clip; this function never submits a generation request."""
    require("starts" not in options and "source_durations" not in options, "Use the edit map for single-source timing")
    edited, starts, durations = single_source_plan(lead, segments)
    return assemble(edited, [source] * 5, output, width, height, starts=starts, source_durations=durations, **options)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job"); parser.add_argument("--lead", choices=["lead-1", "lead-2"], required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--clips", nargs=5, help="Legacy five-source editing")
    inputs.add_argument("--source", help="One Flow-generated five-scene storyboard video")
    parser.add_argument("--edit-map", help="JSON with five source segments and optional overlay/motion placement")
    parser.add_argument("--output", required=True)
    parser.add_argument("--starts", nargs=5, type=float, help="Usable action start in each source clip, in seconds")
    parser.add_argument("--source-durations", nargs=5, type=float, help="Approved source seconds per shot; each is retimed to exactly one output second")
    parser.add_argument("--width", type=int, required=True); parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--caption-band", type=int, default=0, help="Black lower caption band in pixels; default 0 preserves overlay layout")
    parser.add_argument("--style", choices=["plain", "kinetic", "fullbleed-motion"], default="plain")
    parser.add_argument("--font", help="Exact GmarketSansTTFBold.ttf required by fullbleed-motion")
    parser.add_argument("--ffmpeg", default="ffmpeg"); parser.add_argument("--ffprobe", default="ffprobe")
    sound = parser.add_mutually_exclusive_group(required=True)
    sound.add_argument("--mute", action="store_true"); sound.add_argument("--audio")
    args = parser.parse_args()
    try:
        job = validate(read_json(args.job))
        lead = next(item for item in job["leads"] if item["id"] == args.lead)
        if args.source:
            require(args.edit_map is not None and args.starts is None and args.source_durations is None,
                    "Single-source editing requires --edit-map and uses its exact segment timings")
            print(assemble_single(lead, args.source, read_json(args.edit_map)["segments"], args.output, args.width, args.height,
                  ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, audio=args.audio, caption_band=args.caption_band,
                  style=args.style, font_path=args.font))
        else:
            require(args.edit_map is None, "--edit-map belongs to --source")
            print(assemble(lead, args.clips, args.output, args.width, args.height, args.ffmpeg, args.ffprobe, args.audio,
                  args.starts, args.caption_band, args.style, args.source_durations, args.font))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
