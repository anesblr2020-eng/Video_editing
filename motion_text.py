"""
motion_text.py - محرك الموشن جرافيك الاحترافي متعدد الستايلات ومستنسخ الفيديوهات المرجعية (Studio Multi-Style & Reference Cloner Engine)
===========================================================================================================================================
يجمع هذا المحرك بين أرقى تقنيات الموشن جرافيك الاحترافية (بمستوى الفيديوهات المرجعية `6873.mp4` و `6842.mp4` و `6871.mp4`):
1. محرك وكالة BYW الاحترافي (`byw_cyan_agency` - مستوحى من `6873.mp4`):
   - خلفيات شبكية متدرجة تتغير ديناميكياً عبر فصول الفيديو (كحلي داكن للمشكلة -> سيان مشرق للخطوات 01..04 -> أبيض ثلجي للخاتمة).
   - أشكال معينية طافية (`◇`) وأرقام خلفية عملاقة مفرغة (`01`, `02`, `03`, `04`, `دج`).
   - شارة خطوات علوية (`01 • • •`) وعناوين بارزة بستيكر خلفي ملون للكلمة المفتاحية (`راك [تصرف] على الإشهار`، `[نحللو]`، `ونتابعو [النتائج]`).
   - 5 بطاقات وكالة بيضاء مائلة ومتنوعة (فاتورة مشرشرة مع ختم `النتيجة: 0`، مخطط خطوات متصل `01->02->03`، عدسة مكبرة فاحصة `🔍`، رادار الجمهور المستهدف `◎`، وتقرير الأداء على الهاتف `تقرير الأداء 72%`).
2. محرك المخطط الهندسي والخطوات المرقمة (`mazen_blueprint_collage` - مستوحى من `6842.mp4`):
   - خلفية مخطط هندسي سماوي (`Blueprint Grid`) مع علامات ترقيم عملاقة مائية (`!`, `?`).
   - إطار تحديد تفاعلي بـ 8 مقابض تحجيم ومؤشر ماوس متحرك (`Selection Box + Cursor`).
   - قائمة خطوات مرقمة بدوائر زرقاء بارزة (`1`, `2`, `3`, `4`) تنبثق بالتتابع بفيزياء النوابض.
3. محرك مختبر الإعلانات الفاخر (`baghdadi_luxury_plum` - مستوحى من `6871.mp4`):
   - خلفية بنفسجية داكنة فاخرة (`Obsidian Plum`) مع شريط تبويبات علوي مقسم (`[ المشكلة ] [ الحل ] [ النتيجة ]` / `AIDA • PAS • BAB`).
   - شارة حرف متوهجة (`[A]`, `[P]`, `[S]`) وبطاقات مقارنة مزدوجة (`قبل / بعد`) وكابشن سفلي داكن أنيق.
4. محرك التنويع التلقائي للستايلات (`auto_vary_pro`) واستنساخ أي فيديو مرجعي (`clone_reference`) مع الحفاظ التام على الفيديو الأصلي بملء الشاشة 100% في وضع المتحدث.
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
    get_active_brand_theme,
    PRO_STUDIO_STYLE_FAMILIES,
    build_dynamic_scene_style_assignment
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
        "top_bg": (11, 24, 31),
        "bottom_bg": (16, 38, 48),
        "glow": (27, 174, 202),
        "primary": (27, 174, 202),
        "secondary": (250, 204, 21),
        "accent": (99, 102, 241),
        "card_bg": (255, 255, 255)
    },
    "neon_emerald": {
        "top_bg": (9, 26, 22),
        "bottom_bg": (14, 42, 35),
        "glow": (16, 185, 129),
        "primary": (16, 185, 129),
        "secondary": (250, 204, 21),
        "accent": (56, 189, 248),
        "card_bg": (255, 255, 255)
    },
    "royal_purple": {
        "top_bg": (20, 18, 39),
        "bottom_bg": (41, 28, 69),
        "glow": (139, 92, 246),
        "primary": (139, 92, 246),
        "secondary": (216, 180, 254),
        "accent": (250, 204, 21),
        "card_bg": (32, 25, 56)
    },
    "crimson_energy": {
        "top_bg": (26, 14, 22),
        "bottom_bg": (48, 20, 36),
        "glow": (244, 63, 94),
        "primary": (244, 63, 94),
        "secondary": (251, 191, 36),
        "accent": (0, 245, 212),
        "card_bg": (255, 255, 255)
    },
    "electric_cobalt": {
        "top_bg": (27, 174, 202),
        "bottom_bg": (8, 109, 133),
        "glow": (255, 255, 255),
        "primary": (11, 24, 31),
        "secondary": (27, 174, 202),
        "accent": (16, 185, 129),
        "card_bg": (255, 255, 255)
    },
    "sunset_violet": {
        "top_bg": (147, 201, 242),
        "bottom_bg": (198, 226, 248),
        "glow": (2, 132, 199),
        "primary": (2, 132, 199),
        "secondary": (30, 58, 138),
        "accent": (45, 212, 191),
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


def _spring_physics(t: float, stiffness: float = 185.0, damping: float = 13.0, mass: float = 1.0) -> float:
    return float(spring_damper(t, stiffness=stiffness, damping=damping, mass=mass))


def _staggered_spring(global_prog: float, delay: float = 0.0, duration: float = 0.42, stiffness: float = 185.0, damping: float = 13.0) -> float:
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
# 5. محرك الشيدر والزجاج الحقيقي والبطاقات المائلة (VisionOS Glass & Tilted Agency Cards)
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
        s_draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=(0, 0, 0, 115))
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
        ], fill=(255, 255, 255, 28))

    frosted = Image.alpha_composite(frosted, sheen)

    mask = Image.new("L", (pw, ph), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([(0, 0), (pw - 1, ph - 1)], radius=radius, fill=255)
    canvas_rgba.paste(frosted, (x1, y1), mask)

    c_draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    c_draw.rounded_rectangle([(x1, y1), (x2 - 1, y2 - 1)], radius=radius, outline=(*border_color, 225), width=2)
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

    s_main = 0.80 + 0.20 * _staggered_spring(scene_progress, delay=0.0, duration=0.42)
    s_sub1 = 0.74 + 0.26 * _staggered_spring(scene_progress, delay=0.05, duration=0.45)

    rad_glow = cairo.RadialGradient(cx, cy, r * 0.05, cx, cy, r * 1.1)
    rad_glow.add_color_stop_rgba(0.0, p1[0], p1[1], p1[2], 0.25 * s_main)
    rad_glow.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
    ctx.set_source(rad_glow)
    ctx.arc(cx, cy, r * 1.1, 0, 2 * math.pi)
    ctx.fill()

    if scene_type in ("growth_analytics", "ecommerce_showcase"):
        # رسم أبراج العملات ثلاثية الأبعاد مع السهم الصاعد (مطابق لفيديو 6873)
        stack_xs = [cx - r * 0.56, cx, cx + r * 0.56]
        stack_counts = [4, 6, 3]
        coin_rx = r * 0.23 * s_main
        coin_ry = r * 0.075 * s_main
        base_y = cy + r * 0.52

        for sx, cnt in zip(stack_xs, stack_counts):
            for ci in range(cnt):
                cy_c = base_y - ci * (coin_ry * 1.55)
                ctx.save()
                ctx.translate(sx, cy_c)
                ctx.scale(coin_rx, coin_ry)
                ctx.arc(0, 0, 1.0, 0, 2 * math.pi)
                ctx.restore()
                ctx.set_source_rgba(0.11, 0.68, 0.79, 0.96)
                ctx.fill_preserve()
                ctx.set_source_rgba(1.0, 1.0, 1.0, 0.90)
                ctx.set_line_width(2.0)
                ctx.stroke()

        # السهم الصاعد فوق الأبراج مع علامة الصح
        top_y = base_y - 6 * (coin_ry * 1.55) - r * 0.38 * s_sub1
        ctx.move_to(cx, base_y - 3 * coin_ry)
        ctx.line_to(cx, top_y)
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        ctx.set_line_width(5.0)
        ctx.stroke()

        ctx.move_to(cx - 12, top_y + 14)
        ctx.line_to(cx, top_y - 2)
        ctx.line_to(cx + 12, top_y + 14)
        ctx.set_line_width(4.5)
        ctx.stroke()

        ctx.arc(cx, (base_y - 3 * coin_ry + top_y) * 0.5, r * 0.16, 0, 2 * math.pi)
        ctx.set_source_rgba(0.11, 0.68, 0.79, 1.0)
        ctx.fill_preserve()
        ctx.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        ctx.set_line_width(3.0)
        ctx.stroke()

    elif scene_type in ("delivery_express", "cta_tap", "brand_finale"):
        # صاروخ الإطلاق أو سحابة النمو الصاعدة (مطابق لفيديو 6873 المشهد 03 والختام)
        ry = cy - 8 * math.sin(global_t * 4.0)
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
        ctx.set_source_rgba(0.11, 0.68, 0.79, 1.0)
        ctx.fill()

        # شعلة الانطلاق
        flame_h = r * (0.28 + 0.08 * math.sin(global_t * 8.0))
        ctx.move_to(cx - rw * 0.25, ry + rh * 0.45)
        ctx.line_to(cx, ry + rh * 0.45 + flame_h)
        ctx.line_to(cx + rw * 0.25, ry + rh * 0.45)
        ctx.close_path()
        ctx.set_source_rgba(0.11, 0.78, 0.92, 0.90)
        ctx.fill()
    else:
        # العدسة الذكية / الدرع الاحترافي
        cr = r * 0.64 * s_main
        ctx.arc(cx, cy, cr, 0, 2 * math.pi)
        ctx.set_source_rgba(0.08, 0.14, 0.24, 0.92)
        ctx.fill_preserve()
        ctx.set_source_rgba(p1[0], p1[1], p1[2], 0.95)
        ctx.set_line_width(4.0)
        ctx.stroke()

        # أعمدة نمو داخل الدائرة
        for bi, bh in enumerate([0.32, 0.52, 0.78]):
            bx = cx - cr * 0.42 + bi * (cr * 0.32)
            bw = cr * 0.20
            by_h = cr * bh * s_sub1
            _cairo_rounded_rect(ctx, bx, cy + cr * 0.35 - by_h, bw, by_h, 4)
            ctx.set_source_rgba(0.11, 0.68, 0.79 if bi < 2 else 1.0, 0.95)
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
# 7. بناء الخلفيات الشبكية والهندسية المستنسخة من 6873 و 6842 و 6871
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
    يبني خلفية المسرح الاحترافية المطابقة للفيديوهات المرجعية (`6873.mp4`, `6842.mp4`, `6871.mp4`):
    - تدرج لوني ناعم (`top_bg -> bottom_bg`) مع شبكة هندسية (`Engineering Blueprint Grid`).
    - أشكال معينية طافية (`◇`) ومربعات ضوئية ناعمة (كما في `6873.mp4`).
    - رقم الخلفية العملاق المفرغ (`01`, `02`, `03`, `04`) في الثلث السفلي (كما في `6873.mp4`) أو علامة الترقيم المائية العملاقة (`!`, `?` كما في `6842.mp4`).
    """
    pal = style_spec.get("palette", {})
    top_c = np.array(pal.get("top_bg", (27, 174, 202)), dtype=np.float32)
    bot_c = np.array(pal.get("bottom_bg", (8, 109, 133)), dtype=np.float32)
    glow_c = np.array(pal.get("glow", (255, 255, 255)), dtype=np.float32)
    is_light = bool(pal.get("is_light_bg", False))
    design_family = str(style_spec.get("design_family", "byw_cyan_agency"))

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    yy, xx = np.ogrid[:height, :width]
    cx1, cy1 = width * 0.5, height * 0.45
    dist1 = ((xx - cx1) / (width * 0.52)) ** 2 + ((yy - cy1) / (height * 0.36)) ** 2
    glow_strength = 0.26 if design_family == "baghdadi_luxury_plum" else 0.16
    mask1 = np.exp(-dist1 * 2.1)[:, :, None] * glow_strength
    canvas_np = np.clip(canvas_np * (1.0 - mask1) + glow_c * mask1, 0, 255).astype(np.uint8)

    img = Image.fromarray(canvas_np, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    # 1. الشبكة الهندسية الدقيقة (Engineering Grid في 6873 و 6842)
    if style_spec.get("has_grid", True):
        grid_step = max(44, min(width, height) // 11)
        grid_col = (15, 23, 42, 16) if is_light else (255, 255, 255, 22)
        for gx in range(0, width, grid_step):
            draw.line([(gx, 0), (gx, height)], fill=grid_col, width=1)
        for gy in range(0, height, grid_step):
            draw.line([(0, gy), (width, gy)], fill=grid_col, width=1)

    # 2. المعينات الهندسية الطافية (Floating Diamonds `◇` في 6873)
    if style_spec.get("has_floating_diamonds", True):
        d_col = (27, 174, 202, 55) if is_light else (255, 255, 255, 55)
        diamond_positions = [
            (int(width * 0.14), int(height * 0.12), 11),
            (int(width * 0.86), int(height * 0.09), 13),
            (int(width * 0.10), int(height * 0.48), 10),
            (int(width * 0.89), int(height * 0.54), 12),
            (int(width * 0.22), int(height * 0.72), 9),
            (int(width * 0.80), int(height * 0.75), 11),
        ]
        for idx_d, (dx, dy_base, ds) in enumerate(diamond_positions):
            dy = dy_base + int(6 * math.sin(global_t * 2.2 + idx_d * 1.1))
            pts = [(dx, dy - ds), (dx + ds, dy), (dx, dy + ds), (dx - ds, dy)]
            if idx_d % 2 == 0:
                draw.polygon(pts, outline=d_col, width=2)
            else:
                draw.polygon(pts, fill=(d_col[0], d_col[1], d_col[2], 32))

    # 3. الرقم المائي العملاق المفرغ أسفل الخلفية (`01`, `02`, `03`, `04` في 6873) أو علامة الترقيم (`?`, `!` في 6842)
    if design_family == "byw_cyan_agency" and style_spec.get("has_giant_bg_numbers", True):
        act_name = str(style_spec.get("act_name", "body_steps"))
        if act_name != "outro_finale":
            big_font = get_arabic_font(int(height * 0.22), bold=True)
            watermark_str = f"{step_num:02d}"
            wm_col = (255, 255, 255, 36) if not is_light else (11, 24, 31, 22)
            draw_arabic_text(
                draw, (width // 2, int(height * 0.74)),
                watermark_str, font=big_font,
                fill=(255, 255, 255, 8),
                stroke_width=3, stroke_fill=wm_col
            )
    elif design_family == "mazen_blueprint_collage":
        big_font = get_arabic_font(int(height * 0.20), bold=True)
        mark_char = "?" if (step_num % 2 == 0) else "!"
        mark_x = int(width * 0.82) if (step_num % 2 == 0) else int(width * 0.18)
        draw_arabic_text(
            draw, (mark_x, int(height * 0.12)),
            mark_char, font=big_font,
            fill=(255, 255, 255, 195),
            stroke_width=3, stroke_fill=(2, 132, 199, 55)
        )

    return img


# ==============================================================================
# 8. محرك العناوين ذات الستيكر الملون للكلمة المفتاحية (Sticker-Highlighted Headline - 6873)
# ==============================================================================
def _draw_sticker_highlighted_headline(
    draw: ImageDraw.ImageDraw,
    bbox: Tuple[int, int, int, int],
    headline_text: str,
    highlight_word: str = "",
    headline_txt_color: Tuple[int, int, int] = (255, 255, 255),
    sticker_bg_color: Tuple[int, int, int] = (255, 255, 255),
    sticker_txt_color: Tuple[int, int, int] = (11, 24, 31),
    initial_font_size: int = 34,
    scene_progress: float = 1.0
):
    """
    يرسم العنوان الاحترافي على سطر أو سطرين مع وضع الكلمة المفتاحية داخل مستطيل ستيكر ملون بارز
    (مطابق تماماً لأسلوب `6873.mp4`: `راك [تصرف] على الإشهار`، `راه في [الطريقة]`، `[نحللو]`، `ونتابعو [النتائج] خطوة بخطوة`).
    """
    x1, y1, x2, y2 = bbox
    max_w = max(80, x2 - x1 - 24)
    cx = (x1 + x2) // 2

    words = [w.strip() for w in str(headline_text or "").split() if w.strip()]
    if not words:
        return

    # تحديد الكلمة الأهم لتمييزها بالستيكر إن لم تُحدد مسبقاً
    hl_clean = re.sub(r"[،,.!؟?:•]", "", str(highlight_word or "")).strip()
    target_w_idx = -1
    if hl_clean:
        for i, w in enumerate(words):
            if hl_clean in re.sub(r"[،,.!؟?:•]", "", w):
                target_w_idx = i
                break
    if target_w_idx < 0:
        # نختار أطول كلمة دلالية في النصف الأول من العنوان
        best_len = -1
        for i, w in enumerate(words[:min(4, len(words))]):
            wc = re.sub(r"[،,.!؟?:•]", "", w)
            if len(wc) > best_len and wc not in ("في", "من", "على", "مع", "أو", "كل", "هذا", "هذه"):
                best_len = len(wc)
                target_w_idx = i
        if target_w_idx < 0:
            target_w_idx = 0

    # تقسيم الكلمات إلى سطر واحد أو سطرين متوازنين
    if len(words) <= 3:
        lines = [(words, target_w_idx)]
    else:
        mid = max(2, (len(words) + 1) // 2)
        line1 = words[:mid]
        line2 = words[mid:]
        hl1 = target_w_idx if target_w_idx < mid else -1
        hl2 = (target_w_idx - mid) if target_w_idx >= mid else -1
        lines = [(line1, hl1), (line2, hl2)]

    line_count = len(lines)
    avail_h = max(44, y2 - y1)
    line_step_h = min(int(initial_font_size * 1.48), avail_h // max(1, line_count))
    start_cy = (y1 + y2) // 2 - ((line_count - 1) * line_step_h) // 2

    sticker_pop = 0.88 + 0.12 * _staggered_spring(scene_progress, delay=0.06, duration=0.38)

    for l_idx, (l_words, hl_pos) in enumerate(lines):
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
                ww += int(f_sz * 0.65)
            measured.append((w_str, ww, wh, wi == hl_pos))

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
                    ww += int(new_sz * 0.58)
                measured.append((w_str, ww, wh, wi == hl_pos))
            total_lw = sum(m[1] for m in measured) + max(0, len(measured) - 1) * space_w

        cur_right = cx + total_lw // 2
        line_cy = start_cy + l_idx * line_step_h

        for w_str, ww, wh, is_hl in measured:
            w_cx = cur_right - ww // 2
            if is_hl:
                pad_y = max(6, int(wh * 0.24 * sticker_pop))
                rx1 = int(w_cx - (ww * sticker_pop) / 2)
                rx2 = int(w_cx + (ww * sticker_pop) / 2)
                ry1 = int(line_cy - wh // 2 - pad_y)
                ry2 = int(line_cy + wh // 2 + pad_y)
                draw.rounded_rectangle([(rx1, ry1 + 3), (rx2, ry2 + 3)], radius=12, fill=(0, 0, 0, 55))
                draw.rounded_rectangle([(rx1, ry1), (rx2, ry2)], radius=12, fill=(*sticker_bg_color, 255))
                draw_arabic_text(draw, (w_cx, line_cy), w_str, font=f_obj, fill=(*sticker_txt_color, 255))
            else:
                stroke_c = (0, 0, 0, 145) if sum(headline_txt_color) > 400 else (255, 255, 255, 0)
                stroke_w = 2 if sum(headline_txt_color) > 400 else 0
                draw_arabic_text(
                    draw, (w_cx, line_cy), w_str, font=f_obj,
                    fill=(*headline_txt_color, 255), stroke_width=stroke_w, stroke_fill=stroke_c
                )
            cur_right -= (ww + space_w)


# ==============================================================================
# 9. المحركات الثلاثة لرندرة المشاهد الكاملة المطابقة لـ 6873 و 6842 و 6871
# ==============================================================================
def _draw_checkmark_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color_rgb: Tuple[int, int, int] = (16, 185, 129), scale: float = 1.0):
    r = max(8, int(radius * scale))
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(*color_rgb, 255), outline=(255, 255, 255, 230), width=2)
    draw.line([(cx - int(r * 0.42), cy + int(r * 0.05)), (cx - int(r * 0.10), cy + int(r * 0.38)), (cx + int(r * 0.46), cy - int(r * 0.32))], fill=(255, 255, 255, 255), width=max(2, int(r * 0.22)))


def _draw_cursor_with_ripple(
    draw: ImageDraw.ImageDraw,
    start_xy: Tuple[int, int],
    target_xy: Tuple[int, int],
    prog: float,
    accent_rgb: Tuple[int, int, int] = (37, 99, 235)
):
    move_p = _ease_out_cubic(max(0.0, min(1.0, (prog - 0.15) / 0.45)))
    cx = int(start_xy[0] + (target_xy[0] - start_xy[0]) * move_p)
    cy = int(start_xy[1] + (target_xy[1] - start_xy[1]) * move_p)

    click_scale = 1.0
    if prog > 0.62:
        ripple_p = min(1.0, (prog - 0.62) / 0.35)
        click_scale = 1.0 - 0.16 * math.sin(min(1.0, ripple_p * 2.0) * math.pi)
        for ri in range(2):
            rp = max(0.0, min(1.0, ripple_p - ri * 0.18))
            if rp > 0.0:
                rr = int(8 + 32 * rp)
                ra = int(175 * (1.0 - rp))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*accent_rgb, ra), width=2)

    s = max(13, int(19 * click_scale))
    pts = [
        (cx, cy),
        (cx, cy + int(s * 1.35)),
        (cx + int(s * 0.38), cy + int(s * 1.02)),
        (cx + int(s * 0.68), cy + int(s * 1.55)),
        (cx + int(s * 0.90), cy + int(s * 1.42)),
        (cx + int(s * 0.58), cy + int(s * 0.90)),
        (cx + int(s * 1.05), cy + int(s * 0.85))
    ]
    draw.polygon([(px + 2, py + 3) for px, py in pts], fill=(0, 0, 0, 120))
    draw.polygon(pts, fill=(255, 255, 255, 255), outline=(17, 24, 39, 255))


def _render_byw_agency_stage_6873(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float
) -> Image.Image:
    """
    يرسم مشهد وكالة BYW الاحترافي المطابق تماماً لفيديو `6873.mp4`:
    1. شارة الخطوات العلوية (`[ (01) ● ● ● ]`).
    2. العنوان الرئيسي الكبير المزود بـ ستيكر الكلمة المفتاحية (`Sticker-Highlighted Headline`).
    3. البطاقات البيضاء المائلة المتنوعة (5 بطاقات مختلفة تتبدل حسب المشهد لكي لا يتكرر نفس الكادر أبداً):
       - الفاتورة المشرشرة مع ختم النتيجة (`receipt_stamp`)
       - مخطط الخطوات المتصل 01->02->03 (`step_nodes_graph`)
       - بطاقة العدسة المكبرة الفاحصة (`magnifier_browser_card`)
       - رادار الجمهور المستهدف (`radar_target_circle`)
       - تقرير الأداء على الهاتف الذكي (`mobile_performance_report`) أو شاشة الختام البيضاء مع أعمدة النمو الصاعدة (`outro_finale`).
    """
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img, "RGBA")
    pal = style_spec.get("palette", {})
    act_name = str(style_spec.get("act_name", "body_steps"))
    step_num = int(scene_meta.get("step_number") or style_spec.get("step_number") or 1)
    card_variant = int(style_spec.get("card_variant_index", step_num % 5))

    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "خطوة استراتيجية ذكية")
    kpi_val = str(scene_meta.get("kpi_value") or "نتائج مضمونة")
    kpi_lbl = str(scene_meta.get("kpi_label") or "أداء احترافي")
    sub_items = [re.sub(r"^\d+[\.\-\s]+", "", str(s)).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    if len(sub_items) < 3:
        sub_items = [kpi_lbl, concept_title, kpi_val]

    headline_txt_c = tuple(pal.get("headline_txt", (255, 255, 255)))
    sticker_bg_c = tuple(pal.get("sticker_bg", (255, 255, 255)))
    sticker_txt_c = tuple(pal.get("sticker_txt", (11, 24, 31)))
    accent_cyan = (27, 174, 202)
    dark_navy = (11, 24, 31)

    # 1. شارة الخطوات العلوية البيضاء (`[ (01) ● ● ● ]`) كما في `6873.mp4`
    pill_w, pill_h = int(w * 0.28), max(34, int(h * 0.038))
    pill_x1, pill_y1 = cx - pill_w // 2, int(h * 0.055)
    pill_x2, pill_y2 = pill_x1 + pill_w, pill_y1 + pill_h
    draw.rounded_rectangle([(pill_x1, pill_y1 + 3), (pill_x2, pill_y2 + 3)], radius=pill_h // 2, fill=(0, 0, 0, 40))
    draw.rounded_rectangle([(pill_x1, pill_y1), (pill_x2, pill_y2)], radius=pill_h // 2, fill=(255, 255, 255, 250))

    # الدائرة السوداء اليسرى التي تحمل رقم المشهد (01, 02, 03...)
    badge_r = (pill_h - 8) // 2
    b_cx = pill_x1 + 6 + badge_r
    b_cy = pill_y1 + pill_h // 2
    draw.ellipse([(b_cx - badge_r, b_cy - badge_r), (b_cx + badge_r, b_cy + badge_r)], fill=(*dark_navy, 255))
    num_f = get_arabic_font(max(12, int(pill_h * 0.44)), bold=True)
    draw_arabic_text(draw, (b_cx, b_cy), f"{step_num:02d}", font=num_f, fill=(255, 255, 255, 255))

    # نقاط التقدم الثلاث بجانب الرقم
    dots_start_x = b_cx + badge_r + 14
    for di in range(4):
        d_active = (di == ((step_num - 1) % 4))
        dw_dot = 18 if d_active else 8
        draw.rounded_rectangle(
            [(dots_start_x, b_cy - 4), (dots_start_x + dw_dot, b_cy + 4)],
            radius=4,
            fill=(*accent_cyan, 255) if d_active else (203, 213, 225, 255)
        )
        dots_start_x += dw_dot + 7

    # 2. العنوان الرئيسي الكبير مع ستيكر الكلمة المفتاحية (`Sticker-Highlighted Headline`)
    kw_list = scene_meta.get("key_words") or []
    hl_word = kw_list[0] if kw_list else ""
    _draw_sticker_highlighted_headline(
        draw=draw,
        bbox=(int(w * 0.06), int(h * 0.11), int(w * 0.94), int(h * 0.25)),
        headline_text=concept_title,
        highlight_word=hl_word,
        headline_txt_color=headline_txt_c,
        sticker_bg_color=sticker_bg_c,
        sticker_txt_color=sticker_txt_c,
        initial_font_size=max(26, int(h * 0.038)),
        scene_progress=scene_progress
    )

    # 3. مسرح البطاقة البيضاء الاحترافية في المنتصف
    s_card = 0.88 + 0.12 * _staggered_spring(scene_progress, delay=0.05, duration=0.42)

    # --- حالة أ: مشهد الخاتمة الأبيض والـ CTA مع أعمدة النمو الصاعدة (مطابق لـ sec_32 في 6873) ---
    if act_name == "outro_finale":
        logo_card_sz = int(w * 0.34 * s_card)
        lcx1, lcy1 = cx - logo_card_sz // 2, int(h * 0.28)
        lcx2, lcy2 = lcx1 + logo_card_sz, lcy1 + logo_card_sz
        draw.rounded_rectangle([(lcx1, lcy1 + 8), (lcx2, lcy2 + 8)], radius=28, fill=(11, 24, 31, 28))
        draw.rounded_rectangle([(lcx1, lcy1), (lcx2, lcy2)], radius=28, fill=(255, 255, 255, 255), outline=(*accent_cyan, 180), width=2)

        ic_img = render_cairo_vector_illustration("growth_analytics", int(logo_card_sz * 0.68), int(logo_card_sz * 0.68), scene_progress, global_t, {"primary": accent_cyan, "secondary": dark_navy, "accent": accent_cyan})
        img.alpha_composite(ic_img, (cx - ic_img.width // 2, lcy1 + int(logo_card_sz * 0.08)))
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(
            draw, (lcx1 + 10, lcy2 - int(logo_card_sz * 0.28), lcx2 - 10, lcy2 - 6),
            kpi_val, initial_font_size=max(18, int(h * 0.026)), fill=(*dark_navy, 255)
        )

        # زر التواصل الـ Pill السيان (`تواصل معانا اليوم ✈️`)
        btn_w, btn_h = int(w * 0.68 * s_card), max(50, int(h * 0.058))
        bx1, by1 = cx - btn_w // 2, lcy2 + int(h * 0.035)
        bx2, by2 = bx1 + btn_w, by1 + btn_h
        draw.rounded_rectangle([(bx1, by1 + 5), (bx2, by2 + 5)], radius=btn_h // 2, fill=(27, 174, 202, 70))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=btn_h // 2, fill=(*accent_cyan, 255))

        ir = (btn_h - 12) // 2
        ic_cx, ic_cy = bx1 + 8 + ir, by1 + btn_h // 2
        draw.ellipse([(ic_cx - ir, ic_cy - ir), (ic_cx + ir, ic_cy + ir)], fill=(255, 255, 255, 255))
        draw.polygon([(ic_cx + 5, ic_cy - 5), (ic_cx - 6, ic_cy), (ic_cx - 1, ic_cy + 2), (ic_cx + 2, ic_cy + 6)], fill=(*dark_navy, 255))
        draw_contained_arabic_text(
            draw, (ic_cx + ir + 8, by1, bx2 - 14, by2),
            sub_items[0] if sub_items else "تواصل معنا اليوم",
            initial_font_size=max(19, int(h * 0.028)), fill=(255, 255, 255, 255)
        )

        # أعمدة النمو السوداء والسيان في أسفل الشاشة مع السهم المنحني الصاعد
        bars_base_y = int(h * 0.78)
        bar_w = int(w * 0.085)
        bar_xs = [int(w * 0.56), int(w * 0.69), int(w * 0.82)]
        bar_hs = [int(h * 0.08 * s_card), int(h * 0.13 * s_card), int(h * 0.19 * s_card)]
        for bi, (bx_i, bh_i) in enumerate(zip(bar_xs, bar_hs)):
            b_col = accent_cyan if bi == 1 else dark_navy
            draw.rounded_rectangle([(bx_i, bars_base_y - bh_i), (bx_i + bar_w, bars_base_y)], radius=8, fill=(*b_col, 255))

        # قوس السهم الصاعد
        curve_pts = [
            (int(w * 0.36), bars_base_y),
            (int(w * 0.52), bars_base_y - int(h * 0.06)),
            (int(w * 0.70), bars_base_y - int(h * 0.14)),
            (int(w * 0.88), bars_base_y - int(h * 0.22))
        ]
        draw.line(curve_pts, fill=(*dark_navy, 255), width=5)
        ex, ey = curve_pts[-1]
        draw.polygon([(ex, ey - 10), (ex - 12, ey + 4), (ex + 6, ey + 8)], fill=(*dark_navy, 255))
        return img

    # --- حالة ب: بطاقة الفاتورة المشرشرة وختم النتيجة (`receipt_stamp` - لمشاهد المشكلة / الافتتاحية كما في sec_01..05 من 6873) ---
    if act_name == "hook_problem" or card_variant == 0:
        cw, ch = int(w * 0.78 * s_card), int(h * 0.26 * s_card)
        rx1, ry1 = cx - cw // 2, int(h * 0.27)
        rx2, ry2 = rx1 + cw, ry1 + ch

        # شريط متصفح علوي باللون السيان (`ممول 📢`)
        hdr_h = max(36, int(ch * 0.22))
        draw.rounded_rectangle([(rx1, ry1), (rx2, ry1 + hdr_h)], radius=14, fill=(*accent_cyan, 255))
        for di in range(3):
            draw.ellipse([(rx1 + 18 + di * 14, ry1 + hdr_h // 2 - 4), (rx1 + 26 + di * 14, ry1 + hdr_h // 2 + 4)], fill=(255, 255, 255, 210))
        tag_w = int(cw * 0.28)
        draw.rounded_rectangle([(rx2 - tag_w - 10, ry1 + 6), (rx2 - 10, ry1 + hdr_h - 6)], radius=10, fill=(255, 255, 255, 250))
        draw_contained_arabic_text(draw, (rx2 - tag_w - 10, ry1 + 6, rx2 - 10, ry1 + hdr_h - 6), kpi_lbl[:14], initial_font_size=14, fill=(*dark_navy, 255))

        # جسم الفاتورة الأبيض مع الحافة السفلية المشرشرة (Zig-Zag Torn Edge)
        body_y1 = ry1 + hdr_h + 6
        pts_receipt = [(rx1 + 10, body_y1), (rx2 - 10, body_y1), (rx2 - 10, ry2)]
        num_teeth = 12
        tooth_w = (rx2 - rx1 - 20) / float(num_teeth)
        for ti in range(num_teeth, -1, -1):
            tx = int(rx1 + 10 + ti * tooth_w)
            ty = ry2 + (8 if ti % 2 == 1 else 0)
            pts_receipt.append((tx, ty))
        draw.polygon([(px, py + 6) for px, py in pts_receipt], fill=(0, 0, 0, 95))
        draw.polygon(pts_receipt, fill=(255, 255, 255, 252))

        # سطور الفاتورة
        row1_y = body_y1 + int((ry2 - body_y1) * 0.28)
        row2_y = body_y1 + int((ry2 - body_y1) * 0.68)
        draw_contained_arabic_text(draw, (rx1 + 20, row1_y - 16, rx2 - 20, row1_y + 16), sub_items[0], initial_font_size=18, fill=(51, 65, 85, 255))
        draw_contained_arabic_text(draw, (rx1 + 20, row2_y - 16, rx2 - 20, row2_y + 16), sub_items[min(1, len(sub_items)-1)], initial_font_size=18, fill=(*accent_cyan, 255))

        # الختم العريض البارز في وسط الفاتورة (`[ النتيجة: ... ]`)
        stamp_w, stamp_h = int(cw * 0.86), max(46, int(ch * 0.32))
        sx1, sy1 = cx - stamp_w // 2, (body_y1 + ry2) // 2 - stamp_h // 2
        draw.rounded_rectangle([(sx1, sy1 + 4), (sx1 + stamp_w, sy1 + stamp_h + 4)], radius=12, fill=(0, 0, 0, 75))
        draw.rounded_rectangle([(sx1, sy1), (sx1 + stamp_w, sy1 + stamp_h)], radius=12, fill=(255, 255, 255, 255), outline=(*dark_navy, 255), width=4)
        draw_contained_arabic_text(
            draw, (sx1 + 12, sy1, sx1 + stamp_w - 12, sy1 + stamp_h),
            kpi_val, initial_font_size=max(22, int(h * 0.034)), fill=(*dark_navy, 255)
        )

        # أبراج العملات ثلاثية الأبعاد أسفل الفاتورة
        coin_ic = render_cairo_vector_illustration("growth_analytics", int(w * 0.46), int(h * 0.20), scene_progress, global_t, {"primary": accent_cyan, "secondary": (255, 255, 255), "accent": accent_cyan})
        img.alpha_composite(coin_ic, (cx - coin_ic.width // 2, ry2 + int(h * 0.02)))
        return img

    # --- حالة ج: مخطط الخطوات المتصل (`step_nodes_graph` - كما في sec_12 و sec_24 من 6873) ---
    if card_variant == 1:
        cw, ch = int(w * 0.80 * s_card), int(h * 0.28 * s_card)
        card_img = Image.new("RGBA", (cw + 24, ch + 24), (0, 0, 0, 0))
        cdraw = ImageDraw.Draw(card_img, "RGBA")
        cdraw.rounded_rectangle([(12, 16), (cw + 12, ch + 16)], radius=24, fill=(0, 0, 0, 65))
        cdraw.rounded_rectangle([(8, 8), (cw + 8, ch + 8)], radius=24, fill=(255, 255, 255, 255))

        # شبكة خفيفة داخل البطاقة البيضاء
        for gx in range(28, cw, 36):
            cdraw.line([(gx, 16), (gx, ch)], fill=(226, 232, 240, 180), width=1)
        for gy in range(28, ch, 36):
            cdraw.line([(16, gy), (cw, gy)], fill=(226, 232, 240, 180), width=1)

        # شريط المؤشرات العلوي داخل البطاقة (`♥ 930   💬 239   ☑ 72` أو الـ KPI)
        pill_y = 22
        cdraw.rounded_rectangle([(24, pill_y), (cw - 8, pill_y + 34)], radius=12, fill=(241, 245, 249, 255))
        draw_contained_arabic_text(
            cdraw, (28, pill_y, cw - 12, pill_y + 34),
            f"{kpi_val}  •  {kpi_lbl}", initial_font_size=16, fill=(*dark_navy, 255)
        )

        # المنحنى الصاعد والعقد الأربع (`01 -> 02 -> 03 -> 04`)
        nodes_xy = [
            (int(cw * 0.18), int(ch * 0.78)),
            (int(cw * 0.40), int(ch * 0.64)),
            (int(cw * 0.63), int(ch * 0.48)),
            (int(cw * 0.84), int(ch * 0.34)),
        ]
        # تظليل تحت المنحنى
        poly_area = [(nodes_xy[0][0], ch - 6)] + nodes_xy + [(nodes_xy[-1][0], ch - 6)]
        cdraw.polygon(poly_area, fill=(27, 174, 202, 48))
        cdraw.line(nodes_xy, fill=(*dark_navy, 255), width=4)

        for ni, (nx, ny) in enumerate(nodes_xy):
            nr = 15
            n_col = accent_cyan if (ni == len(nodes_xy) - 1 or ni == 0) else dark_navy
            cdraw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(*n_col, 255), outline=(255, 255, 255, 255), width=2)
            nf = get_arabic_font(12, bold=True)
            draw_arabic_text(cdraw, (nx, ny), f"{ni + 1:02d}", font=nf, fill=(255, 255, 255, 255))

        rotated_card = card_img.rotate(1.8, resample=Image.Resampling.BICUBIC, expand=True)
        img.alpha_composite(rotated_card, (cx - rotated_card.width // 2, int(h * 0.31)))

        # كبسولة النقطة التوضيحية أسفل البطاقة
        sub_y = int(h * 0.64)
        draw.rounded_rectangle([(int(w * 0.12), sub_y), (int(w * 0.88), sub_y + 46)], radius=23, fill=(11, 24, 31, 185), outline=(255, 255, 255, 190), width=2)
        draw_contained_arabic_text(draw, (int(w * 0.14), sub_y, int(w * 0.86), sub_y + 46), sub_items[0], initial_font_size=18, fill=(255, 255, 255, 255))
        return img

    # --- حالة د: بطاقة العدسة المكبرة الفاحصة (`magnifier_browser_card` - كما في sec_14 من 6873) ---
    if card_variant == 2:
        cw, ch = int(w * 0.76 * s_card), int(h * 0.25 * s_card)
        bx1, by1 = cx - cw // 2, int(h * 0.32)
        bx2, by2 = bx1 + cw, by1 + ch
        draw.rounded_rectangle([(bx1, by1 + 10), (bx2, by2 + 10)], radius=24, fill=(0, 0, 0, 65))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=24, fill=(255, 255, 255, 255))

        # شارة المتجر/الفئة السيان على اليمين
        badge_sz = int(ch * 0.32)
        draw.rounded_rectangle([(bx2 - badge_sz - 18, by1 + 18), (bx2 - 18, by1 + 18 + badge_sz)], radius=14, fill=(*accent_cyan, 255))
        draw_contained_arabic_text(draw, (bx2 - badge_sz - 18, by1 + 18, bx2 - 18, by1 + 18 + badge_sz), kpi_val[:6], initial_font_size=15, fill=(255, 255, 255, 255))

        # قوالب المحتوى داخل البطاقة
        bar_x1, bar_x2 = bx1 + int(cw * 0.26), bx2 - badge_sz - 30
        draw.rounded_rectangle([(bar_x1, by1 + 22), (bar_x2, by1 + 38)], radius=8, fill=(148, 163, 184, 220))
        draw.rounded_rectangle([(bar_x1, by1 + 48), (bar_x2 - 24, by1 + 62)], radius=7, fill=(203, 213, 225, 220))

        # 3 مربعات معاينة سفلية داخل البطاقة
        sq_y1 = by1 + int(ch * 0.48)
        sq_h = int(ch * 0.42)
        sq_w = (cw - 56) // 3
        for si in range(3):
            sx = bx1 + 16 + si * (sq_w + 12)
            scol = (226, 232, 240, 255) if si != 1 else (186, 230, 253, 255)
            draw.rounded_rectangle([(sx, sq_y1), (sx + sq_w, sq_y1 + sq_h)], radius=12, fill=scol)
            if si < len(sub_items):
                draw_contained_arabic_text(draw, (sx + 4, sq_y1 + 6, sx + sq_w - 4, sq_y1 + sq_h - 6), sub_items[si], initial_font_size=14, fill=(*dark_navy, 255))

        # العدسة المكبرة الكبيرة الفاحصة على اليسار (`🔍`)
        mag_r = int(ch * 0.28)
        mag_cx = bx1 + int(cw * 0.16) + int(10 * math.sin(global_t * 3.0))
        mag_cy = by1 + int(ch * 0.26)
        draw.line([(mag_cx - int(mag_r * 0.65), mag_cy + int(mag_r * 0.65)), (mag_cx - int(mag_r * 1.45), mag_cy + int(mag_r * 1.45))], fill=(*dark_navy, 255), width=10)
        draw.ellipse([(mag_cx - mag_r, mag_cy - mag_r), (mag_cx + mag_r, mag_cy + mag_r)], fill=(255, 255, 255, 95), outline=(*dark_navy, 255), width=6)
        draw.ellipse([(mag_cx - mag_r + 5, mag_cy - mag_r + 5), (mag_cx + mag_r - 5, mag_cy + mag_r - 5)], outline=(*accent_cyan, 255), width=3)
        return img

    # --- حالة هـ: رادار الجمهور المستهدف (`radar_target_circle` - كما في sec_17 من 6873) ---
    if card_variant == 3:
        rad_cy = int(h * 0.45)
        max_r = int(min(w, h) * 0.24 * s_card)
        for ri, r_frac in enumerate([1.0, 0.72, 0.44]):
            rr = int(max_r * r_frac)
            draw.ellipse([(cx - rr, rad_cy - rr), (cx + rr, rad_cy + rr)], outline=(255, 255, 255, 220 if ri == 0 else 130), width=3 if ri == 0 else 2)

        # خطوط تقاطع الرادار
        draw.line([(cx - max_r - 16, rad_cy), (cx + max_r + 16, rad_cy)], fill=(255, 255, 255, 160), width=2)
        draw.line([(cx, rad_cy - max_r - 16), (cx, rad_cy + max_r + 16)], fill=(255, 255, 255, 160), width=2)

        # كبسولات العناصر داخل وحول الرادار مع علامة الصح
        node_angles = [0.0, math.pi / 3, 2 * math.pi / 3, math.pi, 4 * math.pi / 3, 5 * math.pi / 3]
        for ni, ang in enumerate(node_angles):
            dist_r = max_r * 0.64
            nx = cx + int(dist_r * math.cos(ang + global_t * 0.25))
            ny = rad_cy + int(dist_r * math.sin(ang + global_t * 0.25))
            nr = max(18, int(max_r * 0.20))
            draw.ellipse([(nx - nr, ny - nr), (nx + nr, ny + nr)], fill=(255, 255, 255, 250), outline=(*dark_navy, 255), width=2)
            draw.ellipse([(nx - nr // 2, ny - nr // 2 - 3), (nx + nr // 2, ny + nr // 2 - 3)], fill=(*accent_cyan, 255))

        _draw_checkmark_badge(draw, cx + int(max_r * 0.68), rad_cy - int(max_r * 0.68), 16, color_rgb=dark_navy)

        # بطاقة المؤشر أسفل الرادار
        pill_y = rad_cy + max_r + 22
        draw.rounded_rectangle([(int(w * 0.14), pill_y), (int(w * 0.86), pill_y + 48)], radius=24, fill=(255, 255, 255, 250))
        draw_contained_arabic_text(draw, (int(w * 0.16), pill_y, int(w * 0.84), pill_y + 48), f"{kpi_val} • {sub_items[0]}", initial_font_size=18, fill=(*dark_navy, 255))
        return img

    # --- حالة و: بطاقة تقرير الأداء على الهاتف (`mobile_performance_report` - كما في sec_27..28 من 6873) ---
    pw, ph = int(w * 0.44 * s_card), int(h * 0.36 * s_card)
    px1, py1 = cx - pw // 2, int(h * 0.29)
    px2, py2 = px1 + pw, py1 + ph

    # الورقتان الجانبيتان المائلتان خلف الهاتف (كما في sec_28)
    side_w, side_h = int(pw * 0.62), int(ph * 0.56)
    draw.rounded_rectangle([(px1 - side_w // 2, py1 + int(ph * 0.22)), (px1 + side_w // 2, py1 + int(ph * 0.22) + side_h)], radius=16, fill=(241, 245, 249, 235), outline=(*accent_cyan, 180), width=2)
    draw.rounded_rectangle([(px2 - side_w // 2, py1 + int(ph * 0.22)), (px2 + side_w // 2, py1 + int(ph * 0.22) + side_h)], radius=16, fill=(241, 245, 249, 235), outline=(*accent_cyan, 180), width=2)

    # جسم الهاتف الأبيض المركزي
    draw.rounded_rectangle([(px1, py1 + 8), (px2, py2 + 8)], radius=26, fill=(0, 0, 0, 85))
    draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=26, fill=(255, 255, 255, 255), outline=(*dark_navy, 255), width=4)

    # شارة `تقرير الأداء` العلوية
    rep_h = 34
    draw.rounded_rectangle([(px1 + 14, py1 + 14), (px2 - 14, py1 + 14 + rep_h)], radius=12, fill=(241, 245, 249, 255), outline=(*dark_navy, 255), width=2)
    draw_contained_arabic_text(draw, (px1 + 18, py1 + 14, px2 - 18, py1 + 14 + rep_h), kpi_lbl, initial_font_size=15, fill=(*dark_navy, 255))

    # مؤشرا الأداء داخل الهاتف
    m_y = py1 + 14 + rep_h + 18
    draw_contained_arabic_text(draw, (px1 + 12, m_y, px2 - 12, m_y + 34), kpi_val, initial_font_size=22, fill=(*accent_cyan, 255))

    # المدرج الصاعد داخل شاشة الهاتف
    st_y = m_y + 46
    st_h = int(ph * 0.22)
    step_pts = [
        (px1 + 22, st_y + st_h),
        (px1 + int(pw * 0.38), st_y + st_h),
        (px1 + int(pw * 0.38), st_y + int(st_h * 0.55)),
        (px1 + int(pw * 0.66), st_y + int(st_h * 0.55)),
        (px1 + int(pw * 0.66), st_y + int(st_h * 0.15)),
        (px2 - 22, st_y + int(st_h * 0.15))
    ]
    draw.line(step_pts, fill=(*accent_cyan, 255), width=3)

    # دائرة النسبة السفلية داخل الهاتف (`95%`)
    ring_y = py2 - 36
    ring_r = 18
    draw.arc([(px1 + 24, ring_y - ring_r), (px1 + 24 + ring_r * 2, ring_y + ring_r)], start=-90, end=200, fill=(*accent_cyan, 255), width=5)
    draw_contained_arabic_text(draw, (px1 + 28 + ring_r * 2, ring_y - 18, px2 - 14, ring_y + 18), sub_items[0][:16], initial_font_size=15, fill=(*dark_navy, 255))
    return img


def _render_mazen_blueprint_stage_6842(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float
) -> Image.Image:
    """
    يرسم مشهد المخطط الهندسي السماوي والخطوات المرقمة المطابق تماماً لفيديو `6842.mp4`:
    1. إطار التحديد الهندسي التفاعلي (`Selection Box` بـ 8 مقابض مربعة + مؤشر الماوس) حول الفكرة المحورية.
    2. الدوائر المرقمة الزرقاء (`1`, `2`, `3`, `4`) على اليمين مع كبسولات الأسئلة/النقاط السماوية التي تنبثق بالتتابع.
    3. رسم الفيكتور التعبيري على اليسار لتحقيق التوازن البصري.
    """
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img, "RGBA")
    pal = style_spec.get("palette", {})

    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "الخطوات الأساسية للنجاح")
    kpi_val = str(scene_meta.get("kpi_value") or "ركيزة أساسية")
    kpi_lbl = str(scene_meta.get("kpi_label") or "تخطيط ذكي")
    sub_items = [re.sub(r"^\d+[\.\-\s]+", "", str(s)).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    while len(sub_items) < 4:
        sub_items.append(kpi_lbl if len(sub_items) % 2 == 0 else kpi_val)

    blue_primary = tuple(pal.get("primary", (2, 132, 199)))
    navy_dark = tuple(pal.get("headline_txt", (15, 23, 42)))

    # 1. إطار التحديد الهندسي العلوي للعنوان مع مقابض التحجيم الثمانية ومؤشر الماوس (مطابق لـ sec_08 في 6842)
    sel_x1, sel_y1 = int(w * 0.08), int(h * 0.14)
    sel_x2, sel_y2 = int(w * 0.92), int(h * 0.27)
    draw.rounded_rectangle([(sel_x1, sel_y1), (sel_x2, sel_y2)], radius=8, fill=(255, 255, 255, 135), outline=(*blue_primary, 235), width=2)

    # مقابض التحجيم المربعة الثمانية (8 Resize Handles)
    handle_pts = [
        (sel_x1, sel_y1), ((sel_x1 + sel_x2) // 2, sel_y1), (sel_x2, sel_y1),
        (sel_x1, (sel_y1 + sel_y2) // 2), (sel_x2, (sel_y1 + sel_y2) // 2),
        (sel_x1, sel_y2), ((sel_x1 + sel_x2) // 2, sel_y2), (sel_x2, sel_y2)
    ]
    for hx, hy in handle_pts:
        draw.rectangle([(hx - 4, hy - 4), (hx + 4, hy + 4)], fill=(255, 255, 255, 255), outline=(*blue_primary, 255), width=2)

    draw_contained_arabic_text(
        draw, (sel_x1 + 14, sel_y1 + 8, sel_x2 - 14, sel_y2 - 8),
        concept_title, initial_font_size=max(24, int(h * 0.036)), fill=(*navy_dark, 255)
    )
    _draw_cursor_with_ripple(draw, (sel_x2 - 48, sel_y2 + 34), (sel_x2 - 4, sel_y2 - 4), scene_progress, accent_rgb=blue_primary)

    # 2. قائمة الخطوات المرقمة `1 - 2 - 3 - 4` بالدوائر الزرقاء على اليمين (مطابق لـ sec_10..15 في 6842)
    list_top_y = int(h * 0.33)
    row_h = max(50, int(h * 0.072))
    row_gap = max(12, int(h * 0.018))
    circle_r = max(18, int(row_h * 0.42))
    right_anchor_x = int(w * 0.90)
    pill_left_x = int(w * 0.12)

    for i in range(4):
        item_pop = _staggered_spring(scene_progress, delay=0.06 + i * 0.08, duration=0.40)
        ry_center = list_top_y + i * (row_h + row_gap) + row_h // 2 + int(18 * (1.0 - item_pop))

        # الكبسولة الزرقاء الفاتحة الشفافة للنقطة
        p_x2 = right_anchor_x - circle_r * 2 - 10
        p_x1 = pill_left_x
        draw.rounded_rectangle(
            [(p_x1, ry_center - row_h // 2), (p_x2, ry_center + row_h // 2)],
            radius=row_h // 2,
            fill=(255, 255, 255, 215),
            outline=(*blue_primary, 195),
            width=2
        )
        draw_contained_arabic_text(
            draw, (p_x1 + 14, ry_center - row_h // 2, p_x2 - 14, ry_center + row_h // 2),
            sub_items[i], initial_font_size=max(17, int(h * 0.025)), fill=(*navy_dark, 255)
        )

        # الدائرة الزرقاء المرقمة (`1`, `2`, `3`, `4`)
        c_cx = right_anchor_x - circle_r
        draw.ellipse(
            [(c_cx - circle_r, ry_center - circle_r), (c_cx + circle_r, ry_center + circle_r)],
            fill=(*blue_primary, 255), outline=(255, 255, 255, 240), width=2
        )
        nf = get_arabic_font(max(18, int(circle_r * 0.95)), bold=True)
        draw_arabic_text(draw, (c_cx, ry_center), str(i + 1), font=nf, fill=(255, 255, 255, 255))

    return img


def _render_baghdadi_plum_stage_6871(
    img: Image.Image,
    scene_meta: Dict[str, Any],
    style_spec: Dict[str, Any],
    scene_progress: float,
    global_t: float
) -> Image.Image:
    """
    يرسم مشهد مختبر الإعلانات الفاخر باللون البنفسجي الداكن المطابق تماماً لفيديو `6871.mp4`:
    1. شريط التبويبات العلوي المقسم إلى 3 مراحل (`[ المشكلة ]  [ الحل ]  [ النتيجة ]`) مع إضاءة المرحلة النشطة بالبنفسجي المتوهج.
    2. شارة المرحلة المربعة على اليمين (`[A]`, `[P]`, `[S]`) مع عنوان المرحلة.
    3. بطاقتا مقارنة مزدوجة (`قبل` مقابل `بعد`) أو مجسم العرض المركزي مع شارات التوضيح وزر الإجراء البنفسجي (`اطلبه اليوم ↖`).
    """
    w, h = img.size
    cx = w // 2
    draw = ImageDraw.Draw(img, "RGBA")
    pal = style_spec.get("palette", {})
    act_name = str(style_spec.get("act_name", "body_steps"))
    step_num = int(scene_meta.get("step_number") or style_spec.get("step_number") or 1)

    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "الفكرة الجوهرية")
    kpi_val = str(scene_meta.get("kpi_value") or "نتيجة فورية")
    kpi_lbl = str(scene_meta.get("kpi_label") or "أداء متفوق")
    sub_items = [re.sub(r"^\d+[\.\-\s]+", "", str(s)).strip() for s in (scene_meta.get("sub_items") or []) if str(s).strip()]
    if len(sub_items) < 2:
        sub_items = [kpi_lbl, kpi_val]

    violet_main = tuple(pal.get("primary", (139, 92, 246)))
    lavender_sec = tuple(pal.get("secondary", (216, 180, 254)))

    # 1. شريط التبويبات الثلاثي العلوي (`[ المشكلة ]  [ الحل ]  [ النتيجة ]`) كما في `6871.mp4`
    tabs_y1 = int(h * 0.055)
    tabs_h = max(30, int(h * 0.034))
    tab_labels = ["المقدمة", "المحور", "النتيجة"]
    active_tab_idx = 0 if act_name == "hook_problem" else (2 if act_name == "outro_finale" else 1)

    total_tabs_w = int(w * 0.86)
    single_tab_w = (total_tabs_w - 16) // 3
    tabs_x0 = (w - total_tabs_w) // 2

    # ترتيب التبويبات من اليمين لليسار
    for ti in range(3):
        rtl_i = 2 - ti
        tx1 = tabs_x0 + rtl_i * (single_tab_w + 8)
        tx2 = tx1 + single_tab_w
        is_act = (ti == active_tab_idx)
        t_fill = (*violet_main, 255) if is_act else (38, 32, 62, 220)
        draw.rounded_rectangle([(tx1, tabs_y1), (tx2, tabs_y1 + tabs_h)], radius=8, fill=t_fill)
        draw_contained_arabic_text(
            draw, (tx1 + 6, tabs_y1, tx2 - 6, tabs_y1 + tabs_h),
            tab_labels[ti], initial_font_size=14, fill=(255, 255, 255, 255 if is_act else 185)
        )

    # 2. شارة المرحلة المربعة على اليمين (`[A]`, `[P]`, `[S]`) وعنوان المرحلة
    phase_y = tabs_y1 + tabs_h + int(h * 0.022)
    sq_sz = max(34, int(h * 0.038))
    sq_x2 = int(w * 0.92)
    sq_x1 = sq_x2 - sq_sz
    draw.rounded_rectangle([(sq_x1, phase_y), (sq_x2, phase_y + sq_sz)], radius=8, fill=(*violet_main, 255))
    letter_code = "P" if active_tab_idx == 0 else ("B" if active_tab_idx == 2 else "S")
    lf = get_arabic_font(18, bold=True)
    draw_arabic_text(draw, ((sq_x1 + sq_x2) // 2, phase_y + sq_sz // 2), letter_code, font=lf, fill=(255, 255, 255, 255))

    draw_contained_arabic_text(
        draw, (int(w * 0.12), phase_y, sq_x1 - 12, phase_y + sq_sz),
        kpi_lbl, initial_font_size=20, fill=(255, 255, 255, 245)
    )

    # 3. العنوان الرئيسي المزدوج اللون (أبيض ناصع + لافندر متوهج)
    hl_y1 = phase_y + sq_sz + int(h * 0.018)
    hl_y2 = hl_y1 + int(h * 0.11)
    draw_contained_arabic_text(
        draw, (int(w * 0.07), hl_y1, int(w * 0.93), hl_y2),
        concept_title, initial_font_size=max(26, int(h * 0.040)), fill=(*lavender_sec, 255)
    )

    # 4. المسرح المركزي: إما بطاقتا المقارنة `قبل / بعد` (كما في الصف الرابع من 6871) أو المجسم المركزي مع زر الـ CTA
    s_in = 0.88 + 0.12 * _staggered_spring(scene_progress, delay=0.05, duration=0.40)
    if step_num % 2 == 0 or scene_meta.get("archetype") in ("stage_before_after_checklist", "stage_balance_scale"):
        comp_y1 = hl_y2 + int(h * 0.025)
        comp_h = int(h * 0.34 * s_in)
        comp_w = int(w * 0.41)
        right_x1 = int(w * 0.52)
        left_x1 = int(w * 0.07)

        # بطاقة "بعد" (اليمين - متوهجة بالبنفسجي)
        draw.rounded_rectangle([(right_x1, comp_y1), (right_x1 + comp_w, comp_y1 + comp_h)], radius=20, fill=(46, 32, 78, 235), outline=(*violet_main, 255), width=2)
        draw_contained_arabic_text(draw, (right_x1 + 10, comp_y1 + 10, right_x1 + comp_w - 10, comp_y1 + 44), "بعد", initial_font_size=18, fill=(255, 255, 255, 255))
        ic_pos = render_cairo_vector_illustration(scene_meta.get("scene_type", "growth_analytics"), int(comp_w * 0.65), int(comp_h * 0.48), scene_progress, global_t, {"primary": violet_main, "secondary": lavender_sec, "accent": (16, 185, 129)})
        img.alpha_composite(ic_pos, (right_x1 + (comp_w - ic_pos.width) // 2, comp_y1 + 52))
        draw = ImageDraw.Draw(img, "RGBA")
        draw_contained_arabic_text(draw, (right_x1 + 8, comp_y1 + comp_h - 46, right_x1 + comp_w - 8, comp_y1 + comp_h - 10), sub_items[0], initial_font_size=16, fill=(255, 255, 255, 255))

        # بطاقة "قبل" (اليسار - داكنة هادئة)
        draw.rounded_rectangle([(left_x1, comp_y1), (left_x1 + comp_w, comp_y1 + comp_h)], radius=20, fill=(24, 22, 42, 235), outline=(100, 116, 139, 180), width=2)
        draw_contained_arabic_text(draw, (left_x1 + 10, comp_y1 + 10, left_x1 + comp_w - 10, comp_y1 + 44), "قبل", initial_font_size=18, fill=(148, 163, 184, 255))
        draw_contained_arabic_text(draw, (left_x1 + 10, comp_y1 + int(comp_h * 0.42), left_x1 + comp_w - 10, comp_y1 + int(comp_h * 0.68)), "الطريقة التقليدية", initial_font_size=16, fill=(203, 213, 225, 230))
        draw_contained_arabic_text(draw, (left_x1 + 8, comp_y1 + comp_h - 46, left_x1 + comp_w - 8, comp_y1 + comp_h - 10), "وقت ومجهود", initial_font_size=15, fill=(148, 163, 184, 240))

        # شارة الجسر المتوسطة بين البطاقتين (`kpi_val`)
        br_w, br_h = int(w * 0.44), 38
        br_y = comp_y1 + int(comp_h * 0.62)
        draw.rounded_rectangle([(cx - br_w // 2, br_y), (cx + br_w // 2, br_y + br_h)], radius=12, fill=(*violet_main, 255), outline=(255, 255, 255, 220), width=2)
        draw_contained_arabic_text(draw, (cx - br_w // 2 + 8, br_y, cx + br_w // 2 - 8, br_y + br_h), kpi_val, initial_font_size=16, fill=(255, 255, 255, 255))
    else:
        ic_sz = int(min(w, h) * 0.34 * s_in)
        hero_ic = render_cairo_vector_illustration(scene_meta.get("scene_type", "growth_analytics"), ic_sz, ic_sz, scene_progress, global_t, {"primary": violet_main, "secondary": lavender_sec, "accent": violet_main})
        ic_y = hl_y2 + int(h * 0.02)
        img.alpha_composite(hero_ic, (cx - ic_sz // 2, ic_y))
        draw = ImageDraw.Draw(img, "RGBA")

        # زر الإجراء البنفسجي أسفل المجسم مع مؤشر الماوس (`اطلبه اليوم ↖` كما في sec_32 من 6871)
        btn_w, btn_h = int(w * 0.64), 48
        btn_y1 = ic_y + ic_sz + 14
        bx1, bx2 = cx - btn_w // 2, cx + btn_w // 2
        draw.rounded_rectangle([(bx1, btn_y1), (bx2, btn_y1 + btn_h)], radius=14, fill=(*violet_main, 255), outline=(255, 255, 255, 210), width=2)
        draw_contained_arabic_text(draw, (bx1 + 16, btn_y1, bx2 - 16, btn_y1 + btn_h), f"{kpi_val} • {sub_items[0]}", initial_font_size=18, fill=(255, 255, 255, 255))
        _draw_cursor_with_ripple(draw, (bx2 - 10, btn_y1 + btn_h + 24), (bx2 - 28, btn_y1 + btn_h // 2), scene_progress, accent_rgb=lavender_sec)

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
# 10. تصيير مشهد موشن جرافيك كامل الشاشة بالستايلات الاحترافية (6873 / 6842 / 6871)
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
    تصيير مشهد موشن جرافيك كامل الشاشة بمستوى الفيديوهات المرجعية (`6873.mp4` و `6842.mp4` و `6871.mp4`):
    - يستخرج `scene_style_spec` (أو يبنيه تلقائياً) ليحدد العائلة البصرية (`byw_cyan_agency`, `mazen_blueprint_collage`, `baghdadi_luxury_plum`)
      والمرحلة اللونية (`hook_problem`, `body_steps`, `outro_finale`) ورقم البطاقة (`card_variant_index`).
    - إذا كان المستخدم قد رفع لوقو أو اختار ألوان براند مخصصة، يدمج ألوان البراند واللوقو بسلاسة داخل الستايل الاحترافي!
    """
    theme_name, theme, is_light, logo_path, logo_pos = _resolve_active_theme_and_style(scene_meta)
    step_num = int(scene_meta.get("step_number") or scene_meta.get("index", 0) + 1)

    style_spec = scene_meta.get("scene_style_spec")
    if not isinstance(style_spec, dict):
        auto_plan = build_dynamic_scene_style_assignment(max(4, step_num + 1), advance_rotation_counter=False)
        style_spec = auto_plan[min(len(auto_plan) - 1, max(0, step_num - 1))]

    # إذا فعل المستخدم ثيم اللوقو المخصص، نطعم باليت الستايل بألوان اللوقو مع الحفاظ على هندسة التصميم الاحترافية
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

    design_family = str(style_spec.get("design_family", "byw_cyan_agency"))
    pal = style_spec.get("palette", {})
    is_light_stage = bool(pal.get("is_light_bg", is_light))

    # 1. رندرة الخلفية الشبكية والهندسية الخاصة بالستايل
    img = _render_pro_stage_background(width, height, style_spec, step_num=step_num, global_t=global_t)

    # 2. رسم اللوقو المرفوع إن وجد
    img, _ = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=is_light_stage)

    # 3. رسم المسرح الاحترافي حسب العائلة البصرية (`6873` أو `6842` أو `6871`)
    if design_family == "mazen_blueprint_collage":
        img = _render_mazen_blueprint_stage_6842(img, scene_meta, style_spec, scene_progress, global_t)
    elif design_family == "baghdadi_luxury_plum":
        img = _render_baghdadi_plum_stage_6871(img, scene_meta, style_spec, scene_progress, global_t)
    else:
        img = _render_byw_agency_stage_6873(img, scene_meta, style_spec, scene_progress, global_t)

    # 4. كابشن الكاريوكي السفلي الموحد والأنيق
    caption_theme = {
        "primary": tuple(pal.get("primary", (27, 174, 202))),
        "secondary": tuple(pal.get("sticker_bg", (250, 204, 21)))
    }
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.855),
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
# 11. محرك الانتقال السلس المريح للعين بين المشاهد (Smooth Studio Camera Handoff)
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

    font_size = max(26, int(min(w, h) * 0.040))
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

    draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(bar_x1, bar_y1, bar_x2, bar_y2),
        radius=16,
        tint_color=(11, 14, 24, 244),
        border_color=theme.get("primary", (27, 174, 202)),
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
                fill=(27, 174, 202, 255)
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

    # وضع الفيديو الحقيقي: يبقى الفيديو بملء الشاشة 100% دائماً مع بطاقات وكالة عائمة أنيقة (بأسلوب 6873 و 6842)!
    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    img, logo_bbox = _render_brand_logo_watermark(img, logo_path, logo_pos, theme, is_light=False)
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2
    step_num = int(sc.get("step_number") or (active_idx + 1))

    if layout_mode in ("floating_callout", "split_screen_stage"):
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.34), stiffness=205.0, damping=15.0)
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

        # بطاقة بيضاء/زجاجية بأسلوب وكالة 6873 مع شارة رقم الخطوة الدائرية
        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=22,
            tint_color=(11, 24, 31, 228),
            border_color=(27, 174, 202),
            secondary_color=theme["secondary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=18,
            light_sweep_prog=(sc_prog * 1.4 - 0.1)
        )

        draw = ImageDraw.Draw(img, "RGBA")
        # شارة رقم الخطوة السيان على اليمين (`01`, `02`, `03`)
        badge_r = max(22, int(card_h * 0.32))
        b_cx = bx2 - badge_r - 16
        b_cy = by1 + card_h // 2
        draw.ellipse([(b_cx - badge_r, b_cy - badge_r), (b_cx + badge_r, b_cy + badge_r)], fill=(27, 174, 202, 255), outline=(255, 255, 255, 240), width=2)
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
            fill=(27, 174, 202, 255), pad_left=10, pad_right=10, min_font_size=11
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
            border_color=(27, 174, 202),
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
            border_color=(27, 174, 202),
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

        update_progress(0.30, "2/4: تفريغ الكلام وتشغيل المخ السياقي وتنويع الستايلات الاحترافية...")
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

        update_progress(0.55, "3/4: تصيير مشاهد الموشن جرافيك الاحترافية المتعددة الستايلات...")

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
            handoff_dur = float(sc.get("handoff_duration_sec", 0.38))
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