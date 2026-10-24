# -*- coding: utf-8 -*-
"""
vector_lottie_engine.py - محرك الأصول الشفافة، الفيكتور المتحرك (Lottie JSON & SVG)، والـ HUD الزجاجي الفائق
=================================================================================================================
Principal Vector, Lottie/SVG & Next-Gen Glassmorphism Engine (Zero-OOM Architecture):
1. تحميل ورندرة ملفات Lottie JSON و SVG محلياً أو سحابياً مع التخزين في `assets/lottie_cache/`.
2. إعادة التلوين الديناميكي (`inject_dynamic_colors_into_lottie`, `inject_dynamic_colors_into_svg`)
   لتطابق ألوان الثيم النشط في الفيديو أو ألوان الفيديو المرجعي المستنسخ.
3. مولد الأشكال الإجرائية الفائقة (`Procedural Next-Gen HUD & Glassmorphism`):
   - إضاءة محيطية شعاعية (`render_radial_ambient_glow`).
   - بطاقات `Glassmorphism` مع ضبابية خلفية حقيقية (`GaussianBlur`) لمنطقة البطاقة من فيديو المتحدث.
   - مسارات متوهجة متحركة (`draw_animated_stroke_dash_rect`).
   - جزيئات طافية تفاعلية (`render_floating_particles_layer`).
"""

import os
import re
import gc
import json
import math
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Tuple, Optional, Union
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

try:
    import cairo
    _HAS_CAIRO = True
except Exception:
    cairo = None
    _HAS_CAIRO = False

from physics_easing import spring_damper, ease_out_back, ease_in_out_expo

logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOTTIE_CACHE_DIR = os.path.join(_CURRENT_DIR, "assets", "lottie_cache")
os.makedirs(LOTTIE_CACHE_DIR, exist_ok=True)


# ==============================================================================
# 1. مكتبة أصول Lottie JSON و SVG المدمجة + الجلب السحابي الآمن مع الكاش المحلي
# ==============================================================================
CURATED_OPEN_LOTTIE_URLS: Dict[str, str] = {
    "ai_neural_brain": "https://assets9.lottiefiles.com/packages/lf20_w51pcehl.json",
    "growth_analytics": "https://assets4.lottiefiles.com/packages/lf20_qp1q7mct.json",
    "reels_smartphone": "https://assets2.lottiefiles.com/packages/lf20_fcfjwiyb.json",
    "delivery_express": "https://assets3.lottiefiles.com/packages/lf20_jmejybvu.json",
    "video_montage_studio": "https://assets5.lottiefiles.com/packages/lf20_knnirj9a.json",
    "ecommerce_showcase": "https://assets10.lottiefiles.com/packages/lf20_3rwasyjy.json"
}


def _build_parametric_lottie_json(scene_type: str) -> Dict[str, Any]:
    """
    يبني هيكل Lottie JSON قياسي (`v: 5.7.4`, `fr: 30`, `layers: [...]`) غني بالمسارات المتجهة
    ومفاتيح الحركة (`ks` keyframes) لكل نوع مشهد، بحيث يعمل محلياً 100% بدون إنترنت ويدعم حقن الألوان.
    """
    return {
        "v": "5.7.4",
        "fr": 30,
        "ip": 0,
        "op": 90,
        "w": 256,
        "h": 256,
        "nm": f"studio_{scene_type}",
        "meta": {"scene_type": scene_type},
        "layers": [
            {
                "ty": 4,
                "nm": "primary_vector_layer",
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 1, "k": [{"t": 0, "s": [0]}, {"t": 90, "s": [360]}]},
                    "p": {"a": 0, "k": [128, 128, 0]},
                    "s": {"a": 1, "k": [{"t": 0, "s": [75, 75, 100]}, {"t": 25, "s": [100, 100, 100]}]}
                },
                "shapes": [
                    {
                        "ty": "el",
                        "p": {"a": 0, "k": [0, 0]},
                        "s": {"a": 0, "k": [172, 172]}
                    },
                    {
                        "ty": "st",
                        "c": {"a": 0, "k": [1.0, 0.84, 0.0, 1.0], "slot": "primary"},
                        "w": {"a": 0, "k": 6}
                    },
                    {
                        "ty": "fl",
                        "c": {"a": 0, "k": [0.0, 0.96, 0.83, 0.22], "slot": "secondary"}
                    }
                ]
            },
            {
                "ty": 4,
                "nm": "accent_core_layer",
                "ks": {
                    "o": {"a": 0, "k": 95},
                    "r": {"a": 1, "k": [{"t": 0, "s": [360]}, {"t": 90, "s": [0]}]},
                    "p": {"a": 0, "k": [128, 128, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]}
                },
                "shapes": [
                    {
                        "ty": "sr",
                        "sy": 2,
                        "pt": {"a": 0, "k": 6},
                        "p": {"a": 0, "k": [0, 0]},
                        "or": {"a": 0, "k": 58},
                        "os": {"a": 0, "k": 0}
                    },
                    {
                        "ty": "st",
                        "c": {"a": 0, "k": [0.38, 0.40, 0.95, 1.0], "slot": "accent"},
                        "w": {"a": 0, "k": 4}
                    }
                ]
            }
        ]
    }


def _build_parametric_svg_xml(scene_type: str) -> str:
    """بناء ملف SVG قياسي قابل لإعادة التلوين الديناميكي لأي موضوع أو مشهد."""
    st = str(scene_type or "key_concept").strip()
    if st in ("problem_alert", "security"):
        inner = '<polygon points="128,36 220,198 36,198" fill="none" stroke="#PRIMARY#" stroke-width="10" stroke-linejoin="round"/><line x1="128" y1="92" x2="128" y2="148" stroke="#SECONDARY#" stroke-width="12" stroke-linecap="round"/><circle cx="128" cy="174" r="8" fill="#SECONDARY#"/>'
    elif st in ("solution_check", "ecommerce_showcase"):
        inner = '<circle cx="128" cy="128" r="84" fill="#SECONDARY#" fill-opacity="0.18" stroke="#PRIMARY#" stroke-width="9"/><polyline points="86,130 116,160 174,98" fill="none" stroke="#SECONDARY#" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>'
    elif st == "question_mark":
        inner = '<circle cx="128" cy="128" r="86" fill="none" stroke="#PRIMARY#" stroke-width="9" stroke-dasharray="18,10"/><path d="M102,98 C102,74 154,74 154,104 C154,124 128,128 128,148" fill="none" stroke="#SECONDARY#" stroke-width="12" stroke-linecap="round"/><circle cx="128" cy="176" r="8" fill="#PRIMARY#"/>'
    elif st in ("cta_tap", "brand_finale"):
        inner = '<rect x="44" y="68" width="168" height="120" rx="28" fill="#PRIMARY#" fill-opacity="0.22" stroke="#PRIMARY#" stroke-width="8"/><polygon points="110,100 110,156 160,128" fill="#SECONDARY#"/>'
    else:
        inner = '<circle cx="128" cy="128" r="86" fill="none" stroke="#PRIMARY#" stroke-width="8"/><circle cx="128" cy="128" r="46" fill="#SECONDARY#" fill-opacity="0.25" stroke="#ACCENT#" stroke-width="6"/>'

    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">{inner}</svg>'


def load_or_fetch_lottie_asset(
    scene_type: str,
    topic: str = "",
    allow_network: bool = False
) -> Dict[str, Any]:
    """
    تحميل ملف Lottie JSON من الكاش المحلي `assets/lottie_cache/` أو جلبه سحابياً عند التوفر،
    مع توليد فوري مضمون 100% في حال عدم وجود إنترنت.
    """
    key = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{scene_type}_{topic}".strip("_")) or "default"
    cache_path = os.path.join(LOTTIE_CACHE_DIR, f"{key}.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "layers" in data:
                return data
        except Exception:
            pass

    if allow_network and scene_type in CURATED_OPEN_LOTTIE_URLS:
        try:
            resp = requests.get(CURATED_OPEN_LOTTIE_URLS[scene_type], timeout=2.5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "layers" in data:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    return data
        except Exception:
            pass

    parametric = _build_parametric_lottie_json(scene_type)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(parametric, f)
    except Exception:
        pass
    return parametric


# ==============================================================================
# 2. إعادة التلوين الديناميكي لملفات Lottie JSON و SVG (Dynamic Color Injection)
# ==============================================================================
def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2])))
    )


def inject_dynamic_colors_into_svg(
    svg_content: str,
    theme: Dict[str, Any]
) -> str:
    """تعديل ألوان XML داخل ملف الـ SVG برمجياً لتطابق ألوان الثيم النشط أو الفيديو المرجعي."""
    p_hex = _rgb_to_hex(theme.get("primary", (255, 215, 0)))
    s_hex = _rgb_to_hex(theme.get("secondary", (0, 245, 212)))
    a_hex = _rgb_to_hex(theme.get("accent", (99, 102, 241)))

    colored = (
        svg_content
        .replace("#PRIMARY#", p_hex)
        .replace("#SECONDARY#", s_hex)
        .replace("#ACCENT#", a_hex)
    )
    return colored


def inject_dynamic_colors_into_lottie(
    lottie_data: Dict[str, Any],
    theme: Dict[str, Any]
) -> Dict[str, Any]:
    """
    تعديل مصفوفات الألوان النسبية `[r, g, b, a]` داخل شجرة `layers -> shapes` في ملف Lottie JSON
    لتطابق ألوان الثيم النشط في الفيديو أو ألوان الفيديو المرجعي المستنسخ.
    """
    cloned = json.loads(json.dumps(lottie_data))
    p_norm = [round(c / 255.0, 4) for c in theme.get("primary", (255, 215, 0))]
    s_norm = [round(c / 255.0, 4) for c in theme.get("secondary", (0, 245, 212))]
    a_norm = [round(c / 255.0, 4) for c in theme.get("accent", (99, 102, 241))]
    palette_cycle = [p_norm, s_norm, a_norm]
    color_counter = [0]

    def _walk(node: Any):
        if isinstance(node, dict):
            if node.get("ty") in ("fl", "st") and isinstance(node.get("c"), dict):
                c_obj = node["c"]
                slot = c_obj.get("slot")
                if slot == "primary":
                    target_rgb = p_norm
                elif slot == "secondary":
                    target_rgb = s_norm
                elif slot == "accent":
                    target_rgb = a_norm
                else:
                    target_rgb = palette_cycle[color_counter[0] % len(palette_cycle)]
                    color_counter[0] += 1

                k_val = c_obj.get("k")
                if isinstance(k_val, list) and len(k_val) >= 3 and all(isinstance(x, (int, float)) for x in k_val):
                    alpha = k_val[3] if len(k_val) >= 4 else 1.0
                    c_obj["k"] = [target_rgb[0], target_rgb[1], target_rgb[2], alpha]
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(cloned)
    return cloned


# ==============================================================================
# 3. رندرة أصول Lottie / SVG والـ HUD الفائق (Next-Gen HUD & Glassmorphism)
# ==============================================================================
def render_lottie_or_svg_badge(
    scene_type: str,
    width: int,
    height: int,
    scene_progress: float,
    global_t: float,
    theme: Dict[str, Any]
) -> Image.Image:
    """
    رندرة أصل Lottie JSON + SVG بعد حقن الألوان الديناميكية عند اللحظة `scene_progress`
    مع ارتداد فيزيائي `ease_out_back` وتوهج محيطي.
    """
    lottie_raw = load_or_fetch_lottie_asset(scene_type)
    lottie_colored = inject_dynamic_colors_into_lottie(lottie_raw, theme)
    svg_colored = inject_dynamic_colors_into_svg(_build_parametric_svg_xml(scene_type), theme)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    cx, cy = width // 2, height // 2
    max_r = int(min(width, height) * 0.44)

    pop = float(ease_out_back(min(1.0, max(0.15, scene_progress * 2.2)), overshoot=1.55))
    p_col = tuple(theme.get("primary", (255, 215, 0)))
    s_col = tuple(theme.get("secondary", (0, 245, 212)))
    a_col = tuple(theme.get("accent", (99, 102, 241)))

    # هالة شعاعية خلفية
    for gi in range(3, 0, -1):
        gr = int(max_r * (0.65 + gi * 0.14) * pop)
        ga = int(28 * (4 - gi))
        draw.ellipse([(cx - gr, cy - gr), (cx + gr, cy + gr)], fill=(*p_col, ga))

    # قراءة وتصيير طبقات Lottie الملونة ديناميكياً
    for lyr_idx, layer in enumerate(lottie_colored.get("layers", [])[:3]):
        shapes = layer.get("shapes", [])
        stroke_rgb = p_col if lyr_idx == 0 else a_col
        for sh in shapes:
            if isinstance(sh, dict) and sh.get("ty") == "st":
                k_c = sh.get("c", {}).get("k", [])
                if isinstance(k_c, list) and len(k_c) >= 3:
                    stroke_rgb = (int(k_c[0] * 255), int(k_c[1] * 255), int(k_c[2] * 255))

        ring_r = int(max_r * (0.92 - lyr_idx * 0.24) * pop)
        if ring_r > 6:
            rot_deg = (global_t * (55.0 if lyr_idx % 2 == 0 else -45.0)) % 360.0
            start_ang = int(rot_deg)
            draw.arc(
                [(cx - ring_r, cy - ring_r), (cx + ring_r, cy + ring_r)],
                start=start_ang,
                end=start_ang + 270,
                fill=(*stroke_rgb, 235),
                width=max(2, int(width * 0.045))
            )

    # تحليل ورسم عناصر الـ SVG الملونة في القلب
    try:
        root = ET.fromstring(svg_colored)
        scale_x = (width * 0.68 * pop) / 256.0
        scale_y = (height * 0.68 * pop) / 256.0
        off_x = cx - 128.0 * scale_x
        off_y = cy - 128.0 * scale_y

        for elem in root:
            tag = elem.tag.split("}")[-1]
            if tag == "polygon":
                pts_str = elem.attrib.get("points", "").strip()
                pts = []
                for pair in pts_str.split():
                    if "," in pair:
                        px, py = pair.split(",", 1)
                        pts.append((int(off_x + float(px) * scale_x), int(off_y + float(py) * scale_y)))
                if len(pts) >= 3:
                    draw.polygon(pts, fill=(*s_col, 90), outline=(*p_col, 255))
            elif tag == "polyline":
                pts_str = elem.attrib.get("points", "").strip()
                pts = []
                for pair in pts_str.split():
                    if "," in pair:
                        px, py = pair.split(",", 1)
                        pts.append((int(off_x + float(px) * scale_x), int(off_y + float(py) * scale_y)))
                if len(pts) >= 2:
                    draw.line(pts, fill=(*s_col, 255), width=max(3, int(width * 0.06)))
    except Exception:
        pass

    return canvas


