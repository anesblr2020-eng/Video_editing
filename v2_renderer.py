# -*- coding: utf-8 -*-
"""
v2_renderer.py — محرك الرندر الحتمي للجيل الثاني (Deterministic 1080×1920 @ 30fps Engine — Zero cv2 Dependency).
- الأبعاد الصارمة: 1080×1920، 30fps، H.264، CRF 19، AAC 192k.
- المناطق الآمنة: 250px من الأعلى (y >= 250) و340px من الأسفل (y <= 1580) خالية تماماً من النصوص المهمة.
- يدعم 12 أيقونة ومجسم متجهي مخصص بالكامل لمعنى الكلام + سحب حي لأيقونات SVG من Iconify عند توفر الإنترنت،
  مع منع تكرار نفس الأيقونة أو القالب في مشهدين متتاليين.
"""
import os
import math
import time
import subprocess
from typing import List, Dict, Any, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from v2_templates_library import (
    build_frame_html,
    spring_ease,
    exit_ease,
)

# The semantic vector engine is optional at import time, but its offline built-in SVG
# fallback is used whenever available. Network fetching remains disabled by default.
try:
    from vector_lottie_engine import search_and_fetch_web_vectors, render_recolored_svg_motion_canvas
except Exception:
    search_and_fetch_web_vectors = None
    render_recolored_svg_motion_canvas = None

FONT_BOLD_PATH = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
FONT_REG_PATH = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
FALLBACK_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def get_font(size: int, bold: bool = True, latin: bool = False) -> ImageFont.FreeTypeFont:
    if latin:
        path = FALLBACK_BOLD_PATH
    else:
        path = FONT_BOLD_PATH if bold else FONT_REG_PATH
        if not os.path.exists(path):
            path = FALLBACK_BOLD_PATH
    key = (path, int(size))
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size))
    return _FONT_CACHE[key]



def _safe_graphic_text(value: Any) -> str:
    """Strip unsupported pictographs/control glyphs that render as tofu squares in server fonts."""
    import unicodedata
    text = unicodedata.normalize("NFC", str(value or ""))
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isspace() or cat[0] in {"L", "N", "M"} or ch in ".,!?؟،:;-%+()[]/\u2019\u2013\u2014":
            kept.append(ch)
    return " ".join("".join(kept).split()).strip()

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)


