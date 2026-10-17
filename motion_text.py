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
    min_font_size: int = 14,
    bold: bool = True
) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    """تصغير حجم الخط تلقائياً لضمان ملاءمة النص داخل حدود البطاقة بدون أي خروج أو تجاوز."""
    size = int(initial_font_size)
    min_size = int(min_font_size)
    f_obj = get_arabic_font(size, bold=bold)
    tw, th = measure_arabic_text(draw, str(text), f_obj)
    while tw > max_width and size > min_size:
        size -= 2
        f_obj = get_arabic_font(size, bold=bold)
        tw, th = measure_arabic_text(draw, str(text), f_obj)
    return f_obj, tw, th


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
    x = max(0.0, min(1.0, float(x)))
    return 1.0 - pow(1.0 - x, 3)


def _ease_in_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, float(x)))
    return 4.0 * x * x * x if x < 0.5 else 1.0 - pow(-2.0 * x + 2.0, 3) / 2.0


def _ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, float(x)))
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * pow(x - 1.0, 3) + c1 * pow(x - 1.0, 2)


def _spring_physics(t: float, stiffness: float = 210.0, damping: float = 15.0, mass: float = 1.0) -> float:
    """محرك فيزياء النوابض الحقيقي (Hooke's Law Damped Harmonic Oscillator)."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    omega_n = math.sqrt(stiffness / mass)
    zeta = damping / (2.0 * math.sqrt(stiffness * mass))
    if zeta < 1.0:
        omega_d = omega_n * math.sqrt(1.0 - zeta * zeta)
        env = math.exp(-zeta * omega_n * t)
        val = 1.0 - env * (math.cos(omega_d * t) + (zeta * omega_n / omega_d) * math.sin(omega_d * t))
        return float(val)
    else:
        return 1.0 - math.exp(-omega_n * t)


def _staggered_spring(global_prog: float, delay: float = 0.0, duration: float = 0.45) -> float:
    """حساب حركة طبقة فرعية بتأخير متتابع (Staggered Choreography)."""
    local_t = (global_prog - delay) / max(0.05, duration)
    return _spring_physics(max(0.0, min(1.0, local_t)))


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
    يرسم الكوريغرافيا التفاعلية الكاملة للمشهد داخل منطقة المسرح المحددة (`stage_bbox`)
    بناءً على الأنماط الـ 8 المستخلصة من الفيديوهات المرجعية (`Motion Graphics Frame By Frame Spec`).
    """
    x1, y1, x2, y2 = stage_bbox
    sw, sh = x2 - x1, y2 - y1
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    archetype = str(scene_meta.get("archetype", "saas_folder_reorder")).strip()
    concept_title = str(scene_meta.get("concept_title") or scene_meta.get("short_title") or "مفهوم ذكي")
    kpi_val = str(scene_meta.get("kpi_value") or "+300%")
    kpi_lbl = str(scene_meta.get("kpi_label") or "مؤشر الأداء")
    sub_items = scene_meta.get("sub_items") or [
        "تحليل الصوت والسياق",
        "توليد المشاهد الحركية",
        "مزامنة الكابشن الذكي",
        "إخراج احترافي فوري"
    ]
    while len(sub_items) < 4:
        sub_items.append("ميزة ذكية متكاملة")

    # ألوان ذكية تتكيف مع النمط الفاتح (101bdarija Clean SaaS) أو الداكن (moujtabakhalifa Stage)
    if is_light_saas:
        card_tint = (255, 255, 255, 245)
        sub_card_tint = (248, 250, 252, 255)
        txt_main = (17, 24, 39, 255)
        txt_sub = (71, 85, 105, 255)
        stroke_c = (255, 255, 255, 0)
        stroke_w = 0
        c_blue = (37, 99, 235)
        c_green = (16, 185, 129)
        c_purple = (139, 92, 246)
        c_pink = (236, 72, 153)
        c_orange = (249, 115, 22)
        c_yellow = (250, 204, 21)
    else:
        card_tint = (16, 23, 42, 225)
        sub_card_tint = (26, 36, 62, 235)
        txt_main = (255, 255, 255, 255)
        txt_sub = (203, 213, 225, 245)
        stroke_c = (0, 0, 0, 210)
        stroke_w = 2
        c_blue = (59, 130, 246)
        c_green = (34, 197, 94)
        c_purple = (168, 85, 247)
        c_pink = (236, 72, 153)
        c_orange = (255, 107, 0)
        c_yellow = (250, 204, 21)

    draw = ImageDraw.Draw(canvas_rgba, "RGBA")

    # =========================================================================
    # النمط 1: saas_folder_reorder (بطاقة مجلد وقائمة عناصر تنزلق بالتتابع وتتبادل مواقعها)
    # =========================================================================
    if archetype == "saas_folder_reorder":
        s_in = 0.86 + 0.14 * _staggered_spring(scene_progress, delay=0.0, duration=0.38)
        cw, ch = int(sw * 0.90 * s_in), int(sh * 0.88 * s_in)
        bx1, by1 = cx - cw // 2, cy - ch // 2
        bx2, by2 = bx1 + cw, by1 + ch

        canvas_rgba = draw_visionos_glass_panel(
            canvas_rgba, (bx1, by1, bx2, by2), radius=26,
            tint_color=card_tint, border_color=c_blue,
            blur_radius=12, shadow_offset=10, shadow_blur=16
        )
        draw = ImageDraw.Draw(canvas_rgba, "RGBA")

        # رأس البطاقة: شارة حالة خضراء على اليسار + عنوان المجلد على اليمين
        hdr_h = int(ch * 0.18)
        pill_w, pill_h = int(cw * 0.28), max(32, int(hdr_h * 0.62))
        px1, py1 = bx1 + 20, by1 + (hdr_h - pill_h) // 2
        draw.rounded_rectangle([(px1, py1), (px1 + pill_w, py1 + pill_h)], radius=pill_h // 2, fill=(*c_green, 35), outline=(*c_green, 220), width=2)
        p_font, _, _ = get_fitted_arabic_font(draw, kpi_val, int(pill_w * 0.82), max(16, int(sh * 0.036)), bold=True)
        draw_arabic_text(draw, (px1 + pill_w // 2, py1 + pill_h // 2), kpi_val, font=p_font, fill=(*c_green, 255))

        hdr_font, _, _ = get_fitted_arabic_font(draw, concept_title, int(cw * 0.58), max(20, int(sh * 0.044)), bold=True)
        draw_arabic_text(draw, (bx2 - int(cw * 0.34), by1 + hdr_h // 2), concept_title, font=hdr_font, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)
        draw.line([(bx1 + 20, by1 + hdr_h), (bx2 - 20, by1 + hdr_h)], fill=(148, 163, 184, 65), width=2)

        # قائمة البطاقات الفرعية الـ 3 مع حركة تبادل المواقع على المحور Y
        list_y0 = by1 + hdr_h + int(ch * 0.05)
        row_h = int(ch * 0.21)
        row_gap = int(ch * 0.04)
        swap_p = _ease_in_out_cubic(max(0.0, min(1.0, (scene_progress - 0.48) / 0.38)))

        row_colors = [c_blue, c_purple, c_green]
        for i in range(3):
            row_spring = _staggered_spring(scene_progress, delay=0.06 + i * 0.08, duration=0.40)
            base_slot = float(i)
            if i == 0:
                eff_slot = base_slot + 1.0 * swap_p
            elif i == 1:
                eff_slot = base_slot - 1.0 * swap_p
            else:
                eff_slot = base_slot

            ry1 = int(list_y0 + eff_slot * (row_h + row_gap) + 35 * (1.0 - row_spring))
            rx1, rx2 = bx1 + int(cw * 0.06), bx2 - int(cw * 0.14)
            rc = row_colors[i % len(row_colors)]

            draw.rounded_rectangle([(rx1, ry1), (rx2, ry1 + row_h)], radius=16, fill=sub_card_tint, outline=(*rc, 195), width=2)
            # شريط جانبي ملون وأيقونة تشغيل
            draw.rounded_rectangle([(rx2 - 12, ry1 + 8), (rx2 - 4, ry1 + row_h - 8)], radius=4, fill=(*rc, 255))
            item_txt = str(sub_items[i])
            r_font, _, _ = get_fitted_arabic_font(draw, item_txt, int((rx2 - rx1) * 0.78), max(18, int(sh * 0.038)), bold=True)
            draw_arabic_text(draw, ((rx1 + rx2) // 2, ry1 + row_h // 2), item_txt, font=r_font, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

        # أسهم التبادل الجانبية الدوارة
        arr_cx = bx2 - int(cw * 0.07)
        arr_cy = list_y0 + row_h + row_gap // 2
        draw.ellipse([(arr_cx - 16, arr_cy - 16), (arr_cx + 16, arr_cy + 16)], fill=(*c_yellow, 45), outline=(*c_yellow, 230), width=2)
        draw.line([(arr_cx, arr_cy - 8), (arr_cx, arr_cy + 8)], fill=(*c_orange, 255), width=3)

    # =========================================================================
    # النمط 2: stage_trust_bubbles (عنصر مركزي + 4 فقاعات منبثقة Pop-in + شريط مؤشر سفلي)
    # =========================================================================
    elif archetype == "stage_trust_bubbles":
        # شاشة هاتف مركزية مصغرة
        pw, ph = int(sw * 0.30), int(sh * 0.56)
        px1, py1 = cx - pw // 2, y1 + int(sh * 0.06)
        draw.rounded_rectangle([(px1, py1), (px1 + pw, py1 + ph)], radius=24, fill=(15, 23, 42, 245), outline=(*c_blue, 235), width=3)
        draw.rounded_rectangle([(px1 + pw // 3, py1 + 10), (px1 + 2 * pw // 3, py1 + 16)], radius=3, fill=(100, 116, 139, 200))
        _draw_checkmark_badge(draw, cx, py1 + ph // 2, int(pw * 0.24), color_rgb=c_orange if "مشكلة" in kpi_val or "يعانون" in kpi_val else c_green)

        # 4 فقاعات محادثة منبثقة بتتابع حول الهاتف (Pop-in Spring)
        bubble_positions = [
            (x1 + int(sw * 0.03), y1 + int(sh * 0.06), int(sw * 0.42), int(sh * 0.19), c_blue),
            (x2 - int(sw * 0.45), y1 + int(sh * 0.06), int(sw * 0.42), int(sh * 0.19), c_purple),
            (x1 + int(sw * 0.03), y1 + int(sh * 0.34), int(sw * 0.42), int(sh * 0.19), c_pink),
            (x2 - int(sw * 0.45), y1 + int(sh * 0.34), int(sw * 0.42), int(sh * 0.19), c_orange),
        ]
        for bi, (bx, by, bw, bh, bcol) in enumerate(bubble_positions):
            b_pop = _staggered_spring(scene_progress, delay=0.05 + bi * 0.10, duration=0.36)
            if b_pop > 0.05:
                cur_w, cur_h = int(bw * b_pop), int(bh * b_pop)
                bcx, bcy = bx + bw // 2, by + bh // 2
                rx1, ry1 = bcx - cur_w // 2, bcy - cur_h // 2
                rx2, ry2 = rx1 + cur_w, ry1 + cur_h
                draw.rounded_rectangle([(rx1, ry1 + 4), (rx2, ry2 + 4)], radius=18, fill=(0, 0, 0, 85))
                draw.rounded_rectangle([(rx1, ry1), (rx2, ry2)], radius=18, fill=(255, 255, 255, 250), outline=(*bcol, 240), width=3)
                b_txt = str(sub_items[bi])
                bf, _, _ = get_fitted_arabic_font(draw, b_txt, int(cur_w * 0.84), max(16, int(sh * 0.035)), min_font_size=12, bold=True)
                draw_arabic_text(draw, (bcx, bcy), b_txt, font=bf, fill=(17, 24, 39, 255))

        # شريط المؤشر السفلي النابض (Trust / Impact Meter Bar)
        my1 = y1 + int(sh * 0.68)
        mh = int(sh * 0.24)
        mx1, mx2 = x1 + int(sw * 0.06), x2 - int(sw * 0.06)
        draw.rounded_rectangle([(mx1, my1), (mx2, my1 + mh)], radius=20, fill=card_tint, outline=(*c_orange, 220), width=2)
        mf, _, _ = get_fitted_arabic_font(draw, f"{concept_title} • {kpi_val}", int((mx2 - mx1) * 0.86), max(18, int(sh * 0.038)), bold=True)
        draw_arabic_text(draw, (cx, my1 + int(mh * 0.36)), f"{concept_title} • {kpi_val}", font=mf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

        bar_w = int((mx2 - mx1) * 0.82)
        bar_x1 = cx - bar_w // 2
        bar_y = my1 + int(mh * 0.72)
        fill_prog = min(1.0, 0.25 + 0.68 * _ease_out_cubic(scene_progress))
        draw.rounded_rectangle([(bar_x1, bar_y - 7), (bar_x1 + bar_w, bar_y + 7)], radius=7, fill=(148, 163, 184, 70))
        draw.rounded_rectangle([(bar_x1, bar_y - 7), (bar_x1 + int(bar_w * fill_prog), bar_y + 7)], radius=7, fill=(*c_orange, 255))

    # =========================================================================
    # النمط 3: stage_balance_scale (ميزان فيزيائي ذو كفتين: اليدوي/التكلفة مقابل الذكي/القيمة)
    # =========================================================================
    elif archetype == "stage_balance_scale":
        left_pan_info = scene_meta.get("balance_left") or ("المونتاج اليدوي", "4 ساعات عمل")
        right_pan_info = scene_meta.get("balance_right") or ("الذكاء الاصطناعي", "أقل من دقيقة")

        # زاوية ميلان ذراع الميزان بفيزياء النوابض بعد سقوط البطاقة
        tilt_prog = _staggered_spring(scene_progress, delay=0.15, duration=0.55)
        tilt_angle = math.radians(-14.0 * tilt_prog)

        pivot_x, pivot_y = cx, y1 + int(sh * 0.42)
        base_y = y1 + int(sh * 0.86)
        # عمود وقاعدة الميزان
        draw.line([(pivot_x, pivot_y), (pivot_x, base_y)], fill=(203, 213, 225, 230), width=8)
        draw.rounded_rectangle([(pivot_x - int(sw * 0.18), base_y - 8), (pivot_x + int(sw * 0.18), base_y + 8)], radius=8, fill=(*c_yellow, 240))
        draw.ellipse([(pivot_x - 14, pivot_y - 14), (pivot_x + 14, pivot_y + 14)], fill=(*c_yellow, 255), outline=(255, 255, 255, 240), width=3)

        arm_half = int(sw * 0.32)
        lx = pivot_x - int(arm_half * math.cos(tilt_angle))
        ly = pivot_y - int(arm_half * math.sin(tilt_angle))
        rx = pivot_x + int(arm_half * math.cos(tilt_angle))
        ry = pivot_y + int(arm_half * math.sin(tilt_angle))

        draw.line([(lx, ly), (rx, ry)], fill=(*c_yellow, 255), width=7)

        pan_w, pan_h = int(sw * 0.38), int(sh * 0.28)
        # الكفة اليسرى (التقليدي / الثقيل)
        l_box = (lx - pan_w // 2, ly + 18, lx + pan_w // 2, ly + 18 + pan_h)
        draw.line([(lx, ly), (lx - 24, ly + 18), (lx + 24, ly + 18), (lx, ly)], fill=(203, 213, 225, 190), width=2)
        draw.rounded_rectangle([(l_box[0], l_box[1]), (l_box[2], l_box[3])], radius=18, fill=(255, 255, 255, 248), outline=(239, 68, 68, 240), width=3)
        lf1, _, _ = get_fitted_arabic_font(draw, str(left_pan_info[0]), int(pan_w * 0.84), max(16, int(sh * 0.036)), bold=True)
        lf2, _, _ = get_fitted_arabic_font(draw, str(left_pan_info[1]), int(pan_w * 0.84), max(18, int(sh * 0.042)), bold=True)
        draw_arabic_text(draw, (lx, l_box[1] + int(pan_h * 0.34)), str(left_pan_info[0]), font=lf1, fill=(71, 85, 105, 255))
        draw_arabic_text(draw, (lx, l_box[1] + int(pan_h * 0.72)), str(left_pan_info[1]), font=lf2, fill=(239, 68, 68, 255))

        # الكفة اليمنى (الحل الذكي / الفائز)
        r_box = (rx - pan_w // 2, ry + 18, rx + pan_w // 2, ry + 18 + pan_h)
        draw.line([(rx, ry), (rx - 24, ry + 18), (rx + 24, ry + 18), (rx, ry)], fill=(203, 213, 225, 190), width=2)
        draw.rounded_rectangle([(r_box[0], r_box[1]), (r_box[2], r_box[3])], radius=18, fill=(255, 255, 255, 248), outline=(*c_green, 245), width=3)
        rf1, _, _ = get_fitted_arabic_font(draw, str(right_pan_info[0]), int(pan_w * 0.84), max(16, int(sh * 0.036)), bold=True)
        rf2, _, _ = get_fitted_arabic_font(draw, str(right_pan_info[1]), int(pan_w * 0.84), max(18, int(sh * 0.042)), bold=True)
        draw_arabic_text(draw, (rx, r_box[1] + int(pan_h * 0.34)), str(right_pan_info[0]), font=rf1, fill=(71, 85, 105, 255))
        draw_arabic_text(draw, (rx, r_box[1] + int(pan_h * 0.72)), str(right_pan_info[1]), font=rf2, fill=(*c_green, 255))

        # شارة علوية فوق الميزان
        top_lbl = f"{concept_title} ({kpi_val})"
        tf, tw, th = get_fitted_arabic_font(draw, top_lbl, int(sw * 0.82), max(18, int(sh * 0.040)), bold=True)
        draw.rounded_rectangle([(cx - tw // 2 - 20, y1 + 8), (cx + tw // 2 + 20, y1 + 8 + th + 16)], radius=(th + 16) // 2, fill=card_tint, outline=(*c_blue, 210), width=2)
        draw_arabic_text(draw, (cx, y1 + 8 + (th + 16) // 2), top_lbl, font=tf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

    # =========================================================================
    # النمط 4: saas_typewriter_mechanism (ترس ميكانيكي دوار + شريط بحث يكتب آلياً + كبسولات)
    # =========================================================================
    elif archetype == "saas_typewriter_mechanism":
        # شريط الآلية العلوي مع الترس الدوار
        mech_y = y1 + int(sh * 0.12)
        _draw_gear_icon(draw, cx + int(sw * 0.32), mech_y, int(sh * 0.055), global_t * 2.4, c_blue)
        mf, _, _ = get_fitted_arabic_font(draw, concept_title, int(sw * 0.62), max(20, int(sh * 0.044)), bold=True)
        draw_arabic_text(draw, (cx - int(sw * 0.04), mech_y), concept_title, font=mf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

        # شريط البحث التفاعلي بكتابة آلية (Typewriter Effect + Blinking Caret)
        type_text = str(scene_meta.get("typewriter_query") or concept_title)
        chars_to_show = max(1, int(len(type_text) * min(1.0, scene_progress / 0.62)))
        visible_str = type_text[:chars_to_show]
        pulse_s = 1.0 + (0.035 * math.sin((scene_progress - 0.62) * 10.0) if scene_progress > 0.62 else 0.0)

        sb_w = int(sw * 0.88 * pulse_s)
        sb_h = int(sh * 0.22 * pulse_s)
        sb_x1, sb_y1 = cx - sb_w // 2, y1 + int(sh * 0.25)
        draw.rounded_rectangle([(sb_x1, sb_y1 + 5), (sb_x1 + sb_w, sb_y1 + sb_h + 5)], radius=22, fill=(0, 0, 0, 75))
        draw.rounded_rectangle([(sb_x1, sb_y1), (sb_x1 + sb_w, sb_y1 + sb_h)], radius=22, fill=(255, 255, 255, 252), outline=(*c_blue, 245), width=3)

        tf, tw, th = get_fitted_arabic_font(draw, visible_str, int(sb_w * 0.78), max(22, int(sh * 0.048)), bold=True)
        draw_arabic_text(draw, (cx, sb_y1 + sb_h // 2), visible_str, font=tf, fill=(17, 24, 39, 255))

        # مؤشر الكتابة النابض (Caret)
        if int(global_t * 4) % 2 == 0:
            caret_x = cx - tw // 2 - 8 if re.search(r"[؀-ۿ]", visible_str) else cx + tw // 2 + 8
            draw.line([(caret_x, sb_y1 + int(sb_h * 0.25)), (caret_x, sb_y1 + int(sb_h * 0.75))], fill=(*c_blue, 255), width=3)

        # 4 كبسولات ميزات سفلية تظهر بالتتابع
        grid_y0 = sb_y1 + sb_h + int(sh * 0.07)
        pw = int(sw * 0.42)
        ph = int(sh * 0.18)
        cols = [c_blue, c_green, c_purple, c_orange]
        for i in range(4):
            sp = _staggered_spring(scene_progress, delay=0.15 + i * 0.08, duration=0.38)
            col_idx = i % 2
            row_idx = i // 2
            px = (cx - pw - 10) if col_idx == 0 else (cx + 10)
            py = int(grid_y0 + row_idx * (ph + 12) + 25 * (1.0 - sp))
            c_rgb = cols[i]
            draw.rounded_rectangle([(px, py), (px + pw, py + ph)], radius=16, fill=card_tint, outline=(*c_rgb, 215), width=2)
            pf, _, _ = get_fitted_arabic_font(draw, str(sub_items[i]), int(pw * 0.85), max(16, int(sh * 0.035)), bold=True)
            draw_arabic_text(draw, (px + pw // 2, py + ph // 2), str(sub_items[i]), font=pf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

    # =========================================================================
    # النمط 5: saas_process_flow (3 بطاقات متدرجة + منحنى بياني تتبعه أيقونة ذكية)
    # =========================================================================
    elif archetype == "saas_process_flow":
        cw = int(sw * 0.88)
        # 1. البطاقة العلوية: شريط التقدم الذكي
        c1_h = int(sh * 0.22)
        c1_y = y1 + int(sh * 0.04)
        draw.rounded_rectangle([(cx - cw // 2, c1_y), (cx + cw // 2, c1_y + c1_h)], radius=20, fill=card_tint, outline=(*c_blue, 215), width=2)
        f1, _, _ = get_fitted_arabic_font(draw, f"{concept_title} ({kpi_val})", int(cw * 0.84), max(18, int(sh * 0.038)), bold=True)
        draw_arabic_text(draw, (cx, c1_y + int(c1_h * 0.36)), f"{concept_title} ({kpi_val})", font=f1, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)
        bar_w = int(cw * 0.82)
        fill_w = int(bar_w * min(1.0, 0.15 + 0.85 * _ease_in_out_cubic(scene_progress)))
        draw.rounded_rectangle([(cx - bar_w // 2, c1_y + int(c1_h * 0.72) - 6), (cx + bar_w // 2, c1_y + int(c1_h * 0.72) + 6)], radius=6, fill=(148, 163, 184, 70))
        draw.rounded_rectangle([(cx - bar_w // 2, c1_y + int(c1_h * 0.72) - 6), (cx - bar_w // 2 + fill_w, c1_y + int(c1_h * 0.72) + 6)], radius=6, fill=(*c_blue, 255))

        # 2. البطاقة الوسطى: منحنى صعود تتبعه عقدة ذكية (Motion Path Follower)
        c2_h = int(sh * 0.38)
        c2_y = c1_y + c1_h + int(sh * 0.04)
        draw.rounded_rectangle([(cx - cw // 2, c2_y), (cx + cw // 2, c2_y + c2_h)], radius=20, fill=card_tint, outline=(*c_purple, 215), width=2)
        gx1, gx2 = cx - int(cw * 0.40), cx + int(cw * 0.40)
        gy_bot, gy_top = c2_y + int(c2_h * 0.80), c2_y + int(c2_h * 0.22)

        curve_pts = []
        steps = 28
        active_steps = max(2, int(steps * min(1.0, scene_progress * 1.25)))
        for si in range(active_steps):
            u = si / float(steps - 1)
            px = int(gx1 + (gx2 - gx1) * u)
            py = int(gy_bot - (gy_bot - gy_top) * (0.15 + 0.72 * u + 0.14 * math.sin(u * math.pi * 2.5)))
            curve_pts.append((px, py))

        if len(curve_pts) >= 2:
            draw.line(curve_pts, fill=(*c_blue, 255), width=5)
            head_x, head_y = curve_pts[-1]
            draw.ellipse([(head_x - 14, head_y - 14), (head_x + 14, head_y + 14)], fill=(*c_yellow, 255), outline=(255, 255, 255, 255), width=3)

        # 3. البطاقة السفلية: الاكتشاف والنتيجة النهائية
        sp3 = _staggered_spring(scene_progress, delay=0.22, duration=0.42)
        c3_h = int(sh * 0.22)
        c3_y = int(c2_y + c2_h + int(sh * 0.04) + 20 * (1.0 - sp3))
        draw.rounded_rectangle([(cx - cw // 2, c3_y), (cx + cw // 2, c3_y + c3_h)], radius=20, fill=(*c_purple, 230), outline=(255, 255, 255, 220), width=2)
        f3, _, _ = get_fitted_arabic_font(draw, f"{sub_items[2]} • {sub_items[3]}", int(cw * 0.86), max(18, int(sh * 0.038)), bold=True)
        draw_arabic_text(draw, (cx, c3_y + c3_h // 2), f"{sub_items[2]} • {sub_items[3]}", font=f3, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 180))

    # =========================================================================
    # النمط 6: saas_grid_2x2_cursor (شبكة رباعية 2x2 + أشرطة تقدم + مؤشر ماوس ينقر مع Ripple)
    # =========================================================================
    elif archetype == "saas_grid_2x2_cursor":
        gap_x, gap_y = int(sw * 0.04), int(sh * 0.04)
        card_w = (int(sw * 0.90) - gap_x) // 2
        card_h = (int(sh * 0.84) - gap_y) // 2
        start_x = cx - (card_w * 2 + gap_x) // 2
        start_y = cy - (card_h * 2 + gap_y) // 2

        grid_colors = [c_blue, c_purple, c_pink, c_green]
        target_click_xy = (cx, cy)

        for idx in range(4):
            row = idx // 2
            col = idx % 2
            sp = _staggered_spring(scene_progress, delay=idx * 0.08, duration=0.40)
            gx1 = start_x + col * (card_w + gap_x)
            gy1 = int(start_y + row * (card_h + gap_y) + 28 * (1.0 - sp))
            gx2, gy2 = gx1 + card_w, gy1 + card_h
            gcol = grid_colors[idx]

            if idx == 3:
                target_click_xy = (gx1 + int(card_w * 0.24), gy1 + int(card_h * 0.80))

            draw.rounded_rectangle([(gx1, gy1 + 4), (gx2, gy2 + 4)], radius=22, fill=(0, 0, 0, 75))
            draw.rounded_rectangle([(gx1, gy1), (gx2, gy2)], radius=22, fill=card_tint, outline=(*gcol, 235), width=3)

            # دائرة أيقونة علوية داخل كل بطاقة
            ic_x, ic_y = (gx1 + gx2) // 2, gy1 + int(card_h * 0.28)
            draw.ellipse([(ic_x - 18, ic_y - 18), (ic_x + 18, ic_y + 18)], fill=(*gcol, 45), outline=(*gcol, 240), width=2)
            draw.ellipse([(ic_x - 7, ic_y - 7), (ic_x + 7, ic_y + 7)], fill=(*gcol, 255))

            # عنوان البطاقة
            lbl_txt = str(sub_items[idx])
            gf, _, _ = get_fitted_arabic_font(draw, lbl_txt, int(card_w * 0.84), max(17, int(sh * 0.036)), bold=True)
            draw_arabic_text(draw, ((gx1 + gx2) // 2, gy1 + int(card_h * 0.58)), lbl_txt, font=gf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

            # شريط التقدم الملون المتزامن
            pw = int(card_w * 0.76)
            px1 = (gx1 + gx2) // 2 - pw // 2
            py = gy1 + int(card_h * 0.82)
            fill_p = min(1.0, max(0.15, (scene_progress - idx * 0.08) * 1.35))
            draw.rounded_rectangle([(px1, py - 5), (px1 + pw, py + 5)], radius=5, fill=(148, 163, 184, 70))
            draw.rounded_rectangle([(px1, py - 5), (px1 + int(pw * fill_p), py + 5)], radius=5, fill=(*gcol, 255))

        # حركة مؤشر الماوس نحو البطاقة الرابعة والنقر عليها مع التموج (Ripple)
        _draw_cursor_with_ripple(draw, (x2 - 20, y2 - 20), target_click_xy, scene_progress, accent_rgb=c_green)

    # =========================================================================
    # النمط 7: stage_before_after_checklist (مقارنة قبل/بعد + قائمة تدقيق بعلامات صح ✔️)
    # =========================================================================
    elif archetype == "stage_before_after_checklist":
        ba_info = scene_meta.get("before_after") or ("قبل: يدوي مرهق", "4.1", "بعد: ذكي فوري", "9.8")
        top_h = int(sh * 0.42)
        card_w = int(sw * 0.40)

        # بطاقة "قبل" (اليمين)
        bef_x1 = x2 - int(sw * 0.05) - card_w
        bef_y1 = y1 + int(sh * 0.04)
        draw.rounded_rectangle([(bef_x1, bef_y1), (bef_x1 + card_w, bef_y1 + top_h)], radius=20, fill=card_tint, outline=(239, 68, 68, 235), width=3)
        draw.rounded_rectangle([(bef_x1 + 16, bef_y1 + 12), (bef_x1 + card_w - 16, bef_y1 + 42)], radius=15, fill=(239, 68, 68, 240))
        bf_font, _, _ = get_fitted_arabic_font(draw, f"قبل • {ba_info[1]}", int(card_w * 0.75), max(16, int(sh * 0.034)), bold=True)
        draw_arabic_text(draw, (bef_x1 + card_w // 2, bef_y1 + 27), f"قبل • {ba_info[1]}", font=bf_font, fill=(255, 255, 255, 255))
        b_desc_f, _, _ = get_fitted_arabic_font(draw, str(ba_info[0]), int(card_w * 0.84), max(16, int(sh * 0.036)), bold=True)
        draw_arabic_text(draw, (bef_x1 + card_w // 2, bef_y1 + int(top_h * 0.56)), str(ba_info[0]), font=b_desc_f, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)
        draw.rounded_rectangle([(bef_x1 + 20, bef_y1 + int(top_h * 0.80)), (bef_x1 + card_w - 20, bef_y1 + int(top_h * 0.80) + 8)], radius=4, fill=(148, 163, 184, 70))
        draw.rounded_rectangle([(bef_x1 + 20, bef_y1 + int(top_h * 0.80)), (bef_x1 + 20 + int((card_w - 40) * 0.36), bef_y1 + int(top_h * 0.80) + 8)], radius=4, fill=(239, 68, 68, 255))

        # سهم التحول المتحرك في المنتصف
        arr_shift = int(8 * math.sin(global_t * 6.0))
        draw.ellipse([(cx - 18 + arr_shift, bef_y1 + top_h // 2 - 18), (cx + 18 + arr_shift, bef_y1 + top_h // 2 + 18)], fill=(*c_yellow, 255))
        draw.line([(cx + 8 + arr_shift, bef_y1 + top_h // 2), (cx - 8 + arr_shift, bef_y1 + top_h // 2)], fill=(17, 24, 39, 255), width=3)

        # بطاقة "بعد" (اليسار) مع عداد التقييم الصاعد
        aft_x1 = x1 + int(sw * 0.05)
        draw.rounded_rectangle([(aft_x1, bef_y1), (aft_x1 + card_w, bef_y1 + top_h)], radius=20, fill=card_tint, outline=(*c_green, 245), width=3)
        draw.rounded_rectangle([(aft_x1 + 16, bef_y1 + 12), (aft_x1 + card_w - 16, bef_y1 + 42)], radius=15, fill=(*c_green, 245))
        draw_arabic_text(draw, (aft_x1 + card_w // 2, bef_y1 + 27), f"بعد • {ba_info[3]}", font=bf_font, fill=(255, 255, 255, 255))
        a_desc_f, _, _ = get_fitted_arabic_font(draw, str(ba_info[2]), int(card_w * 0.84), max(16, int(sh * 0.036)), bold=True)
        draw_arabic_text(draw, (aft_x1 + card_w // 2, bef_y1 + int(top_h * 0.56)), str(ba_info[2]), font=a_desc_f, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)
        draw.rounded_rectangle([(aft_x1 + 20, bef_y1 + int(top_h * 0.80)), (aft_x1 + card_w - 20, bef_y1 + int(top_h * 0.80) + 8)], radius=4, fill=(148, 163, 184, 70))
        draw.rounded_rectangle([(aft_x1 + 20, bef_y1 + int(top_h * 0.80)), (aft_x1 + 20 + int((card_w - 40) * min(0.96, 0.35 + 0.65 * scene_progress)), bef_y1 + int(top_h * 0.80) + 8)], radius=4, fill=(*c_green, 255))

        # قائمة التدقيق السفلية (Checklist Card with Sequential Green Checkmarks ✔️)
        chk_y1 = bef_y1 + top_h + int(sh * 0.05)
        chk_h = int(sh * 0.46)
        chk_w = int(sw * 0.90)
        draw.rounded_rectangle([(cx - chk_w // 2, chk_y1), (cx + chk_w // 2, chk_y1 + chk_h)], radius=22, fill=card_tint, outline=(*c_blue, 215), width=2)

        for ci in range(3):
            ry = chk_y1 + int(chk_h * 0.20) + ci * int(chk_h * 0.28)
            is_checked = scene_progress >= (0.15 + ci * 0.22)
            chk_col = c_green if is_checked else (100, 116, 139)
            _draw_checkmark_badge(draw, cx + int(chk_w * 0.38), ry, 13, color_rgb=chk_col, scale=1.1 if is_checked else 0.85)
            c_txt = str(sub_items[ci])
            cf, _, _ = get_fitted_arabic_font(draw, c_txt, int(chk_w * 0.72), max(16, int(sh * 0.035)), bold=True)
            draw_arabic_text(draw, (cx - int(chk_w * 0.04), ry), c_txt, font=cf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

    # =========================================================================
    # النمط 8: interactive_cta_outro (بطاقة التفاعل الختامية بخطوتين + طائرة ورقية ✈️ + نقرة ماوس)
    # =========================================================================
    else:
        s_in = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.0, duration=0.40)
        cw, ch = int(sw * 0.90 * s_in), int(sh * 0.84 * s_in)
        bx1, by1 = cx - cw // 2, cy - ch // 2
        bx2, by2 = bx1 + cw, by1 + ch

        canvas_rgba = draw_visionos_glass_panel(
            canvas_rgba, (bx1, by1, bx2, by2), radius=28,
            tint_color=card_tint, border_color=c_blue,
            blur_radius=14, shadow_offset=12, shadow_blur=18
        )
        draw = ImageDraw.Draw(canvas_rgba, "RGBA")

        # العنوان الرئيسي للخاتمة
        hf, _, _ = get_fitted_arabic_font(draw, concept_title, int(cw * 0.84), max(22, int(sh * 0.046)), bold=True)
        draw_arabic_text(draw, (cx, by1 + int(ch * 0.18)), concept_title, font=hf, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

        # الخطوة 1: مشاركة / متابعة مع طائرة ورقية متحركة قطرياً ✈️
        r1_y = by1 + int(ch * 0.34)
        r1_h = int(ch * 0.24)
        draw.rounded_rectangle([(bx1 + 22, r1_y), (bx2 - 22, r1_y + r1_h)], radius=18, fill=sub_card_tint, outline=(*c_blue, 200), width=2)
        plane_p = _ease_out_cubic(min(1.0, scene_progress * 1.3))
        _draw_paper_plane(draw, bx1 + 48 + int(18 * plane_p), r1_y + r1_h // 2 - int(10 * plane_p), 16, color_rgb=c_blue)
        s1_f, _, _ = get_fitted_arabic_font(draw, f"1. {sub_items[0]}", int(cw * 0.68), max(17, int(sh * 0.036)), bold=True)
        draw_arabic_text(draw, (cx + 16, r1_y + r1_h // 2), f"1. {sub_items[0]}", font=s1_f, fill=txt_main, stroke_width=stroke_w, stroke_fill=stroke_c)

        # الخطوة 2: زر الـ CTA الأصفر/الأزرق التفاعلي مع نقرة الماوس والتموج
        r2_y = by1 + int(ch * 0.66)
        r2_h = int(ch * 0.24)
        pulse = int(4 * math.sin(global_t * 6.0))
        btn_box = (bx1 + 22 - pulse, r2_y - pulse // 2, bx2 - 22 + pulse, r2_y + r2_h + pulse // 2)
        draw.rounded_rectangle([(btn_box[0], btn_box[1]), (btn_box[2], btn_box[3])], radius=18, fill=(*c_yellow, 255), outline=(*c_orange, 255), width=3)
        cta_txt = f"{kpi_val} • {kpi_lbl}"
        s2_f, _, _ = get_fitted_arabic_font(draw, cta_txt, int(cw * 0.78), max(19, int(sh * 0.040)), bold=True)
        draw_arabic_text(draw, (cx, r2_y + r2_h // 2), cta_txt, font=s2_f, fill=(17, 24, 39, 255))

        _draw_cursor_with_ripple(draw, (bx2 - 15, by2 - 10), (bx1 + int(cw * 0.22), r2_y + int(r2_h * 0.72)), scene_progress, accent_rgb=c_orange)

    return canvas_rgba


# ==============================================================================
# 8. تصيير مشهد موشن جرافيك كامل الشاشة موجه بالسياق (Contextual Bento Scene)
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
    تصيير مشهد موشن جرافيك كامل الشاشة بأسلوب الفيديوهات الاحترافية المرجعية (101bdarija Clean SaaS & moujtabakhalifa Dark Stage):
    - شارة رقم المرحلة أعلى اليسار (`#1`, `#2`...) + شارة الموضوع السياقية أعلى اليمين (`badge_label`).
    - مسرح كوريغرافيا متحرك بالكامل يعرض أحد الأنماط الـ 8 المتقدمة (`render_choreographed_stage_archetype`).
    - كابشن سفلي ديناميكي بتمييز أصفر (`#FACC15`) للكلمة المفتاحية النشطة.
    """
    theme_name = scene_meta.get("theme_name", "cyber_gold")
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    badge_label = scene_meta.get("badge_label", "موشن جرافيك سياقي")
    step_badge = scene_meta.get("step_badge", "#1")
    style_mode = scene_meta.get("style_mode", "dark_stage_split")
    is_light = (style_mode == "clean_saas_light")

    bg_key = f"{theme_name}_{style_mode}_{width}x{height}"
    if bg_key not in bg_cache:
        if is_light:
            # خلفية Clean SaaS الفاتحة الهادئة (#EEF2F6) كما في الفيديو المرجعي الأول
            y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
            top_c = np.array([240, 244, 248], dtype=np.float32)
            bot_c = np.array([226, 232, 240], dtype=np.float32)
            grad = (top_c * (1.0 - y_idx) + bot_c * y_idx).astype(np.uint8)
            bg_cache[bg_key] = np.broadcast_to(grad, (height, width, 3)).copy()
        else:
            bg_cache[bg_key] = create_studio_background(width, height, theme_name)

    base_arr = bg_cache[bg_key]
    img = Image.fromarray(base_arr, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    cx = width // 2

    # إضاءة كشاف المسرح العلوي في الوضع الداكن (Spotlight Cone من الفيديو المرجعي الثاني)
    if not is_light:
        cone = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(cone, "RGBA")
        c_draw.polygon([
            (cx - int(width * 0.12), 0),
            (cx + int(width * 0.12), 0),
            (cx + int(width * 0.48), int(height * 0.68)),
            (cx - int(width * 0.48), int(height * 0.68))
        ], fill=(255, 235, 180, 22))
        img = Image.alpha_composite(img, cone)
        draw = ImageDraw.Draw(img, "RGBA")

    # 1. شارة رقم المشهد على اليسار (#1, #2) + الشارة السياقية الكبسولية على اليمين (HUD Top Layer)
    s_badge = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.01, duration=0.36)
    bp_y = int(height * 0.045 - 18 * (1.0 - s_badge))
    badge_font, btw, bth = get_fitted_arabic_font(
        draw, badge_label, max_width=int(width * 0.66),
        initial_font_size=max(20, int(min(width, height) * 0.031)), bold=True
    )
    bp_h = max(48, bth + 22)
    bp_w = min(int(width * 0.74), btw + 56)

    # شارة الترقيم الملونة أعلى اليسار (#1..#8)
    step_w = max(54, int(width * 0.11))
    sx1 = int(width * 0.05)
    draw.rounded_rectangle([(sx1, bp_y), (sx1 + step_w, bp_y + bp_h)], radius=bp_h // 2, fill=(37, 99, 235, 245), outline=(255, 255, 255, 220), width=2)
    st_font, _, _ = get_fitted_arabic_font(draw, step_badge, int(step_w * 0.8), max(20, int(min(width, height) * 0.032)), bold=True)
    draw_arabic_text(draw, (sx1 + step_w // 2, bp_y + bp_h // 2), step_badge, font=st_font, fill=(255, 255, 255, 255))

    # كبسولة الموضوع أعلى اليمين
    px2 = int(width * 0.95)
    px1 = max(sx1 + step_w + 12, px2 - bp_w)
    pill_bg = (255, 255, 255, 248) if is_light else (15, 23, 42, 230)
    pill_txt_c = (17, 24, 39, 255) if is_light else (255, 255, 255, 250)
    draw.rounded_rectangle([(px1, bp_y + 4), (px2, bp_y + bp_h + 4)], radius=bp_h // 2, fill=(0, 0, 0, 55))
    draw.rounded_rectangle([(px1, bp_y), (px2, bp_y + bp_h)], radius=bp_h // 2, fill=pill_bg, outline=(*theme["primary"], 220), width=2)
    dot_x = px2 - 22
    draw.ellipse([(dot_x - 6, bp_y + bp_h // 2 - 6), (dot_x + 6, bp_y + bp_h // 2 + 6)], fill=(16, 185, 129, 255))
    draw_arabic_text(draw, ((px1 + dot_x - 8) // 2, bp_y + bp_h // 2), badge_label, font=badge_font, fill=pill_txt_c)

    # 2. مسرح الكوريغرافيا الرئيسي (يحتل 62% من ارتفاع الشاشة)
    stage_box = (
        int(width * 0.04),
        int(height * 0.115),
        int(width * 0.96),
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

    # 3. كابشن الكاريوكي الموحد مع مستطيل أصفر (#FACC15) للكلمة المفتاحية النشطة
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.81),
        theme=theme
    )

    # 4. شريط التقدم الزمني السفلي الأنيق
    draw = ImageDraw.Draw(img, "RGBA")
    prog_w = int(width * 0.86 * min(1.0, max(0.02, global_t / max(0.1, total_duration))))
    bar_x1 = (width - int(width * 0.86)) // 2
    bar_y = int(height * 0.93)
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + int(width * 0.86), bar_y + 7)], radius=4, fill=(148, 163, 184, 75))
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + prog_w, bar_y + 7)], radius=4, fill=(37, 99, 235, 255) if is_light else (*theme["primary"], 245))

    return img


# ==============================================================================
# 9. محرك الانتقالات السينمائية مع التمويه الحركي (Transitions with Motion Blur)
# ==============================================================================
def apply_scene_transition(
    prev_img: Image.Image,
    curr_img: Image.Image,
    trans_progress: float,
    transition_type: str
) -> Image.Image:
    p = _spring_physics(trans_progress, stiffness=190.0, damping=18.0)
    w, h = curr_img.size

    blur_strength = int(10 * math.sin(max(0.0, min(1.0, trans_progress)) * math.pi))

    if transition_type == "whip_left":
        offset = int(w * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        p_frame = prev_img.filter(ImageFilter.BoxBlur(blur_strength)) if blur_strength > 1 else prev_img
        c_frame = curr_img.filter(ImageFilter.BoxBlur(blur_strength)) if blur_strength > 1 else curr_img
        out.paste(p_frame, (-int(w * p), 0))
        out.paste(c_frame, (offset, 0))
        return out

    elif transition_type == "whip_up":
        offset = int(h * (1.0 - p))
        out = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        p_frame = prev_img.filter(ImageFilter.BoxBlur(blur_strength)) if blur_strength > 1 else prev_img
        c_frame = curr_img.filter(ImageFilter.BoxBlur(blur_strength)) if blur_strength > 1 else curr_img
        out.paste(p_frame, (0, -int(h * p)))
        out.paste(c_frame, (0, offset))
        return out

    elif transition_type == "zoom_portal":
        scale = 0.55 + 0.45 * p
        zw, zh = max(20, int(w * scale)), max(20, int(h * scale))
        resized_curr = curr_img.resize((zw, zh), Image.Resampling.BILINEAR)
        out = prev_img.copy()
        if blur_strength > 1:
            out = out.filter(ImageFilter.GaussianBlur(radius=blur_strength // 2))
        paste_x, paste_y = (w - zw) // 2, (h - zh) // 2
        alpha_mask = Image.new("L", (zw, zh), int(255 * min(1.0, trans_progress * 1.6)))
        out.paste(resized_curr, (paste_x, paste_y), alpha_mask)
        return out

    else:
        return Image.blend(prev_img, curr_img, max(0.0, min(1.0, p)))


# ==============================================================================
# 10. محرك الكابشن الكاريوكي الموحد بتصميم الزجاج الحقيقي (1-Line VisionOS Karaoke)
# ==============================================================================
def _render_unified_karaoke_subtitle(
    img: Image.Image,
    sc_words: List[str],
    act_word: str,
    w_prog: float,
    cap_y: int,
    theme: Dict[str, Any]
):
    w, h = img.size
    cx = w // 2
    clean_sc_words = [re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(wd)).strip() for wd in sc_words if str(wd).strip()]
    clean_act_word = re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(act_word)).strip() if act_word else (clean_sc_words[0] if clean_sc_words else "")

    if not clean_sc_words and not clean_act_word:
        return

    font_size = max(32, int(min(w, h) * 0.044))
    cap_font = get_arabic_font(font_size, bold=True)
    pop_scale = _spring_physics(min(1.0, w_prog * 2.5), stiffness=240.0, damping=14.0)
    active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)

    active_word_clean = clean_act_word.lower()
    target_idx = 0
    for wi, cw in enumerate(clean_sc_words):
        if cw.lower() == active_word_clean or active_word_clean in cw.lower():
            target_idx = wi
            break

    # نافذة سياقية مريحة تعرض حتى 5 كلمات متتالية من الجملة داخل كبسولة الكابشن
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
    word_spaces = int(font_size * 0.48)
    for wi, dw in enumerate(display_words):
        f_use = active_font if wi == disp_active_idx else cap_font
        ww, wh = measure_arabic_text(draw, dw, f_use)
        if wi == disp_active_idx:
            ww += 16
        word_widths.append((ww, wh))

    total_line_w = sum(ww for ww, _ in word_widths) + (len(display_words) - 1) * word_spaces
    # إذا كان السطر طويلاً جداً، نصغر الخط تلقائياً ليتسع داخل الكبسولة الزجاجية بأناقة
    if total_line_w > int(w * 0.82):
        scale_down = (w * 0.80) / float(total_line_w)
        font_size = max(24, int(font_size * scale_down))
        cap_font = get_arabic_font(font_size, bold=True)
        active_font = get_arabic_font(int(font_size * (1.0 + 0.08 * pop_scale)), bold=True)
        word_spaces = int(font_size * 0.44)
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
        tint_color=(8, 12, 24, 205),
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
                fill=(248, 250, 252, 240),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 230)
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
    theme_name = sc.get("theme_name", "cyber_gold")
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    sc_dur = max(0.18, sc["end"] - sc["start"])
    sc_prog = max(0.0, min(1.0, (t - sc["start"]) / sc_dur))

    sc_words = sc.get("word_strings", [])
    act_word = sc_words[0] if sc_words else sc.get("short_title", "")
    w_prog = 0.5
    for w_obj in sc.get("words", []):
        ws = float(w_obj.get("start", 0.0))
        we = float(w_obj.get("end", ws + 0.3))
        if t >= ws - 0.04:
            act_word = w_obj.get("word", "")
            wdur = max(0.10, we - ws)
            w_prog = max(0.0, min(1.0, (t - ws) / wdur))

    if layout_mode == "split_screen_stage":
        # معمارية الشاشة المقسومة الاحترافية (moujtabakhalifa Split-Screen Stage + Speaker PIP):
        # النصف العلوي (0% -> 53%): مسرح موشن جرافيك داكن مع كشاف ضوئي وكوريغرافيا متحركة
        # النصف السفلي (55% -> 94%): كادر الفيديو الحقيقي للمتحدث داخل إطار أصفر (#FACC15) بحواف دائرية
        # الكبسولة الفاصلة (عند 54%): كابشن أبيض/زجاجي عريض يربط المسرح بالمتحدث
        canvas = Image.new("RGBA", (w, h), (17, 19, 23, 255))
        c_draw = ImageDraw.Draw(canvas, "RGBA")
        cx = w // 2

        # كشاف إضاءة علوي دافئ بشفافية حقيقية (Spotlight Cone Alpha Composite)
        cone_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(cone_layer, "RGBA").polygon([
            (cx - int(w * 0.14), 0),
            (cx + int(w * 0.14), 0),
            (cx + int(w * 0.46), int(h * 0.52)),
            (cx - int(w * 0.46), int(h * 0.52))
        ], fill=(255, 230, 170, 22))
        canvas = Image.alpha_composite(canvas, cone_layer)
        c_draw = ImageDraw.Draw(canvas, "RGBA")

        # شارة الترقيم والشارة العلوية في المسرح العلوي
        badge_title = sc.get("badge_label", sc.get("concept_title", "ميزة ذكية"))
        step_badge = sc.get("step_badge", f"#{active_idx + 1}")
        bf, btw, bth = get_fitted_arabic_font(c_draw, badge_title, int(w * 0.68), max(18, int(min(w, h) * 0.028)), bold=True)
        bp_h = max(40, bth + 16)
        bp_y = int(h * 0.025)
        c_draw.rounded_rectangle([(int(w * 0.05), bp_y), (int(w * 0.16), bp_y + bp_h)], radius=bp_h // 2, fill=(255, 107, 0, 255))
        draw_arabic_text(c_draw, (int(w * 0.105), bp_y + bp_h // 2), step_badge, font=bf, fill=(255, 255, 255, 255))

        px2 = int(w * 0.95)
        px1 = max(int(w * 0.18), px2 - min(int(w * 0.74), btw + 44))
        c_draw.rounded_rectangle([(px1, bp_y), (px2, bp_y + bp_h)], radius=bp_h // 2, fill=(26, 32, 48, 240), outline=(250, 204, 21, 220), width=2)
        draw_arabic_text(c_draw, ((px1 + px2) // 2, bp_y + bp_h // 2), badge_title, font=bf, fill=(255, 255, 255, 250))

        # رسم الكوريغرافيا في المسرح العلوي
        stage_bbox = (int(w * 0.04), int(h * 0.095), int(w * 0.96), int(h * 0.51))
        canvas = render_choreographed_stage_archetype(
            canvas_rgba=canvas,
            stage_bbox=stage_bbox,
            scene_meta=sc,
            scene_progress=sc_prog,
            global_t=t,
            theme=theme,
            is_light_saas=False
        )

        # وضع فيديو المتحدث في الإطار السفلي (Speaker PIP Frame with #FACC15 Yellow Border)
        pip_x1, pip_y1 = int(w * 0.05), int(h * 0.56)
        pip_x2, pip_y2 = int(w * 0.95), int(h * 0.94)
        pip_w, pip_h = pip_x2 - pip_x1, pip_y2 - pip_y1
        spk_pil = Image.fromarray(base_frame_rgb, mode="RGB").resize((pip_w, pip_h), Image.Resampling.BILINEAR).convert("RGBA")
        pip_mask = Image.new("L", (pip_w, pip_h), 0)
        ImageDraw.Draw(pip_mask).rounded_rectangle([(0, 0), (pip_w - 1, pip_h - 1)], radius=28, fill=255)
        canvas.paste(spk_pil, (pip_x1, pip_y1), pip_mask)

        c_draw = ImageDraw.Draw(canvas, "RGBA")
        c_draw.rounded_rectangle([(pip_x1, pip_y1), (pip_x2 - 1, pip_y2 - 1)], radius=28, outline=(250, 204, 21, 255), width=5)

        if caption_mode != "none" and (act_word or sc_words):
            _render_unified_karaoke_subtitle(
                img=canvas,
                sc_words=sc_words,
                act_word=act_word,
                w_prog=w_prog,
                cap_y=int(h * 0.545),
                theme=theme
            )
        return np.array(canvas.convert("RGB"))

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
        time_into_scene = t - sc["start"]
        if active_idx > 0 and 0.0 <= time_into_scene < 0.28:
            prev_base = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
            blended = apply_scene_transition(prev_base, curr_img, time_into_scene / 0.28, sc.get("transition", "zoom_portal"))
            return np.array(blended.convert("RGB"))
        return np.array(curr_img.convert("RGB"))

    img = Image.fromarray(base_frame_rgb, mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    cx = w // 2

    if layout_mode == "top_overlay":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        y_slide_offset = int(-95 * (1.0 - spring_in))

        badge_title = sc.get("badge_label", sc.get("concept_title", "ميزة حصرية"))
        title_font, tw, th = get_fitted_arabic_font(draw, badge_title, max_width=int(w * 0.65), initial_font_size=max(22, int(min(w, h) * 0.032)), min_font_size=14, bold=True)

        icon_box = max(44, th + 18)
        pill_h = max(54, th + 24)
        pill_w = min(int(w * 0.88), max(tw + icon_box + 56, int(w * 0.42)))
        top_y = int(h * 0.045) + y_slide_offset
        x1, y1 = cx - pill_w // 2, top_y
        x2, y2 = cx + pill_w // 2, top_y + pill_h

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(x1, y1, x2, y2),
            radius=pill_h // 2,
            tint_color=(10, 16, 30, 195),
            border_color=theme["primary"],
            secondary_color=theme["secondary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=18,
            light_sweep_prog=(sc_prog * 1.5 - 0.1)
        )

        mini_icon = render_cairo_vector_illustration(
            scene_type=sc.get("scene_type", "ecommerce_showcase"),
            width=icon_box,
            height=icon_box,
            scene_progress=sc_prog,
            global_t=t,
            theme=theme,
            target_number=sc.get("target_number", 17)
        )
        icon_x = x2 - icon_box - 10
        icon_y = y1 + (pill_h - icon_box) // 2
        img.alpha_composite(mini_icon, (icon_x, icon_y))

        draw = ImageDraw.Draw(img, "RGBA")
        text_cx = x1 + (icon_x - x1) // 2 + 6
        draw_arabic_text(
            draw,
            (text_cx, y1 + pill_h // 2),
            badge_title,
            font=title_font,
            fill=(255, 255, 255, 250),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 220)
        )

    elif layout_mode == "lower_third":
        spring_in = _spring_physics(min(1.0, (t - sc["start"]) / 0.32), stiffness=210.0, damping=15.0)
        l3_txt = sc.get("badge_label", "ميزة حصرية")
        l3_font, tw, th = get_fitted_arabic_font(draw, l3_txt, max_width=int(w * 0.78), initial_font_size=max(22, int(min(w, h) * 0.032)), min_font_size=14, bold=True)
        bar_w = min(int(w * 0.88), tw + 74)
        bar_h = max(50, th + 24)
        by1 = int(h * 0.86 + 60 * (1.0 - spring_in))
        by2 = by1 + bar_h
        bx1 = cx - bar_w // 2
        bx2 = cx + bar_w // 2

        img = draw_visionos_glass_panel(
            canvas_rgba=img,
            bbox=(bx1, by1, bx2, by2),
            radius=bar_h // 2,
            tint_color=(10, 16, 28, 205),
            border_color=theme["primary"],
            blur_radius=14,
            shadow_offset=10,
            shadow_blur=16,
            light_sweep_prog=(sc_prog * 1.4)
        )
        draw = ImageDraw.Draw(img, "RGBA")
        draw_arabic_text(
            draw,
            (cx, by1 + bar_h // 2),
            l3_txt,
            font=l3_font,
            fill=(*theme["primary"], 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 235)
        )

    if caption_mode != "none" and (act_word or sc_words):
        if caption_mode == "top_compact":
            cap_y = int(h * 0.14)
        elif layout_mode == "lower_third":
            cap_y = int(h * 0.77)
        else:
            cap_y = int(h * 0.84)

        _render_unified_karaoke_subtitle(
            img=img,
            sc_words=sc_words,
            act_word=act_word,
            w_prog=w_prog,
            cap_y=cap_y,
            theme=theme
        )

    return np.array(img.convert("RGB"))


# ==============================================================================
# 12. المسار الرئيسي لتوليد فيديو الموشن جرافيك السياقي الكامل (Studio Kinetic Typography)
# ==============================================================================
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
            w_p = 0.5
            for w_obj in sc.get("words", []):
                ws = float(w_obj.get("start", 0.0))
                we = float(w_obj.get("end", ws + 0.3))
                if t >= ws - 0.04:
                    act_w = w_obj.get("word", "")
                    w_p = max(0.0, min(1.0, (t - ws) / max(0.10, we - ws)))

            curr_img = render_single_scene_canvas(
                scene_meta=sc,
                active_word=act_w,
                scene_words=sc_words,
                active_word_idx=0,
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
            if active_idx > 0 and 0.0 <= time_into < 0.28:
                prev_sc = planned_scenes[active_idx - 1]
                prev_img = render_single_scene_canvas(
                    scene_meta=prev_sc,
                    active_word="",
                    scene_words=prev_sc.get("word_strings", []),
                    active_word_idx=0,
                    word_local_progress=1.0,
                    scene_progress=1.0,
                    global_t=t,
                    total_duration=total_dur,
                    audio_level=0.8,
                    width=vw,
                    height=vh,
                    bg_cache=bg_cache
                )
                curr_img = apply_scene_transition(prev_img, curr_img, time_into / 0.28, sc.get("transition", "zoom_portal"))

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