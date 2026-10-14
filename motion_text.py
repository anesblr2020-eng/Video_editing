"""
motion_text.py - محرك الموشن جرافيك الكامل والمتحرك إطاراً بإطار (للصوت وللفيديو المدمج)
========================================================================================
يقوم هذا المحرك بـ:
1. تقسيم الفيديو أو الصوت إلى مشاهد قصيرة متجددة كل 1.4 إلى 1.9 ثانية (Micro-Scenes) بحيث يتغير الجرافيك باستمرار.
2. فهم كلمات الدارجة الجزائرية والعربية (اصبر، ما حبستكش، كابل تيب سي، سيبور تيليفون، تشارجي، قاع يتقطع، 58/69 ولاية، اكموندي...) وتوليد رسمة متحركة مطابقة لمعنى كل جملة.
3. تحريك حقيقي إطاراً بإطار (24/30 FPS) يشمل:
   - دخول البطاقات والرسومات بفيزياء زنبركية (Slide & Spring Bounce).
   - حركة داخلية مستمرة للرسومات (عدادات، رادار توصيل، هاتف ذكي، شاحن وطاقة، درع متانة، شريط مونتاج، شبكة ذكاء اصطناعي).
   - شريط كابشن كاريوكي متصل يعرض العبارة كاملة مع إضاءة وتكبير الكلمة المنطوقة لحظياً ليمشي "سوا سوا" مع الصوت بدون أي تقطيع.
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
# 1. إعداد الخطوط العربية وتشكيل الحروف السليم مع التخزين المؤقت للسرعة
# ==============================================================================
_FONT_DOWNLOAD_ATTEMPTED = False
_FONT_OBJECT_CACHE: Dict[Tuple[int, bool], ImageFont.FreeTypeFont] = {}
_HAS_RAQM = False
try:
    _HAS_RAQM = bool(features.check("raqm"))
except Exception:
    _HAS_RAQM = False


def shape_arabic_text(text: str) -> str:
    """ضمان ظهور الحروف العربية متصلة وبالاتجاه الصحيح."""
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
    """رسم نص عربي بدقة عالية."""
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
    """قياس عرض وارتفاع النص العربي بدقة."""
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
    """جلب أفضل خط عربي متوفر مع تخزينه في الذاكرة."""
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
# 2. الثيمات اللونية المتعددة للمشاهد (6 ثيمات أستوديو سينمائية)
# ==============================================================================
MOTION_THEMES = {
    "cyber_gold": {
        "top_bg": (9, 14, 30),
        "bottom_bg": (22, 28, 62),
        "glow": (56, 189, 248),
        "primary": (255, 220, 0),
        "secondary": (0, 245, 212),
        "accent": (99, 102, 241),
        "card_bg": (13, 20, 40, 230)
    },
    "emerald_tech": {
        "top_bg": (5, 24, 22),
        "bottom_bg": (12, 48, 44),
        "glow": (16, 185, 129),
        "primary": (52, 211, 153),
        "secondary": (251, 191, 36),
        "accent": (6, 182, 212),
        "card_bg": (7, 32, 28, 230)
    },
    "royal_purple": {
        "top_bg": (20, 10, 38),
        "bottom_bg": (46, 18, 76),
        "glow": (236, 72, 153),
        "primary": (255, 195, 0),
        "secondary": (255, 77, 141),
        "accent": (168, 85, 247),
        "card_bg": (28, 14, 52, 230)
    },
    "crimson_energy": {
        "top_bg": (28, 9, 16),
        "bottom_bg": (56, 16, 30),
        "glow": (249, 115, 22),
        "primary": (255, 230, 0),
        "secondary": (255, 115, 0),
        "accent": (239, 68, 68),
        "card_bg": (36, 12, 22, 230)
    },
    "ocean_neon": {
        "top_bg": (6, 18, 36),
        "bottom_bg": (14, 42, 74),
        "glow": (14, 165, 233),
        "primary": (56, 189, 248),
        "secondary": (250, 204, 21),
        "accent": (45, 212, 191),
        "card_bg": (10, 26, 48, 230)
    },
    "sunset_violet": {
        "top_bg": (24, 12, 32),
        "bottom_bg": (54, 22, 58),
        "glow": (244, 63, 94),
        "primary": (251, 146, 60),
        "secondary": (56, 189, 248),
        "accent": (232, 121, 249),
        "card_bg": (32, 14, 42, 230)
    }
}


# ==============================================================================
# 3. مصنف المشاهد الذكي (يدعم مفردات الدارجة الجزائرية والتقنية والمنتجات)
# ==============================================================================
def classify_micro_scene_blueprint(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    prev_scene_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    تحديد نوع المشهد الرسومي المتحرك وعنوانه باللغة العربية/الدارجة بناءً على الكلمات المنطوقة
    في هذه الثانية أو الثانيتين، مع ضمان عدم تكرار نفس المشهد مرتين متتاليتين أبداً!
    """
    t = scene_text.strip()
    t_low = t.lower()

    num_match = re.search(r"\b(\d+)\b", t)
    extracted_number = int(num_match.group(1)) if num_match else None

    chosen_type = None
    badge_label = "مشهد موشن جرافيك"

    if any(w in t_low for w in ["توصيل", "ولاية", "58", "69", "باب الدار", "شحن", "متوفر", "ليفريزون"]):
        chosen_type = "delivery_express"
        badge_label = f"توصيل سريع {extracted_number or 58} ولاية"
    elif any(w in t_low for w in ["اكموندي", "كوموندي", "اطلب", "الرابط", "اسفل", "أسفل", "البايو", "كليكي"]):
        chosen_type = "brand_finale"
        badge_label = "اطلب الآن من الرابط"
    elif any(w in t_low for w in ["تشارجي", "شحن", "كابل", "تيب سي", "type-c", "بطارية", "طاقة", "قوة"]):
        chosen_type = "power_charge_tech"
        badge_label = "شحن فائق السرعة"
    elif any(w in t_low for w in ["سيبور", "تيليفون", "تتفرج", "ريلز", "ريز", "تيك توك", "شورتس", "ترفع", "هاتف"]):
        chosen_type = "reels_smartphone"
        badge_label = "سيبور تيليفون ومشاهدة مريحة" if ("سيبور" in t_low or "تيليفون" in t_low or "تتفرج" in t_low) else "نشر الريلز والمحتوى"
    elif any(w in t_low for w in ["مغلف", "قماش", "يتقطع", "ما تخافش", "متخافش", "ضمان", "أصلي", "جودة", "متين"]):
        chosen_type = "ecommerce_showcase"
        badge_label = "متانة وجودة عالية ضد القطع"
    elif any(w in t_low for w in ["اصبر", "أصبر", "حبستكش", "ما حبستكش", "انتبه", "شوف"]):
        chosen_type = "hook_energy_burst"
        badge_label = "انتبه - منتج استثنائي"
    elif any(w in t_low for w in ["مونتاج", "منتاج", "تمنتج", "فيديوهات", "فيديو", "ايديت", "إيديتينج"]):
        if scene_index == total_scenes - 1 and any(w in t_low for w in ["اسم", "منصة", "إيديتينج"]):
            chosen_type = "brand_finale"
            badge_label = "منصة تحرير الفيديو الذكية"
        else:
            chosen_type = "video_montage_studio"
            badge_label = "أستوديو المونتاج الذكي"
    elif any(w in t_low for w in ["ذكاء", "اصطناعي", "استناعي", "أوتوماتيكي", "اوتوماتيكي", "تلقائي"]):
        chosen_type = "ai_neural_brain"
        badge_label = "محرك الذكاء الاصطناعي"
    elif any(w in t_low for w in ["أبني", "ابني", "منصة", "تعمل", "موقع", "تطبيق", "مشروع", "نظام"]):
        chosen_type = "platform_builder"
        badge_label = "بناء وتطوير المنصة"
    elif extracted_number is not None or any(w in t_low for w in ["عمري", "عمره", "سنة", "سنين", "مئة"]):
        chosen_type = "age_number_counter"
        badge_label = f"محطة الإنجاز - {extracted_number or 17}"
    elif any(w in t_low for w in ["وقت", "ساعة", "ما عندها", "سرعة", "ثواني", "نفس الوقت"]):
        chosen_type = "time_warp_clock"
        badge_label = "في نفس الوقت وبكل سرعة"
    elif any(w in t_low for w in ["أهلاً", "اهلا", "سلام", "أنا", "أنس", "اناس", "اسمي", "مرحبا", "خاوتي"]):
        chosen_type = "creator_profile"
        badge_label = "بطاقة تعريف المبدع"
    elif any(w in t_low for w in ["أغلب", "الناس", "مال", "ربح", "دراهم", "سعر", "سومة", "تخفيض", "راحة", "كل يوم"]):
        chosen_type = "growth_analytics"
        badge_label = "أداء عالٍ وراحة تامة"

    fallback_cycle = [
        ("hook_energy_burst", "ميزة استثنائية"),
        ("power_charge_tech", "تقنية متطورة"),
        ("reels_smartphone", "تصميم ذكي ومريح"),
        ("ecommerce_showcase", "جودة أصلية مضمونة"),
        ("time_warp_clock", "سرعة وكفاءة"),
        ("growth_analytics", "الخيار الأول"),
        ("delivery_express", "توصيل سريع لباب الدار"),
        ("brand_finale", "اطلب الآن")
    ]
    if not chosen_type or chosen_type == prev_scene_type:
        alt_type, alt_label = fallback_cycle[scene_index % len(fallback_cycle)]
        if alt_type == prev_scene_type:
            alt_type, alt_label = fallback_cycle[(scene_index + 1) % len(fallback_cycle)]
        chosen_type = alt_type
        if badge_label == "مشهد موشن جرافيك":
            badge_label = alt_label

    stop_words = {"في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "هاذ", "اللي", "التي", "الذي", "ما", "لا", "كل"}
    words = [w for w in re.findall(r"[\w\u0621-\u064A]+", t) if w not in stop_words and len(w) > 2]
    short_title = " ".join(words[:3]) if len(words) >= 2 else (words[0] if words else badge_label)

    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    return {
        "scene_type": chosen_type,
        "badge_label": badge_label,
        "short_title": short_title,
        "target_number": extracted_number if extracted_number is not None else 100,
        "theme_name": theme_keys[scene_index % len(theme_keys)],
        "transition_type": transitions[scene_index % len(transitions)]
    }


# ==============================================================================
# 4. رسام المشاهد الرسومية الكاملة والمتحركة إطاراً بإطار (12+ مشهد متحرك)
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
    """رسم مشهد موشن جرافيك متحرك بالكامل يتفاعل لحظياً مع الزمن global_t."""
    prim = (*theme["primary"], 255)
    sec = (*theme["secondary"], 255)
    acc = (*theme["accent"], 240)
    white = (255, 255, 255, 255)
    dark_panel = (12, 19, 38, 240)

    enter_scale = _ease_out_back(min(1.0, scene_progress * 2.8))
    r = int(radius * max(0.25, enter_scale))

    orbit_angle = global_t * 65.0
    draw.ellipse(
        [(cx - int(r * 1.05), cy - int(r * 1.05)), (cx + int(r * 1.05), cy + int(r * 1.05))],
        fill=(14, 22, 44, 245),
        outline=(*theme["secondary"], 110),
        width=3
    )
    draw.arc(
        [(cx - int(r * 1.14), cy - int(r * 1.14)), (cx + int(r * 1.14), cy + int(r * 1.14))],
        start=int(orbit_angle) % 360,
        end=(int(orbit_angle) + 115) % 360,
        fill=prim,
        width=6
    )
    draw.arc(
        [(cx - int(r * 1.14), cy - int(r * 1.14)), (cx + int(r * 1.14), cy + int(r * 1.14))],
        start=(int(orbit_angle) + 180) % 360,
        end=(int(orbit_angle) + 285) % 360,
        fill=sec,
        width=5
    )

    # مشهد أ: شحن الطاقة والكابل الذكي (Power Charge & Cable Tech)
    if scene_type == "power_charge_tech":
        bat_w, bat_h = int(r * 1.10), int(r * 1.45)
        bx1, by1 = cx - bat_w // 2, cy - bat_h // 2
        bx2, by2 = cx + bat_w // 2, cy + bat_h // 2
        # رأس البطارية/الموصل
        draw.rounded_rectangle([(cx - int(bat_w * 0.25), by1 - 18), (cx + int(bat_w * 0.25), by1 + 4)], radius=6, fill=sec)
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=24, fill=dark_panel, outline=prim, width=5)

        # مستوى الشحن يصعد ديناميكياً
        fill_ratio = 0.25 + 0.75 * ((global_t * 1.2) % 1.0)
        fh = int((bat_h - 24) * fill_ratio)
        draw.rounded_rectangle([(bx1 + 12, by2 - 12 - fh), (bx2 - 12, by2 - 12)], radius=14, fill=(*theme["secondary"], 180))

        # صاعقة شحن كهربائية نابضة في المنتصف
        bolt = [
            (cx + 12, cy - int(r * 0.45)),
            (cx - int(r * 0.28), cy + 6),
            (cx + 4, cy + 6),
            (cx - 16, cy + int(r * 0.48)),
            (cx + int(r * 0.30), cy - 8),
            (cx - 4, cy - 8),
        ]
        draw.polygon(bolt, fill=prim, outline=white)

    # مشهد ب: خطاف الانتباه الناري (Hook Energy Burst)
    elif scene_type == "hook_energy_burst":
        for ring_k in range(3):
            rr = int(r * (0.42 + ring_k * 0.22 + 0.06 * math.sin(global_t * 8 + ring_k)))
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=prim if ring_k % 2 == 0 else sec, width=5)
        # مثلث تنبيه / صاعقة الطاقة
        tri_r = int(r * 0.52)
        pts = [
            (cx, cy - tri_r),
            (cx - int(tri_r * 0.92), cy + int(tri_r * 0.75)),
            (cx + int(tri_r * 0.92), cy + int(tri_r * 0.75))
        ]
        draw.polygon(pts, fill=dark_panel, outline=prim)
        draw.line(pts + [pts[0]], fill=prim, width=6)
        draw.rounded_rectangle([(cx - 8, cy - int(tri_r * 0.35)), (cx + 8, cy + int(tri_r * 0.20))], radius=6, fill=sec)
        draw.ellipse([(cx - 9, cy + int(tri_r * 0.34)), (cx + 9, cy + int(tri_r * 0.52))], fill=prim)

    # مشهد 1: بطاقة الهوية والمبدع
    elif scene_type == "creator_profile":
        card_w, card_h = int(r * 1.75), int(r * 1.35)
        x1, y1 = cx - card_w // 2, cy - card_h // 2
        x2, y2 = cx + card_w // 2, cy + card_h // 2

        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=28, fill=dark_panel, outline=prim, width=4)
        av_r = int(r * 0.36)
        av_y = cy - int(r * 0.05)
        pulse = int(7 * math.sin(global_t * 6.0))
        draw.ellipse([(cx - av_r - pulse, av_y - av_r - pulse), (cx + av_r + pulse, av_y + av_r + pulse)], outline=sec, width=3)
        draw.ellipse([(cx - av_r, av_y - av_r), (cx + av_r, av_y + av_r)], fill=(28, 45, 82, 255), outline=prim, width=4)
        head_r = int(av_r * 0.34)
        draw.ellipse([(cx - head_r, av_y - int(av_r * 0.45) - head_r), (cx + head_r, av_y - int(av_r * 0.45) + head_r)], fill=prim)
        draw.pieslice([(cx - int(av_r * 0.62), av_y + int(av_r * 0.05)), (cx + int(av_r * 0.62), av_y + int(av_r * 0.95))], start=180, end=360, fill=sec)

    # مشهد 2: عداد الأرقام الديناميكي
    elif scene_type == "age_number_counter":
        count_progress = _ease_out_cubic(min(1.0, scene_progress * 1.5))
        current_val = max(1, int(round(target_number * count_progress)))
        gauge_r = int(r * 0.88)
        draw.ellipse([(cx - gauge_r, cy - gauge_r), (cx + gauge_r, cy + gauge_r)], fill=dark_panel, outline=(255, 255, 255, 60), width=4)
        sweep_deg = int(300 * count_progress)
        draw.arc([(cx - gauge_r + 12, cy - gauge_r + 12), (cx + gauge_r - 12, cy + gauge_r - 12)], start=120, end=120 + sweep_deg, fill=prim, width=14)
        num_font = get_arabic_font(int(r * 0.68), bold=True)
        draw_arabic_text(draw, (cx, cy - 6), str(current_val), font=num_font, fill=prim, stroke_width=3, stroke_fill=(0, 0, 0, 240))

    # مشهد 3: بناء المنصة والواجهة الذكية
    elif scene_type == "platform_builder":
        win_w, win_h = int(r * 1.80), int(r * 1.35)
        wx1, wy1 = cx - win_w // 2, cy - win_h // 2
        wx2, wy2 = cx + win_w // 2, cy + win_h // 2
        draw.rounded_rectangle([(wx1, wy1), (wx2, wy2)], radius=22, fill=dark_panel, outline=sec, width=4)
        pad = 18
        body_y1 = wy1 + 42
        sb_w = int((win_w - 3 * pad) * 0.30)
        draw.rounded_rectangle([(wx1 + pad, body_y1), (wx1 + pad + sb_w, wy2 - pad)], radius=12, fill=(20, 32, 58, 230))
        main_x1 = wx1 + 2 * pad + sb_w
        main_w = wx2 - pad - main_x1
        card_h_top = int((wy2 - pad - body_y1) * 0.52)
        draw.rounded_rectangle([(main_x1, body_y1), (main_x1 + main_w, body_y1 + card_h_top)], radius=12, fill=(28, 42, 78, 235), outline=prim, width=3)
        pts = [
            (main_x1 + 14 + int((main_w - 28) * (step_i / 6.0)), body_y1 + card_h_top // 2 + int(18 * math.sin(global_t * 6.0 + step_i)))
            for step_i in range(7)
        ]
        draw.line(pts, fill=prim, width=4)

    # مشهد 4: أستوديو وشريط المونتاج المتحرك
    elif scene_type == "video_montage_studio":
        studio_w, studio_h = int(r * 1.85), int(r * 1.40)
        sx1, sy1 = cx - studio_w // 2, cy - studio_h // 2
        sx2, sy2 = cx + studio_w // 2, cy + studio_h // 2
        draw.rounded_rectangle([(sx1, sy1), (sx2, sy2)], radius=24, fill=dark_panel, outline=prim, width=4)
        mon_h = int(studio_h * 0.48)
        mx1, my1 = sx1 + 18, sy1 + 18
        mx2, my2 = sx2 - 18, sy1 + 18 + mon_h
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=14, fill=(18, 28, 54, 255), outline=sec, width=2)
        mcx, mcy = (mx1 + mx2) // 2, (my1 + my2) // 2
        pr_s = int(22 + 4 * math.sin(global_t * 7.0))
        draw.polygon([(mcx - pr_s // 2, mcy - pr_s), (mcx - pr_s // 2, mcy + pr_s), (mcx + pr_s, mcy)], fill=prim)
        tl_y1 = my2 + 16
        track_h = max(16, int((sy2 - tl_y1 - 24) / 2))
        for t_idx in range(2):
            ty = tl_y1 + t_idx * (track_h + 8)
            draw.rounded_rectangle([(mx1, ty), (mx2, ty + track_h)], radius=6, fill=(56, 189, 248, 200) if t_idx == 0 else (255, 220, 0, 200))
        playhead_ratio = (global_t * 0.65) % 1.0
        px = int(mx1 + 12 + (mx2 - mx1 - 24) * playhead_ratio)
        draw.line([(px, tl_y1 - 6), (px, sy2 - 10)], fill=(255, 60, 80, 255), width=4)

    # مشهد 5: شبكة الذكاء الاصطناعي العصبية
    elif scene_type == "ai_neural_brain":
        node_positions = []
        outer_r = int(r * 0.82)
        for i in range(6):
            ang = math.radians(i * 60 + global_t * 30)
            node_positions.append((cx + int(outer_r * math.cos(ang)), cy + int(outer_r * math.sin(ang))))
        node_positions.append((cx, cy))
        pulse_pos = (global_t * 2.0) % 1.0
        for i in range(len(node_positions) - 1):
            x1, y1 = node_positions[i]
            x2, y2 = cx, cy
            draw.line([(x1, y1), (x2, y2)], fill=(*theme["secondary"], 140), width=3)
            px = int(x1 + (x2 - x1) * pulse_pos)
            py = int(y1 + (y2 - y1) * pulse_pos)
            draw.ellipse([(px - 5, py - 5), (px + 5, py + 5)], fill=prim)
        for idx, (nx, ny) in enumerate(node_positions):
            nr = 22 if idx == len(node_positions) - 1 else 12
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=dark_panel, outline=prim if idx % 2 == 0 else sec, width=4)

    # مشهد 6: الساعة والمؤقت السريع
    elif scene_type == "time_warp_clock":
        clock_r = int(r * 0.85)
        draw.ellipse([(cx - clock_r, cy - clock_r), (cx + clock_r, cy + clock_r)], fill=dark_panel, outline=prim, width=5)
        fast_ang = math.radians(global_t * 360 - 90)
        slow_ang = math.radians(global_t * 60 - 90)
        draw.line([(cx, cy), (cx + int(clock_r * 0.50 * math.cos(slow_ang)), cy + int(clock_r * 0.50 * math.sin(slow_ang)))], fill=sec, width=6)
        draw.line([(cx, cy), (cx + int(clock_r * 0.72 * math.cos(fast_ang)), cy + int(clock_r * 0.72 * math.sin(fast_ang)))], fill=prim, width=5)
        draw.ellipse([(cx - 9, cy - 9), (cx + 9, cy + 9)], fill=white)

    # مشهد 7: الهاتف الذكي وحامل الهاتف (Smartphone Stand & Reels)
    elif scene_type == "reels_smartphone":
        ph_w, ph_h = int(r * 1.02), int(r * 1.65)
        px1, py1 = cx - ph_w // 2, cy - ph_h // 2
        px2, py2 = cx + ph_w // 2, cy + ph_h // 2
        # رجل تثبيت الهاتف (Support Stand) في الخلفية
        stand_offset = int(18 + 8 * math.sin(global_t * 4.0))
        draw.line([(px2, cy), (px2 + 45 + stand_offset, py2 - 12), (px2, py2 - 12)], fill=sec, width=6)
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=28, fill=(10, 16, 32, 245), outline=prim, width=4)
        scroll_offset = int(((global_t * 120) % 90) - 45)
        card_y = cy + scroll_offset
        draw.rounded_rectangle([(px1 + 14, card_y - int(ph_h * 0.25)), (px2 - 14, card_y + int(ph_h * 0.25))], radius=16, fill=(24, 38, 72, 235), outline=sec, width=3)
        draw.polygon([(cx - 14, card_y - 20), (cx - 14, card_y + 20), (cx + 22, card_y)], fill=prim)

    # مشهد 8: درع المتانة والمنتج الأصلي (Product Durability Shield & Stars)
    elif scene_type == "ecommerce_showcase":
        float_y = int(10 * math.sin(global_t * 4.5))
        box_s = int(r * 0.62)
        by_center = cy + float_y
        draw.regular_polygon((cx, by_center, int(r * 0.76)), n_sides=6, rotation=int(global_t * 20), fill=dark_panel, outline=prim)
        draw.ellipse([(cx - int(box_s * 0.6), by_center - int(box_s * 0.6)), (cx + int(box_s * 0.6), by_center + int(box_s * 0.6))], fill=sec)
        draw.line([(cx - 18, by_center), (cx - 4, by_center + 16), (cx + 22, by_center - 14)], fill=(10, 16, 30, 255), width=6)

    # مشهد 9: رادار وخريطة التوصيل السريع (Express Delivery Radar)
    elif scene_type == "delivery_express":
        map_w, map_h = int(r * 1.75), int(r * 1.25)
        mx1, my1 = cx - map_w // 2, cy - map_h // 2
        mx2, my2 = cx + map_w // 2, cy + map_h // 2
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=22, fill=dark_panel, outline=sec, width=4)
        p_start = (mx1 + 38, my2 - 38)
        p_mid = (cx, my1 + 32)
        p_end = (mx2 - 38, my2 - 42)
        route_pts = [
            (
                int((1 - (step / 20.0)) ** 2 * p_start[0] + 2 * (1 - (step / 20.0)) * (step / 20.0) * p_mid[0] + (step / 20.0) ** 2 * p_end[0]),
                int((1 - (step / 20.0)) ** 2 * p_start[1] + 2 * (1 - (step / 20.0)) * (step / 20.0) * p_mid[1] + (step / 20.0) ** 2 * p_end[1])
            )
            for step in range(21)
        ]
        draw.line(route_pts, fill=(255, 255, 255, 85), width=4)
        active_idx = max(2, int(len(route_pts) * ((global_t * 0.85) % 1.0)))
        draw.line(route_pts[:active_idx], fill=prim, width=6)
        cur_x, cur_y = route_pts[active_idx - 1]
        draw.ellipse([(cur_x - 14, cur_y - 14), (cur_x + 14, cur_y + 14)], fill=sec, outline=white, width=3)

    # مشهد 10: مخطط النمو الصاعد
    elif scene_type == "growth_analytics":
        chart_w, chart_h = int(r * 1.70), int(r * 1.30)
        cx1, cy1 = cx - chart_w // 2, cy - chart_h // 2
        cx2, cy2 = cx + chart_w // 2, cy + chart_h // 2
        draw.rounded_rectangle([(cx1, cy1), (cx2, cy2)], radius=20, fill=dark_panel, outline=(255, 255, 255, 80), width=3)
        num_bars = 4
        bar_space = (chart_w - 50) // num_bars
        bar_w = int(bar_space * 0.62)
        base_y = cy2 - 22
        max_bh = chart_h - 60
        for b_i, rat in enumerate([0.35, 0.55, 0.78, 1.0]):
            anim_p = _ease_out_back(min(1.0, max(0.1, scene_progress * 1.8 - b_i * 0.12)))
            bh = int(max_bh * rat * anim_p)
            bx = cx1 + 28 + b_i * bar_space
            draw.rounded_rectangle([(bx, base_y - bh), (bx + bar_w, base_y)], radius=8, fill=prim if b_i == 3 else sec)

    # مشهد 11: الختام ونداء الطلب
    else:
        for ring_i in range(3):
            rr = int(r * (0.45 + ring_i * 0.22 + 0.05 * math.sin(global_t * 6 + ring_i)))
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=prim if ring_i == 0 else sec, width=4)
        draw.regular_polygon((cx, cy, int(r * 0.45)), n_sides=6, rotation=int(global_t * 30), fill=dark_panel, outline=prim)
        draw.regular_polygon((cx, cy, int(r * 0.28)), n_sides=3, rotation=int(-global_t * 45), fill=sec, outline=white)


