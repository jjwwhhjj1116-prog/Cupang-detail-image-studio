"""Shared creative values for the FFmpeg preview and the unverified AE project builder."""
import re
import math
import struct
from pathlib import Path
from studio import require, caption_mode as resolve_caption_mode


def captionless_design(lead, width, height):
    """Keep footage motion without requiring any caption layout or font."""
    shots = []
    for source in lead["seconds"]:
        motion = source.get("motion", "none")
        require(motion in {"none", "zoom-in", "zoom-out"}, "Local motion cannot invent camera orbit")
        shots.append({"second": source["second"], "start": source["second"] - 1,
                      "end": source["second"], "caption": source["caption"],
                      "display_caption": "", "motion": motion, "zoom_amount": .025,
                      "enabled": False, "text_layers": []})
    return {"name": "fullbleed-without-captions", "caption_mode": "without-captions",
            "sample_creative_not_brand_standard": True, "width": width, "height": height,
            "caption_band": 0, "content_height": height, "font_family": None,
            "font_postscript": None, "background_box": False, "shots": shots}


def kinetic_design(lead, width, height, band, caption_mode=None):
    if resolve_caption_mode(lead, caption_mode) == "without-captions":
        return captionless_design(lead, width, height)
    require(type(band) is int and 64 <= band < height, "Kinetic style requires a caption band of at least 64 pixels")
    captions = [shot["caption"] for shot in lead["seconds"]]
    require(all("\n" not in caption and "\r" not in caption for caption in captions), "Kinetic captions must be single lines")
    font_size = min(28, int((width - 64) / max(len(caption) for caption in captions)), int((band - 30) / 1.5))
    require(font_size >= 14, "Kinetic caption cannot fit at a readable size")
    preferred = ["에어홀", "통기홀", "펀칭", "스트랩", "착용감", "조절", "운동", "챙", "답답함"]
    shots = []
    for shot in lead["seconds"]:
        caption = shot["caption"]
        keyword = shot.get("accent_keyword") or next((word for word in preferred if word in caption), None)
        if not keyword:
            words = re.findall(r"[\w가-힣]+", caption)
            keyword = max(words, key=len) if words else caption
        require(keyword in caption, "Accent keyword must appear in the unchanged original caption")
        shots.append({"second": shot["second"], "caption": caption, "keyword": keyword,
                      "start": shot["second"] - 1, "end": shot["second"]})
    return {"name": "kinetic-lime-sample-v1", "caption_mode": "with-captions", "sample_creative_not_brand_standard": True,
            "width": width, "height": height, "caption_band": band, "content_height": height - band,
            "font_family": "Malgun Gothic", "font_postscript": "MalgunGothicBold", "main_font_size": font_size,
            "accent_font_size": 16, "caption_center": [width / 2, height - 26],
            "accent_center": [width / 2, height - band + 14], "accent_slide_px": 10,
            "accent_pop": [{"time": 0, "scale": 88}, {"time": 0.06, "scale": 110}, {"time": 0.12, "scale": 100}],
            "lime_rgb": [204 / 255, 1, 0], "lime_ass": "&H00FFCC&", "progress_y": height - 4,
            "progress_left": 24, "progress_width": width - 48, "progress_height": 2, "progress_gap": 6,
            "shots": shots}


def gmarket_font(path):
    """Verify the supplied Bold font's actual name table; never silently substitute."""
    path = Path(path).resolve()
    require(path.is_file(), "GmarketSansTTFBold.ttf is required for fullbleed-motion")
    data, names = path.read_bytes(), {}
    require(data[:4] in {b"\x00\x01\x00\x00", b"OTTO"}, "Invalid font file")
    for index in range(struct.unpack_from(">H", data, 4)[0]):
        tag, _, offset, _ = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if tag != b"name":
            continue
        _, count, strings = struct.unpack_from(">HHH", data, offset)
        for row in range(count):
            platform, _, _, name, size, position = struct.unpack_from(">HHHHHH", data, offset + 6 + row * 12)
            if platform in (0, 3) and name in (1, 2, 6):
                raw = data[offset + strings + position:offset + strings + position + size]
                names.setdefault(name, set()).add(raw.decode("utf-16-be"))
    require("GmarketSansTTFBold" in names.get(6, set()), "The requested font must be Gmarket Sans TTF Bold")
    return {"path": path, "family": "Gmarket Sans TTF", "postscript": "GmarketSansTTFBold"}


