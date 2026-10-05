#!/usr/bin/env python3
"""Assemble five Flow clips into a verified five-second lead; no media generation."""
import argparse
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from studio import digest, read_json, require, validate, write_json


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


def ass(lead, width, height):
    font_size = max(18, round(width / 22))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,24,24,{round(height * .07)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(
        f"Dialogue: 0,0:00:0{s['second'] - 1}.00,0:00:0{s['second']}.00,Default,,0,0,0,,{ass_escape(s['caption'])}"
        for s in lead["seconds"]) + "\n"


def assemble(lead, clips, output, width, height, ffmpeg="ffmpeg", ffprobe="ffprobe", audio=None, starts=None):
    require(len(clips) == 5, "Exactly five source clips are required, ordered by second")
    starts = starts if starts is not None else [0.0] * 5
    require(len(starts) == 5 and all(isinstance(n, (int, float)) and math.isfinite(n) and n >= 0 for n in starts),
            "Clip start offsets must contain five nonnegative finite seconds")
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and width % 2 == height % 2 == 0,
            "Video dimensions must be positive even integers")
    clips = [Path(path).resolve() for path in clips]
    output = Path(output).resolve()
    require(output.suffix.lower() == ".mp4", "Output must be an MP4 file")
    for clip in clips:
        require(clip.is_file(), f"Missing source clip: {clip}")
        require(clip != output, "Output cannot replace a source clip")
    if audio:
        audio = Path(audio).resolve()
        require(audio.is_file() and audio != output, "Invalid audio source")
    require(not output.exists(), "Output exists; choose a new path to preserve the prior version")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lead-render-", dir=output.parent) as temp:
        temp = Path(temp)
        filters = f"fps=30,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        for index, clip in enumerate(clips):
            segment = temp / f"segment-{index}.mp4"
            run([ffmpeg, "-v", "error", "-nostdin", "-ss", starts[index], "-i", clip, "-map", "0:v:0", "-an", "-vf", filters,
                 "-frames:v", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", segment])
            check_video(probe(segment, ffprobe), 30, width, height)
        (temp / "segments.txt").write_text("".join(f"file 'segment-{i}.mp4'\n" for i in range(5)), encoding="utf-8")
        (temp / "captions.ass").write_text(ass(lead, width, height), encoding="utf-8-sig")
        argv = [ffmpeg, "-v", "error", "-nostdin", "-f", "concat", "-safe", "1", "-i", "segments.txt"]
        if audio:
            argv += ["-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-af", "apad,atrim=duration=5", "-c:a", "aac"]
        else:
            argv += ["-map", "0:v:0", "-an"]
        argv += ["-vf", "subtitles=captions.ass", "-frames:v", "150", "-t", "5", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", "render.mp4"]
        run(argv, cwd=temp)
        metadata = probe(temp / "render.mp4", ffprobe)
        check_video(metadata, 150, width, height)
        shutil.copyfile(temp / "render.mp4", output)
        shutil.copyfile(temp / "captions.ass", output.with_suffix(".ass"))
    write_json(output.with_suffix(".probe.json"), {
        "artifact_sha256": digest(output), "metadata": metadata,
        "mechanical_checks": {"duration": "pass", "frame_count": "pass", "fps": "pass", "dimensions": "pass"},
        "visual_review_required": ["product_fidelity", "subtitle_timing", "Korean font rendering", "scene action"],
        "audio_mode": "provided_track" if audio else "mute"})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job"); parser.add_argument("--lead", choices=["lead-1", "lead-2"], required=True)
    parser.add_argument("--clips", nargs=5, required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--starts", nargs=5, type=float, help="Usable action start in each source clip, in seconds")
    parser.add_argument("--width", type=int, required=True); parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg"); parser.add_argument("--ffprobe", default="ffprobe")
    sound = parser.add_mutually_exclusive_group(required=True)
    sound.add_argument("--mute", action="store_true"); sound.add_argument("--audio")
    args = parser.parse_args()
    try:
        job = validate(read_json(args.job))
        lead = next(item for item in job["leads"] if item["id"] == args.lead)
        print(assemble(lead, args.clips, args.output, args.width, args.height, args.ffmpeg, args.ffprobe, args.audio, args.starts))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
