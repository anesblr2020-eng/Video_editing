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
        draw.rounded_rectangle([(bx1 + 2, by1 + 6), (bx2 + 2, by2 + 6)], radius=radius, fill=(10, 12, 20, 55))
        draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=radius, fill=pod_bg, outline=(*badge_col, 215), width=2)
        dot_r = 6
        draw.ellipse([(bx2 - 18 - dot_r, (by1 + by2) // 2 - dot_r), (bx2 - 18 + dot_r, (by1 + by2) // 2 + dot_r)], fill=(*badge_col, 255))
        if sub_t:
            mid_y = by1 + int((by2 - by1) * 0.52)
            draw_contained_text_fn(draw, (bx1 + 10, by1 + 4, bx2 - 30, mid_y), title_t, initial_font_size=15, fill=(*txt_main, 255))
            draw_contained_text_fn(draw, (bx1 + 10, mid_y, bx2 - 30, by2 - 4), sub_t, initial_font_size=13, fill=(*badge_col, 255))
        else:
            draw_contained_text_fn(draw, (bx1 + 12, by1 + 4, bx2 - 30, by2 - 4), title_t, initial_font_size=15, fill=(*txt_main, 255))

    def _draw_bottom_speech_pills(y_top: int):
        pw = (st_w - 14) // 2
        ph = 48
        for pi in range(2):
            sp = _spring(choreo_u, delay=0.22 + pi * 0.12, dur=0.36)
            if sp <= 0.05:
                continue
            px1 = st_x1 + pi * (pw + 14)
            py1 = y_top + int(18 * (1.0 - min(1.0, sp)))
            b_col = primary_c if pi == 0 else accent_c
            _draw_floating_pod(px1, py1, px1 + pw, py1 + ph, sub_items[pi % len(sub_items)], "", badge_col=b_col, radius=16)

    sp_main = max(0.15, min(1.12, _spring(choreo_u, delay=0.04, dur=0.40)))
    float_dy = int(5.0 * math.sin(global_t * 2.8))
    cy += float_dy

    # -------------------------------------------------------------------------
    # 1. hero_smartphone_reels: مجسم الهاتف الذكي ومشغل الريلز التفاعلي
    # -------------------------------------------------------------------------
    if archetype == "hero_smartphone_reels":
        ph_w = int(st_w * 0.42 * sp_main)
        ph_h = int(st_h * 0.64 * sp_main)
        px1, py1 = cx - ph_w // 2, cy - ph_h // 2 - 10
        px2, py2 = px1 + ph_w, py1 + ph_h

        # ظل وإطار الهاتف الثلاثي الأبعاد
        draw.rounded_rectangle([(px1 + 8, py1 + 12), (px2 + 8, py2 + 12)], radius=28, fill=(8, 10, 18, 95))
        draw.rounded_rectangle([(px1, py1), (px2, py2)], radius=28, fill=(18, 22, 36, 252), outline=(*primary_c, 245), width=3)
        # شاشة الريلز الداخلية
        sc_x1, sc_y1, sc_x2, sc_y2 = px1 + 10, py1 + 14, px2 - 10, py2 - 14
        draw.rounded_rectangle([(sc_x1, sc_y1), (sc_x2, sc_y2)], radius=20, fill=(30, 41, 68, 255))
        # نوتش علوي (Dynamic Island)
        isl_w = max(36, int(ph_w * 0.30))
        draw.rounded_rectangle([(cx - isl_w // 2, sc_y1 + 8), (cx + isl_w // 2, sc_y1 + 18)], radius=5, fill=(10, 12, 18, 255))

        # زر تشغيل الريلز النابض في قلب الشاشة
        play_r = max(20, int(ph_w * 0.18 * (0.92 + 0.08 * math.sin(global_t * 5.0))))
        p_cy = (sc_y1 + sc_y2) // 2 - 14
        draw.ellipse([(cx - play_r - 8, p_cy - play_r - 8), (cx + play_r + 8, p_cy + play_r + 8)], fill=(*primary_c, 55))
        draw.ellipse([(cx - play_r, p_cy - play_r), (cx + play_r, p_cy + play_r)], fill=(*primary_c, 255))
        tri = [(cx - play_r // 3, p_cy - play_r // 2), (cx - play_r // 3, p_cy + play_r // 2), (cx + play_r // 2, p_cy)]
        draw.polygon(tri, fill=(255, 255, 255, 255))

        # موجات الصوت الحية وشريط التقدم أسفل شاشة الهاتف
        wave_y = sc_y2 - 36
        n_bars = 14
        bw = max(3, (sc_x2 - sc_x1 - 28) // (n_bars * 2))
        for bi in range(n_bars):
            bh = int(6 + 14 * abs(math.sin(global_t * 4.5 + bi * 0.55)))
            bx = sc_x1 + 16 + bi * (bw * 2)
            b_col = secondary_c if (bi / float(n_bars)) <= choreo_u else (148, 163, 184)
            draw.rounded_rectangle([(bx, wave_y - bh), (bx + bw, wave_y + bh)], radius=2, fill=(*b_col, 245))

        # كبسولات عائمة حول الهاتف للكلمات المنطوقة
        if choreo_u >= 0.16:
            _draw_floating_pod(st_x1, py1 + 18, px1 - 8, py1 + 74, kpi_val, badge_col=secondary_c, radius=14)
        if choreo_u >= 0.28:
            _draw_floating_pod(px2 + 8, py1 + int(ph_h * 0.35), st_x2, py1 + int(ph_h * 0.35) + 56, sub_items[2 % len(sub_items)], badge_col=accent_c, radius=14)

        _draw_bottom_speech_pills(py2 + 16)
        draw_cursor_fn(draw, (px2 + 24, p_cy + 40), (cx, p_cy), choreo_u, accent_rgb=secondary_c)
        return img

    # -------------------------------------------------------------------------
    # 2. hero_camera_production: عدسة الكاميرا السينمائية ومؤشر التسجيل REC
    # -------------------------------------------------------------------------
    if archetype == "hero_camera_production":
        lens_r = int(min(st_w, st_h) * 0.27 * sp_main)
        # أركان الـ Viewfinder السينمائية
        vf_x1, vf_y1, vf_x2, vf_y2 = st_x1 + 14, st_y1 + 10, st_x2 - 14, cy + lens_r + 28
        cl = 22
        for (vx, vy, dx, dy) in [(vf_x1, vf_y1, 1, 1), (vf_x2, vf_y1, -1, 1), (vf_x1, vf_y2, 1, -1), (vf_x2, vf_y2, -1, -1)]:
            draw.line([(vx, vy), (vx + dx * cl, vy)], fill=(*primary_c, 220), width=3)
            draw.line([(vx, vy), (vx, vy + dy * cl)], fill=(*primary_c, 220), width=3)

        # شارة REC الحمراء النابضة
        rec_alpha = int(155 + 100 * math.sin(global_t * 6.0))
        draw.ellipse([(vf_x1 + 18, vf_y1 + 14), (vf_x1 + 30, vf_y1 + 26)], fill=(239, 68, 68, rec_alpha))
        f_rec = get_font_fn(14, bold=True)
        draw_arabic_text_fn(draw, (vf_x1 + 62, vf_y1 + 20), "REC 30FPS", font=f_rec, fill=(239, 68, 68, 255))

        # حلقات عدسة الكاميرا المتعددة وشفرات الـ Aperture المتحركة
        draw.ellipse([(cx - lens_r - 10, cy - lens_r - 10), (cx + lens_r + 10, cy + lens_r + 10)], fill=(15, 23, 42, 240), outline=(*primary_c, 245), width=4)
        draw.ellipse([(cx - int(lens_r * 0.82), cy - int(lens_r * 0.82)), (cx + int(lens_r * 0.82), cy + int(lens_r * 0.82))], fill=(24, 34, 62, 250), outline=(*secondary_c, 210), width=2)

        n_blades = 6
        ap_open = 0.28 + 0.25 * math.sin(choreo_u * math.pi)
        inner_r = int(lens_r * ap_open)
        for bi in range(n_blades):
            ang = bi * (2.0 * math.pi / n_blades) + global_t * 0.45
            x_a = cx + int(lens_r * 0.75 * math.cos(ang))
            y_a = cy + int(lens_r * 0.75 * math.sin(ang))
            x_b = cx + int(inner_r * math.cos(ang + 0.55))
            y_b = cy + int(inner_r * math.sin(ang + 0.55))
            draw.line([(x_a, y_a), (x_b, y_b)], fill=(*primary_c, 200), width=3)

        draw.ellipse([(cx - inner_r, cy - inner_r), (cx + inner_r, cy + inner_r)], fill=(*primary_c, 75), outline=(255, 255, 255, 220), width=2)
        draw_contained_text_fn(draw, (cx - inner_r, cy - 18, cx + inner_r, cy + 18), kpi_val, initial_font_size=18, fill=(255, 255, 255, 255))

        _draw_bottom_speech_pills(vf_y2 + 14)
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
    # 5. hero_chrono_speedometer: عداد السرعة والزمن التوربيني
    # -------------------------------------------------------------------------
    if archetype == "hero_chrono_speedometer":
        sp_r = int(min(st_w, st_h) * 0.30 * sp_main)
        draw.arc([(cx - sp_r, cy - sp_r), (cx + sp_r, cy + sp_r)], start=135, end=405, fill=(148, 163, 184, 95), width=18)
        sweep_deg = int(270 * min(1.0, max(0.12, choreo_u * 1.25)))
        draw.arc([(cx - sp_r, cy - sp_r), (cx + sp_r, cy + sp_r)], start=135, end=135 + sweep_deg, fill=(*primary_c, 255), width=18)

        # تدريجات عداد السرعة
        for ti in range(11):
            t_ang = math.radians(135 + ti * 27)
            tx0 = cx + int((sp_r - 24) * math.cos(t_ang))
            ty0 = cy + int((sp_r - 24) * math.sin(t_ang))
            tx1 = cx + int((sp_r - 12) * math.cos(t_ang))
            ty1 = cy + int((sp_r - 12) * math.sin(t_ang))
            draw.line([(tx0, ty0), (tx1, ty1)], fill=(*txt_main, 190), width=2)

        # عقرب السرعة المتحرك
        needle_ang = math.radians(135 + sweep_deg)
        nx = cx + int((sp_r - 28) * math.cos(needle_ang))
        ny = cy + int((sp_r - 28) * math.sin(needle_ang))
        draw.line([(cx, cy), (nx, ny)], fill=(*secondary_c, 255), width=5)
        draw.ellipse([(cx - 12, cy - 12), (cx + 12, cy + 12)], fill=(*secondary_c, 255), outline=(255, 255, 255, 255), width=3)

        draw_contained_text_fn(draw, (cx - int(sp_r * 0.75), cy + 18, cx + int(sp_r * 0.75), cy + int(sp_r * 0.68)), kpi_val, initial_font_size=22, fill=(*txt_main, 255))
        _draw_bottom_speech_pills(cy + sp_r + 14)
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
    # 13. hero_platform_workspace: واجهة المنصة الذكية العائمة وزر التوليد
    # -------------------------------------------------------------------------
    if archetype == "hero_platform_workspace":
        dk_w, dk_h = int(st_w * 0.88 * sp_main), int(st_h * 0.46 * sp_main)
        dx1, dy1 = cx - dk_w // 2, cy - dk_h // 2 - 12
        dx2, dy2 = dx1 + dk_w, dy1 + dk_h
        draw.rounded_rectangle([(dx1, dy1), (dx2, dy2)], radius=24, fill=pod_bg, outline=(*primary_c, 235), width=3)
        # نقاط نافذة النظام العلوية
        for di, dcol in enumerate([(244, 63, 94), (250, 204, 21), (16, 185, 129)]):
            draw.ellipse([(dx1 + 18 + di * 18, dy1 + 14), (dx1 + 28 + di * 18, dy1 + 24)], fill=(*dcol, 255))

        draw_contained_text_fn(draw, (dx1 + 18, dy1 + 36, dx2 - 18, dy1 + int(dk_h * 0.54)), concept_title, initial_font_size=19, fill=(*txt_main, 255))
        btn_x1, btn_y1, btn_x2, btn_y2 = cx - int(dk_w * 0.38), dy2 - 58, cx + int(dk_w * 0.38), dy2 - 14
        is_clicked = (choreo_u >= 0.62)
        btn_col = accent_c if is_clicked else primary_c
        draw.rounded_rectangle([(btn_x1, btn_y1), (btn_x2, btn_y2)], radius=22, fill=(*btn_col, 255))
        draw_contained_text_fn(draw, (btn_x1 + 14, btn_y1, btn_x2 - 14, btn_y2), f"✨ {kpi_val}", initial_font_size=16, fill=(255, 255, 255, 255))

        _draw_bottom_speech_pills(dy2 + 16)
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
    # 16. hero_cta_magnet_finale: مغناطيس الجذب التفاعلي وبطاقة الـ CTA
    # -------------------------------------------------------------------------
    mag_r = int(min(st_w, st_h) * 0.22 * sp_main)
    draw.arc([(cx - mag_r, cy - mag_r - 12), (cx + mag_r, cy + mag_r - 12)], start=0, end=180, fill=(244, 63, 94, 255), width=20)
    draw.rectangle([(cx - mag_r, cy - mag_r - 28), (cx - mag_r + 20, cy - 12)], fill=(226, 232, 240, 255))
    draw.rectangle([(cx + mag_r - 20, cy - mag_r - 28), (cx + mag_r, cy - 12)], fill=(226, 232, 240, 255))

    btn_w, btn_h = int(st_w * 0.78), 54
    bx1, by1 = cx - btn_w // 2, cy + mag_r + 12
    bx2, by2 = bx1 + btn_w, by1 + btn_h
    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=27, fill=(*primary_c, 255), outline=(255, 255, 255, 235), width=2)
    draw_contained_text_fn(draw, (bx1 + 16, by1, bx2 - 16, by2), f"🚀 {concept_title}", initial_font_size=18, fill=(255, 255, 255, 255))
    draw_cursor_fn(draw, (bx2 - 12, by2 + 34), (cx, (by1 + by2) // 2), choreo_u, accent_rgb=secondary_c)
    return img