# ==============================================================================
# 5. محرك تراكب الموشن جرافيك والكابشن المتزامن إطاراً بإطار فوق الفيديو الأصلي!
# ==============================================================================
def render_live_video_motion_frame(
    base_frame_rgb: np.ndarray,
    t: float,
    total_duration: float,
    storyboard: List[Dict[str, Any]],
    words_data: List[Dict[str, Any]]
) -> np.ndarray:
    """
    يرسم الموشن جرافيك المتحرك والكابشن الكاريوكي مباشرة فوق إطار الفيديو الأصلي `base_frame_rgb` في اللحظة `t`:
    1. يحدد المشهد القصير النشط (`sc`) عند الثانية `t` (يتغير كل 1.4 - 1.9 ثانية!).
    2. يحرك بطاقة الموشن جرافيك العلوية (انزلاق زنبركي + رسمة تتحرك فعلياً في كل إطار `t` + تبديل الموقع والثيم في كل مشهد).
    3. يرسم شريط الكابشن الكاريوكي المتصل أسفل الفيديو، حيث تضيء وتكبر الكلمة المنطوقة حالياً ("يمشي سوا سوا" مع الصوت بدون اختفاء أو تقطيع).
    """
    h, w, _ = base_frame_rgb.shape
    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    if not storyboard:
        return base_frame_rgb

    # 1. تحديد المشهد القصير الحالي عند اللحظة t
    active_sc_idx = 0
    for idx, sc in enumerate(storyboard):
        if t >= sc["start"]:
            active_sc_idx = idx
        else:
            break

    sc = storyboard[active_sc_idx]
    sc_dur = max(0.18, sc["end"] - sc["start"])
    sc_prog = max(0.0, min(1.0, (t - sc["start"]) / sc_dur))
    theme = MOTION_THEMES.get(sc["theme_name"], MOTION_THEMES["cyber_gold"])

    # 2. تحريك بطاقة الموشن جرافيك العلوية (Animated Motion Graphics HUD Card)
    # دخول انسيابي خلال أول 0.22 ثانية من كل مشهد قصير
    slide_in = _ease_out_back(min(1.0, (t - sc["start"]) / 0.22)) if (t >= sc["start"]) else 1.0
    y_slide_offset = int(-140 * (1.0 - slide_in))

    icon_r = max(46, int(min(w, h) * 0.062))
    title_font = get_arabic_font(max(26, int(min(w, h) * 0.040)), bold=True)
    sub_badge_font = get_arabic_font(max(19, int(min(w, h) * 0.027)), bold=True)

    badge_title = sc.get("badge_label", sc.get("short_title", "ميزة حصرية"))
    short_sub = sc.get("short_title", "")

    tw, th = measure_arabic_text(draw, badge_title, title_font)
    card_w = min(int(w * 0.90), max(tw + icon_r * 2 + 75, int(w * 0.58)))
    card_h = icon_r * 2 + 30

    cx = w // 2
    # تناوب بسيط في موضع البطاقة العلوية بين المشاهد لكسر الجمود
    if active_sc_idx % 3 == 1:
        card_cx = max(card_w // 2 + 20, int(w * 0.54))
    elif active_sc_idx % 3 == 2:
        card_cx = min(w - card_w // 2 - 20, int(w * 0.46))
    else:
        card_cx = cx

    top_y = int(h * 0.055) + y_slide_offset
    x1, y1 = card_cx - card_w // 2, top_y
    x2, y2 = card_cx + card_w // 2, top_y + card_h

    # هالة مضيئة وخلفية زجاجية داكنة للبطاقة
    draw.rounded_rectangle([(x1 - 5, y1 - 5), (x2 + 5, y2 + 5)], radius=28, fill=(*theme["primary"], 60))
    draw.rounded_rectangle(
        [(x1, y1), (x2, y2)],
        radius=24,
        fill=(10, 16, 34, 232),
        outline=(*theme["primary"], 245),
        width=3
    )
    # شريط طاقة متحرك أسفل البطاقة يعبر عن تقدم المشهد
    prog_bar_w = int((card_w - 48) * min(1.0, max(0.05, sc_prog)))
    draw.rounded_rectangle([(x1 + 24, y2 - 9), (x1 + 24 + prog_bar_w, y2 - 4)], radius=3, fill=(*theme["secondary"], 255))

    # رسم المشهد المتحرك الحي داخل البطاقة (على اليمين)
    illus_cx = x2 - icon_r - 18
    illus_cy = y1 + card_h // 2
    draw_animated_scene_illustration(
        draw=draw,
        scene_type=sc["scene_type"],
        cx=illus_cx,
        cy=illus_cy,
        radius=int(icon_r * 0.86),
        scene_progress=sc_prog,
        global_t=t,
        theme=theme,
        target_number=sc.get("target_number", 58),
        short_title=short_sub
    )

    # رسم عنوان الفكرة والشارة النصية داخل البطاقة
    text_area_cx = x1 + (illus_cx - icon_r - x1) // 2
    draw_arabic_text(
        draw,
        (text_area_cx, y1 + int(card_h * 0.40)),
        badge_title,
        font=title_font,
        fill=(*theme["primary"], 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220)
    )
    if short_sub and short_sub != badge_title:
        draw_arabic_text(
            draw,
            (text_area_cx, y1 + int(card_h * 0.75)),
            short_sub,
            font=sub_badge_font,
            fill=(235, 245, 255, 235)
        )

    # 3. شريط الكابشن الكاريوكي المتزامن في الثلث السفلي ("يمشي سوا سوا مع الكلام")
    sc_words = sc.get("words", [])
    act_word_str = ""
    w_local_prog = 0.5

    for wi, w_obj in enumerate(sc_words):
        ws = float(w_obj["start"])
        we = float(sc_words[wi + 1]["start"]) if (wi + 1 < len(sc_words)) else float(w_obj["end"])
        if t >= ws - 0.04:
            act_word_str = w_obj["word"]
            wdur = max(0.10, we - ws)
            w_local_prog = max(0.0, min(1.0, (t - ws) / wdur))

    if not act_word_str and sc_words:
        act_word_str = sc_words[0]["word"]

    if act_word_str:
        # أ) البطاقة البارزة للكلمة المنطوقة حالياً بفيزياء زنبركية (Active Spoken Word Pop)
        pop_scale = _ease_out_back(min(1.0, w_local_prog * 3.0))
        base_cap_size = max(42, int(min(w, h) * 0.068))
        act_font_size = max(34, int(base_cap_size * (0.85 + 0.18 * pop_scale)))
        act_font = get_arabic_font(act_font_size, bold=True)

        cap_y = int(h * 0.72)
        cw, ch = measure_arabic_text(draw, act_word_str, act_font)
        pad_x = max(34, int(act_font_size * 0.58))
        pad_y = max(18, int(act_font_size * 0.34))

        wx1, wy1 = cx - cw // 2 - pad_x, cap_y - ch // 2 - pad_y
        wx2, wy2 = cx + cw // 2 + pad_x, cap_y + ch // 2 + pad_y

        draw.rounded_rectangle([(wx1 - 5, wy1 - 5), (wx2 + 5, wy2 + 5)], radius=24, fill=(*theme["primary"], 65))
        draw.rounded_rectangle(
            [(wx1, wy1), (wx2, wy2)],
            radius=20,
            fill=(10, 15, 30, 235),
            outline=(*theme["primary"], 255),
            width=4
        )
        draw_arabic_text(
            draw,
            (cx, cap_y),
            act_word_str,
            font=act_font,
            fill=(*theme["primary"], 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 240)
        )

        # ب) شريط العبارة الكاملة للمشهد أسفل الكلمة النشطة مباشرة لمنع أي تقطع في القراءة
        phrase_str = sc.get("text", "")
        if phrase_str and len(sc_words) > 1:
            p_font = get_arabic_font(max(26, int(base_cap_size * 0.48)), bold=True)
            pw, ph = measure_arabic_text(draw, phrase_str, p_font)
            sub_y = wy2 + ph // 2 + 22
            p_bar_w = min(int(w * 0.92), pw + 48)
            draw.rounded_rectangle(
                [(cx - p_bar_w // 2, sub_y - ph // 2 - 12), (cx + p_bar_w // 2, sub_y + ph // 2 + 12)],
                radius=16,
                fill=(8, 12, 24, 215),
                outline=(*theme["secondary"], 180),
                width=2
            )
            draw_arabic_text(
                draw,
                (cx, sub_y),
                phrase_str,
                font=p_font,
                fill=(255, 255, 255, 250),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 200)
            )

    # 4. وميض انتقالي سينمائي ناعم عند بداية كل مشهد جديد (Shot Transition Accent)
    if active_sc_idx > 0 and 0.0 <= (t - sc["start"]) < 0.16:
        flash_alpha = int(160 * (1.0 - (t - sc["start"]) / 0.16))
        draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=24, outline=(*theme["primary"], flash_alpha), width=10)

    return np.array(img.convert("RGB"))


# ==============================================================================
# 6. تصيير المشهد الكامل لوضع الموشن جرافيك الصافي (Full-Screen Motion Canvas)
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
    """رسم إطار كامل (1080x1920) لمشهد موشن جرافيك مستقل."""
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
        out.paste(prev_img, (-int(w * p), 0))
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
        draw = ImageDraw.Draw(out, "RGBA")
        draw.rounded_rectangle([(paste_x, paste_y), (paste_x + zw, paste_y + zh)], radius=24, outline=(255, 220, 0, int(255 * (1.0 - p))), width=6)
        return out

    else:
        return Image.blend(prev_img, curr_img, p)


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


def draw_procedural_vector_icon(
    icon_type: str,
    size: int = 140,
    accent_color: Tuple[int, int, int] = (255, 225, 0),
    secondary_color: Tuple[int, int, int] = (0, 245, 212)
) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    theme = {"primary": accent_color, "secondary": secondary_color, "accent": secondary_color, "glow": accent_color}
    scene_map = {
        "money": "growth_analytics",
        "time": "time_warp_clock",
        "idea": "ai_neural_brain",
        "code": "platform_builder",
        "question": "video_montage_studio",
        "warning": "hook_energy_burst",
        "success": "ecommerce_showcase"
    }
    draw_animated_scene_illustration(
        draw=draw,
        scene_type=scene_map.get(icon_type, "ai_neural_brain"),
        cx=size // 2,
        cy=size // 2,
        radius=int(size * 0.44),
        scene_progress=0.85,
        global_t=1.2,
        theme=theme
    )
    return img


def analyze_sentence_visual_metadata(
    sentence: str,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, str]:
    bp = classify_micro_scene_blueprint(sentence, 0, 10)
    return {
        "keyword": bp["short_title"],
        "icon_type": "success",
        "scene_type": bp["scene_type"]
    }


def render_video_motion_overlay_card(
    keyword_title: str,
    icon_type: str,
    video_width: int,
    video_height: int,
    mode: str = "corner_card",
    subtitle_line: str = "",
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    title_font_size = max(28, int(min(video_width, video_height) * 0.044))
    title_font = get_arabic_font(title_font_size, bold=True)

    icon_size = max(92, int(min(video_width, video_height) * 0.115))
    icon_img = draw_procedural_vector_icon(icon_type=icon_type, size=icon_size, accent_color=theme["primary"], secondary_color=theme["secondary"])

    tw, th = measure_arabic_text(draw, keyword_title, title_font)
    card_w = min(int(video_width * 0.88), max(tw + icon_size + 85, int(video_width * 0.54)))
    card_h = icon_size + 36
    cx = video_width // 2
    top_y = int(video_height * 0.075)

    x1, y1 = cx - card_w // 2, top_y
    x2, y2 = cx + card_w // 2, top_y + card_h

    draw.rounded_rectangle([(x1 - 5, y1 - 5), (x2 + 5, y2 + 5)], radius=28, fill=(*theme["primary"], 55))
    draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=24, fill=(11, 17, 34, 232), outline=(*theme["primary"], 245), width=3)

    icon_x = x2 - icon_size - 18
    icon_y = y1 + (card_h - icon_size) // 2
    canvas.paste(icon_img, (icon_x, icon_y), icon_img)

    text_center_x = x1 + (icon_x - x1) // 2
    text_center_y = y1 + card_h // 2
    draw_arabic_text(draw, (text_center_x, text_center_y), keyword_title, font=title_font, fill=(*theme["primary"], 255))

    return np.array(canvas)


def render_ecommerce_ad_overlay(
    ad_role: str,
    badge_title: str,
    icon_cat: str,
    video_width: int,
    video_height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    return render_video_motion_overlay_card(
        keyword_title=badge_title,
        icon_type=icon_cat,
        video_width=video_width,
        video_height=video_height,
        theme_name=theme_name
    )


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
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """إنشاء فيديو موشن جرافيك كامل ومتحرك إطاراً بإطار."""
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
        update_progress(0.10, "1/4: قراءة الصوت وتفريغ الدارجة الجزائرية والعربية بدقة...")
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

        update_progress(0.28, "2/4: بناء القصة البصرية وتوليد مشهد موشن جرافيك جديد لكل 1.5 ثانية...")
        micro_scenes = split_words_into_micro_scenes(words_data, max_words_per_scene=4, max_duration_per_scene=1.9)

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

        update_progress(0.65, f"4/4: رندرة {len(storyboard)} مشهد موشن جرافيك متحرك مع الانتقالات البصرية...")
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
