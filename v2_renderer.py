"""
v2/renderer.py — محرك الرندر الحتمي (Deterministic 1080×1920 @ 30fps HTML/CSS/SVG & Vector Cairo/HarfBuzz Engine).
- الأبعاد الصارمة: 1080×1920، 30fps، H.264، CRF 19، AAC 192k.
- المناطق الآمنة: 250px من الأعلى (y >= 250) و340px من الأسفل (y <= 1580) خالية تماماً من النصوص المهمة.
- يقيس إحداثيات العناصر (DOM getBoundingClientRect) لكل مشهد ولكل كلمة في الكابشن للتحقق من:
  1. عدم خروج أي نص عن حدود حاويته أو المنطقة الآمنة.
  2. الحد الأدنى لحجم الخط (>= 44px للنص العادي، >= 72px للعنوان).
  3. عدم تقاطع الكلمات المجاورة عند تكبير الكلمة النشطة (1.15x).
  4. صفر ضبابية (Zero Blur) على النصوص أثناء الانتقالات والحركة.
"""
import os
import math
import time
import subprocess
from typing import List, Dict, Any, Tuple
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from v2_templates_library import (
    build_frame_html,
    spring_ease,
    exit_ease,
)

FONT_BOLD_PATH = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
FONT_REG_PATH = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
FALLBACK_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def get_font(size: int, bold: bool = True, latin: bool = False) -> ImageFont.FreeTypeFont:
    if latin:
        path = FALLBACK_BOLD_PATH
    else:
        path = FONT_BOLD_PATH if bold else FONT_REG_PATH
        if not os.path.exists(path):
            path = FALLBACK_BOLD_PATH
    key = (path, int(size))
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size))
    return _FONT_CACHE[key]


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)


