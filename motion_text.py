"""
motion_text.py - محرك الموشن جرافيك الاحترافي والأنفوجرافيك المتحرك وعناصر إعلانات المنتجات
==========================================================================================
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy لمنع خطأ 'PIL.Image' has no attribute 'ANTIALIAS'
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
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features

from transcriber import transcribe_audio, transcribe_sentences

try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. إعداد الخطوط العربية وتشكيل الحروف السليم
# ==============================================================================
_FONT_DOWNLOAD_ATTEMPTED = False
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
    """قياس عرض وارتفاع النص العربي."""
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
    """جلب أفضل خط عربي متوفر مع تحميل تلقائي لـ Cairo-Bold عند توفر الإنترنت."""
    global _FONT_DOWNLOAD_ATTEMPTED
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
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue

    return ImageFont.load_default()


# ==============================================================================
# 2. الثيمات اللونية ورسام الأيقونات الفيكتور
# ==============================================================================
MOTION_THEMES = {
    "cyber_gold": {
        "top_bg": (11, 17, 34),
        "bottom_bg": (26, 20, 56),
        "glow": (56, 189, 248),
        "primary": (255, 225, 0),
        "secondary": (0, 245, 212),
        "card_bg": (15, 23, 42, 215)
    },
    "emerald_tech": {
        "top_bg": (6, 26, 23),
        "bottom_bg": (15, 46, 42),
        "glow": (16, 185, 129),
        "primary": (52, 211, 153),
        "secondary": (251, 191, 36),
        "card_bg": (8, 32, 28, 215)
    },
    "royal_purple": {
        "top_bg": (22, 12, 40),
        "bottom_bg": (45, 22, 74),
        "glow": (236, 72, 153),
        "primary": (255, 190, 11),
        "secondary": (255, 77, 141),
        "card_bg": (28, 16, 50, 215)
    },
    "crimson_energy": {
        "top_bg": (26, 10, 16),
        "bottom_bg": (52, 16, 28),
        "glow": (249, 115, 22),
        "primary": (255, 230, 0),
        "secondary": (255, 123, 0),
        "card_bg": (34, 12, 20, 215)
    }
}


def draw_procedural_vector_icon(
    icon_type: str,
    size: int = 140,
    accent_color: Tuple[int, int, int] = (255, 225, 0),
    secondary_color: Tuple[int, int, int] = (0, 245, 212)
) -> Image.Image:
    """رسم أيقونة فيكتور عالية الدقة داخل درع زجاجي مضيء."""
    ss = 2
    dim = size * ss
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = dim // 2, dim // 2
    r_outer = int(dim * 0.44)

    draw.ellipse(
        [(cx - r_outer - 6, cy - r_outer - 6), (cx + r_outer + 6, cy + r_outer + 6)],
        fill=(accent_color[0], accent_color[1], accent_color[2], 45)
    )
    draw.ellipse(
        [(cx - r_outer, cy - r_outer), (cx + r_outer, cy + r_outer)],
        fill=(18, 25, 45, 230),
        outline=(*accent_color, 240),
        width=6
    )
    r_inner = int(r_outer * 0.84)
    draw.arc(
        [(cx - r_inner, cy - r_inner), (cx + r_inner, cy + r_inner)],
        start=200, end=340,
        fill=(*secondary_color, 190),
        width=4
    )

    fg = (*accent_color, 255)
    fg2 = (*secondary_color, 255)
    white = (255, 255, 255, 255)

    if icon_type in {"money", "finance", "growth", "chart"}:
        bar_w = int(dim * 0.08)
        base_y = cy + int(dim * 0.18)
        heights = [int(dim * 0.14), int(dim * 0.24), int(dim * 0.35)]
        xs = [cx - int(dim * 0.16), cx, cx + int(dim * 0.16)]
        for bx, bh in zip(xs, heights):
            draw.rounded_rectangle(
                [(bx - bar_w // 2, base_y - bh), (bx + bar_w // 2, base_y)],
                radius=6,
                fill=fg2 if bh < heights[-1] else fg
            )
        pts = [(xs[0], base_y - heights[0] - 12), (xs[1], base_y - heights[1] - 16), (xs[2], base_y - heights[2] - 20)]
        draw.line(pts, fill=white, width=7)

    elif icon_type in {"time", "clock", "speed"}:
        cr = int(dim * 0.22)
        draw.ellipse([(cx - cr, cy - cr), (cx + cr, cy + cr)], outline=white, width=6)
        draw.line([(cx, cy), (cx, cy - int(cr * 0.65))], fill=fg, width=7)
        draw.line([(cx, cy), (cx + int(cr * 0.55), cy + int(cr * 0.2))], fill=fg2, width=6)
        draw.ellipse([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill=fg)

    elif icon_type in {"idea", "brain", "ai", "light"}:
        br = int(dim * 0.16)
        by = cy - int(dim * 0.04)
        draw.ellipse([(cx - br, by - br), (cx + br, by + br)], fill=fg, outline=white, width=5)
        draw.rounded_rectangle(
            [(cx - int(br * 0.55), by + br - 4), (cx + int(br * 0.55), by + br + int(dim * 0.11))],
            radius=6,
            fill=fg2
        )
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + int((br + 12) * math.cos(rad))
            y1 = by + int((br + 12) * math.sin(rad))
            x2 = cx + int((br + 26) * math.cos(rad))
            y2 = by + int((br + 26) * math.sin(rad))
            draw.line([(x1, y1), (x2, y2)], fill=white, width=5)

    elif icon_type in {"question", "search", "why", "how"}:
        lr = int(dim * 0.16)
        lx, ly = cx - int(dim * 0.05), cy - int(dim * 0.05)
        draw.ellipse([(lx - lr, ly - lr), (lx + lr, ly + lr)], outline=fg, width=8)
        draw.line(
            [(lx + int(lr * 0.7), ly + int(lr * 0.7)), (lx + int(lr * 1.65), ly + int(lr * 1.65))],
            fill=fg2,
            width=10
        )

    elif icon_type in {"code", "tech", "system"}:
        offset = int(dim * 0.16)
        h_off = int(dim * 0.12)
        draw.line([(cx - offset // 2, cy - h_off), (cx - offset, cy), (cx - offset // 2, cy + h_off)], fill=fg2, width=7)
        draw.line([(cx + offset // 2, cy - h_off), (cx + offset, cy), (cx + offset // 2, cy + h_off)], fill=fg2, width=7)
        draw.line([(cx + 12, cy - h_off - 6), (cx - 12, cy + h_off + 6)], fill=fg, width=7)

    elif icon_type in {"warning", "alert", "fire", "important"}:
        bolt = [
            (cx + 10, cy - int(dim * 0.24)),
            (cx - int(dim * 0.14), cy + 4),
            (cx + 2, cy + 4),
            (cx - 12, cy + int(dim * 0.24)),
            (cx + int(dim * 0.15), cy - 6),
            (cx - 2, cy - 6),
        ]
        draw.polygon(bolt, fill=fg, outline=white)

    else:
        points = []
        outer_r = int(dim * 0.22)
        inner_r = int(dim * 0.10)
        for i in range(10):
            ang = math.radians(i * 36 - 90)
            r = outer_r if i % 2 == 0 else inner_r
            points.append((cx + int(r * math.cos(ang)), cy + int(r * math.sin(ang))))
        draw.polygon(points, fill=fg, outline=white)

    return img.resize((size, size), Image.Resampling.LANCZOS)


# ==============================================================================
# 3. تحليل الجمل واستخراج الكلمة المفتاحية
# ==============================================================================
def analyze_sentence_visual_metadata(
    sentence: str,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, str]:
    """استخراج الكلمة المفتاحية وفئة الأيقونة."""
    if not sentence or not sentence.strip():
        return {"keyword": "نقطة مهمة", "icon_type": "success"}

    s_lower = sentence.strip()
    heuristic_icon = "success"
    if any(w in s_lower for w in ["دراهم", "مال", "ربح", "سومة", "سعر", "مشروع", "بيع", "شراء", "تجارة", "دولار", "دينار", "ثروة"]):
        heuristic_icon = "money"
    elif any(w in s_lower for w in ["وقت", "ساعة", "نهار", "يوم", "بكري", "درك", "دوكا", "سرعة", "تاريخ", "دقيقة"]):
        heuristic_icon = "time"
    elif any(w in s_lower for w in ["علاش", "كيفاش", "واش", "شكون", "وين", "سؤال", "مشكل", "سبب", "طريقة", "؟"]):
        heuristic_icon = "question"
    elif any(w in s_lower for w in ["ذكاء", "فكرة", "عفسة", "معلومة", "تعلم", "قراية", "فهم", "عقل", "إبداع", "سر"]):
        heuristic_icon = "idea"
    elif any(w in s_lower for w in ["برمجة", "تطبيق", "موقع", "تليفون", "انترنت", "كود", "خوارزمية", "حاسوب", "فيديو"]):
        heuristic_icon = "code"
    elif any(w in s_lower for w in ["رد بالك", "خطير", "مهم", "بزاف", "لازم", "ضروري", "غلط", "احذر", "قوة"]):
        heuristic_icon = "warning"

    prompt = (
        f"الجملة التالية بالدارجة الجزائرية أو العربية: \"{sentence}\"\n"
        "استخرج منها:\n"
        "1. keyword: عنوان جذاب مختصر جداً (كلمة أو كلمتين فقط) يمثل الفكرة الرئيسية.\n"
        "2. icon_type: اختر قيمة واحدة فقط من القائمة: [idea, money, time, question, code, warning, success].\n"
        "أرجع JSON فقط بهذا الشكل: {\"keyword\": \"...\", \"icon_type\": \"...\"}"
    )

    ai_resp = query_hybrid_llm(
        prompt=prompt,
        system_prompt="أنت مخرج موشن جرافيك محترف يفهم الدارجة الجزائرية والعربية. أرجع JSON فقط.",
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        ollama_model=model_name,
        ollama_url=ollama_url,
        temperature=0.2,
        max_tokens=100
    )

    if ai_resp:
        try:
            match = re.search(r"\{.*?\}", ai_resp, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                kw = str(data.get("keyword", "")).strip()
                ic = str(data.get("icon_type", heuristic_icon)).strip().lower()
                if kw and len(kw) <= 28:
                    if ic not in {"idea", "money", "time", "question", "code", "warning", "success"}:
                        ic = heuristic_icon
                    return {"keyword": kw, "icon_type": ic}
        except Exception:
            pass

    stop_words = {
        "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "هاذ", "هذيك", "اللي", "التي",
        "الذي", "أن", "إن", "ما", "لا", "كان", "هو", "هي", "راكم", "راني", "باش", "كيما"
    }
    words = [w for w in re.findall(r"[\w\u0621-\u064A]+", sentence) if w not in stop_words and len(w) > 2]
    keyword = words[0] if words else "فكرة أساسية"
    if len(words) >= 2 and len(words[0]) + len(words[1]) < 14:
        keyword = f"{words[0]} {words[1]}"
    return {"keyword": keyword, "icon_type": heuristic_icon}


def extract_keyword_ollama(
    sentence: str,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434"
) -> str:
    meta = analyze_sentence_visual_metadata(sentence, model_name=model_name, ollama_url=ollama_url)
    return meta["keyword"]


def find_matching_icon(keyword: str, icons_dir: str = "assets/icons") -> Optional[str]:
    if not keyword or not os.path.exists(icons_dir):
        return None
    kw = keyword.strip().lower()
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    for fname in os.listdir(icons_dir):
        base, ext = os.path.splitext(fname.lower())
        if ext in valid_exts and (base == kw or kw in base or base in kw):
            return os.path.join(icons_dir, fname)
    return None


# ==============================================================================
# 4. توليد الخلفية السينمائية وبطاقات الموشن جرافيك
# ==============================================================================
def create_studio_background(
    width: int,
    height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """إنشاء خلفية موشن جرافيك سينمائية."""
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    top_c = np.array(theme["top_bg"], dtype=np.float32)
    bot_c = np.array(theme["bottom_bg"], dtype=np.float32)
    glow_c = np.array(theme["glow"], dtype=np.float32)

    y_idx = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    grad = top_c * (1.0 - y_idx) + bot_c * y_idx
    canvas_np = np.broadcast_to(grad, (height, width, 3)).copy()

    yy, xx = np.ogrid[:height, :width]
    cx, cy = width * 0.5, height * 0.45
    dist_sq = ((xx - cx) / (width * 0.55)) ** 2 + ((yy - cy) / (height * 0.42)) ** 2
    radial_mask = np.exp(-dist_sq * 1.8)[:, :, None] * 0.24
    canvas_np = np.clip(canvas_np * (1.0 - radial_mask) + glow_c * radial_mask, 0, 255).astype(np.uint8)

    img = Image.fromarray(canvas_np, mode="RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    step = max(60, min(width, height) // 12)
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 10), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 10), width=1)

    pad = 36
    corner_len = 55
    acc = (*theme["secondary"], 110)
    draw.line([(pad, pad), (pad + corner_len, pad)], fill=acc, width=3)
    draw.line([(pad, pad), (pad, pad + corner_len)], fill=acc, width=3)
    draw.line([(width - pad - corner_len, pad), (width - pad, pad)], fill=acc, width=3)
    draw.line([(width - pad, pad), (width - pad, pad + corner_len)], fill=acc, width=3)
    draw.line([(pad, height - pad), (pad + corner_len, height - pad)], fill=acc, width=3)
    draw.line([(pad, height - pad - corner_len), (pad, height - pad)], fill=acc, width=3)
    draw.line([(width - pad - corner_len, height - pad), (width - pad, height - pad)], fill=acc, width=3)
    draw.line([(width - pad, height - pad - corner_len), (width - pad, height - pad)], fill=acc, width=3)

    return np.array(img)


def render_kinetic_frame(
    current_word: str,
    prev_word: Optional[str],
    video_width: int,
    video_height: int,
    icon_path: Optional[str] = None,
    keyword_title: Optional[str] = None,
    icon_type: str = "success",
    phrase_words: Optional[List[str]] = None,
    active_word_index: int = 0,
    progress_ratio: float = 0.0,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """تصيير إطار موشن جرافيك شفاف (RGBA)."""
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    center_x = video_width // 2
    center_y = video_height // 2

    main_font_size = max(50, int(min(video_width, video_height) * 0.082))
    phrase_font_size = max(32, int(main_font_size * 0.56))
    badge_font_size = max(26, int(main_font_size * 0.44))

    main_font = get_arabic_font(main_font_size, bold=True)
    phrase_font = get_arabic_font(phrase_font_size, bold=True)
    badge_font = get_arabic_font(badge_font_size, bold=False)

    icon_size = max(110, int(min(video_width, video_height) * 0.14))
    icon_y = center_y - int(main_font_size * 2.55)

    icon_img = None
    if icon_path and os.path.exists(icon_path):
        try:
            icon_img = Image.open(icon_path).convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        except Exception:
            icon_img = None

    if icon_img is None:
        icon_img = draw_procedural_vector_icon(
            icon_type=icon_type,
            size=icon_size,
            accent_color=theme["primary"],
            secondary_color=theme["secondary"]
        )

    icon_x = center_x - (icon_size // 2)
    if icon_y > 20:
        canvas.paste(icon_img, (icon_x, icon_y), icon_img)

    if keyword_title:
        kw_y = icon_y + icon_size + int(badge_font_size * 0.85)
        kw_w, kw_h = measure_arabic_text(draw, keyword_title, badge_font)
        pill_pad_x = 28
        pill_pad_y = 12
        draw.rounded_rectangle(
            [(center_x - kw_w // 2 - pill_pad_x, kw_y - kw_h // 2 - pill_pad_y),
             (center_x + kw_w // 2 + pill_pad_x, kw_y + kw_h // 2 + pill_pad_y)],
            radius=24,
            fill=(15, 23, 42, 220),
            outline=(*theme["secondary"], 200),
            width=2
        )
        draw_arabic_text(
            draw,
            (center_x, kw_y),
            keyword_title,
            font=badge_font,
            fill=(*theme["secondary"], 255)
        )

    if prev_word and prev_word != current_word:
        prev_y = center_y - int(main_font_size * 0.95)
        pw, ph = measure_arabic_text(draw, prev_word, badge_font)
        draw.rounded_rectangle(
            [(center_x - pw // 2 - 22, prev_y - ph // 2 - 10),
             (center_x + pw // 2 + 22, prev_y + ph // 2 + 10)],
            radius=16,
            fill=(20, 26, 45, 135)
        )
        draw_arabic_text(
            draw,
            (center_x, prev_y),
            prev_word,
            font=badge_font,
            fill=(190, 205, 220, 195)
        )

    curr_y = center_y + int(main_font_size * 0.20)
    cw, ch = measure_arabic_text(draw, current_word, main_font)
    pad_x = max(42, int(main_font_size * 0.65))
    pad_y = max(24, int(main_font_size * 0.38))

    box_x1 = center_x - cw // 2 - pad_x
    box_y1 = curr_y - ch // 2 - pad_y
    box_x2 = center_x + cw // 2 + pad_x
    box_y2 = curr_y + ch // 2 + pad_y

    draw.rounded_rectangle(
        [(box_x1 - 6, box_y1 - 6), (box_x2 + 6, box_y2 + 6)],
        radius=28,
        fill=(*theme["primary"], 45)
    )
    draw.rounded_rectangle(
        [(box_x1, box_y1), (box_x2, box_y2)],
        radius=24,
        fill=theme["card_bg"],
        outline=(*theme["primary"], 230),
        width=4
    )
    draw.rounded_rectangle(
        [(box_x2 - 12, box_y1 + 14), (box_x2 - 6, box_y2 - 14)],
        radius=3,
        fill=(*theme["secondary"], 255)
    )

    draw_arabic_text(
        draw,
        (center_x, curr_y),
        current_word,
        font=main_font,
        fill=(*theme["primary"], 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220)
    )

    if phrase_words and len(phrase_words) > 1:
        phrase_text = " ".join(phrase_words)
        sub_y = box_y2 + int(phrase_font_size * 1.45)
        sw, sh = measure_arabic_text(draw, phrase_text, phrase_font)
        max_bar_w = int(video_width * 0.88)
        bar_w = min(max_bar_w, sw + 48)
        draw.rounded_rectangle(
            [(center_x - bar_w // 2, sub_y - sh // 2 - 14),
             (center_x + bar_w // 2, sub_y + sh // 2 + 14)],
            radius=18,
            fill=(10, 15, 30, 195),
            outline=(255, 255, 255, 65),
            width=1
        )
        draw_arabic_text(
            draw,
            (center_x, sub_y),
            phrase_text,
            font=phrase_font,
            fill=(245, 247, 250, 240)
        )

    if progress_ratio > 0:
        bar_margin = int(video_width * 0.12)
        bar_y = video_height - 56
        full_w = video_width - 2 * bar_margin
        prog_w = int(full_w * min(1.0, max(0.02, progress_ratio)))
        draw.rounded_rectangle(
            [(bar_margin, bar_y), (bar_margin + full_w, bar_y + 10)],
            radius=5,
            fill=(255, 255, 255, 45)
        )
        draw.rounded_rectangle(
            [(bar_margin, bar_y), (bar_margin + prog_w, bar_y + 10)],
            radius=5,
            fill=(*theme["secondary"], 240)
        )

    return np.array(canvas)


def render_video_motion_overlay_card(
    keyword_title: str,
    icon_type: str,
    video_width: int,
    video_height: int,
    mode: str = "corner_card",
    subtitle_line: str = "",
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """توليد طبقة موشن جرافيك شفافة للدمج فوق الفيديو الأصلي."""
    theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    title_font_size = max(28, int(min(video_width, video_height) * 0.042))
    title_font = get_arabic_font(title_font_size, bold=True)

    icon_size = max(68, int(min(video_width, video_height) * 0.085))
    icon_img = draw_procedural_vector_icon(
        icon_type=icon_type,
        size=icon_size,
        accent_color=theme["primary"],
        secondary_color=theme["secondary"]
    )

    if mode == "graphic_burst":
        tw, th = measure_arabic_text(draw, keyword_title, title_font)
        card_w = min(int(video_width * 0.86), max(tw + icon_size + 90, int(video_width * 0.55)))
        card_h = icon_size + 44
        cx = video_width // 2
        top_y = int(video_height * 0.09)

        x1, y1 = cx - card_w // 2, top_y
        x2, y2 = cx + card_w // 2, top_y + card_h

        draw.rounded_rectangle([(x1 - 5, y1 - 5), (x2 + 5, y2 + 5)], radius=28, fill=(*theme["primary"], 55))
        draw.rounded_rectangle(
            [(x1, y1), (x2, y2)],
            radius=24,
            fill=(11, 17, 34, 232),
            outline=(*theme["primary"], 240),
            width=3
        )
        draw.rounded_rectangle(
            [(x1 + 24, y2 - 8), (x2 - 24, y2 - 3)],
            radius=3,
            fill=(*theme["secondary"], 255)
        )

        icon_x = x2 - icon_size - 22
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
    else:
        tw, th = measure_arabic_text(draw, keyword_title, title_font)
        card_w = min(int(video_width * 0.82), tw + icon_size + 68)
        card_h = icon_size + 24
        margin_x = int(video_width * 0.045)
        margin_y = int(video_height * 0.065)

        x2 = video_width - margin_x
        x1 = max(margin_x, x2 - card_w)
        y1 = margin_y
        y2 = y1 + card_h

        draw.rounded_rectangle(
            [(x1, y1), (x2, y2)],
            radius=20,
            fill=(15, 23, 42, 215),
            outline=(*theme["secondary"], 215),
            width=3
        )
        icon_x = x2 - icon_size - 14
        icon_y = y1 + (card_h - icon_size) // 2
        canvas.paste(icon_img, (icon_x, icon_y), icon_img)

        text_cx = x1 + (icon_x - x1) // 2
        text_cy = y1 + card_h // 2
        draw_arabic_text(
            draw,
            (text_cx, text_cy),
            keyword_title,
            font=title_font,
            fill=(255, 255, 255, 255)
        )

    return np.array(canvas)


# ==============================================================================
# 5. عناصر الموشن جرافيك المخصصة لإعلانات المنتجات (E-Commerce Ad Elements)
# ==============================================================================
def render_ecommerce_ad_overlay(
    ad_role: str,
    badge_title: str,
    icon_cat: str,
    video_width: int,
    video_height: int,
    theme_name: str = "cyber_gold"
) -> np.ndarray:
    """
    رسم عناصر الموشن جرافيك الخاصة بإعلانات المنتجات التجارية:
    - ad_hook: لافتة خطاف نارية / مضيئة في أعلى الشاشة (Stop the Scroll).
    - ad_problem: بطاقة تنبيه حمراء لتحذير العميل من المشكلة وتوضيح الحاجة للمنتج.
    - ad_feature: بطاقة زجاجية فاخرة في الزاوية تبرز ميزات المنتج التقنية والعملية.
    - ad_trust: شارة ثقة وتوصيل (🚚 توصيل 58 ولاية / 💵 الدفع عند الاستلام / 🛡️ ضمان).
    - ad_cta: لافتة تسوق وحث على الطلب والشراء في أسفل الشاشة.
    """
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    title_size = max(26, int(min(video_width, video_height) * 0.044))
    font_bold = get_arabic_font(title_size, bold=True)
    font_badge = get_arabic_font(max(20, int(title_size * 0.75)), bold=False)

    icon_size = max(64, int(min(video_width, video_height) * 0.082))

    if ad_role == "ad_hook":
        # لافتة الخطاف العلوي النارية لإيقاف التمرير
        cx = video_width // 2
        top_y = int(video_height * 0.075)
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        banner_w = min(int(video_width * 0.92), tw + 80)
        banner_h = th + 36

        bx1 = cx - banner_w // 2
        by1 = top_y
        bx2 = cx + banner_w // 2
        by2 = top_y + banner_h

        # إطار نيون برتقالي/أصفر ساطع
        draw.rounded_rectangle([(bx1 - 4, by1 - 4), (bx2 + 4, by2 + 4)], radius=22, fill=(245, 158, 11, 80))
        draw.rounded_rectangle(
            [(bx1, by1), (bx2, by2)],
            radius=18,
            fill=(20, 10, 10, 235),
            outline=(255, 215, 0, 255),
            width=3
        )
        draw_arabic_text(
            draw,
            (cx, by1 + banner_h // 2),
            badge_title,
            font=font_bold,
            fill=(255, 230, 0, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 240)
        )

    elif ad_role == "ad_cta":
        # لافتة الحث على الشراء والطلب أسفل الفيديو (Pulsing Bottom CTA Banner)
        cx = video_width // 2
        bot_y = int(video_height * 0.84)
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        banner_w = min(int(video_width * 0.94), tw + 90)
        banner_h = th + 40

        bx1 = cx - banner_w // 2
        by1 = bot_y
        bx2 = cx + banner_w // 2
        by2 = bot_y + banner_h

        # هالة خضراء/ذهبية مشعة للطلب الفوري
        draw.rounded_rectangle([(bx1 - 5, by1 - 5), (bx2 + 5, by2 + 5)], radius=24, fill=(16, 185, 129, 90))
        draw.rounded_rectangle(
            [(bx1, by1), (bx2, by2)],
            radius=20,
            fill=(6, 26, 20, 240),
            outline=(52, 211, 153, 255),
            width=4
        )
        draw_arabic_text(
            draw,
            (cx, by1 + banner_h // 2),
            badge_title,
            font=font_bold,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 220)
        )

    elif ad_role == "ad_problem":
        # بطاقة المشكلة والمعاناة
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        margin_x = int(video_width * 0.05)
        top_y = int(video_height * 0.08)
        card_w = min(int(video_width * 0.85), tw + 60)
        card_h = th + 28
        cx = video_width // 2

        draw.rounded_rectangle(
            [(cx - card_w // 2, top_y), (cx + card_w // 2, top_y + card_h)],
            radius=16,
            fill=(45, 12, 16, 225),
            outline=(239, 68, 68, 220),
            width=2
        )
        draw_arabic_text(
            draw,
            (cx, top_y + card_h // 2),
            badge_title,
            font=font_bold,
            fill=(254, 202, 202, 255)
        )

    else:
        # بطاقات ميزات المنتج وشارات الثقة والتوصيل في الزاوية العلوية
        icon_img = draw_procedural_vector_icon(
            icon_type=icon_cat,
            size=icon_size,
            accent_color=(0, 245, 212) if ad_role == "ad_trust" else (255, 225, 0),
            secondary_color=(255, 225, 0) if ad_role == "ad_trust" else (56, 189, 248)
        )
        tw, th = measure_arabic_text(draw, badge_title, font_bold)
        card_w = min(int(video_width * 0.86), tw + icon_size + 65)
        card_h = icon_size + 24
        margin_x = int(video_width * 0.045)
        margin_y = int(video_height * 0.075)

        x2 = video_width - margin_x
        x1 = max(margin_x, x2 - card_w)
        y1 = margin_y
        y2 = y1 + card_h

        border_c = (0, 245, 212, 230) if ad_role == "ad_trust" else (255, 215, 0, 230)
        draw.rounded_rectangle(
            [(x1, y1), (x2, y2)],
            radius=20,
            fill=(11, 18, 36, 225),
            outline=border_c,
            width=3
        )
        icon_x = x2 - icon_size - 12
        icon_y = y1 + (card_h - icon_size) // 2
        canvas.paste(icon_img, (icon_x, icon_y), icon_img)

        text_cx = x1 + (icon_x - x1) // 2
        text_cy = y1 + card_h // 2
        draw_arabic_text(
            draw,
            (text_cx, text_cy),
            badge_title,
            font=font_bold,
            fill=(255, 255, 255, 255)
        )

    return np.array(canvas)


# ==============================================================================
# 6. مسار التوليد والتصدير لموشن جرافيك النصوص
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
    """إنشاء فيديو موشن جرافيك نصي وأنفوجرافيك متكامل."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف المدخل غير موجود: {input_path}")

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    icons_dir = os.path.join(base_dir, "assets", "icons")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    from moviepy.editor import AudioFileClip, ImageClip, CompositeVideoClip

    audio_clip = None
    bg_clip = None
    final_video = None
    frame_clips = []

    try:
        update_progress(0.1, "1/4: قراءة وتفريغ الصوت (بدعم الدارجة الجزائرية والعربية)...")
        audio_clip = AudioFileClip(input_path)
        total_duration = audio_clip.duration

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
        sentences_data = transcribe_sentences(
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

        update_progress(0.3, "2/4: تصميم المشاهد والأيقونات المفتاحية عبر الذكاء الاصطناعي...")
        theme_keys = list(MOTION_THEMES.keys())
        sentence_meta_list = []

        for idx, sent in enumerate(sentences_data):
            sent_text = sent["text"]
            meta = analyze_sentence_visual_metadata(
                sent_text,
                model_name=ollama_model,
                groq_api_key=groq_api_key,
                gemini_api_key=gemini_api_key,
                openai_api_key=openai_api_key
            )
            matched_icon = find_matching_icon(meta["keyword"], icons_dir=icons_dir)
            sentence_meta_list.append({
                "start": sent["start"],
                "end": sent["end"],
                "keyword": meta["keyword"],
                "icon_type": meta["icon_type"],
                "icon_path": matched_icon,
                "theme": theme_keys[idx % len(theme_keys)],
                "words": [w["word"] for w in sent.get("words", [])]
            })

        update_progress(0.5, "3/4: توليد خلفية الأستوديو السينمائية...")
        w, h = video_resolution
        studio_bg_arr = create_studio_background(width=w, height=h, theme_name="cyber_gold")
        bg_clip = ImageClip(studio_bg_arr).set_duration(total_duration)

        update_progress(0.7, "4/4: بناء طبقات الموشن جرافيك والأيقونات الفيكتور المتزامنة...")
        for i, item in enumerate(words_data):
            curr_w = item["word"]
            prev_w = words_data[i - 1]["word"] if i > 0 else None
            w_start = item["start"]
            w_end = item["end"]

            if w_start >= total_duration:
                continue

            if i + 1 < len(words_data):
                next_start = words_data[i + 1]["start"]
                duration = max(0.10, next_start - w_start)
            else:
                duration = max(0.15, min(w_end - w_start, total_duration - w_start))

            active_meta = sentence_meta_list[0] if sentence_meta_list else {
                "keyword": "موشن جرافيك",
                "icon_type": "success",
                "icon_path": None,
                "theme": "cyber_gold",
                "words": [curr_w]
            }
            for sm in sentence_meta_list:
                if w_start >= sm["start"] - 0.05:
                    active_meta = sm

            window_start = (i // 4) * 4
            phrase_window = [w_obj["word"] for w_obj in words_data[window_start:window_start + 4]]

            frame_arr = render_kinetic_frame(
                current_word=curr_w,
                prev_word=prev_w,
                video_width=w,
                video_height=h,
                icon_path=active_meta["icon_path"],
                keyword_title=active_meta["keyword"],
                icon_type=active_meta["icon_type"],
                phrase_words=phrase_window,
                progress_ratio=(w_start / max(1.0, total_duration)),
                theme_name=active_meta["theme"]
            )

            txt_clip = (
                ImageClip(frame_arr, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(duration)
                .set_position(("center", "center"))
            )
            frame_clips.append(txt_clip)

        composite_layers = [bg_clip, *frame_clips]
        final_video = CompositeVideoClip(composite_layers, size=(w, h)).set_audio(audio_clip)

        update_progress(0.85, "جاري رندرة وتصدير فيديو الموشن جرافيك النهائي...")
        temp_audio_file = os.path.join(temp_dir, "temp_motion_audio.m4a")

        final_video.write_videofile(
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

        update_progress(1.0, "تم إنتاج فيديو الموشن جرافيك الاحترافي بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ أثناء تصدير الموشن جرافيك النصي: {str(err)}", exc_info=True)
        raise err

    finally:
        for fc in frame_clips:
            try:
                fc.close()
            except Exception:
                pass
        if bg_clip is not None:
            try:
                bg_clip.close()
            except Exception:
                pass
        if audio_clip is not None:
            try:
                audio_clip.close()
            except Exception:
                pass
        if final_video is not None:
            try:
                final_video.close()
            except Exception:
                pass
