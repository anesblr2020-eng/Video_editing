"""
motion_text.py - محرك الموشن جرافيك الكامل متعدد الأبعاد ومتعدد الأنماط المكانية (Multi-Layout Motion Engine)
=============================================================================================================
يدعم هذا المحرك تنفيذ أوامر "مخطط المخرج الشامل (Master Director Plan)" في كل لقطة:
1. full_screen: شاشة موشن جرافيك كاملة ومتحركة (B-roll Cutaway) مع انتقالات كاميرا سينمائية.
2. top_overlay: بطاقة موشن جرافيك ورسمة متحركة في النصف العلوي فوق المتحدث.
3. lower_third: شارة أو لافتة موشن جرافيك في الثلث السفلي (توصيل، ضمان، ميزات، أسعار).
4. speaker_clean: لقطة متحدث صافية مع زوم هادئ وكابشن كاريوكي فقط لراحة العين.
5. رسومات متحركة إطاراً بإطار (24 FPS) تتطابق 100% مع الكلمات المنطوقة وتوقيتها.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

def _safe_rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, *, corners=None):
    try:
        if isinstance(xy[0], (list, tuple)):
            (x0, y0), (x1, y1) = xy
        else:
            x0, y0, x1, y1 = xy
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        if x_max - x_min < 1:
            x_max = x_min + 1
        if y_max - y_min < 1:
            y_max = y_min + 1
        safe_r = max(0, min(int(radius), int((x_max - x_min) // 2), int((y_max - y_min) // 2)))
        return _orig_rounded_rect(self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners)
    except Exception:
        pass

PIL.ImageDraw.ImageDraw.rounded_rectangle = _safe_rounded_rectangle

import re
import math
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, features

from transcriber import transcribe_audio, transcribe_sentences, split_words_into_micro_scenes

try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. إعداد الخطوط العربية وتشكيل الحروف
# ==============================================================================
_FONT_DOWNLOAD_ATTEMPTED = False
_FONT_OBJECT_CACHE: Dict[Tuple[int, bool], ImageFont.FreeTypeFont] = {}
_HAS_RAQM = False
try:
    _HAS_RAQM = bool(features.check("raqm"))
except Exception:
    _HAS_RAQM = False


def shape_arabic_text(text: str) -> str:
    if not text:
        return ""
    if _HAS_RAQM:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def draw_arabic_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
    anchor: str = "mm",
    stroke_width: int = 0,
    stroke_fill: Optional[Tuple[int, int, int, int]] = None
):
    prepared = shape_arabic_text(text)
    kwargs = {"font": font, "fill": fill, "anchor": anchor}
    if stroke_width > 0 and stroke_fill is not None:
        kwargs["stroke_width"] = stroke_width
        kwargs["stroke_fill"] = stroke_fill

    if _HAS_RAQM:
        try:
            draw.text(xy, prepared, direction="rtl", **kwargs)
            return
        except Exception:
            pass

    try:
        draw.text(xy, prepared, **kwargs)
    except Exception:
        kwargs.pop("anchor", None)
        draw.text(xy, prepared, **kwargs)


def measure_arabic_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont
) -> Tuple[int, int]:
    prepared = shape_arabic_text(text)
    try:
        if _HAS_RAQM:
            bbox = draw.textbbox((0, 0), prepared, font=font, direction="rtl")
        else:
            bbox = draw.textbbox((0, 0), prepared, font=font)
        return max(12, int(bbox[2] - bbox[0])), max(12, int(bbox[3] - bbox[1]))
    except Exception:
        return max(20, len(text) * 18), 36


def get_arabic_font(font_size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    global _FONT_DOWNLOAD_ATTEMPTED
    cache_key = (int(font_size), bool(bold))
    if cache_key in _FONT_OBJECT_CACHE:
        return _FONT_OBJECT_CACHE[cache_key]

    fonts_dir = os.path.join(_CURRENT_DIR, "assets", "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    cairo_bold_path = os.path.join(fonts_dir, "Cairo-Bold.ttf")

    if not os.path.exists(cairo_bold_path) and not _FONT_DOWNLOAD_ATTEMPTED:
        _FONT_DOWNLOAD_ATTEMPTED = True
        font_urls = [
            "https://github.com/google/fonts/raw/main/ofl/cairo/static/Cairo-Bold.ttf",
            "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Bold.ttf"
        ]
        for url in font_urls:
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200 and len(resp.content) > 20000:
                    with open(cairo_bold_path, "wb") as f:
                        f.write(resp.content)
                    break
            except Exception:
                continue

    candidate_fonts = [
        cairo_bold_path,
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "/System/Library/Fonts/GeezaPro.ttc",
        "arial.ttf"
    ]

    for path in candidate_fonts:
        if path and os.path.exists(path):
            try:
                f_obj = ImageFont.truetype(path, int(font_size))
                _FONT_OBJECT_CACHE[cache_key] = f_obj
                return f_obj
            except Exception:
                continue

    f_def = ImageFont.load_default()
    _FONT_OBJECT_CACHE[cache_key] = f_def
    return f_def


# ==============================================================================
# 2. الثيمات اللونية المتعددة للمشاهد
# ==============================================================================
MOTION_THEMES = {
    "cyber_gold": {
        "top_bg": (9, 14, 30),
        "bottom_bg": (22, 28, 62),
        "glow": (56, 189, 248),
        "primary": (255, 220, 0),
        "secondary": (0, 245, 212),
        "accent": (99, 102, 241),
        "card_bg": (13, 20, 40, 225)
    },
    "emerald_tech": {
        "top_bg": (5, 24, 22),
        "bottom_bg": (12, 48, 44),
        "glow": (16, 185, 129),
        "primary": (52, 211, 153),
        "secondary": (251, 191, 36),
        "accent": (6, 182, 212),
        "card_bg": (7, 32, 28, 225)
    },
    "royal_purple": {
        "top_bg": (20, 10, 38),
        "bottom_bg": (46, 18, 76),
        "glow": (236, 72, 153),
        "primary": (255, 195, 0),
        "secondary": (255, 77, 141),
        "accent": (168, 85, 247),
        "card_bg": (28, 14, 52, 225)
    },
    "crimson_energy": {
        "top_bg": (28, 9, 16),
        "bottom_bg": (56, 16, 30),
        "glow": (249, 115, 22),
        "primary": (255, 230, 0),
        "secondary": (255, 115, 0),
        "accent": (239, 68, 68),
        "card_bg": (36, 12, 22, 225)
    },
    "ocean_neon": {
        "top_bg": (6, 18, 36),
        "bottom_bg": (14, 42, 74),
        "glow": (14, 165, 233),
        "primary": (56, 189, 248),
        "secondary": (250, 204, 21),
        "accent": (45, 212, 191),
        "card_bg": (10, 26, 48, 225)
    },
    "sunset_violet": {
        "top_bg": (24, 12, 32),
        "bottom_bg": (54, 22, 58),
        "glow": (244, 63, 94),
        "primary": (251, 146, 60),
        "secondary": (56, 189, 248),
        "accent": (232, 121, 249),
        "card_bg": (32, 14, 42, 225)
    }
}


# ==============================================================================
# 3. مصنف المشاهد الرسومية المخصص لكل لقطة (Micro-Scene Classifier)
# ==============================================================================
def classify_micro_scene_blueprint(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    prev_scene_type: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    t = scene_text.strip()
    t_low = t.lower()

    num_match = re.search(r"\b(\d+)\b", t)
    extracted_number = int(num_match.group(1)) if num_match else None

    chosen_type = None
    badge_label = "مشهد موشن جرافيك"

    if any(w in t_low for w in ["مونتاج", "منتاج", "تمنتج", "فيديوهات", "فيديو", "ايديت", "إيديتينج", "editing", "قص", "لقطات"]):
        if scene_index == total_scenes - 1 and any(w in t_low for w in ["اسم", "منصة", "إيديتينج", "editing"]):
            chosen_type = "brand_finale"
            badge_label = "منصة تحرير الفيديو الذكية"
        else:
            chosen_type = "video_montage_studio"
            badge_label = "أستوديو المونتاج الذكي"
    elif any(w in t_low for w in ["ذكاء", "اصطناعي", "استناعي", "أوتوماتيكي", "اوتوماتيكي", "تلقائي", "آلي", "خوارزمية"]):
        chosen_type = "ai_neural_brain"
        badge_label = "محرك الذكاء الاصطناعي"
    elif any(w in t_low for w in ["ريلز", "ريز", "تيك توك", "شورتس", "ترفع", "نشر", "سوشيال", "يوتيوب", "انستغرام"]):
        chosen_type = "reels_smartphone"
        badge_label = "نشر الريلز والمحتوى اليومي"
    elif any(w in t_low for w in ["أبني", "ابني", "منصة", "تعمل", "موقع", "تطبيق", "مشروع", "نظام", "برمجة"]):
        chosen_type = "platform_builder"
        badge_label = "بناء وتطوير المنصة"
    elif any(w in t_low for w in ["توصيل", "ولاية", "58", "باب الدار"]) or (any(w in t_low for w in ["شحن"]) and any(w in t_low for w in ["توصيل", "ولاية"])):
        chosen_type = "delivery_express"
        badge_label = "توصيل سريع 58 ولاية"
    elif any(w in t_low for w in ["شحن", "واط", "شارجي", "fast charge", "شحن فائق"]):
        chosen_type = "ecommerce_showcase"
        badge_label = "شحن فائق السرعة"
    elif any(w in t_low for w in ["سيبور", "ستاند", "حامل", "تيليفون"]) and any(w in t_low for w in ["تتفرج", "مشاهدة", "راحة"]):
        chosen_type = "reels_smartphone"
        badge_label = "حامل هاتف مدمج ومشاهدة مريحة"
    elif any(w in t_low for w in ["قماش", "يتقطع", "ضد القطع", "متانة", "جودة", "مضمونة"]):
        chosen_type = "ecommerce_showcase"
        badge_label = "متانة وجودة فائقة ضد القطع"
    elif any(w in t_low for w in ["منتج", "سلعة", "أصلي", "اطلب", "كليكي", "بايو", "تعليق"]) and scene_index >= total_scenes - 2:
        chosen_type = "ecommerce_showcase"
        badge_label = "اطلب الآن - متوفر بكمية محدودة"
    elif any(w in t_low for w in ["اصبر", "انتبه", "شوف"]) and scene_index == 0:
        chosen_type = "ecommerce_showcase"
        badge_label = "انتبه - منتج عملي واستثنائي"
    elif any(w in t_low for w in ["وقت", "ساعة", "ما عندها", "مشغولة", "تأخير", "ثواني"]):
        chosen_type = "time_warp_clock"
        badge_label = "توفير الوقت والسرعة"
    elif any(w in t_low for w in ["سعر", "سومة", "تخفيض", "عرض", "دراهم", "دينار", "بروموسيون"]):
        chosen_type = "growth_analytics"
        badge_label = "عرض وسعر استثنائي"
    elif extracted_number is not None and any(w in t_low for w in ["عمري", "عمره", "سنة", "سنين", "مئة", "ألف", "مليون"]):
        chosen_type = "age_number_counter"
        badge_label = f"محطة الإنجاز - {extracted_number}"
    elif any(w in t_low for w in ["أهلاً", "اهلا", "سلام", "أنا", "أنس", "اسمي", "مرحبا"]):
        chosen_type = "creator_profile"
        badge_label = "بطاقة تعريف المبدع"
    elif scene_index == total_scenes - 1:
        chosen_type = "brand_finale"
        badge_label = "الإطلاق الرسمي للمنصة"

    fallback_cycle = [
        ("creator_profile", "إضاءة تعريفية"),
        ("platform_builder", "هندسة وبناء النظام"),
        ("ai_neural_brain", "نواة الذكاء الاصطناعي"),
        ("video_montage_studio", "أتمتة شريط المونتاج"),
        ("growth_analytics", "أداء وإنتاجية عالية"),
        ("reels_smartphone", "محتوى ريلز تفاعلي"),
        ("brand_finale", "أستوديو الجيل الجديد")
    ]
    if not chosen_type or chosen_type == prev_scene_type:
        alt_type, alt_label = fallback_cycle[scene_index % len(fallback_cycle)]
        if alt_type == prev_scene_type:
            alt_type, alt_label = fallback_cycle[(scene_index + 1) % len(fallback_cycle)]
        chosen_type = alt_type
        if badge_label == "مشهد موشن جرافيك":
            badge_label = alt_label

    words = [w for w in re.findall(r"[\w\u0621-\u064A]+", t) if len(w) > 2]
    short_title = " ".join(words[:2]) if len(words) >= 2 else (words[0] if words else t[:16])

    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    return {
        "scene_type": chosen_type,
        "badge_label": badge_label,
        "short_title": short_title,
        "target_number": extracted_number if extracted_number is not None else 17,
        "theme_name": theme_keys[scene_index % len(theme_keys)],
        "transition_type": transitions[scene_index % len(transitions)]
    }


# ==============================================================================
# 4. رسام المشاهد الرسومية المتحركة إطاراً بإطار (24 FPS Frame Artists)
# ==============================================================================
def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def _ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * ((x - 1.0) ** 3) + c1 * ((x - 1.0) ** 2)


def draw_animated_scene_illustration(
    draw: ImageDraw.ImageDraw,
    scene_type: str,
    cx: int,
    cy: int,
    radius: int,
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any],
    target_number: int = 17,
    short_title: str = ""
):
    prim = (*theme["primary"], 255)
    sec = (*theme["secondary"], 255)
    acc = (*theme["accent"], 240)
    white = (255, 255, 255, 255)
    dark_panel = (12, 19, 38, 230)

    enter_scale = _ease_out_back(min(1.0, scene_progress * 2.8))
    r = int(radius * max(0.2, enter_scale))

    orbit_angle = global_t * 55.0
    draw.ellipse(
        [(cx - int(r * 1.05), cy - int(r * 1.05)), (cx + int(r * 1.05), cy + int(r * 1.05))],
        fill=(14, 22, 44, 255),
        outline=(*theme["secondary"], 90),
        width=2
    )
    draw.arc(
        [(cx - int(r * 1.14), cy - int(r * 1.14)), (cx + int(r * 1.14), cy + int(r * 1.14))],
        start=int(orbit_angle) % 360,
        end=(int(orbit_angle) + 110) % 360,
        fill=prim,
        width=5
    )
    draw.arc(
        [(cx - int(r * 1.14), cy - int(r * 1.14)), (cx + int(r * 1.14), cy + int(r * 1.14))],
        start=(int(orbit_angle) + 180) % 360,
        end=(int(orbit_angle) + 280) % 360,
        fill=sec,
        width=4
    )

    if scene_type == "creator_profile":
        card_w, card_h = int(r * 1.75), int(r * 1.35)
        x1, y1 = cx - card_w // 2, cy - card_h // 2
        x2, y2 = cx + card_w // 2, cy + card_h // 2

        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=28, fill=dark_panel, outline=prim, width=4)
        draw.rounded_rectangle([(x1 + 20, y1 + 18), (x2 - 20, y1 + 52)], radius=12, fill=(25, 38, 68, 220))
        for idx, dot_c in enumerate([(239, 68, 68, 255), (250, 204, 21, 255), (52, 211, 153, 255)]):
            dx = x1 + 42 + idx * 24
            draw.ellipse([(dx - 7, y1 + 35 - 7), (dx + 7, y1 + 35 + 7)], fill=dot_c)

        av_r = int(r * 0.36)
        av_y = cy - int(r * 0.06)
        pulse = int(8 * math.sin(global_t * 6.0))
        draw.ellipse([(cx - av_r - pulse, av_y - av_r - pulse), (cx + av_r + pulse, av_y + av_r + pulse)], outline=sec, width=3)
        draw.ellipse([(cx - av_r, av_y - av_r), (cx + av_r, av_y + av_r)], fill=(28, 45, 82, 255), outline=prim, width=5)
        head_r = int(av_r * 0.34)
        draw.ellipse([(cx - head_r, av_y - int(av_r * 0.45) - head_r), (cx + head_r, av_y - int(av_r * 0.45) + head_r)], fill=prim)
        draw.pieslice(
            [(cx - int(av_r * 0.62), av_y + int(av_r * 0.05)), (cx + int(av_r * 0.62), av_y + int(av_r * 0.95))],
            start=180, end=360, fill=sec
        )
        bx, by = cx + int(av_r * 0.72), av_y + int(av_r * 0.65)
        draw.ellipse([(bx - 22, by - 22), (bx + 22, by + 22)], fill=(16, 185, 129, 255), outline=white, width=3)
        draw.line([(bx - 10, by), (bx - 2, by + 9), (bx + 12, by - 8)], fill=white, width=4)

        bar_y = y2 - 44
        bar_w = int(card_w * 0.55 * min(1.0, scene_progress * 1.8))
        draw.rounded_rectangle([(cx - bar_w // 2, bar_y - 8), (cx + bar_w // 2, bar_y + 8)], radius=8, fill=prim)

    elif scene_type == "age_number_counter":
        count_progress = _ease_out_cubic(min(1.0, scene_progress * 1.6))
        current_val = max(1, int(round(target_number * count_progress)))

        gauge_r = int(r * 0.88)
        draw.ellipse([(cx - gauge_r, cy - gauge_r), (cx + gauge_r, cy + gauge_r)], fill=dark_panel, outline=(255, 255, 255, 50), width=4)
        sweep_deg = int(300 * count_progress)
        draw.arc(
            [(cx - gauge_r + 14, cy - gauge_r + 14), (cx + gauge_r - 14, cy + gauge_r - 14)],
            start=120, end=120 + sweep_deg,
            fill=prim, width=18
        )
        draw.arc(
            [(cx - gauge_r + 36, cy - gauge_r + 36), (cx + gauge_r - 36, cy + gauge_r - 36)],
            start=120, end=120 + int(sweep_deg * 0.85),
            fill=sec, width=8
        )

        num_font = get_arabic_font(int(r * 0.72), bold=True)
        draw_arabic_text(
            draw, (cx, cy - 10), str(current_val),
            font=num_font, fill=prim, stroke_width=4, stroke_fill=(0, 0, 0, 240)
        )
        for i in range(12):
            ang = math.radians(i * 30 + global_t * 40)
            x1 = cx + int((gauge_r + 12) * math.cos(ang))
            y1 = cy + int((gauge_r + 12) * math.sin(ang))
            x2 = cx + int((gauge_r + 32) * math.cos(ang))
            y2 = cy + int((gauge_r + 32) * math.sin(ang))
            draw.line([(x1, y1), (x2, y2)], fill=sec if i % 2 == 0 else prim, width=4)

    elif scene_type == "platform_builder":
        win_w, win_h = max(24, int(r * 1.80)), max(20, int(r * 1.35))
        wx1, wy1 = cx - win_w // 2, cy - win_h // 2
        wx2, wy2 = cx + win_w // 2, cy + win_h // 2
        draw.rounded_rectangle([(wx1, wy1), (wx2, wy2)], radius=max(4, int(r * 0.12)), fill=dark_panel, outline=sec, width=max(2, int(r * 0.03)))
        pad = max(4, int(r * 0.08))
        body_y1 = wy1 + max(8, int(win_h * 0.22))
        body_y2 = max(body_y1 + 4, wy2 - pad)
        sb_w = max(6, int((win_w - 3 * pad) * 0.28))
        draw.rounded_rectangle([(wx1 + pad, body_y1), (wx1 + pad + sb_w, body_y2)], radius=max(3, int(r * 0.06)), fill=(20, 32, 58, 230))
        main_x1 = wx1 + 2 * pad + sb_w
        main_w = max(6, wx2 - pad - main_x1)
        card_h_top = max(4, int((body_y2 - body_y1) * 0.52))
        draw.rounded_rectangle([(main_x1, body_y1), (main_x1 + main_w, body_y1 + card_h_top)], radius=max(3, int(r * 0.06)), fill=(28, 42, 78, 235), outline=prim, width=2)
        pts = [
            (main_x1 + 14 + int((main_w - 28) * (step_i / 6.0)), body_y1 + card_h_top // 2 + int(18 * math.sin(global_t * 6.0 + step_i)))
            for step_i in range(7)
        ]
        if len(pts) >= 2:
            draw.line(pts, fill=prim, width=4)

    elif scene_type == "video_montage_studio":
        studio_w, studio_h = int(r * 1.90), int(r * 1.45)
        sx1, sy1 = cx - studio_w // 2, cy - studio_h // 2
        sx2, sy2 = cx + studio_w // 2, cy + studio_h // 2

        draw.rounded_rectangle([(sx1, sy1), (sx2, sy2)], radius=26, fill=dark_panel, outline=prim, width=4)
        mon_h = int(studio_h * 0.50)
        mx1, my1 = sx1 + 24, sy1 + 22
        mx2, my2 = sx2 - 24, sy1 + 22 + mon_h
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=16, fill=(18, 28, 54, 255), outline=sec, width=3)

        mcx, mcy = (mx1 + mx2) // 2, (my1 + my2) // 2
        pr_s = int(28 + 5 * math.sin(global_t * 7.0))
        draw.polygon([(mcx - pr_s // 2, mcy - pr_s), (mcx - pr_s // 2, mcy + pr_s), (mcx + pr_s, mcy)], fill=prim, outline=white)

        tl_y1 = my2 + 22
        track_h = max(20, int((sy2 - tl_y1 - 36) / 3))
        track_colors = [
            [(56, 189, 248, 220), (99, 102, 241, 220), (56, 189, 248, 220)],
            [(255, 220, 0, 220), (249, 115, 22, 220)],
            [(52, 211, 153, 220), (16, 185, 129, 220), (52, 211, 153, 220)]
        ]
        for t_idx in range(3):
            ty = tl_y1 + t_idx * (track_h + 10)
            draw.rounded_rectangle([(mx1, ty), (mx2, ty + track_h)], radius=8, fill=(8, 13, 26, 230))
            segs = track_colors[t_idx]
            seg_w = (mx2 - mx1 - 24) // len(segs)
            for s_i, col in enumerate(segs):
                bx1 = mx1 + 8 + s_i * (seg_w + 6)
                bx2 = min(mx2 - 8, bx1 + seg_w - 4)
                draw.rounded_rectangle([(bx1, ty + 3), (bx2, ty + track_h - 3)], radius=6, fill=col)

        playhead_ratio = (scene_progress * 1.15) % 1.0
        px = int(mx1 + 16 + (mx2 - mx1 - 32) * playhead_ratio)
        draw.line([(px, tl_y1 - 10), (px, sy2 - 14)], fill=(255, 60, 80, 255), width=5)
        draw.polygon([(px - 10, tl_y1 - 12), (px + 10, tl_y1 - 12), (px, tl_y1 + 2)], fill=(255, 220, 0, 255))

    elif scene_type == "ai_neural_brain":
        node_positions = []
        num_outer = 8
        outer_r = int(r * 0.85)
        inner_r = int(r * 0.42)
        for i in range(num_outer):
            ang = math.radians(i * (360 / num_outer) + global_t * 25)
            node_positions.append((cx + int(outer_r * math.cos(ang)), cy + int(outer_r * math.sin(ang))))
        for i in range(4):
            ang = math.radians(i * 90 - global_t * 35)
            node_positions.append((cx + int(inner_r * math.cos(ang)), cy + int(inner_r * math.sin(ang))))
        node_positions.append((cx, cy))

        pulse_pos = (global_t * 1.8) % 1.0
        for i in range(len(node_positions)):
            for j in range(i + 1, len(node_positions)):
                x1, y1 = node_positions[i]
                x2, y2 = node_positions[j]
                if math.hypot(x2 - x1, y2 - y1) < r * 0.98:
                    draw.line([(x1, y1), (x2, y2)], fill=(*theme["secondary"], 95), width=3)
                    if (i + j) % 2 == 0:
                        px = int(x1 + (x2 - x1) * pulse_pos)
                        py = int(y1 + (y2 - y1) * pulse_pos)
                        draw.ellipse([(px - 6, py - 6), (px + 6, py + 6)], fill=prim)

        for idx, (nx, ny) in enumerate(node_positions):
            nr = 28 if idx == len(node_positions) - 1 else 15
            ncol = prim if idx % 2 == 0 else sec
            draw.ellipse([(nx - nr - 5, ny - nr - 5), (nx + nr + 5, ny + nr + 5)], fill=(ncol[0], ncol[1], ncol[2], 65))
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=dark_panel, outline=ncol, width=4)

        ai_font = get_arabic_font(int(r * 0.22), bold=True)
        draw_arabic_text(draw, (cx, cy), "ذكاء", font=ai_font, fill=prim)

    elif scene_type == "time_warp_clock":
        clock_r = int(r * 0.86)
        draw.ellipse([(cx - clock_r, cy - clock_r), (cx + clock_r, cy + clock_r)], fill=dark_panel, outline=prim, width=6)
        for h_i in range(12):
            ang = math.radians(h_i * 30 - 90)
            x1 = cx + int((clock_r - 24) * math.cos(ang))
            y1 = cy + int((clock_r - 24) * math.sin(ang))
            x2 = cx + int((clock_r - 8) * math.cos(ang))
            y2 = cy + int((clock_r - 8) * math.sin(ang))
            draw.line([(x1, y1), (x2, y2)], fill=sec if h_i % 3 == 0 else white, width=5 if h_i % 3 == 0 else 2)

        fast_ang = math.radians(global_t * 360 - 90)
        slow_ang = math.radians(global_t * 60 - 90)
        draw.line([(cx, cy), (cx + int(clock_r * 0.52 * math.cos(slow_ang)), cy + int(clock_r * 0.52 * math.sin(slow_ang)))], fill=sec, width=8)
        draw.line([(cx, cy), (cx + int(clock_r * 0.74 * math.cos(fast_ang)), cy + int(clock_r * 0.74 * math.sin(fast_ang)))], fill=prim, width=6)
        draw.ellipse([(cx - 12, cy - 12), (cx + 12, cy + 12)], fill=white)

    elif scene_type == "reels_smartphone":
        ph_w, ph_h = int(r * 1.05), int(r * 1.72)
        px1, py1 = cx - ph_w // 2, cy - ph_h // 2
        px2, py2 = cx + ph_w // 2, cy + ph_h // 2

        draw.rounded_rectangle([(px1 - 6, py1 - 6), (px2 + 6, py2 + 6)], radius=38, fill=(*theme["primary"], 55))
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=34, fill=(10, 16, 32, 245), outline=prim, width=5)
        draw.rounded_rectangle([(cx - 38, py1 + 14), (cx + 38, py1 + 26)], radius=6, fill=(40, 50, 75, 255))

        scroll_offset = int(((global_t * 140) % 120) - 60)
        card_y = cy + scroll_offset
        draw.rounded_rectangle([(px1 + 18, card_y - int(ph_h * 0.28)), (px2 - 18, card_y + int(ph_h * 0.28))], radius=20, fill=(24, 38, 72, 235), outline=sec, width=3)
        draw.polygon([(cx - 18, card_y - 26), (cx - 18, card_y + 26), (cx + 28, card_y)], fill=prim)

        for k in range(4):
            fy = py2 - 40 - int(((global_t * 180 + k * 95) % (ph_h - 60)))
            fx = px2 + 34 + int(14 * math.sin(global_t * 5 + k))
            b_col = (244, 63, 94, 240) if k % 2 == 0 else prim
            draw.ellipse([(fx - 18, fy - 18), (fx + 18, fy + 18)], fill=b_col, outline=white, width=2)

    elif scene_type == "ecommerce_showcase":
        float_y = int(14 * math.sin(global_t * 4.5))
        ped_y = cy + int(r * 0.52)
        draw.ellipse([(cx - int(r * 0.75), ped_y - 28), (cx + int(r * 0.75), ped_y + 28)], fill=(*theme["secondary"], 85), outline=sec, width=4)
        draw.ellipse([(cx - int(r * 0.50), ped_y - 16), (cx + int(r * 0.50), ped_y + 16)], fill=(*theme["primary"], 140))

        box_s = int(r * 0.62)
        by_center = cy - int(r * 0.12) + float_y
        draw.rounded_rectangle([(cx - box_s, by_center - box_s), (cx + box_s, by_center + box_s)], radius=28, fill=dark_panel, outline=prim, width=5)

        num_stars = min(5, max(1, int(scene_progress * 7)))
        star_y = by_center - box_s - 34
        for s_i in range(num_stars):
            sx = cx - 100 + s_i * 50
            draw.regular_polygon((sx, star_y, 18), n_sides=5, rotation=int(global_t * 30), fill=prim, outline=white)

        draw.ellipse([(cx - 42, by_center - 42), (cx + 42, by_center + 42)], fill=sec)
        draw.line([(cx - 20, by_center), (cx - 4, by_center + 18), (cx + 24, by_center - 16)], fill=(10, 16, 30, 255), width=7)

    elif scene_type == "delivery_express":
        map_w, map_h = int(r * 1.80), int(r * 1.30)
        mx1, my1 = cx - map_w // 2, cy - map_h // 2
        mx2, my2 = cx + map_w // 2, cy + map_h // 2
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=26, fill=dark_panel, outline=sec, width=4)

        p_start = (mx1 + 55, my2 - 55)
        p_mid = (cx, my1 + 45)
        p_end = (mx2 - 55, my2 - 65)
        route_pts = []
        for step in range(25):
            u = step / 24.0
            rx = int((1 - u) ** 2 * p_start[0] + 2 * (1 - u) * u * p_mid[0] + u ** 2 * p_end[0])
            ry = int((1 - u) ** 2 * p_start[1] + 2 * (1 - u) * u * p_mid[1] + u ** 2 * p_end[1])
            route_pts.append((rx, ry))
        draw.line(route_pts, fill=(255, 255, 255, 90), width=5)

        active_idx = max(2, int(len(route_pts) * min(1.0, scene_progress * 1.35)))
        draw.line(route_pts[:active_idx], fill=prim, width=8)
        cur_x, cur_y = route_pts[active_idx - 1]
        draw.ellipse([(cur_x - 20, cur_y - 20), (cur_x + 20, cur_y + 20)], fill=sec, outline=white, width=4)
        draw.ellipse([(p_end[0] - 16, p_end[1] - 16), (p_end[0] + 16, p_end[1] + 16)], fill=prim, outline=white, width=3)

    elif scene_type == "growth_analytics":
        chart_w, chart_h = int(r * 1.75), int(r * 1.35)
        cx1, cy1 = cx - chart_w // 2, cy - chart_h // 2
        cx2, cy2 = cx + chart_w // 2, cy + chart_h // 2
        draw.rounded_rectangle([(cx1, cy1), (cx2, cy2)], radius=24, fill=dark_panel, outline=(255, 255, 255, 80), width=3)

        num_bars = 5
        bar_space = (chart_w - 70) // num_bars
        bar_w = int(bar_space * 0.62)
        base_y = cy2 - 32
        max_bh = chart_h - 85
        ratios = [0.32, 0.48, 0.64, 0.82, 1.0]
        top_points = []

        for b_i, rat in enumerate(ratios):
            anim_p = _ease_out_back(min(1.0, max(0.05, scene_progress * 2.0 - b_i * 0.15)))
            bh = int(max_bh * rat * anim_p)
            bx = cx1 + 42 + b_i * bar_space
            b_col = prim if b_i == num_bars - 1 else (sec if b_i >= 2 else acc)
            draw.rounded_rectangle([(bx, base_y - bh), (bx + bar_w, base_y)], radius=10, fill=b_col, outline=white, width=2)
            top_points.append((bx + bar_w // 2, base_y - bh - 14))

        if len(top_points) >= 2:
            draw.line(top_points, fill=prim, width=6)
            lx, ly = top_points[-1]
            draw.ellipse([(lx - 12, ly - 12), (lx + 12, ly + 12)], fill=white, outline=prim, width=4)

    else:
        for ring_i in range(3):
            rr = int(r * (0.45 + ring_i * 0.24 + 0.05 * math.sin(global_t * 5 + ring_i)))
            col = prim if ring_i == 0 else (sec if ring_i == 1 else acc)
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=col, width=5 - ring_i)

        draw.regular_polygon((cx, cy, int(r * 0.48)), n_sides=6, rotation=int(global_t * 25), fill=dark_panel, outline=prim)
        draw.regular_polygon((cx, cy, int(r * 0.32)), n_sides=3, rotation=int(-global_t * 40), fill=sec, outline=white)


# ==============================================================================
# 5. تصيير المشهد الكامل لوضع الموشن جرافيك الصافي (Full-Screen Motion Canvas)
# ==============================================================================
def render_single_scene_canvas(
    scene_meta: Dict[str, Any],
    active_word: str,
    scene_words: List[str],
    active_word_idx: int,
    word_local_progress: float,
    scene_progress: float,
    global_t: float,
    total_duration: float,
    audio_level: float,
    width: int,
    height: int,
    bg_cache: Dict[str, np.ndarray]
) -> Image.Image:
    theme_name = scene_meta["theme_name"]
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])

    base_bg = bg_cache[theme_name]
    img = Image.fromarray(base_bg, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    cx = width // 2

    for p_i in range(10):
        px = int((width * (0.12 + 0.76 * ((p_i * 37) % 10) / 10.0) + 35 * math.sin(global_t * 1.5 + p_i)) % width)
        py = int((height * (0.85 - ((global_t * 65 + p_i * 180) % height) / float(height))) % height)
        pr = 4 + (p_i % 4) * 2
        draw.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(*theme["secondary"], 55))

    badge_font = get_arabic_font(max(22, int(width * 0.025)), bold=True)
    header_y = int(height * 0.065)
    badge_txt = scene_meta.get("badge_label", "أستوديو الموشن الذكي")
    bw, bh = measure_arabic_text(draw, badge_txt, badge_font)
    draw.rounded_rectangle(
        [(cx - bw // 2 - 28, header_y - bh // 2 - 10), (cx + bw // 2 + 28, header_y + bh // 2 + 10)],
        radius=20,
        fill=(12, 18, 36, 210),
        outline=(*theme["secondary"], 180),
        width=2
    )
    draw_arabic_text(draw, (cx, header_y), badge_txt, font=badge_font, fill=(*theme["secondary"], 255))

    illus_cy = int(height * 0.31) + int(10 * math.sin(global_t * 3.2))
    illus_radius = int(min(width, height) * 0.255)
    draw_animated_scene_illustration(
        draw=draw,
        scene_type=scene_meta["scene_type"],
        cx=cx,
        cy=illus_cy,
        radius=illus_radius,
        scene_progress=scene_progress,
        global_t=global_t,
        theme=theme,
        target_number=scene_meta.get("target_number", 17),
        short_title=scene_meta.get("short_title", "")
    )

    spring_scale = _ease_out_back(min(1.0, word_local_progress * 3.2))
    base_word_size = max(54, int(min(width, height) * 0.086))
    dynamic_font_size = max(36, int(base_word_size * max(0.65, spring_scale)))
    main_font = get_arabic_font(dynamic_font_size, bold=True)

    word_y = int(height * 0.62)
    cw, ch = measure_arabic_text(draw, active_word, main_font)
    pad_x = max(44, int(dynamic_font_size * 0.65))
    pad_y = max(24, int(dynamic_font_size * 0.38))

    bx1, by1 = cx - cw // 2 - pad_x, word_y - ch // 2 - pad_y
    bx2, by2 = cx + cw // 2 + pad_x, word_y + ch // 2 + pad_y

    draw.rounded_rectangle([(bx1 - 8, by1 - 8), (bx2 + 8, by2 + 8)], radius=30, fill=(*theme["primary"], 60))
    draw.rounded_rectangle(
        [(bx1, by1), (bx2, by2)],
        radius=26,
        fill=theme["card_bg"],
        outline=(*theme["primary"], 255),
        width=4
    )
    draw_arabic_text(
        draw,
        (cx, word_y),
        active_word,
        font=main_font,
        fill=(*theme["primary"], 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 230)
    )

    if scene_words:
        phrase_font = get_arabic_font(max(30, int(base_word_size * 0.48)), bold=True)
        phrase_str = " ".join(scene_words)
        pw, ph = measure_arabic_text(draw, phrase_str, phrase_font)
        sub_y = int(height * 0.745)
        bar_w = min(int(width * 0.90), pw + 56)
        draw.rounded_rectangle(
            [(cx - bar_w // 2, sub_y - ph // 2 - 16), (cx + bar_w // 2, sub_y + ph // 2 + 16)],
            radius=20,
            fill=(10, 16, 32, 215),
            outline=(*theme["secondary"], 150),
            width=2
        )
        draw_arabic_text(draw, (cx, sub_y), phrase_str, font=phrase_font, fill=(255, 255, 255, 245))

    eq_y_base = int(height * 0.885)
    num_bars = 22
    eq_total_w = int(width * 0.72)
    bar_step = eq_total_w // num_bars
    start_x = cx - eq_total_w // 2

    for b_i in range(num_bars):
        dist_center = 1.0 - abs(b_i - num_bars / 2.0) / (num_bars / 2.0)
        wave = 0.55 + 0.45 * math.sin(global_t * 14.0 + b_i * 0.75)
        bh = max(8, int(95 * audio_level * dist_center * wave))
        bx = start_x + b_i * bar_step
        b_col = (*theme["primary"], 230) if b_i % 2 == 0 else (*theme["secondary"], 220)
        draw.rounded_rectangle([(bx, eq_y_base - bh // 2), (bx + max(6, bar_step - 8), eq_y_base + bh // 2)], radius=4, fill=b_col)

    prog_ratio = min(1.0, max(0.01, global_t / max(0.1, total_duration)))
    bar_margin = int(width * 0.10)
    bar_y = height - 48
    full_w = width - 2 * bar_margin
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + full_w, bar_y + 10)], radius=5, fill=(255, 255, 255, 45))
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + int(full_w * prog_ratio), bar_y + 10)], radius=5, fill=(*theme["primary"], 255))

    return img


def apply_scene_transition(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str
) -> Image.Image:
    p = _ease_out_cubic(trans_progress)
    w, h = curr_img.size

    if transition_type == "whip_left":
        offset = int(w * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        out.paste(prev_img, (- int(w * p), 0))
        out.paste(curr_img, (offset, 0))
        draw = ImageDraw.Draw(out, "RGBA")
        draw.line([(offset, 0), (offset, h)], fill=(255, 230, 0, 220), width=8)
        return out

    elif transition_type == "whip_up":
        offset = int(h * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        out.paste(prev_img, (0, -int(h * p)))
        out.paste(curr_img, (0, offset))
        draw = ImageDraw.Draw(out, "RGBA")
        draw.line([(0, offset), (w, offset)], fill=(0, 245, 212, 220), width=8)
        return out

    elif transition_type == "zoom_portal":
        scale = 0.35 + 0.65 * p
        zw, zh = max(20, int(w * scale)), max(20, int(h * scale))
        resized_curr = curr_img.resize((zw, zh), Image.Resampling.BILINEAR)
        out = prev_img.copy()
        paste_x, paste_y = (w - zw) // 2, (h - zh) // 2
        out.paste(resized_curr, (paste_x, paste_y))
        return out

    else:
        return Image.blend(prev_img, curr_img, p)


# ==============================================================================
# 6. تصيير إطار الفيديو متعدد الأنماط المكانية (Master Directed Multi-Layout Frame)
# ==============================================================================
def render_master_directed_video_frame(
    base_frame_rgb: np.ndarray,
    t: float,
    total_duration: float,
    master_plan: List[Dict[str, Any]],
    words_data: List[Dict[str, Any]],
    bg_cache: Dict[str, np.ndarray],
    audio_level: float = 0.75,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> np.ndarray:
    """
    تصيير إطار الفيديو بتوزيع الأنماط المكانية وفق أوامر مخطط المخرج الشامل:
    - full_screen: يقطع لشاشة موشن جرافيك كاملة ومتحركة (B-roll) مع انتقالات سينمائية.
    - top_overlay: بطاقة موشن جرافيك ورسمة متحركة في النصف العلوي فوق المتحدث.
    - lower_third: شارة أو لافتة موشن جرافيك في الثلث السفلي (توصيل، ضمان، ميزات، أسعار).
    - speaker_clean: لقطة متحدث صافية مع زوم هادئ وكابشن كاريوكي فقط لراحة العين.
    """
    h, w, _ = base_frame_rgb.shape
    if not master_plan:
        return base_frame_rgb

    # 1. تحديد الأمر الإخراجي للمشهد الحالي عند اللحظة t
    active_idx = 0
    for idx, sc in enumerate(master_plan):
        if t >= sc["start"]:
            active_idx = idx
        else:
            break

    sc = master_plan[active_idx]
    layout_mode = sc.get("layout_mode", "top_overlay")
    theme_name = sc.get("theme_name", "cyber_gold")
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    sc_dur = max(0.18, sc["end"] - sc["start"])
    sc_prog = max(0.0, min(1.0, (t - sc["start"]) / sc_dur))

    # تحديد الكلمة المنطوقة حالياً وسياقها
    sc_words = sc.get("word_strings", [])
    act_word = sc_words[0] if sc_words else sc.get("short_title", "")
    w_prog = 0.5
    for wi, w_obj in enumerate(sc.get("words", [])):
        ws = float(w_obj.get("start", 0.0))
        we = float(w_obj.get("end", ws + 0.3))
        if t >= ws - 0.04:
            act_word = w_obj.get("word", "")
            wdur = max(0.10, we - ws)
            w_prog = max(0.0, min(1.0, (t - ws) / wdur))

    # -------------------------------------------------------------------------
    # النمط 1: شاشة موشن جرافيك كاملة B-Roll (Full-Screen Animated Scene)
    # -------------------------------------------------------------------------
    if layout_mode == "full_screen":
        curr_img = render_single_scene_canvas(
            scene_meta=sc,
            active_word=act_word,
            scene_words=sc_words,
            active_word_idx=0,
            word_local_progress=w_prog,
            scene_progress=sc_prog,
            global_t=t,
            total_duration=total_duration,
            audio_level=audio_level,
            width=w,
            height=h,
            bg_cache=bg_cache
        )
        # انتقال سلس عند الدخول في المشهد الكامل
        time_into_scene = t - sc["start"]
        if active_idx > 0 and 0.0 <= time_into_scene < 0.26:
            prev_base = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
            blended = apply_scene_transition(prev_base, curr_img, time_into_scene / 0.26, sc.get("transition", "zoom_portal"))
            return np.array(blended.convert("RGB"))
        return np.array(curr_img.convert("RGB"))

    # -------------------------------------------------------------------------
    # الأنماط التراكبية فوق فيديو المتحدث (Overlays on Speaker Video)
    # -------------------------------------------------------------------------
    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2

    # أ) النمط 2: شارة الميزة العلوية السينمائية الأنيقة (Sleek Glassmorphic Feature Pill)
    if layout_mode == "top_overlay":
        slide_in = _ease_out_back(min(1.0, (t - sc["start"]) / 0.22)) if (t >= sc["start"]) else 1.0
        y_slide_offset = int(-90 * (1.0 - slide_in))

        badge_title = sc.get("badge_label", sc.get("short_title", "ميزة حصرية"))
        title_font = get_arabic_font(max(24, int(min(w, h) * 0.034)), bold=True)
        tw, th = measure_arabic_text(draw, badge_title, title_font)

        pill_h = max(48, th + 22)
        pill_w = min(int(w * 0.84), max(tw + 78, int(w * 0.38)))
        top_y = int(h * 0.045) + y_slide_offset
        x1, y1 = cx - pill_w // 2, top_y
        x2, y2 = cx + pill_w // 2, top_y + pill_h

        # كبسولة زجاجية سينمائية رفيعة وغير مزعجة
        draw.rounded_rectangle([(x1 - 3, y1 - 3), (x2 + 3, y2 + 3)], radius=pill_h // 2, fill=(*theme["primary"], 45))
        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=pill_h // 2, fill=(12, 18, 32, 215), outline=(*theme["primary"], 220), width=2)

        # نقطة ضوئية نابضة أو أيقونة مصغرة
        dot_x = x2 - 24
        dot_y = y1 + pill_h // 2
        draw.ellipse([(dot_x - 6, dot_y - 6), (dot_x + 6, dot_y + 6)], fill=(*theme["primary"], 255))

        # النص بوضوح وأناقة
        text_cx = cx - 8
        draw_arabic_text(draw, (text_cx, y1 + pill_h // 2), badge_title, font=title_font, fill=(255, 255, 255, 245), stroke_width=2, stroke_fill=(0, 0, 0, 220))

    # ب) النمط 3: تراكب الثلث السفلي الأنيق (Sleek Lower Third Pill)
    elif layout_mode == "lower_third":
        l3_font = get_arabic_font(max(24, int(min(w, h) * 0.034)), bold=True)
        l3_txt = sc.get("badge_label", "ميزة حصرية")
        tw, th = measure_arabic_text(draw, l3_txt, l3_font)
        bar_w = min(int(w * 0.88), tw + 64)
        bar_h = th + 24
        by1 = int(h * 0.86)
        by2 = by1 + bar_h
        bx1 = cx - bar_w // 2
        bx2 = cx + bar_w // 2

        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=bar_h // 2, fill=(10, 16, 28, 225), outline=(*theme["primary"], 240), width=2)
        draw_arabic_text(draw, (cx, by1 + bar_h // 2), l3_txt, font=l3_font, fill=(*theme["primary"], 255), stroke_width=2, stroke_fill=(0, 0, 0, 230))

    # -------------------------------------------------------------------------
    # ج) الكابشن الاحترافي الحديث (Modern Social-Media 1-Line Karaoke Subtitles)
    # -------------------------------------------------------------------------
    if caption_mode != "none" and (act_word or sc_words):
        # موضع الأمان للكابشن: أسفل الشاشة (Lower-Third Safe Zone) بعيداً تماماً عن المنتجات والأيدي في المركز
        if caption_mode == "top_compact":
            cap_y = int(h * 0.14)
        elif layout_mode == "lower_third":
            cap_y = int(h * 0.77)
        else:
            cap_y = int(h * 0.84)

        # تنظيف الكلمات من الفواصل وعلامات الترقيم المعكوسة
        clean_sc_words = [re.sub(r'^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$', '', w).strip() for w in sc_words if w.strip()]
        clean_act_word = re.sub(r'^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$', '', act_word).strip() if act_word else (clean_sc_words[0] if clean_sc_words else "")

        font_size = max(34, int(min(w, h) * 0.048))
        cap_font = get_arabic_font(font_size, bold=True)
        glow_font = get_arabic_font(font_size + 2, bold=True)

        # تحديد نافذة من 3-4 كلمات كحد أقصى للعرض
        active_word_clean = clean_act_word.lower()
        target_idx = 0
        for wi, cw in enumerate(clean_sc_words):
            if cw.lower() == active_word_clean or active_word_clean in cw.lower():
                target_idx = wi
                break

        win_size = min(4, len(clean_sc_words))
        if len(clean_sc_words) <= 4:
            display_words = clean_sc_words
            disp_active_idx = target_idx
        else:
            start_w = max(0, min(target_idx - 1, len(clean_sc_words) - win_size))
            display_words = clean_sc_words[start_w:start_w + win_size]
            disp_active_idx = max(0, min(target_idx - start_w, len(display_words) - 1))

        if not display_words:
            display_words = [clean_act_word]
            disp_active_idx = 0

        # قياس الكلمات وتجميعها
        word_widths = []
        word_spaces = int(font_size * 0.35)
        for dw in display_words:
            ww, wh = measure_arabic_text(draw, dw, cap_font)
            word_widths.append((ww, wh))

        total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces
        max_line_h = max(wh for _, wh in word_widths) if word_widths else font_size

        # كبسولة زجاجية أنيقة وموحدة تحمي القراءة
        box_pad_x = int(font_size * 0.60)
        box_pad_y = int(font_size * 0.30)
        bar_x1 = max(int(w * 0.04), cx - total_line_w // 2 - box_pad_x)
        bar_x2 = min(int(w * 0.96), cx + total_line_w // 2 + box_pad_x)
        bar_y1 = cap_y - max_line_h // 2 - box_pad_y
        bar_y2 = cap_y + max_line_h // 2 + box_pad_y

        draw.rounded_rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], radius=20, fill=(8, 12, 22, 195), outline=(255, 255, 255, 35), width=1)

        # رسم الكلمات بالترتيب من اليمين إلى اليسار (RTL)
        cur_right_x = bar_x2 - box_pad_x
        for wi, dw in enumerate(display_words):
            ww, wh = word_widths[wi]
            is_active = (wi == disp_active_idx)
            word_cx = cur_right_x - ww // 2

            if is_active:
                # الكلمة الحالية: لون أصفر ذهبي ناصع وتوهج فخم
                draw_arabic_text(draw, (word_cx, cap_y), dw, font=glow_font, fill=(255, 225, 0, 90), stroke_width=4, stroke_fill=(0, 0, 0, 180))
                draw_arabic_text(draw, (word_cx, cap_y), dw, font=cap_font, fill=(255, 230, 0, 255), stroke_width=3, stroke_fill=(0, 0, 0, 245))
            else:
                # الكلمات المحيطة: أبيض ناصع مع تظليل أسود
                draw_arabic_text(draw, (word_cx, cap_y), dw, font=cap_font, fill=(245, 245, 245, 235), stroke_width=2, stroke_fill=(0, 0, 0, 230))

            cur_right_x -= (ww + word_spaces)

    return np.array(img.convert("RGB"))


def create_studio_background(
    width: int,
    height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    top_c = np.array(theme["top_bg"], dtype=np.float32)
    bot_c = np.array(theme["bottom_bg"], dtype=np.float32)
    glow_c = np.array(theme["glow"], dtype=np.float32)

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    yy, xx = np.ogrid[:height, :width]
    cx, cy = width * 0.5, height * 0.35
    dist_sq = ((xx - cx) / (width * 0.55)) ** 2 + ((yy - cy) / (height * 0.38)) ** 2
    radial_mask = np.exp(-dist_sq * 1.8)[:, :, None] * 0.25
    canvas_np = np.clip(canvas_np * (1.0 - radial_mask) + glow_c * radial_mask, 0, 255).astype(np.uint8)

    img = Image.fromarray(canvas_np, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    step = max(64, min(width, height) // 12)
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 11), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 11), width=1)

    return np.array(img)


# ==============================================================================
# 7. المسار الرئيسي لتوليد فيديو الموشن جرافيك الكامل
# ==============================================================================
def create_kinetic_typography_video(
    input_path: str,
    output_path: str,
    video_resolution: Tuple[int, int] = (1080, 1920),
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    **kwargs
) -> str:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف المدخل غير موجود: {input_path}")

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    from moviepy.editor import AudioFileClip, VideoClip

    audio_clip = None
    motion_clip = None

    try:
        update_progress(0.10, "1/4: قراءة الصوت وتفريغ الكلمات بدقة الملي ثانية...")
        audio_clip = AudioFileClip(input_path)
        total_duration = float(audio_clip.duration)

        if total_duration <= 0.2:
            raise ValueError("الملف الصوتي قصير جداً وغير صالح للمعالجة.")

        words_data = transcribe_audio(
            input_path,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        if not words_data:
            raise ValueError("لم يتم استخراج أي كلمات من الملف الصوتي.")

        update_progress(0.28, "2/4: بناء القصة البصرية وتوليد مشهد موشن جرافيك جديد لكل 1.5 - 2 ثانية...")
        micro_scenes = split_words_into_micro_scenes(words_data, max_words_per_scene=4, max_duration_per_scene=2.0)

        storyboard: List[Dict[str, Any]] = []
        prev_s_type = None
        for idx, sc in enumerate(micro_scenes):
            bp = classify_micro_scene_blueprint(
                scene_text=sc["text"],
                scene_index=idx,
                total_scenes=len(micro_scenes),
                prev_scene_type=prev_s_type
            )
            prev_s_type = bp["scene_type"]
            s_start = float(sc["start"])
            s_end = float(micro_scenes[idx + 1]["start"]) if (idx + 1 < len(micro_scenes)) else total_duration

            storyboard.append({
                "index": idx,
                "start": s_start,
                "end": max(s_start + 0.2, s_end),
                "text": sc["text"],
                "words": sc["words"],
                "word_strings": [w["word"] for w in sc["words"]],
                **bp
            })

        update_progress(0.45, "3/4: تجهيز الخلفيات الديناميكية ومعايرة الموجات الصوتية...")
        w, h = video_resolution
        bg_cache = {
            t_name: create_studio_background(w, h, theme_name=t_name)
            for t_name in MOTION_THEMES.keys()
        }

        audio_envelope = np.ones(int(total_duration * 24) + 24, dtype=np.float32) * 0.5
        try:
            from pydub import AudioSegment
            aud_seg = AudioSegment.from_file(input_path)
            step_ms = int(1000 / 24)
            raw_rms = [c.rms for c in aud_seg[::step_ms]]
            if raw_rms and max(raw_rms) > 0:
                max_r = float(max(raw_rms))
                norm_rms = [min(1.0, max(0.22, (r_val / max_r) ** 0.65)) for r_val in raw_rms]
                audio_envelope[:len(norm_rms)] = norm_rms
        except Exception:
            pass

        def _get_scene_state_at(t_sec: float) -> Tuple[int, Dict[str, Any], str, int, float, float]:
            active_sc_idx = 0
            for idx, sc in enumerate(storyboard):
                if t_sec >= sc["start"]:
                    active_sc_idx = idx
                else:
                    break

            sc = storyboard[active_sc_idx]
            sc_dur = max(0.15, sc["end"] - sc["start"])
            sc_prog = max(0.0, min(1.0, (t_sec - sc["start"]) / sc_dur))

            sc_words = sc["words"]
            act_w_str = sc_words[0]["word"] if sc_words else sc["short_title"]
            act_w_idx = 0
            w_prog = sc_prog

            for wi, w_obj in enumerate(sc_words):
                ws = float(w_obj["start"])
                we = float(sc_words[wi + 1]["start"]) if (wi + 1 < len(sc_words)) else float(w_obj["end"])
                if t_sec >= ws:
                    act_w_str = w_obj["word"]
                    act_w_idx = wi
                    wdur = max(0.10, we - ws)
                    w_prog = max(0.0, min(1.0, (t_sec - ws) / wdur))

            return active_sc_idx, sc, act_w_str, act_w_idx, w_prog, sc_prog

        transition_duration = 0.28

        def make_frame(t: float) -> np.ndarray:
            frame_idx = min(len(audio_envelope) - 1, max(0, int(t * 24)))
            aud_lvl = float(audio_envelope[frame_idx])

            sc_idx, sc, act_word, act_w_idx, w_prog, sc_prog = _get_scene_state_at(t)

            curr_img = render_single_scene_canvas(
                scene_meta=sc,
                active_word=act_word,
                scene_words=sc["word_strings"],
                active_word_idx=act_w_idx,
                word_local_progress=w_prog,
                scene_progress=sc_prog,
                global_t=t,
                total_duration=total_duration,
                audio_level=aud_lvl,
                width=w,
                height=h,
                bg_cache=bg_cache
            )

            time_into_scene = t - sc["start"]
            if sc_idx > 0 and 0.0 <= time_into_scene < transition_duration:
                prev_sc = storyboard[sc_idx - 1]
                prev_word = prev_sc["word_strings"][-1] if prev_sc["word_strings"] else prev_sc["short_title"]
                prev_img = render_single_scene_canvas(
                    scene_meta=prev_sc,
                    active_word=prev_word,
                    scene_words=prev_sc["word_strings"],
                    active_word_idx=max(0, len(prev_sc["word_strings"]) - 1),
                    word_local_progress=1.0,
                    scene_progress=1.0,
                    global_t=t,
                    total_duration=total_duration,
                    audio_level=aud_lvl,
                    width=w,
                    height=h,
                    bg_cache=bg_cache
                )
                trans_prog = time_into_scene / transition_duration
                blended = apply_scene_transition(
                    prev_img=prev_img,
                    curr_img=curr_img,
                    trans_progress=trans_prog,
                    transition_type=sc["transition_type"]
                )
                return np.array(blended.convert("RGB"))

            return np.array(curr_img.convert("RGB"))

        update_progress(0.65, f"4/4: رندرة {len(storyboard)} مشهد موشن جرافيك متحرك...")
        motion_clip = VideoClip(make_frame, duration=total_duration).set_audio(audio_clip)

        temp_audio_file = os.path.join(temp_dir, "temp_motion_audio.m4a")
        motion_clip.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio_file,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, f"تم إنتاج فيديو الموشن جرافيك المتكامل ({len(storyboard)} مشهد متحرك) بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ أثناء تصدير الموشن جرافيك: {str(err)}", exc_info=True)
        raise err

    finally:
        if motion_clip is not None:
            try:
                motion_clip.close()
            except Exception:
                pass
        if audio_clip is not None:
            try:
                audio_clip.close()
            except Exception:
                pass
