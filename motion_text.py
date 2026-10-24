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
        search_and_fetch_web_vectors,
        render_recolored_svg_motion_canvas,
    render_lottie_or_svg_badge,
    draw_animated_stroke_dash_rect,
    render_floating_particles_layer,
    render_radial_ambient_glow,
    render_contextual_hero_illustration
)
from style_evolution_brain import (
        detect_strict_speech_intent,
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
    """
    خلفية أستوديو سينمائية ناعمة ومريحة للعين تماماً (بدون أي شبكة مربعات أو خطوط مزعجة!):
    تدرج شعاعي وقطري ناعم مع إضاءة محيطية دافئة على طريقة الفيديو الاحترافي 15s (6944.mp4).
    """
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    top_c = np.array(theme["top_bg"], dtype=np.float32)
    bot_c = np.array(theme["bottom_bg"], dtype=np.float32)
    glow_c = np.array(theme["glow"], dtype=np.float32)

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    x_idx = np.linspace(0, 1, width, dtype=np.float32)[None, :, None]
    diag = np.clip(0.65 * y_idx + 0.35 * x_idx, 0.0, 1.0)
    canvas_np = top_c * (1.0 - diag) + bot_c * diag

    yy, xx = np.ogrid[:height, :width]
    cx1, cy1 = width * 0.48, height * 0.38
    dist1 = ((xx - cx1) / (width * 0.62)) ** 2 + ((yy - cy1) / (height * 0.46)) ** 2
    mask1 = np.exp(-dist1 * 1.8)[:, :, None] * 0.18

    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255).astype(np.uint8)
    return canvas_np


def _render_pro_stage_background(
    width: int,
    height: int,
    style_spec: Dict[str, Any],
    step_num: int,
    global_t: float,
    force_dark_cinema: bool = False
) -> Image.Image:
    """
    يبني خلفية المسرح السينمائية الموحدة والناعمة (Smooth Radial Studio Stage - ZERO Grid Squares):
    - تم إلغاء الشبكة المربعات (Grid) والمعينات المشتتة للعين نهائياً بناءً على طلب المستخدم.
    - بدلاً منها: تدرج قطري/شعاعي ناعم جداً (كريمي دافئ فاخر أو مخملي سينمائي داكن) مع هالة ضوئية تتنفس بهدوء.
    """
    pal = style_spec.get("palette", {})
    if force_dark_cinema:
        top_c = np.array((18, 16, 14), dtype=np.float32)
        bot_c = np.array((42, 33, 24), dtype=np.float32)
        glow_c = np.array((234, 179, 8), dtype=np.float32)
        is_light = False
    else:
        top_c = np.array(pal.get("top_bg", (253, 250, 241)), dtype=np.float32)
        bot_c = np.array(pal.get("bottom_bg", (244, 231, 198)), dtype=np.float32)
        glow_c = np.array(pal.get("glow", (234, 179, 8)), dtype=np.float32)
        is_light = bool(pal.get("is_light_bg", True))

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    x_idx = np.linspace(0, 1, width, dtype=np.float32)[None, :, None]
    diag_blend = np.clip(0.68 * y_idx + 0.32 * x_idx, 0.0, 1.0)
    canvas_np = top_c * (1.0 - diag_blend) + bot_c * diag_blend

    yy, xx = np.ogrid[:height, :width]
    cx1 = width * (0.50 + 0.05 * math.sin(global_t * 0.65))
    cy1 = height * (0.42 + 0.04 * math.cos(global_t * 0.55))
    dist1 = ((xx - cx1) / (width * 0.64)) ** 2 + ((yy - cy1) / (height * 0.45)) ** 2
    glow_strength = 0.14 if is_light else 0.22
    mask1 = np.exp(-dist1 * 1.75)[:, :, None] * glow_strength
    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255).astype(np.uint8)

    # إضاءة ركنية ثانوية ناعمة (Soft Corner Vignette / Warm Rim Light)
    cx2 = width * 0.85
    cy2 = height * 0.82
    dist2 = ((xx - cx2) / (width * 0.55)) ** 2 + ((yy - cy2) / (height * 0.42)) ** 2
    mask2 = np.exp(-dist2 * 2.1)[:, :, None] * (0.10 if is_light else 0.15)
    canvas_np = np.clip(canvas_np * (1.0 - mask2) + bot_c * mask2, 0, 255).astype(np.uint8)

    return Image.fromarray(canvas_np, mode="RGB").convert("RGBA")


def _draw_soft_elevated_card(
    canvas_rgba: Image.Image,
    bbox: Tuple[int, int, int, int],
    radius: int = 24,
    fill_rgba: Tuple[int, int, int, int] = (255, 255, 255, 253),
    shadow_offset_y: int = 12,
    shadow_blur: int = 14,
    shadow_alpha: int = 44,
    border_rgba: Optional[Tuple[int, int, int, int]] = (255, 255, 255, 240)
) -> Image.Image:
    """
    يرسم بطاقة ثلاثية الأبعاد بظل ناعم مريح للعين (Soft 3D Drop Shadow - مثل بطاقات الفيديو 15s 6944.mp4)
    بدون أي حدود سوداء كرتونية قاسية!
    """
    w, h = canvas_rgba.size
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    if x2 - x1 < 8 or y2 - y1 < 8:
        return canvas_rgba

    pad = shadow_blur * 2 + abs(shadow_offset_y) + 8
    sx1, sy1 = max(0, x1 - pad), max(0, y1 - pad)
    sx2, sy2 = min(w, x2 + pad), min(h, y2 + pad)
    sw, sh = sx2 - sx1, sy2 - sy1

    if sw > 6 and sh > 6 and shadow_alpha > 0:
        sh_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(sh_layer, "RGBA")
        bx1, by1 = x1 - sx1 + 2, y1 - sy1 + shadow_offset_y
        bx2, by2 = x2 - sx1 - 2, y2 - sy1 + shadow_offset_y
        s_draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=(24, 20, 16, shadow_alpha))
        sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(radius=max(2, shadow_blur)))
        canvas_rgba.alpha_composite(sh_layer, (sx1, sy1))

    c_draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    c_draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=radius, fill=fill_rgba)
    if border_rgba is not None:
        c_draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=radius, outline=border_rgba, width=1)
    return canvas_rgba


def _draw_macos_blue_folder_icon(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int = 28,
    h: int = 22,
    base_rgb: Tuple[int, int, int] = (56, 189, 248),
    tab_rgb: Tuple[int, int, int] = (2, 132, 199)
):
    """يرسم أيقونة مجلد ثلاثية الأبعاد زرقاء أنيقة مطابقة لأيقونات المجلدات في الفيديو المرجعي 6944.mp4."""
    tab_w = max(10, int(w * 0.44))
    tab_h = max(4, int(h * 0.22))
    draw.rounded_rectangle([(x, y), (x + tab_w, y + tab_h + 4)], radius=3, fill=(*tab_rgb, 255))
    draw.rounded_rectangle([(x, y + tab_h), (x + w, y + h)], radius=4, fill=(*base_rgb, 255))
    draw.line([(x + 2, y + tab_h + 2), (x + w - 2, y + tab_h + 2)], fill=(255, 255, 255, 135), width=1)