def fullbleed_design(lead, width, height, caption_mode=None):
    """Overlay positions are creative choices, requiring review against the actual product."""
    if resolve_caption_mode(lead, caption_mode) == "without-captions":
        return captionless_design(lead, width, height)
    anchors = {"top-left": (0.08, 0.10, 7), "top-center": (0.50, 0.10, 8),
               "top-right": (0.92, 0.10, 9), "bottom-left": (0.08, 0.88, 1),
               "bottom-center": (0.50, 0.88, 2), "bottom-right": (0.92, 0.88, 3)}
    preferred = ["에어홀", "통기홀", "펀칭", "스트랩", "착용감", "조절", "운동", "챙", "답답함"]
    shots = []
    for source in lead["seconds"]:
        caption, overlay = source["caption"], source.get("overlay", {})
        require(isinstance(overlay, dict), "Caption overlay must be an object")
        mode = overlay.get("mode", "caption")
        require(mode in {"caption", "editorial"}, "Unknown fullbleed overlay mode")
        if mode == "editorial":
            shots.append(editorial_shot(source, width, height, anchors))
            continue
        anchor = overlay.get("anchor", "top-center")
        require(anchor in anchors, "Unknown caption anchor")
        display = overlay.get("display_caption", caption)
        require(isinstance(display, str) and display.strip(), "Display caption is required")
        require(" ".join(display.split()) == " ".join(caption.split()), "Display line breaks cannot change original caption words")
        lines = display.splitlines()
        require(1 <= len(lines) <= 2, "Use at most two full-caption lines")
        size = overlay.get("font_size", min(round(width * .053), int(width * .80 / max(len(line) for line in lines))))
        require(type(size) in {int, float} and math.isfinite(size) and 18 <= size <= height * .16, "Caption font size is out of bounds")
        color = overlay.get("color", "white")
        require(color in {"white", "black"}, "Caption color must be white or black")
        keyword = source.get("accent_keyword") or next((word for word in preferred if word in caption), "")
        require(not keyword or keyword in caption, "Accent keyword must come from the original caption")
        motion = source.get("motion", "none")
        require(motion in {"none", "zoom-in", "zoom-out"}, "Local motion can only be none, zoom-in or zoom-out; real 360 footage must come from Flow")
        x, y, alignment = anchors[anchor]
        shots.append({"second": source["second"], "start": source["second"] - 1, "end": source["second"],
                      "caption": caption, "display_caption": display, "keyword": keyword,
                      "anchor": anchor, "alignment": alignment, "position": [round(width * x), round(height * y)],
                      "font_size": size, "color": color, "motion": motion,
                      "slide_px": round(width * .015), "entry_seconds": .16, "zoom_amount": .025})
    return {"name": "fullbleed-motion-v2", "caption_mode": "with-captions", "sample_creative_not_brand_standard": True,
            "width": width, "height": height, "caption_band": 0, "content_height": height,
            "font_family": "G마켓 산스 TTF Bold", "font_postscript": "GmarketSansTTFBold",
            "background_box": False, "product_overlap_review_required": True, "shots": shots}


def display_caption(shot):
    """Plain-text representation of displayed copy; original caption remains separate."""
    overlay = shot.get("overlay", {})
    require(isinstance(overlay, dict), "Caption overlay must be an object")
    mode = overlay.get("mode", "caption")
    require(mode in {"caption", "editorial"}, "Unknown fullbleed overlay mode")
    if mode == "caption":
        return shot["caption"]
    require(isinstance(overlay.get("copy_change_reason"), str) and overlay["copy_change_reason"].strip(),
            "Editorial copy needs a recorded copy_change_reason")
    keyword, support = overlay.get("keyword"), overlay.get("support", "")
    require(isinstance(keyword, str) and keyword.strip(), "Editorial keyword is required")
    require(isinstance(support, str), "Editorial support must be text")
    require(type(overlay.get("enabled", True)) is bool, "Editorial enabled must be a boolean")
    for value in (keyword, support):
        require("\r" not in value and len(value.splitlines()) <= 2 and
                (not value or all(line.strip() for line in value.splitlines())),
                "Editorial copy must have at most two nonempty lines per layer")
    return "\n".join(text for text in (keyword, support) if text) if overlay.get("enabled", True) else ""