def draw_animated_stroke_dash_rect(
    draw: ImageDraw.ImageDraw,
    bbox: Tuple[int, int, int, int],
    radius: int,
    global_t: float,
    color_rgb: Tuple[int, int, int] = (56, 189, 248),
    dash_length: int = 26,
    gap_length: int = 18,
    width: int = 3,
    alpha: int = 230
) -> None:
    """
    رسم مسار حدود متوهج متحرك (`Animated Marching Stroke Dash`) حول البطاقة الزجاجية
    يعطي إحساساً حياً بالتدفق الطاقي حول الإطار حتى أثناء ثبات البطاقة للقراءة.
    """
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    if x2 - x1 < 16 or y2 - y1 < 16:
        return

    # بناء مضلع تقريبي لمحيط المستطيل الدائري الزوايا
    pts: List[Tuple[float, float]] = []
    r = max(2, min(int(radius), (x2 - x1) // 2, (y2 - y1) // 2))
    steps_corner = 5

    # الحافة العلوية + الزاوية اليمنى العلوية
    pts.append((x1 + r, y1))
    pts.append((x2 - r, y1))
    for i in range(1, steps_corner + 1):
        a = -math.pi / 2 + (math.pi / 2) * (i / float(steps_corner))
        pts.append((x2 - r + r * math.cos(a), y1 + r + r * math.sin(a)))

    # الحافة اليمنى + الزاوية اليمنى السفلية
    pts.append((x2, y2 - r))
    for i in range(1, steps_corner + 1):
        a = 0.0 + (math.pi / 2) * (i / float(steps_corner))
        pts.append((x2 - r + r * math.cos(a), y2 - r + r * math.sin(a)))

    # الحافة السفلية + الزاوية اليسرى السفلية
    pts.append((x1 + r, y2))
    for i in range(1, steps_corner + 1):
        a = math.pi / 2 + (math.pi / 2) * (i / float(steps_corner))
        pts.append((x1 + r + r * math.cos(a), y2 - r + r * math.sin(a)))

    # الحافة اليسرى + الزاوية اليسرى العلوية
    pts.append((x1, y1 + r))
    for i in range(1, steps_corner + 1):
        a = math.pi + (math.pi / 2) * (i / float(steps_corner))
        pts.append((x1 + r + r * math.cos(a), y1 + r + r * math.sin(a)))

    period = max(8, int(dash_length + gap_length))
    phase_offset = (global_t * 95.0) % period
    cum_dist = 0.0

    for i in range(len(pts) - 1):
        p_start = pts[i]
        p_end = pts[i + 1]
        seg_len = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])
        if seg_len < 1.0:
            continue

        pos = 0.0
        step_sz = 6.0
        while pos < seg_len:
            d_now = (cum_dist + pos - phase_offset) % period
            if d_now < dash_length:
                u1 = pos / seg_len
                u2 = min(1.0, (pos + min(step_sz, dash_length - d_now)) / seg_len)
                lx1 = int(round(p_start[0] + (p_end[0] - p_start[0]) * u1))
                ly1 = int(round(p_start[1] + (p_end[1] - p_start[1]) * u1))
                lx2 = int(round(p_start[0] + (p_end[0] - p_start[0]) * u2))
                ly2 = int(round(p_start[1] + (p_end[1] - p_start[1]) * u2))
                draw.line([(lx1, ly1), (lx2, ly2)], fill=(*color_rgb, alpha), width=width)
            pos += step_sz
        cum_dist += seg_len