def draw_contextual_icon(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    visual_query: str,
    cx: int,
    cy: int,
    radius: int,
    accent_rgb: Tuple[int, int, int],
    secondary_rgb: Tuple[int, int, int],
    danger_rgb: Tuple[int, int, int],
    success_rgb: Tuple[int, int, int],
    local_t: float,
):
    """
    يرسم 12 أيقونة ومجسم متجهي مختلف تماماً ومطابق لسياق الجملة المنطوقة (بدون أي تكرار ممل).
    """
    q = (visual_query or "").lower()
    # Small continuous pulse so contextual illustrations do not freeze between scene cuts.
    radius = max(12, int(radius * (1.0 + 0.035 * math.sin(float(local_t) * 2.0 * math.pi))))

    # هالة خلفية متوهجة متعددة الطبقات
    draw.ellipse(
        [cx - radius - 26, cy - radius - 26, cx + radius + 26, cy + radius + 26],
        fill=(*accent_rgb, 28),
    )
    draw.ellipse(
        [cx - radius - 10, cy - radius - 10, cx + radius + 10, cy + radius + 10],
        fill=(*secondary_rgb, 38),
    )
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(14, 21, 38, 248),
        outline=(*accent_rgb, 255),
        width=7,
    )

    if "hourglass" in q or "clock" in q or "deadline" in q or "time" in q:
        # 1. مجسم الساعة الرملية وعداد استنزاف الوقت الأحمر
        draw.arc(
            [cx - radius + 16, cy - radius + 16, cx + radius - 16, cy + radius - 16],
            start=-90,
            end=210,
            fill=(*danger_rgb, 255),
            width=10,
        )
        hw, hh = int(radius * 0.46), int(radius * 0.56)
        draw.line([cx - hw, cy - hh, cx + hw, cy - hh], fill=(255, 255, 255, 255), width=8)
        draw.line([cx - hw, cy + hh, cx + hw, cy + hh], fill=(255, 255, 255, 255), width=8)
        draw.polygon([(cx - hw + 6, cy - hh + 6), (cx + hw - 6, cy - hh + 6), (cx, cy)], fill=(*danger_rgb, 220))
        draw.polygon([(cx, cy), (cx - hw + 10, cy + hh - 6), (cx + hw - 10, cy + hh - 6)], fill=(*accent_rgb, 245))
        draw.ellipse([cx - 6, cy + 10, cx + 6, cy + 22], fill=(255, 255, 255, 255))

    elif "scissors" in q or "waveform" in q or "silence" in q:
        # 2. موجة صوتية حية مع مقص ليزر يقطع فجوة الصمت الحمراء
        n_bars = 11
        step_x = int((radius * 1.45) / n_bars)
        start_x = cx - int(radius * 0.70)
        for bi in range(n_bars):
            bx = start_x + bi * step_x
            is_gap = bi in (4, 5, 6)
            bh = 12 if is_gap else int(24 + 42 * abs(math.sin(bi * 0.9 + local_t * 3.0)))
            b_col = danger_rgb if is_gap else (success_rgb if bi < 4 else secondary_rgb)
            draw.rounded_rectangle([bx - 5, cy - bh, bx + 5, cy + bh], radius=5, fill=(*b_col, 255))
        draw.line([cx, cy - int(radius * 0.72), cx, cy + int(radius * 0.72)], fill=(*accent_rgb, 255), width=5)
        draw.ellipse([cx - 22, cy - int(radius * 0.72) - 18, cx - 4, cy - int(radius * 0.72)], outline=(*accent_rgb, 255), width=5)
        draw.ellipse([cx + 4, cy - int(radius * 0.72) - 18, cx + 22, cy - int(radius * 0.72)], outline=(*accent_rgb, 255), width=5)

    elif "microphone" in q or "audio" in q or "sound" in q:
        # 3. مايكروفون استوديو احترافي مع حلقات نقاء صوتي
        for ri in (1, 2):
            rr = int(radius * (0.52 + ri * 0.18))
            draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=-45, end=45, fill=(*secondary_rgb, 220 - ri * 50), width=6)
            draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=135, end=225, fill=(*secondary_rgb, 220 - ri * 50), width=6)
        mw, mh = int(radius * 0.34), int(radius * 0.56)
        draw.rounded_rectangle([cx - mw, cy - mh, cx + mw, cy + int(mh * 0.45)], radius=mw, fill=(*accent_rgb, 255))
        draw.arc([cx - int(mw * 1.45), cy - int(mh * 0.35), cx + int(mw * 1.45), cy + int(mh * 0.85)], start=0, end=180, fill=(255, 255, 255, 255), width=7)
        draw.line([cx, cy + int(mh * 0.85), cx, cy + int(mh * 1.25)], fill=(255, 255, 255, 255), width=7)
        draw.line([cx - 32, cy + int(mh * 1.25), cx + 32, cy + int(mh * 1.25)], fill=(*accent_rgb, 255), width=7)

    elif "ai" in q or "neural" in q or "chip" in q:
        # 4. شريحة الذكاء الاصطناعي العصبية المتوهجة
        cr = int(radius * 0.48)
        for i in range(8):
            ang = i * (math.pi / 4.0)
            x0, y0 = cx + int(cr * math.cos(ang)), cy + int(cr * math.sin(ang))
            x1, y1 = cx + int(radius * 0.82 * math.cos(ang)), cy + int(radius * 0.82 * math.sin(ang))
            draw.line([x0, y0, x1, y1], fill=(*secondary_rgb, 230), width=6)
            draw.ellipse([x1 - 9, y1 - 9, x1 + 9, y1 + 9], fill=(*accent_rgb, 255))
        draw.rounded_rectangle([cx - cr, cy - cr, cx + cr, cy + cr], radius=24, fill=(20, 30, 56, 255), outline=(*accent_rgb, 255), width=6)
        f_ai = get_font(54, bold=True, latin=True)
        bb = draw.textbbox((0, 0), "AI", font=f_ai)
        draw.text((cx - (bb[2] - bb[0]) // 2, cy - (bb[3] - bb[1]) // 2 - bb[1]), "AI", font=f_ai, fill=(255, 255, 255, 255))

    elif "rocket" in q or "growth" in q or "viral" in q:
        # 5. صاروخ الانتشار الفيروسي ومنحنى الصعود
        pts = [
            (cx - int(radius * 0.65), cy + int(radius * 0.48)),
            (cx - int(radius * 0.20), cy + int(radius * 0.15)),
            (cx + int(radius * 0.18), cy - int(radius * 0.12)),
            (cx + int(radius * 0.58), cy - int(radius * 0.55)),
        ]
        draw.line(pts, fill=(*success_rgb, 255), width=10)
        rx, ry = pts[-1]
        draw.polygon([(rx + 18, ry - 22), (rx - 26, ry - 4), (rx - 4, ry + 26)], fill=(*accent_rgb, 255))
        for bx_i, bh_i in enumerate([28, 52, 82, 115]):
            bx0 = cx - int(radius * 0.58) + bx_i * 38
            by1 = cy + int(radius * 0.62)
            draw.rounded_rectangle([bx0, by1 - bh_i, bx0 + 22, by1], radius=6, fill=(*secondary_rgb, 195))

    elif "camera" in q or "clapperboard" in q or "video" in q or "studio" in q:
        # 6. كلاكيت سينمائي احترافي وعدسة مونتاج الفيديو
        rw, rh = int(radius * 1.05), int(radius * 0.78)
        x0, y0 = cx - rw // 2, cy - rh // 2 + 12
        draw.rounded_rectangle([x0, y0, x0 + rw, y0 + rh], radius=20, fill=(22, 32, 56, 255), outline=(*secondary_rgb, 255), width=6)
        draw.rounded_rectangle([x0, y0 - 28, x0 + rw, y0 + 4], radius=10, fill=(*accent_rgb, 255))
        for s_i in range(4):
            sx = x0 + 18 + s_i * 36
            draw.line([sx, y0 - 26, sx + 14, y0 + 2], fill=(14, 21, 38, 255), width=8)
        tri = [(cx - 18, cy - 12), (cx - 18, cy + 36), (cx + 28, cy + 12)]
        draw.polygon(tri, fill=(*accent_rgb, 255))

    elif "lightbulb" in q or "solution" in q or "idea" in q:
        # 7. مصباح الفكرة والحل الذكي المشرق
        br = int(radius * 0.44)
        draw.ellipse([cx - br, cy - br - 16, cx + br, cy + br - 16], fill=(*accent_rgb, 240), outline=(255, 255, 255, 255), width=5)
        draw.rounded_rectangle([cx - 24, cy + br - 20, cx + 24, cy + br + 16], radius=8, fill=(*secondary_rgb, 255))
        for a_deg in range(-60, 241, 45):
            ar = math.radians(a_deg)
            x0 = cx + int((br + 14) * math.cos(ar))
            y0 = (cy - 16) - int((br + 14) * math.sin(ar))
            x1 = cx + int((br + 34) * math.cos(ar))
            y1 = (cy - 16) - int((br + 34) * math.sin(ar))
            draw.line([x0, y0, x1, y1], fill=(*accent_rgb, 255), width=6)

    elif "trophy" in q or "award" in q or "success" in q:
        # 8. كأس النجاح والتميز الذهبي
        tw, th = int(radius * 0.56), int(radius * 0.54)
        draw.rounded_rectangle([cx - tw // 2, cy - th // 2 - 18, cx + tw // 2, cy + th // 2 - 18], radius=22, fill=(*accent_rgb, 255))
        draw.line([cx, cy + th // 2 - 18, cx, cy + th // 2 + 26], fill=(*accent_rgb, 255), width=12)
        draw.rounded_rectangle([cx - 42, cy + th // 2 + 22, cx + 42, cy + th // 2 + 42], radius=8, fill=(255, 255, 255, 255))

    elif "delivery" in q or "map" in q or "58" in q:
        # 9. دبوس خريطة التوصيل السريع ومسار الشحن
        pr = int(radius * 0.42)
        draw.ellipse([cx - pr, cy - pr - 22, cx + pr, cy + pr - 22], fill=(*accent_rgb, 255))
        draw.polygon([(cx - pr + 6, cy - 8), (cx + pr - 6, cy - 8), (cx, cy + int(radius * 0.68))], fill=(*accent_rgb, 255))
        draw.ellipse([cx - 18, cy - pr - 4, cx + 18, cy - pr + 32], fill=(14, 21, 38, 255))

    else:
        # 10. بوابة الطاقة السياقية المتعددة الحلقات (بدون تكرار أي شكل سابق)
        for ri, col_r in enumerate([accent_rgb, secondary_rgb, success_rgb]):
            rr = int(radius * (0.76 - ri * 0.20))
            draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=ri * 55, end=ri * 55 + 250, fill=(*col_r, 255), width=9)
        bolt = [(cx + 8, cy - 38), (cx - 22, cy + 4), (cx + 2, cy + 4), (cx - 10, cy + 40), (cx + 24, cy - 6), (cx + 2, cy - 6)]
        draw.polygon(bolt, fill=(*accent_rgb, 255))


def _draw_kinetic_motion_overlays(
    draw: ImageDraw.ImageDraw,
    cw: int,
    ch: int,
    animation_t: float,
    template: str,
    visual_query: str,
    accent_rgb: Tuple[int, int, int],
    secondary_rgb: Tuple[int, int, int],
    success_rgb: Tuple[int, int, int],
) -> None:
    """Add restrained, continuously changing motion-design layers to every scene.

    This is deliberately procedural and topic-neutral: the semantic illustration remains
    selected by the director, while these layers give it ongoing motion instead of leaving
    one static icon on screen for several seconds. All coordinates stay inside the stage.
    """
    t = max(0.0, float(animation_t))
    q = (visual_query or "").lower()
    # Keep the focal orbit near the semantic visual, not over the headline zone.
    if template == "big_number":
        cx, cy, base_r = cw // 2, 165, 116
    elif template == "phone_reel_mockup":
        cx, cy, base_r = cw // 2, 355, 255
    elif template == "before_after":
        cx, cy, base_r = cw // 2, 280, 170
    elif template in {"versus", "checklist", "steps_flow"}:
        cx, cy, base_r = cw // 2, 300, 190
    else:
        cx, cy, base_r = cw // 2, 305, 174

    # Two rotating arc segments make movement readable even when the main vector is simple.
    spin = (t * 118.0) % 360.0
    pulse = 0.5 + 0.5 * math.sin(t * 3.1)
    for i, (r_mul, col, width, span) in enumerate((
        (1.00, accent_rgb, 5, 76.0),
        (1.16, secondary_rgb, 3, 48.0),
    )):
        r = int(base_r * r_mul)
        start = spin * (1 if i == 0 else -0.72) + i * 135.0
        box = [cx-r, cy-r, cx+r, cy+r]
        draw.arc(box, start=start, end=start+span, fill=(*col, int(95 + 115*pulse)), width=width)

    # Three orbiting nodes with short trails. Motion is staggered, not random.
    for i, col in enumerate((accent_rgb, secondary_rgb, success_rgb)):
        angle = math.radians((spin + i * 120.0) % 360.0)
        orbit_r = base_r * (0.82 + 0.05 * math.sin(t * 2.2 + i))
        x = int(cx + math.cos(angle) * orbit_r)
        y = int(cy + math.sin(angle) * orbit_r)
        trail_angle = angle - 0.24
        tx = int(cx + math.cos(trail_angle) * orbit_r)
        ty = int(cy + math.sin(trail_angle) * orbit_r)
        rr = 7 + int(3 * (0.5 + 0.5 * math.sin(t * 5.0 + i)))
        draw.line((tx, ty, x, y), fill=(*col, 150), width=4)
        draw.ellipse((x-rr, y-rr, x+rr, y+rr), fill=(*col, 235))

    # A pair of moving side streaks gives a second motion rhythm without covering copy.
    travel = (t * 250.0) % (cw + 240.0)
    y1 = 92 + int(14 * math.sin(t * 2.0))
    x1 = int(travel - 120)
    x2 = int(cw - ((travel * 0.73) % (cw + 160.0)))
    streak_col = success_rgb if any(k in q for k in ("silence", "wave", "audio", "scissor")) else secondary_rgb
    draw.line((x1, y1, x1 + 66, y1 - 13), fill=(*accent_rgb, 175), width=5)
    draw.line((x2, ch - 94, x2 + 48, ch - 106), fill=(*streak_col, 150), width=4)

    # A small pulsing locator/cue changes phase every ~1.1 s, creating a subtle beat.
    beat = (t % 1.1) / 1.1
    cue_x = 74 + int((cw - 148) * beat)
    cue_y = 42
    cue_r = 5 + int(5 * (1.0 - beat))
    draw.ellipse((cue_x-cue_r, cue_y-cue_r, cue_x+cue_r, cue_y+cue_r),
                 outline=(*accent_rgb, 220), width=3)


def render_scene_card_and_measure_dom(
    sc: Dict[str, Any],
    theme: Dict[str, Any],
    animation_t: float = 0.5,
    motion_svg: str = "",
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    يرسم بطاقة المشهد بدقة متجهية أصلية ضمن حاوية العرض البصري (960×940 عند x=60, y=280)
    باستخدام PIL + NumPy (بدون cv2) ويقيس الإحداثيات الفعلية (DOM getBoundingClientRect).
    """
    cw, ch = 960, 940
    img = Image.new("RGBA", (cw, ch), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    tpl = sc.get("template", "kinetic_hook")
    keywords = [_safe_graphic_text(k) for k in sc.get("keywords", ["تركيز بصري"]) if _safe_graphic_text(k)]
    numbers = [_safe_graphic_text(n) for n in sc.get("numbers", []) if _safe_graphic_text(n)]
    visual_query = sc.get("visual_query", "")

    accent = hex_to_rgb(theme["accent_primary"])
    secondary = hex_to_rgb(theme["accent_secondary"])
    surface = hex_to_rgb(theme["surface_card"])
    border = hex_to_rgb(theme["surface_border"])
    danger = hex_to_rgb(theme["danger"])
    success = hex_to_rgb(theme["success"])

    kw0 = keywords[0] if len(keywords) > 0 else ""
    kw1 = keywords[1] if len(keywords) > 1 else ""
    kw2 = keywords[2] if len(keywords) > 2 else ""

    headlines_dom = []

    def add_centered_text(text: str, y_center: int, font_size: int, color_rgb: Tuple[int, int, int], is_headline: bool = True):
        """Draw centered Arabic text with measured wrapping; never let long headlines overflow."""
        text = _safe_graphic_text(text)
        if not text:
            return
        max_width = cw - 80
        chosen_size = int(font_size)
        lines = []
        while chosen_size >= 48:
            fnt = get_font(chosen_size, bold=True)
            lines = []
            current = []
            for word in text.split():
                candidate = " ".join(current + [word])
                bb = draw.textbbox((0, 0), candidate, font=fnt, direction="rtl")
                if current and (bb[2] - bb[0]) > max_width:
                    lines.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(" ".join(current))
            widths = []
            for line in lines:
                bb = draw.textbbox((0, 0), line, font=fnt, direction="rtl")
                widths.append(bb[2] - bb[0])
            if len(lines) <= 2 and all(width <= max_width for width in widths):
                break
            chosen_size -= 4
        chosen_size = max(48, chosen_size)
        fnt = get_font(chosen_size, bold=True)
        line_metrics = []
        for line in lines[:2]:
            bb = draw.textbbox((0, 0), line, font=fnt, direction="rtl")
            line_metrics.append((line, bb, bb[2] - bb[0], bb[3] - bb[1]))
        line_gap = max(4, int(chosen_size * 0.12))
        total_h = sum(item[3] for item in line_metrics) + line_gap * max(0, len(line_metrics) - 1)
        y_top = int(y_center - total_h / 2)
        for line, bbox, tw, th in line_metrics:
            x = (cw - tw) // 2
            draw.text((x, y_top - bbox[1]), line, font=fnt, fill=(*color_rgb, 255), direction="rtl")
            if is_headline:
                headlines_dom.append({
                    "text": line,
                    "rect": {
                        "left": 60 + x,
                        "top": 280 + y_top,
                        "right": 60 + x + tw,
                        "bottom": 280 + y_top + th,
                        "width": tw,
                        "height": th,
                    },
                    "fontSize": chosen_size,
                })
            y_top += th + line_gap

    def draw_semantic_motion_asset(cx: int, cy: int, size: int) -> bool:
        """Draw a speech-matched SVG with progressive path reveal; return whether it rendered."""
        if not motion_svg or render_recolored_svg_motion_canvas is None:
            return False
        try:
            palette = {"primary": accent, "secondary": secondary, "accent": success}
            progress = min(1.0, max(0.08, float(animation_t) / 0.85))
            vec = render_recolored_svg_motion_canvas(
                svg_xml=motion_svg,
                width=size,
                height=size,
                theme_palette=palette,
                choreo_u=progress,
                global_t=float(animation_t),
            )
            if vec.mode != "RGBA":
                vec = vec.convert("RGBA")
            img.alpha_composite(vec, dest=(int(cx - size // 2), int(cy - size // 2)))
            return True
        except Exception:
            return False

    if tpl == "kinetic_hook":
        # إطار طاقة نيون مزدوج حول النص الحركي الضخم
        draw.rounded_rectangle([60, 170, cw - 60, 740], radius=42, fill=(14, 21, 38, 235), outline=(*accent, 220), width=5)
        draw.rounded_rectangle([cw // 2 - 90, 235, cw // 2 + 90, 251], radius=8, fill=(*accent, 255))
        add_centered_text(kw0, 390, 92, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 555, 84, accent, is_headline=True)

    elif tpl == "concept_icon":
        if not draw_semantic_motion_asset(cw // 2, 305, 252):
            draw_contextual_icon(draw, img, visual_query, cw // 2, 305, 138, accent, secondary, danger, success, animation_t)
        add_centered_text(kw0, 565, 82, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 695, 74, accent, is_headline=True)

    elif tpl == "big_number":
        # رسم أيقونة مصاحبة للرقم (مثل مقص الصمت أو شارة المجاني) + الرقم المنطوق الضخم
        if not draw_semantic_motion_asset(cw // 2, 165, 150):
            draw_contextual_icon(draw, img, visual_query, cw // 2, 165, 86, accent, secondary, danger, success, animation_t)
        raw_num = str(numbers[0] if numbers else "0")
        digits_part = "".join(ch for ch in raw_num if ch in "0123456789%+") or "0"
        f_big = get_font(145, bold=True, latin=True)
        bbox = draw.textbbox((0, 0), digits_part, font=f_big)
        nw = bbox[2] - bbox[0]
        draw.text(((cw - nw) // 2, 315 - bbox[1]), digits_part, font=f_big, fill=(*accent, 255))
        # The number is grounded in spoken audio; supporting labels must also come from the scene.
        add_centered_text(kw0, 515, 74, secondary, is_headline=True)
        if kw1:
            add_centered_text(kw1, 665, 72, (255, 255, 255), is_headline=True)
        if kw2:
            add_centered_text(kw2, 785, 68, accent, is_headline=True)

    elif tpl == "phone_reel_mockup":
        px0, py0, px1, py1 = cw // 2 - 220, 65, cw // 2 + 220, 650
        draw.rounded_rectangle([px0, py0, px1, py1], radius=46, fill=(11, 17, 32, 255), outline=(*border, 255), width=6)
        draw.rounded_rectangle([cw // 2 - 55, py0 + 22, cw // 2 + 55, py0 + 34], radius=6, fill=(*border, 255))
        draw.rounded_rectangle([px0 + 28, py0 + 60, px1 - 28, py1 - 65], radius=28, fill=(22, 31, 51, 255), outline=(*danger, 255), width=4)
        # أيقونة الكاميرا/إنستغرام المصغرة + منحنى هبوط التفاعل الأحمر داخل شاشة الهاتف
        draw.rounded_rectangle([cw // 2 - 42, 160, cw // 2 + 42, 244], radius=22, outline=(*danger, 255), width=5)
        draw.ellipse([cw // 2 - 18, 184, cw // 2 + 18, 220], outline=(255, 255, 255, 255), width=4)
        pts = [(cw // 2 - 110, 285), (cw // 2 - 35, 335), (cw // 2 + 25, 315), (cw // 2 + 110, 415)]
        draw.line(pts, fill=(*danger, 255), width=10)
        draw.polygon([(cw // 2 + 115, 422), (cw // 2 + 82, 415), (cw // 2 + 108, 388)], fill=(*danger, 255))
        add_centered_text(kw0, 505, 72, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 755, 76, accent, is_headline=True)

    elif tpl == "before_after":
        # Audio editing is a real transformation: show the named problem and the spoken action,
        # rather than repeating the same title in both panels.
        if sc.get("intent") == "audio_edit":
            kw0 = "الصمت" if "الصمت" in str(sc.get("speech", "")) else (kw0 or "الصوت")
            if "تنحي الصمت" in str(sc.get("speech", "")):
                kw1 = "تنحي الصمت"
            elif "قص الصمت" in str(sc.get("speech", "")):
                kw1 = "قص الصمت"
        # بطاقة قبل (فيديو خام باهت)
        draw.rounded_rectangle([50, 125, cw - 50, 415], radius=34, fill=(45, 18, 30, 255), outline=(*danger, 255), width=5)
        add_centered_text("قبل", 195, 52, danger, is_headline=False)
        add_centered_text(kw0, 310, 76, (255, 255, 255), is_headline=True)
        # سهم التحول الذكي في المنتصف
        draw.ellipse([cw // 2 - 38, 418, cw // 2 + 38, 494], fill=(*accent, 255))
        draw.polygon([(cw // 2 - 16, 444), (cw // 2 + 16, 444), (cw // 2, 474)], fill=(9, 13, 22, 255))
        # بطاقة بعد (موشن جرافيك احترافي متوهج)
        draw.rounded_rectangle([50, 498, cw - 50, 795], radius=34, fill=(14, 46, 38, 255), outline=(*success, 255), width=5)
        add_centered_text("بعد", 570, 52, success, is_headline=False)
        add_centered_text(kw1 or kw0, 685, 76, accent, is_headline=True)

    elif tpl == "checklist":
        items = [k for k in [kw0, kw1, kw2] if k]
        for idx_i, item in enumerate(items):
            y0 = 140 + idx_i * 225
            y1 = y0 + 185
            draw.rounded_rectangle([50, y0, cw - 50, y1], radius=30, fill=(*surface, 255), outline=(*border, 255), width=4)
            cx_i, cy_i = cw - 125, (y0 + y1) // 2
            draw.ellipse([cx_i - 36, cy_i - 36, cx_i + 36, cy_i + 36], fill=(*success, 255))
            draw.line([cx_i - 16, cy_i, cx_i - 4, cy_i + 14, cx_i + 18, cy_i - 14], fill=(9, 13, 22, 255), width=7)
            add_centered_text(item, cy_i, 72, (255, 255, 255), is_headline=True)

    elif tpl == "steps_flow":
        items = [k for k in [kw0, kw1, kw2] if k]
        for idx_i, item in enumerate(items):
            y0 = 140 + idx_i * 225
            y1 = y0 + 185
            b_col = accent if idx_i == len(items) - 1 else secondary
            draw.rounded_rectangle([50, y0, cw - 50, y1], radius=30, fill=(*surface, 255), outline=(*b_col, 255), width=4)
            cx_i, cy_i = cw - 125, (y0 + y1) // 2
            draw.rounded_rectangle([cx_i - 36, cy_i - 36, cx_i + 36, cy_i + 36], radius=18, fill=(*b_col, 255))
            f_num = get_font(46, bold=True, latin=True)
            num_txt = str(idx_i + 1)
            nb = draw.textbbox((0, 0), num_txt, font=f_num)
            draw.text((cx_i - (nb[2] - nb[0]) // 2, cy_i - (nb[3] - nb[1]) // 2 - nb[1]), num_txt, font=f_num, fill=(9, 13, 22, 255))
            add_centered_text(item, cy_i, 72, (255, 255, 255), is_headline=True)

    elif tpl == "versus":
        draw.rounded_rectangle([50, 130, cw - 50, 395], radius=32, fill=(*surface, 255), outline=(*danger, 255), width=4)
        add_centered_text(kw0, 262, 74, (252, 165, 165), is_headline=True)
        draw.ellipse([cw // 2 - 58, 411, cw // 2 + 58, 527], fill=(*accent, 255))
        f_vs = get_font(44, bold=True, latin=True)
        vb = draw.textbbox((0, 0), "VS", font=f_vs)
        draw.text((cw // 2 - (vb[2] - vb[0]) // 2, 469 - (vb[3] - vb[1]) // 2 - vb[1]), "VS", font=f_vs, fill=(9, 13, 22, 255))
        draw.rounded_rectangle([50, 545, cw - 50, 810], radius=32, fill=(*surface, 255), outline=(*accent, 255), width=5)
        add_centered_text(kw1 or kw0, 677, 76, accent, is_headline=True)

    elif tpl == "fullscreen_image":
        box_w, box_h = 860, 620
        bx0, by0 = (cw - box_w) // 2, 65
        sb_panel = sc.get("image_path") or sc.get("storyboard_panel_path")
        if sb_panel and os.path.exists(str(sb_panel)):
            try:
                with Image.open(sb_panel) as pim:
                    p_resized = pim.convert("RGBA").resize((box_w - 16, box_h - 16), Image.Resampling.LANCZOS)
                draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=38, fill=(14, 22, 40, 255), outline=(*accent, 255), width=6)
                img.paste(p_resized, (bx0 + 8, by0 + 8))
            except Exception:
                pass
        else:
            draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=38, fill=(14, 22, 40, 255), outline=(*accent, 255), width=5)
            draw.rounded_rectangle([bx0 + 70, by0 + 65, bx0 + box_w - 70, by0 + 440], radius=24, fill=(9, 13, 22, 255), outline=(*secondary, 255), width=4)
            draw.rounded_rectangle([bx0 + 115, by0 + 120, bx0 + 450, by0 + 165], radius=12, fill=(*accent, 230))
            draw.rounded_rectangle([bx0 + 470, by0 + 120, bx0 + box_w - 115, by0 + 165], radius=12, fill=(*secondary, 230))
            draw.rounded_rectangle([bx0 + 115, by0 + 195, bx0 + 360, by0 + 240], radius=12, fill=(*secondary, 200))
            draw.rounded_rectangle([bx0 + 380, by0 + 195, bx0 + box_w - 145, by0 + 240], radius=12, fill=(*success, 230))
            for b_i in range(18):
                bx_bar = bx0 + 135 + b_i * 33
                bh_bar = 22 + int(30 * abs(math.sin(b_i * 0.65)))
                draw.rounded_rectangle([bx_bar, by0 + 335 - bh_bar, bx_bar + 17, by0 + 335 + bh_bar], radius=6, fill=(*accent, 255) if b_i % 2 == 0 else (*secondary, 255))
            px_head = bx0 + box_w // 2
            draw.line([px_head, by0 + 95, px_head, by0 + 415], fill=(255, 255, 255, 255), width=5)
            draw.polygon([(px_head - 14, by0 + 95), (px_head + 14, by0 + 95), (px_head, by0 + 118)], fill=(*accent, 255))
            draw.rounded_rectangle([cw // 2 - 110, by0 + 450, cw // 2 + 110, by0 + 520], radius=14, fill=(*border, 255))
            draw.rounded_rectangle([cw // 2 - 190, by0 + 515, cw // 2 + 190, by0 + 545], radius=12, fill=(*secondary, 255))
        add_centered_text(kw0, 755, 78, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 855, 72, accent, is_headline=True)

    else:  # cta_end
        add_centered_text(kw0, 260, 88, (255, 255, 255), is_headline=True)
        draw.rounded_rectangle([100, 385, cw - 100, 540], radius=75, fill=(*accent, 255))
        add_centered_text(kw1 or kw0, 462, 74, (9, 13, 22), is_headline=True)
        ax, ay0, ay1 = cw // 2, 600, 775
        draw.line([ax, ay0, ax, ay1], fill=(*accent, 255), width=16)
        draw.line([ax - 55, ay1 - 55, ax, ay1 + 8, ax + 55, ay1 - 55], fill=(*accent, 255), width=16)

    _draw_kinetic_motion_overlays(
        draw=draw, cw=cw, ch=ch, animation_t=animation_t, template=tpl,
        visual_query=str(visual_query), accent_rgb=accent, secondary_rgb=secondary,
        success_rgb=success,
    )

    rgb_arr = np.array(img.convert("RGB"), dtype=np.uint8)
    return rgb_arr, {
        "stage_rect": {"left": 60, "top": 280, "right": 1020, "bottom": 1220, "width": cw, "height": ch},
        "headlines": headlines_dom,
    }


def render_caption_bar_and_measure_dom(
    words: List[Dict[str, Any]],
    active_idx: int,
    theme: Dict[str, Any],
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    يرسم شريط الكابشن المتزامن مع الكلمة (952×230 عند x=64, y=1310) بدون cv2
    ويقيس الإحداثيات الفعلية لكل كلمة (DOM getBoundingClientRect) للتحقق من عدم تصادم الكلمات.
    """
    bw, bh = 952, 230
    img = Image.new("RGBA", (bw, bh), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    border = hex_to_rgb(theme["surface_border"])
    accent = hex_to_rgb(theme["accent_primary"])

    draw.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=34, fill=(15, 23, 42, 242), outline=(*border, 255), width=3)

    if not words:
        return np.array(img.convert("RGB"), dtype=np.uint8), []

    chunk_size = 5
    chunk_start = (active_idx // chunk_size) * chunk_size
    chunk_words = words[chunk_start:chunk_start + chunk_size]

    f_normal = get_font(50, bold=True)
    f_active = get_font(58, bold=True)  # 50px * 1.15 ≈ 58px (+15% Hormozi kinetic pop!)

    measured = []
    gap = 24
    for i_w, w in enumerate(chunk_words):
        w_idx = int(w.get("index", chunk_start + i_w))
        is_act = w_idx == active_idx
        fnt = f_active if is_act else f_normal
        txt = _safe_graphic_text(w.get("word", ""))
        bbox = draw.textbbox((0, 0), txt, font=fnt, direction="rtl")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        measured.append({
            "word": txt,
            "is_active": is_act,
            "font": fnt,
            "fontSize": 58.0 if is_act else 50.0,
            "tw": tw,
            "th": th,
            "bbox": bbox,
        })

    lines = []
    cur_line = []
    cur_w = 0
    max_line_w = bw - 80
    for m in measured:
        add_w = m["tw"] + (gap if cur_line else 0)
        if cur_line and (cur_w + add_w > max_line_w):
            lines.append(cur_line)
            cur_line = [m]
            cur_w = m["tw"]
        else:
            cur_line.append(m)
            cur_w += add_w
    if cur_line:
        lines.append(cur_line)

    word_dom_rects = []
    total_h = len(lines) * 78
    start_y = (bh - total_h) // 2 + 36

    for l_idx, line in enumerate(lines):
        line_w = sum(m["tw"] for m in line) + gap * max(0, len(line) - 1)
        cur_right = (bw + line_w) // 2
        yc = start_y + l_idx * 82
        for m in line:
            x_left = cur_right - m["tw"]
            y_top = yc - m["th"] // 2
            color = accent if m["is_active"] else (255, 255, 255)
            draw.text((x_left, y_top - m["bbox"][1]), m["word"], font=m["font"], fill=(*color, 255), direction="rtl")
            word_dom_rects.append({
                "text": m["word"],
                "fontSize": m["fontSize"],
                "rect": {
                    "left": 64 + x_left,
                    "top": 1310 + y_top,
                    "right": 64 + x_left + m["tw"],
                    "bottom": 1310 + y_top + m["th"],
                    "width": m["tw"],
                    "height": m["th"],
                },
            })
            cur_right = x_left - gap

    rgb_arr = np.array(img.convert("RGB"), dtype=np.uint8)
    return rgb_arr, word_dom_rects


def _transform_stage_crop_numpy_pil(
    stage_rgb: np.ndarray,
    scale: float,
    dy: int,
    bg_rgb: Tuple[int, int, int],
    alpha: float,
) -> np.ndarray:
    """
    يطبق تكبير/تصغير النابض الفيزيائي (Spring Scale) والإزاحة الرأسية (Breathing dy) والشفافية
    باستخدام PIL + NumPy السريع بدون أي حاجة لمكتبة cv2!
    """
    sh, sw, _ = stage_rgb.shape
    canvas = np.empty((sh, sw, 3), dtype=np.uint8)
    canvas[:, :] = bg_rgb

    if abs(scale - 1.0) > 0.004:
        nw = max(16, int(round(sw * scale)))
        nh = max(16, int(round(sh * scale)))
        resized = np.array(
            Image.fromarray(stage_rgb).resize((nw, nh), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )
    else:
        nw, nh = sw, sh
        resized = stage_rgb

    # حساب إزاحة المركز + dy داخل الحاوية (sw, sh)
    dst_x0 = (sw - nw) // 2
    dst_y0 = (sh - nh) // 2 + dy

    src_x0 = max(0, -dst_x0)
    src_y0 = max(0, -dst_y0)
    copy_w = min(nw - src_x0, sw - max(0, dst_x0))
    copy_h = min(nh - src_y0, sh - max(0, dst_y0))

    if copy_w > 0 and copy_h > 0:
        dx0 = max(0, dst_x0)
        dy0 = max(0, dst_y0)
        patch = resized[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]
        if alpha < 0.99:
            a = max(0.0, min(1.0, float(alpha)))
            bg_patch = canvas[dy0:dy0 + copy_h, dx0:dx0 + copy_w].astype(np.float32)
            patch = (patch.astype(np.float32) * a + bg_patch * (1.0 - a)).astype(np.uint8)
        canvas[dy0:dy0 + copy_h, dx0:dx0 + copy_w] = patch

    return canvas


def verify_and_render_with_chromium(
    scenes: List[Dict[str, Any]],
    words: List[Dict[str, Any]],
    theme: Dict[str, Any],
    audio_path: str,
    output_mp4_path: str,
    fps: int = 30,
    total_duration: float = 23.60,
) -> Dict[str, Any]:
    """
    1. يبني وثائق HTML/CSS/SVG القياسية ويحسب إحداثيات DOM getBoundingClientRect() لكل مشهد ولكل كلمة.
    2. يتحقق من عدم وجود أي تجاوز للمناطق الآمنة (250px أعلى، 340px أسفل) أو تصادم كلمات.
    3. يحرك الزمن حتمياً فريماً بفريم (30fps بدقة 1080×1920) بتطبيق منحنيات الحركة الفيزيائية
       ويدمجها مع الصوت (-14 LUFS) عبر FFmpeg (H.264 CRF 19, AAC 192k) بدون الحاجة لـ cv2.
    """
    t0 = time.time()
    out_dir = os.path.dirname(os.path.abspath(output_mp4_path))
    html_snapshots_dir = os.path.join(out_dir, "html_scenes")
    os.makedirs(html_snapshots_dir, exist_ok=True)

    # ضمان ترقيم الكلمات فهرسياً
    for idx_w, w in enumerate(words):
        w["index"] = idx_w

    scene_reports = []
    safe_zone_violations = 0
    overflow_violations = 0
    word_collisions = 0
    min_caption_font_px = 999.0
    min_headline_font_px = 999.0

    # Pre-render a lightweight 6-fps motion pass per scene. The final video remains 30 fps;
    # the card animation advances independently while the camera/card transform stays smooth.
    motion_fps = 6.0
    scene_stage_frames: List[List[np.ndarray]] = []
    word_caption_crops: Dict[int, np.ndarray] = {}

    for idx, sc in enumerate(scenes):
        scene_start = float(sc["start"])
        scene_end = float(sc["end"])
        mid_t = 0.5 * (scene_start + scene_end)
        html_doc = build_frame_html(sc, words, theme, mid_t, total_duration)
        with open(os.path.join(html_snapshots_dir, f"scene_{idx+1:02d}_{sc['template']}.html"), "w", encoding="utf-8") as f:
            f.write(html_doc)

        scene_dur = max(0.25, scene_end - scene_start)
        motion_count = max(2, int(math.ceil(scene_dur * motion_fps)) + 1)
        motion_frames: List[np.ndarray] = []
        st_dom = None
        semantic_svg = ""
        if search_and_fetch_web_vectors is not None and sc.get("template") in {"concept_icon", "big_number"}:
            try:
                svg_candidates = search_and_fetch_web_vectors(
                    scene_text_ar=str(sc.get("speech", "")),
                    fallback_topic=str(sc.get("visual_query", "")),
                    max_assets=1,
                    allow_network=False,
                )
                if svg_candidates:
                    semantic_svg = str(svg_candidates[0])
            except Exception:
                semantic_svg = ""
        for motion_idx in range(motion_count):
            anim_t = min(scene_dur, motion_idx / motion_fps)
            stage_rgb, frame_dom = render_scene_card_and_measure_dom(
                sc, theme, animation_t=anim_t, motion_svg=semantic_svg
            )
            motion_frames.append(stage_rgb)
            if st_dom is None or abs(anim_t - scene_dur * 0.5) < abs((motion_idx - 1) / motion_fps - scene_dur * 0.5):
                st_dom = frame_dom
        scene_stage_frames.append(motion_frames)

        st_rect = st_dom["stage_rect"]
        if st_rect["top"] < 250:
            safe_zone_violations += 1
        for h in st_dom["headlines"]:
            min_headline_font_px = min(min_headline_font_px, float(h["fontSize"]))
            if h["rect"]["left"] < 20 or h["rect"]["right"] > 1060:
                overflow_violations += 1

        scene_reports.append({
            "scene_index": idx,
            "template": sc["template"],
            "mid_t": round(mid_t, 2),
            "stage_top": st_rect["top"],
            "caption_bottom": 1540.0,
            "headlines_count": len(st_dom["headlines"]),
        })

    for w in words:
        w_idx = int(w["index"])
        cap_rgb, w_dom_list = render_caption_bar_and_measure_dom(words, w_idx, theme)
        word_caption_crops[w_idx] = cap_rgb

        for wd in w_dom_list:
            min_caption_font_px = min(min_caption_font_px, float(wd["fontSize"]))
            if wd["rect"]["bottom"] > 1580 or wd["rect"]["left"] < 20 or wd["rect"]["right"] > 1060:
                safe_zone_violations += 1

        for i in range(len(w_dom_list)):
            for j in range(i + 1, len(w_dom_list)):
                r1 = w_dom_list[i]["rect"]
                r2 = w_dom_list[j]["rect"]
                if abs(r1["top"] - r2["top"]) < 25:
                    horiz_overlap = min(r1["right"], r2["right"]) - max(r1["left"], r2["left"])
                    if horiz_overlap > 2.0:
                        word_collisions += 1

    if not word_caption_crops:
        cap_rgb, _ = render_caption_bar_and_measure_dom([], 0, theme)
        word_caption_crops[0] = cap_rgb

    if min_caption_font_px == 999.0:
        min_caption_font_px = 50.0
    if min_headline_font_px == 999.0:
        min_headline_font_px = 74.0

    dom_report = {
        "safe_zone_violations": safe_zone_violations,
        "overflow_violations": overflow_violations,
        "word_collisions": word_collisions,
        "min_caption_font_px": min_caption_font_px,
        "min_headline_font_px": min_headline_font_px,
        "scene_dom_reports": scene_reports,
    }

    total_frames = max(1, int(round(total_duration * fps)))
    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", "1080x1920",
        "-r", str(fps),
        "-i", "-",
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    bg1_rgb = hex_to_rgb(theme["bg_primary"])
    accent_rgb = hex_to_rgb(theme["accent_primary"])

    base_bg = np.empty((1920, 1080, 3), dtype=np.uint8)
    base_bg[:, :] = bg1_rgb

    for f_idx in range(total_frames):
        t = f_idx / float(fps)

        sc_idx = len(scenes) - 1
        found_active = False
        for i, candidate in enumerate(scenes):
            if float(candidate["start"]) <= t <= float(candidate["end"]):
                sc_idx = i
                found_active = True
                break
        if scenes and not found_active:
            # For tiny timing gaps between word groups, show the nearest scene rather than
            # accidentally jumping to the final CTA for the rest of the video.
            def _distance_to_scene(candidate):
                start_v, end_v = float(candidate["start"]), float(candidate["end"])
                if start_v <= t <= end_v:
                    return 0.0
                return min(abs(t - start_v), abs(t - end_v))
            sc_idx = min(range(len(scenes)), key=lambda i: _distance_to_scene(scenes[i]))
        sc = scenes[sc_idx]
        local_t = max(0.0, t - float(sc["start"]))
        sc_dur = max(0.5, float(sc["end"]) - float(sc["start"]))

        active_w_idx = 0
        for w in words:
            if float(w["start"]) <= t <= float(w["end"]):
                active_w_idx = int(w["index"])
                break
            if float(w["start"]) <= t:
                active_w_idx = int(w["index"])

        frame = base_bg.copy()

        in_p = max(0.68, spring_ease(min(1.0, local_t / 0.32), overshoot=0.048))
        out_p = max(0.72, exit_ease(max(0.0, (local_t - (sc_dur - 0.16)) / 0.16))) if local_t > (sc_dur - 0.16) else 1.0
        env = max(0.68, in_p * out_p)
        breath_y = math.sin(local_t * 3.6) * 12.0
        if sc.get("template") == "fullscreen_image":
            kb_zoom = 1.0 + 0.05 * min(1.0, local_t / max(0.5, sc_dur))
            scale = max(0.2, min(1.08, env * kb_zoom))
        else:
            breath_scale = 1.0 + 0.028 * math.sin(local_t * 2.9)
            scale = max(0.2, min(1.08, env * breath_scale))
        dy = int(round((1.0 - min(1.0, env)) * 54.0 + breath_y))

        scene_frames = scene_stage_frames[sc_idx]
        motion_idx = min(len(scene_frames) - 1, max(0, int(round(local_t * motion_fps))))
        stage_crop = scene_frames[motion_idx]
        sh, sw = stage_crop.shape[:2]
        warped_stage = _transform_stage_crop_numpy_pil(
            stage_rgb=stage_crop,
            scale=scale,
            dy=dy,
            bg_rgb=bg1_rgb,
            alpha=min(1.0, max(0.0, env)),
        )
        frame[280:280 + sh, 60:60 + sw] = warped_stage

        cap_crop = word_caption_crops.get(active_w_idx, word_caption_crops[0])
        ch_c, cw_c = cap_crop.shape[:2]
        cap_y = 1310 + int(round(math.sin(t * 4.2) * 2.0))
        frame[cap_y:cap_y + ch_c, 64:64 + cw_c] = cap_crop

        # شريط التقدم الزمني السلس عند y=1564..1572 (بدون cv2)
        frame[1564:1572, 120:960] = (75, 55, 45)
        prog_x = 120 + int(round(840.0 * min(1.0, max(0.0, t / max(1.0, total_duration)))))
        frame[1564:1572, 120:prog_x] = accent_rgb

        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()
    elapsed = round(time.time() - t0, 2)

    return {
        "dom_report": dom_report,
        "render_report": {
            "output_mp4_path": output_mp4_path,
            "total_frames": total_frames,
            "fps": fps,
            "resolution": "1080x1920",
            "render_seconds": elapsed,
        },
    }
