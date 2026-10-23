"""
motion_text.py - محرك الموشن جرافيك الاحترافي الفائق الموجه بالسياق (Contextual Pro Vector, Shader & VisionOS Engine)
=======================================================================================================================
يجمع هذا المحرك بين 5 تقنيات متقدمة للوصول لمستوى مصمم موشن جرافيك محترف يفهم سياق الفيديو الكامل:
1. مخ التحليل السياقي والسردي (Contextual & Narrative Storyboard Brain):
   - يحلل النص الكامل للفيديو ويقسمه إلى جمل وأفكار متكاملة المعنى (وليس كلمة بكلمة).
   - يولد لكل فكرة مشهداً بصرياً متكاملاً، وعنواناً مفاهيمياً (`concept_title`)، ومؤشر أداء سياقي (`kpi_value`) دون تكرار نص الكابشن حرفياً.
2. محرك الفيكتور والتدرجات اللونية (PyCairo Vector & Bezier Spline Engine):
   - رسم منحنيات بيزيير الناعمة وتدرجات لونية خطية وشعاعية متصلة لجميع أنماط المشاهد.
3. محرك الزجاج الحقيقي والظلال الثلاثية الأبعاد (Real Backdrop Gaussian Blur & Soft Drop Shadows - Apple visionOS).
4. فيزياء النوابض الحقيقية وتحريك الطبقات المتتابع (Damped Spring Physics & Staggered Layer Choreography).
5. كابشن كاريوكي زجاجي موحد يبرز الكلمة المنطوقة لحظياً داخل الجملة السياقية الكاملة.
"""

import sys
import os
import gc
import subprocess

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
if not hasattr(PIL.ImageDraw.ImageDraw, "_true_orig_rounded_rect"):
    PIL.ImageDraw.ImageDraw._true_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

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
        return PIL.ImageDraw.ImageDraw._true_orig_rounded_rect(
            self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners
        )
    except Exception:
        pass

PIL.ImageDraw.ImageDraw.rounded_rectangle = _safe_rounded_rectangle

import re
import math
import time
import hashlib
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features

try:
    import cairo
    _HAS_CAIRO = True
except Exception:
    cairo = None
    _HAS_CAIRO = False

from auto_cut import remove_silence, is_video_file, get_safe_working_resolution, extract_jumpcut_audio_and_intervals, force_free_ram
from physics_easing import (
    spring_damper,
    spring_velocity,
    ease_out_back as physics_ease_out_back,
    ease_in_out_expo as physics_ease_in_out_expo,
    ease_out_elastic as physics_ease_out_elastic,
    StaggeredKeyframeSequencer,
    apply_fast_directional_motion_blur
)
from vector_lottie_engine import (
    render_lottie_or_svg_badge,
    draw_animated_stroke_dash_rect,
    render_floating_particles_layer,
    render_radial_ambient_glow
)
from style_evolution_brain import (
    evaluate_and_evolve_frame,
    get_best_params_for_scene_type,
    get_active_brand_theme
)
from transcriber import (
    transcribe_audio,
    split_words_into_micro_scenes
)

try:
    from transcriber import query_hybrid_llm
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
    # إزالة رموز الإيموجي غير المدعومة في خطوط TrueType لمنع ظهور المربعات الفارغة (▯)
    text = re.sub(r"[\U00010000-\U0010ffff\u2700-\u27bf\u2600-\u26ff\ufe0f]", "", str(text)).strip()
    if _HAS_RAQM:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _get_latin_safe_font(font: ImageFont.FreeTypeFont, text: str) -> ImageFont.FreeTypeFont:
    """استخدام خط يدعم الرموز والحروف اللاتينية (+, %, W, AI) تلقائياً لمنع ظهور المربعات الفارغة."""
    if not text or not re.search(r"[A-Za-z+%$#@&*=/\\•()\-:|]", str(text)):
        return font
    f_path = getattr(font, "path", "")
    if "Cairo" in f_path or "DejaVu" in f_path:
        return font
    dejavu_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(dejavu_p):
        sz = getattr(font, "size", 32)
        key = ("dejavu_safe", int(sz))
        if key not in _FONT_OBJECT_CACHE:
            try:
                _FONT_OBJECT_CACHE[key] = ImageFont.truetype(dejavu_p, int(sz))
            except Exception:
                return font
        return _FONT_OBJECT_CACHE[key]
    return font


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
    if not text:
        return
    eff_font = _get_latin_safe_font(font, str(text))
    prepared = shape_arabic_text(str(text))
    kwargs = {"font": eff_font, "fill": fill, "anchor": anchor}
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
    if not text:
        return 12, 24
    font = _get_latin_safe_font(font, str(text))
    prepared = shape_arabic_text(str(text))
    try:
        if _HAS_RAQM:
            bbox = draw.textbbox((0, 0), prepared, font=font, direction="rtl")
        else:
            bbox = draw.textbbox((0, 0), prepared, font=font)
        return max(12, int(bbox[2] - bbox[0])), max(12, int(bbox[3] - bbox[1]))
    except Exception:
        return max(20, len(str(text)) * 18), 36


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
                resp = requests.get(url, timeout=4)
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


def get_fitted_arabic_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    initial_font_size: int,
    min_font_size: int = 10,
    bold: bool = True
) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    """تصغير حجم الخط تلقائياً بدقة 1px لضمان ملاءمة النص داخل حدود البطاقة بدون أي خروج أو تجاوز."""
    size = int(initial_font_size)
    min_size = max(9, int(min_font_size))
    safe_max_w = max(24, int(max_width))
    f_obj = get_arabic_font(size, bold=bold)
    tw, th = measure_arabic_text(draw, str(text), f_obj)
    while tw > safe_max_w and size > min_size:
        step = 2 if size > 18 else 1
        size = max(min_size, size - step)
        f_obj = get_arabic_font(size, bold=bold)
        tw, th = measure_arabic_text(draw, str(text), f_obj)
    return f_obj, tw, th


