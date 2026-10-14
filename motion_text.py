"""
motion_text.py - محرك الموشن جرافيك الكامل والمتحرك إطاراً بإطار (Full-Screen Scene-by-Scene Motion Graphics Engine)
====================================================================================================================
يقوم هذا المحرك بتحويل أي صوت أو فيديو إلى عمل موشن جرافيك سينمائي متكامل:
1. تقسيم الفيديو تلقائياً إلى مشاهد قصيرة متجددة كل 1.5 إلى 2.1 ثانية (Micro-Scenes) بدلاً من بقاء رسمة ثابتة.
2. توليد 11+ مشهد رسومي كامل ومتحرك (Full-Screen Animated Illustrations) يتغير كل ثانية أو ثانيتين حسب معنى الكلام:
   - مشهد بناء منصة/واجهة (Platform UI Builder)
   - مشهد أستوديو وشريط المونتاج المتحرك (Video Timeline & Playhead Studio)
   - مشهد شبكة الذكاء الاصطناعي العصبية (AI Neural Brain & Synapses)
   - مشهد هاتف الريلز والتيك توك المتفاعل (3D Smartphone Reels & Likes Feed)
   - مشهد عداد الأرقام والإحصائيات المتصاعد (Animated Digital Counter 0 -> N)
   - مشهد الساعة والمؤقت السريع (High-Speed Chronometer & Time Gauge)
   - مشهد البطاقة التعريفية للمتحدث (Creator Holo-ID Badge)
   - مشهد استعراض المنتجات والتجارة الإلكترونية (Product Hologram Pedestal & 5-Star Rating)
   - مشهد خريطة التوصيل السريع (GPS Radar & Delivery Route)
   - مشهد مخطط النمو الصاعد (Rising 3D Bar Chart & Trend Line)
   - مشهد الإعلان الختامي وإبراز الهوية (Cinematic Brand Spotlight Finale)
3. انتقالات كاميرا سينمائية حقيقية بين كل لقطة وأخرى (Whip-Pan Slide, Vertical Swipe, Zoom Portal, Laser Wipe).
4. فيزياء زنبركية (Spring Pop-in) للكلمات + موجات صوتية متفاعلة لحظياً مع تردد الصوت الفعلي.
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
    """رسم نص عربي أو إنجليزي بدقة عالية."""
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
    """جلب أفضل خط عربي متوفر مع تخزينه في الذاكرة لتسريع الرندرة إطاراً بإطار."""
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
# 2. الثيمات اللونية المتعددة للمشاهد (6 ثيمات أستوديو سينمائية متباينة)
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
# 3. مصنف المشاهد الذكي (يختار مشهداً رسومياً مخصصاً لكل 1.5 - 2 ثانية)
# ==============================================================================
SCENE_TYPES_LIST = [
    "creator_profile",
    "age_number_counter",
    "platform_builder",
    "video_montage_studio",
    "ai_neural_brain",
    "time_warp_clock",
    "reels_smartphone",
    "ecommerce_showcase",
    "delivery_express",
    "growth_analytics",
    "brand_finale"
]


def classify_micro_scene_blueprint(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    prev_scene_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    تحديد نوع المشهد الرسومي المتكامل (Scene Blueprint) وعنوانه بناءً على الكلمات المنطوقة
    في هذه الثانية أو الثانيتين، مع ضمان عدم تكرار نفس المشهد مرتين متتاليتين!
    """
    t = scene_text.strip()
    t_low = t.lower()

    # استخراج أي رقم موجود في النص (مثل 17، 58، 100...)
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
    elif extracted_number is not None or any(w in t_low for w in ["عمري", "عمره", "سنة", "سنين", "مئة", "ألف", "مليون"]):
        chosen_type = "age_number_counter"
        badge_label = f"محطة الإنجاز - {extracted_number or 17}"
    elif any(w in t_low for w in ["وقت", "ساعة", "ما عندها", "مشغولة", "تأخير", "سرعة", "ثواني"]):
        chosen_type = "time_warp_clock"
        badge_label = "توفير الوقت والسرعة"
    elif any(w in t_low for w in ["أهلاً", "اهلا", "سلام", "أنا", "أنس", "اناس", "اسمي", "مرحبا", "خاوتي"]):
        chosen_type = "creator_profile"
        badge_label = "بطاقة تعريف المبدع"
    elif any(w in t_low for w in ["توصيل", "ولاية", "58", "باب الدار", "شحن"]):
        chosen_type = "delivery_express"
        badge_label = "توصيل سريع 58 ولاية"
    elif any(w in t_low for w in ["منتج", "سلعة", "جودة", "أصلي", "عفسة", "اطلب", "شراء"]):
        chosen_type = "ecommerce_showcase"
        badge_label = "استعراض المنتج الأصلي"
    elif any(w in t_low for w in ["أغلب", "الناس", "مال", "ربح", "دراهم", "سعر", "سومة", "تخفيض", "نجاح", "كل يوم"]):
        chosen_type = "growth_analytics"
        badge_label = "مؤشر النمو والانتشار"
    elif scene_index == total_scenes - 1:
        chosen_type = "brand_finale"
        badge_label = "الإطلاق الرسمي للمنصة"

    # إذا لم يطابق أو كان نفس المشهد السابق تماماً، نختار مشهداً مكملاً مختلفاً لضمان التجدد البصري كل ثانية!
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

    # استخراج عنوان مختصر (كلمتين) من نص المشهد
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
# 4. رسام المشاهد الرسومية الكاملة والمتحركة إطاراً بإطار (Full-Screen Scene Artists)
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
    """
    رسم مشهد موشن جرافيك كبير ومتحرك بالكامل في النصف العلوي من الشاشة (بمساحة ~650x650 بكسل)
    يتفاعل لحظياً مع الزمن global_t وتقدم المشهد scene_progress!
    """
    prim = (*theme["primary"], 255)
    sec = (*theme["secondary"], 255)
    acc = (*theme["accent"], 240)
    white = (255, 255, 255, 255)
    dark_panel = (12, 19, 38, 230)

    enter_scale = _ease_out_back(min(1.0, scene_progress * 2.8))
    r = int(radius * max(0.2, enter_scale))

    # خلفية هالة مدارية متحركة لكل المشاهد
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

    # -------------------------------------------------------------------------
    # مشهد 1: بطاقة الهوية والمبدع المتحركة (Creator Profile Holo-Card)
    # -------------------------------------------------------------------------
    if scene_type == "creator_profile":
        card_w, card_h = int(r * 1.75), int(r * 1.35)
        x1, y1 = cx - card_w // 2, cy - card_h // 2
        x2, y2 = cx + card_w // 2, cy + card_h // 2

        draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=32, fill=dark_panel, outline=prim, width=4)
        # شريط علوي للنوافذ
        draw.rounded_rectangle([(x1 + 20, y1 + 18), (x2 - 20, y1 + 52)], radius=12, fill=(25, 38, 68, 220))
        for idx, dot_c in enumerate([(239, 68, 68, 255), (250, 204, 21, 255), (52, 211, 153, 255)]):
            dx = x1 + 42 + idx * 24
            draw.ellipse([(dx - 7, y1 + 35 - 7), (dx + 7, y1 + 35 + 7)], fill=dot_c)

        # دائرة الأفاتار النابضة في المنتصف
        av_r = int(r * 0.36)
        av_y = cy - int(r * 0.06)
        pulse = int(8 * math.sin(global_t * 6.0))
        draw.ellipse([(cx - av_r - pulse, av_y - av_r - pulse), (cx + av_r + pulse, av_y + av_r + pulse)], outline=sec, width=3)
        draw.ellipse([(cx - av_r, av_y - av_r), (cx + av_r, av_y + av_r)], fill=(28, 45, 82, 255), outline=prim, width=5)
        # رأس وكتفي المتحدث داخل الأفاتار
        head_r = int(av_r * 0.34)
        draw.ellipse([(cx - head_r, av_y - int(av_r * 0.45) - head_r), (cx + head_r, av_y - int(av_r * 0.45) + head_r)], fill=prim)
        draw.pieslice(
            [(cx - int(av_r * 0.62), av_y + int(av_r * 0.05)), (cx + int(av_r * 0.62), av_y + int(av_r * 0.95))],
            start=180, end=360, fill=sec
        )
        # شارة توثيق خضراء/ذهبية متحركة
        bx, by = cx + int(av_r * 0.72), av_y + int(av_r * 0.65)
        draw.ellipse([(bx - 22, by - 22), (bx + 22, by + 22)], fill=(16, 185, 129, 255), outline=white, width=3)
        draw.line([(bx - 10, by), (bx - 2, by + 9), (bx + 12, by - 8)], fill=white, width=4)

        # أشرطة بيانات هولوغرافية أسفل الأفاتار
        bar_y = y2 - 48
        bar_w = int(card_w * 0.55 * min(1.0, scene_progress * 1.8))
        draw.rounded_rectangle([(cx - bar_w // 2, bar_y - 10), (cx + bar_w // 2, bar_y + 10)], radius=10, fill=prim)

    # -------------------------------------------------------------------------
    # مشهد 2: عداد الأرقام والسنين الديناميكي (Animated Number Counter 0 -> N)
    # -------------------------------------------------------------------------
    elif scene_type == "age_number_counter":
        # عداد رقمي يصعد من 0 إلى الرقم المستهدف (مثل 17)
        count_progress = _ease_out_cubic(min(1.0, scene_progress * 1.6))
        current_val = max(1, int(round(target_number * count_progress)))

        # حلقة عداد السرعة (Tachometer Gauge)
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

        # رسم الرقم العملاق في المنتصف
        num_font = get_arabic_font(int(r * 0.72), bold=True)
        draw_arabic_text(
            draw, (cx, cy - 10), str(current_val),
            font=num_font, fill=prim, stroke_width=4, stroke_fill=(0, 0, 0, 240)
        )
        # اشعاعات احتفالية حول الحلقة
        for i in range(12):
            ang = math.radians(i * 30 + global_t * 40)
            x1 = cx + int((gauge_r + 12) * math.cos(ang))
            y1 = cy + int((gauge_r + 12) * math.sin(ang))
            x2 = cx + int((gauge_r + 32) * math.cos(ang))
            y2 = cy + int((gauge_r + 32) * math.sin(ang))
            draw.line([(x1, y1), (x2, y2)], fill=sec if i % 2 == 0 else prim, width=4)

    # -------------------------------------------------------------------------
    # مشهد 3: بناء المنصة والواجهة الذكية (Platform UI Dashboard Builder)
    # -------------------------------------------------------------------------
    elif scene_type == "platform_builder":
        win_w, win_h = int(r * 1.85), int(r * 1.40)
        wx1, wy1 = cx - win_w // 2, cy - win_h // 2
        wx2, wy2 = cx + win_w // 2, cy + win_h // 2

        draw.rounded_rectangle([(wx1, wy1), (wx2, wy2)], radius=24, fill=dark_panel, outline=sec, width=4)
        # شريط عنوان المتصفح
        draw.rounded_rectangle([(wx1, wy1), (wx2, wy1 + 48)], radius=24, fill=(22, 34, 64, 255), outline=sec, width=2)
        for i, col in enumerate([(239, 68, 68, 255), (250, 204, 21, 255), (52, 211, 153, 255)]):
            draw.ellipse([(wx1 + 24 + i * 22, wy1 + 18), (wx1 + 36 + i * 22, wy1 + 30)], fill=col)

        # بطاقات واجهة المستخدم (UI Blocks) تتركب وتتحرك تدريجياً
        pad = 22
        body_y1 = wy1 + 64
        # لوحة جانبية
        sb_w = int((win_w - 3 * pad) * 0.30)
        draw.rounded_rectangle([(wx1 + pad, body_y1), (wx1 + pad + sb_w, wy2 - pad)], radius=14, fill=(20, 32, 58, 230), outline=(255, 255, 255, 60), width=2)
        for row in range(4):
            ry = body_y1 + 20 + row * 42
            rw = int((sb_w - 24) * min(1.0, max(0.2, scene_progress * 2.0 - row * 0.2)))
            if ry + 18 < wy2 - pad:
                draw.rounded_rectangle([(wx1 + pad + 12, ry), (wx1 + pad + 12 + rw, ry + 16)], radius=6, fill=sec if row == 0 else (148, 163, 184, 180))

        # منطقة العمل الرئيسية: 3 بطاقات متحركة + ترس بناء يدور
        main_x1 = wx1 + 2 * pad + sb_w
        main_w = wx2 - pad - main_x1
        card_h_top = int((wy2 - pad - body_y1) * 0.48)
        draw.rounded_rectangle([(main_x1, body_y1), (main_x1 + main_w, body_y1 + card_h_top)], radius=14, fill=(28, 42, 78, 235), outline=prim, width=3)

        # رسم موجات/خطوط بناء داخل البطاقة العلوية
        pts = []
        for step_i in range(8):
            px = main_x1 + 18 + int((main_w - 36) * (step_i / 7.0))
            py = body_y1 + card_h_top // 2 + int(24 * math.sin(global_t * 5.0 + step_i * 0.9))
            pts.append((px, py))
        if len(pts) >= 2:
            draw.line(pts, fill=prim, width=5)

        # بطاقتان سفليتان
        bot_y1 = body_y1 + card_h_top + 16
        half_w = (main_w - 16) // 2
        draw.rounded_rectangle([(main_x1, bot_y1), (main_x1 + half_w, wy2 - pad)], radius=14, fill=(22, 36, 68, 230), outline=acc, width=2)
        draw.rounded_rectangle([(main_x1 + half_w + 16, bot_y1), (main_x1 + main_w, wy2 - pad)], radius=14, fill=(22, 36, 68, 230), outline=sec, width=2)

        # ترس هندسي يدور في الزاوية
        gx, gy = wx2 - 36, wy1 + 24
        for tooth in range(8):
            ang = math.radians(tooth * 45 + global_t * 120)
            tx1 = gx + int(10 * math.cos(ang))
            ty1 = gy + int(10 * math.sin(ang))
            tx2 = gx + int(22 * math.cos(ang))
            ty2 = gy + int(22 * math.sin(ang))
            draw.line([(tx1, ty1), (tx2, ty2)], fill=prim, width=5)

    # -------------------------------------------------------------------------
    # مشهد 4: أستوديو وشريط المونتاج المتحرك (Video Editing Timeline Studio)
    # -------------------------------------------------------------------------
    elif scene_type == "video_montage_studio":
        studio_w, studio_h = int(r * 1.90), int(r * 1.45)
        sx1, sy1 = cx - studio_w // 2, cy - studio_h // 2
        sx2, sy2 = cx + studio_w // 2, cy + studio_h // 2

        draw.rounded_rectangle([(sx1, sy1), (sx2, sy2)], radius=26, fill=dark_panel, outline=prim, width=4)

        # شاشة معاينة الفيديو في النصف العلوي مع زر Play نابض
        mon_h = int(studio_h * 0.50)
        mx1, my1 = sx1 + 24, sy1 + 22
        mx2, my2 = sx2 - 24, sy1 + 22 + mon_h
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=16, fill=(18, 28, 54, 255), outline=sec, width=3)

        # مثلث التشغيل (Play Prism) في وسط شاشة المعاينة
        mcx, mcy = (mx1 + mx2) // 2, (my1 + my2) // 2
        pr_s = int(28 + 5 * math.sin(global_t * 7.0))
        draw.polygon([(mcx - pr_s // 2, mcy - pr_s), (mcx - pr_s // 2, mcy + pr_s), (mcx + pr_s, mcy)], fill=prim, outline=white)

        # مسارات المونتاج الثلاثة (Multi-Track Timeline) في النصف السفلي
        tl_y1 = my2 + 22
        track_h = max(22, int((sy2 - tl_y1 - 36) / 3))
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

        # إبرة التشغيل الحمراء/الذهبية المتحركة (Moving Playhead) تعبر التايم لاين!
        playhead_ratio = (scene_progress * 1.15) % 1.0
        px = int(mx1 + 16 + (mx2 - mx1 - 32) * playhead_ratio)
        draw.line([(px, tl_y1 - 10), (px, sy2 - 14)], fill=(255, 60, 80, 255), width=5)
        draw.polygon([(px - 10, tl_y1 - 12), (px + 10, tl_y1 - 12), (px, tl_y1 + 2)], fill=(255, 220, 0, 255))

    # -------------------------------------------------------------------------
    # مشهد 5: شبكة الذكاء الاصطناعي العصبية (AI Neural Brain & Synapses)
    # -------------------------------------------------------------------------
    elif scene_type == "ai_neural_brain":
        # عقد ذكاء اصطناعي متصلة مع نبضات ضوئية تسري بين الخطوط لحظياً
        node_positions = []
        num_outer = 8
        outer_r = int(r * 0.85)
        inner_r = int(r * 0.42)
        for i in range(num_outer):
            ang = math.radians(i * (360 / num_outer) + global_t * 25)
            nx = cx + int(outer_r * math.cos(ang))
            ny = cy + int(outer_r * math.sin(ang))
            node_positions.append((nx, ny))
        for i in range(4):
            ang = math.radians(i * 90 - global_t * 35)
            nx = cx + int(inner_r * math.cos(ang))
            ny = cy + int(inner_r * math.sin(ang))
            node_positions.append((nx, ny))
        node_positions.append((cx, cy))

        # رسم الروابط والنبضات المسافرة (Data Pulses)
        pulse_pos = (global_t * 1.8) % 1.0
        for i in range(len(node_positions)):
            for j in range(i + 1, len(node_positions)):
                x1, y1 = node_positions[i]
                x2, y2 = node_positions[j]
                dist = math.hypot(x2 - x1, y2 - y1)
                if dist < r * 0.98:
                    draw.line([(x1, y1), (x2, y2)], fill=(*theme["secondary"], 95), width=3)
                    # نبضة البيانات المتحركة على طول الرابط
                    if (i + j) % 2 == 0:
                        px = int(x1 + (x2 - x1) * pulse_pos)
                        py = int(y1 + (y2 - y1) * pulse_pos)
                        draw.ellipse([(px - 6, py - 6), (px + 6, py + 6)], fill=prim)

        # رسم العقد المضيئة والنواة المركزية
        for idx, (nx, ny) in enumerate(node_positions):
            nr = 28 if idx == len(node_positions) - 1 else 15
            ncol = prim if idx % 2 == 0 else sec
            draw.ellipse([(nx - nr - 5, ny - nr - 5), (nx + nr + 5, ny + nr + 5)], fill=(ncol[0], ncol[1], ncol[2], 65))
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=dark_panel, outline=ncol, width=4)

        ai_font = get_arabic_font(int(r * 0.22), bold=True)
        draw_arabic_text(draw, (cx, cy), "ذكاء", font=ai_font, fill=prim)

    # -------------------------------------------------------------------------
    # مشهد 6: الساعة والمؤقت السريع (High-Speed Time Warp Chronometer)
    # -------------------------------------------------------------------------
    elif scene_type == "time_warp_clock":
        clock_r = int(r * 0.86)
        draw.ellipse([(cx - clock_r, cy - clock_r), (cx + clock_r, cy + clock_r)], fill=dark_panel, outline=prim, width=6)

        # علامات الساعات الـ 12
        for h_i in range(12):
            ang = math.radians(h_i * 30 - 90)
            x1 = cx + int((clock_r - 24) * math.cos(ang))
            y1 = cy + int((clock_r - 24) * math.sin(ang))
            x2 = cx + int((clock_r - 8) * math.cos(ang))
            y2 = cy + int((clock_r - 8) * math.sin(ang))
            draw.line([(x1, y1), (x2, y2)], fill=sec if h_i % 3 == 0 else white, width=5 if h_i % 3 == 0 else 2)

        # عقارب الساعة تدور بسرعة ديناميكية لتعبر عن ضيق الوقت والسرعة
        fast_ang = math.radians(global_t * 360 - 90)
        slow_ang = math.radians(global_t * 60 - 90)
        draw.line(
            [(cx, cy), (cx + int(clock_r * 0.52 * math.cos(slow_ang)), cy + int(clock_r * 0.52 * math.sin(slow_ang)))],
            fill=sec, width=8
        )
        draw.line(
            [(cx, cy), (cx + int(clock_r * 0.74 * math.cos(fast_ang)), cy + int(clock_r * 0.74 * math.sin(fast_ang)))],
            fill=prim, width=6
        )
        draw.ellipse([(cx - 12, cy - 12), (cx + 12, cy + 12)], fill=white)

    # -------------------------------------------------------------------------
    # مشهد 7: هاتف الريلز والتيك توك والتفاعل (3D Smartphone Reels Feed)
    # -------------------------------------------------------------------------
    elif scene_type == "reels_smartphone":
        ph_w, ph_h = int(r * 1.05), int(r * 1.72)
        px1, py1 = cx - ph_w // 2, cy - ph_h // 2
        px2, py2 = cx + ph_w // 2, cy + ph_h // 2

        # جسم الهاتف الذكي مع حواف مضيئة
        draw.rounded_rectangle([(px1 - 6, py1 - 6), (px2 + 6, py2 + 6)], radius=38, fill=(*theme["primary"], 55))
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=34, fill=(10, 16, 32, 245), outline=prim, width=5)
        # نوتش الكاميرا العلوية
        draw.rounded_rectangle([(cx - 38, py1 + 14), (cx + 38, py1 + 26)], radius=6, fill=(40, 50, 75, 255))

        # بطاقة ريلز تنزلق للأعلى داخل شاشة الهاتف (Scrolling Reels Effect)
        scroll_offset = int(((global_t * 140) % 120) - 60)
        card_y = cy + scroll_offset
        draw.rounded_rectangle(
            [(px1 + 18, card_y - int(ph_h * 0.28)), (px2 - 18, card_y + int(ph_h * 0.28))],
            radius=20, fill=(24, 38, 72, 235), outline=sec, width=3
        )
        # زر تشغيل الريلز
        draw.polygon(
            [(cx - 18, card_y - 26), (cx - 18, card_y + 26), (cx + 28, card_y)],
            fill=prim
        )

        # أيقونات تفاعل وإعجابات (Floating Likes & Views) تصعد على جانب الهاتف
        for k in range(4):
            fy = py2 - 40 - int(((global_t * 180 + k * 95) % (ph_h - 60)))
            fx = px2 + 34 + int(14 * math.sin(global_t * 5 + k))
            b_col = (244, 63, 94, 240) if k % 2 == 0 else prim
            draw.ellipse([(fx - 18, fy - 18), (fx + 18, fy + 18)], fill=b_col, outline=white, width=2)

    # -------------------------------------------------------------------------
    # مشهد 8: استعراض المنتج والنجوم الخمس (E-Commerce Product Showcase)
    # -------------------------------------------------------------------------
    elif scene_type == "ecommerce_showcase":
        # منصة هولوغرام ثلاثية الأبعاد مع مكعب/صندوق منتج يطفو للأعلى والأسفل
        float_y = int(14 * math.sin(global_t * 4.5))
        ped_y = cy + int(r * 0.52)
        draw.ellipse([(cx - int(r * 0.75), ped_y - 28), (cx + int(r * 0.75), ped_y + 28)], fill=(*theme["secondary"], 85), outline=sec, width=4)
        draw.ellipse([(cx - int(r * 0.50), ped_y - 16), (cx + int(r * 0.50), ped_y + 16)], fill=(*theme["primary"], 140))

        # بطاقة المنتج الفاخرة الطافية
        box_s = int(r * 0.62)
        by_center = cy - int(r * 0.12) + float_y
        draw.rounded_rectangle(
            [(cx - box_s, by_center - box_s), (cx + box_s, by_center + box_s)],
            radius=28, fill=dark_panel, outline=prim, width=5
        )
        # 5 نجوم ذهبية تظهر بالتتابع أعلى المنتج
        num_stars = min(5, max(1, int(scene_progress * 7)))
        star_y = by_center - box_s - 34
        for s_i in range(num_stars):
            sx = cx - 100 + s_i * 50
            draw.regular_polygon((sx, star_y, 18), n_sides=5, rotation=int(global_t * 30), fill=prim, outline=white)

        # علامة الجودة الأصلي داخل الصندوق
        draw.ellipse([(cx - 42, by_center - 42), (cx + 42, by_center + 42)], fill=sec)
        draw.line([(cx - 20, by_center), (cx - 4, by_center + 18), (cx + 24, by_center - 16)], fill=(10, 16, 30, 255), width=7)

    # -------------------------------------------------------------------------
    # مشهد 9: خريطة ورادار التوصيل السريع (Express Delivery Radar & Route)
    # -------------------------------------------------------------------------
    elif scene_type == "delivery_express":
        map_w, map_h = int(r * 1.80), int(r * 1.30)
        mx1, my1 = cx - map_w // 2, cy - map_h // 2
        mx2, my2 = cx + map_w // 2, cy + map_h // 2
        draw.rounded_rectangle([(mx1, my1), (mx2, my2)], radius=26, fill=dark_panel, outline=sec, width=4)

        # مسار التوصيل المنحني من النقطة A إلى النقطة B
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

        # الجزء المقطوع من المسار يتحرك مع تقدم المشهد
        active_idx = max(2, int(len(route_pts) * min(1.0, scene_progress * 1.35)))
        draw.line(route_pts[:active_idx], fill=prim, width=8)
        cur_x, cur_y = route_pts[active_idx - 1]
        draw.ellipse([(cur_x - 20, cur_y - 20), (cur_x + 20, cur_y + 20)], fill=sec, outline=white, width=4)
        draw.ellipse([(p_end[0] - 16, p_end[1] - 16), (p_end[0] + 16, p_end[1] + 16)], fill=prim, outline=white, width=3)

    # -------------------------------------------------------------------------
    # مشهد 10: مخطط النمو والإحصائيات الصاعدة (Rising 3D Bar Chart & Trend)
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # مشهد 11: الختام وإبراز اسم المنصة أو العلامة (Brand Spotlight Finale)
    # -------------------------------------------------------------------------
    else:
        for ring_i in range(3):
            rr = int(r * (0.45 + ring_i * 0.24 + 0.05 * math.sin(global_t * 5 + ring_i)))
            col = prim if ring_i == 0 else (sec if ring_i == 1 else acc)
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=col, width=5 - ring_i)

        # درع نجمي سداسي مضيء في المركز
        draw.regular_polygon((cx, cy, int(r * 0.48)), n_sides=6, rotation=int(global_t * 25), fill=dark_panel, outline=prim)
        draw.regular_polygon((cx, cy, int(r * 0.32)), n_sides=3, rotation=int(-global_t * 40), fill=sec, outline=white)


# ==============================================================================
# 5. تصيير المشهد الكامل مع الكلمات الزنبركية والموجات الصوتية (Full Scene Frame)
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
    """
    رسم إطار كامل (1080x1920) لمشهد واحد في اللحظة global_t:
    - الخلفية المتحركة + الجزيئات المضيئة
    - الشارة العلوية للمشهد
    - الرسمة التفاعلية الكبرى في النصف العلوي (تتغير كل 1.5 - 2 ثانية)
    - بطاقة الكلمة النشطة بفيزياء زنبركية (Spring Pop-in) + شريط كلمات المشهد (Karaoke Pills)
    - معادل الموجات الصوتية (Audio Equalizer) المتفاعل مع الصوت أسفل الشاشة.
    """
    theme_name = scene_meta["theme_name"]
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])

    # نسخ الخلفية المخزنة مسبقاً
    base_bg = bg_cache[theme_name]
    img = Image.fromarray(base_bg, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    cx = width // 2

    # 1. جزيئات مضيئة تسبح في الخلفية باستمرار (Floating Particles)
    for p_i in range(10):
        px = int((width * (0.12 + 0.76 * ((p_i * 37) % 10) / 10.0) + 35 * math.sin(global_t * 1.5 + p_i)) % width)
        py = int((height * (0.85 - ((global_t * 65 + p_i * 180) % height) / float(height))) % height)
        pr = 4 + (p_i % 4) * 2
        draw.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(*theme["secondary"], 55))

    # 2. الشارة العلوية للمشهد (Top Scene Header Pill)
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

    # 3. الرسمة التفاعلية الكبرى في النصف العلوي من الشاشة (تملأ المساحة البصرية!)
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

    # 4. بطاقة الكلمة النشطة بفيزياء زنبركية (Spring Pop-in Word Card)
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

    # هالة مضيئة حول الكلمة النشطة
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

    # 5. شريط كلمات المشهد الكامل أسفل البطاقة (Karaoke Scene Phrase Bar)
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

    # 6. معادل الموجات الصوتية المتفاعل لحظياً مع الصوت (Real-Time Audio Spectrum Equalizer)
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

    # 7. شريط التقدم الزمني السفلي
    prog_ratio = min(1.0, max(0.01, global_t / max(0.1, total_duration)))
    bar_margin = int(width * 0.10)
    bar_y = height - 48
    full_w = width - 2 * bar_margin
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + full_w, bar_y + 10)], radius=5, fill=(255, 255, 255, 45))
    draw.rounded_rectangle([(bar_margin, bar_y), (bar_margin + int(full_w * prog_ratio), bar_y + 10)], radius=5, fill=(*theme["primary"], 255))

    return img


