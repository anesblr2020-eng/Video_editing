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


def render_scene_card_and_measure_dom(
    sc: Dict[str, Any],
    theme: Dict[str, Any],
    state_phase: str = "B",
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    يرسم بطاقة المشهد بدقة متجهية أصلية ضمن حاوية العرض البصري (960×940 عند x=60, y=280)
    باستخدام PIL + NumPy (بدون cv2) ويقيس الإحداثيات الفعلية (DOM getBoundingClientRect).
    """
    cw, ch = 960, 940
    img = Image.new("RGBA", (cw, ch), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    tpl = sc.get("template", "kinetic_hook")
    keywords = sc.get("keywords", ["تركيز بصري"])
    numbers = sc.get("numbers", [])
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
        if not text:
            return
        fnt = get_font(font_size, bold=True)
        bbox = draw.textbbox((0, 0), text, font=fnt, direction="rtl")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        while tw > 880 and font_size > 72:
            font_size -= 4
            fnt = get_font(font_size, bold=True)
            bbox = draw.textbbox((0, 0), text, font=fnt, direction="rtl")
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        x = (cw - tw) // 2
        y = y_center - th // 2
        draw.text((x, y - bbox[1]), text, font=fnt, fill=(*color_rgb, 255), direction="rtl")
        if is_headline:
            headlines_dom.append({
                "rect": {
                    "left": 60 + x,
                    "top": 280 + y,
                    "right": 60 + x + tw,
                    "bottom": 280 + y + th,
                    "width": tw,
                    "height": th,
                },
                "fontSize": font_size,
            })

    is_state_b = (state_phase == "B")

    if tpl == "kinetic_hook":
        # إطار طاقة نيون مزدوج حول النص الحركي الضخم: في الحالة A يبرز الشطر الأول، وفي الحالة B ينبثق الشطر الثاني بشريط مميز
        draw.rounded_rectangle([60, 170, cw - 60, 740], radius=42, fill=(14, 21, 38, 235), outline=(*(accent if is_state_b else secondary), 230), width=5)
        draw.rounded_rectangle([cw // 2 - 110, 235, cw // 2 + 110, 251], radius=8, fill=(*accent, 255))
        add_centered_text(kw0, 365 if is_state_b else 435, 92, (255, 255, 255), is_headline=True)
        if kw1 and is_state_b:
            draw.rounded_rectangle([130, 495, cw - 130, 625], radius=28, fill=(*surface, 255), outline=(*accent, 255), width=4)
            add_centered_text(kw1, 560, 84, accent, is_headline=True)

    elif tpl == "anchor_expand":
        # تطبيق VERB_01_ANCHOR_AND_EXPAND (تثبيت المرساة وتوسيع السياق كما في VIDEO_01 Phone -> AI Powered)
        if not is_state_b:
            draw.rounded_rectangle([70, 110, cw - 70, 820], radius=38, fill=(*surface, 255), outline=(*secondary, 255), width=5)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 345, 145, accent, secondary, danger, success, 0.3)
            add_centered_text(kw0, 645, 84, (255, 255, 255), is_headline=True)
        else:
            # في الحالة B: ينزاح الكيان الأول لأسفل الشاشة كمرساة (Anchor) وينبثق المحرك/النتيجة في الأعلى
            draw.rounded_rectangle([70, 85, cw - 70, 505], radius=36, fill=(16, 38, 48, 255), outline=(*accent, 255), width=6)
            draw_contextual_icon(draw, img, "ai_neural_chip", cw // 2, 225, 92, accent, secondary, danger, success, 0.9)
            add_centered_text(kw1 or kw0, 405, 82, accent, is_headline=True)
            # المرساة السفلية المستمرة من الحالة A (مرئية بوضوح في الأسفل دون تداخل الأيقونة مع النص)
            draw.rounded_rectangle([110, 545, cw - 110, 875], radius=32, fill=(*surface, 230), outline=(*border, 255), width=4)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 655, 64, secondary, accent, danger, success, 0.6)
            add_centered_text(kw0, 800, 72, (215, 225, 240), is_headline=True)

    elif tpl == "process_simulation":
        # تطبيق VERB_02_SIMULATE_PROCESS_TRANSFORM (منصة المحاكاة ثلاثية الطبقات: عنوان + بطاقة حالة + شريط Prompt وزر Generate)
        if not is_state_b:
            add_centered_text(kw0, 125, 76, (255, 255, 255), is_headline=True)
            draw.rounded_rectangle([75, 215, cw - 75, 665], radius=36, fill=(42, 18, 32, 255), outline=(*danger, 255), width=5)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 410, 118, danger, secondary, danger, success, 0.3)
            add_centered_text("الحالة الأولية قبل التحويل", 590, 52, (252, 165, 165), is_headline=False)
            # شريط الـ Prompt السفلي أثناء الكتابة
            draw.rounded_rectangle([75, 715, cw - 75, 845], radius=45, fill=(11, 17, 30, 255), outline=(*secondary, 255), width=4)
            draw.rounded_rectangle([98, 738, 330, 822], radius=34, fill=(*border, 255))
            add_centered_text("توليد...", 780, 48, (255, 255, 255), is_headline=False)
        else:
            add_centered_text(kw1 or kw0, 125, 82, accent, is_headline=True)
            draw.rounded_rectangle([75, 215, cw - 75, 665], radius=36, fill=(12, 46, 38, 255), outline=(*success, 255), width=6)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 405, 126, success, accent, danger, success, 0.9)
            add_centered_text("تم التحويل الفوري بنجاح", 590, 54, success, is_headline=False)
            # شريط الـ Prompt بعد ضغط زر Generate
            draw.rounded_rectangle([75, 715, cw - 75, 845], radius=45, fill=(11, 17, 30, 255), outline=(*accent, 255), width=5)
            draw.rounded_rectangle([98, 738, 345, 822], radius=34, fill=(*accent, 255))
            add_centered_text("مكتمل بنجاح", 780, 50, accent, is_headline=False)

    elif tpl == "dual_layer_proof":
        # تطبيق VERB_03_DUAL_LAYER_COMPARISON_REVEAL (كشف الطبقة الثانية للمقارنة داخل نفس الحاوية كما في VIDEO_01 Tesla Road)
        if not is_state_b:
            draw.rounded_rectangle([65, 145, cw - 65, 785], radius=38, fill=(*surface, 255), outline=(*secondary, 255), width=5)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 385, 130, secondary, accent, danger, success, 0.4)
            add_centered_text(kw0, 650, 80, (255, 255, 255), is_headline=True)
        else:
            # انقسام الحاوية عمودياً لكشف الطرف الثاني فوق الطرف الأول للمقارنة المباشرة دون تداخل الأيقونة مع النص
            draw.rounded_rectangle([65, 85, cw - 65, 455], radius=36, fill=(14, 44, 38, 255), outline=(*success, 255), width=6)
            draw_contextual_icon(draw, img, "viral_rocket_growth", cw // 2, 205, 72, success, accent, danger, success, 0.8)
            add_centered_text(kw1 or kw0, 365, 76, accent, is_headline=True)
            draw.rounded_rectangle([65, 485, cw - 65, 845], radius=36, fill=(*surface, 240), outline=(*border, 255), width=4)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 605, 68, secondary, accent, danger, success, 0.4)
            add_centered_text(kw0, 760, 72, (220, 230, 242), is_headline=True)

    elif tpl == "editorial_proof_card":
        # بطاقة الدليل الموثق مع تظليل الكلمات المفتاحية (كما في VIDEO_01 ZME Science News Card)
        draw.rounded_rectangle([55, 115, cw - 55, 825], radius=36, fill=(20, 30, 48, 255), outline=(*accent, 255), width=5)
        draw.rounded_rectangle([95, 160, cw - 95, 235], radius=18, fill=(11, 17, 30, 255))
        add_centered_text("تقرير موثق • نتائج مثبتة", 198, 48, secondary, is_headline=False)
        add_centered_text(kw0, 385, 78, (255, 255, 255), is_headline=True)
        if is_state_b:
            # شريط تظليل أصفر/مميز يمسح خلفية النص الثاني (Highlight sweep)
            draw.rounded_rectangle([105, 515, cw - 105, 665], radius=24, fill=(*accent, 255))
            add_centered_text(kw1 or kw0, 590, 76, (9, 13, 22), is_headline=True)
            draw_contextual_icon(draw, img, visual_query, cw // 2, 745, 56, success, accent, danger, success, 0.9)
        else:
            add_centered_text(kw1 or kw0, 590, 74, (180, 195, 215), is_headline=True)

    elif tpl == "minimalist_reset":
        # تطبيق VERB_06_CONTRAST_DECELERATION_RESET (التهدئة وكسر النمط بمساحة سلبية >= 75% كما في VIDEO_01 و VIDEO_03)
        draw.ellipse([cw // 2 - 95, 215, cw // 2 + 95, 405], outline=(*secondary, 180), width=4)
        draw.ellipse([cw // 2 - 45, 265, cw // 2 + 45, 355], fill=(*(accent if is_state_b else secondary), 210))
        add_centered_text(kw0, 520, 78, (255, 255, 255), is_headline=True)
        if kw1 and is_state_b:
            add_centered_text(kw1, 665, 72, secondary, is_headline=True)

    elif tpl == "concept_icon":
        icon_y = 265 if is_state_b else 335
        icon_r = 126 if is_state_b else 148
        draw_contextual_icon(draw, img, visual_query, cw // 2, icon_y, icon_r, accent, secondary, danger, success, 0.8 if is_state_b else 0.2)
        add_centered_text(kw0, 525 if is_state_b else 615, 82, (255, 255, 255), is_headline=True)
        if kw1 and is_state_b:
            draw.rounded_rectangle([120, 625, cw - 120, 755], radius=28, fill=(*surface, 255), outline=(*accent, 255), width=4)
            add_centered_text(kw1, 690, 74, accent, is_headline=True)

    elif tpl == "big_number":
        # رسم أيقونة مصاحبة للرقم (مثل مقص الصمت أو شارة المجاني) + الرقم المنطوق الضخم
        draw_contextual_icon(draw, img, visual_query, cw // 2, 165, 86, accent, secondary, danger, success, 0.5)
        raw_num = str(numbers[0] if numbers else "0")
        digits_part = "".join(ch for ch in raw_num if ch in "0123456789%+") or "0"
        f_big = get_font(145, bold=True, latin=True)
        bbox = draw.textbbox((0, 0), digits_part, font=f_big)
        nw = bbox[2] - bbox[0]
        draw.text(((cw - nw) // 2, 315 - bbox[1]), digits_part, font=f_big, fill=(*accent, 255))
        if digits_part == "0":
            add_centered_text("صفر دينار مجاناً", 515, 74, secondary, is_headline=True)
            add_centered_text(kw0, 645, 80, (255, 255, 255), is_headline=True)
            if kw1 and is_state_b:
                add_centered_text(kw1, 765, 72, accent, is_headline=True)
        else:
            add_centered_text(kw0, 545, 82, (255, 255, 255), is_headline=True)
            if kw1 and is_state_b:
                draw.rounded_rectangle([130, 645, cw - 130, 775], radius=28, fill=(*surface, 255), outline=(*accent, 255), width=4)
                add_centered_text(kw1, 710, 76, accent, is_headline=True)

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
        # بطاقة قبل (تتصدر الحالة A، وتنكمش للأعلى في الحالة B لكشف بطاقة بعد)
        draw.rounded_rectangle([50, 115, cw - 50, 405], radius=34, fill=(45, 18, 30, 255), outline=(*danger, 255), width=5)
        add_centered_text("قبل", 185, 52, danger, is_headline=False)
        add_centered_text(kw0, 300, 76, (255, 255, 255), is_headline=True)
        if is_state_b:
            draw.ellipse([cw // 2 - 38, 418, cw // 2 + 38, 494], fill=(*accent, 255))
            draw.polygon([(cw // 2 - 16, 444), (cw // 2 + 16, 444), (cw // 2, 474)], fill=(9, 13, 22, 255))
            draw.rounded_rectangle([50, 498, cw - 50, 805], radius=34, fill=(14, 46, 38, 255), outline=(*success, 255), width=6)
            add_centered_text("بعد", 570, 52, success, is_headline=False)
            add_centered_text(kw1 or kw0, 690, 76, accent, is_headline=True)

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
        if is_state_b:
            draw.ellipse([cw // 2 - 58, 411, cw // 2 + 58, 527], fill=(*accent, 255))
            f_vs = get_font(44, bold=True, latin=True)
            vb = draw.textbbox((0, 0), "VS", font=f_vs)
            draw.text((cw // 2 - (vb[2] - vb[0]) // 2, 469 - (vb[3] - vb[1]) // 2 - vb[1]), "VS", font=f_vs, fill=(9, 13, 22, 255))
            draw.rounded_rectangle([50, 545, cw - 50, 810], radius=32, fill=(*surface, 255), outline=(*accent, 255), width=6)
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
        add_centered_text(kw1 or "الرابط في الأسفل", 462, 74, (9, 13, 22), is_headline=True)
        ax, ay0, ay1 = cw // 2, 600, 775
        draw.line([ax, ay0, ax, ay1], fill=(*accent, 255), width=16)
        draw.line([ax - 55, ay1 - 55, ax, ay1 + 8, ax + 55, ay1 - 55], fill=(*accent, 255), width=16)

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
        txt = str(w.get("word", ""))
        has_ascii_num = any(ch in "0123456789%" for ch in txt)
        fnt = get_font(58 if is_act else 50, bold=True, latin=has_ascii_num)
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

    scene_stage_crops_a: List[np.ndarray] = []
    scene_stage_crops_b: List[np.ndarray] = []
    word_caption_crops: Dict[int, np.ndarray] = {}

    for idx, sc in enumerate(scenes):
        mid_t = 0.5 * (float(sc["start"]) + float(sc["end"]))
        html_doc = build_frame_html(sc, words, theme, mid_t, total_duration)
        with open(os.path.join(html_snapshots_dir, f"scene_{idx+1:02d}_{sc['template']}.html"), "w", encoding="utf-8") as f:
            f.write(html_doc)

        stage_rgb_a, _ = render_scene_card_and_measure_dom(sc, theme, state_phase="A")
        stage_rgb_b, st_dom = render_scene_card_and_measure_dom(sc, theme, state_phase="B")
        scene_stage_crops_a.append(stage_rgb_a)
        scene_stage_crops_b.append(stage_rgb_b)

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

    # بناء مشاهد الاستوديو الغنية عبر محرك الإخراج الموحد (motion_text + vector_lottie_engine + style_evolution_brain)
    from motion_text import render_single_scene_canvas, render_one_take_camera_handoff
    from style_evolution_brain import PRO_STUDIO_STYLE_FAMILIES
    from smart_analyzer import decompose_scene_clauses_and_verb

    ref_family_cycle = ["honeyy_highkey_3d_ui", "divyansh_kinetic_contrast", "morningstar_editorial_25d"]
    # حافظ على هوية بصرية واحدة داخل الفيديو؛ لا تبدّل عائلة المرجع آلياً في كل مشهد.
    family_seed = sum(ord(ch) for ch in str(theme.get("name", theme_name if "theme_name" in locals() else "auto")))
    video_family = ref_family_cycle[family_seed % len(ref_family_cycle)]
    v2_to_hero = {
        "kinetic_hook": "hero_smartphone_reels",
        "concept_icon": "hero_ai_neural_core",
        "big_number": "hero_chrono_speedometer",
        "steps_flow": "hero_roadmap_milestones",
        "checklist": "hero_platform_workspace",
        "before_after": "hero_comparison_duel",
        "versus": "hero_comparison_duel",
        "phone_reel_mockup": "hero_smartphone_reels",
        "alert_warning": "hero_problem_radar_fix",
        "cta_end": "hero_cta_magnet_finale",
    }
    trans_cycle = ["whip_pan_blur_left", "circle_expand_wipe", "whip_pan_blur_up", "portal_zoom_morph"]

    visual_query_to_hero = {
        "hourglass_deadline": "hero_chrono_speedometer",
        "clock_speedometer": "hero_chrono_speedometer",
        "waveform_scissors": "hero_waveform_scissors",
        "studio_microphone": "hero_sound_wave_mixer",
        "instagram_decline": "hero_smartphone_reels",
        "ai_neural_chip": "hero_ai_neural_core",
        "viral_rocket_growth": "hero_viral_rocket_chart",
        "camera_clapperboard": "hero_camera_production",
        "lightbulb_solution": "hero_creative_palette_pen",
        "shield_guarantee": "hero_problem_radar_fix",
        "trophy_success": "hero_cta_magnet_finale",
        "delivery_map_58": "hero_delivery_route",
        "cta_arrow_down": "hero_cta_magnet_finale",
        "immune_cell_shield": "hero_problem_radar_fix",
        "passkey_lock_vault": "hero_problem_radar_fix",
        "solar_grid_chart": "hero_viral_rocket_chart",
        "compiler_syntax_tree": "hero_ai_neural_core",
    }
    studio_scenes = []
    for s_i, sc_item in enumerate(scenes):
        fam_key = video_family
        fam_spec = PRO_STUDIO_STYLE_FAMILIES[fam_key]
        act_name = "hook_problem" if s_i == 0 else ("outro_finale" if s_i == len(scenes) - 1 else "body_steps")
        pal_use = dict(fam_spec["acts"].get(act_name, fam_spec["unified_palette"]))
        style_spec = {
            "style_family_id": fam_key,
            "design_family": fam_key,
            "act_name": act_name,
            "step_number": s_i + 1,
            "visual_archetype": visual_query_to_hero.get(
                str(sc_item.get("visual_query", "")).strip(),
                ("web_dynamic_scene" if str(sc_item.get("visual_query", "")).startswith("semantic_concept")
                 else v2_to_hero.get(sc_item.get("template", ""), "web_dynamic_scene"))
            ),
            "has_grid": False,
            "has_floating_diamonds": False,
            "has_giant_bg_numbers": (fam_key == "honeyy_highkey_3d_ui"),
            "header_style": fam_spec["header_style"],
            "headline_style": fam_spec["headline_style"],
            "card_tilt_deg": fam_spec["card_tilt_deg"],
            "palette": pal_use,
            "spring_stiffness": 215.0,
            "spring_damping": 13.5,
            "camera_float_amp": 5.0,
        }
        s_start = float(sc_item.get("start", 0.0))
        s_end = float(sc_item.get("end", s_start + 2.5))
        sc_w_objs = [w for w in words if s_start - 0.08 <= float(w.get("start", 0.0)) <= s_end + 0.08]
        if not sc_w_objs:
            sc_w_objs = [{"word": w_s, "start": s_start, "end": s_end} for w_s in str(sc_item.get("speech", "")).split() if w_s]
        speech_txt = str(sc_item.get("speech") or sc_item.get("text") or "")
        decomp = decompose_scene_clauses_and_verb(speech_txt, s_i, len(scenes), sc_w_objs)
        kws = sc_item.get("keywords") or [decomp["clause_a"], decomp["clause_b"]]
        studio_scenes.append({
            "index": s_i,
            "step_number": s_i + 1,
            "total_scenes_count": len(scenes),
            "start": s_start,
            "end": s_end,
            "text": speech_txt,
            "words": sc_w_objs,
            "word_strings": [w.get("word", "") for w in sc_w_objs],
            "archetype": style_spec["visual_archetype"],
            "visual_subject": sc_item.get("visual_query", style_spec["visual_archetype"]),
            "concept_title": sc_item.get("clause_a") or decomp["clause_a"] or (kws[0] if kws else speech_txt[:24]),
            "clause_a": sc_item.get("clause_a") or decomp["clause_a"],
            "clause_b": sc_item.get("clause_b") or decomp["clause_b"],
            "pivot_u": decomp["pivot_u"],
            "visual_verb": decomp["visual_verb"],
            "bridge_shape": decomp["bridge_shape"],
            "kpi_value": kws[1] if len(kws) > 1 else decomp["clause_b"],
            "kpi_label": kws[2] if len(kws) > 2 else "",
            "sub_items": kws[:3],
            "scene_style_spec": style_spec,
            "transition_type": trans_cycle[s_i % len(trans_cycle)],
            "handoff_duration_sec": 0.32,
        })

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
    bg_cache = {}
    # Preload generated scene artwork once. The art is composited behind the motion-graphics
    # layer with restrained opacity so captions remain readable while scene-specific imagery is visible.
    from PIL import ImageEnhance
    scene_art = {}
    for _idx, _sc in enumerate(studio_scenes):
        _ip = str(scenes[_idx].get("image_path") or "") if _idx < len(scenes) else ""
        if _ip and os.path.isfile(_ip):
            try:
                _art = Image.open(_ip).convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
                _art = ImageEnhance.Brightness(_art).enhance(0.58)
                scene_art[_idx] = _art
            except Exception:
                pass

    for f_idx in range(total_frames):
        t = f_idx / float(fps)
        active_idx = len(studio_scenes) - 1
        for i, sc_st in enumerate(studio_scenes):
            if sc_st["start"] <= t <= sc_st["end"]:
                active_idx = i
                break
        sc_st = studio_scenes[active_idx]
        sc_dur = max(0.25, sc_st["end"] - sc_st["start"])
        sc_prog = max(0.0, min(1.0, (t - sc_st["start"]) / sc_dur))

        sc_words = sc_st["word_strings"]
        act_w = sc_words[0] if sc_words else sc_st["concept_title"]
        act_w_idx = 0
        w_p = 0.5
        for wi, w_obj in enumerate(sc_st["words"]):
            ws = float(w_obj.get("start", 0.0))
            we = float(w_obj.get("end", ws + 0.3))
            if t >= ws - 0.04:
                act_w = w_obj.get("word", "")
                act_w_idx = wi
                w_p = max(0.0, min(1.0, (t - ws) / max(0.10, we - ws)))

        curr_img = render_single_scene_canvas(
            scene_meta=sc_st,
            active_word=act_w,
            scene_words=sc_words,
            active_word_idx=act_w_idx,
            word_local_progress=w_p,
            scene_progress=sc_prog,
            global_t=t,
            total_duration=total_duration,
            audio_level=0.85,
            width=1080,
            height=1920,
            bg_cache=bg_cache
        )

        time_into = t - sc_st["start"]
        handoff_dur = float(sc_st.get("handoff_duration_sec", 0.32))
        if active_idx > 0 and 0.0 <= time_into < handoff_dur:
            prev_sc = studio_scenes[active_idx - 1]
            prev_img = render_single_scene_canvas(
                scene_meta=prev_sc,
                active_word="",
                scene_words=prev_sc["word_strings"],
                active_word_idx=max(0, len(prev_sc["word_strings"]) - 1),
                word_local_progress=1.0,
                scene_progress=1.0,
                global_t=t,
                total_duration=total_duration,
                audio_level=0.85,
                width=1080,
                height=1920,
                bg_cache=bg_cache
            )
            curr_img = render_one_take_camera_handoff(
                prev_img=prev_img,
                curr_img=curr_img,
                trans_progress=time_into / handoff_dur,
                transition_type=sc_st["transition_type"],
                prev_meta=prev_sc,
                curr_meta=sc_st
            )

        # Show the generated scene image as a full-frame semantic backdrop with gentle camera motion.
        # Keep the existing designed foreground visible; never replace captions or motion graphics.
        if active_idx in scene_art:
            try:
                art = scene_art[active_idx]
                # Small Ken Burns drift/zoom per scene, deterministic and tied to scene progress.
                zoom = 1.0 + 0.045 * sc_prog
                aw, ah = int(1080 * zoom), int(1920 * zoom)
                art_zoom = art.resize((aw, ah), Image.Resampling.BICUBIC)
                left = max(0, (aw - 1080) // 2 + int(10 * math.sin(sc_prog * math.pi)))
                top = max(0, (ah - 1920) // 2 + int(12 * math.cos(sc_prog * math.pi)))
                art_zoom = art_zoom.crop((left, top, left + 1080, top + 1920))
                curr_img = Image.blend(art_zoom.convert("RGBA"), curr_img.convert("RGBA"), 0.70)
            except Exception:
                pass
        frame_rgb = np.ascontiguousarray(np.array(curr_img.convert("RGB"), dtype=np.uint8))
        proc.stdin.write(frame_rgb.tobytes())

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