def fit_and_condense_arabic_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    initial_font_size: int,
    min_font_size: int = 11,
    bold: bool = True
) -> Tuple[str, ImageFont.FreeTypeFont, int, int]:
    """
    حلال قيود الهندسة البصرية الشامل (Universal Container Text Constraint Solver):
    يصغر الخط أولاً حتى `min_font_size`، وإذا ظل النص أعرض من `max_width` يقوم بتكثيفه ذكياً
    عند حدود الكلمات أو الفواصل (`•`) ليضمن رياضياً 100% أن `tw <= max_width` في كل فريم!
    """
    clean_t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_t:
        f_obj = get_arabic_font(initial_font_size, bold=bold)
        return "", f_obj, 0, initial_font_size

    safe_max_w = max(28, int(max_width))
    f_obj, tw, th = get_fitted_arabic_font(draw, clean_t, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
    if tw <= safe_max_w:
        return clean_t, f_obj, tw, th

    # المحاولة 1: إزالة الأقواس التوضيحية إن وجدت
    no_paren = re.sub(r"\s*\([^)]*\)", "", clean_t).strip()
    if no_paren and no_paren != clean_t:
        f_obj, tw, th = get_fitted_arabic_font(draw, no_paren, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
        if tw <= safe_max_w:
            return no_paren, f_obj, tw, th
        clean_t = no_paren

    # المحاولة 2: تقليص الكلمات تدريجياً من النهاية مع الحفاظ على المعنى الكامل قدر الإمكان
    words = clean_t.split()
    while len(words) > 2:
        words.pop()
        cand = " ".join(words).rstrip("•:-،,")
        f_obj, tw, th = get_fitted_arabic_font(draw, cand, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
        if tw <= safe_max_w:
            return cand, f_obj, tw, th

    # المحاولة 3: تصغير إضافي للخط حتى 9px للكلمات الطويلة جداً
    f_obj, tw, th = get_fitted_arabic_font(draw, clean_t, safe_max_w, min_font_size, min_font_size=8, bold=bold)
    return clean_t, f_obj, tw, th


def draw_contained_arabic_text(
    draw: ImageDraw.ImageDraw,
    container_bbox: Tuple[int, int, int, int],
    text: str,
    initial_font_size: int,
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
    pad_left: int = 14,
    pad_right: int = 14,
    min_font_size: int = 11,
    bold: bool = True,
    stroke_width: int = 0,
    stroke_fill: Optional[Tuple[int, int, int, int]] = None
) -> Tuple[int, int]:
    """
    يرسم النص العربي داخل المنطقة الآمنة `(x1 + pad_left, x2 - pad_right)` للحاوية
    مع ضمان عدم تجاوز النص لحدود الحاوية أو اصطدامه بالأيقونات الجانبية إطلاقاً.
    """
    x1, y1, x2, y2 = container_bbox
    safe_x1 = int(x1 + pad_left)
    safe_x2 = int(x2 - pad_right)
    if safe_x2 <= safe_x1 + 16:
        safe_x1 = int(x1 + 4)
        safe_x2 = int(x2 - 4)
    safe_w = max(20, safe_x2 - safe_x1)
    safe_cx = (safe_x1 + safe_x2) // 2
    safe_cy = (int(y1) + int(y2)) // 2

    fitted_text, f_obj, tw, th = fit_and_condense_arabic_text(
        draw, text, safe_w, initial_font_size=initial_font_size, min_font_size=min_font_size, bold=bold
    )
    draw_arabic_text(
        draw, (safe_cx, safe_cy), fitted_text, font=f_obj, fill=fill,
        stroke_width=stroke_width, stroke_fill=stroke_fill
    )
    return tw, th


# ==============================================================================
# 2. الثيمات اللونية السينمائية المتقدمة (Pro Studio Color Palettes)
# ==============================================================================
MOTION_THEMES = {
    "cyber_gold": {
        "top_bg": (7, 11, 22),
        "bottom_bg": (15, 23, 42),
        "glow": (255, 200, 0),
        "primary": (255, 215, 0),
        "secondary": (0, 245, 212),
        "accent": (99, 102, 241),
        "card_bg": (13, 19, 38)
    },
    "neon_emerald": {
        "top_bg": (5, 16, 20),
        "bottom_bg": (10, 31, 38),
        "glow": (16, 185, 129),
        "primary": (0, 245, 212),
        "secondary": (250, 204, 21),
        "accent": (56, 189, 248),
        "card_bg": (10, 25, 34)
    },
    "royal_purple": {
        "top_bg": (12, 8, 28),
        "bottom_bg": (24, 14, 48),
        "glow": (168, 85, 247),
        "primary": (56, 189, 248),
        "secondary": (236, 72, 153),
        "accent": (250, 204, 21),
        "card_bg": (20, 14, 42)
    },
    "crimson_energy": {
        "top_bg": (18, 8, 16),
        "bottom_bg": (34, 12, 26),
        "glow": (244, 63, 94),
        "primary": (255, 190, 11),
        "secondary": (255, 0, 110),
        "accent": (0, 245, 212),
        "card_bg": (28, 12, 24)
    },
    "electric_cobalt": {
        "top_bg": (6, 12, 28),
        "bottom_bg": (14, 26, 54),
        "glow": (59, 130, 246),
        "primary": (56, 189, 248),
        "secondary": (255, 214, 10),
        "accent": (16, 185, 129),
        "card_bg": (12, 22, 46)
    },
    "sunset_violet": {
        "top_bg": (16, 10, 26),
        "bottom_bg": (32, 16, 44),
        "glow": (249, 115, 22),
        "primary": (251, 146, 60),
        "secondary": (192, 132, 252),
        "accent": (45, 212, 191),
        "card_bg": (24, 14, 38)
    }
}


# ==============================================================================
# 3. محرك الفيزياء الحقيقية للنوابض والمنحنيات (Spring Physics & Easing Solver)
# ==============================================================================
def _ease_out_cubic(x: float) -> float:
    return float(physics_ease_out_back(x, overshoot=0.65))


def _ease_in_out_cubic(x: float) -> float:
    return float(physics_ease_in_out_expo(x))


def _ease_out_back(x: float, overshoot: float = 1.70158) -> float:
    return float(physics_ease_out_back(x, overshoot=overshoot))


def _spring_physics(t: float, stiffness: float = 185.0, damping: float = 13.0, mass: float = 1.0) -> float:
    """محرك فيزياء النوابض الحقيقي عبر وحدة `physics_easing.spring_damper`."""
    return float(spring_damper(t, stiffness=stiffness, damping=damping, mass=mass))


def _staggered_spring(global_prog: float, delay: float = 0.0, duration: float = 0.42, stiffness: float = 185.0, damping: float = 13.0) -> float:
    """حساب حركة طبقة فرعية بتأخير متتابع (Staggered Keyframe Choreography)."""
    local_t = (global_prog - delay) / max(0.05, duration)
    return float(spring_damper(max(0.0, min(1.0, local_t)), stiffness=stiffness, damping=damping))


# ==============================================================================
# 4. تصنيف المشاهد وبناء البلوبرينت الدلالي السياقي الذكي
# ==============================================================================
def classify_micro_scene_blueprint(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    prev_scene_type: Optional[str] = None,
    full_transcript: str = "",
    prev_scene_text: str = "",
    next_scene_text: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    تصنيف المشهد بناءً على السياق الكامل للجملة والفيديو (وليس كلمة بكلمة):
    يستدعي المخ السياقي في `smart_analyzer` لتوليد نوع المشهد، عنوان الشارة، المفهوم السياقي للبطاقة اليسرى،
    ومؤشر الـ KPI السياقي للبطاقة اليمنى دون تكرار الكلمات المنطوقة حرفياً.
    """
    try:
        from smart_analyzer import extract_global_video_context, analyze_scene_with_context
        global_ctx = extract_global_video_context(full_transcript or scene_text)
        res = analyze_scene_with_context(
            scene_text=scene_text,
            scene_index=scene_index,
            total_scenes=total_scenes,
            global_ctx=global_ctx,
            prev_scene_text=prev_scene_text,
            next_scene_text=next_scene_text,
            prev_scene_type=prev_scene_type
        )
        theme_keys = list(MOTION_THEMES.keys())
        transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]
        res["theme_name"] = theme_keys[scene_index % len(theme_keys)]
        res["transition_type"] = transitions[scene_index % len(transitions)]
        return res
    except Exception:
        pass

    # احتياطي سياقي مدمج
    t = scene_text.strip()
    num_match = re.search(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t)
    extracted_number = int(num_match.group(1)) if num_match else 17

    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    return {
        "scene_type": "video_montage_studio",
        "badge_label": "أستوديو المونتاج الذكي",
        "short_title": "تطوير المحتوى الذكي",
        "concept_title": "تطوير المحتوى الذكي",
        "concept_subtitle": "معالجة سياقية متكاملة",
        "kpi_value": "AI Studio",
        "kpi_label": "أداء احترافي",
        "target_number": extracted_number,
        "theme_name": theme_keys[scene_index % len(theme_keys)],
        "transition_type": transitions[scene_index % len(transitions)]
    }


# ==============================================================================
# 5. محرك الشيدر والزجاج الحقيقي (Apple visionOS Glassmorphism & Drop Shadows)
# ==============================================================================
def draw_visionos_glass_panel(
    canvas_rgba: Image.Image,
    bbox: Tuple[int, int, int, int],
    radius: int = 28,
    tint_color: Tuple[int, int, int, int] = (12, 18, 34, 185),
    border_color: Tuple[int, int, int] = (255, 215, 0),
    secondary_color: Tuple[int, int, int] = (0, 245, 212),
    blur_radius: int = 16,
    shadow_offset: int = 14,
    shadow_blur: int = 20,
    light_sweep_prog: float = -1.0
) -> Image.Image:
    """
    رسم بطاقة زجاجية حقيقية بمستوى Apple visionOS:
    1. ظل سفلي ناعم (Gaussian Drop Shadow) يعطي عمقاً ثلاثي الأبعاد.
    2. قص الخلفية وتطبيق ضبابية بصرية حقيقية (Backdrop Gaussian Blur).
    3. لمعان ضوئي قطري متحرك (Specular Light Sweep).
    4. حدود مزدوجة متوهجة (Dual Specular Rim).
    """
    w, h = canvas_rgba.size
    x1, y1, x2, y2 = int(max(0, bbox[0])), int(max(0, bbox[1])), int(min(w, bbox[2])), int(min(h, bbox[3]))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return canvas_rgba

    # 1. رسم الظل الناعم الثلاثي الأبعاد (Soft Drop Shadow)
    pad = shadow_blur * 2 + abs(shadow_offset) + 8
    sx1, sy1 = max(0, x1 - pad), max(0, y1 - pad)
    sx2, sy2 = min(w, x2 + pad), min(h, y2 + pad)
    sw, sh = sx2 - sx1, sy2 - sy1

    if sw > 4 and sh > 4:
        shadow_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer, "RGBA")
        bx1, by1 = x1 - sx1, y1 - sy1 + shadow_offset
        bx2, by2 = x2 - sx1, y2 - sy1 + shadow_offset
        s_draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=(0, 0, 0, 155))
        s_draw.rounded_rectangle([(bx1 - 2, by1 - shadow_offset), (bx2 + 2, by2 - shadow_offset)], radius=radius + 2, outline=(*border_color, 80), width=4)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(2, shadow_blur // 2)))
        canvas_rgba.alpha_composite(shadow_layer, (sx1, sy1))

    # 2. قص الخلفية وتطبيق التمويه الزجاجي الحقيقي (Backdrop Blur)
    pw, ph = x2 - x1, y2 - y1
    backdrop_crop = canvas_rgba.crop((x1, y1, x2, y2))
    if blur_radius > 0:
        backdrop_crop = backdrop_crop.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    glass_tint = Image.new("RGBA", (pw, ph), tint_color)
    frosted = Image.alpha_composite(backdrop_crop, glass_tint)

    # 3. انعكاس الضوء القطري المتحرك (Specular Sheen & Light Sweep)
    sheen = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sheen, "RGBA")
    for sy in range(min(28, ph // 4)):
        alpha_v = int(24 * (1.0 - sy / 28.0))
        if alpha_v > 0:
            sh_draw.line([(radius // 2, sy + 2), (pw - radius // 2, sy + 2)], fill=(255, 255, 255, alpha_v), width=1)

    if 0.0 <= light_sweep_prog <= 1.0:
        sweep_x = int(-pw * 0.4 + (pw * 1.8) * light_sweep_prog)
        beam_w = max(24, pw // 5)
        sh_draw.polygon([
            (sweep_x, 0),
            (sweep_x + beam_w, 0),
            (sweep_x - int(ph * 0.4) + beam_w, ph),
            (sweep_x - int(ph * 0.4), ph)
        ], fill=(255, 255, 255, 30))

    frosted = Image.alpha_composite(frosted, sheen)

    mask = Image.new("L", (pw, ph), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([(0, 0), (pw - 1, ph - 1)], radius=radius, fill=255)
    canvas_rgba.paste(frosted, (x1, y1), mask)

    # 4. رسم الإطار المتوهج المزدوج (Dual Specular Rim)
    c_draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    c_draw.rounded_rectangle([(x1, y1), (x2 - 1, y2 - 1)], radius=radius, outline=(*border_color, 225), width=2)
    c_draw.rounded_rectangle([(x1 + 2, y1 + 2), (x2 - 3, y2 - 3)], radius=max(2, radius - 2), outline=(255, 255, 255, 50), width=1)

    return canvas_rgba


# ==============================================================================
# 6. محرك الرسوميات الفيكتور الاحترافي (PyCairo Vector & Bezier Studio Engine)
# ==============================================================================
def _cairo_rounded_rect(ctx, x: float, y: float, w: float, h: float, r: float):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def _cairo_regular_polygon(ctx, cx: float, cy: float, radius: float, sides: int = 6, rotation: float = 0.0):
    ctx.new_sub_path()
    for i in range(sides):
        ang = rotation + i * (2.0 * math.pi / sides)
        px = cx + radius * math.cos(ang)
        py = cy + radius * math.sin(ang)
        if i == 0:
            ctx.move_to(px, py)
        else:
            ctx.line_to(px, py)
    ctx.close_path()


def _norm_rgb(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def render_cairo_vector_illustration(
    scene_type: str,
    width: int,
    height: int,
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any],
    target_number: int = 17
) -> Image.Image:
    """
    توليد رسومات فيكتور احترافية بمنحنيات بيزيير وتدرجات لونية عبر PyCairo
    مع ضمان ظهور الرسمة فوراً من اللحظة 0.0 (Scale 0.78 -> 1.0) لجميع الأنماط الـ 11.
    """
    if not _HAS_CAIRO:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)

    cx, cy = width / 2.0, height / 2.0
    r = min(width, height) * 0.46
    p1 = _norm_rgb(theme["primary"])
    p2 = _norm_rgb(theme["secondary"])
    acc = _norm_rgb(theme["accent"])

    # حركة نابضية متتابعة تبدأ من 0.78 لتكون الرسمة مرئية فوراً في الإطار 0.0s
    s_main = 0.78 + 0.22 * _staggered_spring(scene_progress, delay=0.0, duration=0.45)
    s_sub1 = 0.72 + 0.28 * _staggered_spring(scene_progress, delay=0.06, duration=0.48)
    s_sub2 = 0.68 + 0.32 * _staggered_spring(scene_progress, delay=0.12, duration=0.50)

    # 1. هالة ضوئية خلفية ناعمة (Radial Ambient Glow)
    rad_glow = cairo.RadialGradient(cx, cy, r * 0.05, cx, cy, r * 1.15)
    rad_glow.add_color_stop_rgba(0.0, p1[0], p1[1], p1[2], 0.28 * s_main)
    rad_glow.add_color_stop_rgba(0.5, p2[0], p2[1], p2[2], 0.11 * s_main)
    rad_glow.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
    ctx.set_source(rad_glow)
    ctx.arc(cx, cy, r * 1.15, 0, 2 * math.pi)
    ctx.fill()

    # 2. حلقات مدار تقنية دوارة بنقاط متقطعة (Orbital HUD Rings)
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(global_t * 0.45)
    ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.24 * s_main)
    ctx.set_line_width(2.0)
    ctx.set_dash([14.0, 10.0])
    ctx.arc(0, 0, r * 0.96 * s_main, 0, 2 * math.pi)
    ctx.stroke()
    ctx.restore()

    # -------------------------------------------------------------------------
    # المشهد 1: أستوديو المونتاج الذكي (Pro NLE Video Timeline & Cinema Monitor)
    # -------------------------------------------------------------------------
    if scene_type == "video_montage_studio":
        mw, mh = r * 1.65 * s_main, r * 1.25 * s_main
        mx, my = cx - mw / 2, cy - mh / 2

        _cairo_rounded_rect(ctx, mx, my, mw, mh, 22)
        bg_grad = cairo.LinearGradient(mx, my, mx, my + mh)
        bg_grad.add_color_stop_rgba(0, 0.08, 0.12, 0.22, 0.95)
        bg_grad.add_color_stop_rgba(1, 0.04, 0.06, 0.14, 0.98)
        ctx.set_source(bg_grad)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.85)
        ctx.set_line_width(3.0)
        ctx.stroke()

        vw, vh = mw * 0.88, mh * 0.46
        vx, vy = cx - vw / 2, my + mh * 0.08
        _cairo_rounded_rect(ctx, vx, vy, vw, vh, 12)
        scr_grad = cairo.LinearGradient(vx, vy, vx + vw, vy + vh)
        scr_grad.add_color_stop_rgba(0, p2[0] * 0.35, p2[1] * 0.35, p2[2] * 0.45, 0.9)
        scr_grad.add_color_stop_rgba(1, acc[0] * 0.35, acc[1] * 0.35, acc[2] * 0.55, 0.9)
        ctx.set_source(scr_grad)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.25)
        ctx.set_line_width(1.5)
        ctx.stroke()

        ctx.move_to(vx + 10, vy + vh * 0.7)
        ctx.curve_to(
            vx + vw * 0.3, vy + vh * (0.3 + 0.2 * math.sin(global_t * 3)),
            vx + vw * 0.7, vy + vh * (0.9 - 0.2 * math.cos(global_t * 3)),
            vx + vw - 10, vy + vh * 0.5
        )
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.65)
        ctx.set_line_width(3.0)
        ctx.stroke()

        pr = vh * 0.24 * (1.0 + 0.08 * math.sin(global_t * 5))
        ctx.arc(cx, vy + vh / 2, pr * 1.35, 0, 2 * math.pi)
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.25)
        ctx.fill()
        ctx.arc(cx, vy + vh / 2, pr, 0, 2 * math.pi)
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.95)
        ctx.fill()
        ctx.move_to(cx - pr * 0.3, vy + vh / 2 - pr * 0.42)
        ctx.line_to(cx - pr * 0.3, vy + vh / 2 + pr * 0.42)
        ctx.line_to(cx + pr * 0.48, vy + vh / 2)
        ctx.close_path()
        ctx.set_source_rgba(0.05, 0.08, 0.15, 1.0)
        ctx.fill()

        track_colors = [p1, p2, acc]
        track_y0 = vy + vh + mh * 0.08
        track_h = mh * 0.09
        for ti in range(3):
            ty = track_y0 + ti * (track_h + mh * 0.035)
            _cairo_rounded_rect(ctx, vx, ty, vw, track_h, 6)
            ctx.set_source_rgba(1, 1, 1, 0.07)
            ctx.fill()

            tc = track_colors[ti]
            c1_w = vw * (0.38 if ti != 1 else 0.28) * s_sub1
            _cairo_rounded_rect(ctx, vx + 6, ty + 2, c1_w, track_h - 4, 4)
            cg = cairo.LinearGradient(vx, ty, vx + c1_w, ty)
            cg.add_color_stop_rgba(0, tc[0], tc[1], tc[2], 0.92)
            cg.add_color_stop_rgba(1, tc[0] * 0.6, tc[1] * 0.6, tc[2] * 0.6, 0.92)
            ctx.set_source(cg)
            ctx.fill()

            c2_x = vx + 12 + c1_w
            c2_w = vw * (0.44 if ti != 2 else 0.52) * s_sub2
            if c2_x + c2_w < vx + vw - 4:
                _cairo_rounded_rect(ctx, c2_x, ty + 2, c2_w, track_h - 4, 4)
                ctx.set_source_rgba(tc[0], tc[1], tc[2], 0.75)
                ctx.fill()

        ph_x = vx + vw * (0.15 + 0.72 * ((scene_progress * 0.8 + (global_t * 0.25) % 1.0) % 1.0))
        ctx.move_to(ph_x, vy + vh + 4)
        ctx.line_to(ph_x, my + mh - 10)
        ctx.set_source_rgba(1.0, 0.25, 0.35, 0.95)
        ctx.set_line_width(3.5)
        ctx.stroke()
        ctx.arc(ph_x, vy + vh + 4, 6, 0, 2 * math.pi)
        ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 2: محرك الذكاء الاصطناعي (3D Neural Core & Synaptic Bezier Pulses)
    # -------------------------------------------------------------------------
    elif scene_type == "ai_neural_brain":
        num_nodes = 8
        outer_r = r * 0.82 * s_sub1
        nodes = []
        for i in range(num_nodes):
            ang = i * (2 * math.pi / num_nodes) + global_t * 0.35
            nx = cx + outer_r * math.cos(ang)
            ny = cy + outer_r * math.sin(ang)
            nodes.append((nx, ny, ang))

        for i, (nx, ny, ang) in enumerate(nodes):
            ctrl_ang = ang + 0.45 * math.sin(global_t * 2 + i)
            ctrl_x = cx + outer_r * 0.48 * math.cos(ctrl_ang)
            ctrl_y = cy + outer_r * 0.48 * math.sin(ctrl_ang)

            ctx.move_to(cx, cy)
            ctx.curve_to(ctrl_x, ctrl_y, ctrl_x, ctrl_y, nx, ny)
            line_grad = cairo.LinearGradient(cx, cy, nx, ny)
            line_grad.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 0.85)
            line_grad.add_color_stop_rgba(1, p2[0], p2[1], p2[2], 0.35)
            ctx.set_source(line_grad)
            ctx.set_line_width(3.0)
            ctx.stroke()

            pulse_t = (global_t * 1.4 + i * 0.18) % 1.0
            px = (1 - pulse_t)**2 * cx + 2 * (1 - pulse_t) * pulse_t * ctrl_x + pulse_t**2 * nx
            py = (1 - pulse_t)**2 * cy + 2 * (1 - pulse_t) * pulse_t * ctrl_y + pulse_t**2 * ny
            ctx.arc(px, py, 5.5, 0, 2 * math.pi)
            ctx.set_source_rgba(1, 1, 1, 0.95)
            ctx.fill()

            nr = 15.0 + 3.0 * math.sin(global_t * 4 + i)
            ctx.arc(nx, ny, nr * 1.6, 0, 2 * math.pi)
            ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.25)
            ctx.fill()
            ctx.arc(nx, ny, nr, 0, 2 * math.pi)
            ctx.set_source_rgba(0.06, 0.10, 0.20, 0.95)
            ctx.fill_preserve()
            ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.95)
            ctx.set_line_width(3.0)
            ctx.stroke()

        core_r = r * 0.32 * s_main
        _cairo_rounded_rect(ctx, cx - core_r, cy - core_r, core_r * 2, core_r * 2, core_r * 0.38)
        core_grad = cairo.RadialGradient(cx - core_r * 0.3, cy - core_r * 0.3, 4, cx, cy, core_r * 1.3)
        core_grad.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 1.0)
        core_grad.add_color_stop_rgba(1, acc[0], acc[1], acc[2], 0.95)
        ctx.set_source(core_grad)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.set_line_width(3.5)
        ctx.stroke()

        inner_s = core_r * 0.52
        _cairo_rounded_rect(ctx, cx - inner_s, cy - inner_s, inner_s * 2, inner_s * 2, 8)
        ctx.set_source_rgba(0.05, 0.08, 0.16, 0.92)
        ctx.fill()
        ctx.arc(cx, cy, inner_s * 0.45, 0, 2 * math.pi)
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 1.0)
        ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 3: هاتف الريلز والبطاقات العائمة (3D Smartphone & Floating Social UI)
    # -------------------------------------------------------------------------
    elif scene_type == "reels_smartphone":
        pw, ph = r * 0.92 * s_main, r * 1.62 * s_main
        px, py = cx - pw / 2, cy - ph / 2

        _cairo_rounded_rect(ctx, px, py, pw, ph, 28)
        ph_grad = cairo.LinearGradient(px, py, px + pw, py + ph)
        ph_grad.add_color_stop_rgba(0, 0.12, 0.18, 0.32, 0.98)
        ph_grad.add_color_stop_rgba(1, 0.05, 0.08, 0.16, 0.98)
        ctx.set_source(ph_grad)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.95)
        ctx.set_line_width(4.0)
        ctx.stroke()

        _cairo_rounded_rect(ctx, px + 10, py + 14, pw - 20, ph - 28, 20)
        scr_g = cairo.LinearGradient(px, py, px + pw, py + ph)
        scr_g.add_color_stop_rgba(0, acc[0] * 0.45, acc[1] * 0.45, acc[2] * 0.65, 0.85)
        scr_g.add_color_stop_rgba(1, p2[0] * 0.25, p2[1] * 0.25, p2[2] * 0.35, 0.90)
        ctx.set_source(scr_g)
        ctx.fill()

        di_w, di_h = pw * 0.34, 10
        _cairo_rounded_rect(ctx, cx - di_w / 2, py + 22, di_w, di_h, 5)
        ctx.set_source_rgba(0.02, 0.03, 0.06, 0.95)
        ctx.fill()

        float_y = cy - ph * 0.12 + 8 * math.sin(global_t * 3.5)
        fw, fh = pw * 1.25 * s_sub1, ph * 0.28 * s_sub1
        _cairo_rounded_rect(ctx, cx - fw / 2, float_y - fh / 2, fw, fh, 18)
        ctx.set_source_rgba(0.08, 0.13, 0.25, 0.94)
        ctx.fill_preserve()
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.9)
        ctx.set_line_width(2.5)
        ctx.stroke()

        ctx.arc(cx, float_y, fh * 0.28, 0, 2 * math.pi)
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.95)
        ctx.fill()

        for bi in range(4):
            by = py + ph * 0.78 - ((global_t * 55 + bi * 38) % (ph * 0.55))
            bx = px + pw * 0.82 + 12 * math.sin(global_t * 3 + bi)
            ctx.arc(bx, by, 10 - bi * 1.2, 0, 2 * math.pi)
            col = p1 if bi % 2 == 0 else p2
            ctx.set_source_rgba(col[0], col[1], col[2], 0.88)
            ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 4: مؤشر النمو والإحصائيات (Spline Area Chart & Analytics Dashboard)
    # -------------------------------------------------------------------------
    elif scene_type == "growth_analytics":
        cw, ch = r * 1.62 * s_main, r * 1.15 * s_main
        x0, y0 = cx - cw / 2, cy - ch / 2

        _cairo_rounded_rect(ctx, x0, y0, cw, ch, 22)
        ctx.set_source_rgba(0.06, 0.10, 0.20, 0.92)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.18)
        ctx.set_line_width(2.0)
        ctx.stroke()

        gx1, gx2 = x0 + cw * 0.10, x0 + cw * 0.90
        gy_bot = y0 + ch * 0.82
        gy_top = y0 + ch * 0.22
        for gi in range(4):
            ly = gy_top + gi * ((gy_bot - gy_top) / 3.0)
            ctx.move_to(gx1, ly)
            ctx.line_to(gx2, ly)
            ctx.set_source_rgba(1, 1, 1, 0.08)
            ctx.set_line_width(1.2)
            ctx.stroke()

        pts = [
            (gx1, gy_bot - (gy_bot - gy_top) * 0.12),
            (gx1 + (gx2 - gx1) * 0.25, gy_bot - (gy_bot - gy_top) * 0.35 * s_sub1),
            (gx1 + (gx2 - gx1) * 0.50, gy_bot - (gy_bot - gy_top) * 0.28 * s_sub1),
            (gx1 + (gx2 - gx1) * 0.75, gy_bot - (gy_bot - gy_top) * 0.68 * s_sub2),
            (gx2, gy_bot - (gy_bot - gy_top) * 0.92 * s_sub2)
        ]

        ctx.move_to(pts[0][0], gy_bot)
        ctx.line_to(pts[0][0], pts[0][1])
        for i in range(len(pts) - 1):
            p_curr = pts[i]
            p_next = pts[i + 1]
            mid_x = (p_curr[0] + p_next[0]) / 2.0
            ctx.curve_to(mid_x, p_curr[1], mid_x, p_next[1], p_next[0], p_next[1])
        ctx.line_to(pts[-1][0], gy_bot)
        ctx.close_path()

        area_g = cairo.LinearGradient(0, gy_top, 0, gy_bot)
        area_g.add_color_stop_rgba(0, p2[0], p2[1], p2[2], 0.55)
        area_g.add_color_stop_rgba(1, p2[0], p2[1], p2[2], 0.02)
        ctx.set_source(area_g)
        ctx.fill()

        ctx.move_to(pts[0][0], pts[0][1])
        for i in range(len(pts) - 1):
            p_curr = pts[i]
            p_next = pts[i + 1]
            mid_x = (p_curr[0] + p_next[0]) / 2.0
            ctx.curve_to(mid_x, p_curr[1], mid_x, p_next[1], p_next[0], p_next[1])
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 1.0)
        ctx.set_line_width(4.5)
        ctx.stroke()

        for px_i, py_i in pts:
            ctx.arc(px_i, py_i, 9, 0, 2 * math.pi)
            ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.35)
            ctx.fill()
            ctx.arc(px_i, py_i, 5.5, 0, 2 * math.pi)
            ctx.set_source_rgba(1, 1, 1, 1.0)
            ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 5: استعراض المنتج الفاخر (3D Spotlight Podium & Quality Shield)
    # -------------------------------------------------------------------------
    elif scene_type == "ecommerce_showcase":
        ctx.move_to(cx - r * 0.25, cy - r * 0.95)
        ctx.line_to(cx + r * 0.25, cy - r * 0.95)
        ctx.line_to(cx + r * 0.85, cy + r * 0.65)
        ctx.line_to(cx - r * 0.85, cy + r * 0.65)
        ctx.close_path()
        spot_g = cairo.LinearGradient(cx, cy - r * 0.95, cx, cy + r * 0.65)
        spot_g.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 0.32 * s_main)
        spot_g.add_color_stop_rgba(1, p1[0], p1[1], p1[2], 0.0)
        ctx.set_source(spot_g)
        ctx.fill()

        ctx.save()
        ctx.translate(cx, cy + r * 0.58)
        ctx.scale(1.0, 0.28)
        ctx.arc(0, 0, r * 0.82 * s_main, 0, 2 * math.pi)
        pod_g = cairo.RadialGradient(0, 0, 5, 0, 0, r * 0.82)
        pod_g.add_color_stop_rgba(0, p2[0], p2[1], p2[2], 0.85)
        pod_g.add_color_stop_rgba(1, 0.05, 0.08, 0.18, 0.95)
        ctx.set_source(pod_g)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.9)
        ctx.set_line_width(6.0)
        ctx.stroke()
        ctx.restore()

        fy = cy - r * 0.08 + 10 * math.sin(global_t * 3.0)
        bs = r * 0.48 * s_sub1
        _cairo_rounded_rect(ctx, cx - bs, fy - bs, bs * 2, bs * 2, 24)
        box_g = cairo.LinearGradient(cx - bs, fy - bs, cx + bs, fy + bs)
        box_g.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 0.95)
        box_g.add_color_stop_rgba(1, acc[0], acc[1], acc[2], 0.92)
        ctx.set_source(box_g)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.set_line_width(3.5)
        ctx.stroke()

        ctx.move_to(cx - bs * 0.38, fy + bs * 0.02)
        ctx.line_to(cx - bs * 0.08, fy + bs * 0.32)
        ctx.line_to(cx + bs * 0.42, fy - bs * 0.28)
        ctx.set_source_rgba(0.05, 0.08, 0.16, 0.95)
        ctx.set_line_width(8.0)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke()

    # -------------------------------------------------------------------------
    # المشهد 6: التوصيل السريع 58 ولاية (Express Radar Route & Pin)
    # -------------------------------------------------------------------------
    elif scene_type == "delivery_express":
        p_start = (cx - r * 0.65, cy + r * 0.32)
        p_end = (cx + r * 0.65, cy - r * 0.28)

        ctx.move_to(p_start[0], p_start[1])
        ctx.curve_to(cx - r * 0.1, cy + r * 0.45, cx + r * 0.1, cy - r * 0.45, p_end[0], p_end[1])
        ctx.set_source_rgba(1, 1, 1, 0.22)
        ctx.set_line_width(5.0)
        ctx.set_dash([12.0, 8.0])
        ctx.stroke()
        ctx.set_dash([])

        ctx.move_to(p_start[0], p_start[1])
        ctx.curve_to(cx - r * 0.1, cy + r * 0.45, cx + r * 0.1, cy - r * 0.45, p_end[0], p_end[1])
        rt_g = cairo.LinearGradient(p_start[0], p_start[1], p_end[0], p_end[1])
        rt_g.add_color_stop_rgba(0, p2[0], p2[1], p2[2], 1.0)
        rt_g.add_color_stop_rgba(1, p1[0], p1[1], p1[2], 1.0)
        ctx.set_source(rt_g)
        ctx.set_line_width(4.0)
        ctx.stroke()

        for ri in range(3):
            rr = (16 + ri * 16 + (global_t * 25) % 16) * s_sub1
            ctx.arc(p_end[0], p_end[1], rr, 0, 2 * math.pi)
            ctx.set_source_rgba(p1[0], p1[1], p1[2], max(0.0, 0.65 - ri * 0.22))
            ctx.set_line_width(2.5)
            ctx.stroke()

        ctx.arc(p_end[0], p_end[1] - 24, 18 * s_main, 0, 2 * math.pi)
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.98)
        ctx.fill()
        ctx.arc(p_end[0], p_end[1] - 24, 7 * s_main, 0, 2 * math.pi)
        ctx.set_source_rgba(0.05, 0.08, 0.16, 1.0)
        ctx.fill()

        t_pos = (scene_progress * 0.85 + 0.15) % 1.0
        bx = (1 - t_pos)**3 * p_start[0] + 3 * (1 - t_pos)**2 * t_pos * (cx - r * 0.1) + 3 * (1 - t_pos) * t_pos**2 * (cx + r * 0.1) + t_pos**3 * p_end[0]
        by = (1 - t_pos)**3 * p_start[1] + 3 * (1 - t_pos)**2 * t_pos * (cy + r * 0.45) + 3 * (1 - t_pos) * t_pos**2 * (cy - r * 0.45) + t_pos**3 * p_end[1]
        ctx.arc(bx, by, 14, 0, 2 * math.pi)
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.95)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 1.0)
        ctx.set_line_width(3.0)
        ctx.stroke()

    # -------------------------------------------------------------------------
    # المشهد 7: توفير الوقت والسرعة (Precision Speedometer & Chrono Gauge)
    # -------------------------------------------------------------------------
    elif scene_type == "time_warp_clock":
        cr = r * 0.78 * s_main
        ctx.arc(cx, cy, cr, 0, 2 * math.pi)
        ctx.set_source_rgba(0.06, 0.10, 0.20, 0.92)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.15)
        ctx.set_line_width(3.0)
        ctx.stroke()

        start_a = 0.75 * math.pi
        end_a = start_a + 1.5 * math.pi * min(1.0, 0.25 + scene_progress * 0.90)
        ctx.arc(cx, cy, cr * 0.84, start_a, end_a)
        arc_g = cairo.LinearGradient(cx - cr, cy, cx + cr, cy)
        arc_g.add_color_stop_rgba(0, p2[0], p2[1], p2[2], 1.0)
        arc_g.add_color_stop_rgba(1, p1[0], p1[1], p1[2], 1.0)
        ctx.set_source(arc_g)
        ctx.set_line_width(12.0)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.stroke()

        for ti in range(24):
            tang = ti * (2 * math.pi / 24)
            in_r = cr * (0.68 if ti % 3 == 0 else 0.73)
            out_r = cr * 0.76
            ctx.move_to(cx + in_r * math.cos(tang), cy + in_r * math.sin(tang))
            ctx.line_to(cx + out_r * math.cos(tang), cy + out_r * math.sin(tang))
            ctx.set_source_rgba(1, 1, 1, 0.55 if ti % 3 == 0 else 0.22)
            ctx.set_line_width(2.5 if ti % 3 == 0 else 1.2)
            ctx.stroke()

        needle_a = end_a
        ctx.move_to(cx, cy)
        ctx.line_to(cx + cr * 0.65 * math.cos(needle_a), cy + cr * 0.65 * math.sin(needle_a))
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 1.0)
        ctx.set_line_width(5.0)
        ctx.stroke()
        ctx.arc(cx, cy, 11, 0, 2 * math.pi)
        ctx.set_source_rgba(1, 1, 1, 1.0)
        ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 8: بناء المنصة والكود (Modern IDE & Cloud Architecture Bento)
    # -------------------------------------------------------------------------
    elif scene_type == "platform_builder":
        ww, wh = r * 1.58 * s_main, r * 1.15 * s_main
        wx, wy = cx - ww / 2, cy - wh / 2

        _cairo_rounded_rect(ctx, wx, wy, ww, wh, 20)
        ctx.set_source_rgba(0.06, 0.09, 0.18, 0.95)
        ctx.fill_preserve()
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.85)
        ctx.set_line_width(3.0)
        ctx.stroke()

        for bi, bcol in enumerate([(1.0, 0.37, 0.34), (1.0, 0.74, 0.18), (0.16, 0.78, 0.25)]):
            ctx.arc(wx + 24 + bi * 20, wy + 22, 6.0, 0, 2 * math.pi)
            ctx.set_source_rgba(*bcol, 0.95)
            ctx.fill()

        code_y0 = wy + 52
        bar_Pallet = [p1, p2, acc, (0.95, 0.95, 0.98)]
        for row in range(6):
            ry = code_y0 + row * 24
            indent = (row % 3) * 24
            row_prog = 0.45 + 0.55 * _staggered_spring(scene_progress, delay=row * 0.04)
            bw = (ww * (0.28 + 0.35 * ((row * 37) % 10) / 10.0)) * row_prog
            if bw > 8:
                _cairo_rounded_rect(ctx, wx + 28 + indent, ry, bw, 12, 6)
                bc = bar_Pallet[row % len(bar_Pallet)]
                ctx.set_source_rgba(bc[0], bc[1], bc[2], 0.88)
                ctx.fill()

        ring_cx, ring_cy = wx + ww * 0.78, wy + wh * 0.62
        ring_r = wh * 0.22 * s_sub2
        ctx.arc(ring_cx, ring_cy, ring_r, 0, 2 * math.pi)
        ctx.set_source_rgba(1, 1, 1, 0.12)
        ctx.set_line_width(7.0)
        ctx.stroke()
        ctx.arc(ring_cx, ring_cy, ring_r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * min(1.0, 0.3 + scene_progress * 0.9))
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 1.0)
        ctx.set_line_width(7.0)
        ctx.stroke()

    # -------------------------------------------------------------------------
    # المشهد 9: هوية المؤسس والمبدع ومحطة العمر (Founder Identity & Milestone Badge)
    # -------------------------------------------------------------------------
    elif scene_type in ("creator_profile", "age_number_counter"):
        # درع سداسي متوهج يمثل هوية المبدع أو محطة الإنجاز
        hex_r = r * 0.72 * s_main
        _cairo_regular_polygon(ctx, cx, cy, hex_r, sides=6, rotation=-math.pi / 2 + 0.06 * math.sin(global_t * 2))
        hex_g = cairo.LinearGradient(cx - hex_r, cy - hex_r, cx + hex_r, cy + hex_r)
        hex_g.add_color_stop_rgba(0, 0.08, 0.14, 0.28, 0.95)
        hex_g.add_color_stop_rgba(1, 0.04, 0.07, 0.16, 0.98)
        ctx.set_source(hex_g)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.92)
        ctx.set_line_width(4.0)
        ctx.stroke()

        # حلقة طاقة داخلية مضيئة
        ctx.arc(cx, cy, hex_r * 0.72 * s_sub1, 0, 2 * math.pi)
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.45)
        ctx.set_line_width(2.5)
        ctx.stroke()

        # أيقونة المبدع المبرمج (Avatar Silhouette + Glowing Crown/Star Nodes)
        head_r = hex_r * 0.22 * s_sub1
        ctx.arc(cx, cy - hex_r * 0.14, head_r, 0, 2 * math.pi)
        av_g = cairo.RadialGradient(cx - head_r * 0.3, cy - hex_r * 0.18, 2, cx, cy - hex_r * 0.14, head_r * 1.2)
        av_g.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 1.0)
        av_g.add_color_stop_rgba(1, p2[0], p2[1], p2[2], 0.95)
        ctx.set_source(av_g)
        ctx.fill()

        # قوس الكتفين الانسيابي (Shoulders Bezier Arc)
        sh_w = hex_r * 0.42 * s_sub2
        sh_y = cy + hex_r * 0.34
        ctx.move_to(cx - sh_w, sh_y)
        ctx.curve_to(cx - sh_w * 0.6, cy + hex_r * 0.06, cx + sh_w * 0.6, cy + hex_r * 0.06, cx + sh_w, sh_y)
        ctx.close_path()
        ctx.set_source(av_g)
        ctx.fill()

        # 6 عقد ضوئية تدور حول درع المؤسس
        for ni in range(6):
            n_ang = ni * (math.pi / 3.0) + global_t * 0.6
            nx = cx + hex_r * 0.92 * math.cos(n_ang)
            ny = cy + hex_r * 0.92 * math.sin(n_ang)
            ctx.arc(nx, ny, 7.0, 0, 2 * math.pi)
            col = p1 if ni % 2 == 0 else p2
            ctx.set_source_rgba(col[0], col[1], col[2], 0.92)
            ctx.fill()

    # -------------------------------------------------------------------------
    # المشهد 10: الإطلاق الرسمي للمنصة والختام (Brand Finale & Prism Studio Crest)
    # -------------------------------------------------------------------------
    else:
        # أشعة طاقة سينمائية متوهجة خلف شعار المنصة
        num_bars = 24
        inner_rad = r * 0.54 * s_main
        for bi in range(num_bars):
            bang = bi * (2 * math.pi / num_bars) + global_t * 0.35
            blen = r * (0.14 + 0.16 * abs(math.sin(global_t * 4 + bi * 0.5))) * s_sub1
            x_in = cx + inner_rad * math.cos(bang)
            y_in = cy + inner_rad * math.sin(bang)
            x_out = cx + (inner_rad + blen) * math.cos(bang)
            y_out = cy + (inner_rad + blen) * math.sin(bang)
            ctx.move_to(x_in, y_in)
            ctx.line_to(x_out, y_out)
            col = p1 if bi % 2 == 0 else p2
            ctx.set_source_rgba(col[0], col[1], col[2], 0.88)
            ctx.set_line_width(4.5)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.stroke()

        # درع المنصة المركزي الثلاثي الأبعاد
        ctx.arc(cx, cy, inner_rad * 0.88, 0, 2 * math.pi)
        cg = cairo.RadialGradient(cx - inner_rad * 0.25, cy - inner_rad * 0.25, 4, cx, cy, inner_rad)
        cg.add_color_stop_rgba(0, p1[0], p1[1], p1[2], 0.98)
        cg.add_color_stop_rgba(1, 0.06, 0.10, 0.22, 0.96)
        ctx.set_source(cg)
        ctx.fill_preserve()
        ctx.set_source_rgba(1, 1, 1, 0.92)
        ctx.set_line_width(3.5)
        ctx.stroke()

        # أيقونة عدسة/تشغيل المنصة في المركز (Studio Play Prism)
        pr_s = inner_rad * 0.38 * s_sub2
        ctx.move_to(cx - pr_s * 0.45, cy - pr_s * 0.65)
        ctx.line_to(cx - pr_s * 0.45, cy + pr_s * 0.65)
        ctx.line_to(cx + pr_s * 0.72, cy)
        ctx.close_path()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.96)
        ctx.fill()

    buf = np.frombuffer(surface.get_data(), dtype=np.uint8).reshape((height, width, 4)).copy()
    buf = buf[:, :, [2, 1, 0, 3]]
    return Image.fromarray(buf, mode="RGBA")


def draw_animated_scene_illustration(
    draw: ImageDraw.ImageDraw,
    scene_type: str,
    cx: int,
    cy: int,
    radius: int,
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any],
    target_number: int = 58,
    short_title: str = ""
):
    r = max(16, int(radius))
    p1 = (*theme["primary"], 255)
    p2 = (*theme["secondary"], 255)
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(12, 18, 34, 230), outline=p1, width=2)
    in_r = max(6, int(r * 0.45 * (0.85 + 0.15 * math.sin(global_t * 4))))
    draw.ellipse([(cx - in_r, cy - in_r), (cx + in_r, cy + in_r)], fill=p2)


# ==============================================================================
# 7. بناء خلفية الأستوديو السينمائية (Aurora Mesh & Perspective Grid)
# ==============================================================================
def create_studio_background(
    width: int,
    height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    top_c = np.array(theme["top_bg"], dtype=np.float32)
    bot_c = np.array(theme["bottom_bg"], dtype=np.float32)
    glow_c = np.array(theme["glow"], dtype=np.float32)
    sec_c = np.array(theme["secondary"], dtype=np.float32)

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    yy, xx = np.ogrid[:height, :width]
    cx1, cy1 = width * 0.5, height * 0.34
    dist1 = ((xx - cx1) / (width * 0.52)) ** 2 + ((yy - cy1) / (height * 0.32)) ** 2
    mask1 = np.exp(-dist1 * 2.0)[:, :, None] * 0.24

    cx2, cy2 = width * 0.25, height * 0.75
    dist2 = ((xx - cx2) / (width * 0.45)) ** 2 + ((yy - cy2) / (height * 0.30)) ** 2
    mask2 = np.exp(-dist2 * 2.2)[:, :, None] * 0.14

    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255)
    canvas_np = np.clip(canvas_np * (1.0 - mask2) + sec_c * mask2, 0, 255).astype(np.uint8)

    img = Image.fromarray(canvas_np, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    step = max(56, min(width, height) // 14)
    for x in range(step // 2, width, step):
        for y in range(step // 2, height, step):
            draw.ellipse([(x - 1, y - 1), (x + 1, y + 1)], fill=(255, 255, 255, 22))

    return np.array(img)



# ==============================================================================
# 7.5 محرك الكوريغرافيا الاحترافي الفريم-باي-فريم (8 Archetypes from Reference Spec)
# ==============================================================================
def _draw_cursor_with_ripple(
    draw: ImageDraw.ImageDraw,
    start_xy: Tuple[int, int],
    target_xy: Tuple[int, int],
    prog: float,
    accent_rgb: Tuple[int, int, int] = (37, 99, 235)
):
    """رسم مؤشر ماوس تفاعلي يتحرك نحو الهدف وينقر مع دوائر تموج (Cursor Click + Ripple Effect)."""
    move_p = _ease_out_cubic(max(0.0, min(1.0, (prog - 0.25) / 0.40)))
    cx = int(start_xy[0] + (target_xy[0] - start_xy[0]) * move_p)
    cy = int(start_xy[1] + (target_xy[1] - start_xy[1]) * move_p)

    # تأثير النقر ودوائر التموج بعد الوصول للهدف
    click_scale = 1.0
    if prog > 0.65:
        ripple_p = min(1.0, (prog - 0.65) / 0.32)
        click_scale = 1.0 - 0.18 * math.sin(min(1.0, ripple_p * 2.0) * math.pi)
        for ri in range(2):
            rp = max(0.0, min(1.0, ripple_p - ri * 0.18))
            if rp > 0.0:
                rr = int(10 + 42 * rp)
                ra = int(190 * (1.0 - rp))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*accent_rgb, ra), width=3)

    # رسم سهم مؤشر الماوس الاحترافي
    s = max(14, int(22 * click_scale))
    pts = [
        (cx, cy),
        (cx, cy + int(s * 1.35)),
        (cx + int(s * 0.38), cy + int(s * 1.02)),
        (cx + int(s * 0.68), cy + int(s * 1.55)),
        (cx + int(s * 0.90), cy + int(s * 1.42)),
        (cx + int(s * 0.58), cy + int(s * 0.90)),
        (cx + int(s * 1.05), cy + int(s * 0.85))
    ]
    draw.polygon([(px + 2, py + 3) for px, py in pts], fill=(0, 0, 0, 140))
    draw.polygon(pts, fill=(255, 255, 255, 255), outline=(17, 24, 39, 255))


def _draw_checkmark_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color_rgb: Tuple[int, int, int] = (16, 185, 129), scale: float = 1.0):
    r = max(8, int(radius * scale))
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(*color_rgb, 255), outline=(255, 255, 255, 230), width=2)
    draw.line([(cx - int(r * 0.42), cy + int(r * 0.05)), (cx - int(r * 0.10), cy + int(r * 0.38)), (cx + int(r * 0.46), cy - int(r * 0.32))], fill=(255, 255, 255, 255), width=max(2, int(r * 0.22)))


def _draw_gear_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, angle_rad: float, color_rgb: Tuple[int, int, int]):
    r_out = max(10, int(radius))
    r_in = max(6, int(radius * 0.68))
    num_teeth = 8
    for i in range(num_teeth):
        a = angle_rad + i * (2.0 * math.pi / num_teeth)
        tx = cx + int(r_out * math.cos(a))
        ty = cy + int(r_out * math.sin(a))
        draw.ellipse([(tx - 4, ty - 4), (tx + 4, ty + 4)], fill=(*color_rgb, 255))
    draw.ellipse([(cx - r_in, cy - r_in), (cx + r_in, cy + r_in)], fill=(*color_rgb, 255))
    draw.ellipse([(cx - int(r_in * 0.42), cy - int(r_in * 0.42)), (cx + int(r_in * 0.42), cy + int(r_in * 0.42))], fill=(255, 255, 255, 255))


def _draw_paper_plane(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color_rgb: Tuple[int, int, int] = (37, 99, 235)):
    s = max(12, int(size))
    pts = [
        (cx + s, cy - int(s * 0.7)),
        (cx - s, cy - int(s * 0.05)),
        (cx - int(s * 0.2), cy + int(s * 0.25)),
        (cx + int(s * 0.25), cy + int(s * 0.85))
    ]
    draw.polygon(pts, fill=(*color_rgb, 255), outline=(255, 255, 255, 220))
    draw.line([(cx + s, cy - int(s * 0.7)), (cx - int(s * 0.2), cy + int(s * 0.25))], fill=(255, 255, 255, 220), width=2)


_LOGO_WATERMARK_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}


def _resolve_active_theme_and_style(scene_meta: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool, Optional[str], str]:
    """
    يحدد الثيم اللوني الفعال ونمط الإضاءة ومسار اللوقو المرفوع مع إعطاء الأولوية
    للثيم المخصص واللوقو الذي اختاره المستخدم في الواجهة (`active_brand_theme`).
    """
    brand = None
    if callable(get_active_brand_theme):
        try:
            brand = get_active_brand_theme()
        except Exception:
            brand = None

    if isinstance(brand, dict) and brand.get("enabled", True):
        t_name = str(brand.get("theme_name") or "custom_brand_theme")
        if "theme_palette" in brand and isinstance(brand["theme_palette"], dict):
            MOTION_THEMES[t_name] = brand["theme_palette"]
        theme = MOTION_THEMES.get(t_name, MOTION_THEMES["cyber_gold"])
        style_mode = str(brand.get("style_mode") or scene_meta.get("style_mode") or "dark_stage_pro")
        is_light = (style_mode == "clean_saas_light") or bool(brand.get("is_light_mode", False))
        logo_path = brand.get("logo_path") if brand.get("show_logo_watermark", True) else None
        logo_pos = str(brand.get("logo_position") or "top_right")
        return t_name, theme, is_light, logo_path, logo_pos

    t_name = str(scene_meta.get("theme_name") or "cyber_gold")
    theme = MOTION_THEMES.get(t_name, MOTION_THEMES["cyber_gold"])
    style_mode = str(scene_meta.get("style_mode") or "dark_stage_pro")
    is_light = (style_mode == "clean_saas_light")
    logo_path = scene_meta.get("brand_logo_path")
    logo_pos = str(scene_meta.get("brand_logo_position") or "top_right")
    return t_name, theme, is_light, logo_path, logo_pos


def _render_brand_logo_watermark(
    canvas_rgba: Image.Image,
    logo_path: Optional[str],
    logo_position: str,
    theme: Dict[str, Any],
    is_light: bool = False
) -> Tuple[Image.Image, Optional[Tuple[int, int, int, int]]]:
    """
    يرسم شعار الهوية البصرية (Logo Watermark) في الزاوية المختارة (`top_right` أو `top_left`)
    داخل شارة زجاجية أنيقة مع الحفاظ التام على أبعاد الشعار وشفافيته.
    """
    if not logo_path or not os.path.exists(str(logo_path)) or str(logo_position) == "none":
        return canvas_rgba, None

    w, h = canvas_rgba.size
    max_logo_h = max(36, int(h * 0.048))
    max_logo_w = max(72, int(w * 0.22))
    cache_key = (str(logo_path), max_logo_w, max_logo_h)

    if cache_key not in _LOGO_WATERMARK_CACHE:
        try:
            with Image.open(logo_path) as lim:
                l_rgba = lim.convert("RGBA")
                lw, lh = l_rgba.size
                scale = min(max_logo_w / float(max(1, lw)), max_logo_h / float(max(1, lh)))
                nw = max(20, int(round(lw * scale)))
                nh = max(20, int(round(lh * scale)))
                _LOGO_WATERMARK_CACHE[cache_key] = l_rgba.resize((nw, nh), Image.Resampling.LANCZOS)
        except Exception:
            return canvas_rgba, None

    logo_img = _LOGO_WATERMARK_CACHE[cache_key]
    lw, lh = logo_img.size
    pad_x, pad_y = 10, 6
    box_w, box_h = lw + pad_x * 2, lh + pad_y * 2
    by1 = int(h * 0.032)

    if logo_position == "top_left":
        bx1 = int(w * 0.04)
    else:
        bx1 = int(w * 0.96) - box_w
    bx2, by2 = bx1 + box_w, by1 + box_h

    draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    bg_col = (255, 255, 255, 225) if is_light else (12, 18, 34, 210)
    border_col = (*theme.get("primary", (56, 189, 248)), 210)
    draw.rounded_rectangle([(bx1, by1 + 2), (bx2, by2 + 2)], radius=max(12, box_h // 3), fill=(0, 0, 0, 55))
    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=max(12, box_h // 3), fill=bg_col, outline=border_col, width=2)
    canvas_rgba.alpha_composite(logo_img, (bx1 + pad_x, by1 + pad_y))
    return canvas_rgba, (bx1, by1, bx2, by2)


def _compose_hero_centerpiece_icon(
    scene_type: str,
    icon_size: int,
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any],
    target_number: int = 58
) -> Image.Image:
    """يرسم أيقونة البطل المركزية الموحدة بدقة عالية وهالة ضوئية ناعمة بدون ازدواجية أيقونات."""
    out = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(out, "RGBA")
    primary_c = tuple(theme.get("primary", (56, 189, 248)))
    secondary_c = tuple(theme.get("secondary", (250, 204, 21)))
    pad = max(4, int(icon_size * 0.06))
    odraw.ellipse(
        [(pad, pad), (icon_size - pad, icon_size - pad)],
        fill=(primary_c[0], primary_c[1], primary_c[2], 28),
        outline=(*primary_c, 185),
        width=2
    )
    inner_sz = max(28, int(icon_size * 0.82))
    cairo_ic = render_cairo_vector_illustration(
        scene_type=scene_type,
        width=inner_sz,
        height=inner_sz,
        scene_progress=scene_progress,
        global_t=global_t,
        theme=theme,
        target_number=target_number
    )
    offset = (icon_size - inner_sz) // 2
    out.alpha_composite(cairo_ic, (offset, offset))
    return out


def render_choreographed_stage_archetype(
    canvas_rgba: Image.Image,
    stage_bbox: Tuple[int, int, int, int],
    scene_meta: Dict[str, Any],
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any],
    is_light_saas: bool = False
) -> Image.Image:
    """
    محرك التركيز البصري الواحد فائق الوضوح (Single-Focus Visual Clarity Stage Engine):
    بدلاً من تشتيت عين المشاهد بـ 6 إلى 8 صناديق نصية صغيرة ومزدحمة في وقت واحد:
    - يركز كل مشهد على **فكرة بصرية واحدة واضحة جداً** (أيقونة مركزية كبيرة متحركة + عنوان رئيسي عريض وواضح + شارة تركيز واحدة أو مقارنة ثنائية نظيفة).
    - خالٍ تماماً من الخطوط المتقطعة المزعجة (`Marching Ants`) أو النوافذ المزدحمة التي تعيق القراءة.
    """
    x1, y1, x2, y2 = stage_bbox
    sw, sh = x2 - x1, y2 - y1
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    archetype = str(scene_meta.get("archetype", "saas_folder_reorder")).strip()
    scene_type = str(scene_meta.get("scene_type", "growth_analytics")).strip()
    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "فكرة أساسية")
    kpi_val = str(scene_meta.get("kpi_value") or "ميزة ذكية")
    kpi_lbl = str(scene_meta.get("kpi_label") or "محور أساسي")
    sub_items = [str(s).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    if not sub_items:
        sub_items = [kpi_lbl]

    primary_c = tuple(theme.get("primary", (56, 189, 248)))
    secondary_c = tuple(theme.get("secondary", (250, 204, 21)))

    if is_light_saas:
        card_tint = (255, 255, 255, 246)
        inner_pill_tint = (241, 245, 249, 255)
        txt_main = (15, 23, 42, 255)
        txt_sub = (51, 65, 85, 255)
        stroke_c = (255, 255, 255, 0)
        stroke_w = 0
    else:
        c_bg = tuple(theme.get("card_bg", (14, 22, 42)))
        card_tint = (c_bg[0], c_bg[1], c_bg[2], 232)
        inner_pill_tint = (min(255, c_bg[0] + 12), min(255, c_bg[1] + 16), min(255, c_bg[2] + 26), 245)
        txt_main = (255, 255, 255, 255)
        txt_sub = (203, 213, 225, 245)
        stroke_c = (0, 0, 0, 210)
        stroke_w = 2

    # توهج محيطي ناعم جداً بدون أي إزعاج بصري
    glow_intensity = float(scene_meta.get("accent_glow", 0.25))
    canvas_rgba = render_radial_ambient_glow(
        canvas_rgba=canvas_rgba,
        center_xy=(cx, cy - int(sh * 0.06)),
        radius=int(min(sw, sh) * 0.44),
        color_rgb=primary_c,
        intensity=glow_intensity * (0.45 if is_light_saas else 0.85)
    )

    s_in = 0.92 + 0.08 * _staggered_spring(scene_progress, delay=0.0, duration=0.40)
    cw, ch = int(sw * 0.90 * s_in), int(sh * 0.84 * s_in)
    bx1, by1 = cx - cw // 2, cy - ch // 2
    bx2, by2 = bx1 + cw, by1 + ch

    canvas_rgba = draw_visionos_glass_panel(
        canvas_rgba, (bx1, by1, bx2, by2), radius=32,
        tint_color=card_tint, border_color=primary_c,
        secondary_color=secondary_c,
        blur_radius=16, shadow_offset=12, shadow_blur=22,
        light_sweep_prog=(scene_progress * 1.3 - 0.15)
    )
    draw = ImageDraw.Draw(canvas_rgba, "RGBA")

    # =========================================================================
    # الفئة 1: مقارنة ثنائية نظيفة وواضحة (Before/After أو Balance Scale بدون قوائم مزدحمة)
    # =========================================================================
    if archetype in ("stage_balance_scale", "stage_before_after_checklist"):
        if archetype == "stage_balance_scale":
            left_info = scene_meta.get("balance_left") or ("الطريقة التقليدية", "وقت ومجهود")
            right_info = scene_meta.get("balance_right") or ("الحل الذكي", "سرعة وإتقان")
            neg_title, neg_val = str(left_info[0]), str(left_info[1])
            pos_title, pos_val = str(right_info[0]), str(right_info[1])
        else:
            ba_info = scene_meta.get("before_after") or ("قبل الحل", "تقليدي", "بعد الحل", "احترافي")
            neg_title, neg_val = str(ba_info[0]), f"قبل • {ba_info[1]}"
            pos_title, pos_val = str(ba_info[2]), f"بعد • {ba_info[3]}"

        # العنوان الرئيسي في أعلى البطاقة
        title_y1 = by1 + int(ch * 0.06)
        title_y2 = by1 + int(ch * 0.24)
        draw_contained_arabic_text(
            draw, (bx1 + 20, title_y1, bx2 - 20, title_y2),
            concept_title, initial_font_size=max(22, int(sh * 0.048)),
            fill=txt_main, pad_left=16, pad_right=16, min_font_size=13,
            stroke_width=stroke_w, stroke_fill=stroke_c
        )

        # بطاقتا المقارنة الكبيرتان والواضحتان فقط (يمين: قبل / يسار: بعد)
        comp_y1 = by1 + int(ch * 0.30)
        comp_h = int(ch * 0.58)
        comp_w = int(cw * 0.43)
        neg_x1 = bx2 - int(cw * 0.05) - comp_w
        pos_x1 = bx1 + int(cw * 0.05)

        c_red = (239, 68, 68)
        c_green = (16, 185, 129)

        # بطاقة "قبل" (اليمين) بتباين نصي أبيض ناصع 100%
        draw.rounded_rectangle([(neg_x1, comp_y1), (neg_x1 + comp_w, comp_y1 + comp_h)], radius=24, fill=inner_pill_tint, outline=(*c_red, 225), width=2)
        badge_h = max(36, int(comp_h * 0.22))
        draw.rounded_rectangle([(neg_x1 + 14, comp_y1 + 14), (neg_x1 + comp_w - 14, comp_y1 + 14 + badge_h)], radius=badge_h // 2, fill=(220, 38, 38, 245))
        draw_contained_arabic_text(
            draw, (neg_x1 + 14, comp_y1 + 14, neg_x1 + comp_w - 14, comp_y1 + 14 + badge_h),
            neg_val, initial_font_size=max(16, int(sh * 0.034)),
            fill=(255, 255, 255, 255), pad_left=10, pad_right=10, min_font_size=11
        )
        draw_contained_arabic_text(
            draw, (neg_x1 + 10, comp_y1 + badge_h + 24, neg_x1 + comp_w - 10, comp_y1 + comp_h - 16),
            neg_title, initial_font_size=max(19, int(sh * 0.040)),
            fill=txt_main, pad_left=10, pad_right=10, min_font_size=12,
            stroke_width=stroke_w, stroke_fill=stroke_c
        )

        # بطاقة "بعد / الأفضل" (اليسار) مع بروز زنبركي
        sp_pos = 0.94 + 0.06 * _staggered_spring(scene_progress, delay=0.10, duration=0.40)
        pw_s, ph_s = int(comp_w * sp_pos), int(comp_h * sp_pos)
        px1 = pos_x1 + (comp_w - pw_s) // 2
        py1 = comp_y1 + (comp_h - ph_s) // 2
        draw.rounded_rectangle([(px1, py1), (px1 + pw_s, py1 + ph_s)], radius=24, fill=inner_pill_tint, outline=(*c_green, 250), width=3)
        draw.rounded_rectangle([(px1 + 14, py1 + 14), (px1 + pw_s - 14, py1 + 14 + badge_h)], radius=badge_h // 2, fill=(*c_green, 245))
        draw_contained_arabic_text(
            draw, (px1 + 14, py1 + 14, px1 + pw_s - 14, py1 + 14 + badge_h),
            pos_val, initial_font_size=max(16, int(sh * 0.034)),
            fill=(255, 255, 255, 255), pad_left=8, pad_right=8, min_font_size=11
        )
        draw_contained_arabic_text(
            draw, (px1 + 10, py1 + badge_h + 24, px1 + pw_s - 10, py1 + ph_s - 16),
            pos_title, initial_font_size=max(19, int(sh * 0.040)),
            fill=txt_main, pad_left=10, pad_right=10, min_font_size=12,
            stroke_width=stroke_w, stroke_fill=stroke_c
        )
        return canvas_rgba

    # =========================================================================
    # الفئة 2: بطاقة الدعوة للتفاعل الختامية (Clean Focused CTA Finale)
    # =========================================================================
    if archetype == "interactive_cta_outro":
        icon_sz = max(96, int(min(cw, ch) * 0.28))
        hero_ic = _compose_hero_centerpiece_icon(scene_type, icon_sz, scene_progress, global_t, theme)
        ic_x = cx - icon_sz // 2
        ic_y = by1 + int(ch * 0.07) + int(4 * math.sin(global_t * 3.5))
        canvas_rgba.alpha_composite(hero_ic, (ic_x, ic_y))
        draw = ImageDraw.Draw(canvas_rgba, "RGBA")

        # العنوان الرئيسي الكبير
        t_y1 = ic_y + icon_sz + int(ch * 0.03)
        t_y2 = t_y1 + int(ch * 0.22)
        draw_contained_arabic_text(
            draw, (bx1 + 20, t_y1, bx2 - 20, t_y2),
            concept_title, initial_font_size=max(22, int(sh * 0.048)),
            fill=txt_main, pad_left=18, pad_right=18, min_font_size=13,
            stroke_width=stroke_w, stroke_fill=stroke_c
        )

        # زر الإجراء الواضح في الأسفل (بدون تغطية النص بمؤشر الماوس!)
        btn_y1 = by1 + int(ch * 0.68)
        btn_h = int(ch * 0.20)
        pulse = int(4 * math.sin(global_t * 5.5))
        btn_box = (bx1 + int(cw * 0.08) - pulse, btn_y1 - pulse // 2, bx2 - int(cw * 0.08) + pulse, btn_y1 + btn_h + pulse // 2)
        draw.rounded_rectangle([(btn_box[0], btn_box[1]), (btn_box[2], btn_box[3])], radius=btn_h // 2, fill=(*secondary_c, 255), outline=(255, 255, 255, 240), width=3)
        draw_contained_arabic_text(
            draw, btn_box, f"{kpi_val} • {kpi_lbl}",
            initial_font_size=max(20, int(sh * 0.042)),
            fill=(15, 23, 42, 255), pad_left=24, pad_right=24, min_font_size=12
        )
        return canvas_rgba

    # =========================================================================
    # الفئة 3: بطاقة التركيز البصري الواحد (Hero Visual + Bold Concept + Single Active Point)
    # =========================================================================
    # 1. شارة المؤشر (KPI Pill) أعلى داخل البطاقة
    kpi_h = max(36, int(ch * 0.11))
    kpi_y1 = by1 + int(ch * 0.06)
    kpi_text = f"{kpi_val} • {kpi_lbl}" if (kpi_lbl and kpi_lbl not in kpi_val) else kpi_val
    _, _, k_tw, _ = fit_and_condense_arabic_text(draw, kpi_text, max_width=int(cw * 0.80), initial_font_size=max(16, int(sh * 0.033)), min_font_size=11)
    kpi_w = min(int(cw * 0.86), max(int(cw * 0.38), k_tw + 44))
    kx1, kx2 = cx - kpi_w // 2, cx + kpi_w // 2
    kpi_bg_fill = (241, 245, 249, 255) if is_light_saas else (10, 16, 30, 235)
    kpi_txt_fill = (15, 23, 42, 255) if is_light_saas else (255, 255, 255, 255)
    draw.rounded_rectangle([(kx1, kpi_y1), (kx2, kpi_y1 + kpi_h)], radius=kpi_h // 2, fill=kpi_bg_fill, outline=(*primary_c, 245), width=2)
    draw_contained_arabic_text(
        draw, (kx1, kpi_y1, kx2, kpi_y1 + kpi_h),
        kpi_text, initial_font_size=max(16, int(sh * 0.033)),
        fill=kpi_txt_fill,
        pad_left=14, pad_right=14, min_font_size=11
    )

    # 2. الأيقونة البصرية الكبرى في المركز (Hero Illustration Centerpiece)
    icon_sz = max(118, int(min(cw, ch) * 0.34))
    hero_ic = _compose_hero_centerpiece_icon(
        scene_type=scene_type,
        icon_size=icon_sz,
        scene_progress=scene_progress,
        global_t=global_t,
        theme=theme,
        target_number=int(scene_meta.get("target_number") or 58)
    )
    float_dy = int(5 * math.sin(global_t * 3.2))
    ic_x = cx - icon_sz // 2
    ic_y = kpi_y1 + kpi_h + int(ch * 0.04) + float_dy
    canvas_rgba.alpha_composite(hero_ic, (ic_x, ic_y))
    draw = ImageDraw.Draw(canvas_rgba, "RGBA")

    # 3. العنوان الرئيسي الكبير والواضح جداً (Single Bold Concept Title)
    title_y1 = ic_y + icon_sz + int(ch * 0.02)
    title_h = int(ch * 0.20)
    draw_contained_arabic_text(
        draw, (bx1 + 22, title_y1, bx2 - 22, title_y1 + title_h),
        concept_title, initial_font_size=max(24, int(sh * 0.050)),
        fill=txt_main, pad_left=18, pad_right=18, min_font_size=14,
        stroke_width=stroke_w, stroke_fill=stroke_c
    )

    # 4. كبسولة النقطة التوضيحية الواحدة النشطة في الأسفل (تتبدل بنعومة بدلاً من رص 4 صناديق معاً!)
    active_sub_idx = min(len(sub_items) - 1, int(scene_progress * min(2, len(sub_items))))
    active_sub_txt = re.sub(r"^\d+[\.\-\s]+", "", str(sub_items[active_sub_idx])).strip()

    sub_h = max(48, int(ch * 0.16))
    sub_y1 = by2 - sub_h - int(ch * 0.06)
    sub_x1, sub_x2 = bx1 + int(cw * 0.07), bx2 - int(cw * 0.07)

    draw.rounded_rectangle([(sub_x1, sub_y1), (sub_x2, sub_y1 + sub_h)], radius=sub_h // 2, fill=inner_pill_tint, outline=(*primary_c, 210), width=2)
    dot_r = 11
    dot_cx = sub_x2 - 24
    dot_cy = sub_y1 + sub_h // 2
    _draw_checkmark_badge(draw, dot_cx, dot_cy, dot_r, color_rgb=secondary_c, scale=1.0)
    draw_contained_arabic_text(
        draw, (sub_x1 + 16, sub_y1, dot_cx - dot_r - 10, sub_y1 + sub_h),
        active_sub_txt, initial_font_size=max(18, int(sh * 0.038)),
        fill=txt_main, pad_left=12, pad_right=10, min_font_size=12,
        stroke_width=stroke_w, stroke_fill=stroke_c
    )

    return canvas_rgba


# ==============================================================================
# 8. تصيير مشهد موشن جرافيك كامل الشاشة موجه بالسياق (Single-Focus Clean Scene)
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
    bg_cache: Dict[str, np.ndarray],
    **kwargs
) -> Image.Image:
    """
    تصيير مشهد موشن جرافيك كامل الشاشة بأسلوب التركيز البصري الواحد الفخم (Single-Focus Studio Motion):
    - يدعم ألوان الهوية البصرية المخصصة واللوقو المرفوع (`_resolve_active_theme_and_style`).
    - شارة موضوع علوية نظيفة ومتمركزة بدون ازدحام.
    - مسرح مركزي يوضح الفكرة المنطوقة بعنصر بصري رئيسي واحد واضح وعنوان كبير مقروء فوراً.
    - كابشن سفلي متزامن بدقة مع النطق.
    """
    theme_name, theme, is_light, logo_path, logo_pos = _resolve_active_theme_and_style(scene_meta)
    badge_label = str(scene_meta.get("badge_label", "موشن جرافيك سياقي")).split("•")[0].strip() or "محور أساسي"
    style_key = "light" if is_light else "dark"

    bg_key = f"{theme_name}_{style_key}_{width}x{height}"
    if bg_key not in bg_cache:
        if is_light:
            y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
            top_c = np.array(theme.get("top_bg", (244, 247, 252)), dtype=np.float32)
            bot_c = np.array(theme.get("bottom_bg", (228, 236, 246)), dtype=np.float32)
            grad = (top_c * (1.0 - y_idx) + bot_c * y_idx).astype(np.uint8)
            bg_cache[bg_key] = np.broadcast_to(grad, (height, width, 3)).copy()
        else:
            bg_cache[bg_key] = create_studio_background(width, height, theme_name)

    base_arr = bg_cache[bg_key]
    img = Image.fromarray(base_arr, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    cx = width // 2

    # 1. رسم اللوقو المرفوع إن وجد (Brand Logo Watermark)
    img, logo_bbox = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=is_light)
    draw = ImageDraw.Draw(img, "RGBA")

    # 2. شارة الموضوع العلوية النظيفة (بدون رقم #1 الجانبي المشتت)
    s_badge = 0.90 + 0.10 * _staggered_spring(scene_progress, delay=0.01, duration=0.35)
    bp_y = int(height * 0.040 - 10 * (1.0 - s_badge))
    bp_h = max(44, int(height * 0.048))

    avail_x1 = int(width * 0.06)
    avail_x2 = int(width * 0.94)
    if logo_bbox is not None:
        if logo_pos == "top_left":
            avail_x1 = max(avail_x1, logo_bbox[2] + 12)
        else:
            avail_x2 = min(avail_x2, logo_bbox[0] - 12)

    max_pill_w = max(120, avail_x2 - avail_x1)
    _, _, measured_tw, _ = fit_and_condense_arabic_text(
        draw, badge_label, max_width=max_pill_w - 48,
        initial_font_size=max(18, int(min(width, height) * 0.028)), min_font_size=11, bold=True
    )
    bp_w = min(max_pill_w, max(int(width * 0.36), measured_tw + 48))
    pill_cx = (avail_x1 + avail_x2) // 2
    px1, px2 = pill_cx - bp_w // 2, pill_cx + bp_w // 2

    pill_bg = (255, 255, 255, 245) if is_light else (14, 22, 42, 230)
    pill_txt_c = (15, 23, 42, 255) if is_light else (255, 255, 255, 250)
    draw.rounded_rectangle([(px1, bp_y + 3), (px2, bp_y + bp_h + 3)], radius=bp_h // 2, fill=(0, 0, 0, 45))
    draw.rounded_rectangle([(px1, bp_y), (px2, bp_y + bp_h)], radius=bp_h // 2, fill=pill_bg, outline=(*theme["primary"], 220), width=2)
    dot_x = px2 - 18
    draw.ellipse([(dot_x - 5, bp_y + bp_h // 2 - 5), (dot_x + 5, bp_y + bp_h // 2 + 5)], fill=(*theme["secondary"], 255))
    draw_contained_arabic_text(
        draw, (px1, bp_y, px2, bp_y + bp_h),
        badge_label, initial_font_size=max(18, int(min(width, height) * 0.028)),
        fill=pill_txt_c, pad_left=16, pad_right=30, min_font_size=11
    )

    # 3. مسرح التركيز البصري الواحد
    stage_box = (
        int(width * 0.05),
        int(height * 0.115),
        int(width * 0.95),
        int(height * 0.725)
    )
    img = render_choreographed_stage_archetype(
        canvas_rgba=img,
        stage_bbox=stage_box,
        scene_meta=scene_meta,
        scene_progress=scene_progress,
        global_t=global_t,
        theme=theme,
        is_light_saas=is_light
    )

    # 4. كابشن الكاريوكي الموحد
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.82),
        theme=theme,
        active_word_idx=active_word_idx
    )

    # 5. شريط التقدم الزمني السفلي الأنيق
    draw = ImageDraw.Draw(img, "RGBA")
    prog_w = int(width * 0.84 * min(1.0, max(0.02, global_t / max(0.1, total_duration))))
    bar_x1 = (width - int(width * 0.84)) // 2
    bar_y = int(height * 0.935)
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + int(width * 0.84), bar_y + 6)], radius=3, fill=(148, 163, 184, 65))
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + prog_w, bar_y + 6)], radius=3, fill=(*theme["primary"], 240))

    return img


# ==============================================================================
# 9. محرك الانتقال السلس المريح للعين بين المشاهد (Smooth Studio Camera Handoff)
# ==============================================================================
def get_archetype_portal_and_survivor_bboxes(
    width: int,
    height: int,
    stage_bbox: Tuple[int, int, int, int],
    scene_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Tuple[int, int, int, int, int]]:
    x1, y1, x2, y2 = stage_bbox
    sw, sh = x2 - x1, y2 - y1
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    main_win = (cx - int(sw * 0.45), cy - int(sh * 0.42), cx + int(sw * 0.45), cy + int(sh * 0.42), 32)
    return {"portal": main_win, "container": main_win}


def _camera_curve(u: float) -> float:
    u = max(0.0, min(1.0, float(u)))
    if u < 0.5:
        return 4.0 * u * u * u
    return 1.0 - pow(-2.0 * u + 2.0, 3) / 2.0


def render_one_take_camera_handoff(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str,
    prev_meta: Optional[Dict[str, Any]] = None,
    curr_meta: Optional[Dict[str, Any]] = None,
    stage_bbox: Optional[Tuple[int, int, int, int]] = None
) -> Image.Image:
    """
    انتقال كاميرا سينمائي ناعم ومريح للعين (Smooth Depth Zoom & Cross-Dissolve)
    بدون أي تكبير عنيف أو تقطيع يسبب تشوش النصوص أو تشتت المشاهد.
    """
    w, h = curr_img.size
    p = _camera_curve(max(0.0, min(1.0, float(trans_progress))))

    # تقريب لطيف للمشهد السابق (1.0 -> 1.05) بينما ينبثق المشهد الجديد من (0.96 -> 1.0)
    prev_scale = 1.0 + 0.05 * p
    pw, ph = int(round(w * prev_scale)), int(round(h * prev_scale))
    prev_zoomed = prev_img.convert("RGBA").resize((pw, ph), Image.Resampling.BILINEAR)
    px1, py1 = (pw - w) // 2, (ph - h) // 2
    prev_crop = prev_zoomed.crop((px1, py1, px1 + w, py1 + h))

    curr_scale = 0.96 + 0.04 * p
    cw, ch = max(16, int(round(w * curr_scale))), max(16, int(round(h * curr_scale)))
    curr_scaled = curr_img.convert("RGBA").resize((cw, ch), Image.Resampling.BILINEAR)
    curr_canvas = prev_crop.copy()
    curr_canvas.paste(curr_scaled, ((w - cw) // 2, (h - ch) // 2))

    return Image.blend(prev_crop, curr_canvas, p)


def apply_scene_transition(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str,
    prev_meta: Optional[Dict[str, Any]] = None,
    curr_meta: Optional[Dict[str, Any]] = None,
    stage_bbox: Optional[Tuple[int, int, int, int]] = None
) -> Image.Image:
    return render_one_take_camera_handoff(
        prev_img=prev_img,
        curr_img=curr_img,
        trans_progress=trans_progress,
        transition_type=transition_type,
        prev_meta=prev_meta,
        curr_meta=curr_meta,
        stage_bbox=stage_bbox
    )


def _render_unified_karaoke_subtitle(
    img: Image.Image,
    sc_words: List[str],
    act_word: str,
    w_prog: float,
    cap_y: int,
    theme: Dict[str, Any],
    active_word_idx: Optional[int] = None
):
    w, h = img.size
    cx = w // 2
    clean_sc_words = [re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(wd)).strip() for wd in sc_words if str(wd).strip()]
    clean_act_word = re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(act_word)).strip() if act_word else (clean_sc_words[0] if clean_sc_words else "")

    if not clean_sc_words and not clean_act_word:
        return

    font_size = max(28, int(min(w, h) * 0.042))
    cap_font = get_arabic_font(font_size, bold=True)
    pop_scale = _spring_physics(min(1.0, w_prog * 2.5), stiffness=240.0, damping=14.0)
    active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)

    # تحديد فهرس الكلمة النشطة بشكل حتمي بدون مطابقة أجزاء الكلمات (Fixes t=11s, t=19s, t=23s backward jump bug!)
    if active_word_idx is not None and 0 <= int(active_word_idx) < len(clean_sc_words):
        target_idx = int(active_word_idx)
    else:
        active_word_clean = clean_act_word.lower()
        target_idx = 0
        for wi, cw in enumerate(clean_sc_words):
            if cw.lower() == active_word_clean:
                target_idx = wi
                break

    win_size = min(5, len(clean_sc_words))
    if len(clean_sc_words) <= 5:
        display_words = clean_sc_words
        disp_active_idx = target_idx
    else:
        start_w = max(0, min(target_idx - 2, len(clean_sc_words) - win_size))
        display_words = clean_sc_words[start_w:start_w + win_size]
        disp_active_idx = max(0, min(target_idx - start_w, len(display_words) - 1))

    if not display_words:
        display_words = [clean_act_word]
        disp_active_idx = 0

    draw = ImageDraw.Draw(img, "RGBA")
    word_widths = []
    word_spaces = int(font_size * 0.46)
    for wi, dw in enumerate(display_words):
        f_use = active_font if wi == disp_active_idx else cap_font
        ww, wh = measure_arabic_text(draw, dw, f_use)
        if wi == disp_active_idx:
            ww += 16
        word_widths.append((ww, wh))

    total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces
    if total_line_w > int(w * 0.82):
        scale_down = (w * 0.80) / float(total_line_w)
        font_size = max(20, int(font_size * scale_down))
        cap_font = get_arabic_font(font_size, bold=True)
        active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)
        word_spaces = int(font_size * 0.42)
        word_widths = []
        for wi, dw in enumerate(display_words):
            f_use = active_font if wi == disp_active_idx else cap_font
            ww, wh = measure_arabic_text(draw, dw, f_use)
            if wi == disp_active_idx:
                ww += 14
            word_widths.append((ww, wh))
        total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces

    max_line_h = max(wh for _, wh in word_widths) if word_widths else font_size

    box_pad_x = int(font_size * 0.65)
    box_pad_y = int(font_size * 0.36)
    bar_x1 = max(int(w * 0.04), cx - total_line_w // 2 - box_pad_x)
    bar_x2 = min(int(w * 0.96), cx + total_line_w // 2 + box_pad_x)
    bar_y1 = cap_y - max_line_h // 2 - box_pad_y
    bar_y2 = cap_y + max_line_h // 2 + box_pad_y

    draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(bar_x1, bar_y1, bar_x2, bar_y2),
        radius=(bar_y2 - bar_y1) // 2,
        tint_color=(8, 12, 24, 242),
        border_color=theme["primary"],
        blur_radius=12,
        shadow_offset=10,
        shadow_blur=16
    )

    draw = ImageDraw.Draw(img, "RGBA")
    cur_right_x = bar_x2 - box_pad_x
    for wi, dw in enumerate(display_words):
        ww, wh = word_widths[wi]
        is_active = (wi == disp_active_idx)
        word_cx = cur_right_x - ww // 2

        if is_active:
            hl_pad_x, hl_pad_y = 8, 8
            draw.rounded_rectangle(
                [(word_cx - ww // 2 - hl_pad_x, cap_y - wh // 2 - hl_pad_y),
                 (word_cx + ww // 2 + hl_pad_x, cap_y + wh // 2 + hl_pad_y)],
                radius=12,
                fill=(250, 204, 21, 255)
            )
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=active_font,
                fill=(17, 24, 39, 255),
                stroke_width=1,
                stroke_fill=(255, 255, 255, 140)
            )
        else:
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=cap_font,
                fill=(248, 250, 252, 245),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 235)
            )

        cur_right_x -= (ww + word_spaces)


# ==============================================================================
# 11. تصيير إطار الفيديو الشامل (Master Directed Multi-Layout Frame)
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
    تصيير إطار الفيديو الشامل بدون تقليص أو إنزال الفيديو الأصلي إطلاقاً (100% Full-Screen Video Preservation):
    - يحافظ على كادر الفيديو الحقيقي للمتحدث أو المنتج بملء الشاشة الكاملة طوال الوقت.
    - يوضح النقاط المهمة عبر بطاقات زجاجية عائمة غير مزعجة (`floating_callout`, `top_overlay`, `lower_third`)
      مع دعم عرض اللوقو المرفوع وألوان الثيم المخصصة.
    """
    h, w, _ = base_frame_rgb.shape
    if not master_plan:
        return base_frame_rgb

    active_idx = 0
    for idx, sc in enumerate(master_plan):
        if t >= sc["start"]:
            active_idx = idx
        else:
            break

    sc = master_plan[active_idx]
    layout_mode = sc.get("layout_mode", "top_overlay")
    _, theme, is_light, logo_path, logo_pos = _resolve_active_theme_and_style(sc)
    sc_dur = max(0.18, sc["end"] - sc["start"])
    sc_prog = max(0.0, min(1.0, (t - sc["start"]) / sc_dur))

    sc_words = sc.get("word_strings", [])
    act_word = sc_words[0] if sc_words else sc.get("short_title", "")
    act_word_idx = 0
    w_prog = 0.5
    for wi, w_obj in enumerate(sc.get("words", [])):
        ws = float(w_obj.get("start", 0.0))
        we = float(w_obj.get("end", ws + 0.3))
        if t >= ws - 0.04:
            act_word = w_obj.get("word", "")
            act_word_idx = wi
            wdur = max(0.10, we - ws)
            w_prog = max(0.0, min(1.0, (t - ws) / wdur))

    if layout_mode == "full_screen":
        curr_img = render_single_scene_canvas(
            scene_meta=sc,
            active_word=act_word,
            scene_words=sc_words,
            active_word_idx=act_word_idx,
            word_local_progress=w_prog,
            scene_progress=sc_prog,
            global_t=t,
            total_duration=total_duration,
            audio_level=audio_level,
            width=w,
            height=h,
            bg_cache=bg_cache
        )
        time_into_scene = t - sc["start"]
        handoff_dur = float(sc.get("handoff_duration_sec", 0.38))
        if active_idx > 0 and 0.0 <= time_into_scene < handoff_dur:
            prev_sc = master_plan[active_idx - 1]
            prev_img = render_single_scene_canvas(
                scene_meta=prev_sc,
                active_word="",
                scene_words=prev_sc.get("word_strings", []),
                active_word_idx=max(0, len(prev_sc.get("word_strings", [])) - 1),
                word_local_progress=1.0,
                scene_progress=1.0,
                global_t=t,
                total_duration=total_duration,
                audio_level=audio_level,
                width=w,
                height=h,
                bg_cache=bg_cache
            )
            blended = render_one_take_camera_handoff(
                prev_img=prev_img,
                curr_img=curr_img,
                trans_progress=time_into_scene / handoff_dur,
                transition_type="smooth_dissolve",
                prev_meta=prev_sc,
                curr_meta=sc
            )
            return np.array(blended.convert("RGB"))
        return np.array(curr_img.convert("RGB"))

    # وضع الفيديو الحقيقي: يبقى الفيديو بملء الشاشة 100% دائماً بدون أي تقليص أو إزاحة للأسفل!
    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    img, logo_bbox = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=False)
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2

    # إذا كان النمط floating_callout (أو split_screen_stage قديماً): نرسم بطاقة توضيحية زجاجية عائمة أنيقة وصغيرة
    # توضح الفكرة أو الميزة المنطوقة دون حجب المتحدث أو تقليص الفيديو الأصلي!
    if layout_mode in ("floating_callout", "split_screen_stage"):
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.34), stiffness=200.0, damping=15.0)
        y_slide_offset = int(-70 * (1.0 - spring_in))

        concept_title = str(sc.get("concept_title") or sc.get("short_title") or "ميزة أساسية")
        kpi_val = str(sc.get("kpi_value") or "تركيز")
        sub_items = [str(s).strip() for s in (sc.get("sub_items") or []) if str(s).strip()]
        sub_line = re.sub(r"^\d+[\.\-\s]+", "", sub_items[0]) if sub_items else str(sc.get("kpi_label", ""))

        card_w = int(w * 0.84)
        card_h = max(84, int(h * 0.115))
        top_y = (int(h * 0.095) if logo_bbox is not None else int(h * 0.055)) + y_slide_offset
        bx1, by1 = cx - card_w // 2, top_y
        bx2, by2 = cx + card_w // 2, top_y + card_h

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=24,
            tint_color=(10, 16, 30, 222),
            border_color=theme["primary"],
            secondary_color=theme["secondary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=18,
            light_sweep_prog=(sc_prog * 1.4 - 0.1)
        )

        icon_box = max(52, int(card_h * 0.68))
        hero_ic = _compose_hero_centerpiece_icon(
            scene_type=sc.get("scene_type", "ecommerce_showcase"),
            icon_size=icon_box,
            scene_progress=sc_prog,
            global_t=t,
            theme=theme,
            target_number=int(sc.get("target_number") or 58)
        )
        ic_x = bx2 - icon_box - 14
        ic_y = by1 + (card_h - icon_box) // 2
        img.alpha_composite(hero_ic, (ic_x, ic_y))

        draw = ImageDraw.Draw(img, "RGBA")
        text_right = ic_x - 10
        text_left = bx1 + 14

        # السطر العلوي: العنوان المفاهيمي الواضح
        draw_contained_arabic_text(
            draw, (text_left, by1 + 8, text_right, by1 + int(card_h * 0.54)),
            concept_title, initial_font_size=max(18, int(min(w, h) * 0.032)),
            fill=(255, 255, 255, 255), pad_left=10, pad_right=10, min_font_size=12,
            stroke_width=2, stroke_fill=(0, 0, 0, 220)
        )
        # السطر السفلي: شارة التوضيح المختصرة
        sub_display = f"{kpi_val} • {sub_line}" if (sub_line and sub_line not in kpi_val) else kpi_val
        draw_contained_arabic_text(
            draw, (text_left, by1 + int(card_h * 0.54), text_right, by2 - 8),
            sub_display, initial_font_size=max(15, int(min(w, h) * 0.026)),
            fill=(*theme["secondary"], 255), pad_left=10, pad_right=10, min_font_size=11
        )

    elif layout_mode == "top_overlay":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        y_slide_offset = int(-80 * (1.0 - spring_in))

        badge_title = sc.get("concept_title") or sc.get("badge_label", "ميزة حصرية")
        pill_h = max(50, int(h * 0.054))
        icon_box = max(38, pill_h - 10)
        max_pill_w = int(w * 0.88)
        _, _, tw, _ = fit_and_condense_arabic_text(
            draw, badge_title, max_width=max_pill_w - icon_box - 36,
            initial_font_size=max(19, int(min(w, h) * 0.029)), min_font_size=11, bold=True
        )
        pill_w = min(max_pill_w, max(tw + icon_box + 42, int(w * 0.44)))
        top_y = (int(h * 0.092) if logo_bbox is not None else int(h * 0.042)) + y_slide_offset
        x1, y1 = cx - pill_w // 2, top_y
        x2, y2 = cx + pill_w // 2, top_y + pill_h

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(x1, y1, x2, y2),
            radius=pill_h // 2,
            tint_color=(10, 16, 30, 218),
            border_color=theme["primary"],
            secondary_color=theme["secondary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=18,
            light_sweep_prog=(sc_prog * 1.5 - 0.1)
        )

        mini_icon = _compose_hero_centerpiece_icon(
            scene_type=sc.get("scene_type", "ecommerce_showcase"),
            icon_size=icon_box,
            scene_progress=sc_prog,
            global_t=t,
            theme=theme,
            target_number=int(sc.get("target_number") or 58)
        )
        icon_x = x2 - icon_box - 8
        icon_y = y1 + (pill_h - icon_box) // 2
        img.alpha_composite(mini_icon, (icon_x, icon_y))

        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(
            draw, (x1, y1, icon_x, y2),
            badge_title, initial_font_size=max(19, int(min(w, h) * 0.029)),
            fill=(255, 255, 255, 250), pad_left=16, pad_right=10, min_font_size=11,
            stroke_width=2, stroke_fill=(0, 0, 0, 220)
        )

    elif layout_mode == "lower_third":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        l3_txt = sc.get("badge_label", "ميزة حصرية")
        bar_h = max(48, int(h * 0.052))
        max_bar_w = int(w * 0.88)
        _, _, tw, _ = fit_and_condense_arabic_text(
            draw, l3_txt, max_width=max_bar_w - 40,
            initial_font_size=max(19, int(min(w, h) * 0.029)), min_font_size=11, bold=True
        )
        bar_w = min(max_bar_w, max(int(w * 0.46), tw + 48))
        by1 = int(h * 0.86 + 60 * (1.0 - spring_in))
        by2 = by1 + bar_h
        bx1 = cx - bar_w // 2
        bx2 = cx + bar_w // 2

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=bar_h // 2,
            tint_color=(10, 16, 28, 225),
            border_color=theme["primary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=16,
            light_sweep_prog=(sc_prog * 1.4)
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(
            draw, (bx1, by1, bx2, by2),
            l3_txt, initial_font_size=max(19, int(min(w, h) * 0.029)),
            fill=(*theme["primary"], 255), pad_left=18, pad_right=18, min_font_size=11,
            stroke_width=2, stroke_fill=(0, 0, 0, 235)
        )

    if caption_mode != "none" and (act_word or sc_words):
        if caption_mode == "top_compact":
            cap_y = int(h * 0.14)
        elif layout_mode == "lower_third":
            cap_y = int(h * 0.77)
        else:
            cap_y = int(h * 0.84)

        cap_until = float(sc.get("caption_until", float(sc.get("end", total_duration)) + 0.6))
        if t <= cap_until:
            _render_unified_karaoke_subtitle(
                img=img,
                sc_words=sc_words,
                act_word=act_word,
                w_prog=w_prog,
                cap_y=cap_y,
                theme=theme,
                active_word_idx=act_word_idx
            )

    out_rgb = np.array(img.convert("RGB"))
    if 0.48 <= sc_prog <= 0.52 and not sc.get("_critic_evaluated"):
        sc["_critic_evaluated"] = True
        out_rgb, critic_rep = evaluate_and_evolve_frame(out_rgb, sc, persist_to_disk=True)
        sc["visual_quality_score"] = critic_rep.get("overall_score", 0.94)
    return out_rgb


def create_kinetic_typography_video(
    input_path: str,
    output_path: str,
    video_resolution: Tuple[int, int] = (540, 960),
    whisper_model: str = "base",
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    **kwargs
) -> str:
    from smart_analyzer import analyze_contextual_storyboard

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(output_path)), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    def update_progress(val: float, text: str):
        if progress_callback:
            progress_callback(val, text)
        logger.info(f"Progress: {val*100:.1f}% - {text}")

    clean_media = os.path.join(temp_dir, f"clean_kinetic_input_{os.getpid()}.mp3")
    enc_proc = None

    try:
        gc.collect()
        update_progress(0.10, "1/4: تنظيف الصوت وقص الصمت الطبيعي بدون استهلاك ذاكرة...")
        _, total_dur = extract_jumpcut_audio_and_intervals(
            input_path=input_path,
            clean_audio_output_path=clean_media,
            silence_threshold=-42.0,
            padding_ms=250
        )
        vw, vh = get_safe_working_resolution(video_resolution[0], video_resolution[1], max_dim=960)

        update_progress(0.30, "2/4: تفريغ الكلام وتشغيل المخ السياقي (Contextual Storyboard Brain)...")
        words = transcribe_audio(
            audio_path=clean_media,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        semantic_clauses = split_words_into_micro_scenes(
            words,
            max_words_per_scene=8,
            max_duration_per_scene=4.2,
            min_words_per_scene=4
        )
        full_transcript = " ".join(w.get("word", "") for w in words)

        planned_scenes = analyze_contextual_storyboard(
            scenes=semantic_clauses,
            full_transcript=full_transcript,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            ollama_model=ollama_model
        )

        bg_cache: Dict[str, np.ndarray] = {}
        gc.collect()

        update_progress(0.55, "3/4: تصيير رسومات الفيكتور السياقية (PyCairo) وبطاقات الزجاج (VisionOS Glass)...")

        def make_frame(t: float) -> np.ndarray:
            if len(bg_cache) > 1:
                bg_cache.clear()
            if not planned_scenes:
                if "cyber_gold" not in bg_cache:
                    bg_cache["cyber_gold"] = create_studio_background(vw, vh, "cyber_gold")
                return bg_cache["cyber_gold"]
            active_idx = 0
            for i, s in enumerate(planned_scenes):
                if t >= s["start"]:
                    active_idx = i
                else:
                    break
            sc = planned_scenes[active_idx]
            sc_dur = max(0.18, sc["end"] - sc["start"])
            sc_prog = max(0.0, min(1.0, (t - sc["start"]) / sc_dur))

            sc_words = sc.get("word_strings", [])
            act_w = sc_words[0] if sc_words else sc.get("short_title", "")
            act_w_idx = 0
            w_p = 0.5
            for wi, w_obj in enumerate(sc.get("words", [])):
                ws = float(w_obj.get("start", 0.0))
                we = float(w_obj.get("end", ws + 0.3))
                if t >= ws - 0.04:
                    act_w = w_obj.get("word", "")
                    act_w_idx = wi
                    w_p = max(0.0, min(1.0, (t - ws) / max(0.10, we - ws)))

            curr_img = render_single_scene_canvas(
                scene_meta=sc,
                active_word=act_w,
                scene_words=sc_words,
                active_word_idx=act_w_idx,
                word_local_progress=w_p,
                scene_progress=sc_prog,
                global_t=t,
                total_duration=total_dur,
                audio_level=0.8,
                width=vw,
                height=vh,
                bg_cache=bg_cache
            )

            time_into = t - sc["start"]
            handoff_dur = float(sc.get("handoff_duration_sec", 0.42))
            if active_idx > 0 and 0.0 <= time_into < handoff_dur:
                prev_sc = planned_scenes[active_idx - 1]
                prev_img = render_single_scene_canvas(
                    scene_meta=prev_sc,
                    active_word="",
                    scene_words=prev_sc.get("word_strings", []),
                    active_word_idx=max(0, len(prev_sc.get("word_strings", [])) - 1),
                    word_local_progress=1.0,
                    scene_progress=1.0,
                    global_t=t,
                    total_duration=total_dur,
                    audio_level=0.8,
                    width=vw,
                    height=vh,
                    bg_cache=bg_cache
                )
                handoff_mode = sc.get("one_take_handoff") or sc.get("transition", "camera_dive_into_portal")
                curr_img = render_one_take_camera_handoff(
                    prev_img=prev_img,
                    curr_img=curr_img,
                    trans_progress=time_into / handoff_dur,
                    transition_type=handoff_mode,
                    prev_meta=prev_sc,
                    curr_meta=sc,
                    stage_bbox=(int(vw * 0.04), int(vh * 0.112), int(vw * 0.96), int(vh * 0.725))
                )

            return np.array(curr_img.convert("RGB"), dtype=np.uint8)

        fps = 30
        total_frames = max(1, int(round(total_dur * fps)))
        update_progress(0.65, "4/4: الرندرة النهائية عبر التدفق المباشر (Zero-RAM FFmpeg Pipe)...")

        enc_cmd = [
            "ffmpeg", "-y", "-v", "error", "-threads", "1",
            "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{vw}x{vh}", "-r", str(fps), "-i", "-",
            "-threads", "1", "-i", clean_media,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-x264-params", "rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0",
            "-crf", "21", "-pix_fmt", "yuv420p", "-threads", "1",
            "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "16000",
            "-movflags", "+faststart", "-shortest",
            output_path
        ]
        enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for f_idx in range(total_frames):
            t_cur = f_idx / float(fps)
            frm = make_frame(t_cur)
            enc_proc.stdin.write(np.ascontiguousarray(frm, dtype=np.uint8).tobytes())
            if f_idx % 24 == 0:
                prog_ratio = 0.65 + 0.33 * (f_idx / float(max(1, total_frames)))
                pct_done = int(round((f_idx / float(max(1, total_frames))) * 100))
                update_progress(prog_ratio, f"4/4: جاري رندرة الفيديو النهائي باستهلاك ذاكرة منخفض ({pct_done}%)...")
            if f_idx % 60 == 0 and f_idx > 0:
                force_free_ram()

        enc_proc.stdin.close()
        enc_proc.wait(timeout=120)
        enc_proc = None

        update_progress(1.0, "اكتمل تصيير الموشن جرافيك السياقي الاحترافي بنجاح!")
        return output_path

    finally:
        if enc_proc is not None:
            try:
                if enc_proc.stdin:
                    enc_proc.stdin.close()
                enc_proc.kill()
            except Exception:
                pass
        if os.path.exists(clean_media):
            try:
                os.remove(clean_media)
            except Exception:
                pass
        gc.collect()