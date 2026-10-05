"""Shared creative values for the FFmpeg preview and the unverified AE project builder."""
import re
from studio import require


def kinetic_design(lead, width, height, band):
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
    return {"name": "kinetic-lime-sample-v1", "sample_creative_not_brand_standard": True,
            "width": width, "height": height, "caption_band": band, "content_height": height - band,
            "font_family": "Malgun Gothic", "font_postscript": "MalgunGothicBold", "main_font_size": font_size,
            "accent_font_size": 16, "caption_center": [width / 2, height - 26],
            "accent_center": [width / 2, height - band + 14], "accent_slide_px": 10,
            "accent_pop": [{"time": 0, "scale": 88}, {"time": 0.06, "scale": 110}, {"time": 0.12, "scale": 100}],
            "lime_rgb": [204 / 255, 1, 0], "lime_ass": "&H00FFCC&", "progress_y": height - 4,
            "progress_left": 24, "progress_width": width - 48, "progress_height": 2, "progress_gap": 6,
            "shots": shots}
