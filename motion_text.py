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
    تصيير مشهد موشن جرافيك كامل الشاشة بأسلوب Apple Keynote / Stripe Bento Grid:
    - بطاقة علوية ديناميكية (Dynamic Island Header) تعرض مرحلة السرد السياقية (`badge_label`).
    - بطاقة Bento رئيسية (Hero Vector Canvas) مع شريط عنوان macOS ورسمة فيكتور سياقية.
    - البطاقة اليمنى (Contextual KPI Card): تعرض المؤشر الرقمي السياقي المستنتج من معنى الجملة والفيديو.
    - البطاقة اليسرى (Contextual Concept Card): تعرض المفهوم الضمني للجملة (وليس تكرار الكلمات المنطوقة!).
    - كابشن كاريوكي زجاجي موحد في الثلث السفلي + طيف صوتي تفاعلي.
    """
    theme_name = scene_meta.get("theme_name", "cyber_gold")
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    scene_type = scene_meta.get("scene_type", "video_montage_studio")
    badge_label = scene_meta.get("badge_label", "موشن جرافيك احترافي")
    concept_title = scene_meta.get("concept_title") or scene_meta.get("short_title") or "مفهوم ذكي"
    target_number = int(scene_meta.get("target_number", 17))

    if theme_name not in bg_cache:
        bg_cache[theme_name] = create_studio_background(width, height, theme_name)
    base_arr = bg_cache[theme_name]
    img = Image.fromarray(base_arr, mode="RGB").convert("RGBA")

    cx = width // 2
    s_card = 0.88 + 0.12 * _staggered_spring(scene_progress, delay=0.0, duration=0.40)
    s_sub_left = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.08, duration=0.45)
    s_sub_right = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.14, duration=0.48)

    # 1. شارة العنوان العلوية بأسلوب Apple Dynamic Pill
    draw = ImageDraw.Draw(img, "RGBA")
    s_badge = 0.85 + 0.15 * _staggered_spring(scene_progress, delay=0.02, duration=0.40)
    badge_font = get_arabic_font(max(24, int(min(width, height) * 0.032)), bold=True)
    btw, bth = measure_arabic_text(draw, badge_label, badge_font)
    bp_w = min(int(width * 0.88), btw + 80)
    bp_h = max(52, bth + 24)
    bp_y = int(height * 0.052 - 20 * (1.0 - s_badge))

    img = draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(cx - bp_w // 2, bp_y, cx + bp_w // 2, bp_y + bp_h),
        radius=bp_h // 2,
        tint_color=(10, 16, 30, 215),
        border_color=theme["secondary"],
        blur_radius=12,
        shadow_offset=8,
        shadow_blur=14
    )
    draw = ImageDraw.Draw(img, "RGBA")
    dot_x = cx + bp_w // 2 - 24
    draw.ellipse([(dot_x - 6, bp_y + bp_h // 2 - 6), (dot_x + 6, bp_y + bp_h // 2 + 6)], fill=(*theme["primary"], 255))
    draw_arabic_text(draw, (cx - 8, bp_y + bp_h // 2), badge_label, font=badge_font, fill=(255, 255, 255, 250), stroke_width=2, stroke_fill=(0, 0, 0, 210))

    # 2. بطاقة الـ Bento الرئيسية الكبرى (Hero Vector Studio Card)
    bento_w = int(width * 0.88 * s_card)
    bento_h = int(height * 0.37 * s_card)
    bento_y1 = int(height * 0.125 + 24 * (1.0 - s_card))
    bento_x1 = cx - bento_w // 2
    bento_x2 = cx + bento_w // 2
    bento_y2 = bento_y1 + bento_h

    img = draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(bento_x1, bento_y1, bento_x2, bento_y2),
        radius=34,
        tint_color=(*theme["card_bg"], 200),
        border_color=theme["primary"],
        secondary_color=theme["secondary"],
        blur_radius=16,
        shadow_offset=16,
        shadow_blur=22,
        light_sweep_prog=(scene_progress * 1.35 - 0.08)
    )

    draw = ImageDraw.Draw(img, "RGBA")
    hdr_y = bento_y1 + 24
    for bi, bcol in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        bx = bento_x1 + 28 + bi * 20
        draw.ellipse([(bx - 6, hdr_y - 6), (bx + 6, hdr_y + 6)], fill=(*bcol, 235))
    draw.line([(bento_x1 + 16, bento_y1 + 46), (bento_x2 - 16, bento_y1 + 46)], fill=(255, 255, 255, 28), width=1)

    vec_w = max(80, int(bento_w * 0.96))
    vec_h = max(80, int((bento_h - 52) * 0.96))
    vec_img = render_cairo_vector_illustration(
        scene_type=scene_type,
        width=vec_w,
        height=vec_h,
        scene_progress=scene_progress,
        global_t=global_t,
        theme=theme,
        target_number=target_number
    )
    img.alpha_composite(vec_img, (cx - vec_w // 2, bento_y1 + 48 + (bento_h - 48 - vec_h) // 2))

    # 3. بطاقتا الـ Bento الفرعيتان جنباً إلى جنب (Contextual KPI + Contextual Concept Cards)
    gap = int(width * 0.03)
    total_w = int(width * 0.88)
    sub_w = (total_w - gap) // 2
    sub_h = int(height * 0.145)
    sub_y1 = bento_y2 + int(height * 0.022)

    # أ) البطاقة اليمنى: بطاقة المؤشر الرقمي السياقي (Contextual KPI Metric Card)
    rx1 = cx + gap // 2
    rx2 = rx1 + sub_w
    ry1 = int(sub_y1 + 22 * (1.0 - s_sub_right))
    ry2 = ry1 + sub_h

    img = draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(rx1, ry1, rx2, ry2),
        radius=26,
        tint_color=(12, 19, 38, 210),
        border_color=theme["secondary"],
        blur_radius=12,
        shadow_offset=10,
        shadow_blur=16
    )
    draw = ImageDraw.Draw(img, "RGBA")

    default_kpi_map = {
        "creator_profile": (f"{target_number} عاماً", "مؤسس ومطور شاب"),
        "age_number_counter": (f"{target_number} سنة", "محطة طموح مبكرة"),
        "video_montage_studio": ("4K 60FPS", "جودة إخراج سينمائية"),
        "ai_neural_brain": ("100% تلقائي", "يعمل بالذكاء الاصطناعي"),
        "reels_smartphone": ("يومياً", "نشر ريلز مستمر"),
        "growth_analytics": ("+300%", "مضاعفة الإنتاجية"),
        "ecommerce_showcase": ("100%", "ضمان الجودة والمتانة"),
        "delivery_express": (f"{target_number} ولاية", "تغطية التوصيل"),
        "time_warp_clock": ("10x أسرع", "توفير وقت الصناع"),
        "platform_builder": ("Full-Stack", "تطوير وبناء المنصة"),
        "brand_finale": ("AI Studio", "منصة الجيل الجديد"),
    }
    fallback_val, fallback_lbl = default_kpi_map.get(scene_type, ("AI Pro", "أداء ذكي متكامل"))
    kpi_val = str(scene_meta.get("kpi_value") or fallback_val)
    kpi_lbl = str(scene_meta.get("kpi_label") or fallback_lbl)

    kpi_val_font = get_arabic_font(max(30, int(min(width, height) * 0.042)), bold=True)
    kpi_lbl_font = get_arabic_font(max(20, int(min(width, height) * 0.025)), bold=True)

    rcx = (rx1 + rx2) // 2
    draw_arabic_text(draw, (rcx, ry1 + int(sub_h * 0.38)), kpi_val, font=kpi_val_font, fill=(*theme["primary"], 255), stroke_width=2, stroke_fill=(0, 0, 0, 220))
    draw_arabic_text(draw, (rcx, ry1 + int(sub_h * 0.74)), kpi_lbl, font=kpi_lbl_font, fill=(215, 225, 245, 240))

    # ب) البطاقة اليسرى: بطاقة المفهوم السياقي (Contextual Concept Card - لا تكرر الكلمات المنطوقة!)
    lx1 = cx - gap // 2 - sub_w
    lx2 = lx1 + sub_w
    ly1 = int(sub_y1 + 22 * (1.0 - s_sub_left))
    ly2 = ly1 + sub_h

    img = draw_visionos_glass_panel(
        canvas_rgba=img,
        bbox=(lx1, ly1, lx2, ly2),
        radius=26,
        tint_color=(12, 19, 38, 210),
        border_color=theme["primary"],
        blur_radius=12,
        shadow_offset=10,
        shadow_blur=16
    )
    draw = ImageDraw.Draw(img, "RGBA")
    lcx = (lx1 + lx2) // 2
    feat_font = get_arabic_font(max(22, int(min(width, height) * 0.030)), bold=True)
    clean_concept = re.sub(r"^[،,.\s!؟:؛-]+|[،,.\s!؟:؛-]+$", "", str(concept_title)).strip() or "فكرة محورية"
    draw_arabic_text(draw, (lcx, ly1 + int(sub_h * 0.38)), clean_concept, font=feat_font, fill=(255, 255, 255, 250), stroke_width=2, stroke_fill=(0, 0, 0, 220))

    # شريط طاقة متحرك أنيق داخل البطاقة اليسرى
    pbar_w = int(sub_w * 0.74)
    pbar_x1 = lcx - pbar_w // 2
    pbar_y = ly1 + int(sub_h * 0.75)
    fill_w = max(16, int(pbar_w * min(1.0, 0.28 + 0.72 * scene_progress)))
    draw.rounded_rectangle([(pbar_x1, pbar_y - 6), (pbar_x1 + pbar_w, pbar_y + 6)], radius=6, fill=(255, 255, 255, 38))
    draw.rounded_rectangle([(pbar_x1, pbar_y - 6), (pbar_x1 + fill_w, pbar_y + 6)], radius=6, fill=(*theme["secondary"], 245))

    # 4. كابشن الكاريوكي الموحد في الثلث السفلي
    _render_unified_karaoke_subtitle(
        img=img,
        sc_words=scene_words,
        act_word=active_word,
        w_prog=word_local_progress,
        cap_y=int(height * 0.78),
        theme=theme
    )

    # 5. موجات الطيف الصوتي التفاعلية السفلية (Audio-Reactive Equalizer Bars)
    draw = ImageDraw.Draw(img, "RGBA")
    num_eq = 28
    eq_total_w = int(width * 0.68)
    eq_x0 = cx - eq_total_w // 2
    eq_spacing = eq_total_w // num_eq
    eq_base_y = int(height * 0.895)
    for ei in range(num_eq):
        wave = abs(math.sin(global_t * 6.5 + ei * 0.45)) * abs(math.cos(global_t * 3.2 - ei * 0.25))
        bh = int(6 + 22 * wave * audio_level)
        ex = eq_x0 + ei * eq_spacing
        ecol = (*theme["primary"], 195) if ei % 2 == 0 else (*theme["secondary"], 195)
        draw.rounded_rectangle([(ex, eq_base_y - bh), (ex + 5, eq_base_y + bh)], radius=2, fill=ecol)

    # 6. شريط التقدم الزمني السفلي الأنيق
    prog_w = int(width * 0.84 * min(1.0, max(0.02, global_t / max(0.1, total_duration))))
    bar_x1 = (width - int(width * 0.84)) // 2
    bar_y = int(height * 0.94)
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + int(width * 0.84), bar_y + 6)], radius=3, fill=(255, 255, 255, 40))
    draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + prog_w, bar_y + 6)], radius=3, fill=(*theme["primary"], 245))

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
            hl_pad_x, hl_pad_y = 4, 6
            draw.rounded_rectangle(
                [(word_cx - ww // 2 - hl_pad_x, cap_y - wh // 2 - hl_pad_y),
                 (word_cx + ww // 2 + hl_pad_x, cap_y + wh // 2 + hl_pad_y)],
                radius=12,
                fill=(*theme["primary"], 55)
            )
            draw_arabic_text(
                draw,
                (word_cx, cap_y),
                dw,
                font=active_font,
                fill=(255, 230, 0, 255),
                stroke_width=3,
                stroke_fill=(0, 0, 0, 245)
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
        title_font = get_arabic_font(max(24, int(min(w, h) * 0.033)), bold=True)
        tw, th = measure_arabic_text(draw, badge_title, title_font)

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
        l3_font = get_arabic_font(max(24, int(min(w, h) * 0.033)), bold=True)
        l3_txt = sc.get("badge_label", "ميزة حصرية")
        tw, th = measure_arabic_text(draw, l3_txt, l3_font)
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

        fps = 24
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
            "-crf", "24", "-pix_fmt", "yuv420p", "-threads", "1",
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