# ==============================================================================
# 6. تطبيق انتقالات الكاميرا السينمائية بين المشاهد (Whip-Pan, Zoom, Swipe)
# ==============================================================================
def apply_scene_transition(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str
) -> Image.Image:
    """
    تحريك سينمائي حقيقي بين المشهد السابق والمشهد الجديد خلال أول 0.28 ثانية من كل مشهد!
    """
    p = _ease_out_cubic(trans_progress)
    w, h = curr_img.size

    if transition_type == "whip_left":
        # انزلاق أفقي سريع (Whip-Pan Horizontal) مع خط نيون فاصل
        offset = int(w * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        out.paste(prev_img, (- int(w * p), 0))
        out.paste(curr_img, (offset, 0))
        draw = ImageDraw.Draw(out, "RGBA")
        draw.line([(offset, 0), (offset, h)], fill=(255, 230, 0, 220), width=8)
        return out

    elif transition_type == "whip_up":
        # انزلاق عمودي على غرار الريلز (Vertical Swipe Transition)
        offset = int(h * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        out.paste(prev_img, (0, -int(h * p)))
        out.paste(curr_img, (0, offset))
        draw = ImageDraw.Draw(out, "RGBA")
        draw.line([(0, offset), (w, offset)], fill=(0, 245, 212, 220), width=8)
        return out

    elif transition_type == "zoom_portal":
        # انتقال تكبير سينمائي من المركز (Zoom-Through Transition)
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
        # مسح ضوئي متدرج (Cross-Dissolve + Laser Wipe)
        return Image.blend(prev_img, curr_img, p)


# ==============================================================================
# 7. دوال التوافق للبطاقات العلوية ودمج الموشن جرافيك بالفيديو الأصلي
# ==============================================================================
def create_studio_background(
    width: int,
    height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """إنشاء خلفية أستوديو سينمائية متدرجة."""
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
    """رسم أيقونة فيكتور عالية الدقة للبطاقات المدمجة."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    theme = {
        "primary": accent_color,
        "secondary": secondary_color,
        "accent": secondary_color,
        "glow": accent_color
    }
    scene_map = {
        "money": "growth_analytics",
        "time": "time_warp_clock",
        "idea": "ai_neural_brain",
        "code": "platform_builder",
        "question": "video_montage_studio",
        "warning": "reels_smartphone",
        "success": "ecommerce_showcase"
    }
    mapped_scene = scene_map.get(icon_type, "ai_neural_brain")
    draw_animated_scene_illustration(
        draw=draw,
        scene_type=mapped_scene,
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
    icon_map = {
        "video_montage_studio": "question",
        "ai_neural_brain": "idea",
        "reels_smartphone": "warning",
        "platform_builder": "code",
        "time_warp_clock": "time",
        "growth_analytics": "money"
    }
    return {
        "keyword": bp["short_title"],
        "icon_type": icon_map.get(bp["scene_type"], "success"),
        "scene_type": bp["scene_type"]
    }


def render_video_motion_overlay_card(
    keyword_title: str,
    icon_type: str,
    video_width: int,
    video_height: int,
    mode: str = "corner_card",
    subtitle_line: str = "",
    theme_name: str = "cyber_gold",
    scene_type: Optional[str] = None,
    scene_progress: float = 0.8,
    global_t: float = 1.0
) -> np.ndarray:
    """
    توليد طبقة موشن جرافيك غنية للتراكب فوق الفيديو الأصلي:
    ترسم مشهداً مصغراً متحركاً (Mini Animated Scene Graphic) مع العنوان في بطاقة زجاجية أنيقة!
    """
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    title_font_size = max(28, int(min(video_width, video_height) * 0.044))
    title_font = get_arabic_font(title_font_size, bold=True)

    icon_size = max(92, int(min(video_width, video_height) * 0.115))
    icon_img = draw_procedural_vector_icon(
        icon_type=icon_type,
        size=icon_size,
        accent_color=theme["primary"],
        secondary_color=theme["secondary"]
    )

    tw, th = measure_arabic_text(draw, keyword_title, title_font)
    card_w = min(int(video_width * 0.88), max(tw + icon_size + 85, int(video_width * 0.54)))
    card_h = icon_size + 36
    cx = video_width // 2
    top_y = int(video_height * 0.075)

    x1, y1 = cx - card_w // 2, top_y
    x2, y2 = cx + card_w // 2, top_y + card_h

    draw.rounded_rectangle([(x1 - 5, y1 - 5), (x2 + 5, y2 + 5)], radius=28, fill=(*theme["primary"], 55))
    draw.rounded_rectangle(
        [(x1, y1), (x2, y2)],
        radius=24,
        fill=(11, 17, 34, 232),
        outline=(*theme["primary"], 245),
        width=3
    )

    icon_x = x2 - icon_size - 18
    icon_y = y1 + (card_h - icon_size) // 2
    canvas.paste(icon_img, (icon_x, icon_y), icon_img)

    text_center_x = x1 + (icon_x - x1) // 2
    text_center_y = y1 + card_h // 2
    draw_arabic_text(
        draw,
        (text_center_x, text_center_y),
        keyword_title,
        font=title_font,
        fill=(*theme["primary"], 255)
    )

    return np.array(canvas)


def render_ecommerce_ad_overlay(
    ad_role: str,
    badge_title: str,
    icon_cat: str,
    video_width: int,
    video_height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """رسم عناصر الموشن جرافيك الخاصة بإعلانات المنتجات التجارية."""
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    title_size = max(28, int(min(video_width, video_height) * 0.044))
    font_bold = get_arabic_font(title_size, bold=True)
    icon_size = max(78, int(min(video_width, video_height) * 0.095))

    if ad_role == "ad_hook":
        cx = video_width // 2
        top_y = int(video_height * 0.075)
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        banner_w = min(int(video_width * 0.92), tw + 80)
        banner_h = th + 38

        bx1, by1 = cx - banner_w // 2, top_y
        bx2, by2 = cx + banner_w // 2, top_y + banner_h
        draw.rounded_rectangle([(bx1 - 4, by1 - 4), (bx2 + 4, by2 + 4)], radius=22, fill=(245, 158, 11, 85))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=18, fill=(20, 10, 10, 238), outline=(255, 215, 0, 255), width=3)
        draw_arabic_text(draw, (cx, by1 + banner_h // 2), badge_title, font=font_bold, fill=(255, 230, 0, 255), stroke_width=2, stroke_fill=(0, 0, 0, 240))

    elif ad_role == "ad_cta":
        cx = video_width // 2
        bot_y = int(video_height * 0.84)
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        banner_w = min(int(video_width * 0.94), tw + 90)
        banner_h = th + 42

        bx1, by1 = cx - banner_w // 2, bot_y
        bx2, by2 = cx + banner_w // 2, bot_y + banner_h
        draw.rounded_rectangle([(bx1 - 5, by1 - 5), (bx2 + 5, by2 + 5)], radius=24, fill=(16, 185, 129, 95))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=20, fill=(6, 26, 20, 242), outline=(52, 211, 153, 255), width=4)
        draw_arabic_text(draw, (cx, by1 + banner_h // 2), badge_title, font=font_bold, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 220))

    elif ad_role == "ad_problem":
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        top_y = int(video_height * 0.08)
        card_w = min(int(video_width * 0.85), tw + 65)
        card_h = th + 30
        cx = video_width // 2
        draw.rounded_rectangle([(cx - card_w // 2, top_y), (cx + card_w // 2, top_y + card_h)], radius=18, fill=(48, 12, 16, 232), outline=(239, 68, 68, 235), width=3)
        draw_arabic_text(draw, (cx, top_y + card_h // 2), badge_title, font=font_bold, fill=(254, 202, 202, 255))

    else:
        return render_video_motion_overlay_card(
            keyword_title=badge_title,
            icon_type=icon_cat,
            video_width=video_width,
            video_height=video_height,
            theme_name=theme_name
        )

    return np.array(canvas)


# ==============================================================================
# 8. المسار الرئيسي لتوليد فيديو الموشن جرافيك الكامل المتحرك (Full Animated VideoClip)
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
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    إنشاء فيديو موشن جرافيك كامل ومتحرك إطاراً بإطار (24 FPS Real-Time Animation):
    - يولّد مشهداً رسومياً جديداً كل 1.5 إلى 2.1 ثانية يناسب معنى الكلام المنطوق في تلك اللحظة.
    - يطبق انتقالات كاميرا سينمائية (Whip-Pan, Zoom Portal, Vertical Swipe) بين كل مشهد وآخر.
    - يحرك الرسومات، العدادات، شريط المونتاج، شبكة الذكاء الاصطناعي، والكلمات بفيزياء زنبركية سلسة.
    """
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

        # تقسيم الكلمات إلى مشاهد قصيرة متجددة كل 1.5 - 2.1 ثانية
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
            # جعل نهاية المشهد تمتد حتى بداية المشهد التالي لمنع أي فراغ بصري
            if idx + 1 < len(micro_scenes):
                s_end = float(micro_scenes[idx + 1]["start"])
            else:
                s_end = total_duration

            storyboard.append({
                "index": idx,
                "start": s_start,
                "end": max(s_start + 0.2, s_end),
                "text": sc["text"],
                "words": sc["words"],
                "word_strings": [w["word"] for w in sc["words"]],
                **bp
            })

        # حساب غلاف شدة الصوت (Audio Envelope) لتفاعل الموجات الصوتية مع الصوت الحقيقي
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
            """تحديد المشهد والكلمة النشطة ونسبة التقدم عند اللحظة t_sec."""
            active_sc_idx = 0
            for idx, sc in enumerate(storyboard):
                if t_sec >= sc["start"]:
                    active_sc_idx = idx
                else:
                    break

            sc = storyboard[active_sc_idx]
            sc_dur = max(0.15, sc["end"] - sc["start"])
            sc_prog = max(0.0, min(1.0, (t_sec - sc["start"]) / sc_dur))

            # تحديد الكلمة المنطوقة داخل المشهد
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

        transition_duration = 0.28  # مدة التحريك الانتقالي بين كل لقطة وأخرى

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

            # إذا كنا في بداية مشهد جديد، نطبق انتقال كاميرا سينمائي (Whip-Pan / Zoom / Swipe) من المشهد السابق!
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