def editorial_shot(source, width, height, anchors):
    """Explicit, logged display-copy adaptation; original caption is never overwritten."""
    overlay, start = source["overlay"], source["second"] - 1
    display = display_caption(source)
    reason = overlay.get("copy_change_reason")
    require(isinstance(reason, str) and reason.strip(), "Editorial copy needs a recorded copy_change_reason")
    enabled = overlay.get("enabled", True)
    require(type(enabled) is bool, "Editorial enabled must be a boolean")
    keyword, support = overlay.get("keyword"), overlay.get("support", "")
    require(isinstance(keyword, str) and keyword.strip(), "Editorial keyword is required")
    require(isinstance(support, str), "Editorial support must be text")
    for label, value, limit in (("keyword", keyword, 2), ("support", support, 2)):
        require("\r" not in value and len(value.splitlines()) <= limit,
                f"Editorial {label} must have at most two lines")
        require(not value or all(line.strip() for line in value.splitlines()), "Editorial text cannot contain empty lines")
    anchor = overlay.get("anchor", "top-left")
    require(anchor in anchors, "Unknown caption anchor")
    ax, ay, alignment = anchors[anchor]
    position = overlay.get("position", [ax, ay])
    require(isinstance(position, list) and len(position) == 2 and
            all(type(n) in {int, float} and math.isfinite(n) and .03 <= n <= .97 for n in position),
            "Editorial position must contain two normalized coordinates between .03 and .97")
    color, support_color = overlay.get("color", "white"), overlay.get("support_color", overlay.get("color", "white"))
    require(color in {"white", "black"} and support_color in {"white", "black"}, "Editorial color must be white or black")
    size = overlay.get("keyword_font_size", round(width * .078))
    small = overlay.get("support_font_size", round(width * .020))
    require(type(size) in {int, float} and math.isfinite(size) and 24 <= size <= height * .23,
            "Editorial keyword font size is out of bounds")
    require(type(small) in {int, float} and math.isfinite(small) and 12 <= small <= size * .55,
            "Editorial support font size must be smaller than keyword")
    motion = source.get("motion", "none")
    require(motion in {"none", "zoom-in", "zoom-out"}, "Local motion cannot invent camera orbit")
    x, y = round(width * position[0]), round(height * position[1])
    gap = round(height * .016)
    keyword_height, support_height = len(keyword.splitlines()) * size * 1.18, len(support.splitlines()) * small * 1.2
    block_height = keyword_height + (gap + support_height if support else 0)
    top = y if anchor.startswith("top") else y - block_height
    require(top >= 0 and top + block_height <= height, "Editorial text block exceeds vertical canvas bounds")
    # All layers use top vertical anchors; bottom-* places the complete block by its lower edge.
    layer_alignment = {1: 7, 2: 8, 3: 9}.get(alignment, alignment)
    layers = []
    if enabled:
        layers.append({"role": "keyword", "text": keyword, "font_size": size, "alignment": layer_alignment,
                       "position": [x, round(top)], "start": start, "end": start + 1,
                       "entry_seconds": .14, "start_scale": 94, "slide_px": round(height * .018),
                       "color": color, "outline_width": .45, "shadow": .2})
        if support:
            layers.append({"role": "support", "text": support, "font_size": small, "alignment": layer_alignment,
                           "position": [x, round(top + keyword_height + gap)], "start": start + .06, "end": start + 1,
                           "entry_seconds": .18, "start_scale": 99, "slide_px": round(height * .012),
                           "color": support_color, "outline_width": .35, "shadow": .1})
    return {"second": source["second"], "start": start, "end": start + 1, "caption": source["caption"],
            "display_caption": display, "keyword": keyword,
            "overlay_mode": "editorial", "enabled": enabled, "copy_change_reason": reason,
            "anchor": anchor, "alignment": alignment, "position": [x, y], "font_size": size,
            "color": color, "motion": motion, "slide_px": round(height * .018), "entry_seconds": .14,
            "zoom_amount": .025, "text_layers": layers, "placement_review_required": True}