# ==============================================================================
# 8. محرك العناوين الحركية المتتابعة المتزامنة مع النطق (Audio-Synced Kinetic Headline)
# ==============================================================================
def _draw_sticker_highlighted_headline(
    draw: ImageDraw.ImageDraw,
    bbox: Tuple[int, int, int, int],
    headline_text: str,
    highlight_word: str = "",
    headline_txt_color: Tuple[int, int, int] = (24, 24, 27),
    sticker_bg_color: Tuple[int, int, int] = (234, 179, 8),
    sticker_txt_color: Tuple[int, int, int] = (24, 24, 27),
    initial_font_size: int = 32,
    scene_progress: float = 1.0,
    global_t: float = 0.0,
    style_mode_hint: str = "gold_accent_clean"
):
    """
    يرسم العنوان الاحترافي بتحريك متتابع كلمة بكلمة مع الصوت (`Audio-Synced Word Reveal`):
    - يحجز عرض الكبسولة الكامل (`ww_text + 2 * pad_x + 12`) قبل حساب المواقع لضمان عدم تداخل
      الكبسولة الملونة أو البيضاء مع حروف الكلمات المجاورة نهائياً.
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
        for i, w in enumerate(words[:min(5, len(words))]):
            wc = re.sub(r"[،,.!؟?:•]", "", w)
            if len(wc) > best_len and wc not in ("في", "من", "على", "مع", "أو", "كل", "هذا", "هذه", "إلى", "ما", "ولا"):
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
    avail_h = max(48, y2 - y1)
    line_step_h = min(int(initial_font_size * 1.48), avail_h // max(1, line_count))
    start_cy = (y1 + y2) // 2 - ((line_count - 1) * line_step_h) // 2

    total_w_count = max(1, len(words))
    for l_idx, (l_words, hl_pos, word_offset_idx) in enumerate(lines):
        line_str = " ".join(l_words)
        f_obj, _, _ = get_fitted_arabic_font(
            draw, line_str, max_width=int(max_w * 0.84),
            initial_font_size=initial_font_size, min_font_size=16, bold=True
        )
        f_sz = getattr(f_obj, "size", 24)
        space_w = max(11, int(f_sz * 0.40))
        pad_x = max(11, int(f_sz * 0.34))

        measured = []
        for wi, w_str in enumerate(l_words):
            ww_txt, wh_txt = measure_arabic_text(draw, w_str, f_obj)
            is_hl = (wi == hl_pos)
            ww_slot = (ww_txt + 2 * pad_x + 10) if (is_hl and style_mode_hint != "gold_accent_clean") else ww_txt
            measured.append((w_str, ww_txt, ww_slot, wh_txt, is_hl, word_offset_idx + wi))

        total_lw = sum(m[2] for m in measured) + max(0, len(measured) - 1) * space_w
        if total_lw > max_w:
            scale_f = max_w / float(max(1, total_lw))
            new_sz = max(15, int(f_sz * scale_f * 0.95))
            f_obj = get_arabic_font(new_sz, bold=True)
            f_sz = new_sz
            space_w = max(9, int(new_sz * 0.36))
            pad_x = max(9, int(new_sz * 0.30))
            measured = []
            for wi, w_str in enumerate(l_words):
                ww_txt, wh_txt = measure_arabic_text(draw, w_str, f_obj)
                is_hl = (wi == hl_pos)
                ww_slot = (ww_txt + 2 * pad_x + 8) if (is_hl and style_mode_hint != "gold_accent_clean") else ww_txt
                measured.append((w_str, ww_txt, ww_slot, wh_txt, is_hl, word_offset_idx + wi))
            total_lw = sum(m[2] for m in measured) + max(0, len(measured) - 1) * space_w

        cur_right = cx + total_lw // 2
        base_line_cy = start_cy + l_idx * line_step_h

        for w_str, ww_txt, ww_slot, wh_txt, is_hl, global_wi in measured:
            word_delay = (global_wi / float(total_w_count)) * 0.30
            w_spring = _staggered_spring(scene_progress, delay=word_delay, duration=0.34, stiffness=190.0, damping=14.0)
            alpha_w = int(255 * min(1.0, max(0.0, (scene_progress - word_delay * 0.85) * 4.2)))
            if alpha_w <= 8:
                cur_right -= (ww_slot + space_w)
                continue

            dy_word = int(18.0 * (1.0 - w_spring))
            line_cy = base_line_cy + dy_word
            w_cx = cur_right - ww_slot // 2

            if is_hl:
                if style_mode_hint == "gold_accent_clean":
                    gold_col = sticker_bg_color if sum(sticker_bg_color) < 700 else (217, 155, 28)
                    draw_arabic_text(draw, (w_cx, line_cy), w_str, font=f_obj, fill=(*gold_col, alpha_w))
                else:
                    sticker_sweep = min(1.0, max(0.90, _staggered_spring(scene_progress, delay=word_delay + 0.02, duration=0.32)))
                    pad_y = max(6, int(wh_txt * 0.24))
                    half_w = int((ww_txt * 0.50 + pad_x) * sticker_sweep)
                    rx1 = int(w_cx - half_w)
                    rx2 = int(w_cx + half_w)
                    ry1 = int(line_cy - wh_txt // 2 - pad_y)
                    ry2 = int(line_cy + wh_txt // 2 + pad_y)
                    draw.rounded_rectangle([(rx1, ry1 + 4), (rx2, ry2 + 4)], radius=13, fill=(0, 0, 0, int(52 * (alpha_w / 255.0))))
                    draw.rounded_rectangle([(rx1, ry1), (rx2, ry2)], radius=13, fill=(*sticker_bg_color, alpha_w), outline=(255, 255, 255, int(115 * (alpha_w / 255.0))), width=1)
                    bg_luma = 0.299 * sticker_bg_color[0] + 0.587 * sticker_bg_color[1] + 0.114 * sticker_bg_color[2]
                    safe_txt_col = (255, 255, 255) if bg_luma < 168 else (15, 23, 42)
                    draw_arabic_text(
                        draw, (w_cx, line_cy), w_str, font=f_obj,
                        fill=(*safe_txt_col, alpha_w)
                    )
            else:
                draw_arabic_text(
                    draw, (w_cx, line_cy), w_str, font=f_obj,
                    fill=(*headline_txt_color, alpha_w)
                )
            cur_right -= (ww_slot + space_w)


# ==============================================================================
# 9. محرك الـ 12 مشهداً حركياً المتعلمة من الفيديو المرجعي 15s (6944.mp4)
#    مع تزامن صوتي كامل (لا تظهر الأيقونات قبل الكلام ولا تبقى جامدة!)
# ==============================================================================
def _draw_checkmark_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color_rgb: Tuple[int, int, int] = (16, 185, 129), scale: float = 1.0):
    r = max(8, int(radius * scale))
    if r <= 2:
        return
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(*color_rgb, 255), outline=(255, 255, 255, 240), width=2)
    draw.line([(cx - int(r * 0.42), cy + int(r * 0.05)), (cx - int(r * 0.10), cy + int(r * 0.38)), (cx + int(r * 0.46), cy - int(r * 0.32))], fill=(255, 255, 255, 255), width=max(2, int(r * 0.22)))


def _draw_cursor_with_ripple(
    draw: ImageDraw.ImageDraw,
    start_xy: Tuple[int, int],
    target_xy: Tuple[int, int],
    prog: float,
    accent_rgb: Tuple[int, int, int] = (217, 155, 28)
):
    """
    يرسم مؤشر اليد التفاعلي الأنيق (Pointing Hand Cursor 👆 مثل الفيديو المرجعي 6944.mp4)
    الذي يدخل بعد اكتمال ظهور العنصر وينقر عليه مع دوائر تموج ضوئية.
    """
    if prog < 0.32:
        return
    move_p = _ease_out_cubic(max(0.0, min(1.0, (prog - 0.32) / 0.36)))
    # مسار منحني طبيعي لحركة اليد
    arc_lift = -28.0 * math.sin(move_p * math.pi)
    cx = int(start_xy[0] + (target_xy[0] - start_xy[0]) * move_p)
    cy = int(start_xy[1] + (target_xy[1] - start_xy[1]) * move_p + arc_lift)

    click_scale = 1.0
    if prog > 0.66:
        ripple_p = ((prog - 0.66) * 2.6) % 1.0
        click_scale = 1.0 - 0.14 * math.sin(min(1.0, ripple_p * 2.0) * math.pi)
        for ri in range(2):
            rp = max(0.0, min(1.0, ripple_p - ri * 0.22))
            if rp > 0.0:
                rr = int(8 + 32 * rp)
                ra = int(175 * (1.0 - rp))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*accent_rgb, ra), width=2)

    s = max(13, int(17 * click_scale))
    # رسم كف اليد والإصبع السبابة (Pointing Hand Silhouette with Shadow)
    palm_box = [(cx - int(s * 0.42), cy + int(s * 0.38)), (cx + int(s * 0.68), cy + int(s * 1.45))]
    finger_box = [(cx - int(s * 0.20), cy - int(s * 0.10)), (cx + int(s * 0.22), cy + int(s * 0.75))]
    thumb_box = [(cx - int(s * 0.72), cy + int(s * 0.55)), (cx - int(s * 0.15), cy + int(s * 1.05))]

    # الظل الناعم لليد
    draw.rounded_rectangle([(palm_box[0][0] + 2, palm_box[0][1] + 4), (palm_box[1][0] + 2, palm_box[1][1] + 4)], radius=6, fill=(0, 0, 0, 75))
    draw.rounded_rectangle([(finger_box[0][0] + 2, finger_box[0][1] + 4), (finger_box[1][0] + 2, finger_box[1][1] + 4)], radius=5, fill=(0, 0, 0, 75))

    # اليد البيضاء بحافة ناعمة
    draw.rounded_rectangle(thumb_box, radius=4, fill=(255, 255, 255, 255), outline=(30, 41, 59, 230), width=2)
    draw.rounded_rectangle(palm_box, radius=6, fill=(255, 255, 255, 255), outline=(30, 41, 59, 230), width=2)
    draw.rounded_rectangle(finger_box, radius=5, fill=(255, 255, 255, 255), outline=(30, 41, 59, 230), width=2)


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
    في ستايل الـ 15 ثانية السينمائي (none_clean)، نبقي أعلى الشاشة نظيفاً ومريحاً للعين بدون كبسولات مزدحمة!
    """
    return  # إبقاء أعلى الشاشة نظيفاً وسينمائياً بالكامل بدون كبسولة 01 ••••

    cx = w // 2
    pal = style_spec.get("palette", {})
    primary_c = tuple(pal.get("primary", (217, 155, 28)))
    dark_navy = (24, 24, 27)
    s_in = _staggered_spring(scene_progress, delay=0.0, duration=0.35)
    y_off = int(-24 * (1.0 - s_in))

    pill_w, pill_h = int(w * 0.28), max(30, int(h * 0.034))
    pill_x1, pill_y1 = cx - pill_w // 2, int(h * 0.042) + y_off
    pill_x2, pill_y2 = pill_x1 + pill_w, pill_y1 + pill_h
    draw.rounded_rectangle([(pill_x1, pill_y1 + 3), (pill_x2, pill_y2 + 3)], radius=pill_h // 2, fill=(0, 0, 0, 28))
    draw.rounded_rectangle([(pill_x1, pill_y1), (pill_x2, pill_y2)], radius=pill_h // 2, fill=(255, 255, 255, 240))

    badge_r = (pill_h - 8) // 2
    b_cx = pill_x1 + 6 + badge_r
    b_cy = pill_y1 + pill_h // 2
    draw.ellipse([(b_cx - badge_r, b_cy - badge_r), (b_cx + badge_r, b_cy + badge_r)], fill=(*dark_navy, 255))
    num_f = get_arabic_font(max(11, int(pill_h * 0.42)), bold=True)
    draw_arabic_text(draw, (b_cx, b_cy), f"{step_num:02d}", font=num_f, fill=(255, 255, 255, 255))

    dots_start_x = b_cx + badge_r + 10
    for di in range(4):
        d_active = (di == ((step_num - 1) % 4))
        dw_dot = 18 if d_active else 7
        draw.rounded_rectangle(
            [(dots_start_x, b_cy - 3), (dots_start_x + dw_dot, b_cy + 3)],
            radius=3,
            fill=(*primary_c, 255) if d_active else (203, 213, 225, 255)
        )
        dots_start_x += dw_dot + 6



_STORYBOARD_PANEL_CACHE: Dict[str, Image.Image] = {}


def render_animated_storyboard_panel_scene(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float,
    choreo_u: float,
    panel_info: Dict[str, Any]
) -> Image.Image:
    """
    يحرك لوحة الستوري بورد المرفوعة من المستخدم بـ 4 أنماط كاميرا 2.5D سينمائية متنوعة:
    1. النمط 0: Ken Burns Deep Push + 2.5D Foreground Subject Pop-Out
    2. النمط 1: 3D Floating Glass Showcase + PyCairo Light Sweep Sheen
    3. النمط 2: Dynamic Pan-Across + Focal Spotlight Pulse
    4. النمط 3: Split Depth Multi-Layer Parallax Card
    """
    w, h = img.size
    cx = w // 2
    step_num = int(scene_meta.get("step_number") or 1)
    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "")
    pal = panel_info.get("palette") or style_spec.get("palette", {})
    is_light_bg = bool(pal.get("is_light_bg", True))
    primary_c = tuple(pal.get("primary", (56, 189, 248)))[:3]
    secondary_c = tuple(pal.get("secondary", (250, 204, 21)))[:3]
    accent_c = tuple(pal.get("accent", (16, 185, 129)))[:3]
    headline_txt_c = (24, 24, 27) if is_light_bg else (248, 250, 252)
    sticker_bg_c = primary_c

    panel_path = str(panel_info.get("panel_path", ""))
    fg_path = str(panel_info.get("fg_path", ""))
    focal_pt = panel_info.get("focal_point", [0.5, 0.5])
    fx_norm, fy_norm = float(focal_pt[0]), float(focal_pt[1])

    if not panel_path or not os.path.exists(panel_path):
        return img

    if panel_path not in _STORYBOARD_PANEL_CACHE:
        if len(_STORYBOARD_PANEL_CACHE) >= 8:
            _STORYBOARD_PANEL_CACHE.clear()
        _STORYBOARD_PANEL_CACHE[panel_path] = Image.open(panel_path).convert("RGBA")
    base_panel_pil = _STORYBOARD_PANEL_CACHE[panel_path]

    fg_panel_pil = None
    if fg_path and os.path.exists(fg_path):
        if fg_path not in _STORYBOARD_PANEL_CACHE:
            _STORYBOARD_PANEL_CACHE[fg_path] = Image.open(fg_path).convert("RGBA")
        fg_panel_pil = _STORYBOARD_PANEL_CACHE[fg_path]

    # 1. خلفية سينمائية غامرة مستخرجة من نفس اللوحة مع تحريك بطيء معكس (Counter-Parallax)
    bg_zoom = int(w * 1.12), int(h * 1.12)
    bg_fill = base_panel_pil.resize(bg_zoom, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=28))
    bg_ox = int((bg_zoom[0] - w) * (0.5 - 0.35 * (choreo_u - 0.5)))
    bg_oy = int((bg_zoom[1] - h) * (0.5 - 0.25 * math.sin(global_t * 1.5)))
    bg_fill = bg_fill.crop((bg_ox, bg_oy, bg_ox + w, bg_oy + h))
    tint_col = (*tuple(pal.get("top_bg", (15, 23, 42)))[:3], 160 if is_light_bg else 182)
    img = Image.alpha_composite(bg_fill, Image.new("RGBA", (w, h), tint_col))
    draw = ImageDraw.Draw(img, "RGBA")

    # 2. العنوان الحركي المتزامن مع الكلمات المنطوقة
    kw_list = scene_meta.get("key_words") or []
    hl_word = kw_list[0] if kw_list else ""
    if concept_title:
        _draw_sticker_highlighted_headline(
            draw=draw,
            bbox=(int(w * 0.06), int(h * 0.075), int(w * 0.94), int(h * 0.205)),
            headline_text=concept_title,
            highlight_word=hl_word,
            headline_txt_color=headline_txt_c,
            sticker_bg_color=sticker_bg_c,
            initial_font_size=max(24, int(h * 0.035)),
            scene_progress=choreo_u,
            global_t=global_t,
            style_mode_hint="sticker_pill"
        )

    # 3. مسرح لوحة الستوري بورد بـ 4 أنماط كاميرا متنوعة بين المشاهد
    st_x1, st_y1 = int(w * 0.055), int(h * 0.22)
    st_x2, st_y2 = int(w * 0.945), int(h * 0.80)
    st_w, st_h = st_x2 - st_x1, st_y2 - st_y1

    cam_mode = (step_num - 1) % 4
    sp_in = _staggered_spring(choreo_u, delay=0.01, duration=0.38, stiffness=200.0, damping=14.0)
    float_y = int(6.0 * math.sin(global_t * 2.5 + step_num))
    float_x = int(4.0 * math.cos(global_t * 1.9 + step_num))

    pw0, ph0 = base_panel_pil.size
    p_aspect = pw0 / float(max(1, ph0))
    target_w = int(st_w * max(0.86, min(1.0, sp_in)))
    target_h = int(target_w / max(0.48, min(1.80, p_aspect)))
    if target_h > st_h:
        target_h = int(st_h * max(0.86, min(1.0, sp_in)))
        target_w = int(target_h * p_aspect)
    target_w = max(160, min(st_w, target_w))
    target_h = max(160, min(st_h, target_h))

    card_x1 = cx - target_w // 2 + float_x
    card_y1 = (st_y1 + st_y2) // 2 - target_h // 2 + float_y + int(24 * (1.0 - min(1.0, sp_in)))
    card_x2, card_y2 = card_x1 + target_w, card_y1 + target_h

    # إطار زجاجي ثلاثي الأبعاد ناعم خلف اللوحة
    img = _draw_soft_elevated_card(
        img, (card_x1 - 6, card_y1 - 6, card_x2 + 6, card_y2 + 6),
        radius=26, fill_rgba=(255, 255, 255, 245) if is_light_bg else (15, 23, 42, 245),
        shadow_offset_y=18, shadow_blur=22, shadow_alpha=78,
        border_rgba=(*primary_c, 235)
    )

    # حساب حركة الكاميرا داخل اللوحة حسب النمط (Push-In / Pull-Out / Pan-Sweep / Dynamic Focus)
    u_smooth = _ease_out_cubic(min(1.0, choreo_u * 1.12))
    if cam_mode == 0:
        cam_zoom = 1.02 + 0.16 * u_smooth
        pan_x = (fx_norm - 0.5) * 0.52 * u_smooth
        pan_y = (fy_norm - 0.5) * 0.52 * u_smooth
    elif cam_mode == 1:
        cam_zoom = 1.18 - 0.14 * u_smooth
        pan_x = (fx_norm - 0.5) * 0.40 * (1.0 - u_smooth)
        pan_y = (fy_norm - 0.5) * 0.40 * (1.0 - u_smooth)
    elif cam_mode == 2:
        cam_zoom = 1.12 + 0.06 * math.sin(u_smooth * math.pi)
        pan_x = -0.18 + 0.36 * u_smooth
        pan_y = (fy_norm - 0.5) * 0.35 * u_smooth
    else:
        cam_zoom = 1.05 + 0.14 * u_smooth
        pan_x = 0.16 - 0.32 * u_smooth
        pan_y = (fy_norm - 0.5) * 0.45 * u_smooth

    zw, zh = int(round(target_w * cam_zoom)), int(round(target_h * cam_zoom))
    panel_resized = base_panel_pil.resize((zw, zh), Image.Resampling.BICUBIC)
    crop_cx = int(zw * (0.5 + pan_x))
    crop_cy = int(zh * (0.5 + pan_y))
    cx0 = max(0, min(zw - target_w, crop_cx - target_w // 2))
    cy0 = max(0, min(zh - target_h, crop_cy - target_h // 2))
    panel_cropped = panel_resized.crop((cx0, cy0, cx0 + target_w, cy0 + target_h))

    # 4. تحريك الطبقة الأمامية المفرغة (2.5D Foreground Subject Pop-Out) ببروز ثلاثي الأبعاد
    if fg_panel_pil is not None and choreo_u >= 0.08:
        fg_sp = _staggered_spring(choreo_u, delay=0.08, duration=0.40, stiffness=210.0, damping=13.0)
        fg_zoom = cam_zoom * (1.0 + 0.085 * min(1.15, fg_sp))
        fzw, fzh = int(round(target_w * fg_zoom)), int(round(target_h * fg_zoom))
        fg_resized = fg_panel_pil.resize((fzw, fzh), Image.Resampling.BICUBIC)
        fcx0 = max(0, min(fzw - target_w, int(fzw * (0.5 + pan_x * 1.15)) - target_w // 2))
        fcy0 = max(0, min(fzh - target_h, int(fzh * (0.5 + pan_y * 1.15)) - target_h // 2))
        fg_cropped = fg_resized.crop((fcx0, fcy0, fcx0 + target_w, fcy0 + target_h))
        panel_cropped = Image.alpha_composite(panel_cropped, fg_cropped)

    # 5. لمعان سينمائي متحرك (Diagonal Glass Light Sweep) فوق اللوحة
    sweep_layer = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    sw_draw = ImageDraw.Draw(sweep_layer, "RGBA")
    sweep_x = int(-target_w * 0.4 + (target_w * 1.8) * min(1.0, max(0.0, (choreo_u - 0.10) / 0.65)))
    sw_poly = [
        (sweep_x, 0),
        (sweep_x + int(target_w * 0.22), 0),
        (sweep_x - int(target_w * 0.08), target_h),
        (sweep_x - int(target_w * 0.30), target_h),
    ]
    sw_draw.polygon(sw_poly, fill=(255, 255, 255, 36))
    panel_cropped = Image.alpha_composite(panel_cropped, sweep_layer)

    mask_round = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask_round).rounded_rectangle([(0, 0), (target_w - 1, target_h - 1)], radius=22, fill=255)
    img.paste(panel_cropped, (card_x1, card_y1), mask_round)
    draw = ImageDraw.Draw(img, "RGBA")

    # 6. تسليط ضوء تفاعلي ناعم حول العنصر المركزي + حركة مؤشر اليد التفاعلي
    focus_screen_x = card_x1 + int(target_w * max(0.2, min(0.8, fx_norm)))
    focus_screen_y = card_y1 + int(target_h * max(0.2, min(0.8, fy_norm)))
    if 0.20 <= choreo_u <= 0.90:
        pulse_r = int(28 + 12 * math.sin(global_t * 5.0))
        ring_alpha = int(165 * math.sin(min(1.0, (choreo_u - 0.20) / 0.70) * math.pi))
        draw.ellipse(
            [(focus_screen_x - pulse_r, focus_screen_y - pulse_r), (focus_screen_x + pulse_r, focus_screen_y + pulse_r)],
            outline=(*secondary_c, max(0, ring_alpha)), width=3
        )

    _draw_cursor_with_ripple(
        draw,
        (card_x2 - 22, card_y2 + 24),
        (focus_screen_x, focus_screen_y),
        choreo_u,
        accent_rgb=primary_c
    )
    return img


def _render_dynamic_archetype_stage(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float,
    active_word_idx: int = 0,
    word_local_progress: float = 0.5,
    scene_words: Optional[List[str]] = None
) -> Image.Image:
    """
    محرك الكوريغرافيا التوليدي المتعلم من الفيديو المرجعي 15s (6944.mp4):
    - تزامن صوتي صارم (Audio-Synced Progressive Reveal):
      لا تظهر الأيقونات أو البطاقات قبل نطق الكلام، ولا تبقى جامدة أبداً!
      بل يبدأ المشهد بدخول الكلمات المنطوقة، ثم تتشكل عناصر الموشن جرافيك تدريجياً كلمة بكلمة،
      ثم تتفاعل اليد المؤشرة (👆) بالنقر والتحريك قبل الانتقال السلس للمشهد التالي.
    """
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img, "RGBA")
    pal = style_spec.get("palette", {})
    is_light_bg = bool(pal.get("is_light_bg", True))

    step_num = int(scene_meta.get("step_number") or style_spec.get("step_number") or 1)
    total_scenes = int(scene_meta.get("total_scenes_count") or 999)
    badge_label = str(scene_meta.get("badge_label") or "محور أساسي")
    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "فكرة محورية ذكية")
    kpi_val = str(scene_meta.get("kpi_value") or "").strip()
    kpi_lbl = str(scene_meta.get("kpi_label") or "").strip()

    raw_sub_items = [re.sub(r"^\d+[\.\-\s]+", "", str(s)).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    sub_items: List[str] = []
    for s_it in raw_sub_items:
        if s_it and s_it not in sub_items:
            sub_items.append(s_it)
    # استخراج عبارات قصيرة متميزة من كلمات الجملة المنطوقة لمنع تكرار نفس العنوان داخل البطاقات
    raw_txt_words = [w.strip() for w in str(scene_meta.get("text") or concept_title or "").split() if len(w.strip()) >= 2]
    for wi in range(0, len(raw_txt_words), 2):
        chunk_phrase = " ".join(raw_txt_words[wi:wi + 2]).strip()
        if len(chunk_phrase) >= 4 and chunk_phrase not in sub_items and chunk_phrase != concept_title:
            sub_items.append(chunk_phrase)
    for fallback_s in [kpi_lbl, concept_title, kpi_val]:
        fb_clean = str(fallback_s or "").strip()
        if fb_clean and fb_clean not in sub_items:
            sub_items.append(fb_clean)
    studio_default_tags = ["AI STUDIO", "4K 60FPS", "AUTO CUT", "PRO SFX", "3D MOTION", "SMART EDIT"]
    for st_tag in studio_default_tags:
        if len(sub_items) >= 6:
            break
        if st_tag not in sub_items:
            sub_items.append(st_tag)

    # حساب التقدم المتزامن مع الكلمات المنطوقة فعلياً (Audio-Synced Progression)
    sc_w_list = scene_words if scene_words else (scene_meta.get("word_strings") or concept_title.split())
    n_words = max(1, len(sc_w_list))
    word_sync_u = min(1.0, max(0.0, (float(active_word_idx) + float(word_local_progress)) / float(n_words)))
    choreo_u = min(1.0, max(0.0, 0.48 * float(scene_progress) + 0.52 * word_sync_u))

    # فحص وضع الستوري بورد المرفوع من المستخدم (Single-Image Storyboard Mode):
    # إذا رفع المستخدم صورة ستوري بورد، يحرك النظام لوحات الستوري بورد مباشرةً بعمق 2.5D دون اختراع أشكال عشوائية!
    try:
        from style_evolution_brain import get_active_storyboard_state
        sb_state = get_active_storyboard_state()
        if sb_state.get("enabled") and sb_state.get("panels"):
            sb_panels = sb_state["panels"]
            p_idx = min(len(sb_panels) - 1, int((max(1, step_num) - 1) * len(sb_panels) / max(1, min(total_scenes, 24))))
            return render_animated_storyboard_panel_scene(
                img=img,
                scene_meta=scene_meta,
                style_spec=style_spec,
                scene_progress=scene_progress,
                global_t=global_t,
                choreo_u=choreo_u,
                panel_info=sb_panels[p_idx]
            )
    except Exception:
        pass

    primary_c = tuple(pal.get("primary", (217, 155, 28)))
    secondary_c = tuple(pal.get("secondary", (37, 99, 235)))
    accent_c = tuple(pal.get("accent", (16, 185, 129)))
    headline_txt_c = tuple(pal.get("headline_txt", (24, 24, 27) if is_light_bg else (255, 255, 255)))
    sticker_bg_c = tuple(pal.get("sticker_bg", (234, 179, 8)))
    sticker_txt_c = tuple(pal.get("sticker_txt", (24, 24, 27)))
    dark_navy = (24, 24, 27)

    user_override_arch = str(scene_meta.get("user_override_archetype") or "").strip()
    raw_arch = str(user_override_arch or scene_meta.get("archetype") or style_spec.get("visual_archetype") or "").strip()
    legacy_map = {
        "agency_receipt_stamp": "chrono_ring_3d_counter",
        "fan_out_mobile_report": "pack_3d_extruding_pillars",
        "blueprint_numbered_steps": "step_cascade_ribbon_cards",
        "saas_folder_reorder": "macos_folder_counter_list",
        "bento_grid_2x2_ripple": "reels_6card_showcase_grid",
        "saas_grid_2x2_cursor": "reels_6card_showcase_grid",
        "split_before_after_cards": "floating_3d_stat_Compare",
        "stage_before_after_checklist": "dual_metric_gauge_pods",
        "typewriter_gear_console": "hero_platform_workspace",
        "saas_typewriter_mechanism": "hero_platform_workspace",
        "stage_trust_bubbles": "hero_problem_radar_fix",
        "stage_balance_scale": "damped_balance_scale",
        "saas_process_flow": "hero_ai_neural_core",
        "video_schedule_table": "nle_timeline_matrix",
        "interactive_cta_outro": "hero_cta_magnet_finale",
        "rocket_bars_cta_outro": "hero_viral_rocket_chart"
    }
    archetype = legacy_map.get(raw_arch, raw_arch)
    if archetype not in ALL_DYNAMIC_VISUAL_ARCHETYPES:
        archetype = ALL_DYNAMIC_VISUAL_ARCHETYPES[(step_num - 1) % len(ALL_DYNAMIC_VISUAL_ARCHETYPES)]

    # بوابة المنطق الصارم: منع ظهور القوالب المرقمة (1-2-3-4) أو الميزان أو العدادات في مشاهد الكلام العام غير المرقمة!
    if not user_override_arch and callable(detect_strict_speech_intent):
        raw_scene_txt = str(scene_meta.get("text") or concept_title or "")
        intent_info = detect_strict_speech_intent(raw_scene_txt, step_num - 1, total_scenes)
        if archetype in intent_info.get("forbidden_archetypes", set()):
            matched_arch, _ = match_speech_to_visual_archetype(
                scene_text=raw_scene_txt,
                scene_index=step_num - 1,
                total_scenes=total_scenes,
                used_archetypes=[],
                variation_seed=step_num * 17
            )
            archetype = matched_arch if matched_arch not in intent_info.get("forbidden_archetypes", set()) else "web_dynamic_scene"

    if not user_override_arch and step_num == total_scenes and total_scenes >= 3 and archetype not in ("interactive_profile_follow_card", "hero_cta_magnet_finale", "kinetic_quote_dm_finale", "hero_commerce_delivery"):
        archetype = "hero_cta_magnet_finale" if (step_num % 2 == 0) else "kinetic_quote_dm_finale"

    # إذا كان المشهد هو المسرح السينمائي الداكن (Shot 5 من 6944.mp4)، نحول الخلفية إلى الغرفة السينمائية الداكنة الدافئة!
    if archetype == "dark_cinema_fanned_cards":
        img = _render_pro_stage_background(w, h, style_spec, step_num=step_num, global_t=global_t, force_dark_cinema=True)
        draw = ImageDraw.Draw(img, "RGBA")
        headline_txt_c = (255, 255, 255)
        is_light_bg = False

    _render_unified_top_header(draw, w, h, step_num, total_scenes, badge_label, style_spec, choreo_u)

    # للعناصر التي تحتوي عنواناً علوياً، نرسم العنوان بكلمات متتابعة متزامنة مع الصوت
    kw_list = scene_meta.get("key_words") or []
    hl_word = kw_list[0] if kw_list else ""
    headline_style_hint = str(style_spec.get("headline_style", "gold_accent_clean"))
    if archetype not in ("chrono_ring_3d_counter", "kinetic_quote_dm_finale"):
        _draw_sticker_highlighted_headline(
            draw=draw,
            bbox=(int(w * 0.06), int(h * 0.085), int(w * 0.94), int(h * 0.215)),
            headline_text=concept_title,
            highlight_word=hl_word,
            headline_txt_color=headline_txt_c,
            sticker_bg_color=sticker_bg_c,
            sticker_txt_color=sticker_txt_c,
            initial_font_size=max(24, int(h * 0.036)),
            scene_progress=choreo_u,
            global_t=global_t,
            style_mode_hint=headline_style_hint
        )

    stiffness = float(style_spec.get("spring_stiffness", 205.0))
    damping = float(style_spec.get("spring_damping", 14.0))
    float_y = int(float(style_spec.get("camera_float_amp", 5.0)) * math.sin(global_t * 2.4 + step_num))

    st_x1, st_y1 = int(w * 0.07), int(h * 0.235) + float_y
    st_x2, st_y2 = int(w * 0.93), int(h * 0.775) + float_y
    st_w, st_h = st_x2 - st_x1, st_y2 - st_y1

    # =========================================================================
    # Archetypes 1..16 (Bespoke Speech-Matched Open-Canvas Hero Illustrations)
    # =========================================================================
    if archetype.startswith("hero_") or archetype == "web_dynamic_scene":
        return render_contextual_hero_illustration(
            img=img,
            archetype=archetype,
            stage_bbox=(st_x1, st_y1, st_x2, st_y2),
            choreo_u=choreo_u,
            global_t=global_t,
            style_spec=style_spec,
            scene_meta=scene_meta,
            sub_items=sub_items,
            kpi_val=kpi_val,
            kpi_lbl=kpi_lbl,
            concept_title=concept_title,
            draw_contained_text_fn=draw_contained_arabic_text,
            draw_arabic_text_fn=draw_arabic_text,
            get_font_fn=get_arabic_font,
            draw_cursor_fn=_draw_cursor_with_ripple
        )

    # =========================================================================
    # Archetype 17 [6944 Shot 1]: chrono_ring_3d_counter (الحلقة ثلاثية الأبعاد والعداد الدائري السريع 10->14->20)
    # =========================================================================
    if archetype == "chrono_ring_3d_counter":
        ring_cy = int(h * 0.46) + float_y
        # تبدأ الحلقة كبيرة (Zoom-Out من الكاميرا 1.55x -> 1.0x) كما في أول لقطة من 6944.mp4
        zoom_out_p = _staggered_spring(choreo_u, delay=0.0, duration=0.45, stiffness=180.0, damping=14.0)
        scale_ring = 1.48 - 0.48 * zoom_out_p
        outer_r = int(min(w, h) * 0.27 * scale_ring)
        ring_thick = max(20, int(outer_r * 0.21))

        # ظل ثلاثي الأبعاد ناعم خلف الحلقة
        sh_r = outer_r + 12
        sh_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_d = ImageDraw.Draw(sh_layer, "RGBA")
        sh_d.ellipse(
            [(cx - outer_r, ring_cy - outer_r + 12), (cx + outer_r, ring_cy + outer_r + 12)],
            outline=(24, 20, 16, 48), width=ring_thick
        )
        sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(radius=10))
        img.alpha_composite(sh_layer)
        draw = ImageDraw.Draw(img, "RGBA")

        # مسار الحلقة الرمادي الفضي الثلاثي الأبعاد
        track_col = (212, 212, 216, 245) if is_light_bg else (51, 65, 85, 235)
        draw.ellipse(
            [(cx - outer_r, ring_cy - outer_r), (cx + outer_r, ring_cy + outer_r)],
            outline=track_col, width=ring_thick
        )

        # المرحلة 1 (0.0 -> 0.28): ظهور الكلمات التمهيدية داخل الحلقة بالتزامن مع بداية الجملة
        # المرحلة 2 (0.20 -> 0.95): دوران القوس الذهبي وتصاعد الرقم الحي في قلب الحلقة!
        arc_u = max(0.0, min(1.0, (choreo_u - 0.12) / 0.78))
        sweep_deg = int(325.0 * _ease_out_cubic(arc_u))
        if sweep_deg > 4:
            draw.arc(
                [(cx - outer_r, ring_cy - outer_r), (cx + outer_r, ring_cy + outer_r)],
                start=-90, end=-90 + sweep_deg,
                fill=(*primary_c, 255), width=ring_thick
            )
            # كبسولة الرأس الذهبي الثلاثي الأبعاد في مقدمة القوس
            head_rad = math.radians(-90 + sweep_deg)
            mid_r = outer_r - ring_thick // 2
            hx = cx + int(mid_r * math.cos(head_rad))
            hy = ring_cy + int(mid_r * math.sin(head_rad))
            cap_r = ring_thick // 2 + 2
            draw.ellipse([(hx - cap_r, hy - cap_r), (hx + cap_r, hy + cap_r)], fill=(*sticker_bg_c, 255))

        # المحتوى داخل الحلقة: كلمات البداية ثم العداد الرقمي الحي (مثل "في أقل من" -> "10 -> 14 -> 20")
        raw_num_m = re.search(r"(\d+)", f"{kpi_val} {concept_title}")
        target_num = int(raw_num_m.group(1)) if raw_num_m else int(scene_meta.get("target_number") or 20)
        if target_num <= 1:
            target_num = 20

        if choreo_u < 0.24:
            intro_words = " ".join(sc_w_list[:min(3, len(sc_w_list))])
            draw_contained_arabic_text(
                draw,
                (cx - int(outer_r * 0.68), ring_cy - int(outer_r * 0.40), cx + int(outer_r * 0.68), ring_cy + int(outer_r * 0.40)),
                intro_words, initial_font_size=max(26, int(outer_r * 0.32)), fill=(*headline_txt_c, 255)
            )
        else:
            count_u = min(1.0, (choreo_u - 0.22) / 0.62)
            cur_num = max(1, int(round(target_num * _ease_out_cubic(count_u))))
            num_font = get_arabic_font(max(44, int(outer_r * 0.62)), bold=True)
            draw_arabic_text(draw, (cx, ring_cy - 6), f"{cur_num}", font=num_font, fill=(*headline_txt_c, 255))

        # عنوان الفكرة يظهر بنعومة أسفل الحلقة بعد بدء العد
        if choreo_u >= 0.28:
            lbl_sp = _staggered_spring(choreo_u, delay=0.28, duration=0.36)
            ly = ring_cy + outer_r + 36 + int(24 * (1.0 - lbl_sp))
            draw_contained_arabic_text(
                draw, (st_x1 + 16, ly - 24, st_x2 - 16, ly + 24),
                concept_title, initial_font_size=max(24, int(h * 0.033)), fill=(*headline_txt_c, int(255 * min(1.0, lbl_sp)))
            )
        return img

    # =========================================================================
    # Archetype 2 [6944 Shot 2]: pack_3d_extruding_pillars (صندوق الأصول ثلاثي الأبعاد والأعمدة الملونة المنبثقة بالتتابع)
    # =========================================================================
    if archetype == "pack_3d_extruding_pillars":
        # صندوق الأصول لا يظهر قبل الكلام، بل ينبثق بفيزياء الزنبرك بعد أولى الكلمات (choreo_u >= 0.14)
        dock_sp = _staggered_spring(choreo_u, delay=0.12, duration=0.40, stiffness=stiffness, damping=damping)
        if dock_sp <= 0.04:
            return img

        box_sz = int(min(st_w, st_h) * 0.46 * max(0.35, dock_sp))
        box_cx = cx
        box_cy = st_y1 + int(st_h * 0.50) + int(32 * (1.0 - dock_sp))

        # نرسم الصندوق والأعمدة الثلاثة الملونة التي ترتفع واحداً تلو الآخر على طبقة مستقلة ثم نميلها (-8 درجات) كما في 6944.mp4!
        layer_sz = int(min(st_w, st_h) * 0.82)
        pack_layer = Image.new("RGBA", (layer_sz, layer_sz), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pack_layer, "RGBA")
        lcx, lcy = layer_sz // 2, int(layer_sz * 0.58)
        bsz = int(layer_sz * 0.48 * max(0.4, dock_sp))

        # الظل الخلفي للصندوق الذهبي
        pdraw.rounded_rectangle(
            [(lcx - bsz // 2 + 6, lcy - bsz // 2 + 12), (lcx + bsz // 2 + 6, lcy + bsz // 2 + 12)],
            radius=28, fill=(24, 20, 16, 55)
        )
        # جسم الصندوق الذهبي/الكهرماني الخلفي
        pdraw.rounded_rectangle(
            [(lcx - bsz // 2, lcy - bsz // 2), (lcx + bsz // 2, lcy + bsz // 2)],
            radius=28, fill=(238, 196, 92, 255), outline=(255, 255, 255, 220), width=3
        )

        # الأعمدة الثلاثة الملونة (بنفسجي، سيان، أخضر ليموني) ترتفع بالتتابع واحداً تلو الآخر مع الكلمات المنطوقة!
        pillar_specs = [
            (-int(bsz * 0.27), -12.0, (124, 58, 237), (167, 139, 250), 0.22),
            (0, -2.0, (6, 182, 212), (103, 232, 249), 0.36),
            (int(bsz * 0.27), 8.0, (132, 204, 22), (190, 242, 100), 0.50),
        ]
        pw_pil = max(24, int(bsz * 0.22))
        max_ph_pil = int(bsz * 0.96)

        for x_off, tilt_p, col_dark, col_light, p_delay in pillar_specs:
            p_extrude = _staggered_spring(choreo_u, delay=p_delay, duration=0.38, stiffness=210.0, damping=13.0)
            if p_extrude <= 0.05:
                continue
            cur_ph = max(18, int(max_ph_pil * p_extrude))
            px1 = lcx + x_off - pw_pil // 2
            py2 = lcy + int(bsz * 0.22)
            py1 = py2 - cur_ph
            pdraw.rounded_rectangle([(px1 + 3, py1 + 5), (px1 + pw_pil + 3, py2 + 5)], radius=10, fill=(0, 0, 0, 48))
            pdraw.rounded_rectangle([(px1, py1), (px1 + pw_pil, py2)], radius=10, fill=(*col_dark, 255), outline=(*col_light, 240), width=2)
            # خطوط الملمس الأفقية على كل عمود (كما في أيقونة Sounds Pack في 6944.mp4)
            for ry in range(py1 + 10, py2 - 8, 9):
                pdraw.line([(px1 + 5, ry), (px1 + pw_pil - 5, ry)], fill=(*col_light, 195), width=2)

        # الجيب الأمامي نصف الشفاف للصندوق مع النص
        pocket_y1 = lcy + int(bsz * 0.02)
        pocket_y2 = lcy + bsz // 2
        pdraw.rounded_rectangle(
            [(lcx - bsz // 2, pocket_y1), (lcx + bsz // 2, pocket_y2)],
            radius=24, fill=(245, 208, 108, 228), outline=(255, 255, 255, 190), width=2
        )
        mid_pocket_y = (pocket_y1 + pocket_y2) // 2
        pill_pw = int(bsz * 0.78)
        pill_ph = max(28, int((pocket_y2 - pocket_y1) * 0.54))
        ppx1, ppy1 = lcx - pill_pw // 2, mid_pocket_y - pill_ph // 2
        ppx2, ppy2 = ppx1 + pill_pw, ppy1 + pill_ph
        pdraw.rounded_rectangle([(ppx1, ppy1), (ppx2, ppy2)], radius=pill_ph // 2, fill=(15, 23, 42, 238), outline=(255, 255, 255, 210), width=1)
        pocket_txt = kpi_lbl if kpi_lbl else (sub_items[0] if sub_items else "PRO PACK")
        draw_contained_arabic_text(
            pdraw, (ppx1 + 10, ppy1 + 2, ppx2 - 10, ppy2 - 2),
            pocket_txt, initial_font_size=14, min_font_size=10, fill=(255, 255, 255, 255)
        )

        tilted_pack = pack_layer.rotate(4.5 * math.sin(min(1.0, choreo_u * 1.4) * math.pi * 0.5), resample=Image.Resampling.BICUBIC, expand=False)
        img.alpha_composite(tilted_pack, (box_cx - layer_sz // 2, box_cy - int(layer_sz * 0.55)))
        draw = ImageDraw.Draw(img, "RGBA")

        # مؤشر اليد ينزلق وينقر على الصندوق بعد اكتمال خروج الأعمدة الثلاثة!
        _draw_cursor_with_ripple(draw, (box_cx + 90, box_cy + 130), (box_cx + 12, box_cy + 28), choreo_u, accent_rgb=primary_c)
        return img

    # =========================================================================
    # Archetype 3 [6944 Shot 3]: macos_folder_counter_list (قائمة المجلدات الزرقاء مع العداد الخلفي المتصاعد +44)
    # =========================================================================
    if archetype == "macos_folder_counter_list":
        card_sp = _staggered_spring(choreo_u, delay=0.06, duration=0.38, stiffness=stiffness, damping=damping)
        cw = int(st_w * 0.76 * max(0.75, card_sp))
        ch = int(st_h * 0.64 * max(0.75, card_sp))
        bx1 = cx - cw // 2
        by1 = st_y1 + int(st_h * 0.16) + int(28 * (1.0 - card_sp))
        bx2, by2 = bx1 + cw, by1 + ch

        # العداد الخلفي يظهر فقط إذا ذكر المتحدث رقماً حقيقياً في الجملة (بدون أي أرقام +28 أو +44 عشوائية!)
        num_m = re.search(r"(\d+)", f"{kpi_val} {concept_title}")
        if num_m:
            target_c = max(1, int(num_m.group(1)))
            cur_c = max(1, int(round(target_c * min(1.0, max(0.25, choreo_u * 1.35)))))
            cnt_font = get_arabic_font(max(40, int(h * 0.052)), bold=True)
            cnt_col = (161, 161, 170, 175) if is_light_bg else (148, 163, 184, 175)
            draw_arabic_text(draw, (cx, by1 - int(h * 0.026)), f"+{cur_c}", font=cnt_font, fill=cnt_col)

        # البطاقة البيضاء الناعمة بدون أي حدود سوداء كرتونية (Soft 3D Drop Shadow)
        img = _draw_soft_elevated_card(
            img, (bx1, by1, bx2, by2), radius=24,
            fill_rgba=(255, 255, 255, 253), shadow_offset_y=14, shadow_blur=16, shadow_alpha=46
        )
        draw = ImageDraw.Draw(img, "RGBA")

        # صفوف المجلدات الزرقاء تظهر واحداً تلو الآخر بالتزامن مع تقدم الكلام!
        num_rows = 5
        row_h = (ch - 28) // num_rows
        for ri in range(num_rows):
            row_delay = 0.12 + ri * 0.11
            r_sp = _staggered_spring(choreo_u, delay=row_delay, duration=0.34)
            if r_sp <= 0.05:
                continue
            ry_top = by1 + 14 + ri * row_h + int(14 * (1.0 - r_sp))
            ry_mid = ry_top + row_h // 2

            # أيقونة المجلد الأزرق ثلاثي الأبعاد + النص
            folder_x = bx2 - 42
            _draw_macos_blue_folder_icon(draw, folder_x, ry_mid - 11, w=28, h=22)

            item_txt = f"{ri + 1} - {sub_items[ri % len(sub_items)]}"
            draw_contained_arabic_text(
                draw, (bx1 + 18, ry_top + 2, folder_x - 10, ry_top + row_h - 2),
                item_txt, initial_font_size=16, fill=(39, 39, 42, int(255 * min(1.0, r_sp)))
            )

        # مؤشر اليد ينزلق لأسفل البطاقة وينقر على المجلد الأخير
        _draw_cursor_with_ripple(draw, (bx2 - 20, by1 + 30), (bx2 - 28, by2 - 14), choreo_u, accent_rgb=secondary_c)
        return img

    # =========================================================================
    # Archetype 4 [6944 Shot 4]: reels_6card_showcase_grid (معرض الفيديوهات والبطاقات الستة المتحركة 2×3)
    # =========================================================================
    if archetype == "reels_6card_showcase_grid":
        cols_n, rows_n = 3, 2
        gap_x, gap_y = 12, 14
        card_w = (st_w - (cols_n - 1) * gap_x) // cols_n
        card_h = int((st_h - gap_y - 16) // rows_n)

        live_spk_frm = scene_meta.get("_live_speaker_frame")
        card_palettes = [
            ((15, 23, 42), (56, 189, 248)),
            ((46, 16, 101), (192, 132, 252)),
            ((6, 78, 59), (52, 211, 153)),
            ((30, 58, 138), (96, 165, 250)),
            ((88, 28, 135), (244, 114, 182)),
            ((20, 83, 45), (74, 222, 128)),
        ]

        for idx_c in range(6):
            r_i = idx_c // cols_n
            c_i = idx_c % cols_n
            # توزيع البطاقات الستة بالتتابع كأوراق اللعب مع نطق الكلمات (Staggered Card Deal)
            c_delay = 0.08 + idx_c * 0.09
            c_sp = _staggered_spring(choreo_u, delay=c_delay, duration=0.38, stiffness=200.0, damping=13.5)
            if c_sp <= 0.04:
                continue

            gx1 = st_x1 + c_i * (card_w + gap_x) + int(35 * (1.0 - c_sp))
            gy1 = st_y1 + 8 + r_i * (card_h + gap_y) + int(45 * (1.0 - c_sp))
            gx2, gy2 = gx1 + card_w, gy1 + card_h

            img = _draw_soft_elevated_card(
                img, (gx1, gy1, gx2, gy2), radius=18,
                fill_rgba=(20, 24, 38, 255), shadow_offset_y=10, shadow_blur=10, shadow_alpha=45,
                border_rgba=(255, 255, 255, 220)
            )
            draw = ImageDraw.Draw(img, "RGBA")

            # إذا توفر فريم فيديو حي للمتحدث/المنتج، نعرضه داخل البطاقات المصغرة مع تدرجات لونية سينمائية!
            bg_dark, acc_glow = card_palettes[idx_c % len(card_palettes)]
            inner_pad = 3
            ix1, iy1, ix2, iy2 = gx1 + inner_pad, gy1 + inner_pad, gx2 - inner_pad, gy2 - inner_pad
            iw, ih = max(8, ix2 - ix1), max(8, iy2 - iy1)

            if isinstance(live_spk_frm, np.ndarray) and live_spk_frm.ndim == 3:
                thumb_pil = Image.fromarray(live_spk_frm).resize((iw, ih), Image.Resampling.BILINEAR).convert("RGBA")
                tint_ov = Image.new("RGBA", (iw, ih), (*bg_dark, 85))
                thumb_pil = Image.alpha_composite(thumb_pil, tint_ov)
                mask_c = Image.new("L", (iw, ih), 0)
                ImageDraw.Draw(mask_c).rounded_rectangle([(0, 0), (iw - 1, ih - 1)], radius=15, fill=255)
                img.paste(thumb_pil, (ix1, iy1), mask_c)
                draw = ImageDraw.Draw(img, "RGBA")
            else:
                draw.rounded_rectangle([(ix1, iy1), (ix2, iy2)], radius=15, fill=(*bg_dark, 255))
                # هالة ضوئية وصورة رمزية أنيقة داخل بطاقة الريلز
                av_r = max(14, int(min(iw, ih) * 0.22))
                av_cx, av_cy = (ix1 + ix2) // 2, iy1 + int(ih * 0.38)
                draw.ellipse([(av_cx - av_r - 4, av_cy - av_r - 4), (av_cx + av_r + 4, av_cy + av_r + 4)], fill=(*acc_glow, 55))
                draw.ellipse([(av_cx - av_r, av_cy - av_r), (av_cx + av_r, av_cy + av_r)], fill=(*acc_glow, 240))
                draw.polygon([(av_cx - 4, av_cy - 6), (av_cx - 4, av_cy + 6), (av_cx + 7, av_cy)], fill=(255, 255, 255, 255))

            # شريط العنوان المصغر أسفل كل بطاقة ريلز
            lbl_y1 = iy2 - max(28, int(ih * 0.26))
            draw.rounded_rectangle([(ix1 + 4, lbl_y1), (ix2 - 4, iy2 - 4)], radius=8, fill=(0, 0, 0, 155))
            draw_contained_arabic_text(
                draw, (ix1 + 6, lbl_y1, ix2 - 6, iy2 - 4),
                sub_items[idx_c % len(sub_items)], initial_font_size=12, min_font_size=9, fill=(255, 255, 255, 255)
            )

            # شارة المنصة المضيئة في زاوية البطاقة (كما في 6944.mp4)
            b_col = (225, 48, 108) if idx_c % 2 == 0 else (16, 185, 129)
            _draw_checkmark_badge(draw, ix2 - 12, iy1 + 12, 8, color_rgb=b_col)

        return img

    # =========================================================================
    if archetype == "dark_cinema_fanned_cards":
        card_w = int(st_w * 0.46)
        card_h = int(st_h * 0.54)
        top_tags = [
            kpi_lbl if kpi_lbl else (sub_items[0] if sub_items else "AI AUDIO"),
            kpi_val if kpi_val else (sub_items[1] if len(sub_items) > 1 else "PRO STUDIO")
        ]
        bot_labels = [
            sub_items[0] if sub_items else "تنقية الصوت",
            sub_items[min(1, len(sub_items) - 1)] if sub_items else "موشن غرافيك"
        ]

        for ci in range(2):
            c_delay = 0.08 + ci * 0.16
            c_sp = _staggered_spring(choreo_u, delay=c_delay, duration=0.40, stiffness=195.0, damping=14.0)
            if c_sp <= 0.05:
                continue

            # رندرة بدقة مضاعفة 2x قبل التدوير لمنع أي تكسر في حواف البطاقات المروحية!
            ss = 2
            cw_s, ch_s = (card_w + 28) * ss, (card_h + 28) * ss
            c_layer = Image.new("RGBA", (cw_s, ch_s), (0, 0, 0, 0))
            cdraw = ImageDraw.Draw(c_layer, "RGBA")
            accent_card_c = (16, 185, 129) if ci == 0 else (56, 189, 248)
            pad_s = 14 * ss
            w_s, h_s = card_w * ss, card_h * ss

            cdraw.rounded_rectangle([(pad_s + 4, pad_s + 10), (pad_s + w_s + 4, pad_s + h_s + 10)], radius=24 * ss, fill=(0, 0, 0, 135))
            cdraw.rounded_rectangle([(pad_s, pad_s), (pad_s + w_s, pad_s + h_s)], radius=24 * ss, fill=(20, 25, 38, 252), outline=(*accent_card_c, 235), width=2 * ss)

            # شريط علوي مضيء
            cdraw.rounded_rectangle([(pad_s + 12 * ss, pad_s + 12 * ss), (pad_s + w_s - 12 * ss, pad_s + 46 * ss)], radius=12 * ss, fill=(*accent_card_c, 240))
            draw_contained_arabic_text(cdraw, (pad_s + 18 * ss, pad_s + 14 * ss, pad_s + w_s - 18 * ss, pad_s + 44 * ss), top_tags[ci], initial_font_size=15 * ss, fill=(255, 255, 255, 255))

            # موجة صوتية متوهجة
            wf_cy = pad_s + 46 * ss + int((h_s - 46 * ss) * 0.42)
            num_bars = 14
            bar_step = (w_s - 36 * ss) // num_bars
            for bi in range(num_bars):
                bx_w = pad_s + 22 * ss + bi * bar_step
                bh_w = int((8 + 22 * abs(math.sin(global_t * 6.0 + bi * 0.55 + ci))) * ss)
                cdraw.rounded_rectangle([(bx_w - 2 * ss, wf_cy - bh_w), (bx_w + 2 * ss, wf_cy + bh_w)], radius=2 * ss, fill=(*accent_card_c, 245))

            draw_contained_arabic_text(
                cdraw, (pad_s + 14 * ss, wf_cy + 28 * ss, pad_s + w_s - 14 * ss, pad_s + h_s - 10 * ss),
                bot_labels[ci], initial_font_size=15 * ss, fill=(248, 250, 252, 255)
            )

            c_layer_1x = c_layer.resize((card_w + 28, card_h + 28), Image.Resampling.LANCZOS)
            tilt = (-5.0 if ci == 0 else 5.0) * c_sp
            rot_c = c_layer_1x.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)
            dest_x = (st_x1 - 6 if ci == 0 else st_x2 - card_w - 18) + int((0 if ci == 0 else 1) * 18 * (1.0 - c_sp))
            dest_y = st_y1 + int(st_h * 0.14) + int(28 * (1.0 - c_sp))
            img.alpha_composite(rot_c, (dest_x, dest_y))

        return img

    # =========================================================================
    # Archetype 6 [6944 Shot 6]: interactive_profile_follow_card (بطاقة المنصة/الحساب التفاعلية الثلاثية الأبعاد)
    # =========================================================================
    if archetype == "interactive_profile_follow_card":
        card_sp = _staggered_spring(choreo_u, delay=0.06, duration=0.38, stiffness=stiffness, damping=damping)
        cw = int(st_w * 0.90 * max(0.80, card_sp))
        ch = int(st_h * 0.64 * max(0.80, card_sp))
        bx1 = cx - cw // 2
        by1 = st_y1 + int(st_h * 0.10) + int(28 * (1.0 - card_sp))
        bx2, by2 = bx1 + cw, by1 + ch

        img = _draw_soft_elevated_card(
            img, (bx1, by1, bx2, by2), radius=26,
            fill_rgba=(255, 255, 255, 254), shadow_offset_y=16, shadow_blur=18, shadow_alpha=58,
            border_rgba=(*primary_c, 210)
        )
        draw = ImageDraw.Draw(img, "RGBA")

        # ترويسة البطاقة: أفاتار ثلاثي الأبعاد بداخله أيقونة ماسية/تاج مضيء + شارة توثيق
        av_r = max(26, int(ch * 0.14))
        av_cx, av_cy = bx1 + 26 + av_r, by1 + 24 + av_r
        draw.ellipse([(av_cx - av_r - 3, av_cy - av_r - 3), (av_cx + av_r + 3, av_cy + av_r + 3)], outline=(*primary_c, 255), width=2)
        draw.ellipse([(av_cx - av_r, av_cy - av_r), (av_cx + av_r, av_cy + av_r)], fill=(15, 23, 42, 255))
        # رسم أيقونة نجمة رباعية ذكية داخل الدائرة حتى لا تبدو دائرة سوداء فارغة!
        star_r = int(av_r * 0.52)
        star_poly = [
            (av_cx, av_cy - star_r),
            (av_cx + int(star_r * 0.35), av_cy - int(star_r * 0.35)),
            (av_cx + star_r, av_cy),
            (av_cx + int(star_r * 0.35), av_cy + int(star_r * 0.35)),
            (av_cx, av_cy + star_r),
            (av_cx - int(star_r * 0.35), av_cy + int(star_r * 0.35)),
            (av_cx - star_r, av_cy),
            (av_cx - int(star_r * 0.35), av_cy - int(star_r * 0.35)),
        ]
        draw.polygon(star_poly, fill=(*primary_c, 255), outline=(255, 255, 255, 230))
        _draw_checkmark_badge(draw, av_cx + av_r - 4, av_cy + av_r - 4, 8, color_rgb=(37, 99, 235))

        info_x1 = av_cx + av_r + 14
        info_x2 = bx2 - 18
        top_title = concept_title if concept_title else "منصة الذكاء الاصطناعي"
        sub_tag = kpi_lbl if (kpi_lbl and kpi_lbl != top_title) else "100% مجاناً • جودة استوديو"
        draw_contained_arabic_text(draw, (info_x1, by1 + 18, info_x2, by1 + 48), top_title, initial_font_size=17, fill=(15, 23, 42, 255))
        draw_contained_arabic_text(draw, (info_x1, by1 + 48, info_x2, by1 + 74), sub_tag, initial_font_size=14, fill=(37, 99, 235, 255))

        # خط فاصل ناعم
        div_y = av_cy + av_r + 10
        draw.line([(bx1 + 22, div_y), (bx2 - 22, div_y)], fill=(226, 232, 240, 255), width=2)

        # سطرا المزايا بدون تكرار
        mid_y1 = div_y + 10
        feat_items = [s for s in sub_items if s != top_title and s != sub_tag]
        if len(feat_items) < 2:
            feat_items = [sub_tag, "توليد تلقائي بالكامل"]
        for li in range(2):
            l_sp = _staggered_spring(choreo_u, delay=0.18 + li * 0.10, duration=0.34)
            if l_sp > 0.05:
                ly_r = mid_y1 + li * 34
                draw.rounded_rectangle([(bx1 + 20, ly_r), (bx2 - 20, ly_r + 28)], radius=8, fill=(248, 250, 252, 255))
                _draw_checkmark_badge(draw, bx2 - 34, ly_r + 14, 8, color_rgb=accent_c)
                draw_contained_arabic_text(draw, (bx1 + 28, ly_r + 2, bx2 - 50, ly_r + 26), feat_items[li % len(feat_items)], initial_font_size=14, fill=(30, 41, 59, 255))

        # زر الإجراء التفاعلي الأزرق
        is_clicked = (choreo_u >= 0.66)
        btn_h = max(44, int(ch * 0.17))
        btn_y1 = by2 - btn_h - 14
        btn_y2 = by2 - 14
        btn_x1, btn_x2 = bx1 + 20, bx2 - 20
        btn_col = (16, 185, 129, 255) if is_clicked else (37, 99, 235, 255)
        btn_label = f"✔ {sub_tag}" if is_clicked else f"✨ {sub_tag}"

        draw.rounded_rectangle([(btn_x1, btn_y1 + 3), (btn_x2, btn_y2 + 3)], radius=14, fill=(15, 23, 42, 45))
        draw.rounded_rectangle([(btn_x1, btn_y1), (btn_x2, btn_y2)], radius=14, fill=btn_col)
        draw_contained_arabic_text(draw, (btn_x1 + 14, btn_y1, btn_x2 - 14, btn_y2), btn_label, initial_font_size=16, fill=(255, 255, 255, 255))

        _draw_cursor_with_ripple(draw, (bx2 - 20, by2 + 35), (cx, (btn_y1 + btn_y2) // 2), choreo_u, accent_rgb=primary_c)
        return img

    # =========================================================================
    # Archetype 7: bezier_growth_nodes (مخطط المنحنى الصاعد المرسوم تدريجياً مع العقد)
    # =========================================================================
    if archetype == "bezier_growth_nodes":
        s_card = 0.82 + 0.18 * _staggered_spring(choreo_u, delay=0.06, duration=0.40)
        cw, ch = int(st_w * 0.92 * s_card), int(st_h * 0.64 * s_card)
        bx1, by1 = cx - cw // 2, st_y1 + 8
        bx2, by2 = bx1 + cw, by1 + ch

        img = _draw_soft_elevated_card(
            img, (bx1, by1, bx2, by2), radius=24,
            fill_rgba=(255, 255, 255, 253), shadow_offset_y=14, shadow_blur=16, shadow_alpha=46
        )
        draw = ImageDraw.Draw(img, "RGBA")

        pill_y = by1 + 16
        draw.rounded_rectangle([(bx1 + 18, pill_y), (bx2 - 18, pill_y + 36)], radius=12, fill=(244, 244, 245, 255))
        draw_contained_arabic_text(
            draw, (bx1 + 24, pill_y, bx2 - 24, pill_y + 36),
            f"{kpi_val}  •  {kpi_lbl}", initial_font_size=16, fill=(*dark_navy, 255)
        )

        nodes_xy = [
            (bx1 + int(cw * 0.16), by1 + int(ch * 0.80)),
            (bx1 + int(cw * 0.39), by1 + int(ch * 0.64)),
            (bx1 + int(cw * 0.63), by1 + int(ch * 0.47)),
            (bx1 + int(cw * 0.85), by1 + int(ch * 0.30)),
        ]
        trace_prog = min(1.0, max(0.08, (choreo_u - 0.10) * 1.25))
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
            poly_area = [(dense_pts[0][0], by2 - 10)] + dense_pts + [(dense_pts[-1][0], by2 - 10)]
            draw.polygon(poly_area, fill=(primary_c[0], primary_c[1], primary_c[2], 45))
            draw.line(dense_pts, fill=(*primary_c, 255), width=4)

        for ni, (nx, ny) in enumerate(nodes_xy):
            node_u = ni / float(total_segs)
            if trace_prog + 0.04 >= node_u:
                n_pop = _staggered_spring(choreo_u, delay=0.12 + ni * 0.14, duration=0.35)
                nr = max(9, int(15 * n_pop))
                n_col = primary_c if (ni == len(nodes_xy) - 1 or ni == 0) else dark_navy
                if ni == len(nodes_xy) - 1:
                    pulse_r = nr + int(5 + 4 * math.sin(global_t * 5.0))
                    draw.ellipse([(nx - pulse_r, ny - pulse_r), (nx + pulse_r, ny + pulse_r)], fill=(*primary_c, 65))
                draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(*n_col, 255), outline=(255, 255, 255, 255), width=2)
                nf = get_arabic_font(11, bold=True)
                draw_arabic_text(draw, (nx, ny), f"{ni + 1:02d}", font=nf, fill=(255, 255, 255, 255))

        sub_y = by2 + 18
        pill_w = (st_w - 14) // 2
        for pi in range(2):
            p_sp = _staggered_spring(choreo_u, delay=0.28 + pi * 0.14, duration=0.36)
            if p_sp <= 0.05:
                continue
            px1 = st_x1 + pi * (pill_w + 14)
            py1 = sub_y + int(18 * (1.0 - p_sp))
            img = _draw_soft_elevated_card(img, (px1, py1, px1 + pill_w, py1 + 48), radius=16, fill_rgba=(255, 255, 255, 248), shadow_offset_y=8, shadow_blur=10, shadow_alpha=36)
            draw = ImageDraw.Draw(img, "RGBA")
            draw_contained_arabic_text(draw, (px1 + 10, py1, px1 + pill_w - 10, py1 + 48), sub_items[pi], initial_font_size=15, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 8: live_magnifier_scanner (المكبّر الفاحص المتحرك حياً فوق البطاقات)
    # =========================================================================
    if archetype == "live_magnifier_scanner":
        s_card = 0.82 + 0.18 * _staggered_spring(choreo_u, delay=0.06, duration=0.40)
        cw, ch = int(st_w * 0.92 * s_card), int(st_h * 0.70 * s_card)
        bx1, by1 = cx - cw // 2, st_y1 + int(st_h * 0.05)
        bx2, by2 = bx1 + cw, by1 + ch

        img = _draw_soft_elevated_card(img, (bx1, by1, bx2, by2), radius=24, fill_rgba=(255, 255, 255, 253), shadow_offset_y=14, shadow_blur=16, shadow_alpha=46)
        draw = ImageDraw.Draw(img, "RGBA")

        hdr_y1, hdr_y2 = by1 + 16, by1 + 58
        badge_w = int(cw * 0.34)
        draw.rounded_rectangle([(bx2 - badge_w - 16, hdr_y1), (bx2 - 16, hdr_y2)], radius=12, fill=(*primary_c, 255))
        draw_contained_arabic_text(draw, (bx2 - badge_w - 10, hdr_y1, bx2 - 22, hdr_y2), kpi_val, initial_font_size=15, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(bx1 + 16, hdr_y1), (bx2 - badge_w - 28, hdr_y2)], radius=12, fill=(244, 244, 245, 255))
        draw_contained_arabic_text(draw, (bx1 + 24, hdr_y1, bx2 - badge_w - 34, hdr_y2), kpi_lbl, initial_font_size=15, fill=(*dark_navy, 255))

        sq_y1 = hdr_y2 + 18
        sq_h = by2 - sq_y1 - 20
        sq_w = (cw - 56) // 3

        scan_u = 0.5 - 0.45 * math.cos(choreo_u * math.pi * 1.4)
        mag_cx = int(bx1 + 36 + scan_u * (cw - 72))
        mag_cy = sq_y1 + sq_h // 2 + int(8 * math.sin(global_t * 3.5))
        active_sq_idx = min(2, max(0, int(scan_u * 3.0)))

        for si in range(3):
            s_sp = _staggered_spring(choreo_u, delay=0.10 + si * 0.12, duration=0.36)
            if s_sp <= 0.05:
                continue
            sx = bx1 + 16 + si * (sq_w + 12)
            is_hovered = (si == active_sq_idx)
            pad_zoom = -4 if is_hovered else 0
            scol = (254, 249, 195, 255) if is_hovered else (244, 244, 245, 255)
            b_col = primary_c if is_hovered else (228, 228, 231)
            draw.rounded_rectangle(
                [(sx + pad_zoom, sq_y1 + pad_zoom), (sx + sq_w - pad_zoom, sq_y1 + sq_h - pad_zoom)],
                radius=16, fill=scol, outline=(*b_col, 255), width=2 if is_hovered else 1
            )
            ic_y = sq_y1 + int(sq_h * 0.25)
            draw.ellipse([(sx + sq_w // 2 - 14, ic_y - 14), (sx + sq_w // 2 + 14, ic_y + 14)], fill=(*primary_c, 255) if is_hovered else (161, 161, 170, 255))
            nf = get_arabic_font(12, bold=True)
            draw_arabic_text(draw, (sx + sq_w // 2, ic_y), str(si + 1), font=nf, fill=(255, 255, 255, 255))

            if si < len(sub_items):
                draw_contained_arabic_text(
                    draw, (sx + 6, sq_y1 + int(sq_h * 0.48), sx + sq_w - 6, sq_y1 + sq_h - 10),
                    sub_items[si], initial_font_size=15 if is_hovered else 13, fill=(*dark_navy, 255)
                )

        if choreo_u >= 0.22:
            mag_r = int(min(cw, ch) * 0.18)
            handle_end_x = mag_cx - int(mag_r * 1.30)
            handle_end_y = mag_cy + int(mag_r * 1.30)
            draw.line([(mag_cx - int(mag_r * 0.68), mag_cy + int(mag_r * 0.68)), (handle_end_x, handle_end_y)], fill=(*dark_navy, 255), width=9)
            draw.ellipse([(mag_cx - mag_r, mag_cy - mag_r), (mag_cx + mag_r, mag_cy + mag_r)], fill=(255, 255, 255, 92), outline=(*dark_navy, 255), width=5)
            draw.ellipse([(mag_cx - mag_r + 4, mag_cy - mag_r + 4), (mag_cx + mag_r - 4, mag_cy + mag_r - 4)], outline=(*primary_c, 255), width=2)
        return img

    # =========================================================================
    # Archetype 9: damped_balance_scale (الميزان الفيزيائي المتأرجح للمقارنة بين المشكلة والحل)
    # =========================================================================
    if archetype == "damped_balance_scale":
        left_pan_info = scene_meta.get("balance_left") or ("الطريقة التقليدية", "وقت ومجهود")
        right_pan_info = scene_meta.get("balance_right") or (kpi_lbl, kpi_val)

        tilt_prog = _staggered_spring(choreo_u, delay=0.14, duration=0.52, stiffness=180.0, damping=11.0)
        sway = 2.0 * math.sin(global_t * 3.6)
        tilt_angle = math.radians(-12.5 * tilt_prog + sway)

        pivot_x, pivot_y = cx, st_y1 + int(st_h * 0.32)
        base_y = st_y1 + int(st_h * 0.86)
        beam_col = (39, 39, 42, 225) if is_light_bg else (255, 255, 255, 225)

        draw.line([(pivot_x, pivot_y), (pivot_x, base_y)], fill=beam_col, width=6)
        draw.rounded_rectangle([(pivot_x - int(st_w * 0.18), base_y - 7), (pivot_x + int(st_w * 0.18), base_y + 7)], radius=7, fill=(*primary_c, 255))
        draw.ellipse([(pivot_x - 13, pivot_y - 13), (pivot_x + 13, pivot_y + 13)], fill=(*primary_c, 255), outline=(255, 255, 255, 245), width=3)

        arm_half = int(st_w * 0.29)
        lx = pivot_x - int(arm_half * math.cos(tilt_angle))
        ly = pivot_y - int(arm_half * math.sin(tilt_angle))
        rx = pivot_x + int(arm_half * math.cos(tilt_angle))
        ry = pivot_y + int(arm_half * math.sin(tilt_angle))
        draw.line([(lx, ly), (rx, ry)], fill=(*primary_c, 255), width=5)

        pan_w, pan_h = int(st_w * 0.42), int(st_h * 0.33)
        if choreo_u >= 0.12:
            l_box = (lx - pan_w // 2, ly + 16, lx + pan_w // 2, ly + 16 + pan_h)
            img = _draw_soft_elevated_card(img, l_box, radius=18, fill_rgba=(255, 255, 255, 252), shadow_offset_y=10, shadow_blur=12, shadow_alpha=42, border_rgba=(239, 68, 68, 190))
            draw = ImageDraw.Draw(img, "RGBA")
            draw_contained_arabic_text(draw, (l_box[0] + 8, l_box[1] + 8, l_box[2] - 8, l_box[1] + int(pan_h * 0.48)), str(left_pan_info[0]), initial_font_size=15, fill=(71, 85, 105, 255))
            draw_contained_arabic_text(draw, (l_box[0] + 8, l_box[1] + int(pan_h * 0.50), l_box[2] - 8, l_box[3] - 8), str(left_pan_info[1]), initial_font_size=17, fill=(239, 68, 68, 255))

        if choreo_u >= 0.26:
            r_box = (rx - pan_w // 2, ry + 16, rx + pan_w // 2, ry + 16 + pan_h)
            img = _draw_soft_elevated_card(img, r_box, radius=18, fill_rgba=(255, 255, 255, 254), shadow_offset_y=10, shadow_blur=12, shadow_alpha=42, border_rgba=(*accent_c, 210))
            draw = ImageDraw.Draw(img, "RGBA")
            _draw_checkmark_badge(draw, r_box[2] - 14, r_box[1] + 14, 10, color_rgb=accent_c)
            draw_contained_arabic_text(draw, (r_box[0] + 8, r_box[1] + 8, r_box[2] - 24, r_box[1] + int(pan_h * 0.48)), str(right_pan_info[0]), initial_font_size=15, fill=(30, 41, 59, 255))
            draw_contained_arabic_text(draw, (r_box[0] + 8, r_box[1] + int(pan_h * 0.50), r_box[2] - 8, r_box[3] - 8), str(right_pan_info[1]), initial_font_size=17, fill=(*accent_c, 255))
        return img

    # =========================================================================
    # Archetype 10: nle_timeline_matrix (جدول ومخطط التايملاين التفاعلي مع مؤشر القراءة Playhead)
    # =========================================================================
    if archetype == "nle_timeline_matrix":
        s_card = 0.84 + 0.16 * _staggered_spring(choreo_u, delay=0.06, duration=0.38)
        cw, ch = int(st_w * 0.94 * s_card), int(st_h * 0.78 * s_card)
        bx1, by1 = cx - cw // 2, st_y1 + int(st_h * 0.04)
        bx2, by2 = bx1 + cw, by1 + ch

        img = _draw_soft_elevated_card(img, (bx1, by1, bx2, by2), radius=24, fill_rgba=(255, 255, 255, 253), shadow_offset_y=14, shadow_blur=16, shadow_alpha=46)
        draw = ImageDraw.Draw(img, "RGBA")

        hdr_h = 44
        draw.rounded_rectangle([(bx1 + 14, by1 + 14), (bx2 - 14, by1 + 14 + hdr_h)], radius=14, fill=(*dark_navy, 255))
        hdr_str = f"{kpi_val} • {kpi_lbl}".strip(" •") or concept_title
        draw_contained_arabic_text(draw, (bx1 + 20, by1 + 14, bx2 - 20, by1 + 14 + hdr_h), hdr_str, initial_font_size=16, fill=(255, 255, 255, 255))

        track_colors = [primary_c, (139, 92, 246), accent_c, (59, 130, 246)]
        rows_top = by1 + 14 + hdr_h + 14
        row_h = (ch - hdr_h - 46) // 4
        tl_x1, tl_x2 = bx1 + 18, bx1 + int(cw * 0.48)

        for ri in range(4):
            r_sp = _staggered_spring(choreo_u, delay=0.10 + ri * 0.11, duration=0.35)
            if r_sp <= 0.05:
                continue
            ry1 = rows_top + ri * (row_h + 6)
            ry2 = ry1 + row_h
            draw.rounded_rectangle([(bx1 + 14, ry1), (bx2 - 14, ry2)], radius=12, fill=(244, 244, 245, 255))
            clip_prog = min(1.0, max(0.18, r_sp))
            c_w = int((tl_x2 - tl_x1) * clip_prog)
            t_col = track_colors[ri % len(track_colors)]
            draw.rounded_rectangle([(tl_x1, ry1 + 8), (tl_x1 + c_w, ry2 - 8)], radius=8, fill=(*t_col, 245))
            draw_contained_arabic_text(draw, (tl_x2 + 10, ry1 + 4, bx2 - 18, ry2 - 4), sub_items[ri], initial_font_size=15, fill=(*dark_navy, 255))

        ph_x = int(tl_x1 + (tl_x2 - tl_x1) * (0.12 + 0.82 * choreo_u))
        draw.line([(ph_x, rows_top - 4), (ph_x, by2 - 14)], fill=(239, 68, 68, 255), width=3)
        draw.polygon([(ph_x - 6, rows_top - 6), (ph_x + 6, rows_top - 6), (ph_x, rows_top + 2)], fill=(239, 68, 68, 255))
        return img

    # =========================================================================
    # Archetype 11: radar_target_sweep (رادار الاستهداف الدوار بشعاع مسح ضوئي حي 360°)
    # =========================================================================
    if archetype == "radar_target_sweep":
        rad_cy = st_y1 + int(st_h * 0.42)
        s_card = 0.80 + 0.20 * _staggered_spring(choreo_u, delay=0.06, duration=0.40)
        max_r = int(min(st_w, st_h) * 0.33 * s_card)
        ring_col = (39, 39, 42) if is_light_bg else (255, 255, 255)

        for ri, r_frac in enumerate([1.0, 0.70, 0.40]):
            rr = int(max_r * r_frac)
            draw.ellipse(
                [(cx - rr, rad_cy - rr), (cx + rr, rad_cy + rr)],
                fill=(primary_c[0], primary_c[1], primary_c[2], 24 if ri == 0 else 12),
                outline=(*ring_col, 195 if ri == 0 else 110),
                width=2
            )

        sweep_deg = (global_t * 145.0) % 360.0
        draw.pieslice(
            [(cx - max_r, rad_cy - max_r), (cx + max_r, rad_cy + max_r)],
            start=sweep_deg - 42.0, end=sweep_deg,
            fill=(primary_c[0], primary_c[1], primary_c[2], 80)
        )

        node_angles = [i * (math.pi / 3.0) for i in range(6)]
        for ni, ang in enumerate(node_angles):
            n_sp = _staggered_spring(choreo_u, delay=0.10 + ni * 0.08, duration=0.36)
            if n_sp <= 0.08:
                continue
            dist_r = max_r * 0.68 * n_sp
            nx = cx + int(dist_r * math.cos(ang + global_t * 0.35))
            ny = rad_cy + int(dist_r * math.sin(ang + global_t * 0.35))
            nr = max(14, int(max_r * 0.16))
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(255, 255, 255, 252), outline=(*primary_c, 240), width=2)
            draw.ellipse([(nx - nr // 2, ny - nr // 2), (nx + nr // 2, ny + nr // 2)], fill=(*primary_c, 255))
            if ni % 2 == 0 and choreo_u >= 0.30 + ni * 0.08:
                _draw_checkmark_badge(draw, nx + nr - 3, ny - nr + 3, 8, color_rgb=accent_c)

        if choreo_u >= 0.25:
            pill_y = rad_cy + max_r + 18
            img = _draw_soft_elevated_card(img, (st_x1 + 14, pill_y, st_x2 - 14, pill_y + 50), radius=25, fill_rgba=(255, 255, 255, 252), shadow_offset_y=10, shadow_blur=12, shadow_alpha=40)
            draw = ImageDraw.Draw(img, "RGBA")
            rad_pill_txt = concept_title if (kpi_val == sub_items[0] or kpi_val in sub_items[0]) else f"{kpi_val}  •  {sub_items[0]}"
            draw_contained_arabic_text(
                draw, (st_x1 + 26, pill_y, st_x2 - 26, pill_y + 50),
                rad_pill_txt, initial_font_size=17, fill=(*dark_navy, 255)
            )
        return img

    # =========================================================================
    # Archetype 12: floating_3d_stat_Compare (بطاقتا مقارنة ثلاثيتا الأبعاد مع مؤشر تحول مركزي حي)
    # =========================================================================
    if archetype == "floating_3d_stat_Compare":
        ba_info = scene_meta.get("before_after") or ("الطريقة التقليدية", "3.8", kpi_lbl, "9.8")
        card_w = int(st_w * 0.44)
        card_h = int(st_h * 0.56)
        top_y = st_y1 + int(st_h * 0.14)

        for ci in range(2):
            c_sp = _staggered_spring(choreo_u, delay=0.08 + ci * 0.16, duration=0.38, stiffness=200.0, damping=14.0)
            if c_sp <= 0.05:
                continue
            bx1 = (st_x1 + 4 if ci == 0 else st_x2 - card_w - 4)
            by1 = top_y + int(28 * (1.0 - c_sp))
            bx2, by2 = bx1 + card_w, by1 + card_h

            is_win = (ci == 0)
            b_col = accent_c if is_win else (239, 68, 68)
            img = _draw_soft_elevated_card(
                img, (bx1, by1, bx2, by2), radius=22,
                fill_rgba=(255, 255, 255, 253), shadow_offset_y=12, shadow_blur=14, shadow_alpha=44,
                border_rgba=(*b_col, 210)
            )
            draw = ImageDraw.Draw(img, "RGBA")
            draw.rounded_rectangle([(bx1 + 14, by1 + 14), (bx2 - 14, by1 + 52)], radius=12, fill=(*b_col, 240))
            hdr_t = kpi_val if is_win else "السابق"
            draw_contained_arabic_text(draw, (bx1 + 18, by1 + 14, bx2 - 18, by1 + 52), hdr_t, initial_font_size=16, fill=(255, 255, 255, 255))

            ring_r = int(min(card_w, card_h) * 0.24)
            rcx, rcy = (bx1 + bx2) // 2, by1 + int(card_h * 0.52)
            draw.ellipse([(rcx - ring_r, rcy - ring_r), (rcx + ring_r, rcy + ring_r)], outline=(228, 228, 231, 255), width=8)
            sweep = int((315 if is_win else 135) * min(1.0, max(0.2, choreo_u * 1.35)))
            draw.arc([(rcx - ring_r, rcy - ring_r), (rcx + ring_r, rcy + ring_r)], start=-90, end=-90 + sweep, fill=(*b_col, 255), width=8)
            score_txt = str(ba_info[3] if is_win else ba_info[1])
            draw_contained_arabic_text(draw, (rcx - ring_r + 8, rcy - 18, rcx + ring_r - 8, rcy + 18), score_txt, initial_font_size=20, fill=(*dark_navy, 255))

            lbl_t = str(ba_info[2] if is_win else ba_info[0])
            draw_contained_arabic_text(draw, (bx1 + 10, by2 - 54, bx2 - 10, by2 - 12), lbl_t, initial_font_size=15, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 13: step_cascade_ribbon_cards (شرائط الخطوات المتدرجة ثلاثية الأبعاد بعلامات التحقق)
    # =========================================================================
    if archetype == "step_cascade_ribbon_cards":
        num_steps = 4
        rib_h = int((st_h - 44) // num_steps)
        for si in range(num_steps):
            s_sp = _staggered_spring(choreo_u, delay=0.06 + si * 0.12, duration=0.36, stiffness=205.0, damping=14.0)
            if s_sp <= 0.05:
                continue
            indent = (num_steps - 1 - si) * 8
            rx1 = st_x1 + indent + int(36 * (1.0 - s_sp))
            rx2 = st_x2 - indent
            ry1 = st_y1 + 8 + si * (rib_h + 8)
            ry2 = ry1 + rib_h

            img = _draw_soft_elevated_card(
                img, (rx1, ry1, rx2, ry2), radius=18,
                fill_rgba=(255, 255, 255, 253), shadow_offset_y=10, shadow_blur=12, shadow_alpha=42
            )
            draw = ImageDraw.Draw(img, "RGBA")
            tag_w = 56
            col_step = primary_c if si % 2 == 0 else secondary_c
            draw.rounded_rectangle([(rx2 - tag_w - 10, ry1 + 10), (rx2 - 10, ry2 - 10)], radius=12, fill=(*col_step, 255))
            draw_contained_arabic_text(draw, (rx2 - tag_w - 6, ry1 + 10, rx2 - 14, ry2 - 10), f"0{si + 1}", initial_font_size=18, fill=(255, 255, 255, 255))
            _draw_checkmark_badge(draw, rx1 + 26, (ry1 + ry2) // 2, 11, color_rgb=accent_c)
            draw_contained_arabic_text(draw, (rx1 + 48, ry1 + 8, rx2 - tag_w - 20, ry2 - 8), sub_items[si % len(sub_items)], initial_font_size=17, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 14: neural_hub_spoke_network (شبكة العقد الذكية المركزية المتصلة بنبضات ضوئية)
    # =========================================================================
    if archetype == "neural_hub_spoke_network":
        hub_cy = st_y1 + int(st_h * 0.45)
        hub_sp = _staggered_spring(choreo_u, delay=0.05, duration=0.38)
        orbit_rx = int(st_w * 0.34 * max(0.6, hub_sp))
        orbit_ry = int(st_h * 0.30 * max(0.6, hub_sp))

        spoke_angles = [-math.pi * 0.78, -math.pi * 0.22, math.pi * 0.22, math.pi * 0.78]
        spoke_coords = []
        for ai, ang in enumerate(spoke_angles):
            n_sp = _staggered_spring(choreo_u, delay=0.12 + ai * 0.10, duration=0.36)
            nx = cx + int(orbit_rx * math.cos(ang) * n_sp)
            ny = hub_cy + int(orbit_ry * math.sin(ang) * n_sp)
            spoke_coords.append((nx, ny, n_sp))
            if n_sp > 0.1:
                draw.line([(cx, hub_cy), (nx, ny)], fill=(*primary_c, 210), width=4)
                pulse_u = ((global_t * 1.8 + ai * 0.25) % 1.0)
                px = int(cx + (nx - cx) * pulse_u)
                py = int(hub_cy + (ny - hub_cy) * pulse_u)
                draw.ellipse([(px - 5, py - 5), (px + 5, py + 5)], fill=(*accent_c, 255))

        hr = int(min(st_w, st_h) * 0.15 * max(0.7, hub_sp))
        img = _draw_soft_elevated_card(img, (cx - hr, hub_cy - hr, cx + hr, hub_cy + hr), radius=hr, fill_rgba=(*dark_navy, 255), shadow_offset_y=12, shadow_blur=14, shadow_alpha=50, border_rgba=(*primary_c, 255))
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(draw, (cx - hr + 8, hub_cy - hr + 8, cx + hr - 8, hub_cy + hr - 8), kpi_val, initial_font_size=18, fill=(255, 255, 255, 255))

        pw_node, ph_node = int(st_w * 0.40), 46
        for ai, (nx, ny, n_sp) in enumerate(spoke_coords):
            if n_sp <= 0.15:
                continue
            bx1 = max(st_x1, min(st_x2 - pw_node, nx - pw_node // 2))
            by1 = ny - ph_node // 2
            img = _draw_soft_elevated_card(img, (bx1, by1, bx1 + pw_node, by1 + ph_node), radius=14, fill_rgba=(255, 255, 255, 253), shadow_offset_y=8, shadow_blur=10, shadow_alpha=40)
            draw = ImageDraw.Draw(img, "RGBA")
            draw_contained_arabic_text(draw, (bx1 + 10, by1 + 4, bx1 + pw_node - 10, by1 + ph_node - 4), sub_items[ai % len(sub_items)], initial_font_size=14, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 15: dual_metric_gauge_pods (عدادا الأداء المزدوجان مع قائمة الفوائد السفلية)
    # =========================================================================
    if archetype == "dual_metric_gauge_pods":
        pod_w = (st_w - 16) // 2
        pod_h = int(st_h * 0.46)
        for pi in range(2):
            p_sp = _staggered_spring(choreo_u, delay=0.08 + pi * 0.14, duration=0.38)
            if p_sp <= 0.05:
                continue
            px1 = st_x1 + pi * (pod_w + 16)
            py1 = st_y1 + 8 + int(24 * (1.0 - p_sp))
            px2, py2 = px1 + pod_w, py1 + pod_h
            img = _draw_soft_elevated_card(img, (px1, py1, px2, py2), radius=22, fill_rgba=(255, 255, 255, 253), shadow_offset_y=12, shadow_blur=14, shadow_alpha=44)
            draw = ImageDraw.Draw(img, "RGBA")
            gcx, gcy = (px1 + px2) // 2, py1 + int(pod_h * 0.46)
            gr = int(min(pod_w, pod_h) * 0.30)
            g_col = primary_c if pi == 0 else accent_c
            draw.arc([(gcx - gr, gcy - gr), (gcx + gr, gcy + gr)], start=150, end=390, fill=(228, 228, 231, 255), width=10)
            sweep_g = int(240 * min(1.0, max(0.25, choreo_u * 1.35)) * (0.95 if pi == 0 else 0.88))
            draw.arc([(gcx - gr, gcy - gr), (gcx + gr, gcy + gr)], start=150, end=150 + sweep_g, fill=(*g_col, 255), width=10)
            val_t = kpi_val if pi == 0 else "100%"
            lbl_t = kpi_lbl if pi == 0 else sub_items[0]
            draw_contained_arabic_text(draw, (gcx - gr + 8, gcy - 18, gcx + gr - 8, gcy + 18), val_t, initial_font_size=18, fill=(*dark_navy, 255))
            draw_contained_arabic_text(draw, (px1 + 10, py2 - 42, px2 - 10, py2 - 8), lbl_t, initial_font_size=14, fill=(100, 116, 139, 255))

        bot_y1 = st_y1 + pod_h + 24
        bot_h = st_y2 - bot_y1 - 8
        if choreo_u >= 0.24 and bot_h >= 48:
            img = _draw_soft_elevated_card(img, (st_x1, bot_y1, st_x2, bot_y1 + bot_h), radius=20, fill_rgba=(255, 255, 255, 253), shadow_offset_y=10, shadow_blur=12, shadow_alpha=40)
            draw = ImageDraw.Draw(img, "RGBA")
            draw_contained_arabic_text(draw, (st_x1 + 18, bot_y1 + 8, st_x2 - 18, bot_y1 + bot_h - 8), f"✔ {sub_items[1]}   •   ✔ {sub_items[2]}", initial_font_size=16, fill=(*dark_navy, 255))
        return img

    # =========================================================================
    # Archetype 16 [6944 Shot 7]: kinetic_quote_dm_finale (الخاتمة الحركية السريعة بالكلمة المفتاحية وعلامات التنصيص)
    # =========================================================================
    center_y = int(h * 0.46) + float_y
    q_sp = _staggered_spring(choreo_u, delay=0.04, duration=0.40, stiffness=210.0, damping=13.5)

    # علامات التنصيص الذهبية العملاقة (“ Keyword ” كما في اللقطة الختامية من 6944.mp4)
    card_w = int(st_w * 0.84 * max(0.75, q_sp))
    card_h = int(st_h * 0.34 * max(0.75, q_sp))
    qx1, qy1 = cx - card_w // 2, center_y - card_h // 2 - int(h * 0.05)
    qx2, qy2 = qx1 + card_w, qy1 + card_h

    img = _draw_soft_elevated_card(
        img, (qx1, qy1, qx2, qy2), radius=28,
        fill_rgba=(255, 255, 255, 252), shadow_offset_y=14, shadow_blur=18, shadow_alpha=45
    )
    draw = ImageDraw.Draw(img, "RGBA")

    quote_txt = f"“ {kpi_val} ”"
    draw_contained_arabic_text(
        draw, (qx1 + 20, qy1 + 14, qx2 - 20, qy1 + int(card_h * 0.62)),
        quote_txt, initial_font_size=max(32, int(h * 0.046)), fill=(*primary_c, 255)
    )
    draw_contained_arabic_text(
        draw, (qx1 + 24, qy1 + int(card_h * 0.60), qx2 - 24, qy2 - 12),
        concept_title, initial_font_size=max(18, int(h * 0.026)), fill=(*dark_navy, 255)
    )

    if choreo_u >= 0.30:
        cta_sp = _staggered_spring(choreo_u, delay=0.30, duration=0.38)
        btn_w = int(st_w * 0.78 * max(0.75, cta_sp))
        btn_h = max(48, int(h * 0.054))
        bx1 = cx - btn_w // 2
        by1 = qy2 + 24 + int(22 * (1.0 - cta_sp))
        bx2, by2 = bx1 + btn_w, by1 + btn_h
        draw.rounded_rectangle([(bx1, by1 + 5), (bx2, by2 + 5)], radius=btn_h // 2, fill=(24, 20, 16, 42))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=btn_h // 2, fill=(*dark_navy, 255))
        draw_contained_arabic_text(
            draw, (bx1 + 18, by1, bx2 - 18, by2),
            sub_items[0] if sub_items else kpi_lbl,
            initial_font_size=18, fill=(255, 255, 255, 255)
        )
        _draw_cursor_with_ripple(draw, (bx2 - 10, by2 + 36), (cx, (by1 + by2) // 2), choreo_u, accent_rgb=primary_c)

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
        style_mode = str(brand.get("style_mode") or scene_meta.get("style_mode") or "clean_saas_light")
        is_light = (style_mode == "clean_saas_light") or bool(brand.get("is_light_mode", True))
        logo_path = brand.get("logo_path") if brand.get("show_logo_watermark", True) else None
        logo_pos = str(brand.get("logo_position") or "top_right")
        return t_name, theme, is_light, logo_path, logo_pos

    spec = scene_meta.get("scene_style_spec")
    if isinstance(spec, dict) and isinstance(spec.get("palette"), dict):
        pal = spec["palette"]
        t_name = str(spec.get("style_family_id") or scene_meta.get("theme_name") or "studio_active")
        MOTION_THEMES[t_name] = pal
        is_light = bool(pal.get("is_light_bg", False))
        logo_path = scene_meta.get("brand_logo_path")
        logo_pos = str(scene_meta.get("brand_logo_position") or "top_right")
        return t_name, pal, is_light, logo_path, logo_pos

    t_name = str(scene_meta.get("theme_name") or "cyber_gold")
    theme = MOTION_THEMES.get(t_name, MOTION_THEMES["cyber_gold"])
    style_mode = str(scene_meta.get("style_mode") or "clean_saas_light")
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
    bg_col = (255, 255, 255, 230) if is_light else (12, 18, 34, 210)
    border_col = (*theme.get("primary", (217, 155, 28)), 200)
    draw.rounded_rectangle([(bx1, by1 + 2), (bx2, by2 + 2)], radius=max(12, box_h // 3), fill=(0, 0, 0, 40))
    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=max(12, box_h // 3), fill=bg_col, outline=border_col, width=1)
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
    primary_c = tuple(theme.get("primary", (217, 155, 28)))
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
# 10. تصيير مشهد موشن جرافيك كامل الشاشة بدون شبكة مربعات وبتزامن صوتي كامل
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
    if not isinstance(style_spec, dict) and isinstance(scene_meta.get("palette"), dict) and "style_family_id" in scene_meta:
        style_spec = scene_meta
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

    # 1. رندرة الخلفية السينمائية الموحدة والناعمة بدون أي شبكة مربعات
    img = _render_pro_stage_background(width, height, style_spec, step_num=step_num, global_t=global_t)

    # 2. رسم اللوقو المرفوع إن وجد
    img, _ = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=is_light_stage)

    # 3. رسم المسرح التفاعلي المتحرك بالتزامن مع الكلمات المنطوقة (Audio-Synced Progressive Choreography)
    img = _render_dynamic_archetype_stage(
        img=img,
        scene_meta=scene_meta,
        style_spec=style_spec,
        scene_progress=scene_progress,
        global_t=global_t,
        active_word_idx=active_word_idx,
        word_local_progress=word_local_progress,
        scene_words=scene_words
    )

    # 4. كابشن الكاريوكي السفلي بنظام الصفحات الثابتة غير المتكررة
    caption_theme = {
        "primary": tuple(pal.get("primary", (217, 155, 28))),
        "secondary": tuple(pal.get("sticker_bg", (234, 179, 8)))
    }
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.865),
        theme=caption_theme,
        active_word_idx=active_word_idx
    )

    return img


# ==============================================================================
# 11. محرك الانتقالات السينمائية السلسة المريحة للعين (15s Reference Smooth Transitions)
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
    return float(physics_ease_in_out_expo(max(0.0, min(1.0, float(u)))))


def render_one_take_camera_handoff(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str = "whip_pan_blur_left",
    prev_meta: Optional[Dict[str, Any]] = None,
    curr_meta: Optional[Dict[str, Any]] = None,
    stage_bbox: Optional[Tuple[int, int, int, int]] = None
) -> Image.Image:
    """
    ينفذ الانتقالات السلسة والمريحة للعين المستوحاة من الفيديو المرجعي 15s (6944.mp4):
    1. `whip_pan_blur_left` / `whip_left`: سحب أفقي سريع مع ضبابية حركة اتجاهية حقيقية (Directional Motion Blur).
    2. `whip_pan_blur_up` / `whip_up`: سحب عمودي انسيابي مع ضبابية حركة عمودية.
    3. `portal_zoom_morph` / `zoom_portal`: زوم داخلي ناعم مع تلاشي ضبابي مريح للعين (Cross-Zoom Morph).
    4. `cinema_cross_zoom`: انتقال سينمائي فائق النعومة بين فيديو المتحدث ومشاهد الموشن جرافيك الكاملة!
    """
    w, h = curr_img.size
    u = max(0.0, min(1.0, float(trans_progress)))
    p = _camera_curve(u)
    vel_bell = math.sin(u * math.pi)  # يبلغ ذروته في منتصف الانتقال (u=0.5) ويهبط للصفر عند الأطراف

    prev_rgba = prev_img.convert("RGBA")
    curr_rgba = curr_img.convert("RGBA")

    t_mode = str(transition_type or "whip_pan_blur_left").lower()

    if t_mode in ("whip_pan_blur_left", "whip_left"):
        out_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        dx_prev = -int(round(w * p))
        dx_curr = int(round(w * (1.0 - p)))
        out_canvas.paste(prev_rgba, (dx_prev, 0))
        out_canvas.paste(curr_rgba, (dx_curr, 0))
        if vel_bell > 0.18:
            out_canvas = apply_fast_directional_motion_blur(
                out_canvas, velocity_xy=(-420.0 * vel_bell, 0.0), max_kernel_size=11
            )
        return out_canvas

    if t_mode in ("whip_pan_blur_up", "whip_up"):
        out_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        dy_prev = -int(round(h * p))
        dy_curr = int(round(h * (1.0 - p)))
        out_canvas.paste(prev_rgba, (0, dy_prev))
        out_canvas.paste(curr_rgba, (0, dy_curr))
        if vel_bell > 0.18:
            out_canvas = apply_fast_directional_motion_blur(
                out_canvas, velocity_xy=(0.0, -420.0 * vel_bell), max_kernel_size=11
            )
        return out_canvas

    # Default / portal_zoom_morph / cinema_cross_zoom (تلاشي وزوم سينمائي ناعم جداً ومريح للعين)
    prev_scale = 1.0 + 0.14 * p
    pw, ph = int(round(w * prev_scale)), int(round(h * prev_scale))
    prev_zoomed = prev_rgba.resize((pw, ph), Image.Resampling.BILINEAR).crop(((pw - w) // 2, (ph - h) // 2, (pw - w) // 2 + w, (ph - h) // 2 + h))

    curr_scale = 0.88 + 0.12 * p
    cw, ch = max(16, int(round(w * curr_scale))), max(16, int(round(h * curr_scale)))
    curr_scaled = curr_rgba.resize((cw, ch), Image.Resampling.BILINEAR)
    curr_canvas = prev_zoomed.copy()
    curr_canvas.paste(curr_scaled, ((w - cw) // 2, (h - ch) // 2))

    blended = Image.blend(prev_zoomed, curr_canvas, p)
    if vel_bell > 0.25:
        blended = blended.filter(ImageFilter.GaussianBlur(radius=max(1, int(3.0 * vel_bell))))
    return blended


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
    كابشن كاريوكي بنظام الصفحات الثابتة غير المتداخلة (`Non-Overlapping 4-Word Pages`)
    مع كبسولة زجاجية أنيقة.
    """
    w, h = img.size
    cx = w // 2
    clean_sc_words = [re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(wd)).strip() for wd in sc_words if str(wd).strip()]
    clean_act_word = re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(act_word)).strip() if act_word else (clean_sc_words[0] if clean_sc_words else "")

    if not clean_sc_words and not clean_act_word:
        return

    font_size = max(24, int(min(w, h) * 0.038))
    cap_font = get_arabic_font(font_size, bold=True)
    pop_scale = _spring_physics(min(1.0, w_prog * 2.5), stiffness=230.0, damping=14.0)
    active_font = get_arabic_font(int(font_size * (1.0 + 0.07 * pop_scale)), bold=True)

    if active_word_idx is not None and 0 <= int(active_word_idx) < len(clean_sc_words):
        target_idx = int(active_word_idx)
    else:
        active_word_clean = clean_act_word.lower()
        target_idx = 0
        for wi, cw in enumerate(clean_sc_words):
            if cw.lower() == active_word_clean:
                target_idx = wi
                break

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
    word_spaces = int(font_size * 0.42)
    for wi, dw in enumerate(display_words):
        f_use = active_font if wi == disp_active_idx else cap_font
        ww, wh = measure_arabic_text(draw, dw, f_use)
        if wi == disp_active_idx:
            ww += 14
        word_widths.append((ww, wh))

    total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces
    if total_line_w > int(w * 0.82):
        scale_down = (w * 0.80) / float(total_line_w)
        font_size = max(18, int(font_size * scale_down))
        cap_font = get_arabic_font(font_size, bold=True)
        active_font = get_arabic_font(int(font_size * (1.0 + 0.07 * pop_scale)), bold=True)
        word_spaces = int(font_size * 0.38)
        word_widths = []
        for wi, dw in enumerate(display_words):
            f_use = active_font if wi == disp_active_idx else cap_font
            ww, wh = measure_arabic_text(draw, dw, f_use)
            if wi == disp_active_idx:
                ww += 12
            word_widths.append((ww, wh))
        total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces

    max_line_h = max(wh for _, wh in word_widths) if word_widths else font_size

    box_pad_x = int(font_size * 0.60)
    box_pad_y = int(font_size * 0.32)
    bar_x1 = max(int(w * 0.04), cx - total_line_w // 2 - box_pad_x)
    bar_x2 = min(int(w * 0.96), cx + total_line_w // 2 + box_pad_x)
    bar_y1 = cap_y - max_line_h // 2 - box_pad_y
    bar_y2 = cap_y + max_line_h // 2 + box_pad_y

    p_col = tuple(theme.get("primary", (217, 155, 28)))
    draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(bar_x1, bar_y1, bar_x2, bar_y2),
        radius=18,
        tint_color=(16, 18, 26, 232),
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
            hl_pad_x, hl_pad_y = 8, 6
            draw.rounded_rectangle(
                [(word_cx - ww // 2 - hl_pad_x, cap_y - wh // 2 - hl_pad_y),
                 (word_cx + ww // 2 + hl_pad_x, cap_y + wh // 2 + hl_pad_y)],
                radius=10,
                fill=(*p_col, 255)
            )
            txt_fill = (24, 24, 27, 255) if sum(p_col) > 480 else (255, 255, 255, 255)
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=active_font,
                fill=txt_fill
            )
        else:
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=cap_font,
                fill=(248, 250, 252, 245),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 225)
            )

        cur_right_x -= (ww + word_spaces)


# ==============================================================================
# 12. تصيير إطار الفيديو الشامل مع شاشات موشن جرافيك كاملة (Full-Screen Motion Cutaways)
#     وانتقالات سلسة بين الفيديو الحقيقي وشاشة الموشن جرافيك الكاملة!
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
    sc["_live_speaker_frame"] = base_frame_rgb
    layout_mode = sc.get("layout_mode", "speaker_clean")
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

    time_into_scene = t - sc["start"]
    handoff_dur = float(sc.get("handoff_duration_sec", 0.34))
    trans_modes = ["whip_pan_blur_left", "portal_zoom_morph", "whip_pan_blur_up", "cinema_cross_zoom"]
    active_trans_mode = sc.get("transition_type") or trans_modes[active_idx % len(trans_modes)]

    # 1. إذا كان المشهد الحالي هو شاشة موشن جرافيك كاملة (Full-Screen Motion Cutaway) تشرح فكرة/معلومة مهمة:
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
        if active_idx > 0 and 0.0 <= time_into_scene < handoff_dur:
            prev_sc = master_plan[active_idx - 1]
            prev_sc["_live_speaker_frame"] = base_frame_rgb
            if prev_sc.get("layout_mode") == "full_screen":
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
                    transition_type=active_trans_mode,
                    prev_meta=prev_sc,
                    curr_meta=sc
                )
            else:
                # انتقال سلس ومريح للعين من فيديو المتحدث إلى شاشة الموشن جرافيك الكاملة!
                spk_pil = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
                blended = render_one_take_camera_handoff(
                    prev_img=spk_pil,
                    curr_img=curr_img,
                    trans_progress=time_into_scene / handoff_dur,
                    transition_type="cinema_cross_zoom",
                    prev_meta=prev_sc,
                    curr_meta=sc
                )
            return np.array(blended.convert("RGB"))
        return np.array(curr_img.convert("RGB"))

    # 2. إذا كان المشهد الحالي هو فيديو المتحدث (مع انتقال سلس عند العودة من شاشة الموشن جرافيك الكاملة!)
    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    img, logo_bbox = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=False)
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2
    step_num = int(sc.get("step_number") or (active_idx + 1))

    if layout_mode == "top_overlay":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        y_slide_offset = int(-80 * (1.0 - spring_in))

        badge_title = sc.get("concept_title") or sc.get("badge_label", "ميزة حصرية")
        pill_h = max(46, int(h * 0.050))
        max_pill_w = int(w * 0.84)
        _, _, tw, _ = fit_and_condense_arabic_text(
            draw, badge_title, max_width=max_pill_w - 40,
            initial_font_size=max(18, int(min(w, h) * 0.028)), min_font_size=11, bold=True
        )
        pill_w = min(max_pill_w, max(tw + 44, int(w * 0.40)))
        top_y = (int(h * 0.090) if logo_bbox is not None else int(h * 0.042)) + y_slide_offset
        x1, y1 = cx - pill_w // 2, top_y
        x2, y2 = cx + pill_w // 2, top_y + pill_h

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(x1, y1, x2, y2),
            radius=pill_h // 2,
            tint_color=(14, 18, 28, 218),
            border_color=theme["primary"],
            secondary_color=theme["secondary"],
            blur_radius=12,
            shadow_offset=8,
            shadow_blur=14,
            light_sweep_prog=(sc_prog * 1.4 - 0.1)
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(
            draw, (x1 + 14, y1, x2 - 14, y2),
            badge_title, initial_font_size=max(18, int(min(w, h) * 0.028)),
            fill=(255, 255, 255, 250), pad_left=12, pad_right=12, min_font_size=11,
            stroke_width=2, stroke_fill=(0, 0, 0, 210)
        )

    elif layout_mode == "lower_third":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        l3_txt = sc.get("badge_label", "ميزة حصرية")
        bar_h = max(46, int(h * 0.050))
        max_bar_w = int(w * 0.86)
        _, _, tw, _ = fit_and_condense_arabic_text(
            draw, l3_txt, max_width=max_bar_w - 40,
            initial_font_size=max(18, int(min(w, h) * 0.028)), min_font_size=11, bold=True
        )
        bar_w = min(max_bar_w, max(int(w * 0.44), tw + 44))
        by1 = int(h * 0.86 + 60 * (1.0 - spring_in))
        by2 = by1 + bar_h
        bx1 = cx - bar_w // 2
        bx2 = cx + bar_w // 2

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=bar_h // 2,
            tint_color=(14, 18, 28, 228),
            border_color=theme["primary"],
            blur_radius=12,
            shadow_offset=8,
            shadow_blur=14,
            light_sweep_prog=(sc_prog * 1.4)
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(
            draw, (bx1, by1, bx2, by2),
            l3_txt, initial_font_size=max(18, int(min(w, h) * 0.028)),
            fill=(255, 255, 255, 255), pad_left=16, pad_right=16, min_font_size=11,
            stroke_width=2, stroke_fill=(0, 0, 0, 225)
        )

    if caption_mode != "none" and (act_word or sc_words):
        if caption_mode == "top_compact":
            cap_y = int(h * 0.14)
        elif layout_mode == "lower_third":
            cap_y = int(h * 0.77)
        else:
            cap_y = int(h * 0.855)

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

    # إذا كان المشهد السابق عبارة عن شاشة موشن جرافيك كاملة (full_screen)، ننفذ انتقالاً سينمائياً سلساً بالعودة إلى فيديو المتحدث!
    if active_idx > 0 and 0.0 <= time_into_scene < handoff_dur:
        prev_sc = master_plan[active_idx - 1]
        if prev_sc.get("layout_mode") == "full_screen":
            prev_sc["_live_speaker_frame"] = base_frame_rgb
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
            img = render_one_take_camera_handoff(
                prev_img=prev_img,
                curr_img=img,
                trans_progress=time_into_scene / handoff_dur,
                transition_type="cinema_cross_zoom",
                prev_meta=prev_sc,
                curr_meta=sc
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

        update_progress(0.30, "2/4: تفريغ الكلام وبناء مشاهد الموشن جرافيك السريعة (2.2s - 3.2s للمشهد)...")
        words = transcribe_audio(
            audio_path=clean_media,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        retake_cuts = get_last_detected_retake_cuts()
        if retake_cuts:
            clean_media, total_dur = prune_retake_cuts_from_media(clean_media, retake_cuts, total_dur)
            words = remap_words_after_retake_cuts(words, retake_cuts)

        semantic_clauses = split_words_into_micro_scenes(
            words,
            max_words_per_scene=6,
            max_duration_per_scene=3.1,
            min_words_per_scene=3
        )
        full_transcript = " ".join(w.get("word", "") for w in words)

        custom_planned_scenes = kwargs.get("custom_planned_scenes")
        if isinstance(custom_planned_scenes, list) and len(custom_planned_scenes) > 0:
            planned_scenes = custom_planned_scenes
        else:
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

        update_progress(0.55, "3/4: تصيير مشاهد الموشن جرافيك ثلاثية الأبعاد بانتقالات 15s السلسة...")
        trans_cycle = ["whip_pan_blur_left", "portal_zoom_morph", "whip_pan_blur_up", "cinema_cross_zoom"]

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
            handoff_dur = float(sc.get("handoff_duration_sec", 0.32))
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
                t_mode = trans_cycle[active_idx % len(trans_cycle)]
                curr_img = render_one_take_camera_handoff(
                    prev_img=prev_img,
                    curr_img=curr_img,
                    trans_progress=time_into / handoff_dur,
                    transition_type=t_mode,
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

        # المرحلة 5 (بعد انتهاء الموشن جرافيك بالكامل): دور مصمم الساوند ديزاين الآلي (sound_designer.py)
        sfx_cues_list = []
        try:
            from sound_designer import apply_intelligent_sound_design_to_video, LAST_SESSION_PATH
            update_progress(0.96, "🔊 جاري تصميم ومزج المؤثرات الصوتية (Whoosh, Riser, UI Pop, Click, Button) في الثانية المناسبة...")
            output_path, sfx_rep = apply_intelligent_sound_design_to_video(
                video_path=output_path,
                planned_scenes=planned_scenes,
                total_duration=total_dur,
                output_path=output_path,
                custom_cues=kwargs.get("custom_sfx_cues")
            )
            sfx_cnt = sfx_rep.get("cues_count", 0)
            sfx_cues_list = sfx_rep.get("cues", [])
            try:
                serializable_scenes = []
                for idx_s, sc_item in enumerate(planned_scenes):
                    sc_clean = {k: v for k, v in sc_item.items() if not str(k).startswith("_") and k != "words"}
                    sc_clean["scene_index"] = idx_s
                    serializable_scenes.append(sc_clean)
                session_payload = {
                    "mode": "audio_motion",
                    "input_path": input_path,
                    "output_path": output_path,
                    "total_duration": total_dur,
                    "resolution": [vw, vh],
                    "whisper_model": whisper_model,
                    "dialect_mode": dialect_mode,
                    "planned_scenes": serializable_scenes,
                    "sfx_cues": sfx_cues_list,
                }
                os.makedirs(os.path.dirname(os.path.abspath(LAST_SESSION_PATH)), exist_ok=True)
                with open(LAST_SESSION_PATH, "w", encoding="utf-8") as sf:
                    json.dump(session_payload, sf, ensure_ascii=False, indent=2)
            except Exception as sess_err:
                logger.debug(f"Session save notice: {sess_err}")
            update_progress(1.0, f"اكتمل تصيير الموشن جرافيك ومزج {sfx_cnt} مؤثر صوتي احترافي بنجاح!")
        except Exception as sfx_err:
            logger.warning(f"ملاحظة في مرحلة الساوند ديزاين: {sfx_err}")
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