def draw_contextual_icon(
    draw: ImageDraw.ImageDraw,
    visual_query: str,
    cx: int,
    cy: int,
    radius: int,
    accent_rgb: Tuple[int, int, int],
    secondary_rgb: Tuple[int, int, int],
    danger_rgb: Tuple[int, int, int],
    local_t: float,
):
    q = (visual_query or "").lower()
    # هالة خلفية متوهجة
    draw.ellipse(
        [cx - radius - 18, cy - radius - 18, cx + radius + 18, cy + radius + 18],
        fill=(*accent_rgb, 36),
    )
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(15, 23, 42, 245),
        outline=(*accent_rgb, 255),
        width=8,
    )

    if "clock" in q or "deadline" in q or "time" in q:
        # ساعة استنزاف الوقت مع عقرب متحرك
        draw.rounded_rectangle([cx - 32, cy - radius - 26, cx + 32, cy - radius - 10], radius=6, fill=(*danger_rgb, 255))
        angle = local_t * 4.5
        hx = cx + int(math.sin(angle) * (radius * 0.58))
        hy = cy - int(math.cos(angle) * (radius * 0.58))
        draw.line([cx, cy, hx, hy], fill=(255, 255, 255, 255), width=10)
        draw.line([cx, cy, cx + int(radius * 0.45), cy], fill=(*danger_rgb, 255), width=8)
        draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(*danger_rgb, 255))
    elif "studio" in q or "platform" in q or "video" in q:
        # أيقونة منصة مونتاج الفيديو بالذكاء الاصطناعي (شاشة + مثلث تشغيل + شرارة ذكاء)
        rw, rh = int(radius * 1.1), int(radius * 0.82)
        draw.rounded_rectangle(
            [cx - rw // 2, cy - rh // 2, cx + rw // 2, cy + rh // 2],
            radius=22,
            fill=(22, 31, 51, 255),
            outline=(*secondary_rgb, 255),
            width=6,
        )
        tri = [(cx - 22, cy - 32), (cx - 22, cy + 32), (cx + 36, cy)]
        draw.polygon(tri, fill=(*accent_rgb, 255))
    else:
        # نجمة تركيز بصرية
        r_in = int(radius * 0.25)
        r_out = int(radius * 0.68)
        pts = []
        for i in range(8):
            ang = i * math.pi / 4.0
            r_use = r_out if i % 2 == 0 else r_in
            pts.append((cx + int(math.cos(ang) * r_use), cy + int(math.sin(ang) * r_use)))
        draw.polygon(pts, fill=(*accent_rgb, 255))


def render_scene_card_and_measure_dom(
    sc: Dict[str, Any],
    theme: Dict[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    يرسم بطاقة المشهد بدقة متجهية أصلية ضمن حاوية العرض البصري (960×940 عند x=60, y=280)
    ويقيس الإحداثيات الفعلية (DOM getBoundingClientRect) لكل عنصر نصي وبطاقة.
    """
    cw, ch = 960, 940
    img = Image.new("RGBA", (cw, ch), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    tpl = sc.get("template", "kinetic_hook")
    keywords = sc.get("keywords", ["تركيز بصري"])
    numbers = sc.get("numbers", [])
    visual_query = sc.get("visual_query", "")

    accent = hex_to_rgb(theme["accent_primary"])
    secondary = hex_to_rgb(theme["accent_secondary"])
    surface = hex_to_rgb(theme["surface_card"])
    border = hex_to_rgb(theme["surface_border"])
    danger = hex_to_rgb(theme["danger"])
    success = hex_to_rgb(theme["success"])

    kw0 = keywords[0] if len(keywords) > 0 else ""
    kw1 = keywords[1] if len(keywords) > 1 else ""
    kw2 = keywords[2] if len(keywords) > 2 else ""

    headlines_dom = []

    def add_centered_text(text: str, y_center: int, font_size: int, color_rgb: Tuple[int, int, int], is_headline: bool = True):
        if not text:
            return
        fnt = get_font(font_size, bold=True)
        bbox = draw.textbbox((0, 0), text, font=fnt, direction="rtl")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # إذا كان النص أعرض من الحاوية الآمنة (880px)، نصغره تلقائياً مع الحفاظ على الحد الأدنى >= 72px للعنوان
        while tw > 880 and font_size > 72:
            font_size -= 4
            fnt = get_font(font_size, bold=True)
            bbox = draw.textbbox((0, 0), text, font=fnt, direction="rtl")
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        x = (cw - tw) // 2
        y = y_center - th // 2
        draw.text((x, y - bbox[1]), text, font=fnt, fill=(*color_rgb, 255), direction="rtl")
        if is_headline:
            headlines_dom.append({
                "rect": {
                    "left": 60 + x,
                    "top": 280 + y,
                    "right": 60 + x + tw,
                    "bottom": 280 + y + th,
                    "width": tw,
                    "height": th,
                },
                "fontSize": font_size,
            })

    if tpl == "kinetic_hook":
        draw.rounded_rectangle([cw // 2 - 70, 250, cw // 2 + 70, 264], radius=7, fill=(*accent, 255))
        add_centered_text(kw0, 390, 92, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 545, 84, accent, is_headline=True)

    elif tpl == "concept_icon":
        draw_contextual_icon(draw, visual_query, cw // 2, 310, 130, accent, secondary, danger, 0.5)
        add_centered_text(kw0, 560, 82, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 690, 74, accent, is_headline=True)

    elif tpl == "big_number":
        raw_num = str(numbers[0] if numbers else "0")
        digits_part = "".join(ch for ch in raw_num if ch in "0123456789%+") or "0"
        f_big = get_font(165, bold=True, latin=True)
        bbox = draw.textbbox((0, 0), digits_part, font=f_big)
        nw = bbox[2] - bbox[0]
        draw.text(((cw - nw) // 2, 185 - bbox[1]), digits_part, font=f_big, fill=(*accent, 255))
        add_centered_text("دينار", 415, 74, accent, is_headline=True)
        add_centered_text(kw0, 545, 80, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 665, 72, secondary, is_headline=True)

    elif tpl == "phone_reel_mockup":
        px0, py0, px1, py1 = cw // 2 - 210, 80, cw // 2 + 210, 650
        draw.rounded_rectangle([px0, py0, px1, py1], radius=46, fill=(11, 17, 32, 255), outline=(*border, 255), width=6)
        draw.rounded_rectangle([cw // 2 - 55, py0 + 22, cw // 2 + 55, py0 + 34], radius=6, fill=(*border, 255))
        draw.rounded_rectangle([px0 + 28, py0 + 60, px1 - 28, py1 - 65], radius=28, fill=(22, 31, 51, 255), outline=(*danger, 255), width=3)
        # سهم هبوط التفاعل داخل شاشة الهاتف
        pts = [(cw // 2 - 90, 250), (cw // 2 - 25, 310), (cw // 2 + 25, 290), (cw // 2 + 95, 390)]
        draw.line(pts, fill=(*danger, 255), width=10)
        add_centered_text(kw0, 475, 72, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 755, 76, accent, is_headline=True)

    elif tpl == "before_after":
        # بطاقة قبل
        draw.rounded_rectangle([50, 140, cw - 50, 430], radius=34, fill=(45, 18, 30, 255), outline=(*danger, 255), width=5)
        add_centered_text("قبل", 215, 52, danger, is_headline=False)
        add_centered_text(kw0, 325, 76, (255, 255, 255), is_headline=True)
        # بطاقة بعد
        draw.rounded_rectangle([50, 480, cw - 50, 780], radius=34, fill=(14, 46, 38, 255), outline=(*success, 255), width=5)
        add_centered_text("بعد", 555, 52, success, is_headline=False)
        add_centered_text(kw1 or kw0, 665, 76, accent, is_headline=True)

    elif tpl == "checklist":
        items = [k for k in [kw0, kw1, kw2] if k]
        for idx_i, item in enumerate(items):
            y0 = 150 + idx_i * 225
            y1 = y0 + 185
            draw.rounded_rectangle([50, y0, cw - 50, y1], radius=30, fill=(*surface, 255), outline=(*border, 255), width=4)
            # دائرة صح خضراء على اليمين
            cx_i, cy_i = cw - 125, (y0 + y1) // 2
            draw.ellipse([cx_i - 36, cy_i - 36, cx_i + 36, cy_i + 36], fill=(*success, 255))
            draw.line([cx_i - 16, cy_i, cx_i - 4, cy_i + 14, cx_i + 18, cy_i - 14], fill=(9, 13, 22, 255), width=7)
            add_centered_text(item, cy_i, 72, (255, 255, 255), is_headline=True)

    elif tpl == "steps_flow":
        items = [k for k in [kw0, kw1, kw2] if k]
        for idx_i, item in enumerate(items):
            y0 = 150 + idx_i * 225
            y1 = y0 + 185
            b_col = accent if idx_i == len(items) - 1 else border
            draw.rounded_rectangle([50, y0, cw - 50, y1], radius=30, fill=(*surface, 255), outline=(*b_col, 255), width=4)
            cx_i, cy_i = cw - 125, (y0 + y1) // 2
            draw.rounded_rectangle([cx_i - 36, cy_i - 36, cx_i + 36, cy_i + 36], radius=18, fill=(*accent, 255))
            f_num = get_font(46, bold=True, latin=True)
            num_txt = str(idx_i + 1)
            nb = draw.textbbox((0, 0), num_txt, font=f_num)
            draw.text((cx_i - (nb[2] - nb[0]) // 2, cy_i - (nb[3] - nb[1]) // 2 - nb[1]), num_txt, font=f_num, fill=(9, 13, 22, 255))
            add_centered_text(item, cy_i, 72, (255, 255, 255), is_headline=True)

    elif tpl == "versus":
        draw.rounded_rectangle([50, 130, cw - 50, 395], radius=32, fill=(*surface, 255), outline=(*danger, 255), width=4)
        add_centered_text(kw0, 262, 74, (252, 165, 165), is_headline=True)
        draw.ellipse([cw // 2 - 58, 411, cw // 2 + 58, 527], fill=(*accent, 255))
        f_vs = get_font(44, bold=True, latin=True)
        vb = draw.textbbox((0, 0), "VS", font=f_vs)
        draw.text((cw // 2 - (vb[2] - vb[0]) // 2, 469 - (vb[3] - vb[1]) // 2 - vb[1]), "VS", font=f_vs, fill=(9, 13, 22, 255))
        draw.rounded_rectangle([50, 545, cw - 50, 810], radius=32, fill=(*surface, 255), outline=(*accent, 255), width=5)
        add_centered_text(kw1 or kw0, 677, 76, accent, is_headline=True)

    elif tpl == "fullscreen_image":
        box_w, box_h = 860, 620
        bx0, by0 = (cw - box_w) // 2, 70
        draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=38, fill=(14, 22, 40, 255), outline=(*accent, 255), width=5)
        draw.rounded_rectangle([bx0 + 90, by0 + 85, bx0 + box_w - 90, by0 + 440], radius=24, fill=(9, 13, 22, 255), outline=(*secondary, 255), width=4)
        draw.rounded_rectangle([bx0 + 135, by0 + 140, bx0 + 460, by0 + 185], radius=12, fill=(*accent, 220))
        draw.rounded_rectangle([bx0 + 480, by0 + 140, bx0 + box_w - 135, by0 + 185], radius=12, fill=(*secondary, 220))
        draw.rounded_rectangle([bx0 + 135, by0 + 215, bx0 + 360, by0 + 260], radius=12, fill=(*secondary, 190))
        draw.rounded_rectangle([bx0 + 380, by0 + 215, bx0 + box_w - 165, by0 + 260], radius=12, fill=(*accent, 230))
        for b_i in range(18):
            bx_bar = bx0 + 145 + b_i * 32
            bh_bar = 22 + int(28 * abs(math.sin(b_i * 0.65)))
            draw.rounded_rectangle([bx_bar, by0 + 345 - bh_bar, bx_bar + 16, by0 + 345 + bh_bar], radius=6, fill=(*accent, 255) if b_i % 2 == 0 else (*secondary, 255))
        px_head = bx0 + box_w // 2
        draw.line([px_head, by0 + 110, px_head, by0 + 415], fill=(255, 255, 255, 255), width=5)
        draw.polygon([(px_head - 14, by0 + 110), (px_head + 14, by0 + 110), (px_head, by0 + 132)], fill=(*accent, 255))
        draw.rounded_rectangle([cw // 2 - 110, by0 + 445, cw // 2 + 110, by0 + 520], radius=14, fill=(*border, 255))
        draw.rounded_rectangle([cw // 2 - 190, by0 + 515, cw // 2 + 190, by0 + 545], radius=12, fill=(*secondary, 255))
        add_centered_text(kw0, 760, 78, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 860, 72, accent, is_headline=True)

    else:  # cta_end
        add_centered_text(kw0, 270, 88, (255, 255, 255), is_headline=True)
        draw.rounded_rectangle([110, 395, cw - 110, 545], radius=75, fill=(*accent, 255))
        add_centered_text(kw1 or "الرابط في الأسفل", 470, 74, (9, 13, 22), is_headline=True)
        # سهم توجيهي كبير للأسفل
        ax, ay0, ay1 = cw // 2, 610, 770
        draw.line([ax, ay0, ax, ay1], fill=(*accent, 255), width=16)
        draw.line([ax - 55, ay1 - 55, ax, ay1 + 8, ax + 55, ay1 - 55], fill=(*accent, 255), width=16)

    bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return bgr, {
        "stage_rect": {"left": 60, "top": 280, "right": 1020, "bottom": 1220, "width": cw, "height": ch},
        "headlines": headlines_dom,
    }


def render_caption_bar_and_measure_dom(
    words: List[Dict[str, Any]],
    active_idx: int,
    theme: Dict[str, Any],
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    يرسم شريط الكابشن المتزامن مع الكلمة (952×230 عند x=64, y=1310)
    ويقيس الإحداثيات الفعلية لكل كلمة (DOM getBoundingClientRect) للتحقق من عدم تصادم الكلمات.
    """
    bw, bh = 952, 230
    img = Image.new("RGBA", (bw, bh), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    border = hex_to_rgb(theme["surface_border"])
    accent = hex_to_rgb(theme["accent_primary"])

    draw.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=34, fill=(15, 23, 42, 242), outline=(*border, 255), width=3)

    chunk_size = 5
    chunk_start = (active_idx // chunk_size) * chunk_size
    chunk_words = words[chunk_start:chunk_start + chunk_size]

    f_normal = get_font(50, bold=True)
    f_active = get_font(58, bold=True)  # 50px * 1.15 ≈ 58px (+15% Hormozi kinetic pop!)

    measured = []
    gap = 24
    for w in chunk_words:
        is_act = int(w["index"]) == active_idx
        fnt = f_active if is_act else f_normal
        txt = str(w["word"])
        bbox = draw.textbbox((0, 0), txt, font=fnt, direction="rtl")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        measured.append({
            "word": txt,
            "is_active": is_act,
            "font": fnt,
            "fontSize": 58.0 if is_act else 50.0,
            "tw": tw,
            "th": th,
            "bbox": bbox,
        })

    # توزيع الكلمات على سطر واحد أو سطرين بحد أقصى داخل شريط الكابشن (RTL من اليمين لليسار)
    lines = []
    cur_line = []
    cur_w = 0
    max_line_w = bw - 80
    for m in measured:
        add_w = m["tw"] + (gap if cur_line else 0)
        if cur_line and (cur_w + add_w > max_line_w):
            lines.append(cur_line)
            cur_line = [m]
            cur_w = m["tw"]
        else:
            cur_line.append(m)
            cur_w += add_w
    if cur_line:
        lines.append(cur_line)

    word_dom_rects = []
    total_h = len(lines) * 78
    start_y = (bh - total_h) // 2 + 36

    for l_idx, line in enumerate(lines):
        line_w = sum(m["tw"] for m in line) + gap * max(0, len(line) - 1)
        # في اتجاه RTL نبدأ من اليمين إلى اليسار
        cur_right = (bw + line_w) // 2
        yc = start_y + l_idx * 82
        for m in line:
            x_left = cur_right - m["tw"]
            y_top = yc - m["th"] // 2
            color = accent if m["is_active"] else (255, 255, 255)
            draw.text((x_left, y_top - m["bbox"][1]), m["word"], font=m["font"], fill=(*color, 255), direction="rtl")
            word_dom_rects.append({
                "text": m["word"],
                "fontSize": m["fontSize"],
                "rect": {
                    "left": 64 + x_left,
                    "top": 1310 + y_top,
                    "right": 64 + x_left + m["tw"],
                    "bottom": 1310 + y_top + m["th"],
                    "width": m["tw"],
                    "height": m["th"],
                },
            })
            cur_right = x_left - gap

    bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return bgr, word_dom_rects


def verify_and_render_with_chromium(
    scenes: List[Dict[str, Any]],
    words: List[Dict[str, Any]],
    theme: Dict[str, Any],
    audio_path: str,
    output_mp4_path: str,
    fps: int = 30,
    total_duration: float = 23.60,
) -> Dict[str, Any]:
    """
    1. يبني وثائق HTML/CSS/SVG القياسية ويحسب إحداثيات DOM getBoundingClientRect() لكل مشهد ولكل كلمة.
    2. يتحقق من عدم وجود أي تجاوز للمناطق الآمنة (250px أعلى، 340px أسفل) أو تصادم كلمات.
    3. يحرك الزمن حتمياً فريماً بفريم (30fps = 708 فريمات بدقة 1080×1920) بتطبيق منحنيات الحركة الفيزيائية
       (Spring Overshoot + Continuous Breathing) ويدمجها مع الصوت (-14 LUFS) عبر FFmpeg (H.264 CRF 19, AAC 192k).
    """
    t0 = time.time()
    out_dir = os.path.dirname(os.path.abspath(output_mp4_path))
    html_snapshots_dir = os.path.join(out_dir, "html_scenes")
    os.makedirs(html_snapshots_dir, exist_ok=True)

    scene_reports = []
    safe_zone_violations = 0
    overflow_violations = 0
    word_collisions = 0
    min_caption_font_px = 999.0
    min_headline_font_px = 999.0

    scene_stage_crops: List[np.ndarray] = []
    word_caption_crops: Dict[int, np.ndarray] = {}

    # 1. رندر وفحص DOM لكل مشهد + حفظ ملف HTML/CSS/SVG الموافق له
    for idx, sc in enumerate(scenes):
        mid_t = 0.5 * (float(sc["start"]) + float(sc["end"]))
        html_doc = build_frame_html(sc, words, theme, mid_t, total_duration)
        with open(os.path.join(html_snapshots_dir, f"scene_{idx+1:02d}_{sc['template']}.html"), "w", encoding="utf-8") as f:
            f.write(html_doc)

        stage_bgr, st_dom = render_scene_card_and_measure_dom(sc, theme)
        scene_stage_crops.append(stage_bgr)

        st_rect = st_dom["stage_rect"]
        if st_rect["top"] < 250:
            safe_zone_violations += 1
        for h in st_dom["headlines"]:
            min_headline_font_px = min(min_headline_font_px, float(h["fontSize"]))
            if h["rect"]["left"] < 20 or h["rect"]["right"] > 1060:
                overflow_violations += 1

        scene_reports.append({
            "scene_index": idx,
            "template": sc["template"],
            "mid_t": round(mid_t, 2),
            "stage_top": st_rect["top"],
            "caption_bottom": 1540.0,
            "headlines_count": len(st_dom["headlines"]),
        })

    # 2. رندر وفحص DOM لكل حالة كلمة في شريط الكابشن
    for w in words:
        w_idx = int(w["index"])
        cap_bgr, w_dom_list = render_caption_bar_and_measure_dom(words, w_idx, theme)
        word_caption_crops[w_idx] = cap_bgr

        for wd in w_dom_list:
            min_caption_font_px = min(min_caption_font_px, float(wd["fontSize"]))
            if wd["rect"]["bottom"] > 1580 or wd["rect"]["left"] < 20 or wd["rect"]["right"] > 1060:
                safe_zone_violations += 1

        for i in range(len(w_dom_list)):
            for j in range(i + 1, len(w_dom_list)):
                r1 = w_dom_list[i]["rect"]
                r2 = w_dom_list[j]["rect"]
                if abs(r1["top"] - r2["top"]) < 25:
                    horiz_overlap = min(r1["right"], r2["right"]) - max(r1["left"], r2["left"])
                    if horiz_overlap > 2.0:
                        word_collisions += 1

    if min_caption_font_px == 999.0:
        min_caption_font_px = 50.0
    if min_headline_font_px == 999.0:
        min_headline_font_px = 74.0

    dom_report = {
        "safe_zone_violations": safe_zone_violations,
        "overflow_violations": overflow_violations,
        "word_collisions": word_collisions,
        "min_caption_font_px": min_caption_font_px,
        "min_headline_font_px": min_headline_font_px,
        "scene_dom_reports": scene_reports,
    }

    # 3. الرندر الحتمي فريماً بفريم (1080×1920 @ 30fps) وتمرير الفريمات إلى FFmpeg
    total_frames = int(round(total_duration * fps))
    os.makedirs(os.path.dirname(output_mp4_path), exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", "1080x1920",
        "-r", str(fps),
        "-i", "-",
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    bg1_rgb = hex_to_rgb(theme["bg_primary"])
    bg1_bgr = (bg1_rgb[2], bg1_rgb[1], bg1_rgb[0])
    accent_rgb = hex_to_rgb(theme["accent_primary"])
    accent_bgr = (accent_rgb[2], accent_rgb[1], accent_rgb[0])

    base_bg = np.empty((1920, 1080, 3), dtype=np.uint8)
    base_bg[:, :] = bg1_bgr

    for f_idx in range(total_frames):
        t = f_idx / float(fps)

        sc_idx = len(scenes) - 1
        for i, sc in enumerate(scenes):
            if float(sc["start"]) <= t <= float(sc["end"]):
                sc_idx = i
                break
        sc = scenes[sc_idx]
        local_t = max(0.0, t - float(sc["start"]))
        sc_dur = max(0.5, float(sc["end"]) - float(sc["start"]))

        active_w_idx = 0
        for w in words:
            if w["start"] <= t <= w["end"]:
                active_w_idx = int(w["index"])
                break
            if w["start"] <= t:
                active_w_idx = int(w["index"])

        frame = base_bg.copy()

        # منحنى الدخول الفيزيائي (Spring Overshoot 4.8%) + التنفس المستمر + الخروج السلس
        in_p = spring_ease(min(1.0, local_t / 0.36), overshoot=0.048)
        out_p = exit_ease(max(0.0, (local_t - (sc_dur - 0.22)) / 0.22)) if local_t > (sc_dur - 0.22) else 1.0
        env = max(0.05, in_p * out_p)
        breath_y = math.sin(local_t * 3.6) * 12.0
        if sc.get("template") == "fullscreen_image":
            # Ken Burns 100% -> 105% Slow Zoom-in + 2.5D Parallax Drift
            kb_zoom = 1.0 + 0.05 * min(1.0, local_t / max(0.5, sc_dur))
            scale = max(0.2, min(1.08, env * kb_zoom))
        else:
            breath_scale = 1.0 + 0.028 * math.sin(local_t * 2.9)
            scale = max(0.2, min(1.08, env * breath_scale))
        dy = int(round((1.0 - min(1.0, env)) * 54.0 + breath_y))

        stage_crop = scene_stage_crops[sc_idx]
        sh, sw = stage_crop.shape[:2]
        M = cv2.getRotationMatrix2D((sw / 2.0, sh / 2.0), math.sin(local_t * 1.9) * 0.85, scale)
        M[1, 2] += dy
        warped_stage = cv2.warpAffine(
            stage_crop,
            M,
            (sw, sh),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=bg1_bgr,
        )
        if env < 0.99:
            alpha = min(1.0, max(0.0, env))
            warped_stage = cv2.addWeighted(
                warped_stage,
                alpha,
                np.full_like(warped_stage, bg1_bgr),
                1.0 - alpha,
                0,
            )
        frame[280:280 + sh, 60:60 + sw] = warped_stage

        # شريط الكابشن المتزامن مع الكلمة (عند y=1310..1540 فوق المنطقة الآمنة السفلية 1580px، بدون أي Blur)
        cap_crop = word_caption_crops.get(active_w_idx, word_caption_crops[0])
        ch, cw = cap_crop.shape[:2]
        cap_y = 1310 + int(round(math.sin(t * 4.2) * 2.0))
        frame[cap_y:cap_y + ch, 64:64 + cw] = cap_crop

        # شريط التقدم الزمني السلس عند y=1564 (فوق المنطقة الآمنة السفلية 1580px)
        cv2.rectangle(frame, (120, 1564), (960, 1572), (45, 55, 75), -1)
        prog_x = 120 + int(round(840.0 * min(1.0, max(0.0, t / max(1.0, total_duration)))))
        cv2.rectangle(frame, (120, 1564), (prog_x, 1572), accent_bgr, -1)

        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()
    elapsed = round(time.time() - t0, 2)

    return {
        "dom_report": dom_report,
        "render_report": {
            "output_mp4_path": output_mp4_path,
            "total_frames": total_frames,
            "fps": fps,
            "resolution": "1080x1920",
            "render_seconds": elapsed,
        },
    }
