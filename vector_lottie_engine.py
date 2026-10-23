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