def render_floating_particles_layer(
    canvas_rgba: Image.Image,
    global_t: float,
    theme: Dict[str, Any],
    count: int = 14,
    region_bbox: Optional[Tuple[int, int, int, int]] = None
) -> Image.Image:
    """
    رسم جزيئات ضوئية طافية (`Floating Bokeh & HUD Particles`) تتحرك بفيزياء جيبية ناعمة
    في خلفية المسرح دون أي استهلاك إضافي للذاكرة.
    """
    w, h = canvas_rgba.size
    rx1, ry1, rx2, ry2 = region_bbox if region_bbox else (0, 0, w, int(h * 0.78))
    rw = max(32, rx2 - rx1)
    rh = max(32, ry2 - ry1)

    draw = ImageDraw.Draw(canvas_rgba, "RGBA")
    p_col = tuple(theme.get("primary", (255, 215, 0)))
    s_col = tuple(theme.get("secondary", (0, 245, 212)))

    for i in range(count):
        seed_x = ((i * 73 + 19) % 97) / 97.0
        seed_y = ((i * 41 + 31) % 89) / 89.0
        speed_y = 18.0 + (i % 4) * 7.5
        px = rx1 + int((seed_x * rw + 16.0 * math.sin(global_t * 1.4 + i * 0.9)) % rw)
        py = ry1 + int((seed_y * rh - global_t * speed_y) % rh)

        rad = 2 + (i % 3)
        pulse_a = int(42 + 38 * (0.5 + 0.5 * math.sin(global_t * 3.2 + i * 1.1)))
        col = p_col if (i % 2 == 0) else s_col
        draw.ellipse([(px - rad * 2, py - rad * 2), (px + rad * 2, py + rad * 2)], fill=(*col, pulse_a // 3))
        draw.ellipse([(px - rad, py - rad), (px + rad, py + rad)], fill=(*col, pulse_a))

    return canvas_rgba


def render_radial_ambient_glow(
    canvas_rgba: Image.Image,
    center_xy: Tuple[int, int],
    radius: int,
    color_rgb: Tuple[int, int, int],
    intensity: float = 0.28
) -> Image.Image:
    """إضاءة محيطية متدرجة (`Radial Glow`) خلف البطاقات أو الأيقونات."""
    if radius <= 8 or intensity <= 0.01:
        return canvas_rgba
    w, h = canvas_rgba.size
    cx, cy = int(center_xy[0]), int(center_xy[1])
    x1, y1 = max(0, cx - radius), max(0, cy - radius)
    x2, y2 = min(w, cx + radius), min(h, cy + radius)
    gw, gh = x2 - x1, y2 - y1
    if gw < 8 or gh < 8:
        return canvas_rgba

    yy, xx = np.ogrid[y1:y2, x1:x2]
    dist_sq = ((xx - cx) / float(radius)) ** 2 + ((yy - cy) / float(radius)) ** 2
    alpha_map = (np.exp(-dist_sq * 2.8) * (255.0 * min(0.85, float(intensity)))).astype(np.uint8)

    patch = np.zeros((gh, gw, 4), dtype=np.uint8)
    patch[:, :, 0] = color_rgb[0]
    patch[:, :, 1] = color_rgb[1]
    patch[:, :, 2] = color_rgb[2]
    patch[:, :, 3] = alpha_map

    glow_img = Image.fromarray(patch, mode="RGBA")
    canvas_rgba.alpha_composite(glow_img, (x1, y1))
    return canvas_rgba


# ==============================================================================
# 4. محرك الرسومات التعبيرية والمجسمات المتجهية المتوافقة 100% مع الكلام المنطوق
#    (16 Bespoke Speech-Matched Open-Canvas Vector Hero Illustrations)
# ==============================================================================
def render_contextual_hero_illustration(
    img: Image.Image,
    archetype: str,
    stage_bbox: Tuple[int, int, int, int],
    choreo_u: float,
    global_t: float,
    style_spec: Dict[str, Any],
    scene_meta: Dict[str, Any],
    sub_items: List[str],
    kpi_val: str,
    kpi_lbl: str,
    concept_title: str,
    draw_contained_text_fn,
    draw_arabic_text_fn,
    get_font_fn,
    draw_cursor_fn
) -> Image.Image:
    w, h = img.size
    st_x1, st_y1, st_x2, st_y2 = stage_bbox
    st_w = max(120, st_x2 - st_x1)
    st_h = max(120, st_y2 - st_y1)
    cx = (st_x1 + st_x2) // 2
    cy = st_y1 + int(st_h * 0.44)

    pal = style_spec.get("palette", {})
    is_light_bg = bool(pal.get("is_light_bg", False))
    primary_c = tuple(pal.get("primary", (56, 189, 248)))[:3]
    secondary_c = tuple(pal.get("secondary", (250, 204, 21)))[:3]
    accent_c = tuple(pal.get("accent", (16, 185, 129)))[:3]
    txt_main = (24, 24, 27) if is_light_bg else (248, 250, 252)
    txt_muted = (71, 85, 105) if is_light_bg else (190, 205, 225)
    pod_bg = (255, 255, 255, 238) if is_light_bg else (22, 28, 48, 224)
    pod_border = (*primary_c, 195)

    # إضاءة محيطية ناعمة وجزيئات سينمائية في الفضاء المفتوح (بدون أي صندوق أبيض ضخم!)
    img = render_radial_ambient_glow(img, (cx, cy), int(min(st_w, st_h) * 0.46), primary_c, intensity=0.22 if is_light_bg else 0.32)
    img = render_floating_particles_layer(
        canvas_rgba=img,
        global_t=global_t,
        theme={"primary": primary_c, "secondary": secondary_c},
        count=10,
        region_bbox=(st_x1, st_y1, st_x2, st_y2)
    )
    draw = ImageDraw.Draw(img, "RGBA")

    def _spring(u: float, delay: float = 0.0, dur: float = 0.38) -> float:
        if u <= delay:
            return 0.0
        p = min(1.0, (u - delay) / max(0.05, dur))
        return 1.0 - math.exp(-6.2 * p) * math.cos(8.5 * p)

    def _draw_floating_pod(bx1: int, by1: int, bx2: int, by2: int, title_t: str, sub_t: str = "", badge_col=primary_c, radius: int = 18):
        if bx2 - bx1 < 20 or by2 - by1 < 18:
            return
        draw.rounded_rectangle([(bx1 + 3, by1 + 8), (bx2 + 3, by2 + 8)], radius=radius, fill=(8, 12, 24, 68))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=pod_bg, outline=(*badge_col, 215), width=2)
        dot_r = 6
        draw.ellipse([(bx2 - 18 - dot_r, (by1 + by2) // 2 - dot_r), (bx2 - 18 + dot_r, (by1 + by2) // 2 + dot_r)], fill=(*badge_col, 255))
        if sub_t:
            mid_y = by1 + int((by2 - by1) * 0.52)
            draw_contained_text_fn(draw, (bx1 + 10, by1 + 4, bx2 - 30, mid_y), title_t, initial_font_size=15, fill=(*txt_main, 255))
            draw_contained_text_fn(draw, (bx1 + 10, mid_y, bx2 - 30, by2 - 4), sub_t, initial_font_size=13, fill=(*badge_col, 255))
        else:
            draw_contained_text_fn(draw, (bx1 + 12, by1 + 4, bx2 - 30, by2 - 4), title_t, initial_font_size=15, fill=(*txt_main, 255))

    # حساب متغير التنويع البصري (Variant Seed) لضمان عدم تكرار نفس الشكل الهندسي بين الفيديوهات!
    step_num_v = int(scene_meta.get("step_number") or 1)
    fam_id_str = str(style_spec.get("style_family_id") or scene_meta.get("theme_name") or "default")
    fam_hash = sum(ord(ch) for ch in fam_id_str)
    variant_id = (step_num_v + fam_hash) % 3

    def _draw_bottom_speech_pills(y_top: int):
        # منع ازدحام الشاشة وتكرار الكلام المنطوق في 3 صناديق:
        # لا نرسم الكبسولات السفلية الإضافية إلا إذا كان المتحدث يعدد نقاطاً صراحةً (Explicit Enumeration)!
        if not scene_meta.get("is_explicit_enumeration", False):
            return
        unique_subs: List[str] = []
        title_norm = re.sub(r"\s+", " ", str(concept_title or "")).strip()
        for s_cand in (sub_items or []):
            s_clean = re.sub(r"^\d+[\.\-\s]+", "", str(s_cand or "")).strip()
            if len(s_clean) >= 4 and s_clean != title_norm and s_clean not in unique_subs:
                unique_subs.append(s_clean)
        if not unique_subs:
            return
        if len(unique_subs) == 1:
            sp = _spring(choreo_u, delay=0.24, dur=0.36)
            if sp > 0.05:
                pw = int(st_w * 0.76)
                px1 = cx - pw // 2
                py1 = y_top + int(18 * (1.0 - min(1.0, sp)))
                _draw_floating_pod(px1, py1, px1 + pw, py1 + 46, unique_subs[0], "", badge_col=primary_c, radius=18)
            return
        pw = (st_w - 14) // 2
        ph = 48
        for pi in range(2):
            sp = _spring(choreo_u, delay=0.22 + pi * 0.12, dur=0.36)
            if sp <= 0.05:
                continue
            px1 = st_x1 + pi * (pw + 14)
            py1 = y_top + int(18 * (1.0 - min(1.0, sp)))
            b_col = primary_c if pi == 0 else accent_c
            _draw_floating_pod(px1, py1, px1 + pw, py1 + ph, unique_subs[pi], "", badge_col=b_col, radius=16)

    sp_main = max(0.15, min(1.12, _spring(choreo_u, delay=0.04, dur=0.40)))
    float_dy = int(5.0 * math.sin(global_t * 2.8))
    cy += float_dy

    # -------------------------------------------------------------------------
    # 0. web_dynamic_scene: مشهد الفيكتور الحي المجلوب من الإنترنت والملون بثيم الفيديو
    # -------------------------------------------------------------------------
    if archetype in ("web_dynamic_scene", "hero_web_dynamic_vector"):
        return render_web_fetched_motion_scene(
            img=img,
            stage_bbox=stage_bbox,
            choreo_u=choreo_u,
            global_t=global_t,
            style_spec=style_spec,
            scene_meta=scene_meta,
            concept_title=concept_title,
            kpi_val=kpi_val,
            kpi_lbl=kpi_lbl,
            draw_contained_text_fn=draw_contained_text_fn,
            draw_arabic_text_fn=draw_arabic_text_fn,
            get_font_fn=get_font_fn,
            draw_cursor_fn=draw_cursor_fn
        )

    # -------------------------------------------------------------------------
    # 1. hero_smartphone_reels: مجسم الهاتف الذكي الثلاثي الأبعاد مع بطاقات الريلز العائمة حوله
    # -------------------------------------------------------------------------
    if archetype == "hero_smartphone_reels":
        ph_w = int(st_w * 0.44 * sp_main)
        ph_h = int(st_h * 0.68 * sp_main)
        px1, py1 = cx - ph_w // 2, cy - ph_h // 2 - 8
        px2, py2 = px1 + ph_w, py1 + ph_h

        # بطاقتان جانبيتان عائمتان خلف وحول الهاتف لإعطاء عمق 3D Studio غني
        side_cards = [
            (st_x1 + 4, py1 + int(ph_h * 0.14), px1 - 10, py1 + int(ph_h * 0.44), secondary_c, "REELS 9:16", 0.14),
            (px2 + 10, py1 + int(ph_h * 0.48), st_x2 - 4, py1 + int(ph_h * 0.78), accent_c, kpi_lbl or "HD STUDIO", 0.24),
        ]
        for sx1, sy1, sx2, sy2, scol, slbl, sdel in side_cards:
            if sx2 - sx1 >= 55 and choreo_u >= sdel:
                ssp = _spring(choreo_u, delay=sdel, dur=0.35)
                dy_s = int(18 * (1.0 - min(1.0, ssp)))
                draw.rounded_rectangle([(sx1 + 3, sy1 + dy_s + 8), (sx2 + 3, sy2 + dy_s + 8)], radius=18, fill=(8, 12, 24, 65))
                draw.rounded_rectangle([(sx1, sy1 + dy_s), (sx2, sy2 + dy_s)], radius=18, fill=pod_bg, outline=(*scol, 225), width=2)
                scx, scy = (sx1 + sx2) // 2, sy1 + dy_s + int((sy2 - sy1) * 0.38)
                draw.ellipse([(scx - 16, scy - 16), (scx + 16, scy + 16)], fill=(*scol, 45), outline=(*scol, 240), width=2)
                draw.polygon([(scx - 4, scy - 6), (scx - 4, scy + 6), (scx + 7, scy)], fill=(*scol, 255))
                draw_contained_text_fn(draw, (sx1 + 6, sy1 + dy_s + int((sy2 - sy1) * 0.62), sx2 - 6, sy2 + dy_s - 6), slbl, initial_font_size=12, fill=(*txt_main, 255))

        # ظل Gaussian ثلاثي الأبعاد وإطار الهاتف
        sh_ph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh_ph, "RGBA").rounded_rectangle([(px1 + 6, py1 + 16), (px2 + 6, py2 + 18)], radius=32, fill=(8, 10, 20, 95))
        img = Image.alpha_composite(img, sh_ph.filter(ImageFilter.GaussianBlur(radius=14)))
        draw = ImageDraw.Draw(img, "RGBA")

        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=30, fill=(15, 23, 42, 255), outline=(*primary_c, 245), width=3)
        sc_x1, sc_y1, sc_x2, sc_y2 = px1 + 10, py1 + 12, px2 - 10, py2 - 12
        draw.rounded_rectangle([(sc_x1, sc_y1), (sc_x2, sc_y2)], radius=22, fill=(24, 34, 62, 255))

        isl_w = max(38, int(ph_w * 0.32))
        draw.rounded_rectangle([(cx - isl_w // 2, sc_y1 + 8), (cx + isl_w // 2, sc_y1 + 18)], radius=5, fill=(8, 10, 18, 255))

        play_r = max(22, int(ph_w * 0.19 * (0.94 + 0.06 * math.sin(global_t * 5.0))))
        p_cy = (sc_y1 + sc_y2) // 2 - 16
        draw.ellipse([(cx - play_r - 10, p_cy - play_r - 10), (cx + play_r + 10, p_cy + play_r + 10)], fill=(*primary_c, 58))
        draw.ellipse([(cx - play_r, p_cy - play_r), (cx + play_r, p_cy + play_r)], fill=(*primary_c, 255), outline=(255, 255, 255, 230), width=2)
        tri = [(cx - play_r // 3, p_cy - play_r // 2), (cx - play_r // 3, p_cy + play_r // 2), (cx + play_r // 2, p_cy)]
        draw.polygon(tri, fill=(255, 255, 255, 255))

        wave_y = sc_y2 - 38
        n_bars = 14
        bw = max(3, (sc_x2 - sc_x1 - 28) // (n_bars * 2))
        for bi in range(n_bars):
            bh = int(6 + 15 * abs(math.sin(global_t * 4.5 + bi * 0.55)))
            bx = sc_x1 + 16 + bi * (bw * 2)
            b_col = secondary_c if (bi / float(n_bars)) <= choreo_u else (148, 163, 184)
            draw.rounded_rectangle([(bx, wave_y - bh), (bx + bw, wave_y + bh)], radius=2, fill=(*b_col, 245))

        draw_cursor_fn(draw, (px2 + 24, p_cy + 40), (cx, p_cy), choreo_u, accent_rgb=secondary_c)
        return img

    # -------------------------------------------------------------------------
    # 2. hero_camera_production: استوديو التصوير والمونتاج الثلاثي الأبعاد (3D Viewfinder Deck + Timeline)
    # -------------------------------------------------------------------------
    if archetype == "hero_camera_production":
        deck_w = int(st_w * 0.88 * sp_main)
        deck_h = int(st_h * 0.64 * sp_main)
        dx1, dy1 = cx - deck_w // 2, cy - deck_h // 2 - 6
        dx2, dy2 = dx1 + deck_w, dy1 + deck_h

        sh_cam = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh_cam, "RGBA").rounded_rectangle([(dx1 + 4, dy1 + 16), (dx2 + 4, dy2 + 18)], radius=26, fill=(8, 12, 24, 82))
        img = Image.alpha_composite(img, sh_cam.filter(ImageFilter.GaussianBlur(radius=15)))
        draw = ImageDraw.Draw(img, "RGBA")

        draw.rounded_rectangle([(dx1, dy1), (dx2, dy2)], radius=26, fill=pod_bg, outline=(*primary_c, 225), width=2)

        # شريط علوي للكاميرا مع شارة REC نظيفة ومفصولة عن النقطة الحمراء
        draw.rounded_rectangle([(dx1 + 14, dy1 + 12), (dx1 + 142, dy1 + 40)], radius=14, fill=(15, 23, 42, 240))
        rec_alpha = int(170 + 85 * math.sin(global_t * 6.0))
        draw.ellipse([(dx1 + 24, dy1 + 20), (dx1 + 36, dy1 + 32)], fill=(239, 68, 68, rec_alpha))
        f_rec = get_font_fn(13, bold=True)
        draw_arabic_text_fn(draw, (dx1 + 88, dy1 + 26), "4K 60FPS", font=f_rec, fill=(255, 255, 255, 255))

        # عدسة سينمائية مرسومة بنعومة في النصف العلوي من البطاقة
        lens_cy = dy1 + int(deck_h * 0.44)
        lens_r = int(min(deck_w, deck_h) * 0.24)
        draw.ellipse([(cx - lens_r - 8, lens_cy - lens_r - 8), (cx + lens_r + 8, lens_cy + lens_r + 8)], fill=(15, 23, 42, 248), outline=(*primary_c, 245), width=3)
        draw.ellipse([(cx - int(lens_r * 0.74), lens_cy - int(lens_r * 0.74)), (cx + int(lens_r * 0.74), lens_cy + int(lens_r * 0.74))], fill=(24, 34, 62, 252), outline=(*secondary_c, 225), width=2)
        in_r = int(lens_r * (0.36 + 0.10 * math.sin(choreo_u * math.pi)))
        draw.ellipse([(cx - in_r, lens_cy - in_r), (cx + in_r, lens_cy + in_r)], fill=(*primary_c, 235), outline=(255, 255, 255, 235), width=2)

        # شريط تايملاين المونتاج ثلاثي المسارات في النصف السفلي من البطاقة
        tl_y1 = dy2 - int(deck_h * 0.28)
        tl_y2 = dy2 - 14
        draw.rounded_rectangle([(dx1 + 16, tl_y1), (dx2 - 16, tl_y2)], radius=14, fill=(15, 23, 42, 242))
        for ti in range(2):
            ty = tl_y1 + 10 + ti * 20
            t_prog = min(1.0, max(0.25, choreo_u * 1.3 - ti * 0.15))
            tw = int((deck_w - 56) * t_prog)
            tcol = primary_c if ti == 0 else accent_c
            draw.rounded_rectangle([(dx1 + 28, ty), (dx1 + 28 + tw, ty + 12)], radius=6, fill=(*tcol, 245))
        ph_x = dx1 + 28 + int((deck_w - 56) * min(1.0, choreo_u * 1.15))
        draw.line([(ph_x, tl_y1 - 4), (ph_x, tl_y2 + 4)], fill=(239, 68, 68, 255), width=3)

        draw_cursor_fn(draw, (dx2 - 18, dy2 + 24), (ph_x, (tl_y1 + tl_y2) // 2), choreo_u, accent_rgb=secondary_c)
        return img

    # -------------------------------------------------------------------------
    # 3. hero_waveform_scissors: مقص الليزر الذكي وقص الصمت والأخطاء من الموجة الصوتية
    # -------------------------------------------------------------------------
    if archetype == "hero_waveform_scissors":
        track_y1, track_y2 = cy - int(st_h * 0.22), cy + int(st_h * 0.16)
        track_x1, track_x2 = st_x1 + 8, st_x2 - 8
        draw.rounded_rectangle([(track_x1, track_y1), (track_x2, track_y2)], radius=22, fill=pod_bg, outline=(*primary_c, 210), width=2)

        mid_wy = (track_y1 + track_y2) // 2
        n_bars = 28
        step_x = (track_x2 - track_x1 - 32) / float(n_bars)
        cut_x = int(track_x1 + 24 + (track_x2 - track_x1 - 48) * min(1.0, max(0.08, choreo_u * 1.15)))

        for bi in range(n_bars):
            bx = int(track_x1 + 18 + bi * step_x)
            is_silence_gap = (bi in (8, 9, 10, 18, 19, 20))
            already_cleaned = (bx <= cut_x)
            if is_silence_gap and not already_cleaned:
                bh = 6
                b_col = (239, 68, 68)
            else:
                bh = int(14 + 34 * abs(math.sin(bi * 0.65 + global_t * 3.2)))
                b_col = accent_c if already_cleaned else primary_c
            draw.rounded_rectangle([(bx, mid_wy - bh), (bx + 5, mid_wy + bh)], radius=3, fill=(*b_col, 245))

        # خط الليزر القاطع وأيقونة المقص الهندسية المتحركة
        draw.line([(cut_x, track_y1 - 12), (cut_x, track_y2 + 12)], fill=(*secondary_c, 255), width=3)
        sc_y = track_y1 - 16
        draw.ellipse([(cut_x - 14, sc_y - 14), (cut_x - 2, sc_y - 2)], outline=(*secondary_c, 255), width=3)
        draw.ellipse([(cut_x + 2, sc_y - 14), (cut_x + 14, sc_y - 2)], outline=(*secondary_c, 255), width=3)
        draw.line([(cut_x - 6, sc_y - 2), (cut_x + 10, sc_y + 18)], fill=(255, 255, 255, 255), width=3)
        draw.line([(cut_x + 6, sc_y - 2), (cut_x - 10, sc_y + 18)], fill=(255, 255, 255, 255), width=3)

        _draw_floating_pod(cx - int(st_w * 0.38), track_y2 + 14, cx + int(st_w * 0.38), track_y2 + 62, f"{kpi_val} • {kpi_lbl}", badge_col=accent_c, radius=16)
        _draw_bottom_speech_pills(track_y2 + 74)
        return img

    # -------------------------------------------------------------------------
    # 4. hero_ai_neural_core: معالج ونواة الذكاء الاصطناعي لتحويل الصوت والصورة
    # -------------------------------------------------------------------------
    if archetype == "hero_ai_neural_core":
        chip_r = int(min(st_w, st_h) * 0.21 * sp_main)
        # خطوط الدارات الكهربائية المتشعبة من المعالج
        for pi in range(8):
            ang = pi * (math.pi / 4.0)
            x0 = cx + int(chip_r * math.cos(ang))
            y0 = cy + int(chip_r * math.sin(ang))
            x1 = cx + int(chip_r * 1.65 * math.cos(ang))
            y1 = cy + int(chip_r * 1.65 * math.sin(ang))
            draw.line([(x0, y0), (x1, y1)], fill=(*primary_c, 185), width=3)
            pulse_p = (global_t * 2.2 + pi * 0.15) % 1.0
            px = int(x0 + (x1 - x0) * pulse_p)
            py = int(y0 + (y1 - y0) * pulse_p)
            draw.ellipse([(px - 5, py - 5), (px + 5, py + 5)], fill=(*secondary_c, 255))
            draw.ellipse([(x1 - 7, y1 - 7), (x1 + 7, y1 + 7)], fill=pod_bg, outline=(*accent_c, 240), width=2)

        # جسم شريحة الـ AI المركزية
        draw.rounded_rectangle([(cx - chip_r, cy - chip_r), (cx + chip_r, cy + chip_r)], radius=24, fill=(18, 24, 44, 252), outline=(*primary_c, 255), width=3)
        in_r = int(chip_r * 0.68)
        draw.ellipse([(cx - in_r, cy - in_r), (cx + in_r, cy + in_r)], fill=(*primary_c, 55), outline=(*secondary_c, 245), width=2)
        f_ai = get_font_fn(max(22, int(chip_r * 0.42)), bold=True)
        draw_arabic_text_fn(draw, (cx, cy - 6), "AI", font=f_ai, fill=(255, 255, 255, 255))

        _draw_bottom_speech_pills(cy + int(chip_r * 1.72) + 12)
        return img

    # -------------------------------------------------------------------------
    # 5. hero_chrono_speedometer: 3 أشكال حركية متجددة للسرعة والزمن (Web Vector / Dual Rings / Turbo Gauge)
    # -------------------------------------------------------------------------
    if archetype == "hero_chrono_speedometer":
        if False:
            return render_web_fetched_motion_scene(
                img=img, stage_bbox=stage_bbox, choreo_u=choreo_u, global_t=global_t,
                style_spec=style_spec, scene_meta=scene_meta, concept_title=concept_title,
                kpi_val=kpi_val, kpi_lbl=kpi_lbl, draw_contained_text_fn=draw_contained_text_fn,
                draw_arabic_text_fn=draw_arabic_text_fn, get_font_fn=get_font_fn, draw_cursor_fn=draw_cursor_fn
            )
        sp_r = int(min(st_w, st_h) * 0.29 * sp_main)
        if variant_id == 1:
            # حلقات الزمن المدارية الثلاثية الأبعاد مع برق الطاقة في المركز
            for ri, col_r in enumerate([primary_c, secondary_c, accent_c]):
                rr = sp_r - ri * 20
                if rr <= 18:
                    continue
                rot_a = int((global_t * (85 - ri * 25) + ri * 60) % 360)
                draw.arc([(cx - rr, cy - rr), (cx + rr, cy + rr)], start=rot_a, end=rot_a + 230, fill=(*col_r, 240), width=10)
            bolt_pts = [(cx + 8, cy - 36), (cx - 18, cy + 4), (cx + 2, cy + 4), (cx - 10, cy + 38), (cx + 22, cy - 6), (cx + 2, cy - 6)]
            draw.polygon(bolt_pts, fill=(*secondary_c, 255), outline=(255, 255, 255, 245))
            return img

        draw.arc([(cx - sp_r, cy - sp_r), (cx + sp_r, cy + sp_r)], start=135, end=405, fill=(148, 163, 184, 95), width=18)
        sweep_deg = int(270 * min(1.0, max(0.12, choreo_u * 1.25)))
        draw.arc([(cx - sp_r, cy - sp_r), (cx + sp_r, cy + sp_r)], start=135, end=135 + sweep_deg, fill=(*primary_c, 255), width=18)
        for ti in range(11):
            t_ang = math.radians(135 + ti * 27)
            tx0 = cx + int((sp_r - 24) * math.cos(t_ang))
            ty0 = cy + int((sp_r - 24) * math.sin(t_ang))
            tx1 = cx + int((sp_r - 12) * math.cos(t_ang))
            ty1 = cy + int((sp_r - 12) * math.sin(t_ang))
            draw.line([(tx0, ty0), (tx1, ty1)], fill=(*txt_main, 190), width=2)
        needle_ang = math.radians(135 + sweep_deg)
        nx = cx + int((sp_r - 28) * math.cos(needle_ang))
        ny = cy + int((sp_r - 28) * math.sin(needle_ang))
        draw.line([(cx, cy), (nx, ny)], fill=(*secondary_c, 255), width=5)
        draw.ellipse([(cx - 12, cy - 12), (cx + 12, cy + 12)], fill=(*secondary_c, 255), outline=(255, 255, 255, 255), width=3)
        badge_speed = kpi_val if (kpi_val and kpi_val not in concept_title) else "10x FAST"
        draw_contained_text_fn(draw, (cx - int(sp_r * 0.70), cy + 18, cx + int(sp_r * 0.70), cy + int(sp_r * 0.65)), badge_speed, initial_font_size=20, fill=(*txt_main, 255))
        return img

    # -------------------------------------------------------------------------
    # 6. hero_sound_wave_mixer: مايكروفون الاستوديو وموجات الساوند ديزاين
    # -------------------------------------------------------------------------
    if archetype == "hero_sound_wave_mixer":
        mic_w, mic_h = int(st_w * 0.16 * sp_main), int(st_h * 0.28 * sp_main)
        # حلقات الموجات الصوتية المنبعثة من المايكروفون
        for ri in range(1, 4):
            rr = int(mic_w * (0.9 + ri * 0.55) + (global_t * 28.0) % 24)
            alpha_w = max(25, 165 - ri * 42)
            draw.arc([(cx - rr, cy - rr), (cx + rr, cy + rr)], start=-55, end=55, fill=(*primary_c, alpha_w), width=3)
            draw.arc([(cx - rr, cy - rr), (cx + rr, cy + rr)], start=125, end=235, fill=(*secondary_c, alpha_w), width=3)

        # كبسولة المايكروفون الاحترافي وحامله
        draw.rounded_rectangle([(cx - mic_w // 2, cy - mic_h // 2), (cx + mic_w // 2, cy + mic_h // 2)], radius=mic_w // 2, fill=(30, 41, 59, 255), outline=(*primary_c, 255), width=3)
        for gy in range(cy - mic_h // 2 + 12, cy + 4, 9):
            draw.line([(cx - mic_w // 2 + 8, gy), (cx + mic_w // 2 - 8, gy)], fill=(*secondary_c, 210), width=2)
        arc_r = int(mic_w * 0.72)
        draw.arc([(cx - arc_r, cy - int(mic_h * 0.35)), (cx + arc_r, cy + int(mic_h * 0.65))], start=0, end=180, fill=(*txt_main, 240), width=4)
        draw.line([(cx, cy + int(mic_h * 0.65)), (cx, cy + int(mic_h * 0.92))], fill=(*txt_main, 240), width=5)
        draw.line([(cx - 32, cy + int(mic_h * 0.92)), (cx + 32, cy + int(mic_h * 0.92))], fill=(*primary_c, 255), width=5)

        _draw_bottom_speech_pills(cy + int(mic_h * 1.05) + 18)
        return img

    # -------------------------------------------------------------------------
    # 7. hero_viral_rocket_chart: صاروخ الانتشار الفيروسي ومنحنى مضاعفة الإنتاجية
    # -------------------------------------------------------------------------
    if archetype == "hero_viral_rocket_chart":
        chart_x1, chart_y2 = st_x1 + 20, cy + int(st_h * 0.24)
        chart_x2, chart_y1 = st_x2 - 20, st_y1 + 24
        pts = []
        n_seg = 24
        max_i = max(2, int(n_seg * min(1.0, max(0.15, choreo_u * 1.2))))
        for i in range(max_i + 1):
            u = i / float(n_seg)
            px = int(chart_x1 + (chart_x2 - chart_x1) * u)
            py = int(chart_y2 - (chart_y2 - chart_y1) * (u ** 1.85))
            pts.append((px, py))

        if len(pts) >= 2:
            poly = [(pts[0][0], chart_y2)] + pts + [(pts[-1][0], chart_y2)]
            draw.polygon(poly, fill=(*primary_c, 48))
            draw.line(pts, fill=(*primary_c, 255), width=5)

            # رسم مجسم الصاروخ المضيء في قمة المنحنى
            rx, ry = pts[-1]
            draw.ellipse([(rx - 22, ry - 22), (rx + 22, ry + 22)], fill=(*secondary_c, 85))
            draw.polygon([(rx + 18, ry - 18), (rx - 12, ry - 4), (rx - 4, ry + 12)], fill=(255, 255, 255, 255), outline=(*primary_c, 255))
            draw.ellipse([(rx - 18, ry + 6), (rx - 6, ry + 18)], fill=(244, 63, 94, 235))

        _draw_floating_pod(st_x1 + 16, st_y1 + 16, st_x1 + int(st_w * 0.56), st_y1 + 72, kpi_val, kpi_lbl, badge_col=secondary_c, radius=16)
        _draw_bottom_speech_pills(chart_y2 + 16)
        return img

    # -------------------------------------------------------------------------
    # 8. hero_power_cable_stand: مجسم كابل الشحن السريع المقوى بالقماش وحامل الهاتف
    # -------------------------------------------------------------------------
    if archetype == "hero_power_cable_stand":
        bat_w, bat_h = int(st_w * 0.48 * sp_main), int(st_h * 0.24 * sp_main)
        bx1, by1 = cx - bat_w // 2, cy - bat_h - 10
        bx2, by2 = bx1 + bat_w, by1 + bat_h
        # رأس البطارية وحامل الهاتف المعدني (السيبور المدمج)
        draw.rounded_rectangle([(bx2, by1 + bat_h // 4), (bx2 + 12, by2 - bat_h // 4)], radius=4, fill=(*secondary_c, 255))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=20, fill=(18, 24, 42, 248), outline=(*primary_c, 255), width=3)
        fill_w = int((bat_w - 16) * min(1.0, max(0.25, choreo_u * 1.25)))
        draw.rounded_rectangle([(bx1 + 8, by1 + 8), (bx1 + 8 + fill_w, by2 - 8)], radius=14, fill=(*accent_c, 235))
        draw_contained_text_fn(draw, (bx1 + 12, by1 + 8, bx2 - 12, by2 - 8), f"⚡ {kpi_val}", initial_font_size=20, fill=(255, 255, 255, 255))

        # رسم الكابل المجدول بالقماش مع نبضات الطاقة السريعة
        cable_pts = []
        for ci in range(20):
            u = ci / 19.0
            kx = int(st_x1 + 28 + (st_x2 - st_x1 - 56) * u)
            ky = by2 + 38 + int(22 * math.sin(u * math.pi * 2.0 + global_t * 3.0))
            cable_pts.append((kx, ky))
        draw.line(cable_pts, fill=(*primary_c, 255), width=12)
        draw.line(cable_pts, fill=(*secondary_c, 195), width=4)

        _draw_bottom_speech_pills(by2 + 76)
        return img

    # -------------------------------------------------------------------------
    # 9. hero_shield_durability: الدرع السداسي المدرع للمتانة والضمان 100%
    # -------------------------------------------------------------------------
    if archetype == "hero_shield_durability":
        sh_w, sh_h = int(st_w * 0.40 * sp_main), int(st_h * 0.48 * sp_main)
        shield_poly = [
            (cx, cy - sh_h // 2),
            (cx + sh_w // 2, cy - int(sh_h * 0.28)),
            (cx + int(sh_w * 0.42), cy + int(sh_h * 0.18)),
            (cx, cy + sh_h // 2),
            (cx - int(sh_w * 0.42), cy + int(sh_h * 0.18)),
            (cx - sh_w // 2, cy - int(sh_h * 0.28)),
        ]
        for ring_i in range(1, 3):
            rr = int(max(sh_w, sh_h) * (0.55 + ring_i * 0.16))
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*primary_c, 95 // ring_i), width=2)

        draw.polygon(shield_poly, fill=(20, 30, 56, 248), outline=(*primary_c, 255))
        draw.line(shield_poly + [shield_poly[0]], fill=(*secondary_c, 255), width=4)

        # علامة الصح الذهبية/الخضراء في قلب الدرع
        ck_pts = [(cx - 22, cy + 2), (cx - 4, cy + 20), (cx + 28, cy - 18)]
        draw.line(ck_pts, fill=(*accent_c, 255), width=7)
        _draw_bottom_speech_pills(cy + sh_h // 2 + 22)
        return img

    # -------------------------------------------------------------------------
    # 10. hero_commerce_delivery: خريطة التوصيل السريع لـ 58 ولاية وبطاقة الطلب
    # -------------------------------------------------------------------------
    if archetype == "hero_commerce_delivery":
        map_r = int(min(st_w, st_h) * 0.28 * sp_main)
        draw.ellipse([(cx - map_r, cy - map_r), (cx + map_r, cy + map_r)], fill=pod_bg, outline=(*primary_c, 235), width=3)
        pins = [(cx - int(map_r * 0.48), cy + 16), (cx, cy - int(map_r * 0.36)), (cx + int(map_r * 0.48), cy + 8)]
        draw.line(pins, fill=(*secondary_c, 240), width=4)
        for pi, (px, py) in enumerate(pins):
            draw.ellipse([(px - 12, py - 12), (px + 12, py + 12)], fill=(*accent_c, 255), outline=(255, 255, 255, 255), width=2)

        _draw_floating_pod(cx - int(st_w * 0.36), cy - map_r - 22, cx + int(st_w * 0.36), cy - map_r + 28, kpi_val, kpi_lbl, badge_col=secondary_c, radius=16)
        _draw_bottom_speech_pills(cy + map_r + 18)
        draw_cursor_fn(draw, (cx + 80, cy + map_r + 75), (cx, cy + map_r + 42), choreo_u, accent_rgb=secondary_c)
        return img

    # -------------------------------------------------------------------------
    # 11. hero_creative_palette_pen: لوحة التصميم الذكية وعجلة الألوان وقلم الفيكتور
    # -------------------------------------------------------------------------
    if archetype == "hero_creative_palette_pen":
        sw_colors = [primary_c, secondary_c, accent_c, (244, 63, 94), (168, 85, 247)]
        orbit_r = int(min(st_w, st_h) * 0.26 * sp_main)
        for si, col in enumerate(sw_colors):
            ang = si * (2.0 * math.pi / len(sw_colors)) + global_t * 0.6
            sx = cx + int(orbit_r * math.cos(ang))
            sy = cy + int(orbit_r * math.sin(ang))
            sr = 24
            draw.ellipse([(sx - sr, sy - sr), (sx + sr, sy + sr)], fill=(*col, 255), outline=(255, 255, 255, 245), width=3)

        # منحنى Bezier وأيقونة رأس قلم التصميم في المركز
        draw.ellipse([(cx - 34, cy - 34), (cx + 34, cy + 34)], fill=pod_bg, outline=(*primary_c, 255), width=3)
        pen_poly = [(cx, cy - 20), (cx + 16, cy + 8), (cx, cy + 20), (cx - 16, cy + 8)]
        draw.polygon(pen_poly, fill=(*secondary_c, 255))
        _draw_bottom_speech_pills(cy + orbit_r + 32)
        return img

    # -------------------------------------------------------------------------
    # 12. hero_problem_radar_fix: رادار تشخيص المشكلة وتحويلها الفوري إلى حل
    # -------------------------------------------------------------------------
    if archetype == "hero_problem_radar_fix":
        is_solved = (choreo_u >= 0.48)
        active_col = accent_c if is_solved else (244, 63, 94)
        rad_r = int(min(st_w, st_h) * 0.26 * sp_main)
        for ri in range(1, 4):
            rr = int(rad_r * (ri / 2.2))
            draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(*active_col, 210 - ri * 45), width=3)

        if not is_solved:
            tri = [(cx, cy - int(rad_r * 0.55)), (cx - int(rad_r * 0.52), cy + int(rad_r * 0.42)), (cx + int(rad_r * 0.52), cy + int(rad_r * 0.42))]
            draw.polygon(tri, fill=(244, 63, 94, 235), outline=(255, 255, 255, 245))
            f_ex = get_font_fn(34, bold=True)
            draw_arabic_text_fn(draw, (cx, cy + 4), "!", font=f_ex, fill=(255, 255, 255, 255))
        else:
            draw.ellipse([(cx - int(rad_r * 0.52), cy - int(rad_r * 0.52)), (cx + int(rad_r * 0.52), cy + int(rad_r * 0.52))], fill=(*accent_c, 245), outline=(255, 255, 255, 255), width=3)
            ck = [(cx - 20, cy + 2), (cx - 4, cy + 18), (cx + 24, cy - 14)]
            draw.line(ck, fill=(255, 255, 255, 255), width=6)

        _draw_bottom_speech_pills(cy + int(rad_r * 1.38))
        return img

    # -------------------------------------------------------------------------
    # 13. hero_platform_workspace: واجهة الاستوديو الذكي متعددة الأنماط بدون تكرار العنوان
    # -------------------------------------------------------------------------
    if archetype == "hero_platform_workspace":
        if False:
            return render_web_fetched_motion_scene(
                img=img, stage_bbox=stage_bbox, choreo_u=choreo_u, global_t=global_t,
                style_spec=style_spec, scene_meta=scene_meta, concept_title=concept_title,
                kpi_val=kpi_val, kpi_lbl=kpi_lbl, draw_contained_text_fn=draw_contained_text_fn,
                draw_arabic_text_fn=draw_arabic_text_fn, get_font_fn=get_font_fn, draw_cursor_fn=draw_cursor_fn
            )
        dk_w, dk_h = int(st_w * 0.88 * sp_main), int(st_h * 0.50 * sp_main)
        dx1, dy1 = cx - dk_w // 2, cy - dk_h // 2 - 8
        dx2, dy2 = dx1 + dk_w, dy1 + dk_h
        draw.rounded_rectangle([(dx1 + 4, dy1 + 10), (dx2 + 4, dy2 + 10)], radius=26, fill=(8, 12, 22, 65))
        draw.rounded_rectangle([(dx1, dy1), (dx2, dy2)], radius=26, fill=pod_bg, outline=(*primary_c, 235), width=3)
        for di, dcol in enumerate([(244, 63, 94), (250, 204, 21), (16, 185, 129)]):
            draw.ellipse([(dx1 + 18 + di * 18, dy1 + 14), (dx1 + 28 + di * 18, dy1 + 24)], fill=(*dcol, 255))

        # بدلاً من إعادة كتابة جملة العنوان العلوي داخل النافذة، نرسم معاينة تايملاين ومعالج موشن حي!
        prev_y1, prev_y2 = dy1 + 38, dy2 - 68
        draw.rounded_rectangle([(dx1 + 18, prev_y1), (dx2 - 18, prev_y2)], radius=16, fill=(15, 23, 42, 235))
        n_tracks = 3
        th_bar = max(8, (prev_y2 - prev_y1 - 28) // n_tracks)
        for ti_b in range(n_tracks):
            ty_b = prev_y1 + 10 + ti_b * (th_bar + 6)
            prog_b = min(1.0, max(0.22, (choreo_u * 1.35) - ti_b * 0.12))
            bw_b = int((dk_w - 64) * prog_b)
            t_col = [primary_c, secondary_c, accent_c][ti_b % 3]
            draw.rounded_rectangle([(dx1 + 32, ty_b), (dx1 + 32 + bw_b, ty_b + th_bar)], radius=5, fill=(*t_col, 240))

        btn_x1, btn_y1, btn_x2, btn_y2 = cx - int(dk_w * 0.36), dy2 - 54, cx + int(dk_w * 0.36), dy2 - 12
        is_clicked = (choreo_u >= 0.62)
        btn_col = accent_c if is_clicked else primary_c
        draw.rounded_rectangle([(btn_x1, btn_y1), (btn_x2, btn_y2)], radius=21, fill=(*btn_col, 255))
        btn_txt = "✔ AI STUDIO READY" if is_clicked else "✨ AI AUTO STUDIO"
        draw_contained_text_fn(draw, (btn_x1 + 14, btn_y1, btn_x2 - 14, btn_y2), btn_txt, initial_font_size=15, fill=(255, 255, 255, 255))

        draw_cursor_fn(draw, (btn_x2 + 20, btn_y2 + 30), (cx, (btn_y1 + btn_y2) // 2), choreo_u, accent_rgb=secondary_c)
        return img

    # -------------------------------------------------------------------------
    # 14. hero_roadmap_milestones: مسار الخطوات المنحني المضيء
    # -------------------------------------------------------------------------
    if archetype == "hero_roadmap_milestones":
        nodes_y = [st_y1 + int(st_h * (0.14 + i * 0.22)) for i in range(4)]
        nodes_x = [cx + int(st_w * (0.24 if i % 2 == 0 else -0.24)) for i in range(4)]
        for i in range(3):
            if choreo_u >= i * 0.20:
                draw.line([(nodes_x[i], nodes_y[i]), (nodes_x[i + 1], nodes_y[i + 1])], fill=(*primary_c, 220), width=4)

        for i in range(4):
            sp_n = _spring(choreo_u, delay=i * 0.14, dur=0.35)
            if sp_n <= 0.05:
                continue
            nx, ny = nodes_x[i], nodes_y[i]
            draw.ellipse([(nx - 20, ny - 20), (nx + 20, ny + 20)], fill=(*primary_c, 255), outline=(255, 255, 255, 255), width=2)
            fn = get_font_fn(14, bold=True)
            draw_arabic_text_fn(draw, (nx, ny), f"0{i + 1}", font=fn, fill=(255, 255, 255, 255))
            pod_x1 = st_x1 + 8 if (i % 2 == 1) else nx - int(st_w * 0.62)
            pod_x2 = nx - 28 if (i % 2 == 0) else st_x2 - 8
            if pod_x2 - pod_x1 < 90:
                pod_x1, pod_x2 = st_x1 + 12, st_x2 - 12
            _draw_floating_pod(pod_x1, ny - 22, pod_x2, ny + 22, sub_items[i % len(sub_items)], badge_col=accent_c if i % 2 == 1 else primary_c, radius=14)
        return img

    # -------------------------------------------------------------------------
    # 15. hero_comparison_duel: مواجهة بصرية حية (تقليدي مقابل ذكي)
    # -------------------------------------------------------------------------
    if archetype == "hero_comparison_duel":
        pw = int(st_w * 0.43)
        ph = int(st_h * 0.52)
        py1 = cy - ph // 2
        _draw_floating_pod(st_x1, py1, st_x1 + pw, py1 + ph, sub_items[0], "الوضع التقليدي", badge_col=(244, 63, 94), radius=22)
        _draw_floating_pod(st_x2 - pw, py1, st_x2, py1 + ph, sub_items[min(1, len(sub_items) - 1)], kpi_val, badge_col=accent_c, radius=22)
        draw.ellipse([(cx - 24, cy - 24), (cx + 24, cy + 24)], fill=(*secondary_c, 255), outline=(255, 255, 255, 255), width=3)
        f_vs = get_font_fn(16, bold=True)
        draw_arabic_text_fn(draw, (cx, cy), "VS", font=f_vs, fill=(18, 24, 38, 255))
        _draw_bottom_speech_pills(py1 + ph + 18)
        return img

    # -------------------------------------------------------------------------
    # 16. hero_cta_magnet_finale: خاتمة سينمائية متجددة (Web Vector / Crown Badge / Rocket Portal)
    # -------------------------------------------------------------------------
    if False:
        return render_web_fetched_motion_scene(
            img=img, stage_bbox=stage_bbox, choreo_u=choreo_u, global_t=global_t,
            style_spec=style_spec, scene_meta=scene_meta, concept_title=concept_title,
            kpi_val=kpi_val, kpi_lbl=kpi_lbl, draw_contained_text_fn=draw_contained_text_fn,
            draw_arabic_text_fn=draw_arabic_text_fn, get_font_fn=get_font_fn, draw_cursor_fn=draw_cursor_fn
        )
    portal_r = int(min(st_w, st_h) * 0.25 * sp_main)
    for ri in range(3):
        rr = portal_r + ri * 16
        draw.ellipse([(cx - rr, cy - rr - 10), (cx + rr, cy + rr - 10)], outline=(*primary_c, max(45, 210 - ri * 65)), width=3)
    draw.ellipse([(cx - portal_r, cy - portal_r - 10), (cx + portal_r, cy + portal_r - 10)], fill=(*primary_c, 240), outline=(255, 255, 255, 245), width=3)
    ck_pts = [(cx - 24, cy - 8), (cx - 6, cy + 12), (cx + 28, cy - 24)]
    draw.line(ck_pts, fill=(255, 255, 255, 255), width=7)

    btn_w, btn_h = int(st_w * 0.72), 52
    bx1, by1 = cx - btn_w // 2, cy + portal_r + 18
    bx2, by2 = bx1 + btn_w, by1 + btn_h
    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=26, fill=(*accent_c, 255), outline=(255, 255, 255, 235), width=2)
    cta_lbl = kpi_val if (kpi_val and kpi_val not in concept_title) else "✨ ابدأ الآن مجاناً"
    draw_contained_text_fn(draw, (bx1 + 16, by1, bx2 - 16, by2), cta_lbl, initial_font_size=18, fill=(255, 255, 255, 255))
    draw_cursor_fn(draw, (bx2 - 12, by2 + 34), (cx, (by1 + by2) // 2), choreo_u, accent_rgb=secondary_c)
    return img



# ==============================================================================
# 5. محرك جلب الموشن جرافيك والفيكتور الحي من الإنترنت + إعادة التلوين بثيم الفيديو
#    + دعم حزم الموشن جرافيك الضخمة (400MB+ Google Drive / ZIP Zero-OOM Streamer)
# ==============================================================================
import zipfile
import shutil
import urllib.parse

WEB_MOTION_CACHE_DIR = os.path.join(_CURRENT_DIR, "assets", "web_motion_cache")
CUSTOM_PACK_DIR = os.path.join(_CURRENT_DIR, "assets", "custom_motion_pack")
CUSTOM_PACK_INDEX_PATH = os.path.join(CUSTOM_PACK_DIR, "pack_index.json")
os.makedirs(WEB_MOTION_CACHE_DIR, exist_ok=True)
os.makedirs(CUSTOM_PACK_DIR, exist_ok=True)

_LIVE_WEB_FETCH_ENABLED: bool = True

def set_live_web_fetch_enabled(enabled: bool = True) -> None:
    global _LIVE_WEB_FETCH_ENABLED
    _LIVE_WEB_FETCH_ENABLED = bool(enabled)

def is_live_web_fetch_enabled() -> bool:
    return bool(_LIVE_WEB_FETCH_ENABLED)


# قاموس بصري شامل لتحويل الكلمات العربية والدارجة الجزائرية إلى استعلامات فيكتور وموشن جرافيك دقيقة باللغة الإنجليزية
ARABIC_TO_ENGLISH_VISUAL_CONCEPTS: Dict[str, List[str]] = {
    "مونتاج": ["video-editing", "film-strip", "clapperboard", "timeline-edit"],
    "تمنتج": ["video-editing", "magic-wand", "scissors-cut", "sparkles"],
    "فيديو": ["video-camera", "play-circle", "film-reel", "cinema"],
    "فيديوهات": ["video-library", "multimedia", "play-screen", "reels"],
    "ريلز": ["smartphone-video", "instagram-reels", "tiktok", "mobile-play"],
    "للريلز": ["smartphone-video", "mobile-video", "short-video", "vertical-video"],
    "شورتس": ["smartphone-video", "youtube-shorts", "vertical-video"],
    "تيك توك": ["tiktok", "mobile-video", "music-video"],
    "التواصل": ["social-media", "share-network", "global-chat", "connect"],
    "الاجتماعي": ["social-network", "community", "heart-like", "share-nodes"],
    "ذكاء": ["artificial-intelligence", "brain-circuit", "neural-network", "cpu-chip"],
    "اصطناعي": ["ai-chip", "robot-brain", "magic-sparkles", "automation"],
    "الاصطناعي": ["ai-chip", "neural-network", "cpu-bolt", "sparkles"],
    "منصة": ["dashboard-layout", "web-platform", "laptop-code", "cloud-app"],
    "المنصة": ["web-app", "window-dashboard", "layers-stack", "rocket-launch"],
    "تطبيق": ["mobile-app", "smartphone-grid", "app-window"],
    "موقع": ["browser-window", "globe-web", "Monitor-dashboard"],
    "مشكل": ["alert-triangle", "bug-error", "warning-shield", "radar-scan"],
    "مشكلة": ["warning-octagon", "puzzle-piece", "wrench-fix", "shield-alert"],
    "الحل": ["lightbulb-idea", "check-badge", "key-solution", "magic-wand"],
    "حل": ["lightbulb-on", "shield-check", "sparkles-star"],
    "صوت": ["soundwave", "microphone", "audio-spectrum", "headphones"],
    "تعليق": ["microphone-studio", "voice-wave", "podcast-mic"],
    "ساوند": ["equalizer", "speaker-wave", "music-note", "soundwave"],
    "صمت": ["volume-mute", "Waveform-cut", "scissors", "audio-trim"],
    "تقطيع": ["scissors-cut", "film-cut", "slice-tool", "timeline"],
    "قص": ["scissors", "crop-frame", "razor-blade"],
    "وقت": ["stopwatch", "hourglass", "clock-fast", "timer-flash"],
    "ساعة": ["clock", "time-schedule", "alarm-clock"],
    "ساعات": ["hourglass-Half", "time-history", "clock-rotate"],
    "دقيقة": ["stopwatch-fast", "lightning-bolt", "speedometer"],
    "ثواني": ["bolt-lightning", "gauge-fast", "timer"],
    "سرعة": ["speedometer", "rocket-thrust", "lightning-flash", "fast-forward"],
    "سريع": ["lightning", "rocket", "gauge-high", "wind-fast"],
    "إنتاجية": ["chart-trend-up", "rocket-growth", "trophy-star", "target-arrow"],
    "الإنتاجية": ["trending-up", "bar-chart-grow", "zap-bolt", "award"],
    "ترفع": ["arrow-up-circle", "trending-up", "rocket", "graph-up"],
    "مشاهدات": ["eye-view", "trending-fire", "users-group", "chart-line"],
    "تفاعل": ["heart-flame", "thumbs-up", "message-circle", "share-network"],
    "انتشار": ["viral-network", "globe-share", "rocket-launch", "megaphone"],
    "تصوير": ["camera-lens", "video-recorder", "aperture", "tripod"],
    "تصور": ["camera", "shutter", "smartphone-camera", "studio-light"],
    "كاميرا": ["camera-dslr", "lens-aperture", "video-cam"],
    "ألوان": ["color-palette", "paint-brush", "swatch-book", "droplet"],
    "تصميم": ["bezier-curve", "pen-tool", "layers", "compass-draft"],
    "موشن": ["motion-bounce", "keyframes", "sparkles-wand", "orbit-nodes"],
    "جرافيك": ["vector-pen", "shapes-cube", "layers-3d", "palette"],
    "كابل": ["usb-cable", "plug-zap", "battery-charging", "power-cord"],
    "شاحن": ["battery-bolt", "zap-fast", "plug-charging", "power-adapter"],
    "تشارجي": ["battery-charging", "lightning-bolt", "smartphone-charging"],
    "بطارية": ["battery-full", "battery-bolt", "power-gauge"],
    "سيبور": ["smartphone-stand", "phone-holder", "desktop-dock", "tripod"],
    "قماش": ["shield-check", "layers-weave", "feather-strong", "lock-shield"],
    "متين": ["shield-lock", "anvil-strong", "diamond-gem", "medal"],
    "يتقطع": ["scissors-off", "shield-protect", "link-strong"],
    "توصيل": ["truck-delivery", "package-box", "map-pin", "fast-shipping"],
    "ولاية": ["map-location", "compass-pin", "globe-africa", "route-map"],
    "سعر": ["tag-price", "coins-stack", "wallet-money", "gift-box"],
    "باطل": ["gift-sparkles", "tag-discount", "star-badge"],
    "اكموندي": ["shopping-cart", "cursor-click", "bag-check", "package-send"],
    "اطلب": ["shopping-bag", "mouse-pointer-click", "check-circle"],
    "أهلاً": ["sparkles", "rocket-growth", "star-badge", "crown-star"],
    "السلام": ["sparkles", "rocket-growth", "lightbulb-idea", "dashboard-layout"],
    "أبني": ["hammer-wrench", "code-brackets", "blocks-build", "rocket"],
    "أحاول": ["compass", "target-bullseye", "lightbulb", "gear-cog"],
    "أغلب": ["users-group", "pie-chart", "globe-users"],
    "الناس": ["users-crowd", "community-network", "user-check"],
    "احترافي": ["crown-star", "diamond", "award-medal", "sparkles"],
    "أوتوماتيكي": ["cpu-gear", "refresh-auto", "magic-wand", "robot"],
}

# مكتبة مسارات SVG الفيكتور الاحترافية المدمجة كاحتياطي فوري ومولّد إجرائي متعدد الطبقات
BUILTIN_RICHVECTOR_SVG_PATHS: Dict[str, List[str]] = {
    "video-editing": [
        "M40,60 L216,60 C224,60 230,66 230,74 L230,182 C230,190 224,196 216,196 L40,196 C32,196 26,190 26,182 L26,74 C26,66 32,60 40,60 Z",
        "M26,92 L230,92 M68,60 L84,92 M120,60 L136,92 M172,60 L188,92",
        "M108,116 L160,144 L108,172 Z"
    ],
    "artificial-intelligence": [
        "M84,84 L172,84 L172,172 L84,172 Z",
        "M104,104 L152,104 L152,152 L104,152 Z",
        "M104,52 L104,84 M128,44 L128,84 M152,52 L152,84 M104,172 L104,204 M128,172 L128,212 M152,172 L152,204",
        "M52,104 L84,104 M44,128 L84,128 M52,152 L84,152 M172,104 L204,104 M172,128 L212,128 M172,152 L204,152"
    ],
    "smartphone-video": [
        "M82,28 L174,28 C185,28 194,37 194,48 L194,208 C194,219 185,228 174,228 L82,228 C71,228 62,219 62,208 L62,48 C62,37 71,28 82,28 Z",
        "M110,44 L146,44",
        "M112,104 L154,128 L112,152 Z",
        "M86,188 L170,188"
    ],
    "rocket-growth": [
        "M128,32 C164,56 184,98 184,144 L156,172 L100,172 L72,144 C72,98 92,56 128,32 Z",
        "M128,88 C139,88 148,97 148,108 C148,119 139,128 128,128 C117,128 108,119 108,108 C108,97 117,88 128,88 Z",
        "M72,144 L48,168 L68,188 L100,172 M184,144 L208,168 L188,188 L156,172",
        "M108,172 L118,216 L128,198 L138,216 L148,172"
    ],
    "soundwave": [
        "M36,128 L36,128 M62,96 L62,160 M88,64 L88,192 M114,84 L114,172 M140,48 L140,208 M166,76 L166,180 M192,96 L192,160 M218,114 L218,142"
    ],
    "scissors-cut": [
        "M72,76 C88,76 100,88 100,104 C100,120 88,132 72,132 C56,132 44,120 44,104 C44,88 56,76 72,76 Z",
        "M72,148 C88,148 100,160 100,176 C100,192 88,204 72,204 C56,204 44,192 44,176 C44,160 56,148 72,148 Z",
        "M96,116 L212,184 M96,164 L212,96"
    ],
    "lightbulb-idea": [
        "M92,164 C72,146 64,120 72,92 C80,64 104,44 128,44 C152,44 176,64 184,92 C192,120 184,146 164,164 L156,188 L100,188 L92,164 Z",
        "M104,204 L152,204 M112,220 L144,220",
        "M128,18 L128,32 M48,56 L60,68 M208,56 L196,68"
    ],
    "speedometer": [
        "M44,168 C32,120 60,68 108,54 C156,40 208,68 216,116 C220,134 218,152 212,168",
        "M128,148 L178,94",
        "M116,148 C116,141 121,136 128,136 C135,136 140,141 140,148 C140,155 135,160 128,160 C121,160 116,155 116,148 Z"
    ],
    "shield-check": [
        "M128,32 L208,64 L208,128 C208,176 172,212 128,228 C84,212 48,176 48,128 L48,64 L128,32 Z",
        "M92,128 L118,154 L168,102"
    ],
    "truck-delivery": [
        "M28,72 L152,72 L152,172 L28,172 Z",
        "M152,100 L196,100 L224,136 L224,172 L152,172 Z",
        "M72,172 C72,185 61,196 48,196 C35,196 24,185 24,172 M196,172 C196,185 185,196 172,196 C159,196 148,185 148,172"
    ],
    "dashboard-layout": [
        "M32,44 L224,44 C230,44 236,50 236,56 L236,200 C236,206 230,212 224,212 L32,212 C26,212 20,206 20,200 L20,56 C20,50 26,44 32,44 Z",
        "M20,80 L236,80 M88,80 L88,212",
        "M116,112 L204,112 M116,144 L184,144 M116,176 L204,176"
    ],
}


def translate_scene_to_web_vector_queries(scene_text_ar: str, fallback_topic: str = "") -> List[str]:
    """
    يحول نص الجملة المنطوقة بالعربية/الدارجة إلى قائمة استعلامات بحث فيكتور إنجليزية دقيقة
    للبحث الحي في مكتبات الموشن جرافيك والـ SVG على الإنترنت (Iconify / Lottie / Open SVG).
    """
    queries: List[str] = []
    clean_txt = re.sub(r"[،,.!؟?()\[\]\-\":؛]", " ", str(scene_text_ar or "")).strip()
    tokens = [t.strip() for t in clean_txt.split() if len(t.strip()) >= 2]

    # إعطاء الأولوية للكلمات الموضوعية الفعلية في الجملة على كلمات التحية الافتتاحية (مثل السلام عليكم)
    greeting_set = {"السلام", "سلام", "عليكم", "أهلاً", "اهلا", "مرحبا", "صباح", "مساء"}
    topic_tokens = [t for t in tokens if t.lower() not in greeting_set]
    ordered_tokens = topic_tokens + [t for t in tokens if t.lower() in greeting_set]

    for tok in ordered_tokens:
        tok_low = tok.lower()
        # مطابقة مباشرة أو جزئية في القاموس البصري
        if tok_low in ARABIC_TO_ENGLISH_VISUAL_CONCEPTS:
            for q in ARABIC_TO_ENGLISH_VISUAL_CONCEPTS[tok_low]:
                if q not in queries:
                    queries.append(q)
        else:
            for ar_k, en_list in ARABIC_TO_ENGLISH_VISUAL_CONCEPTS.items():
                if len(ar_k) >= 3 and (ar_k in tok_low or tok_low in ar_k):
                    for q in en_list:
                        if q not in queries:
                            queries.append(q)

    # إذا كان هناك كلمات إنجليزية منطوقة أصلاً في النص
    en_words = re.findall(r"[a-zA-Z]{3,}", clean_txt)
    for ew in en_words:
        ew_l = ew.lower()
        if ew_l not in queries:
            queries.append(ew_l)

    if not queries:
        ft = str(fallback_topic or "").lower()
        if "reel" in ft or "smartphone" in ft:
            queries.extend(["smartphone-video", "video-editing", "social-media"])
        elif "ai" in ft or "neural" in ft:
            queries.extend(["artificial-intelligence", "cpu-chip", "sparkles"])
        elif "delivery" in ft or "commerce" in ft:
            queries.extend(["truck-delivery", "shopping-bag", "shield-check"])
        else:
            queries.extend(["rocket-growth", "dashboard-layout", "lightbulb-idea"])

    return queries[:5]


def search_and_fetch_web_vectors(
    scene_text_ar: str,
    fallback_topic: str = "",
    max_assets: int = 3,
    allow_network: Optional[bool] = None
) -> List[str]:
    """
    يبحث حياً في الإنترنت (عبر محرك Iconify المفتوح الذي يضم +200,000 شكل فيكتور وموشن جرافيك
    من مجموعات Solar, Phosphor, Fluent, Lucide, Tabler, Streamline) ويحمل ملفات الـ SVG المطابقة
    لمعنى الجملة المنطوقة، ويخزنها في الكاش المحلي `assets/web_motion_cache/`.
    كما يبحث أولاً في حزمة المستخدم الضخمة (`assets/custom_motion_pack/`) إن كانت مربوطة!
    """
    use_net = _LIVE_WEB_FETCH_ENABLED if allow_network is None else bool(allow_network)
    queries = translate_scene_to_web_vector_queries(scene_text_ar, fallback_topic=fallback_topic)
    fetched_svgs: List[str] = []

    # 1. البحث في حزمة الموشن جرافيك الخاصة بالمستخدم (400MB+ Pack) إن وجدت
    custom_svgs = load_matching_pack_svg_assets(queries, max_count=max_assets)
    for c_svg in custom_svgs:
        if c_svg and "<svg" in c_svg:
            fetched_svgs.append(c_svg)
            if len(fetched_svgs) >= max_assets:
                return fetched_svgs

    # 2. البحث في الكاش المحلي أو الجلب الحي من الإنترنت (Iconify Open Vector API)
    for q in queries:
        if len(fetched_svgs) >= max_assets:
            break
        safe_q = re.sub(r"[^a-zA-Z0-9_-]", "_", q.lower()).strip("_") or "vector"
        cache_svg_path = os.path.join(WEB_MOTION_CACHE_DIR, f"{safe_q}.svg")

        if os.path.exists(cache_svg_path):
            try:
                with open(cache_svg_path, "r", encoding="utf-8") as f:
                    cached_xml = f.read()
                if "<svg" in cached_xml and ("<path" in cached_xml or "<circle" in cached_xml or "<rect" in cached_xml or "<polygon" in cached_xml):
                    fetched_svgs.append(cached_xml)
                    continue
            except Exception:
                pass

        if use_net:
            try:
                # نبحث في مجموعات الموشن جرافيك الحديثة (solar, ph, lucide, tabler, fluent, mdi)
                search_url = f"https://api.iconify.design/search?query={urllib.parse.quote(q)}&limit=6&prefixes=solar,ph,lucide,tabler,fluent,mdi"
                resp = requests.get(search_url, timeout=1.8)
                if resp.status_code == 200:
                    s_data = resp.json()
                    icons_list = s_data.get("icons", [])
                    for icon_id in icons_list[:3]:
                        if ":" in icon_id:
                            pref, name = icon_id.split(":", 1)
                            svg_url = f"https://api.iconify.design/{pref}/{name}.svg?height=256"
                            svg_resp = requests.get(svg_url, timeout=1.8)
                            if svg_resp.status_code == 200 and "<svg" in svg_resp.text:
                                svg_xml = svg_resp.text
                                try:
                                    with open(cache_svg_path, "w", encoding="utf-8") as f:
                                        f.write(svg_xml)
                                except Exception:
                                    pass
                                fetched_svgs.append(svg_xml)
                                break
            except Exception:
                pass

    # 3. توليد فيكتور غني متعدد الطبقات ومطابق للمفهوم إذا كان السيرفر أوفلاين أو لم يكفِ العدد
    for q in queries:
        if len(fetched_svgs) >= max_assets:
            break
        paths = BUILTIN_RICHVECTOR_SVG_PATHS.get(q)
        if not paths:
            # اختيار أقرب شكل من المكتبة المدمجة بناءً على الكلمات
            for k_b, v_b in BUILTIN_RICHVECTOR_SVG_PATHS.items():
                if any(part in q for part in k_b.split("-")) or any(part in k_b for part in q.split("-")):
                    paths = v_b
                    break
        if not paths:
            k_list = list(BUILTIN_RICHVECTOR_SVG_PATHS.keys())
            q_hash = int(hashlib.md5(q.encode("utf-8")).hexdigest()[:6], 16)
            paths = BUILTIN_RICHVECTOR_SVG_PATHS[k_list[q_hash % len(k_list)]]

        inner_paths = "".join(
            f'<path d="{d_str}" fill="none" stroke="#PRIMARY#" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
            for d_str in paths
        )
        synth_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">{inner_paths}</svg>'
        fetched_svgs.append(synth_svg)

    return fetched_svgs[:max_assets]


# ==============================================================================
# 5.2 محلل ومصيّر مسارات الفيكتور الكامل (Full SVG Path `<path d="...">` Parser & Theme Recolorer)
# ==============================================================================
_SVG_CMD_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


def _cubic_bezier_pt(p0: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    mt = 1.0 - t
    x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
    y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
    return (x, y)


def _quad_bezier_pt(p0: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], t: float) -> Tuple[float, float]:
    mt = 1.0 - t
    x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
    y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
    return (x, y)


def parse_svg_path_to_polylines(d_attr: str, curve_steps: int = 10) -> List[List[Tuple[float, float]]]:
    """
    يحلل خاصية `d="..."` لأي ملف SVG مستخرج من الإنترنت (بجميع أوامر الفيكتور: M, L, H, V, C, S, Q, T, A, Z)
    ويحولها إلى سلاسل نقاط هندسية فائقة الدقة قابلة للرسم التدريجي (`Trim Paths`) وإعادة التلوين بألوان ثيم الفيديو!
    """
    if not d_attr:
        return []

    tokens: List[Union[str, float]] = []
    for m in _SVG_CMD_RE.finditer(d_attr):
        cmd_g, num_g = m.group(1), m.group(2)
        if cmd_g:
            tokens.append(cmd_g)
        elif num_g:
            try:
                tokens.append(float(num_g))
            except Exception:
                pass

    polylines: List[List[Tuple[float, float]]] = []
    curr_line: List[Tuple[float, float]] = []
    cx, cy = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    last_ctrl_x, last_ctrl_y = 0.0, 0.0
    last_cmd = ""

    idx = 0
    n = len(tokens)
    while idx < n:
        tok = tokens[idx]
        if isinstance(tok, str):
            cmd = tok
            idx += 1
        else:
            if not last_cmd:
                idx += 1
                continue
            cmd = "L" if last_cmd == "M" else ("l" if last_cmd == "m" else last_cmd)

        is_rel = cmd.islower()
        cmd_u = cmd.upper()

        if cmd_u == "M":
            if idx + 1 >= n or not isinstance(tokens[idx], float) or not isinstance(tokens[idx + 1], float):
                break
            nx, ny = float(tokens[idx]), float(tokens[idx + 1])
            idx += 2
            cx = (cx + nx) if is_rel else nx
            cy = (cy + ny) if is_rel else ny
            start_x, start_y = cx, cy
            if len(curr_line) >= 2:
                polylines.append(curr_line)
            curr_line = [(cx, cy)]
            last_ctrl_x, last_ctrl_y = cx, cy
            last_cmd = cmd

        elif cmd_u == "L":
            if idx + 1 >= n or not isinstance(tokens[idx], float) or not isinstance(tokens[idx + 1], float):
                break
            nx, ny = float(tokens[idx]), float(tokens[idx + 1])
            idx += 2
            cx = (cx + nx) if is_rel else nx
            cy = (cy + ny) if is_rel else ny
            if not curr_line:
                curr_line = [(cx, cy)]
            else:
                curr_line.append((cx, cy))
            last_ctrl_x, last_ctrl_y = cx, cy
            last_cmd = cmd

        elif cmd_u == "H":
            if idx >= n or not isinstance(tokens[idx], float):
                break
            nx = float(tokens[idx])
            idx += 1
            cx = (cx + nx) if is_rel else nx
            if curr_line:
                curr_line.append((cx, cy))
            last_ctrl_x, last_ctrl_y = cx, cy
            last_cmd = cmd

        elif cmd_u == "V":
            if idx >= n or not isinstance(tokens[idx], float):
                break
            ny = float(tokens[idx])
            idx += 1
            cy = (cy + ny) if is_rel else ny
            if curr_line:
                curr_line.append((cx, cy))
            last_ctrl_x, last_ctrl_y = cx, cy
            last_cmd = cmd

        elif cmd_u == "C":
            if idx + 5 >= n:
                break
            vals = tokens[idx:idx + 6]
            if not all(isinstance(v, float) for v in vals):
                idx += 1
                continue
            idx += 6
            x1, y1, x2, y2, ex, ey = [float(v) for v in vals]
            if is_rel:
                x1, y1 = cx + x1, cy + y1
                x2, y2 = cx + x2, cy + y2
                ex, ey = cx + ex, cy + ey
            p0 = (cx, cy)
            for s_i in range(1, curve_steps + 1):
                pt = _cubic_bezier_pt(p0, (x1, y1), (x2, y2), (ex, ey), s_i / float(curve_steps))
                curr_line.append(pt)
            cx, cy = ex, ey
            last_ctrl_x, last_ctrl_y = x2, y2
            last_cmd = cmd

        elif cmd_u == "S":
            if idx + 3 >= n:
                break
            vals = tokens[idx:idx + 4]
            if not all(isinstance(v, float) for v in vals):
                idx += 1
                continue
            idx += 4
            x2, y2, ex, ey = [float(v) for v in vals]
            if is_rel:
                x2, y2 = cx + x2, cy + y2
                ex, ey = cx + ex, cy + ey
            x1 = 2 * cx - last_ctrl_x if last_cmd.upper() in ("C", "S") else cx
            y1 = 2 * cy - last_ctrl_y if last_cmd.upper() in ("C", "S") else cy
            p0 = (cx, cy)
            for s_i in range(1, curve_steps + 1):
                pt = _cubic_bezier_pt(p0, (x1, y1), (x2, y2), (ex, ey), s_i / float(curve_steps))
                curr_line.append(pt)
            cx, cy = ex, ey
            last_ctrl_x, last_ctrl_y = x2, y2
            last_cmd = cmd

        elif cmd_u in ("Q", "T"):
            if cmd_u == "Q":
                if idx + 3 >= n:
                    break
                vals = tokens[idx:idx + 4]
                if not all(isinstance(v, float) for v in vals):
                    idx += 1
                    continue
                idx += 4
                x1, y1, ex, ey = [float(v) for v in vals]
                if is_rel:
                    x1, y1 = cx + x1, cy + y1
                    ex, ey = cx + ex, cy + ey
            else:
                if idx + 1 >= n:
                    break
                vals = tokens[idx:idx + 2]
                if not all(isinstance(v, float) for v in vals):
                    idx += 1
                    continue
                idx += 2
                ex, ey = [float(v) for v in vals]
                if is_rel:
                    ex, ey = cx + ex, cy + ey
                x1 = 2 * cx - last_ctrl_x if last_cmd.upper() in ("Q", "T") else cx
                y1 = 2 * cy - last_ctrl_y if last_cmd.upper() in ("Q", "T") else cy
            p0 = (cx, cy)
            for s_i in range(1, curve_steps + 1):
                pt = _quad_bezier_pt(p0, (x1, y1), (ex, ey), s_i / float(curve_steps))
                curr_line.append(pt)
            cx, cy = ex, ey
            last_ctrl_x, last_ctrl_y = x1, y1
            last_cmd = cmd

        elif cmd_u == "A":
            if idx + 6 >= n:
                break
            vals = tokens[idx:idx + 7]
            if not all(isinstance(v, float) for v in vals):
                idx += 1
                continue
            idx += 7
            rx_a, ry_a, rot_a, large_arc, sweep_f, ex, ey = [float(v) for v in vals]
            if is_rel:
                ex, ey = cx + ex, cy + ey
            # تقريب سلس لقوس الـ SVG
            p0 = (cx, cy)
            mid_x = (cx + ex) * 0.5 + (ey - cy) * (0.28 if sweep_f > 0 else -0.28)
            mid_y = (cy + ey) * 0.5 + (cx - ex) * (0.28 if sweep_f > 0 else -0.28)
            for s_i in range(1, curve_steps + 1):
                pt = _quad_bezier_pt(p0, (mid_x, mid_y), (ex, ey), s_i / float(curve_steps))
                curr_line.append(pt)
            cx, cy = ex, ey
            last_ctrl_x, last_ctrl_y = cx, cy
            last_cmd = cmd

        elif cmd_u == "Z":
            if curr_line:
                curr_line.append((start_x, start_y))
                if len(curr_line) >= 2:
                    polylines.append(curr_line)
                curr_line = []
            cx, cy = start_x, start_y
            last_cmd = cmd
        else:
            idx += 1

    if len(curr_line) >= 2:
        polylines.append(curr_line)

    return polylines


def extract_all_polylines_from_svg(svg_xml: str) -> Tuple[List[List[Tuple[float, float]]], float, float]:
    """
    يستخرج كافة المسارات الهندسية من أي ملف SVG (سواء `<path>`, `<circle>`, `<rect>`, `<ellipse>`, `<line>`, `<polyline>`, `<polygon>`)
    مع أبعاد الـ `viewBox` الأصلية لتسهيل تحجيمها ورسمها بألوان الثيم النشط.
    """
    polylines: List[List[Tuple[float, float]]] = []
    vb_w, vb_h = 24.0, 24.0
    try:
        clean_xml = re.sub(r'xmlns="[^"]+"', "", svg_xml)
        root = ET.fromstring(clean_xml)
        vb = root.attrib.get("viewBox", "")
        if vb:
            parts = [float(x) for x in re.split(r"[\s,]+", vb.strip()) if x]
            if len(parts) == 4:
                vb_w, vb_h = max(1.0, parts[2]), max(1.0, parts[3])
        else:
            w_attr = re.sub(r"[^0-9.]", "", root.attrib.get("width", "24"))
            h_attr = re.sub(r"[^0-9.]", "", root.attrib.get("height", "24"))
            if w_attr and h_attr:
                vb_w, vb_h = max(1.0, float(w_attr)), max(1.0, float(h_attr))

        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()
            if tag == "path":
                d_str = elem.attrib.get("d", "")
                polylines.extend(parse_svg_path_to_polylines(d_str))
            elif tag == "circle":
                cx_c = float(elem.attrib.get("cx", 0))
                cy_c = float(elem.attrib.get("cy", 0))
                r_c = float(elem.attrib.get("r", 0))
                if r_c > 0:
                    pts = [(cx_c + r_c * math.cos(i * 2 * math.pi / 24), cy_c + r_c * math.sin(i * 2 * math.pi / 24)) for i in range(25)]
                    polylines.append(pts)
            elif tag == "ellipse":
                cx_c = float(elem.attrib.get("cx", 0))
                cy_c = float(elem.attrib.get("cy", 0))
                rx_c = float(elem.attrib.get("rx", 0))
                ry_c = float(elem.attrib.get("ry", 0))
                if rx_c > 0 and ry_c > 0:
                    pts = [(cx_c + rx_c * math.cos(i * 2 * math.pi / 24), cy_c + ry_c * math.sin(i * 2 * math.pi / 24)) for i in range(25)]
                    polylines.append(pts)
            elif tag == "rect":
                rx = float(elem.attrib.get("x", 0))
                ry = float(elem.attrib.get("y", 0))
                rw = float(elem.attrib.get("width", 0))
                rh = float(elem.attrib.get("height", 0))
                if rw > 0 and rh > 0:
                    polylines.append([(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh), (rx, ry)])
            elif tag == "line":
                x1 = float(elem.attrib.get("x1", 0))
                y1 = float(elem.attrib.get("y1", 0))
                x2 = float(elem.attrib.get("x2", 0))
                y2 = float(elem.attrib.get("y2", 0))
                polylines.append([(x1, y1), (x2, y2)])
            elif tag in ("polyline", "polygon"):
                pts_raw = elem.attrib.get("points", "").strip()
                nums = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", pts_raw)]
                pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
                if tag == "polygon" and len(pts) >= 3:
                    pts.append(pts[0])
                if len(pts) >= 2:
                    polylines.append(pts)
    except Exception:
        pass

    return polylines, vb_w, vb_h


def render_recolored_svg_motion_canvas(
    svg_xml: str,
    width: int,
    height: int,
    theme_palette: Dict[str, Any],
    choreo_u: float,
    global_t: float,
    stroke_scale: float = 1.0
) -> Image.Image:
    """
    يرسم أي شكل فيكتور (SVG) بدقة استوديو فائقة النعومة (`PyCairo Sub-Pixel Anti-Aliasing + Linear Gradients`):
    - يستخدم `cairo.ANTIALIAS_BEST` مع `LINE_CAP_ROUND` و`LINE_JOIN_ROUND` وتدرجات لونية متوهجة.
    - لا يرسم أبداً خطوطاً منكسرة أو كرات صفراء فاقعة في نهاية الخطوط!
    """
    width = max(32, int(width))
    height = max(32, int(height))
    primary_c = tuple(theme_palette.get("primary", (56, 189, 248)))[:3]
    secondary_c = tuple(theme_palette.get("secondary", (250, 204, 21)))[:3]
    accent_c = tuple(theme_palette.get("accent", (16, 185, 129)))[:3]
    palette_cycle = [primary_c, secondary_c, accent_c]

    polylines, vb_w, vb_h = extract_all_polylines_from_svg(svg_xml)
    if not polylines:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))

    all_x = [p[0] for line in polylines for p in line]
    all_y = [p[1] for line in polylines for p in line]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    span_w = max(1e-3, max_x - min_x)
    span_h = max(1e-3, max_y - min_y)

    pad = 0.20
    usable_w = width * (1.0 - 2 * pad)
    usable_h = height * (1.0 - 2 * pad)
    scale = min(usable_w / span_w, usable_h / span_h)

    cx_svg = (min_x + max_x) * 0.5
    cy_svg = (min_y + max_y) * 0.5
    cx_can = width * 0.5
    cy_can = height * 0.5

    trim_prog = min(1.0, max(0.35, choreo_u * 1.45))
    line_w = max(2.8, min(width, height) * 0.048 * stroke_scale)

    if _HAS_CAIRO:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_antialias(cairo.ANTIALIAS_BEST)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        for l_idx, line in enumerate(polylines):
            col1 = palette_cycle[l_idx % len(palette_cycle)]
            col2 = palette_cycle[(l_idx + 1) % len(palette_cycle)]
            transformed = [
                (
                    cx_can + (pt[0] - cx_svg) * scale,
                    cy_can + (pt[1] - cy_svg) * scale
                )
                for pt in line
            ]
            if len(transformed) < 2:
                continue

            is_closed = (math.hypot(transformed[0][0] - transformed[-1][0], transformed[0][1] - transformed[-1][1]) <= 6.5)
            vis_count = max(2, int(math.ceil(len(transformed) * trim_prog)))
            vis_pts = transformed[:vis_count]

            # تعبئة ناعمة بتدرج زجاجي للمسارات المغلقة
            if is_closed and len(transformed) >= 4 and trim_prog >= 0.55:
                ctx.new_path()
                ctx.move_to(transformed[0][0], transformed[0][1])
                for px, py in transformed[1:]:
                    ctx.line_to(px, py)
                ctx.close_path()
                grad_fill = cairo.LinearGradient(0, 0, width, height)
                grad_fill.add_color_stop_rgba(0.0, col1[0] / 255.0, col1[1] / 255.0, col1[2] / 255.0, 0.24)
                grad_fill.add_color_stop_rgba(1.0, col2[0] / 255.0, col2[1] / 255.0, col2[2] / 255.0, 0.08)
                ctx.set_source(grad_fill)
                ctx.fill()

            # هالة التوهج الناعمة خلف المسار
            ctx.new_path()
            ctx.move_to(vis_pts[0][0], vis_pts[0][1])
            for px, py in vis_pts[1:]:
                ctx.line_to(px, py)
            if is_closed and trim_prog >= 0.96:
                ctx.close_path()
            ctx.set_source_rgba(col1[0] / 255.0, col1[1] / 255.0, col1[2] / 255.0, 0.22)
            ctx.set_line_width(line_w * 2.1)
            ctx.stroke_preserve()

            # المسار الرئيسي بتدرج لوني فائق النعومة
            grad_stroke = cairo.LinearGradient(0, 0, width, height)
            grad_stroke.add_color_stop_rgba(0.0, col1[0] / 255.0, col1[1] / 255.0, col1[2] / 255.0, 0.98)
            grad_stroke.add_color_stop_rgba(1.0, col2[0] / 255.0, col2[1] / 255.0, col2[2] / 255.0, 0.98)
            ctx.set_source(grad_stroke)
            ctx.set_line_width(line_w)
            ctx.stroke()

        buf = surface.get_data()
        arr = np.ndarray(shape=(height, width, 4), dtype=np.uint8, buffer=buf).copy()
        arr = arr[:, :, [2, 1, 0, 3]]
        return Image.fromarray(arr, "RGBA")

    # Fallback: Supersampled 2x Anti-Aliased Pillow
    ss = 2
    canvas_ss = Image.new("RGBA", (width * ss, height * ss), (0, 0, 0, 0))
    draw_ss = ImageDraw.Draw(canvas_ss, "RGBA")
    for l_idx, line in enumerate(polylines):
        col = palette_cycle[l_idx % len(palette_cycle)]
        transformed = [
            (
                int(round((cx_can + (pt[0] - cx_svg) * scale) * ss)),
                int(round((cy_can + (pt[1] - cy_svg) * scale) * ss))
            )
            for pt in line
        ]
        if len(transformed) >= 2:
            vis_count = max(2, int(math.ceil(len(transformed) * trim_prog)))
            draw_ss.line(transformed[:vis_count], fill=(*col, 255), width=max(3, int(line_w * ss)))
    return canvas_ss.resize((width, height), Image.Resampling.LANCZOS)


def render_web_fetched_motion_scene(
    img: Image.Image,
    stage_bbox: Tuple[int, int, int, int],
    choreo_u: float,
    global_t: float,
    style_spec: Dict[str, Any],
    scene_meta: Dict[str, Any],
    concept_title: str,
    kpi_val: str,
    kpi_lbl: str,
    draw_contained_text_fn,
    draw_arabic_text_fn,
    get_font_fn,
    draw_cursor_fn
) -> Image.Image:
    """
    مشهد استوديو ثلاثي الأبعاد فائق الاحترافية (`3D Glass Bento & PyCairo Live Vector Showcase`):
    - يستبدل الدائرة السوداء البدائية ببطاقة واجهة زجاجية ثلاثية الأبعاد (Apple/SaaS 3D Glass Card)
      ذات ظلال Gaussian ناعمة، شريط نافذة علوي أنيق، أيقونات فيكتور مرسومة بـ PyCairo،
      ومنحنى طاقة متوهج متحرك مع بطاقتين عائمتين بفيزياء الزنبرك!
    """
    w, h = img.size
    st_x1, st_y1, st_x2, st_y2 = stage_bbox
    st_w = max(160, st_x2 - st_x1)
    st_h = max(160, st_y2 - st_y1)
    cx = (st_x1 + st_x2) // 2
    cy = st_y1 + int(st_h * 0.46)

    pal = style_spec.get("palette", {})
    is_light_bg = bool(pal.get("is_light_bg", False))
    primary_c = tuple(pal.get("primary", (56, 189, 248)))[:3]
    secondary_c = tuple(pal.get("secondary", (250, 204, 21)))[:3]
    accent_c = tuple(pal.get("accent", (16, 185, 129)))[:3]
    txt_main = (20, 24, 33) if is_light_bg else (248, 250, 252)
    card_bg = (255, 255, 255, 244) if is_light_bg else (17, 24, 39, 238)
    sub_card_bg = (248, 250, 252, 248) if is_light_bg else (30, 41, 59, 242)

    raw_speech = str(scene_meta.get("text") or concept_title or "")
    fallback_topic = str(scene_meta.get("visual_subject") or scene_meta.get("scene_type") or "")
    svgs = search_and_fetch_web_vectors(raw_speech, fallback_topic=fallback_topic, max_assets=3)

    img = render_radial_ambient_glow(img, (cx, cy), int(min(st_w, st_h) * 0.50), primary_c, intensity=0.24 if is_light_bg else 0.36)
    img = render_floating_particles_layer(
        canvas_rgba=img,
        global_t=global_t,
        theme={"primary": primary_c, "secondary": secondary_c},
        count=10,
        region_bbox=stage_bbox
    )

    p_in = min(1.0, max(0.08, choreo_u * 2.1))
    sp_main = 1.0 - math.exp(-6.2 * p_in) * math.cos(8.0 * p_in)
    float_dy = int(5.0 * math.sin(global_t * 2.4))

    # 1. البطاقة الزجاجية الرئيسية ثلاثية الأبعاد (3D Elevated Studio Glass Deck)
    deck_w = int(st_w * 0.88 * max(0.75, min(1.03, sp_main)))
    deck_h = int(st_h * 0.58 * max(0.75, min(1.03, sp_main)))
    dx1 = cx - deck_w // 2
    dy1 = cy - deck_h // 2 - int(st_h * 0.06) + float_dy
    dx2, dy2 = dx1 + deck_w, dy1 + deck_h

    # ظل Gaussian عميق ثلاثي الأبعاد خلف البطاقة
    sh_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh_layer, "RGBA")
    sh_draw.rounded_rectangle([(dx1 + 4, dy1 + 16), (dx2 + 4, dy2 + 18)], radius=28, fill=(8, 12, 24, 78 if is_light_bg else 125))
    sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(radius=16))
    img = Image.alpha_composite(img, sh_layer)

    draw = ImageDraw.Draw(img, "RGBA")
    draw.rounded_rectangle([(dx1, dy1), (dx2, dy2)], radius=26, fill=card_bg, outline=(*primary_c, 215), width=2)

    # شريط علوي أنيق بأسلوب نافذة macOS Studio
    hdr_h = max(32, int(deck_h * 0.17))
    draw.rounded_rectangle([(dx1 + 2, dy1 + 2), (dx2 - 2, dy1 + hdr_h)], radius=24, fill=(*primary_c, 26 if is_light_bg else 38))
    dot_cols = [(239, 68, 68), (245, 158, 11), (16, 185, 129)]
    for di, dcol in enumerate(dot_cols):
        dot_x = dx1 + 22 + di * 16
        dot_y = dy1 + hdr_h // 2
        draw.ellipse([(dot_x - 5, dot_y - 5), (dot_x + 5, dot_y + 5)], fill=(*dcol, 245))

    # كبسولة حالة ذكية في يمين الهيدر
    pill_w = min(130, int(deck_w * 0.34))
    draw.rounded_rectangle([(dx2 - pill_w - 14, dy1 + 7), (dx2 - 14, dy1 + hdr_h - 7)], radius=12, fill=(*primary_c, 45), outline=(*primary_c, 180), width=1)
    draw.ellipse([(dx2 - 26, dy1 + hdr_h // 2 - 4), (dx2 - 18, dy1 + hdr_h // 2 + 4)], fill=(*accent_c, 255))

    # 2. قسم الأيقونة ثلاثية الأبعاد المرسومة بـ PyCairo داخل كبسولة متوهجة
    icon_box_sz = int(min(deck_w * 0.36, (deck_h - hdr_h) * 0.76))
    ic_cx = dx1 + int(deck_w * 0.26)
    ic_cy = dy1 + hdr_h + (deck_h - hdr_h) // 2
    ir = icon_box_sz // 2
    draw.rounded_rectangle(
        [(ic_cx - ir, ic_cy - ir), (ic_cx + ir, ic_cy + ir)],
        radius=22,
        fill=(*primary_c, 24 if is_light_bg else 38),
        outline=(*primary_c, 165),
        width=2
    )
    if svgs:
        svg_render_sz = int(icon_box_sz * 0.82)
        main_svg_img = render_recolored_svg_motion_canvas(
            svg_xml=svgs[0],
            width=svg_render_sz,
            height=svg_render_sz,
            theme_palette=pal,
            choreo_u=choreo_u,
            global_t=global_t,
            stroke_scale=1.05
        )
        img.alpha_composite(main_svg_img, (ic_cx - svg_render_sz // 2, ic_cy - svg_render_sz // 2))
        draw = ImageDraw.Draw(img, "RGBA")

    # 3. قسم الرسم البياني الموجي التفاعلي والأعمدة الحية (PyCairo Animated Spline & Meter Bars) على يمين الأيقونة
    chart_x1 = dx1 + int(deck_w * 0.48)
    chart_x2 = dx2 - 18
    chart_y1 = dy1 + hdr_h + 16
    chart_y2 = dy2 - 16
    cw_box = max(60, chart_x2 - chart_x1)
    ch_box = max(50, chart_y2 - chart_y1)

    if _HAS_CAIRO and cw_box > 40 and ch_box > 36:
        csurf = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw_box, ch_box)
        cctx = cairo.Context(csurf)
        cctx.set_antialias(cairo.ANTIALIAS_BEST)
        cctx.set_line_cap(cairo.LINE_CAP_ROUND)
        cctx.set_line_join(cairo.LINE_JOIN_ROUND)

        # رسم 3 خطوط قياس تقدمية ناعمة في الأعلى
        for bi in range(3):
            by = 10 + bi * 15
            bar_prog = min(1.0, max(0.18, (choreo_u * 1.35 - bi * 0.12)))
            bcol = [primary_c, secondary_c, accent_c][bi % 3]
            cctx.set_source_rgba(0.5, 0.55, 0.65, 0.18)
            cctx.set_line_width(7.0)
            cctx.move_to(6, by)
            cctx.line_to(cw_box - 8, by)
            cctx.stroke()

            cctx.set_source_rgba(bcol[0] / 255.0, bcol[1] / 255.0, bcol[2] / 255.0, 0.95)
            cctx.set_line_width(7.0)
            cctx.move_to(6, by)
            cctx.line_to(6 + (cw_box - 14) * bar_prog, by)
            cctx.stroke()

        # منحنى موجة PyCairo متوهج أسفل الأشرطة
        wave_y0 = ch_box * 0.74
        wave_amp = ch_box * 0.18
        pts_w = []
        n_steps = 28
        vis_steps = max(4, int(n_steps * min(1.0, choreo_u * 1.35)))
        for si in range(vis_steps):
            u_x = si / float(n_steps - 1)
            wx = 6 + u_x * (cw_box - 12)
            wy = wave_y0 - wave_amp * math.sin(u_x * math.pi * 2.2 + global_t * 3.2) * min(1.0, u_x * 1.8)
            pts_w.append((wx, wy))

        if len(pts_w) >= 2:
            cctx.new_path()
            cctx.move_to(pts_w[0][0], ch_box - 4)
            for px, py in pts_w:
                cctx.line_to(px, py)
            cctx.line_to(pts_w[-1][0], ch_box - 4)
            cctx.close_path()
            g_area = cairo.LinearGradient(0, wave_y0 - wave_amp, 0, ch_box)
            g_area.add_color_stop_rgba(0.0, primary_c[0] / 255.0, primary_c[1] / 255.0, primary_c[2] / 255.0, 0.34)
            g_area.add_color_stop_rgba(1.0, primary_c[0] / 255.0, primary_c[1] / 255.0, primary_c[2] / 255.0, 0.02)
            cctx.set_source(g_area)
            cctx.fill()

            cctx.new_path()
            cctx.move_to(pts_w[0][0], pts_w[0][1])
            for px, py in pts_w[1:]:
                cctx.line_to(px, py)
            cctx.set_source_rgba(primary_c[0] / 255.0, primary_c[1] / 255.0, primary_c[2] / 255.0, 0.98)
            cctx.set_line_width(3.5)
            cctx.stroke()

        cbuf = csurf.get_data()
        carr = np.ndarray(shape=(ch_box, cw_box, 4), dtype=np.uint8, buffer=cbuf).copy()[:, :, [2, 1, 0, 3]]
        img.alpha_composite(Image.fromarray(carr, "RGBA"), (chart_x1, chart_y1))
        draw = ImageDraw.Draw(img, "RGBA")

    # 4. بطاقتان فرعيتان ثلاثيتا الأبعاد أسفل البطاقة الرئيسية (Staggered 3D Floating Bento Pods)
    words_clean = [w_tok for w_tok in re.findall(r"[؀-ۿa-zA-Z0-9]+", concept_title) if len(w_tok) >= 3]
    mid_idx = max(1, len(words_clean) // 2)
    pod1_txt = " ".join(words_clean[:mid_idx]) if words_clean else "تصميم ذكي"
    pod2_txt = " ".join(words_clean[mid_idx:]) if len(words_clean) > mid_idx else (kpi_lbl if kpi_lbl else "جودة احترافية")

    pod_w = (deck_w - 16) // 2
    pod_h = max(58, int(st_h * 0.20))
    pod_y = dy2 + 16
    for pi, (ptxt, pcol, pdelay) in enumerate([(pod1_txt, secondary_c, 0.16), (pod2_txt, accent_c, 0.28)]):
        if choreo_u <= pdelay:
            continue
        pu = min(1.0, (choreo_u - pdelay) / 0.34)
        psp = 1.0 - math.exp(-6.0 * pu) * math.cos(7.5 * pu)
        px1 = dx1 + pi * (pod_w + 16)
        py1 = pod_y + int(22 * (1.0 - min(1.0, psp)))
        px2, py2 = px1 + pod_w, py1 + pod_h

        draw.rounded_rectangle([(px1 + 2, py1 + 7), (px2 + 2, py2 + 7)], radius=18, fill=(8, 12, 24, 52))
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=18, fill=sub_card_bg, outline=(*pcol, 210), width=2)

        badge_r = 16
        bcx = px2 - 24
        bcy = (py1 + py2) // 2
        draw.ellipse([(bcx - badge_r, bcy - badge_r), (bcx + badge_r, bcy + badge_r)], fill=(*pcol, 38), outline=(*pcol, 220), width=2)
        if len(svgs) > pi + 1:
            sat_svg = render_recolored_svg_motion_canvas(
                svg_xml=svgs[pi + 1],
                width=badge_r * 2 - 4,
                height=badge_r * 2 - 4,
                theme_palette={"primary": pcol, "secondary": primary_c, "accent": accent_c},
                choreo_u=pu,
                global_t=global_t,
                stroke_scale=0.9
            )
            img.alpha_composite(sat_svg, (bcx - sat_svg.width // 2, bcy - sat_svg.height // 2))
            draw = ImageDraw.Draw(img, "RGBA")

        draw_contained_text_fn(draw, (px1 + 10, py1 + 8, bcx - badge_r - 8, py2 - 8), ptxt, initial_font_size=15, fill=(*txt_main, 255))

    draw_cursor_fn(draw, (dx2 - 18, dy2 + 30), (ic_cx, ic_cy), choreo_u, accent_rgb=primary_c)
    return img


# ==============================================================================
# 5.3 مدير حزم الموشن جرافيك الضخمة (400MB+ Google Drive / Direct ZIP / Folder Streamer)
# ==============================================================================
def get_custom_pack_stats() -> Dict[str, Any]:
    """إرجاع إحصائيات حزمة الموشن جرافيك المربوطة (عدد ملفات SVG, Lottie JSON, PNG/WebP, MP4/WebM)."""
    if os.path.exists(CUSTOM_PACK_INDEX_PATH):
        try:
            with open(CUSTOM_PACK_INDEX_PATH, "r", encoding="utf-8") as f:
                idx_data = json.load(f)
            if isinstance(idx_data, dict):
                return idx_data.get("stats", {"total_assets": len(idx_data.get("assets", []))})
        except Exception:
            pass
    return {"total_assets": 0, "svg_count": 0, "lottie_count": 0, "image_count": 0, "video_count": 0}


def index_custom_motion_pack_directory(target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    يمسح مجلد حزمة الموشن جرافيك (سواء كانت 400MB أو 2GB) ويبني فهرساً دلالياً خفيفاً جداً (`pack_index.json`)
    بحيث يتم استدعاء ملف واحد فقط عند الحاجة في الرندرة دون استهلاك الرام (`Zero-OOM`).
    """
    scan_dir = target_dir if (target_dir and os.path.isdir(target_dir)) else CUSTOM_PACK_DIR
    assets_list: List[Dict[str, Any]] = []
    counts = {"svg_count": 0, "lottie_count": 0, "image_count": 0, "video_count": 0}

    for root_d, _, files in os.walk(scan_dir):
        for fname in files:
            if fname == "pack_index.json":
                continue
            ext = os.path.splitext(fname)[1].lower()
            full_p = os.path.join(root_d, fname)
            rel_tags = re.findall(r"[a-zA-Z0-9\u0600-\u06FF]+", os.path.splitext(fname)[0].lower())
            folder_tags = re.findall(r"[a-zA-Z0-9\u0600-\u06FF]+", os.path.basename(root_d).lower())
            tags = list(dict.fromkeys(rel_tags + folder_tags))

            if ext == ".svg":
                counts["svg_count"] += 1
                assets_list.append({"path": full_p, "type": "svg", "tags": tags})
            elif ext == ".json":
                counts["lottie_count"] += 1
                assets_list.append({"path": full_p, "type": "lottie", "tags": tags})
            elif ext in (".png", ".webp"):
                counts["image_count"] += 1
                assets_list.append({"path": full_p, "type": "image", "tags": tags})
            elif ext in (".mp4", ".mov", ".webm"):
                counts["video_count"] += 1
                assets_list.append({"path": full_p, "type": "video", "tags": tags})

    stats = {
        "total_assets": len(assets_list),
        **counts,
        "pack_dir": scan_dir
    }
    index_payload = {"stats": stats, "assets": assets_list}
    try:
        with open(CUSTOM_PACK_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index_payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return stats


def import_motion_pack_from_url_or_path(source_url_or_path: str) -> Dict[str, Any]:
    """
    يستورد حزمة موشن جرافيك ضخمة (400MB+) مباشرة من:
    1. مسار مجلد محلي أو ملف `.zip` محلي (إذا كان المستخدم يشغل المنصة على جهازه أو رفع أرشيفاً).
    2. رابط Google Drive أو رابط تحميل مباشر (`.zip`) عبر التدفق المباشر للقرص (`Streaming Chunked Download`)
       بأجزاء 8MB دون تحميل الـ 400MB في الرام أبداً (`Zero-OOM`)!
    """
    src = str(source_url_or_path or "").strip()
    if not src:
        return {"ok": False, "message": "الرجاء إدخال رابط الحزمة أو مسار المجلد."}

    # 1. إذا كان مساراً محلياً لمجلد أو ملف ZIP
    if os.path.isdir(src):
        stats = index_custom_motion_pack_directory(src)
        return {"ok": True, "message": f"تم ربط وفهرسة مجلد حزمة الموشن جرافيك بنجاح ({stats['total_assets']} شكل/ملف).", "stats": stats}

    if os.path.isfile(src) and src.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(src, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    ext = os.path.splitext(member.filename)[1].lower()
                    if ext in (".svg", ".json", ".png", ".webp", ".mp4", ".webm", ".mov"):
                        zf.extract(member, CUSTOM_PACK_DIR)
            stats = index_custom_motion_pack_directory(CUSTOM_PACK_DIR)
            return {"ok": True, "message": f"تم استخراج وفهرسة حزمة الـ ZIP بنجاح ({stats['total_assets']} شكل/ملف).", "stats": stats}
        except Exception as e:
            return {"ok": False, "message": f"تعذر فك ضغط الأرشيف: {e}"}

    # 2. إذا كان رابط Google Drive أو رابط ZIP سحابي مباشر
    if src.startswith("http://") or src.startswith("https://"):
        dl_url = src
        m_drive = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]{20,})", src)
        if m_drive:
            file_id = m_drive.group(1)
            dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        tmp_zip = os.path.join(CUSTOM_PACK_DIR, "_streamed_pack.zip")
        try:
            session = requests.Session()
            resp = session.get(dl_url, stream=True, timeout=15)
            # معالجة صفحة تأكيد التحميل للملفات الكبيرة في Google Drive (>100MB)
            for k, v in resp.cookies.items():
                if k.startswith("download_warning"):
                    dl_url = f"{dl_url}&confirm={v}"
                    resp = session.get(dl_url, stream=True, timeout=20)
                    break

            if resp.status_code != 200:
                return {"ok": False, "message": f"تعذر الوصول للرابط (HTTP {resp.status_code}). تأكد أن الرابط عام (Anyone with the link)."}

            with open(tmp_zip, "wb") as f_out:
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        f_out.write(chunk)

            if zipfile.is_zipfile(tmp_zip):
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    for member in zf.infolist():
                        if member.is_dir():
                            continue
                        ext = os.path.splitext(member.filename)[1].lower()
                        if ext in (".svg", ".json", ".png", ".webp", ".mp4", ".webm", ".mov"):
                            zf.extract(member, CUSTOM_PACK_DIR)
                try:
                    os.remove(tmp_zip)
                except Exception:
                    pass
                stats = index_custom_motion_pack_directory(CUSTOM_PACK_DIR)
                return {"ok": True, "message": f"تم تحميل وفهرسة حزمة الموشن جرافيك السحابية بنجاح ({stats['total_assets']} شكل/ملف)!", "stats": stats}
            else:
                try:
                    os.remove(tmp_zip)
                except Exception:
                    pass
                return {"ok": False, "message": "الرابط لا يشير إلى ملف ZIP مباشر أو يحتاج صلاحية مشاركة عامة."}
        except Exception as e:
            return {"ok": False, "message": f"حدث خطأ أثناء التدفق السحابي للحزمة: {e}"}

    return {"ok": False, "message": "مسار أو رابط غير صالح."}


def load_matching_pack_svg_assets(queries: List[str], max_count: int = 3) -> List[str]:
    """يسترجع ملفات الـ SVG المطابقة للمعنى من حزمة المستخدم المفهرسة دون تحميل الحزمة في الرام."""
    if not os.path.exists(CUSTOM_PACK_INDEX_PATH):
        return []
    try:
        with open(CUSTOM_PACK_INDEX_PATH, "r", encoding="utf-8") as f:
            idx_data = json.load(f)
        assets = idx_data.get("assets", [])
        svg_assets = [a for a in assets if a.get("type") == "svg" and os.path.exists(a.get("path", ""))]
        if not svg_assets:
            return []

        q_terms = [part for q in queries for part in q.lower().split("-") if len(part) >= 2]
        scored = []
        for a in svg_assets:
            tags = a.get("tags", [])
            score = sum(2 if qt in tags else (1 if any(qt in t for t in tags) else 0) for qt in q_terms)
            scored.append((score, a["path"]))
        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[str] = []
        for sc, p in scored[:max_count]:
            with open(p, "r", encoding="utf-8", errors="ignore") as f_svg:
                results.append(f_svg.read())
        return results
    except Exception:
        return []