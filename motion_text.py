"""
motion_text.py - محرك الموشن جرافيك التوليدي متعدد الرسومات والأنيميشن المستمر (12 Dynamic Kinetic Archetypes & Reference Cloner Engine)
==============================================================================================================================================
يعالج هذا المحرك جميع الملاحظات البصرية والحركية ليقدم تجربة موشن جرافيك بمستوى المصممين البشر المحترفين (100% Human Studio Feel):
1. هوية بصرية موحدة لكل فيديو (`Single Cohesive Studio Style Per Video`):
   - كل فيديو يُنتج بهوية لونية وخلفية موحدة ومتناغمة من أول مشهد لآخر مشهد (بدون خلط خلفيات متضاربة داخل الفيديو الواحد).
   - عند تفعيل الاختيار العشوائي/التلقائي، يختار النظام ستايلاً احترافياً كاملاً لكل فيديو جديد.
2. 12 رسماً وأنفوجرافيك تفاعلياً بـ أنيميشن مستمر 30fps طوال المشهد (`12 Dynamic Visual & Kinetic Archetypes`):
   - لا يتجمد أي مشهد أبداً! كل عنصر يتحرك بفيزياء الزنبرك (`Spring Physics`) والتحريك المتتابع للكلمات (`Staggered Word Entrance`)
     والرسم التدريجي للمنحنيات (`Progressive Bezier Tracing`) والعدادات الحية (`Live Counters`) وحركة الماوس والمكبّر والرادار والميزان.
   - عزل هندسي صارم للنصوص والأيقونات (`Zero Text-Border Collision & Zero Coin-Number Overlap`).
3. كابشن كاريوكي بنظام الصفحات الثابتة (`Non-Overlapping Paged Karaoke Captions`):
   - يعرض الكلمات في صفحات نظيفة من 4 كلمات دون تكرار الكلمات بين نهاية جملة وبداية الجملة التالية.
4. ربط مباشر مع كاشف أخطاء وإعادات التعليق الصوتي (`prune_retake_cuts_from_media`) ومعايرة الصمت الطبيعي (`3% - 4%`).
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

from auto_cut import (
    remove_silence,
    is_video_file,
    get_safe_working_resolution,
    extract_jumpcut_audio_and_intervals,
    prune_retake_cuts_from_media,
    force_free_ram
)
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
    get_active_brand_theme,
    PRO_STUDIO_STYLE_FAMILIES,
    ALL_DYNAMIC_VISUAL_ARCHETYPES,
    build_dynamic_scene_style_assignment
)
from transcriber import (
    transcribe_audio,
    split_words_into_micro_scenes,
    get_last_detected_retake_cuts,
    remap_words_after_retake_cuts
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
    if not text or not re.search(r"[A-Za-z+%$#@&*=/\\•()\-:|?!]", str(text)):
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
    clean_t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_t:
        f_obj = get_arabic_font(initial_font_size, bold=bold)
        return "", f_obj, 0, initial_font_size

    safe_max_w = max(28, int(max_width))
    f_obj, tw, th = get_fitted_arabic_font(draw, clean_t, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
    if tw <= safe_max_w:
        return clean_t, f_obj, tw, th

    no_paren = re.sub(r"\s*\([^)]*\)", "", clean_t).strip()
    if no_paren and no_paren != clean_t:
        f_obj, tw, th = get_fitted_arabic_font(draw, no_paren, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
        if tw <= safe_max_w:
            return no_paren, f_obj, tw, th
        clean_t = no_paren

    words = clean_t.split()
    while len(words) > 2:
        words.pop()
        cand = " ".join(words).rstrip("•:-،,")
        f_obj, tw, th = get_fitted_arabic_font(draw, cand, safe_max_w, initial_font_size, min_font_size=min_font_size, bold=bold)
        if tw <= safe_max_w:
            return cand, f_obj, tw, th

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
        "top_bg": (13, 118, 142),
        "bottom_bg": (7, 68, 86),
        "glow": (56, 219, 248),
        "primary": (27, 174, 202),
        "secondary": (250, 204, 21),
        "accent": (16, 185, 129),
        "card_bg": (255, 255, 255)
    },
    "neon_emerald": {
        "top_bg": (9, 32, 26),
        "bottom_bg": (13, 56, 45),
        "glow": (16, 185, 129),
        "primary": (16, 185, 129),
        "secondary": (250, 204, 21),
        "accent": (56, 189, 248),
        "card_bg": (255, 255, 255)
    },
    "royal_purple": {
        "top_bg": (18, 15, 36),
        "bottom_bg": (36, 24, 64),
        "glow": (139, 92, 246),
        "primary": (139, 92, 246),
        "secondary": (216, 180, 254),
        "accent": (250, 204, 21),
        "card_bg": (28, 22, 52)
    },
    "crimson_energy": {
        "top_bg": (26, 14, 24),
        "bottom_bg": (52, 22, 40),
        "glow": (244, 63, 94),
        "primary": (244, 63, 94),
        "secondary": (251, 191, 36),
        "accent": (16, 185, 129),
        "card_bg": (255, 255, 255)
    },
    "electric_cobalt": {
        "top_bg": (11, 20, 44),
        "bottom_bg": (20, 38, 82),
        "glow": (59, 130, 246),
        "primary": (59, 130, 246),
        "secondary": (250, 204, 21),
        "accent": (16, 185, 129),
        "card_bg": (22, 34, 68)
    },
    "sunset_violet": {
        "top_bg": (172, 214, 248),
        "bottom_bg": (208, 232, 252),
        "glow": (2, 132, 199),
        "primary": (2, 132, 199),
        "secondary": (15, 23, 42),
        "accent": (37, 99, 235),
        "card_bg": (255, 255, 255)
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


def _spring_physics(t: float, stiffness: float = 210.0, damping: float = 13.5, mass: float = 1.0) -> float:
    return float(spring_damper(t, stiffness=stiffness, damping=damping, mass=mass))


def _staggered_spring(global_prog: float, delay: float = 0.0, duration: float = 0.42, stiffness: float = 210.0, damping: float = 13.5) -> float:
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

    t = scene_text.strip()
    num_match = re.search(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t)
    extracted_number = int(num_match.group(1)) if num_match else 58

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
# 5. محرك الزجاج الحقيقي والبطاقات الاحترافية (VisionOS Glass & Studio Cards)
# ==============================================================================
def draw_visionos_glass_panel(
    canvas_rgba: Image.Image,
    bbox: Tuple[int, int, int, int],
    radius: int = 28,
    tint_color: Tuple[int, int, int, int] = (12, 18, 34, 185),
    border_color: Tuple[int, int, int] = (27, 174, 202),
    secondary_color: Tuple[int, int, int] = (0, 245, 212),
    blur_radius: int = 16,
    shadow_offset: int = 14,
    shadow_blur: int = 20,
    light_sweep_prog: float = -1.0
) -> Image.Image:
    w, h = canvas_rgba.size
    x1, y1, x2, y2 = int(max(0, bbox[0])), int(max(0, bbox[1])), int(min(w, bbox[2])), int(min(h, bbox[3]))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return canvas_rgba

    pad = shadow_blur * 2 + abs(shadow_offset) + 8
    sx1, sy1 = max(0, x1 - pad), max(0, y1 - pad)
    sx2, sy2 = min(w, x2 + pad), min(h, y2 + pad)
    sw, sh = sx2 - sx1, sy2 - sy1

    if sw > 4 and sh > 4:
        shadow_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer, "RGBA")
        bx1, by1 = x1 - sx1, y1 - sy1 + shadow_offset
        bx2, by2 = x2 - sx1, y2 - sy1 + shadow_offset
        s_draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=(0, 0, 0, 105))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(2, shadow_blur // 2)))
        canvas_rgba.alpha_composite(shadow_layer, (sx1, sy1))

    pw, ph = x2 - x1, y2 - y1
    backdrop_crop = canvas_rgba.crop((x1, y1, x2, y2))
    if blur_radius > 0:
        backdrop_crop = backdrop_crop.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    glass_tint = Image.new("RGBA", (pw, ph), tint_color)
    frosted = Image.alpha_composite(backdrop_crop, glass_tint)

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
        ], fill=(255, 255, 255, 32))

    frosted = Image.alpha_composite(frosted, sheen)

    mask = Image.new("L", (pw, ph), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([(0, 0), (pw - 1, ph - 1)], radius=radius, fill=255)
    canvas_rgba.paste(frosted, (x1, y1), mask)

    c_draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    c_draw.rounded_rectangle([(x1, y1), (x2 - 1, y2 - 1)], radius=radius, outline=(*border_color, 230), width=2)
    return canvas_rgba


# ==============================================================================
# 6. محرك الرسوميات الفيكتور المتحركة (PyCairo Vector & Dynamic Progress Engine)
# ==============================================================================
def _cairo_rounded_rect(ctx, x: float, y: float, w: float, h: float, r: float):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
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
    if not _HAS_CAIRO:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    ctx.set_antialias(cairo.ANTIALIAS_BEST)

    cx, cy = width / 2.0, height / 2.0
    r = min(width, height) * 0.44
    p1 = _norm_rgb(theme.get("primary", (27, 174, 202)))
    p2 = _norm_rgb(theme.get("secondary", (250, 204, 21)))
    acc = _norm_rgb(theme.get("accent", (16, 185, 129)))

    s_main = 0.82 + 0.18 * _staggered_spring(scene_progress, delay=0.0, duration=0.45)
    grow_prog = min(1.0, max(0.15, scene_progress * 1.45))

    rad_glow = cairo.RadialGradient(cx, cy, r * 0.05, cx, cy, r * 1.1)
    rad_glow.add_color_stop_rgba(0.0, p1[0], p1[1], p1[2], 0.24 * s_main)
    rad_glow.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
    ctx.set_source(rad_glow)
    ctx.arc(cx, cy, r * 1.1, 0, 2 * math.pi)
    ctx.fill()

    if scene_type in ("growth_analytics", "ecommerce_showcase"):
        # أبراج العملات ثلاثية الأبعاد ترتفع تدريجياً عملة تلو الأخرى مع تقدم المشهد!
        stack_xs = [cx - r * 0.54, cx, cx + r * 0.54]
        max_counts = [4, 6, 3]
        coin_rx = r * 0.22 * s_main
        coin_ry = r * 0.072 * s_main
        base_y = cy + r * 0.55

        for s_idx, (sx, max_c) in enumerate(zip(stack_xs, max_counts)):
            local_p = max(0.0, min(1.0, (scene_progress - s_idx * 0.08) * 1.6))
            vis_c = max(1, int(round(max_c * local_p)))
            for ci in range(vis_c):
                cy_c = base_y - ci * (coin_ry * 1.55) - 3.0 * math.sin(global_t * 3.5 + s_idx)
                ctx.save()
                ctx.translate(sx, cy_c)
                ctx.scale(coin_rx, coin_ry)
                ctx.arc(0, 0, 1.0, 0, 2 * math.pi)
                ctx.restore()
                ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.96)
                ctx.fill_preserve()
                ctx.set_source_rgba(1.0, 1.0, 1.0, 0.92)
                ctx.set_line_width(2.0)
                ctx.stroke()

        # السهم الصاعد فوق الأبراج
        top_y = base_y - 6 * (coin_ry * 1.55) - r * 0.36 * grow_prog
        ctx.move_to(cx, base_y - 2 * coin_ry)
        ctx.line_to(cx, top_y)
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        ctx.set_line_width(4.5)
        ctx.stroke()

        ctx.move_to(cx - 11, top_y + 13)
        ctx.line_to(cx, top_y - 2)
        ctx.line_to(cx + 11, top_y + 13)
        ctx.set_line_width(4.0)
        ctx.stroke()

    elif scene_type in ("delivery_express", "cta_tap", "brand_finale"):
        ry = cy - 9.0 * math.sin(global_t * 4.2)
        rw, rh = r * 0.36 * s_main, r * 0.78 * s_main
        ctx.move_to(cx, ry - rh * 0.6)
        ctx.curve_to(cx + rw, ry - rh * 0.1, cx + rw * 0.8, ry + rh * 0.4, cx, ry + rh * 0.45)
        ctx.curve_to(cx - rw * 0.8, ry + rh * 0.4, cx - rw, ry - rh * 0.1, cx, ry - rh * 0.6)
        ctx.close_path()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.96)
        ctx.fill_preserve()
        ctx.set_source_rgba(0.05, 0.12, 0.18, 0.95)
        ctx.set_line_width(3.0)
        ctx.stroke()

        ctx.arc(cx, ry - rh * 0.08, rw * 0.28, 0, 2 * math.pi)
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 1.0)
        ctx.fill()

        flame_h = r * (0.26 + 0.10 * math.sin(global_t * 9.0))
        ctx.move_to(cx - rw * 0.25, ry + rh * 0.45)
        ctx.line_to(cx, ry + rh * 0.45 + flame_h)
        ctx.line_to(cx + rw * 0.25, ry + rh * 0.45)
        ctx.close_path()
        ctx.set_source_rgba(p2[0], p2[1], p2[2], 0.92)
        ctx.fill()
    else:
        cr = r * 0.64 * s_main
        ctx.arc(cx, cy, cr, 0, 2 * math.pi)
        ctx.set_source_rgba(0.08, 0.14, 0.24, 0.92)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.95)
        ctx.set_line_width(4.0)
        ctx.stroke()

        for bi, bh in enumerate([0.34, 0.56, 0.82]):
            bx = cx - cr * 0.42 + bi * (cr * 0.32)
            bw = cr * 0.20
            anim_h = cr * bh * min(1.0, max(0.2, (scene_progress - bi * 0.08) * 1.6))
            _cairo_rounded_rect(ctx, bx, cy + cr * 0.35 - anim_h, bw, anim_h, 4)
            ctx.set_source_rgba(p1[0], p1[1], p1[2] if bi < 2 else p2[2], 0.95)
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
    p1 = (*theme.get("primary", (27, 174, 202)), 255)
    p2 = (*theme.get("secondary", (250, 204, 21)), 255)
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(12, 18, 34, 230), outline=p1, width=2)
    in_r = max(6, int(r * 0.45 * (0.85 + 0.15 * math.sin(global_t * 4))))
    draw.ellipse([(cx - in_r, cy - in_r), (cx + in_r, cy + in_r)], fill=p2)


# ==============================================================================
# 7. بناء الخلفيات الشبكية والهندسية الموحدة والمتحركة بنعومة (Animated Parallax Grid)
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

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    yy, xx = np.ogrid[:height, :width]
    cx1, cy1 = width * 0.5, height * 0.42
    dist1 = ((xx - cx1) / (width * 0.55)) ** 2 + ((yy - cy1) / (height * 0.38)) ** 2
    mask1 = np.exp(-dist1 * 2.0)[:, :, None] * 0.20

    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255).astype(np.uint8)
    img = Image.fromarray(canvas_np, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    step = max(48, min(width, height) // 11)
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 16), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 16), width=1)

    return np.array(img)


def _render_pro_stage_background(
    width: int,
    height: int,
    style_spec: Dict[str, Any],
    step_num: int,
    global_t: float
) -> Image.Image:
    """
    يبني خلفية المسرح الموحدة والمتحركة بنعومة (`Animated Parallax Studio Stage`):
    - تدرج لوني موحد مع هالة ضوئية تتنفس بنعومة (`Breathing Ambient Glow`).
    - شبكة هندسية تتحرك ببطء انسيابي (`Subtle Parallax Grid Drift`) تعطي إحساساً بحركة الكاميرا المستمرة.
    - أشكال هندسية طافية (`◇` و `+`) تسبح في الخلفية بدون أي تداخل مع البطاقات أو النصوص!
    """
    pal = style_spec.get("palette", {})
    top_c = np.array(pal.get("top_bg", (13, 118, 142)), dtype=np.float32)
    bot_c = np.array(pal.get("bottom_bg", (7, 68, 86)), dtype=np.float32)
    glow_c = np.array(pal.get("glow", (56, 219, 248)), dtype=np.float32)
    is_light = bool(pal.get("is_light_bg", False))

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    # هالة ضوئية مركزية تتحرك وتنبض بنعومة مع الزمن
    yy, xx = np.ogrid[:height, :width]
    cx1 = width * (0.50 + 0.06 * math.sin(global_t * 0.7))
    cy1 = height * (0.44 + 0.04 * math.cos(global_t * 0.6))
    dist1 = ((xx - cx1) / (width * 0.54)) ** 2 + ((yy - cy1) / (height * 0.38)) ** 2
    glow_strength = 0.22 if not is_light else 0.14
    mask1 = np.exp(-dist1 * 2.1)[:, :, None] * glow_strength
    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255).astype(np.uint8)

    img = Image.fromarray(canvas_np, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    # 1. الشبكة الهندسية المتحركة بنعومة (Parallax Engineering Grid)
    if style_spec.get("has_grid", True):
        grid_step = max(46, min(width, height) // 11)
        drift_x = int((global_t * 10.0) % grid_step)
        drift_y = int((global_t * 8.0) % grid_step)
        grid_col = (15, 23, 42, 15) if is_light else (255, 255, 255, 18)
        for gx in range(-grid_step + drift_x, width + grid_step, grid_step):
            draw.line([(gx, 0), (gx, height)], fill=grid_col, width=1)
        for gy in range(-grid_step + drift_y, height + grid_step, grid_step):
            draw.line([(0, gy), (width, gy)], fill=grid_col, width=1)

    # 2. المعينات والنجوم الهندسية الطافية في الهوامش الجانبية الآمنة
    if style_spec.get("has_floating_diamonds", True):
        d_col = (2, 132, 199, 65) if is_light else (255, 255, 255, 65)
        diamond_positions = [
            (int(width * 0.08), int(height * 0.13), 9),
            (int(width * 0.92), int(height * 0.11), 11),
            (int(width * 0.06), int(height * 0.48), 9),
            (int(width * 0.94), int(height * 0.52), 10),
            (int(width * 0.09), int(height * 0.76), 8),
            (int(width * 0.91), int(height * 0.78), 10),
        ]
        for idx_d, (dx_base, dy_base, ds) in enumerate(diamond_positions):
            dx = dx_base + int(4 * math.cos(global_t * 1.8 + idx_d))
            dy = dy_base + int(8 * math.sin(global_t * 2.3 + idx_d * 1.1))
            pts = [(dx, dy - ds), (dx + ds, dy), (dx, dy + ds), (dx - ds, dy)]
            if idx_d % 2 == 0:
                draw.polygon(pts, outline=d_col, width=2)
            else:
                draw.polygon(pts, fill=(d_col[0], d_col[1], d_col[2], 34))

    return img


# ==============================================================================
# 8. محرك العناوين الحركية المتتابعة مع الستيكر المتمدد (Kinetic Staggered Headline)
# ==============================================================================
def _draw_sticker_highlighted_headline(
    draw: ImageDraw.ImageDraw,
    bbox: Tuple[int, int, int, int],
    headline_text: str,
    highlight_word: str = "",
    headline_txt_color: Tuple[int, int, int] = (255, 255, 255),
    sticker_bg_color: Tuple[int, int, int] = (255, 255, 255),
    sticker_txt_color: Tuple[int, int, int] = (11, 24, 31),
    initial_font_size: int = 32,
    scene_progress: float = 1.0,
    global_t: float = 0.0
):
    """
    يرسم العنوان الاحترافي بتحريك متتابع كلمة بكلمة (`Staggered Word Spring Entrance`)
    مع تمدد فيزيائي لمستطيل الستيكر حول الكلمة المفتاحية (`Sticker Sweep & Pop`)!
    """
    x1, y1, x2, y2 = bbox
    max_w = max(80, x2 - x1 - 24)
    cx = (x1 + x2) // 2

    words = [w.strip() for w in str(headline_text or "").split() if w.strip()]
    if not words:
        return

    hl_clean = re.sub(r"[،,.!؟?:•]", "", str(highlight_word or "")).strip()
    target_w_idx = -1
    if hl_clean:
        for i, w in enumerate(words):
            if hl_clean in re.sub(r"[،,.!؟?:•]", "", w):
                target_w_idx = i
                break
    if target_w_idx < 0:
        best_len = -1
        for i, w in enumerate(words[:min(4, len(words))]):
            wc = re.sub(r"[،,.!؟?:•]", "", w)
            if len(wc) > best_len and wc not in ("في", "من", "على", "مع", "أو", "كل", "هذا", "هذه", "إلى"):
                best_len = len(wc)
                target_w_idx = i
        if target_w_idx < 0:
            target_w_idx = 0

    if len(words) <= 3:
        lines = [(words, target_w_idx, 0)]
    else:
        mid = max(2, (len(words) + 1) // 2)
        line1 = words[:mid]
        line2 = words[mid:]
        hl1 = target_w_idx if target_w_idx < mid else -1
        hl2 = (target_w_idx - mid) if target_w_idx >= mid else -1
        lines = [(line1, hl1, 0), (line2, hl2, len(line1))]

    line_count = len(lines)
    avail_h = max(44, y2 - y1)
    line_step_h = min(int(initial_font_size * 1.46), avail_h // max(1, line_count))
    start_cy = (y1 + y2) // 2 - ((line_count - 1) * line_step_h) // 2

    for l_idx, (l_words, hl_pos, word_offset_idx) in enumerate(lines):
        line_str = " ".join(l_words)
        f_obj, _, _ = get_fitted_arabic_font(
            draw, line_str, max_width=int(max_w * 0.88),
            initial_font_size=initial_font_size, min_font_size=16, bold=True
        )
        f_sz = getattr(f_obj, "size", 24)
        space_w = max(8, int(f_sz * 0.34))

        measured = []
        for wi, w_str in enumerate(l_words):
            ww, wh = measure_arabic_text(draw, w_str, f_obj)
            if wi == hl_pos:
                ww += int(f_sz * 0.62)
            measured.append((w_str, ww, wh, wi == hl_pos, word_offset_idx + wi))

        total_lw = sum(m[1] for m in measured) + max(0, len(measured) - 1) * space_w
        if total_lw > max_w:
            scale_f = max_w / float(max(1, total_lw))
            new_sz = max(14, int(f_sz * scale_f))
            f_obj = get_arabic_font(new_sz, bold=True)
            space_w = max(6, int(new_sz * 0.30))
            measured = []
            for wi, w_str in enumerate(l_words):
                ww, wh = measure_arabic_text(draw, w_str, f_obj)
                if wi == hl_pos:
                    ww += int(new_sz * 0.56)
                measured.append((w_str, ww, wh, wi == hl_pos, word_offset_idx + wi))
            total_lw = sum(m[1] for m in measured) + max(0, len(measured) - 1) * space_w

        cur_right = cx + total_lw // 2
        base_line_cy = start_cy + l_idx * line_step_h

        for w_str, ww, wh, is_hl, global_wi in measured:
            # تحريك متتابع لكل كلمة على حدة (Staggered Word Entrance)
            w_spring = _staggered_spring(scene_progress, delay=0.02 + global_wi * 0.038, duration=0.38)
            dy_word = int(18.0 * (1.0 - w_spring))
            line_cy = base_line_cy + dy_word
            w_cx = cur_right - ww // 2

            if is_hl:
                sticker_sweep = min(1.0, max(0.15, _staggered_spring(scene_progress, delay=0.05 + global_wi * 0.038, duration=0.42)))
                pulse_pad = int(2.0 * math.sin(global_t * 4.5))
                pad_y = max(6, int(wh * 0.24)) + pulse_pad
                eff_w = int(ww * sticker_sweep)
                rx1 = int(w_cx + ww // 2 - eff_w)
                rx2 = int(w_cx + ww // 2)
                ry1 = int(line_cy - wh // 2 - pad_y)
                ry2 = int(line_cy + wh // 2 + pad_y)
                draw.rounded_rectangle([(rx1, ry1 + 4), (rx2, ry2 + 4)], radius=12, fill=(0, 0, 0, 65))
                draw.rounded_rectangle([(rx1, ry1), (rx2, ry2)], radius=12, fill=(*sticker_bg_color, 255))
                draw_arabic_text(draw, (w_cx, line_cy), w_str, font=f_obj, fill=(*sticker_txt_color, 255))
            else:
                stroke_c = (0, 0, 0, 155) if sum(headline_txt_color) > 400 else (255, 255, 255, 0)
                stroke_w = 2 if sum(headline_txt_color) > 400 else 0
                draw_arabic_text(
                    draw, (w_cx, line_cy), w_str, font=f_obj,
                    fill=(*headline_txt_color, 255), stroke_width=stroke_w, stroke_fill=stroke_c
                )
            cur_right -= (ww + space_w)


# ==============================================================================
# 9. محرك الـ 12 رسماً وأنفوجرافيك تفاعلياً بـ أنيميشن مستمر 30fps (12 Kinetic Archetypes)
# ==============================================================================
def _draw_checkmark_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color_rgb: Tuple[int, int, int] = (16, 185, 129), scale: float = 1.0):
    r = max(8, int(radius * scale))
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(*color_rgb, 255), outline=(255, 255, 255, 235), width=2)
    draw.line([(cx - int(r * 0.42), cy + int(r * 0.05)), (cx - int(r * 0.10), cy + int(r * 0.38)), (cx + int(r * 0.46), cy - int(r * 0.32))], fill=(255, 255, 255, 255), width=max(2, int(r * 0.22)))


def _draw_cursor_with_ripple(
    draw: ImageDraw.ImageDraw,
    start_xy: Tuple[int, int],
    target_xy: Tuple[int, int],
    prog: float,
    accent_rgb: Tuple[int, int, int] = (37, 99, 235)
):
    move_p = _ease_out_cubic(max(0.0, min(1.0, (prog - 0.12) / 0.45)))
    cx = int(start_xy[0] + (target_xy[0] - start_xy[0]) * move_p)
    cy = int(start_xy[1] + (target_xy[1] - start_xy[1]) * move_p)

    click_scale = 1.0
    if prog > 0.55:
        ripple_p = ((prog - 0.55) * 2.2) % 1.0
        click_scale = 1.0 - 0.14 * math.sin(min(1.0, ripple_p * 2.0) * math.pi)
        for ri in range(2):
            rp = max(0.0, min(1.0, ripple_p - ri * 0.20))
            if rp > 0.0:
                rr = int(8 + 34 * rp)
                ra = int(180 * (1.0 - rp))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*accent_rgb, ra), width=2)

    s = max(14, int(19 * click_scale))
    pts = [
        (cx, cy),
        (cx, cy + int(s * 1.35)),
        (cx + int(s * 0.38), cy + int(s * 1.02)),
        (cx + int(s * 0.68), cy + int(s * 1.55)),
        (cx + int(s * 0.90), cy + int(s * 1.42)),
        (cx + int(s * 0.58), cy + int(s * 0.90)),
        (cx + int(s * 1.05), cy + int(s * 0.85))
    ]
    draw.polygon([(px + 2, py + 3) for px, py in pts], fill=(0, 0, 0, 130))
    draw.polygon(pts, fill=(255, 255, 255, 255), outline=(17, 24, 39, 255))


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


def _render_unified_top_header(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    step_num: int,
    total_scenes: int,
    badge_label: str,
    style_spec: Dict[str, Any],
    scene_progress: float
):
    """
    يرسم الترويسة العلوية الأنيقة حسب هوية الستايل المختار (شريط الخطوات النقطي، التبويبات الثلاثية، أو الشارة الهندسية)
    مع حركة انزلاق فيزيائية ناعمة.
    """
    cx = w // 2
    pal = style_spec.get("palette", {})
    primary_c = tuple(pal.get("primary", (27, 174, 202)))
    dark_navy = (11, 24, 31)
    header_style = str(style_spec.get("header_style", "step_dots_pill"))
    s_in = _staggered_spring(scene_progress, delay=0.0, duration=0.35)
    y_off = int(-24 * (1.0 - s_in))

    if header_style == "segmented_3tabs":
        tabs_y1 = int(h * 0.048) + y_off
        tabs_h = max(30, int(h * 0.034))
        tab_labels = ["المقدمة", "المحور", "النتيجة"]
        act_name = str(style_spec.get("act_name", "body_steps"))
        active_tab_idx = 0 if act_name == "hook_problem" else (2 if act_name == "outro_finale" else 1)

        total_tabs_w = int(w * 0.84)
        single_tab_w = (total_tabs_w - 16) // 3
        tabs_x0 = (w - total_tabs_w) // 2

        for ti in range(3):
            rtl_i = 2 - ti
            tx1 = tabs_x0 + rtl_i * (single_tab_w + 8)
            tx2 = tx1 + single_tab_w
            is_act = (ti == active_tab_idx)
            t_fill = (*primary_c, 255) if is_act else (30, 32, 58, 210)
            draw.rounded_rectangle([(tx1, tabs_y1), (tx2, tabs_y1 + tabs_h)], radius=10, fill=t_fill, outline=(255, 255, 255, 90 if is_act else 35), width=1)
            draw_contained_arabic_text(
                draw, (tx1 + 6, tabs_y1, tx2 - 6, tabs_y1 + tabs_h),
                tab_labels[ti], initial_font_size=14, fill=(255, 255, 255, 255 if is_act else 185)
            )
    else:
        pill_w, pill_h = int(w * 0.30), max(34, int(h * 0.038))
        pill_x1, pill_y1 = cx - pill_w // 2, int(h * 0.048) + y_off
        pill_x2, pill_y2 = pill_x1 + pill_w, pill_y1 + pill_h
        draw.rounded_rectangle([(pill_x1, pill_y1 + 3), (pill_x2, pill_y2 + 3)], radius=pill_h // 2, fill=(0, 0, 0, 45))
        draw.rounded_rectangle([(pill_x1, pill_y1), (pill_x2, pill_y2)], radius=pill_h // 2, fill=(255, 255, 255, 252))

        badge_r = (pill_h - 8) // 2
        b_cx = pill_x1 + 6 + badge_r
        b_cy = pill_y1 + pill_h // 2
        draw.ellipse([(b_cx - badge_r, b_cy - badge_r), (b_cx + badge_r, b_cy + badge_r)], fill=(*dark_navy, 255))
        num_f = get_arabic_font(max(12, int(pill_h * 0.44)), bold=True)
        draw_arabic_text(draw, (b_cx, b_cy), f"{step_num:02d}", font=num_f, fill=(255, 255, 255, 255))

        dots_start_x = b_cx + badge_r + 12
        for di in range(4):
            d_active = (di == ((step_num - 1) % 4))
            dw_dot = 20 if d_active else 8
            draw.rounded_rectangle(
                [(dots_start_x, b_cy - 4), (dots_start_x + dw_dot, b_cy + 4)],
                radius=4,
                fill=(*primary_c, 255) if d_active else (203, 213, 225, 255)
            )
            dots_start_x += dw_dot + 7


def _render_dynamic_archetype_stage(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float
) -> Image.Image:
    """
    محرك الرسومات والـ Animations التوليدي الشامل (12 Dynamic Kinetic Archetypes):
    - يرسم الترويسة العلوية الموحدة + العنوان المتحرك كلمة بكلمة مع ستيكر الكلمة المفتاحية.
    - يرسم في منطقة المسرح الوسطى (`y: 0.25h .. 0.78h`) أحد الأنماط الـ 12 التفاعلية المتحركة
      بدون أي تداخل نصوص وبتحريك مستمر 30fps من أول فريم لآخر فريم!
    """
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img, "RGBA")
    pal = style_spec.get("palette", {})
    is_light_bg = bool(pal.get("is_light_bg", False))

    step_num = int(scene_meta.get("step_number") or style_spec.get("step_number") or 1)
    total_scenes = int(scene_meta.get("total_scenes_count") or 8)
    badge_label = str(scene_meta.get("badge_label") or "محور أساسي")
    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "فكرة محورية ذكية")
    kpi_val = str(scene_meta.get("kpi_value") or "نتائج مضمونة")
    kpi_lbl = str(scene_meta.get("kpi_label") or "أداء احترافي")

    sub_items = [re.sub(r"^\d+[\.\-\s]+", "", str(s)).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    while len(sub_items) < 4:
        sub_items.append(kpi_lbl if len(sub_items) % 2 == 0 else kpi_val)

    primary_c = tuple(pal.get("primary", (27, 174, 202)))
    secondary_c = tuple(pal.get("secondary", (250, 204, 21)))
    accent_c = tuple(pal.get("accent", (16, 185, 129)))
    headline_txt_c = tuple(pal.get("headline_txt", (15, 23, 42) if is_light_bg else (255, 255, 255)))
    sticker_bg_c = tuple(pal.get("sticker_bg", (2, 132, 199) if is_light_bg else (255, 255, 255)))
    sticker_txt_c = tuple(pal.get("sticker_txt", (255, 255, 255) if is_light_bg else (11, 24, 31)))
    dark_navy = (11, 24, 31)

    # 1. الترويسة العلوية الموحدة
    _render_unified_top_header(draw, w, h, step_num, total_scenes, badge_label, style_spec, scene_progress)

    # 2. العنوان الرئيسي المتحرك كلمة بكلمة مع ستيكر الكلمة المفتاحية
    kw_list = scene_meta.get("key_words") or []
    hl_word = kw_list[0] if kw_list else ""
    _draw_sticker_highlighted_headline(
        draw=draw,
        bbox=(int(w * 0.06), int(h * 0.105), int(w * 0.94), int(h * 0.235)),
        headline_text=concept_title,
        highlight_word=hl_word,
        headline_txt_color=headline_txt_c,
        sticker_bg_color=sticker_bg_c,
        sticker_txt_color=sticker_txt_c,
        initial_font_size=max(24, int(h * 0.036)),
        scene_progress=scene_progress,
        global_t=global_t
    )

    # تحديد الـ Visual Archetype لهذا المشهد (يدعم المسميات الـ 12 الجديدة والمسميات السابقة)
    raw_arch = str(style_spec.get("visual_archetype") or scene_meta.get("archetype") or "").strip()
    legacy_map = {
        "stage_trust_bubbles": "radar_target_sweep",
        "stage_balance_scale": "damped_balance_scale",
        "saas_folder_reorder": "blueprint_numbered_steps",
        "saas_grid_2x2_cursor": "bento_grid_2x2_ripple",
        "saas_typewriter_mechanism": "typewriter_gear_console",
        "saas_process_flow": "bezier_growth_nodes",
        "video_schedule_table": "nle_timeline_matrix",
        "stage_before_after_checklist": "split_before_after_cards",
        "interactive_cta_outro": "rocket_bars_cta_outro"
    }
    archetype = legacy_map.get(raw_arch, raw_arch)
    if archetype not in ALL_DYNAMIC_VISUAL_ARCHETYPES:
        archetype = ALL_DYNAMIC_VISUAL_ARCHETYPES[(step_num - 1) % len(ALL_DYNAMIC_VISUAL_ARCHETYPES)]
    if step_num == total_scenes and total_scenes >= 2:
        archetype = "rocket_bars_cta_outro"

    stiffness = float(style_spec.get("spring_stiffness", 215.0))
    damping = float(style_spec.get("spring_damping", 13.5))
    s_card = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.04, duration=0.42, stiffness=stiffness, damping=damping)
    float_y = int(float(style_spec.get("camera_float_amp", 6.0)) * math.sin(global_t * 2.6 + step_num))

    # منطقة المسرح الصافية للرسومات والبطاقات
    st_x1, st_y1 = int(w * 0.07), int(h * 0.255) + float_y
    st_x2, st_y2 = int(w * 0.93), int(h * 0.775) + float_y
    st_w, st_h = st_x2 - st_x1, st_y2 - st_y1

    # =========================================================================
    # Archetype 1: agency_receipt_stamp (بطاقة الفاتورة التفاعلية والختم المتحرك + أبراج العملات بدون أي تداخل!)
    # =========================================================================
    if archetype == "agency_receipt_stamp":
        cw, ch = int(st_w * 0.94 * s_card), int(st_h * 0.56 * s_card)
        rx1, ry1 = cx - cw // 2, st_y1
        rx2, ry2 = rx1 + cw, ry1 + ch

        hdr_h = max(36, int(ch * 0.20))
        draw.rounded_rectangle([(rx1, ry1), (rx2, ry1 + hdr_h)], radius=14, fill=(*primary_c, 255))
        for di in range(3):
            draw.ellipse([(rx1 + 16 + di * 14, ry1 + hdr_h // 2 - 4), (rx1 + 24 + di * 14, ry1 + hdr_h // 2 + 4)], fill=(255, 255, 255, 220))
        tag_w = int(cw * 0.34)
        draw.rounded_rectangle([(rx2 - tag_w - 10, ry1 + 5), (rx2 - 10, ry1 + hdr_h - 5)], radius=10, fill=(255, 255, 255, 252))
        draw_contained_arabic_text(draw, (rx2 - tag_w - 8, ry1 + 5, rx2 - 12, ry1 + hdr_h - 5), kpi_lbl, initial_font_size=14, fill=(*dark_navy, 255))

        # جسم الفاتورة الأبيض مقسم هندسياً إلى منطقتين معزولتين تماماً لمنع أي تصادم نصي!
        body_y1 = ry1 + hdr_h + 4
        pts_receipt = [(rx1 + 6, body_y1), (rx2 - 6, body_y1), (rx2 - 6, ry2)]
        num_teeth = 12
        tooth_w = (rx2 - rx1 - 12) / float(num_teeth)
        for ti in range(num_teeth, -1, -1):
            tx = int(rx1 + 6 + ti * tooth_w)
            ty = ry2 + (8 if ti % 2 == 1 else 0)
            pts_receipt.append((tx, ty))
        draw.polygon([(px, py + 6) for px, py in pts_receipt], fill=(0, 0, 0, 80))
        draw.polygon(pts_receipt, fill=(255, 255, 255, 254))

        # المنطقة العلوية (45% من جسم الفاتورة): سطرا المعلومات مع شريط تقدم متحرك
        upper_zone_h = int((ry2 - body_y1) * 0.46)
        r1_y = body_y1 + int(upper_zone_h * 0.36)
        draw_contained_arabic_text(draw, (rx1 + 22, r1_y - 14, rx2 - 22, r1_y + 14), sub_items[0], initial_font_size=17, fill=(30, 41, 59, 255))

        bar_y = body_y1 + int(upper_zone_h * 0.78)
        bar_w = int(cw * 0.78)
        bar_x1 = cx - bar_w // 2
        fill_p = min(1.0, max(0.15, scene_progress * 1.4))
        draw.rounded_rectangle([(bar_x1, bar_y - 5), (bar_x1 + bar_w, bar_y + 5)], radius=5, fill=(226, 232, 240, 255))
        draw.rounded_rectangle([(bar_x1, bar_y - 5), (bar_x1 + int(bar_w * fill_p), bar_y + 5)], radius=5, fill=(*primary_c, 255))

        # المنطقة السفلية المعزولة (54% من جسم الفاتورة): الختم البارز ينبثق بفيزياء الزنبرك دون لمس السطر العلوي!
        stamp_pop = _staggered_spring(scene_progress, delay=0.14, duration=0.40, stiffness=250.0, damping=13.0)
        stamp_w = int(cw * 0.82 * max(0.75, stamp_pop))
        stamp_h = max(42, int((ry2 - body_y1) * 0.34))
        stamp_cy = body_y1 + upper_zone_h + (ry2 - body_y1 - upper_zone_h) // 2
        sx1, sy1 = cx - stamp_w // 2, stamp_cy - stamp_h // 2
        draw.rounded_rectangle([(sx1, sy1 + 4), (sx1 + stamp_w, sy1 + stamp_h + 4)], radius=12, fill=(0, 0, 0, 55))
        draw.rounded_rectangle([(sx1, sy1), (sx1 + stamp_w, sy1 + stamp_h)], radius=12, fill=(248, 250, 252, 255), outline=(*dark_navy, 255), width=3)
        draw_contained_arabic_text(
            draw, (sx1 + 12, sy1 + 2, sx1 + stamp_w - 12, sy1 + stamp_h - 2),
            f"{kpi_val} • {sub_items[1][:18]}", initial_font_size=20, fill=(*dark_navy, 255)
        )

        # منطقة الأبراج الصاعدة أسفل الفاتورة (في مساحة نظيفة تماماً بدون أي رقم خلفي)
        coin_h = max(64, int(st_h * 0.38))
        coin_w = int(st_w * 0.68)
        coin_ic = render_cairo_vector_illustration(
            "growth_analytics", coin_w, coin_h, scene_progress, global_t,
            {"primary": primary_c, "secondary": secondary_c, "accent": accent_c}
        )
        img.alpha_composite(coin_ic, (cx - coin_w // 2, ry2 + 12))
        return img

    # =========================================================================
    # Archetype 2: bezier_growth_nodes (مخطط المنحنى الصاعد المرسوم تدريجياً مع العقد 01->04)
    # =========================================================================
    if archetype == "bezier_growth_nodes":
        cw, ch = int(st_w * 0.94 * s_card), int(st_h * 0.66 * s_card)
        card_img = Image.new("RGBA", (cw + 24, ch + 24), (0, 0, 0, 0))
        cdraw = ImageDraw.Draw(card_img, "RGBA")
        cdraw.rounded_rectangle([(12, 16), (cw + 12, ch + 16)], radius=24, fill=(0, 0, 0, 70))
        cdraw.rounded_rectangle([(8, 8), (cw + 8, ch + 8)], radius=24, fill=(255, 255, 255, 255), outline=(*primary_c, 220), width=2)

        for gx in range(28, cw, 36):
            cdraw.line([(gx, 16), (gx, ch)], fill=(226, 232, 240, 170), width=1)
        for gy in range(28, ch, 36):
            cdraw.line([(16, gy), (cw, gy)], fill=(226, 232, 240, 170), width=1)

        pill_y = 20
        cdraw.rounded_rectangle([(22, pill_y), (cw - 10, pill_y + 36)], radius=12, fill=(241, 245, 249, 255))
        draw_contained_arabic_text(
            cdraw, (28, pill_y, cw - 16, pill_y + 36),
            f"{kpi_val}  •  {kpi_lbl}", initial_font_size=17, fill=(*dark_navy, 255)
        )

        # رسم المنحنى تدريجياً من اليسار لليمين مع تقدم المشهد (Progressive Curve Tracing)
        nodes_xy = [
            (int(cw * 0.16), int(ch * 0.80)),
            (int(cw * 0.39), int(ch * 0.64)),
            (int(cw * 0.63), int(ch * 0.47)),
            (int(cw * 0.85), int(ch * 0.30)),
        ]
        trace_prog = min(1.0, max(0.12, scene_progress * 1.35))
        dense_pts: List[Tuple[int, int]] = []
        total_segs = len(nodes_xy) - 1
        for si in range(total_segs):
            p0, p1 = nodes_xy[si], nodes_xy[si + 1]
            for sub in range(16):
                u = sub / 16.0
                g_u = (si + u) / float(total_segs)
                if g_u <= trace_prog:
                    px = int(p0[0] + (p1[0] - p0[0]) * u)
                    py = int(p0[1] + (p1[1] - p0[1]) * (3 * u * u - 2 * u * u * u))
                    dense_pts.append((px, py))
        if trace_prog >= 0.99:
            dense_pts.append(nodes_xy[-1])

        if len(dense_pts) >= 2:
            poly_area = [(dense_pts[0][0], ch - 6)] + dense_pts + [(dense_pts[-1][0], ch - 6)]
            cdraw.polygon(poly_area, fill=(primary_c[0], primary_c[1], primary_c[2], 52))
            cdraw.line(dense_pts, fill=(*dark_navy, 255), width=4)

        for ni, (nx, ny) in enumerate(nodes_xy):
            node_u = ni / float(total_segs)
            if trace_prog + 0.08 >= node_u:
                n_pop = _staggered_spring(scene_progress, delay=ni * 0.12, duration=0.35)
                nr = max(10, int(16 * n_pop))
                n_col = primary_c if (ni == len(nodes_xy) - 1 or ni == 0) else dark_navy
                if ni == len(nodes_xy) - 1:
                    pulse_r = nr + int(5 + 4 * math.sin(global_t * 5.0))
                    cdraw.ellipse([(nx - pulse_r, ny - pulse_r), (nx + pulse_r, ny + pulse_r)], fill=(*primary_c, 70))
                cdraw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(*n_col, 255), outline=(255, 255, 255, 255), width=2)
                nf = get_arabic_font(12, bold=True)
                draw_arabic_text(cdraw, (nx, ny), f"{ni + 1:02d}", font=nf, fill=(255, 255, 255, 255))

        tilt_deg = float(style_spec.get("card_tilt_deg", 1.4)) * math.sin(min(1.0, scene_progress * 1.5) * math.pi * 0.5)
        rotated_card = card_img.rotate(tilt_deg, resample=Image.Resampling.BICUBIC, expand=True)
        img.alpha_composite(rotated_card, (cx - rotated_card.width // 2, st_y1 + 6))

        draw = ImageDraw.Draw(img, "RGBA")
        # كبسولتان سفليتان تظهران بالتتابع تحت بطاقة المنحنى
        sub_y = st_y1 + rotated_card.height + 14
        pill_w = (st_w - 14) // 2
        for pi in range(2):
            p_sp = _staggered_spring(scene_progress, delay=0.18 + pi * 0.10, duration=0.38)
            px1 = st_x1 + pi * (pill_w + 14)
            py1 = sub_y + int(16 * (1.0 - p_sp))
            draw.rounded_rectangle([(px1, py1), (px1 + pill_w, py1 + 48)], radius=16, fill=(11, 24, 31, 215), outline=(*primary_c, 220), width=2)
            draw_contained_arabic_text(draw, (px1 + 10, py1, px1 + pill_w - 10, py1 + 48), sub_items[pi], initial_font_size=16, fill=(255, 255, 255, 255))
        return img

    # =========================================================================
    # Archetype 3: live_magnifier_scanner (المكبّر الفاحص المتحرك حياً فوق البطاقات)
    # =========================================================================
    if archetype == "live_magnifier_scanner":
        cw, ch = int(st_w * 0.94 * s_card), int(st_h * 0.72 * s_card)
        bx1, by1 = cx - cw // 2, st_y1 + int(st_h * 0.06)
        bx2, by2 = bx1 + cw, by1 + ch
        draw.rounded_rectangle([(bx1, by1 + 10), (bx2, by2 + 10)], radius=24, fill=(0, 0, 0, 75))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=24, fill=(255, 255, 255, 255), outline=(*primary_c, 220), width=2)

        # شريط علوي أنيق داخل البطاقة بدون أي بتر للنصوص
        hdr_y1, hdr_y2 = by1 + 16, by1 + 60
        badge_w = int(cw * 0.34)
        draw.rounded_rectangle([(bx2 - badge_w - 16, hdr_y1), (bx2 - 16, hdr_y2)], radius=12, fill=(*primary_c, 255))
        draw_contained_arabic_text(draw, (bx2 - badge_w - 10, hdr_y1, bx2 - 22, hdr_y2), kpi_val, initial_font_size=16, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(bx1 + 16, hdr_y1), (bx2 - badge_w - 28, hdr_y2)], radius=12, fill=(241, 245, 249, 255))
        draw_contained_arabic_text(draw, (bx1 + 24, hdr_y1, bx2 - badge_w - 34, hdr_y2), kpi_lbl, initial_font_size=16, fill=(*dark_navy, 255))

        # 3 بطاقات فرعية داخلية يتم فحصها وتكبيرها عند مرور العدسة المكبرة فوقها!
        sq_y1 = hdr_y2 + 18
        sq_h = by2 - sq_y1 - 20
        sq_w = (cw - 56) // 3

        # موقع العدسة المتحرك بسلاسة عبر البطاقات الثلاث طوال المشهد
        scan_u = 0.5 - 0.45 * math.cos(scene_progress * math.pi * 1.6)
        mag_cx = int(bx1 + 36 + scan_u * (cw - 72))
        mag_cy = sq_y1 + sq_h // 2 + int(10 * math.sin(global_t * 3.5))
        active_sq_idx = min(2, max(0, int(scan_u * 3.0)))

        for si in range(3):
            sx = bx1 + 16 + si * (sq_w + 12)
            is_hovered = (si == active_sq_idx)
            pad_zoom = -4 if is_hovered else 0
            scol = (224, 242, 254, 255) if is_hovered else (241, 245, 249, 255)
            b_col = primary_c if is_hovered else (203, 213, 225)
            draw.rounded_rectangle(
                [(sx + pad_zoom, sq_y1 + pad_zoom), (sx + sq_w - pad_zoom, sq_y1 + sq_h - pad_zoom)],
                radius=16, fill=scol, outline=(*b_col, 255), width=3 if is_hovered else 1
            )
            # دائرة رقم البطاقة الفرعية
            ic_y = sq_y1 + int(sq_h * 0.25)
            draw.ellipse([(sx + sq_w // 2 - 15, ic_y - 15), (sx + sq_w // 2 + 15, ic_y + 15)], fill=(*primary_c, 255) if is_hovered else (148, 163, 184, 255))
            nf = get_arabic_font(13, bold=True)
            draw_arabic_text(draw, (sx + sq_w // 2, ic_y), str(si + 1), font=nf, fill=(255, 255, 255, 255))

            if si < len(sub_items):
                draw_contained_arabic_text(
                    draw, (sx + 6, sq_y1 + int(sq_h * 0.48), sx + sq_w - 6, sq_y1 + sq_h - 10),
                    sub_items[si], initial_font_size=16 if is_hovered else 14, fill=(*dark_navy, 255)
                )

        # رسم العدسة المكبرة الفاحصة المتحركة فوق البطاقات مع لمعان الزجاج
        mag_r = int(min(cw, ch) * 0.19)
        handle_end_x = mag_cx - int(mag_r * 1.35)
        handle_end_y = mag_cy + int(mag_r * 1.35)
        draw.line([(mag_cx - int(mag_r * 0.68), mag_cy + int(mag_r * 0.68)), (handle_end_x, handle_end_y)], fill=(*dark_navy, 255), width=11)
        draw.ellipse([(mag_cx - mag_r, mag_cy - mag_r), (mag_cx + mag_r, mag_cy + mag_r)], fill=(255, 255, 255, 88), outline=(*dark_navy, 255), width=6)
        draw.ellipse([(mag_cx - mag_r + 5, mag_cy - mag_r + 5), (mag_cx + mag_r - 5, mag_cy + mag_r - 5)], outline=(*primary_c, 255), width=3)
        draw.arc([(mag_cx - mag_r + 10, mag_cy - mag_r + 10), (mag_cx + mag_r - 10, mag_cy + mag_r - 10)], start=200, end=260, fill=(255, 255, 255, 230), width=4)
        return img

    # =========================================================================
    # Archetype 4: radar_target_sweep (رادار الاستهداف الدوار بشعاع مسح ضوئي حي 360°)
    # =========================================================================
    if archetype == "radar_target_sweep":
        rad_cy = st_y1 + int(st_h * 0.44)
        max_r = int(min(st_w, st_h) * 0.34 * s_card)
        ring_col = (15, 23, 42) if is_light_bg else (255, 255, 255)

        for ri, r_frac in enumerate([1.0, 0.70, 0.40]):
            rr = int(max_r * r_frac)
            draw.ellipse(
                [(cx - rr, rad_cy - rr), (cx + rr, rad_cy + rr)],
                fill=(primary_c[0], primary_c[1], primary_c[2], 22 if ri == 0 else 12),
                outline=(*ring_col, 215 if ri == 0 else 125),
                width=3 if ri == 0 else 2
            )

        draw.line([(cx - max_r - 14, rad_cy), (cx + max_r + 14, rad_cy)], fill=(*ring_col, 130), width=2)
        draw.line([(cx, rad_cy - max_r - 14), (cx, rad_cy + max_r + 14)], fill=(*ring_col, 130), width=2)

        # شعاع المسح الدوار المستمر (360° Rotating Radar Sweep Beam)
        sweep_deg = (global_t * 140.0) % 360.0
        draw.pieslice(
            [(cx - max_r, rad_cy - max_r), (cx + max_r, rad_cy + max_r)],
            start=sweep_deg - 42.0, end=sweep_deg,
            fill=(primary_c[0], primary_c[1], primary_c[2], 85)
        )

        # العقد المحيطة التي تنبض وتظهر عليها علامة الصح
        node_angles = [i * (math.pi / 3.0) for i in range(6)]
        for ni, ang in enumerate(node_angles):
            n_sp = _staggered_spring(scene_progress, delay=0.05 + ni * 0.06, duration=0.38)
            dist_r = max_r * 0.68 * n_sp
            nx = cx + int(dist_r * math.cos(ang + global_t * 0.35))
            ny = rad_cy + int(dist_r * math.sin(ang + global_t * 0.35))
            nr = max(16, int(max_r * 0.17))
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(255, 255, 255, 252), outline=(*dark_navy, 255), width=2)
            draw.ellipse([(nx - nr // 2, ny - nr // 2), (nx + nr // 2, ny + nr // 2)], fill=(*primary_c, 255))
            if ni % 2 == 0 and scene_progress >= 0.25 + ni * 0.08:
                _draw_checkmark_badge(draw, nx + nr - 3, ny - nr + 3, 9, color_rgb=accent_c)

        # بطاقة المؤشر السفلية تحت الرادار
        pill_y = rad_cy + max_r + 18
        draw.rounded_rectangle([(st_x1 + 14, pill_y), (st_x2 - 14, pill_y + 52)], radius=26, fill=(255, 255, 255, 252), outline=(*primary_c, 230), width=2)
        draw_contained_arabic_text(
            draw, (st_x1 + 26, pill_y, st_x2 - 26, pill_y + 52),
            f"{kpi_val}  •  {sub_items[0]}", initial_font_size=18, fill=(*dark_navy, 255)
        )
        return img

    # =========================================================================
    # Archetype 5: fan_out_mobile_report (الهاتف الذكي مع البطاقات المروحية المنبثقة ومؤشر الأداء)
    # =========================================================================
    if archetype == "fan_out_mobile_report":
        pw, ph = int(st_w * 0.48 * s_card), int(st_h * 0.78 * s_card)
        px1, py1 = cx - pw // 2, st_y1 + int(st_h * 0.05)
        px2, py2 = px1 + pw, py1 + ph

        # البطاقتان المروحيتان اللتان تنفتحان من خلف الهاتف بفيزياء الزنبرك (Animated Fan-Out Cards)
        fan_p = _staggered_spring(scene_progress, delay=0.12, duration=0.45)
        fan_offset = int(pw * 0.44 * fan_p)
        side_w, side_h = int(pw * 0.72), int(ph * 0.62)
        sy1 = py1 + int(ph * 0.18)

        # بطاقة اليسار واليمين الخلفيتان
        draw.rounded_rectangle([(cx - fan_offset - side_w // 2, sy1), (cx - fan_offset + side_w // 2, sy1 + side_h)], radius=18, fill=(241, 245, 249, 240), outline=(*primary_c, 200), width=2)
        draw.rounded_rectangle([(cx + fan_offset - side_w // 2, sy1), (cx + fan_offset + side_w // 2, sy1 + side_h)], radius=18, fill=(241, 245, 249, 240), outline=(*primary_c, 200), width=2)

        # جسم الهاتف الأبيض المركزي
        draw.rounded_rectangle([(px1, py1 + 8), (px2, py2 + 8)], radius=26, fill=(0, 0, 0, 85))
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=26, fill=(255, 255, 255, 255), outline=(*dark_navy, 255), width=4)

        rep_h = 34
        draw.rounded_rectangle([(px1 + 14, py1 + 14), (px2 - 14, py1 + 14 + rep_h)], radius=12, fill=(241, 245, 249, 255), outline=(*dark_navy, 255), width=2)
        draw_contained_arabic_text(draw, (px1 + 18, py1 + 14, px2 - 18, py1 + 14 + rep_h), kpi_lbl, initial_font_size=15, fill=(*dark_navy, 255))

        m_y = py1 + 14 + rep_h + 14
        draw_contained_arabic_text(draw, (px1 + 12, m_y, px2 - 12, m_y + 34), kpi_val, initial_font_size=21, fill=(*primary_c, 255))

        # مدرج الصعود المتحرك داخل الهاتف
        st_y = m_y + 42
        st_h_in = int(ph * 0.22)
        anim_u = min(1.0, max(0.15, scene_progress * 1.4))
        step_pts = [
            (px1 + 20, st_y + st_h_in),
            (px1 + int(pw * 0.38), st_y + st_h_in),
            (px1 + int(pw * 0.38), st_y + int(st_h_in * (1.0 - 0.45 * anim_u))),
            (px1 + int(pw * 0.66), st_y + int(st_h_in * (1.0 - 0.45 * anim_u))),
            (px1 + int(pw * 0.66), st_y + int(st_h_in * (1.0 - 0.85 * anim_u))),
            (px2 - 20, st_y + int(st_h_in * (1.0 - 0.85 * anim_u)))
        ]
        draw.line(step_pts, fill=(*primary_c, 255), width=4)

        # حلقة النسبة المئوية الحية أسفل شاشة الهاتف
        ring_y = py2 - 36
        ring_r = 18
        sweep_ang = int(285 * anim_u)
        draw.ellipse([(px1 + 20, ring_y - ring_r), (px1 + 20 + ring_r * 2, ring_y + ring_r)], outline=(226, 232, 240, 255), width=4)
        draw.arc([(px1 + 20, ring_y - ring_r), (px1 + 20 + ring_r * 2, ring_y + ring_r)], start=-90, end=-90 + sweep_ang, fill=(*primary_c, 255), width=5)
        draw_contained_arabic_text(draw, (px1 + 26 + ring_r * 2, ring_y - 18, px2 - 12, ring_y + 18), sub_items[0], initial_font_size=15, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 6: blueprint_numbered_steps (قائمة الخطوات المرقمة 1-4 التفاعلية مع مؤشر النقر)
    # =========================================================================
    if archetype == "blueprint_numbered_steps":
        row_h = max(48, int(st_h * 0.175))
        row_gap = max(12, int(st_h * 0.042))
        circle_r = max(18, int(row_h * 0.42))
        right_anchor_x = st_x2 - 4
        pill_left_x = st_x1 + 4

        active_step = min(3, int(scene_progress * 4.2))
        target_click_xy = (pill_left_x + 40, st_y1 + active_step * (row_h + row_gap) + row_h // 2)

        for i in range(4):
            item_pop = _staggered_spring(scene_progress, delay=0.05 + i * 0.08, duration=0.40)
            ry_center = st_y1 + 14 + i * (row_h + row_gap) + row_h // 2 + int(22 * (1.0 - item_pop))
            is_done = (i <= active_step)

            p_x2 = right_anchor_x - circle_r * 2 - 12
            p_x1 = pill_left_x
            fill_c = (255, 255, 255, 252) if is_done else (241, 245, 249, 215)
            out_c = primary_c if is_done else (148, 163, 184)
            draw.rounded_rectangle(
                [(p_x1, ry_center - row_h // 2 + 3), (p_x2, ry_center + row_h // 2 + 3)],
                radius=row_h // 2, fill=(0, 0, 0, 45)
            )
            draw.rounded_rectangle(
                [(p_x1, ry_center - row_h // 2), (p_x2, ry_center + row_h // 2)],
                radius=row_h // 2, fill=fill_c, outline=(*out_c, 240), width=3 if i == active_step else 2
            )

            if is_done:
                _draw_checkmark_badge(draw, p_x1 + 26, ry_center, 11, color_rgb=accent_c, scale=1.05 if i == active_step else 0.9)

            draw_contained_arabic_text(
                draw, (p_x1 + 44, ry_center - row_h // 2, p_x2 - 14, ry_center + row_h // 2),
                sub_items[i], initial_font_size=max(16, int(h * 0.024)), fill=(*dark_navy, 255)
            )

            c_cx = right_anchor_x - circle_r
            c_col = primary_c if is_done else dark_navy
            draw.ellipse(
                [(c_cx - circle_r, ry_center - circle_r), (c_cx + circle_r, ry_center + circle_r)],
                fill=(*c_col, 255), outline=(255, 255, 255, 245), width=2
            )
            nf = get_arabic_font(max(17, int(circle_r * 0.90)), bold=True)
            draw_arabic_text(draw, (c_cx, ry_center), str(i + 1), font=nf, fill=(255, 255, 255, 255))

        _draw_cursor_with_ripple(draw, (st_x1 + 80, st_y2 - 10), target_click_xy, scene_progress, accent_rgb=primary_c)
        return img

    # =========================================================================
    # Archetype 7: damped_balance_scale (الميزان الفيزيائي المتأرجح للمقارنة بين المشكلة والحل)
    # =========================================================================
    if archetype == "damped_balance_scale":
        left_pan_info = scene_meta.get("balance_left") or ("الطريقة التقليدية", "وقت ومجهود")
        right_pan_info = scene_meta.get("balance_right") or (kpi_lbl, kpi_val)

        tilt_prog = _staggered_spring(scene_progress, delay=0.10, duration=0.52, stiffness=180.0, damping=11.0)
        sway = 2.2 * math.sin(global_t * 3.8)
        tilt_angle = math.radians(-13.5 * tilt_prog + sway)

        pivot_x, pivot_y = cx, st_y1 + int(st_h * 0.34)
        base_y = st_y1 + int(st_h * 0.88)
        beam_col = (15, 23, 42, 235) if is_light_bg else (255, 255, 255, 235)

        draw.line([(pivot_x, pivot_y), (pivot_x, base_y)], fill=beam_col, width=7)
        draw.rounded_rectangle([(pivot_x - int(st_w * 0.20), base_y - 8), (pivot_x + int(st_w * 0.20), base_y + 8)], radius=8, fill=(*secondary_c, 255))
        draw.ellipse([(pivot_x - 14, pivot_y - 14), (pivot_x + 14, pivot_y + 14)], fill=(*secondary_c, 255), outline=(255, 255, 255, 245), width=3)

        arm_half = int(st_w * 0.30)
        lx = pivot_x - int(arm_half * math.cos(tilt_angle))
        ly = pivot_y - int(arm_half * math.sin(tilt_angle))
        rx = pivot_x + int(arm_half * math.cos(tilt_angle))
        ry = pivot_y + int(arm_half * math.sin(tilt_angle))

        draw.line([(lx, ly), (rx, ry)], fill=(*secondary_c, 255), width=6)

        pan_w, pan_h = int(st_w * 0.42), int(st_h * 0.34)
        l_box = (lx - pan_w // 2, ly + 18, lx + pan_w // 2, ly + 18 + pan_h)
        draw.line([(lx, ly), (lx - 22, ly + 18), (lx + 22, ly + 18), (lx, ly)], fill=beam_col, width=2)
        draw.rounded_rectangle([(l_box[0], l_box[1] + 4), (l_box[2], l_box[3] + 4)], radius=18, fill=(0, 0, 0, 60))
        draw.rounded_rectangle([(l_box[0], l_box[1]), (l_box[2], l_box[3])], radius=18, fill=(255, 255, 255, 252), outline=(239, 68, 68, 240), width=3)
        draw_contained_arabic_text(draw, (l_box[0] + 8, l_box[1] + 8, l_box[2] - 8, l_box[1] + int(pan_h * 0.48)), str(left_pan_info[0]), initial_font_size=16, fill=(71, 85, 105, 255))
        draw_contained_arabic_text(draw, (l_box[0] + 8, l_box[1] + int(pan_h * 0.50), l_box[2] - 8, l_box[3] - 8), str(left_pan_info[1]), initial_font_size=18, fill=(239, 68, 68, 255))

        r_box = (rx - pan_w // 2, ry + 18, rx + pan_w // 2, ry + 18 + pan_h)
        draw.line([(rx, ry), (rx - 22, ry + 18), (rx + 22, ry + 18), (rx, ry)], fill=beam_col, width=2)
        draw.rounded_rectangle([(r_box[0], r_box[1] + 4), (r_box[2], r_box[3] + 4)], radius=18, fill=(0, 0, 0, 60))
        draw.rounded_rectangle([(r_box[0], r_box[1]), (r_box[2], r_box[3])], radius=18, fill=(255, 255, 255, 252), outline=(*accent_c, 255), width=3)
        _draw_checkmark_badge(draw, r_box[2] - 14, r_box[1] + 14, 11, color_rgb=accent_c)
        draw_contained_arabic_text(draw, (r_box[0] + 8, r_box[1] + 8, r_box[2] - 24, r_box[1] + int(pan_h * 0.48)), str(right_pan_info[0]), initial_font_size=16, fill=(30, 41, 59, 255))
        draw_contained_arabic_text(draw, (r_box[0] + 8, r_box[1] + int(pan_h * 0.50), r_box[2] - 8, r_box[3] - 8), str(right_pan_info[1]), initial_font_size=18, fill=(*accent_c, 255))
        return img

    # =========================================================================
    # Archetype 8: split_before_after_cards (مقارنة قبل/بعد المزدوجة مع قائمة التدقيق الحية)
    # =========================================================================
    if archetype == "split_before_after_cards":
        ba_info = scene_meta.get("before_after") or ("الطريقة التقليدية", "3.9", sub_items[0], "9.8")
        top_h = int(st_h * 0.46)
        card_w = int(st_w * 0.44)
        slide_p = _staggered_spring(scene_progress, delay=0.04, duration=0.42)

        bef_x1 = st_x2 - card_w + int(30 * (1.0 - slide_p))
        bef_y1 = st_y1 + 4
        draw.rounded_rectangle([(bef_x1, bef_y1 + 4), (bef_x1 + card_w, bef_y1 + top_h + 4)], radius=20, fill=(0, 0, 0, 60))
        draw.rounded_rectangle([(bef_x1, bef_y1), (bef_x1 + card_w, bef_y1 + top_h)], radius=20, fill=(255, 255, 255, 250), outline=(239, 68, 68, 235), width=3)
        draw.rounded_rectangle([(bef_x1 + 14, bef_y1 + 12), (bef_x1 + card_w - 14, bef_y1 + 42)], radius=14, fill=(239, 68, 68, 245))
        draw_contained_arabic_text(draw, (bef_x1 + 18, bef_y1 + 12, bef_x1 + card_w - 18, bef_y1 + 42), f"قبل • {ba_info[1]}", initial_font_size=15, fill=(255, 255, 255, 255))
        draw_contained_arabic_text(draw, (bef_x1 + 10, bef_y1 + 52, bef_x1 + card_w - 10, bef_y1 + top_h - 14), str(ba_info[0]), initial_font_size=17, fill=(30, 41, 59, 255))

        aft_x1 = st_x1 - int(30 * (1.0 - slide_p))
        draw.rounded_rectangle([(aft_x1, bef_y1 + 4), (aft_x1 + card_w, bef_y1 + top_h + 4)], radius=20, fill=(0, 0, 0, 60))
        draw.rounded_rectangle([(aft_x1, bef_y1), (aft_x1 + card_w, bef_y1 + top_h)], radius=20, fill=(255, 255, 255, 252), outline=(*accent_c, 255), width=3)
        draw.rounded_rectangle([(aft_x1 + 14, bef_y1 + 12), (aft_x1 + card_w - 14, bef_y1 + 42)], radius=14, fill=(*accent_c, 255))
        draw_contained_arabic_text(draw, (aft_x1 + 18, bef_y1 + 12, aft_x1 + card_w - 18, bef_y1 + 42), f"بعد • {ba_info[3]}", initial_font_size=15, fill=(255, 255, 255, 255))
        draw_contained_arabic_text(draw, (aft_x1 + 10, bef_y1 + 52, aft_x1 + card_w - 10, bef_y1 + top_h - 14), str(ba_info[2]), initial_font_size=17, fill=(*dark_navy, 255))

        # جسر المقارنة النابض في المنتصف
        arr_shift = int(5 * math.sin(global_t * 5.5))
        draw.ellipse([(cx - 20 + arr_shift, bef_y1 + top_h // 2 - 20), (cx + 20 + arr_shift, bef_y1 + top_h // 2 + 20)], fill=(*secondary_c, 255), outline=(255, 255, 255, 255), width=2)
        draw.line([(cx + 8 + arr_shift, bef_y1 + top_h // 2), (cx - 8 + arr_shift, bef_y1 + top_h // 2)], fill=(*dark_navy, 255), width=3)

        # بطاقة قائمة التدقيق السفلية
        chk_y1 = bef_y1 + top_h + 16
        chk_h = st_y2 - chk_y1
        draw.rounded_rectangle([(st_x1, chk_y1), (st_x2, st_y2)], radius=22, fill=(255, 255, 255, 250), outline=(*primary_c, 225), width=2)
        for ci in range(3):
            ry = chk_y1 + int(chk_h * 0.22) + ci * int(chk_h * 0.28)
            is_checked = scene_progress >= (0.12 + ci * 0.22)
            _draw_checkmark_badge(draw, st_x2 - 28, ry, 12, color_rgb=accent_c if is_checked else (148, 163, 184), scale=1.08 if is_checked else 0.85)
            draw_contained_arabic_text(draw, (st_x1 + 16, ry - 16, st_x2 - 48, ry + 16), sub_items[ci], initial_font_size=16, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 9: bento_grid_2x2_ripple (شبكة Bento الرباعية التفاعلية مع أشرطة التقدم ونقرة الماوس)
    # =========================================================================
    if archetype == "bento_grid_2x2_ripple":
        gap_x, gap_y = 14, 14
        card_w = (st_w - gap_x) // 2
        card_h = (st_h - gap_y) // 2
        grid_colors = [primary_c, (139, 92, 246), (236, 72, 153), accent_c]

        active_cell = min(3, int(scene_progress * 4.0))
        target_click_xy = (cx, st_y1 + st_h // 2)

        for idx in range(4):
            row, col = idx // 2, idx % 2
            sp = _staggered_spring(scene_progress, delay=idx * 0.07, duration=0.38)
            gx1 = st_x1 + col * (card_w + gap_x)
            gy1 = int(st_y1 + row * (card_h + gap_y) + 24 * (1.0 - sp))
            gx2, gy2 = gx1 + card_w, gy1 + card_h
            gcol = grid_colors[idx]

            if idx == active_cell:
                target_click_xy = (gx1 + int(card_w * 0.26), gy1 + int(card_h * 0.78))

            draw.rounded_rectangle([(gx1, gy1 + 5), (gx2, gy2 + 5)], radius=20, fill=(0, 0, 0, 65))
            draw.rounded_rectangle([(gx1, gy1), (gx2, gy2)], radius=20, fill=(255, 255, 255, 252), outline=(*gcol, 245), width=3 if idx == active_cell else 2)

            ic_x, ic_y = (gx1 + gx2) // 2, gy1 + int(card_h * 0.26)
            draw.ellipse([(ic_x - 17, ic_y - 17), (ic_x + 17, ic_y + 17)], fill=(*gcol, 40), outline=(*gcol, 240), width=2)
            draw.ellipse([(ic_x - 7, ic_y - 7), (ic_x + 7, ic_y + 7)], fill=(*gcol, 255))

            draw_contained_arabic_text(draw, (gx1 + 8, gy1 + int(card_h * 0.44), gx2 - 8, gy1 + int(card_h * 0.72)), sub_items[idx], initial_font_size=16, fill=(*dark_navy, 255))

            pw_bar = int(card_w * 0.76)
            px1_b = (gx1 + gx2) // 2 - pw_bar // 2
            py_b = gy1 + int(card_h * 0.83)
            fill_p = min(1.0, max(0.18, (scene_progress - idx * 0.07) * 1.45))
            draw.rounded_rectangle([(px1_b, py_b - 5), (px1_b + pw_bar, py_b + 5)], radius=5, fill=(226, 232, 240, 255))
            draw.rounded_rectangle([(px1_b, py_b - 5), (px1_b + int(pw_bar * fill_p), py_b + 5)], radius=5, fill=(*gcol, 255))

        _draw_cursor_with_ripple(draw, (st_x2 - 10, st_y2 - 10), target_click_xy, scene_progress, accent_rgb=grid_colors[active_cell])
        return img

    # =========================================================================
    # Archetype 10: typewriter_gear_console (محرك البحث الذكي بالكتابة الآلية والترس الدوار)
    # =========================================================================
    if archetype == "typewriter_gear_console":
        mech_y = st_y1 + int(st_h * 0.12)
        gear_col = primary_c if is_light_bg else secondary_c
        _draw_gear_icon(draw, st_x2 - 28, mech_y, 20, global_t * 2.8, gear_col)
        _draw_gear_icon(draw, st_x2 - 60, mech_y + 14, 13, -global_t * 3.6, primary_c)

        draw_contained_arabic_text(draw, (st_x1 + 10, mech_y - 18, st_x2 - 82, mech_y + 18), f"{kpi_val} • {kpi_lbl}", initial_font_size=18, fill=(*headline_txt_c, 255))

        type_words = [w for w in str(scene_meta.get("typewriter_query") or concept_title).split() if w]
        vis_w_cnt = max(1, int(math.ceil(len(type_words) * min(1.0, scene_progress / 0.58))))
        visible_str = " ".join(type_words[:vis_w_cnt])

        sb_w, sb_h = int(st_w * 0.96), int(st_h * 0.24)
        sb_x1, sb_y1 = cx - sb_w // 2, st_y1 + int(st_h * 0.25)
        draw.rounded_rectangle([(sb_x1, sb_y1 + 5), (sb_x1 + sb_w, sb_y1 + sb_h + 5)], radius=22, fill=(0, 0, 0, 75))
        draw.rounded_rectangle([(sb_x1, sb_y1), (sb_x1 + sb_w, sb_y1 + sb_h)], radius=22, fill=(255, 255, 255, 254), outline=(*primary_c, 255), width=3)

        tw_drawn, _ = draw_contained_arabic_text(draw, (sb_x1 + 24, sb_y1 + 8, sb_x1 + sb_w - 24, sb_y1 + sb_h - 8), visible_str, initial_font_size=22, fill=(*dark_navy, 255))
        if int(global_t * 4.5) % 2 == 0:
            caret_x = max(sb_x1 + 18, cx - tw_drawn // 2 - 10)
            draw.line([(caret_x, sb_y1 + int(sb_h * 0.26)), (caret_x, sb_y1 + int(sb_h * 0.74))], fill=(*primary_c, 255), width=3)

        grid_y0 = sb_y1 + sb_h + 18
        pw_p = (st_w - 14) // 2
        ph_p = int(st_h * 0.19)
        cols = [primary_c, accent_c, (139, 92, 246), (249, 115, 22)]
        for i in range(4):
            sp = _staggered_spring(scene_progress, delay=0.14 + i * 0.08, duration=0.38)
            px = st_x1 + (i % 2) * (pw_p + 14)
            py = int(grid_y0 + (i // 2) * (ph_p + 12) + 22 * (1.0 - sp))
            draw.rounded_rectangle([(px, py), (px + pw_p, py + ph_p)], radius=16, fill=(255, 255, 255, 248), outline=(*cols[i], 235), width=2)
            draw_contained_arabic_text(draw, (px + 10, py + 4, px + pw_p - 10, py + ph_p - 4), sub_items[i], initial_font_size=16, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 11: nle_timeline_matrix (جدول ومخطط التايملاين التفاعلي مع مؤشر القراءة Playhead)
    # =========================================================================
    if archetype == "nle_timeline_matrix":
        cw, ch = int(st_w * 0.96 * s_card), int(st_h * 0.82 * s_card)
        bx1, by1 = cx - cw // 2, st_y1 + int(st_h * 0.04)
        bx2, by2 = bx1 + cw, by1 + ch
        draw.rounded_rectangle([(bx1, by1 + 6), (bx2, by2 + 6)], radius=24, fill=(0, 0, 0, 75))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=24, fill=(255, 255, 255, 252), outline=(*primary_c, 235), width=3)

        hdr_h = 46
        draw.rounded_rectangle([(bx1 + 12, by1 + 12), (bx2 - 12, by1 + 12 + hdr_h)], radius=14, fill=(*dark_navy, 255))
        draw_contained_arabic_text(draw, (bx1 + 20, by1 + 12, bx2 - 20, by1 + 12 + hdr_h), f"{kpi_val} • {kpi_lbl}", initial_font_size=17, fill=(255, 255, 255, 255))

        track_colors = [primary_c, (139, 92, 246), accent_c, (249, 115, 22)]
        rows_top = by1 + 12 + hdr_h + 14
        row_h = (ch - hdr_h - 46) // 4
        tl_x1, tl_x2 = bx1 + 18, bx1 + int(cw * 0.48)

        for ri in range(4):
            ry1 = rows_top + ri * (row_h + 6)
            ry2 = ry1 + row_h
            draw.rounded_rectangle([(bx1 + 12, ry1), (bx2 - 12, ry2)], radius=12, fill=(241, 245, 249, 255))
            # شريط كليب المونتاج الملون يتمدد أفقياً
            clip_prog = min(1.0, max(0.25, (scene_progress - ri * 0.06) * 1.4))
            c_w = int((tl_x2 - tl_x1) * clip_prog)
            t_col = track_colors[ri % len(track_colors)]
            draw.rounded_rectangle([(tl_x1, ry1 + 8), (tl_x1 + c_w, ry2 - 8)], radius=8, fill=(*t_col, 245))
            draw_contained_arabic_text(draw, (tl_x2 + 10, ry1 + 4, bx2 - 18, ry2 - 4), sub_items[ri], initial_font_size=15, fill=(*dark_navy, 255))

        # خط مؤشر التشغيل الأحمر (Moving Playhead) يمسح التايملاين أفقياً
        ph_x = int(tl_x1 + (tl_x2 - tl_x1) * (0.15 + 0.78 * scene_progress))
        draw.line([(ph_x, rows_top - 6), (ph_x, by2 - 14)], fill=(239, 68, 68, 255), width=3)
        draw.polygon([(ph_x - 7, rows_top - 8), (ph_x + 7, rows_top - 8), (ph_x, rows_top + 2)], fill=(239, 68, 68, 255))
        return img

    # =========================================================================
    # Archetype 12: rocket_bars_cta_outro (مشهد الإطلاق الختامي مع أعمدة النمو الصاعدة وزر الإجراء النابض)
    # =========================================================================
    logo_card_sz = int(min(st_w, st_h) * 0.46 * s_card)
    lcx1, lcy1 = cx - logo_card_sz // 2, st_y1 + 4
    lcx2, lcy2 = lcx1 + logo_card_sz, lcy1 + logo_card_sz
    draw.rounded_rectangle([(lcx1, lcy1 + 8), (lcx2, lcy2 + 8)], radius=26, fill=(0, 0, 0, 55))
    draw.rounded_rectangle([(lcx1, lcy1), (lcx2, lcy2)], radius=26, fill=(255, 255, 255, 255), outline=(*primary_c, 225), width=3)

    ic_img = render_cairo_vector_illustration(
        "delivery_express", int(logo_card_sz * 0.70), int(logo_card_sz * 0.70),
        scene_progress, global_t, {"primary": primary_c, "secondary": secondary_c, "accent": accent_c}
    )
    img.alpha_composite(ic_img, (cx - ic_img.width // 2, lcy1 + int(logo_card_sz * 0.06)))
    draw = ImageDraw.Draw(img, "RGBA")
    draw_contained_arabic_text(
        draw, (lcx1 + 10, lcy2 - int(logo_card_sz * 0.28), lcx2 - 10, lcy2 - 6),
        kpi_val, initial_font_size=18, fill=(*dark_navy, 255)
    )

    pulse_btn = int(4 * math.sin(global_t * 6.0))
    btn_w, btn_h = int(st_w * 0.84 * s_card) + pulse_btn, max(50, int(h * 0.056))
    bx1, by1 = cx - btn_w // 2, lcy2 + 16
    bx2, by2 = bx1 + btn_w, by1 + btn_h
    draw.rounded_rectangle([(bx1, by1 + 5), (bx2, by2 + 5)], radius=btn_h // 2, fill=(0, 0, 0, 65))
    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=btn_h // 2, fill=(*primary_c, 255), outline=(255, 255, 255, 235), width=2)

    ir = (btn_h - 12) // 2
    ic_cx, ic_cy = bx1 + 8 + ir, by1 + btn_h // 2
    draw.ellipse([(ic_cx - ir, ic_cy - ir), (ic_cx + ir, ic_cy + ir)], fill=(255, 255, 255, 255))
    draw.polygon([(ic_cx + 5, ic_cy - 5), (ic_cx - 6, ic_cy), (ic_cx - 1, ic_cy + 2), (ic_cx + 2, ic_cy + 6)], fill=(*dark_navy, 255))
    draw_contained_arabic_text(
        draw, (ic_cx + ir + 8, by1, bx2 - 16, by2),
        sub_items[0] if sub_items else "تواصل معنا اليوم",
        initial_font_size=19, fill=(255, 255, 255, 255)
    )

    # أعمدة النمو الصاعدة تدريجياً في الثلث السفلي للمسرح مع السهم الصاعد
    bars_base_y = st_y2 - 4
    bar_w = int(w * 0.085)
    bar_xs = [int(w * 0.56), int(w * 0.69), int(w * 0.82)]
    max_bar_hs = [int(h * 0.065), int(h * 0.105), int(h * 0.150)]
    grow_u = min(1.0, max(0.20, scene_progress * 1.45))

    for bi, (bx_i, max_bh) in enumerate(zip(bar_xs, max_bar_hs)):
        bh_i = int(max_bh * min(1.0, max(0.15, (scene_progress - bi * 0.08) * 1.6)))
        b_col = primary_c if bi == 1 else (dark_navy if is_light_bg else (255, 255, 255))
        draw.rounded_rectangle([(bx_i, bars_base_y - bh_i), (bx_i + bar_w, bars_base_y)], radius=8, fill=(*b_col, 240))

    curve_pts = [
        (int(w * 0.32), bars_base_y - 4),
        (int(w * 0.50), bars_base_y - int(h * 0.045 * grow_u)),
        (int(w * 0.68), bars_base_y - int(h * 0.105 * grow_u)),
        (int(w * 0.86), bars_base_y - int(h * 0.168 * grow_u))
    ]
    arrow_c = dark_navy if is_light_bg else secondary_c
    draw.line(curve_pts, fill=(*arrow_c, 255), width=4)
    ex, ey = curve_pts[-1]
    draw.polygon([(ex, ey - 9), (ex - 11, ey + 4), (ex + 6, ey + 7)], fill=(*arrow_c, 255))
    _draw_cursor_with_ripple(draw, (bx2 - 20, by2 + 30), (cx, by1 + btn_h // 2), scene_progress, accent_rgb=secondary_c)
    return img


_LOGO_WATERMARK_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}


def _resolve_active_theme_and_style(scene_meta: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool, Optional[str], str]:
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
    border_col = (*theme.get("primary", (27, 174, 202)), 210)
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
    out = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(out, "RGBA")
    primary_c = tuple(theme.get("primary", (27, 174, 202)))
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


# ==============================================================================
# 10. تصيير مشهد موشن جرافيك كامل الشاشة بهوية موحدة و 12 رسماً متحركاً
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
    theme_name, theme, is_light, logo_path, logo_pos = _resolve_active_theme_and_style(scene_meta)
    step_num = int(scene_meta.get("step_number") or scene_meta.get("index", 0) + 1)

    style_spec = scene_meta.get("scene_style_spec")
    if not isinstance(style_spec, dict):
        auto_plan = build_dynamic_scene_style_assignment(max(4, step_num + 1), advance_rotation_counter=False)
        style_spec = auto_plan[min(len(auto_plan) - 1, max(0, step_num - 1))]

    brand = get_active_brand_theme() if callable(get_active_brand_theme) else None
    if isinstance(brand, dict) and brand.get("enabled", True) and "theme_palette" in brand:
        b_pal = brand["theme_palette"]
        style_spec = dict(style_spec)
        merged_pal = dict(style_spec.get("palette", {}))
        merged_pal["top_bg"] = b_pal.get("top_bg", merged_pal.get("top_bg"))
        merged_pal["bottom_bg"] = b_pal.get("bottom_bg", merged_pal.get("bottom_bg"))
        merged_pal["primary"] = b_pal.get("primary", merged_pal.get("primary"))
        merged_pal["glow"] = b_pal.get("glow", merged_pal.get("glow"))
        merged_pal["sticker_bg"] = b_pal.get("secondary", merged_pal.get("sticker_bg"))
        style_spec["palette"] = merged_pal

    pal = style_spec.get("palette", {})
    is_light_stage = bool(pal.get("is_light_bg", is_light))

    # 1. رندرة الخلفية الموحدة والمتحركة بنعومة (Parallax Grid + Breathing Glow)
    img = _render_pro_stage_background(width, height, style_spec, step_num=step_num, global_t=global_t)

    # 2. رسم اللوقو المرفوع إن وجد
    img, _ = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=is_light_stage)

    # 3. رسم المسرح التفاعلي المتحرك (12 Dynamic Kinetic Archetypes)
    img = _render_dynamic_archetype_stage(img, scene_meta, style_spec, scene_progress, global_t)

    # 4. كابشن الكاريوكي السفلي بنظام الصفحات الثابتة غير المتكررة
    caption_theme = {
        "primary": tuple(pal.get("primary", (27, 174, 202))),
        "secondary": tuple(pal.get("sticker_bg", (250, 204, 21)))
    }
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.858),
        theme=caption_theme,
        active_word_idx=active_word_idx
    )

    # 5. شريط التقدم الزمني السفلي الأنيق
    draw = ImageDraw.Draw(img, "RGBA")
    prog_w = int(width * 0.84 * min(1.0, max(0.02, global_t / max(0.1, total_duration))))
    bar_x1 = (width - int(width * 0.84)) // 2
    bar_y = int(height * 0.945)
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + int(width * 0.84), bar_y + 5)], radius=3, fill=(148, 163, 184, 75))
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + prog_w, bar_y + 5)], radius=3, fill=(*caption_theme["primary"], 245))

    return img


# ==============================================================================
# 11. محرك الانتقال السينمائي السلس بين المشاهد (Smooth Camera Zoom & Slide Handoff)
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
    w, h = curr_img.size
    p = _camera_curve(max(0.0, min(1.0, float(trans_progress))))

    prev_scale = 1.0 + 0.06 * p
    pw, ph = int(round(w * prev_scale)), int(round(h * prev_scale))
    prev_zoomed = prev_img.convert("RGBA").resize((pw, ph), Image.Resampling.BILINEAR)
    px1, py1 = (pw - w) // 2, (ph - h) // 2
    prev_crop = prev_zoomed.crop((px1, py1, px1 + w, py1 + h))

    curr_scale = 0.94 + 0.06 * p
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
    """
    كابشن كاريوكي بنظام الصفحات الثابتة غير المتداخلة (`Non-Overlapping 4-Word Pages`):
    يمنع تماماً تكرار آخر كلمات الصفحة السابقة في بداية الصفحة التالية!
    """
    w, h = img.size
    cx = w // 2
    clean_sc_words = [re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(wd)).strip() for wd in sc_words if str(wd).strip()]
    clean_act_word = re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(act_word)).strip() if act_word else (clean_sc_words[0] if clean_sc_words else "")

    if not clean_sc_words and not clean_act_word:
        return

    font_size = max(25, int(min(w, h) * 0.039))
    cap_font = get_arabic_font(font_size, bold=True)
    pop_scale = _spring_physics(min(1.0, w_prog * 2.5), stiffness=240.0, damping=14.0)
    active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)

    if active_word_idx is not None and 0 <= int(active_word_idx) < len(clean_sc_words):
        target_idx = int(active_word_idx)
    else:
        active_word_clean = clean_act_word.lower()
        target_idx = 0
        for wi, cw in enumerate(clean_sc_words):
            if cw.lower() == active_word_clean:
                target_idx = wi
                break

    # تقسيم الكلمات إلى صفحات غير متداخلة (4 كلمات لكل صفحة) لمنع تكرار الكلمات بين السطور
    page_size = 4
    if len(clean_sc_words) <= 5:
        display_words = clean_sc_words
        disp_active_idx = target_idx
    else:
        page_idx = target_idx // page_size
        start_w = page_idx * page_size
        display_words = clean_sc_words[start_w:start_w + page_size]
        disp_active_idx = max(0, min(target_idx - start_w, len(display_words) - 1))

    if not display_words:
        display_words = [clean_act_word]
        disp_active_idx = 0

    draw = ImageDraw.Draw(img, "RGBA")
    word_widths = []
    word_spaces = int(font_size * 0.44)
    for wi, dw in enumerate(display_words):
        f_use = active_font if wi == disp_active_idx else cap_font
        ww, wh = measure_arabic_text(draw, dw, f_use)
        if wi == disp_active_idx:
            ww += 16
        word_widths.append((ww, wh))

    total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces
    if total_line_w > int(w * 0.82):
        scale_down = (w * 0.80) / float(total_line_w)
        font_size = max(19, int(font_size * scale_down))
        cap_font = get_arabic_font(font_size, bold=True)
        active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)
        word_spaces = int(font_size * 0.40)
        word_widths = []
        for wi, dw in enumerate(display_words):
            f_use = active_font if wi == disp_active_idx else cap_font
            ww, wh = measure_arabic_text(draw, dw, f_use)
            if wi == disp_active_idx:
                ww += 14
            word_widths.append((ww, wh))
        total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces

    max_line_h = max(wh for _, wh in word_widths) if word_widths else font_size

    box_pad_x = int(font_size * 0.62)
    box_pad_y = int(font_size * 0.34)
    bar_x1 = max(int(w * 0.04), cx - total_line_w // 2 - box_pad_x)
    bar_x2 = min(int(w * 0.96), cx + total_line_w // 2 + box_pad_x)
    bar_y1 = cap_y - max_line_h // 2 - box_pad_y
    bar_y2 = cap_y + max_line_h // 2 + box_pad_y

    p_col = tuple(theme.get("primary", (27, 174, 202)))
    draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(bar_x1, bar_y1, bar_x2, bar_y2),
        radius=16,
        tint_color=(11, 14, 24, 244),
        border_color=p_col,
        blur_radius=12,
        shadow_offset=8,
        shadow_blur=14
    )

    draw = ImageDraw.Draw(img, "RGBA")
    cur_right_x = bar_x2 - box_pad_x
    for wi, dw in enumerate(display_words):
        ww, wh = word_widths[wi]
        is_active = (wi == disp_active_idx)
        word_cx = cur_right_x - ww // 2

        if is_active:
            hl_pad_x, hl_pad_y = 8, 7
            draw.rounded_rectangle(
                [(word_cx - ww // 2 - hl_pad_x, cap_y - wh // 2 - hl_pad_y),
                 (word_cx + ww // 2 + hl_pad_x, cap_y + wh // 2 + hl_pad_y)],
                radius=10,
                fill=(*p_col, 255)
            )
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=active_font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(11, 24, 31, 160)
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
# 12. تصيير إطار الفيديو الشامل بدون تقليص الفيديو الأصلي (100% Full-Screen Video)
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
        handoff_dur = float(sc.get("handoff_duration_sec", 0.36))
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

    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    img, logo_bbox = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=False)
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2
    step_num = int(sc.get("step_number") or (active_idx + 1))

    if layout_mode in ("floating_callout", "split_screen_stage"):
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.34), stiffness=210.0, damping=14.5)
        y_slide_offset = int(-70 * (1.0 - spring_in))

        concept_title = str(sc.get("concept_title") or sc.get("short_title") or "ميزة أساسية")
        kpi_val = str(sc.get("kpi_value") or "تركيز")
        sub_items = [str(s).strip() for s in (sc.get("sub_items") or []) if str(s).strip()]
        sub_line = re.sub(r"^\d+[\.\-\s]+", "", sub_items[0]) if sub_items else str(sc.get("kpi_label", ""))

        card_w = int(w * 0.86)
        card_h = max(86, int(h * 0.118))
        top_y = (int(h * 0.095) if logo_bbox is not None else int(h * 0.052)) + y_slide_offset
        bx1, by1 = cx - card_w // 2, top_y
        bx2, by2 = cx + card_w // 2, top_y + card_h

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=22,
            tint_color=(11, 24, 31, 228),
            border_color=theme["primary"],
            secondary_color=theme["secondary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=18,
            light_sweep_prog=(sc_prog * 1.4 - 0.1)
        )

        draw = ImageDraw.Draw(img, "RGBA")
        badge_r = max(22, int(card_h * 0.32))
        b_cx = bx2 - badge_r - 16
        b_cy = by1 + card_h // 2
        draw.ellipse([(b_cx - badge_r, b_cy - badge_r), (b_cx + badge_r, b_cy + badge_r)], fill=(*theme["primary"], 255), outline=(255, 255, 255, 240), width=2)
        nf = get_arabic_font(max(16, int(badge_r * 0.78)), bold=True)
        draw_arabic_text(draw, (b_cx, b_cy), f"{step_num:02d}", font=nf, fill=(255, 255, 255, 255))

        text_right = b_cx - badge_r - 12
        text_left = bx1 + 14

        draw_contained_arabic_text(
            draw, (text_left, by1 + 8, text_right, by1 + int(card_h * 0.54)),
            concept_title, initial_font_size=max(18, int(min(w, h) * 0.032)),
            fill=(255, 255, 255, 255), pad_left=10, pad_right=10, min_font_size=12,
            stroke_width=2, stroke_fill=(0, 0, 0, 220)
        )
        sub_display = f"{kpi_val} • {sub_line}" if (sub_line and sub_line not in kpi_val) else kpi_val
        draw_contained_arabic_text(
            draw, (text_left, by1 + int(card_h * 0.54), text_right, by2 - 8),
            sub_display, initial_font_size=max(15, int(min(w, h) * 0.026)),
            fill=(*theme["primary"], 255), pad_left=10, pad_right=10, min_font_size=11
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
            tint_color=(11, 24, 31, 224),
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
            tint_color=(11, 24, 31, 232),
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
            fill=(255, 255, 255, 255), pad_left=18, pad_right=18, min_font_size=11,
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
        sc["visual_quality_score"] = critic_rep.get("overall_score", 0.95)
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
        update_progress(0.10, "1/4: تنظيف الصوت وضبط الصمت الطبيعي (3% - 4%) بدون استهلاك ذاكرة...")
        _, total_dur = extract_jumpcut_audio_and_intervals(
            input_path=input_path,
            clean_audio_output_path=clean_media,
            silence_threshold=-42.0,
            padding_ms=75
        )
        vw, vh = get_safe_working_resolution(video_resolution[0], video_resolution[1], max_dim=960)

        update_progress(0.30, "2/4: تفريغ الكلام وحذف الجمل/الكلمات المعادة بالخطأ وبناء الرسومات التفاعلية...")
        words = transcribe_audio(
            audio_path=clean_media,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        # إذا اكتشف المحرك أن المتحدث أعاد جملة أو كلمة مرتين بالخطأ، نقص المحاولة الخاطئة من الصوت ونعيد مزامنة التوقيت!
        retake_cuts = get_last_detected_retake_cuts()
        if retake_cuts:
            clean_media, total_dur = prune_retake_cuts_from_media(clean_media, retake_cuts, total_dur)
            words = remap_words_after_retake_cuts(words, retake_cuts)

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

        update_progress(0.55, "3/4: تصيير مشاهد الموشن جرافيك الاحترافية بـ 12 نمطاً تفاعلياً...")

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
            handoff_dur = float(sc.get("handoff_duration_sec", 0.36))
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
                curr_img = render_one_take_camera_handoff(
                    prev_img=prev_img,
                    curr_img=curr_img,
                    trans_progress=time_into / handoff_dur,
                    transition_type="smooth_dissolve",
                    prev_meta=prev_sc,
                    curr_meta=sc,
                    stage_bbox=(int(vw * 0.04), int(vh * 0.112), int(vw * 0.96), int(vh * 0.725))
                )

            return np.array(curr_img.convert("RGB"), dtype=np.uint8)

        fps = 30
        total_frames = max(1, int(round(total_dur * fps)))
        update_progress(0.65, "4/4: الرندرة النهائية السلسة (30fps Zero-RAM FFmpeg Pipe)...")

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

        update_progress(1.0, "اكتمل تصيير الموشن جرافيك الاحترافي بنجاح!")
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