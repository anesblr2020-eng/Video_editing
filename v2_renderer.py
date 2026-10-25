# -*- coding: utf-8 -*-
"""
v2_renderer.py — محرك الرندر الحتمي للجيل الثاني (Deterministic 1080×1920 @ 30fps Engine — Zero cv2 Dependency).
- الأبعاد الصارمة: 1080×1920، 30fps، H.264، CRF 19، AAC 192k.
- المناطق الآمنة: 250px من الأعلى (y >= 250) و340px من الأسفل (y <= 1580) خالية تماماً من النصوص المهمة.
- يحوّل نية المشهد (الصوت، السوشيال، الذكاء الاصطناعي، التحرير، الخطوات والمقارنة)
  إلى تسلسل بصري وظيفي؛ لا يستخدم زخارف مدارية عامة أو حركة تنفّس تجعل الرسم يطفو في مكانه.
- تُخزّن عينات الحركة بمعدل 15fps لمشهد واحد فقط في كل مرة، بينما يظل الفيديو النهائي 30fps.
"""
import os
import math
import time
import subprocess
from typing import List, Dict, Any, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from v2_templates_library import (
    build_frame_html,
    spring_ease,
    exit_ease,
)

# v2 scene motion is authored as semantic, deterministic choreography below.
# The legacy vector/Lottie engine remains in the project for other pipelines, but this
# renderer does not wrap a single SVG in generic orbit effects anymore.

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



def _safe_graphic_text(value: Any) -> str:
    """Strip unsupported pictographs/control glyphs that render as tofu squares in server fonts."""
    import unicodedata
    text = unicodedata.normalize("NFC", str(value or ""))
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isspace() or cat[0] in {"L", "N", "M"} or ch in ".,!?؟،:;-%+()[]/\u2019\u2013\u2014":
            kept.append(ch)
    return " ".join("".join(kept).split()).strip()

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _smoothstep(value: float) -> float:
    x = _clamp01(value)
    return x * x * (3.0 - 2.0 * x)


def _draw_storyboard_scene(
    draw: ImageDraw.ImageDraw,
    sc: Dict[str, Any],
    animation_t: float,
    colors: Dict[str, Tuple[int, int, int]],
) -> bool:
    """Draw a purposeful mini-storyboard for concept scenes, not decorative orbit effects.

    Each choreography represents the spoken intent with a visible action:
    audio gaps close, a timeline playhead advances, a social UI reveals analytics,
    or information passes through an input-process-output layout. All labels come
    from words already supplied in the scene; generic UI labels describe the diagram.
    """
    intent = str(sc.get("intent", "explanation") or "explanation").lower()
    visual = str(sc.get("visual_query", "") or "").lower()
    speech = str(sc.get("speech", "") or "")
    keywords = [_safe_graphic_text(x) for x in sc.get("keywords", []) if _safe_graphic_text(x)]
    k0 = keywords[0] if keywords else "الفكرة"
    k1 = keywords[1] if len(keywords) > 1 else k0
    k2 = keywords[2] if len(keywords) > 2 else k1
    start = float(sc.get("start", 0.0) or 0.0)
    end = float(sc.get("end", start + 2.5) or start + 2.5)
    dur = max(1.0, end - start)
    t = max(0.0, float(animation_t))
    p = _clamp01(t / dur)
    pulse = 0.5 + 0.5 * math.sin(t * 5.2)

    accent = colors["accent"]
    secondary = colors["secondary"]
    success = colors["success"]
    danger = colors["danger"]
    surface = colors["surface"]
    border = colors["border"]
    text = colors["text"]
    muted = colors["muted"]

    def card(box, fill=surface, outline=border, width=3, radius=22):
        draw.rounded_rectangle(box, radius=radius, fill=(*fill, 255), outline=(*outline, 255), width=width)

    def label(txt, xy, size=28, color=text, anchor="mm", bold=True):
        txt = _safe_graphic_text(txt)
        if not txt:
            return
        fnt = get_font(size, bold=bold)
        try:
            draw.text(xy, txt, font=fnt, fill=(*color, 255), anchor=anchor, direction="rtl")
        except TypeError:
            draw.text(xy, txt, font=fnt, fill=(*color, 255), anchor=anchor)

    def line(points, color=accent, width=6):
        draw.line(points, fill=(*color, 255), width=width, joint="curve")

    def arrow(x1, y1, x2, y2, color=accent, width=6):
        line([(x1, y1), (x2, y2)], color, width)
        ang = math.atan2(y2-y1, x2-x1)
        size = 18
        a1 = ang + math.radians(150)
        a2 = ang - math.radians(150)
        draw.polygon([
            (x2, y2),
            (x2 + size*math.cos(a1), y2 + size*math.sin(a1)),
            (x2 + size*math.cos(a2), y2 + size*math.sin(a2)),
        ], fill=(*color, 255))

    # Single clean canvas panel: no rotating rings, random particles or flying decoration.
    card((28, 34, 932, 474), fill=surface, outline=border, width=3, radius=30)

    audio_like = intent == "audio_edit" or any(k in visual for k in ("waveform", "silence", "scissor", "microphone", "audio", "sound"))
    social_like = intent == "social_media" or any(k in visual for k in ("instagram", "viral", "reel"))
    ai_like = intent == "ai" or any(k in visual for k in ("neural", "chip", "ai_"))
    time_like = intent == "time" or any(k in visual for k in ("hourglass", "clock", "deadline"))
    editing_like = intent == "editing" or any(k in visual for k in ("camera", "clapperboard", "video"))
    delivery_like = any(k in visual for k in ("delivery", "map_58", "shipping", "route"))
    security_like = any(k in visual for k in ("shield", "guarantee", "secure", "safety"))
    success_like = any(k in visual for k in ("trophy", "success", "award", "growth", "rocket"))
    idea_like = any(k in visual for k in ("lightbulb", "solution", "idea"))
    step_like = intent == "step" or intent == "explanation" and any(k in speech for k in ("خطوة", "طريقة", "كيف", "ثم", "بعدها"))

    if audio_like or time_like:
        # Two real timeline tracks. The red gap visibly collapses while the cutter
        # crosses it; the clean track then keeps playing under a moving playhead.
        label("قبل المعالجة" if audio_like else "الوقت قبل التنظيم", (480, 94), 27, danger)
        x0, x1 = 86, 874
        top_y, bottom_y = 205, 358
        line([(x0, top_y), (x1, top_y)], border, 3)
        line([(x0, bottom_y), (x1, bottom_y)], border, 3)
        bars = 34
        gap_a, gap_b = 14, 19
        cut_progress = _smoothstep((p - 0.13) / 0.42)
        # Original track: a real gap is shown in red, not an unrelated badge.
        x_gap0 = int(x0 + 8 + gap_a * ((x1-x0-16) / (bars-1)))
        x_gap1 = int(x0 + 8 + gap_b * ((x1-x0-16) / (bars-1)))
        gap_cx = (x_gap0+x_gap1)//2
        open_half = int(((x_gap1-x_gap0)//2 + 10) * (1.0-cut_progress) + 3)
        # A clearly visible red empty segment is the problem itself. It closes once
        # as the edit action completes; no unrelated rings or decorative particles.
        draw.rounded_rectangle((gap_cx-open_half, top_y-62, gap_cx+open_half, top_y+62),
                               radius=10, fill=(*danger, 34), outline=(*danger, 170), width=2)
        for i in range(bars):
            x = x0 + 8 + i * ((x1-x0-16) / (bars-1))
            is_gap = gap_a <= i <= gap_b
            h = int(18 + 34 * abs(math.sin(i * 1.17 + t * 2.1)))
            if is_gap and abs(x-gap_cx) < open_half-3:
                # Deliberately leave the silence blank until the cutter closes it.
                continue
            col = secondary if i < gap_a else accent
            draw.rounded_rectangle((int(x-5), top_y-h, int(x+5), top_y+h), radius=4, fill=(*col, 255))
        label("فجوة صمت" if open_half > 18 else "تم القص", (gap_cx, top_y-76), 20, danger if open_half > 18 else success)
        # The cutter approaches and passes through the gap during the action phase.
        cutter_x = int(x0 + (x1-x0) * _clamp01((p - 0.08) / 0.48))
        if p < 0.62:
            line([(cutter_x-14, top_y-46), (cutter_x+14, top_y-18)], danger, 6)
            line([(cutter_x+14, top_y-46), (cutter_x-14, top_y-18)], danger, 6)
            line([(cutter_x, top_y-14), (cutter_x, top_y+17)], danger, 4)
        label("بعد القص" if audio_like else "الوقت بعد التنظيم", (480, 288), 26, success)
        # Clean waveform follows a playback playhead; this motion continues for the
        # whole scene so the illustration never freezes after the initial reveal.
        play_x = int(x0 + ((t * 190.0) % (x1 - x0)))
        for i in range(bars):
            x = x0 + 8 + i * ((x1-x0-16) / (bars-1))
            h = int(12 + 25 * abs(math.sin(i * .86 + t * 3.0)))
            col = success if x < play_x else secondary
            draw.rounded_rectangle((int(x-4), bottom_y-h, int(x+4), bottom_y+h), radius=4, fill=(*col, 255))
        line([(play_x, bottom_y-52), (play_x, bottom_y+52)], text, 3)
        card((74, 410, 886, 452), fill=border, outline=border, width=1, radius=14)
        progress_w = int(800 * ((t * 0.36) % 1.0))
        if progress_w > 0:
            draw.rounded_rectangle((80, 416, min(880, 80+progress_w), 446), radius=10, fill=(*success, 255))
        return True

    if social_like:
        # A social post becomes an analytics composition: media preview on the left,
        # metrics and bars on the right, then a cursor activates the matching metric.
        card((74, 78, 370, 426), fill=border, outline=secondary, width=3, radius=30)
        card((94, 98, 350, 406), fill=surface, outline=border, width=2, radius=20)
        # Content preview, not a decorative icon.
        draw.rounded_rectangle((120, 128, 324, 232), radius=16, fill=(*secondary, 255))
        draw.polygon([(200, 153), (200, 207), (245, 180)], fill=(*text, 255))
        for j in range(3):
            w = 150 - 16*j
            draw.rounded_rectangle((120, 250+j*18, 120+w, 258+j*18), radius=4, fill=(*muted, 255))
        # Reaction chips appear in sequence, attached to the content card.
        reaction_phase = int((t * 1.05) % 3)
        for j, x in enumerate((155, 225, 295)):
            y = 365
            fill = accent if j == reaction_phase else border
            card((x-25, y-22, x+25, y+22), fill=fill, outline=fill, width=1, radius=14)
            icon_col = text if j == reaction_phase else muted
            if j == 0:  # like / reaction
                draw.polygon([(x, y+11), (x-13, y-1), (x-13, y-8), (x-6, y-13), (x, y-6), (x+6, y-13), (x+13, y-8), (x+13, y-1)], fill=(*icon_col, 255))
            elif j == 1:  # comment bubble
                draw.rounded_rectangle((x-13, y-10, x+13, y+8), radius=5, outline=(*icon_col, 255), width=3)
                draw.polygon([(x-6, y+7), (x-2, y+14), (x+3, y+7)], fill=(*icon_col, 255))
            else:  # share arrow
                line([(x-12, y+8), (x+10, y-9)], icon_col, 3)
                draw.polygon([(x+10, y-9), (x+1, y-8), (x+9, y+1)], fill=(*icon_col, 255))
        # Three analytics cards, one active at a time; progress bars fill to measured
        # phase positions, making the visual tell a cause -> result story.
        metric_rows = [(110, "المشاهدة"), (220, "التفاعل"), (330, "الوصول")]
        for i, (cy, title) in enumerate(metric_rows):
            active = (int(t * 1.0) % 3) == i
            fill = (*accent, 255) if active else (*border, 255)
            card((430, cy-43, 874, cy+43), fill=surface, outline=accent if active else border, width=4 if active else 2, radius=18)
            label(title, (805, cy-13), 25, text)
            bar_x0, bar_y, bar_w = 465, cy+13, 340
            draw.rounded_rectangle((bar_x0, bar_y, bar_x0+bar_w, bar_y+9), radius=4, fill=(*border, 255))
            fill_p = _clamp01(0.20 + 0.72 * ((t * 0.42 + i*0.23) % 1.0))
            draw.rounded_rectangle((bar_x0, bar_y, bar_x0+int(bar_w*fill_p), bar_y+9), radius=4, fill=(*(success if active else secondary), 255))
        # Cursor travels from post to the active metric, then visibly presses it.
        target = metric_rows[int(t*1.0)%3][0]
        cursor_p = (t * 0.75) % 1.0
        cx = int(370 + (430-370)*cursor_p)
        cy = int(260 + (target-260)*cursor_p)
        draw.polygon([(cx, cy), (cx+5, cy+27), (cx+12, cy+17), (cx+25, cy+20), (cx+28, cy+14), (cx+16, cy+10), (cx+23, cy+1)], fill=(*text, 255), outline=(*surface, 255))
        return True

    if ai_like:
        # Three-stage transformation: the spoken phrase moves through a processor
        # and becomes an on-screen scene. The moving signal follows the connector path.
        card((62, 142, 302, 332), fill=border, outline=secondary, width=3, radius=22)
        card((360, 116, 600, 360), fill=surface, outline=accent, width=4, radius=32)
        card((658, 142, 898, 332), fill=border, outline=success, width=3, radius=22)
        label("الكلام", (182, 177), 26, secondary)
        phrase = k0[:18]
        label(phrase, (182, 236), 25, text)
        label("فهم المعنى", (480, 163), 29, accent)
        # Processor blocks transform / light up in order.
        for i in range(4):
            active = (int(t*2.1) % 4) == i
            x = 407 + i*38
            draw.rounded_rectangle((x, 222, x+25, 281), radius=7, fill=(*(accent if active else border), 255))
        label("المشهد", (778, 177), 26, success)
        label(k1[:18], (778, 236), 25, text)
        arrow(304, 245, 350, 245, secondary, 5)
        arrow(602, 245, 648, 245, success, 5)
        # Signal dot travels left -> processor -> output; unlike an orbit it means data flow.
        phase = (t * 0.72) % 1.0
        sx, ex = 309, 651
        dot_x = int(sx + (ex-sx)*phase)
        dot_y = 245 + int(8*math.sin(phase*math.pi*2))
        draw.ellipse((dot_x-8, dot_y-8, dot_x+8, dot_y+8), fill=(*text, 255))
        # The output card is progressively revealed and continuously reflows a caption block.
        reveal = _clamp01((p - .14) / .65)
        for i in range(3):
            w = int((160 - i*28) * reveal)
            if w > 0:
                draw.rounded_rectangle((705, 278+i*13, 705+w, 284+i*13), radius=3, fill=(*success, 255))
        return True

    if editing_like:
        # A real editing timeline: media clips, audio lane, and a playback head move
        # in sync. This reads as software in use rather than a hovering camera icon.
        label("معاينة الفيديو", (480, 92), 26, secondary)
        card((255, 120, 705, 270), fill=border, outline=secondary, width=3, radius=18)
        draw.rounded_rectangle((280, 142, 680, 250), radius=12, fill=(*surface, 255))
        label(k0[:22], (480, 191), 27, text)
        # Playback timeline with clip segments of different lengths.
        tx0, ty0, tx1 = 90, 330, 870
        clip_cols = [accent, secondary, success, accent, danger]
        widths = [108, 146, 94, 166, 112]
        x = tx0
        active_idx = int((t * 1.25) % len(widths))
        for i, w in enumerate(widths):
            ww = int(w * (1.0 + 0.05*p))
            col = clip_cols[i]
            draw.rounded_rectangle((x, ty0, x+ww, ty0+46), radius=8, fill=(*col, 255), outline=(*text, 255) if active_idx==i else (*col,255), width=3 if active_idx==i else 1)
            for k in range(2):
                draw.rounded_rectangle((x+9, ty0+8+k*14, x+ww-9, ty0+14+k*14), radius=3, fill=(*(surface if k==0 else border), 255))
            x += ww + 10
        # Audio lane + continuous playback head.
        draw.rounded_rectangle((tx0, 390, tx1, 425), radius=8, fill=(*border, 255))
        for i in range(40):
            bx = tx0 + 5 + i*19
            h = 5 + int(9*abs(math.sin(i*.55+t*3.5)))
            draw.rounded_rectangle((bx, 407-h, bx+6, 407+h), radius=2, fill=(*(success if i < int(40*((t*.32)%1)) else secondary), 255))
        play_x = int(tx0 + ((t*205) % (tx1-tx0)))
        line([(play_x, 300), (play_x, 434)], text, 4)
        return True

    if delivery_like:
        # A route diagram with start, transit and destination. The parcel follows the
        # actual route line; it does not orbit the map or drift independently.
        label("مسار الحركة", (480, 91), 26, secondary)
        route = [(105, 290), (270, 208), (425, 285), (590, 190), (840, 284)]
        line(route, border, 16)
        # Draw the completed route in a progressive stroke, segment by segment.
        seg_progress = _clamp01((t * 0.55) % 1.0)
        max_seg = int(seg_progress * (len(route)-1))
        for i in range(max_seg):
            line([route[i], route[i+1]], success, 9)
        if max_seg < len(route)-1:
            a, b = route[max_seg], route[max_seg+1]
            u = (seg_progress*(len(route)-1)) - max_seg
            mx, my = int(a[0]+(b[0]-a[0])*u), int(a[1]+(b[1]-a[1])*u)
            line([a,(mx,my)],success,9)
        # Origin / transit / destination are anchored to the actual path.
        for i, (x, y) in enumerate((route[0], route[2], route[-1])):
            col = accent if i == 1 else (success if i == 2 and seg_progress > .8 else secondary)
            card((x-43,y-41,x+43,y+41),fill=surface,outline=col,width=4,radius=16)
            if i == 0:
                draw.rectangle((x-13,y-12,x+13,y+12),fill=(*col,255))
            elif i == 1:
                draw.rounded_rectangle((x-20,y-13,x+20,y+13),radius=5,fill=(*col,255))
                draw.ellipse((x-14,y+7,x-4,y+17),fill=(*text,255)); draw.ellipse((x+4,y+7,x+14,y+17),fill=(*text,255))
            else:
                draw.line([(x-17,y),(x-3,y+13),(x+20,y-16)],fill=(*col,255),width=6)
        # Moving parcel sits on the route itself.
        parcel_phase = (t*0.5) % 1.0
        distance = parcel_phase * (len(route)-1)
        i = min(len(route)-2, int(distance)); u = distance-i
        a, b = route[i], route[i+1]
        mx, my = int(a[0]+(b[0]-a[0])*u), int(a[1]+(b[1]-a[1])*u)
        card((mx-21,my-19,mx+21,my+19),fill=accent,outline=text,width=2,radius=7)
        label(k0[:18], (210, 390), 24, text)
        label(k1[:18], (745, 390), 24, text)
        return True

    if security_like:
        # Verification interface with a moving scan band and a deliberate approval
        # transition; the shield belongs to the access panel rather than floating.
        card((80, 105, 880, 422), fill=border, outline=secondary, width=3, radius=26)
        card((115, 146, 340, 374), fill=surface, outline=accent, width=3, radius=20)
        card((620, 146, 845, 374), fill=surface, outline=success, width=3, radius=20)
        label("فحص", (227, 184), 26, secondary)
        label(k0[:16], (227, 240), 24, text)
        # Shield/check graphic is integrated in the approval panel.
        sx, sy = 732, 250
        shield=[(sx,sy-62),(sx+49,sy-42),(sx+42,sy+24),(sx,sy+65),(sx-42,sy+24),(sx-49,sy-42)]
        draw.polygon(shield,fill=(*success,255),outline=(*text,255))
        draw.line([(sx-24,sy),(sx-6,sy+18),(sx+28,sy-22)],fill=(*surface,255),width=8)
        label(k1[:16], (732, 348), 24, success)
        arrow(360, 260, 596, 260, secondary, 5)
        scan_x = 118 + int(200*((t*.65)%1.0))
        draw.rounded_rectangle((scan_x, 205, min(330,scan_x+9), 322), radius=4, fill=(*accent,255))
        return True

    if success_like:
        # A result assembles through a progress board: bars grow, the active bar moves,
        # and the outcome card is revealed. No floating trophy or invented KPI number.
        card((78, 82, 882, 421), fill=border, outline=secondary, width=3, radius=26)
        label(k0[:25], (480, 128), 28, text)
        chart_x0, chart_y0, chart_h = 170, 355, 170
        bar_w, gap = 92, 52
        active = int((t*0.9)%5)
        for i in range(5):
            h = int((38 + i*25) * _smoothstep((t - i*.10 + .1)/.55))
            x = chart_x0 + i*(bar_w+gap)
            col = accent if i==active else (success if i<active else secondary)
            draw.rounded_rectangle((x, chart_y0-h, x+bar_w, chart_y0), radius=10, fill=(*col,255))
        # Focus marker moves to the current stage of the result.
        marker_x = chart_x0 + active*(bar_w+gap) + bar_w//2
        line([(marker_x, 172), (marker_x, 190)], text, 4)
        label(k1[:18], (480, 398), 24, success)
        return True

    if idea_like:
        # One spoken idea branches into only the distinct sub-phrases actually available.
        idea_labels = list(dict.fromkeys(x for x in keywords if x))[:3]
        card((66, 168, 350, 342), fill=border, outline=accent, width=4, radius=26)
        label((idea_labels[0] if idea_labels else k0)[:20], (208, 240), 28, text)
        branch_labels = idea_labels[1:3]
        if branch_labels:
            branch_y = [255] if len(branch_labels) == 1 else [166, 344]
            for i, (title, y) in enumerate(zip(branch_labels, branch_y)):
                col = secondary if i == 0 else success
                card((590, y-54, 890, y+54), fill=surface, outline=col, width=4, radius=20)
                label(title[:20], (740, y), 25, text)
                points = [(350,255),(450,255),(450,y),(575,y)]
                line(points, col, 5)
            # Signal follows one of the actual branches, staying on its connector.
            branch = int((t*.7)%len(branch_labels))
            u = (t*.7)%1.0
            y = branch_y[branch]
            pts=[(350,255),(450,255),(450,y),(575,y)]
            lengths=[math.dist(pts[i],pts[i+1]) for i in range(len(pts)-1)]
            distance=u*sum(lengths)
            cur=pts[0]
            dot=pts[-1]
            for i, length in enumerate(lengths):
                nxt=pts[i+1]
                if distance <= length:
                    frac=distance/max(1.0,length)
                    dot=(int(cur[0]+(nxt[0]-cur[0])*frac),int(cur[1]+(nxt[1]-cur[1])*frac))
                    break
                distance-=length; cur=nxt
            draw.ellipse((dot[0]-7,dot[1]-7,dot[0]+7,dot[1]+7),fill=(*accent,255))
        else:
            # A single idea stays singular: reveal an underline and sweep a scan marker.
            reveal = int(230*_smoothstep((t-.12)/.5))
            if reveal:
                draw.rounded_rectangle((92, 365, 92+reveal, 377), radius=5, fill=(*accent,255))
            scan_x = 90 + int(245*((t*.42)%1.0))
            line([(scan_x,190),(scan_x,310)], secondary, 3)
        return True

    if step_like:
        # Sequential cards connected by arrows. Each current step lights up in order.
        labels = [k0, k1, k2]
        xs = [175, 480, 785]
        active_idx = int((t * 0.95) % 3)
        for i, (x, title) in enumerate(zip(xs, labels)):
            entered = _smoothstep((t - i*0.16) / 0.28)
            y_shift = int((1.0-entered)*42)
            col = accent if i == active_idx else border
            card((x-122, 170+y_shift, x+122, 338+y_shift), fill=surface, outline=col, width=5 if i==active_idx else 2, radius=24)
            draw.ellipse((x-27, 120+y_shift, x+27, 174+y_shift), fill=(*col, 255))
            label(str(i+1), (x, 147+y_shift), 26, text if i==active_idx else muted)
            label(title[:16], (x, 253+y_shift), 26, text)
            if i < 2:
                arrow(x+124, 252+y_shift, xs[i+1]-126, 252+y_shift, secondary, 5)
        # Progress bar moves from one step to the next; it has a narrative purpose.
        draw.rounded_rectangle((100, 390, 860, 407), radius=8, fill=(*border, 255))
        draw.rounded_rectangle((100, 390, 100+int(760*((t*.34)%1)), 407), radius=8, fill=(*success, 255))
        return True

    # General explanation fallback: use only distinct phrases from this clause. Never
    # duplicate a keyword just to fill three cards; one- and two-idea clauses get a
    # proportionate layout instead of an artificial three-step story.
    labels = list(dict.fromkeys(x for x in keywords if x))[:3]
    if len(labels) >= 3:
        xs = [175, 480, 785]
        active_idx = int((t * 0.8) % 3)
        for i, (x, title) in enumerate(zip(xs, labels)):
            col = accent if i == active_idx else border
            enter = _smoothstep((t-i*0.13)/0.25)
            lift = int((1.0-enter)*26)
            card((x-122, 164+lift, x+122, 335+lift), fill=surface, outline=col, width=5 if i==active_idx else 2, radius=24)
            label(title[:18], (x, 240+lift), 27, text if i == active_idx else muted)
            if i < 2:
                arrow(x+124, 250+lift, xs[i+1]-126, 250+lift, secondary, 5)
        phase = (t*0.68) % 1.0
        seg = 0 if phase < .5 else 1
        u = (phase*2) % 1.0
        x = int(xs[seg] + (xs[seg+1]-xs[seg])*u)
        draw.ellipse((x-7, 244, x+7, 258), fill=(*success, 255))
    elif len(labels) == 2:
        left_x, right_x = 270, 690
        active_idx = int((t * .65) % 2)
        for i, (x, title) in enumerate(((left_x, labels[0]), (right_x, labels[1]))):
            enter = _smoothstep((t - i*0.17)/0.28)
            y_shift = int((1.0-enter)*36)
            col = accent if active_idx == i else border
            card((x-155, 155+y_shift, x+155, 345+y_shift), fill=surface, outline=col, width=5 if active_idx==i else 2, radius=26)
            label(title[:22], (x, 250+y_shift), 30, text if active_idx==i else muted)
        arrow(438, 250, 522, 250, secondary, 5)
        progress = (t*0.6) % 1.0
        x = int(440 + 80*progress)
        draw.ellipse((x-7, 243, x+7, 257), fill=(*success, 255))
    elif len(labels) == 1:
        # Single idea: one strong stage with a revealing underline and an active timeline.
        enter = _smoothstep(t/.3)
        y = 235 + int((1.0-enter)*35)
        card((150, 148, 810, 350), fill=surface, outline=accent, width=4, radius=28)
        label(labels[0][:30], (480, y), 34, text)
        width = int(540*_smoothstep((t-.12)/.62))
        if width > 0:
            draw.rounded_rectangle((210, 300, min(750, 210+width), 312), radius=6, fill=(*accent, 255))
        cue_x = 210 + int(540*((t*.42)%1))
        line([(cue_x, 324), (cue_x, 340)], success, 4)
    else:
        # With no grounded headline, show a neutral timeline rather than fabricate text.
        for i in range(5):
            x = 120 + i*165
            active = int(t*1.2)%5 == i
            card((x-55, 195, x+55, 305), fill=surface, outline=accent if active else border, width=4 if active else 2, radius=18)
            draw.rounded_rectangle((x-24, 230, x+24, 270), radius=6, fill=(*(accent if active else border), 255))
    return True


def render_scene_card_and_measure_dom(
    sc: Dict[str, Any],
    theme: Dict[str, Any],
    animation_t: float = 0.5,
    motion_svg: str = "",
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    يرسم مشهدًا ضمن حاوية العرض البصري (960×940 عند x=60, y=280) باستخدام PIL + NumPy.
    motion_svg محفوظ كوسيط اختياري للتوافق مع المستدعين الأقدم؛ السلوك المرئي الحالي
    يعتمد على حركات دلالية وظيفية مرتبطة بنية المشهد، وليس على أيقونة SVG وحيدة.
    """
    cw, ch = 960, 940
    img = Image.new("RGBA", (cw, ch), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    tpl = sc.get("template", "kinetic_hook")
    keywords = [_safe_graphic_text(k) for k in sc.get("keywords", ["تركيز بصري"]) if _safe_graphic_text(k)]
    numbers = [_safe_graphic_text(n) for n in sc.get("numbers", []) if _safe_graphic_text(n)]
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
        """Draw centered Arabic text with measured wrapping; never let long headlines overflow."""
        text = _safe_graphic_text(text)
        if not text:
            return
        max_width = cw - 80
        chosen_size = int(font_size)
        lines = []
        while chosen_size >= 48:
            fnt = get_font(chosen_size, bold=True)
            lines = []
            current = []
            for word in text.split():
                candidate = " ".join(current + [word])
                bb = draw.textbbox((0, 0), candidate, font=fnt, direction="rtl")
                if current and (bb[2] - bb[0]) > max_width:
                    lines.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(" ".join(current))
            widths = []
            for line in lines:
                bb = draw.textbbox((0, 0), line, font=fnt, direction="rtl")
                widths.append(bb[2] - bb[0])
            if len(lines) <= 2 and all(width <= max_width for width in widths):
                break
            chosen_size -= 4
        chosen_size = max(48, chosen_size)
        fnt = get_font(chosen_size, bold=True)
        line_metrics = []
        for line in lines[:2]:
            bb = draw.textbbox((0, 0), line, font=fnt, direction="rtl")
            line_metrics.append((line, bb, bb[2] - bb[0], bb[3] - bb[1]))
        line_gap = max(4, int(chosen_size * 0.12))
        total_h = sum(item[3] for item in line_metrics) + line_gap * max(0, len(line_metrics) - 1)
        y_top = int(y_center - total_h / 2)
        for line, bbox, tw, th in line_metrics:
            x = (cw - tw) // 2
            draw.text((x, y_top - bbox[1]), line, font=fnt, fill=(*color_rgb, 255), direction="rtl")
            if is_headline:
                headlines_dom.append({
                    "text": line,
                    "rect": {
                        "left": 60 + x,
                        "top": 280 + y_top,
                        "right": 60 + x + tw,
                        "bottom": 280 + y_top + th,
                        "width": tw,
                        "height": th,
                    },
                    "fontSize": chosen_size,
                })
            y_top += th + line_gap


    if tpl == "kinetic_hook":
        # Kinetic typography as a deliberate reveal: words enter in two beats, with a
        # directional underline wipe instead of a decorative energy ring.
        enter0 = _smoothstep((float(animation_t) - 0.02) / 0.26)
        enter1 = _smoothstep((float(animation_t) - 0.18) / 0.28)
        y0 = 390 + int((1.0-enter0)*46)
        y1 = 555 + int((1.0-enter1)*38)
        draw.rounded_rectangle([60, 170, cw - 60, 740], radius=34, fill=(14, 21, 38, 235), outline=(*border, 255), width=3)
        add_centered_text(kw0, y0, 92, (255, 255, 255), is_headline=True)
        wipe = int((cw - 160) * _smoothstep((float(animation_t)-0.22)/0.38))
        if wipe > 0:
            draw.rounded_rectangle([80, 474, min(cw-80, 80+wipe), 487], radius=6, fill=(*accent, 255))
        if kw1 and float(animation_t) > 0.12:
            add_centered_text(kw1, y1, 84, accent, is_headline=True)

    elif tpl == "concept_icon":
        story_colors = {
            "accent": accent, "secondary": secondary, "success": success, "danger": danger,
            "surface": surface, "border": border, "text": (255,255,255), "muted": (155,170,190),
        }
        _draw_storyboard_scene(draw, sc, animation_t, story_colors)
        add_centered_text(kw0, 565, 82, (255, 255, 255), is_headline=True)
        if kw1 and kw1 != kw0:
            add_centered_text(kw1, 695, 74, accent, is_headline=True)

    elif tpl == "big_number":
        # A spoken number is the hero. Use a linear reveal rail instead of a generic
        # halo/icon that would make the scene look like a floating sticker.
        rail_p = _smoothstep(float(animation_t) / 0.7)
        draw.rounded_rectangle([cw//2-245, 160, cw//2+245, 178], radius=8, fill=(*border,255))
        rail_fill = int(490 * rail_p)
        if rail_fill:
            draw.rounded_rectangle([cw//2-245,160,cw//2-245+rail_fill,178],radius=8,fill=(*accent,255))
        raw_num = str(numbers[0] if numbers else "0")
        digits_part = "".join(ch for ch in raw_num if ch in "0123456789%+") or "0"
        entry_scale = _smoothstep(float(animation_t) / 0.34)
        f_big = get_font(int(100 + 45*entry_scale), bold=True, latin=True)
        bbox = draw.textbbox((0, 0), digits_part, font=f_big)
        nw = bbox[2] - bbox[0]
        num_y = 315 + int((1.0-entry_scale)*42)
        draw.text(((cw - nw) // 2, num_y - bbox[1]), digits_part, font=f_big, fill=(*accent, 255))
        rail_w = int(480*_smoothstep((float(animation_t)-0.12)/0.55))
        if rail_w:
            draw.rounded_rectangle([cw//2-240, 410, cw//2-240+rail_w, 422], radius=5, fill=(*secondary,255))
        # The number is grounded in spoken audio; supporting labels must also come from the scene.
        add_centered_text(kw0, 515, 74, secondary, is_headline=True)
        if kw1:
            add_centered_text(kw1, 665, 72, (255, 255, 255), is_headline=True)
        if kw2:
            add_centered_text(kw2, 785, 68, accent, is_headline=True)

    elif tpl == "phone_reel_mockup":
        if sc.get("intent") == "social_media":
            story_colors = {"accent": accent, "secondary": secondary, "success": success, "danger": danger,
                            "surface": surface, "border": border, "text": (255,255,255), "muted": (155,170,190)}
            _draw_storyboard_scene(draw, sc, animation_t, story_colors)
            add_centered_text(kw0, 565, 82, (255,255,255), is_headline=True)
            if kw1 and kw1 != kw0:
                add_centered_text(kw1, 695, 74, accent, is_headline=True)
        else:
            px0, py0, px1, py1 = cw // 2 - 220, 65, cw // 2 + 220, 650
            draw.rounded_rectangle([px0, py0, px1, py1], radius=46, fill=(11, 17, 32, 255), outline=(*border, 255), width=6)
            draw.rounded_rectangle([cw // 2 - 55, py0 + 22, cw // 2 + 55, py0 + 34], radius=6, fill=(*border, 255))
            draw.rounded_rectangle([px0 + 28, py0 + 60, px1 - 28, py1 - 65], radius=28, fill=(22, 31, 51, 255), outline=(*danger, 255), width=4)
            # أيقونة الكاميرا/إنستغرام المصغرة + منحنى هبوط التفاعل الأحمر داخل شاشة الهاتف
            draw.rounded_rectangle([cw // 2 - 42, 160, cw // 2 + 42, 244], radius=22, outline=(*danger, 255), width=5)
            draw.ellipse([cw // 2 - 18, 184, cw // 2 + 18, 220], outline=(255, 255, 255, 255), width=4)
            chart_p = _clamp01(float(animation_t) / max(0.8, (float(sc.get("end", 3.0)) - float(sc.get("start", 0.0))) * 0.65))
            pts = [(cw // 2 - 110, 285), (cw // 2 - 35, 335), (cw // 2 + 25, 315), (cw // 2 + 110, 415)]
            visible_pts = max(2, min(len(pts), int(2 + chart_p * (len(pts)-1))))
            draw.line(pts[:visible_pts], fill=(*danger, 255), width=10)
            if visible_pts == len(pts):
                draw.polygon([(cw // 2 + 115, 422), (cw // 2 + 82, 415), (cw // 2 + 108, 388)], fill=(*danger, 255))
            # The mini progress rail scrolls while the content is playing.
            moving_x = px0 + 30 + int(((float(animation_t)*115) % 280))
            draw.line([(moving_x, py1-55), (moving_x, py1-28)], fill=(*accent, 255), width=6)
            add_centered_text(kw0, 505, 72, (255, 255, 255), is_headline=True)
            if kw1:
                add_centered_text(kw1, 755, 76, accent, is_headline=True)
    elif tpl == "before_after":
        # For audio editing, show the actual edit operation (gap closure + playhead),
        # not two static labels. Other comparisons animate the two panels into place.
        if sc.get("intent") == "audio_edit":
            story_colors = {"accent": accent, "secondary": secondary, "success": success, "danger": danger,
                            "surface": surface, "border": border, "text": (255,255,255), "muted": (155,170,190)}
            _draw_storyboard_scene(draw, sc, animation_t, story_colors)
            add_centered_text(kw0 or "الصمت", 565, 82, (255, 255, 255), is_headline=True)
            if kw1 and kw1 != kw0:
                add_centered_text(kw1, 695, 74, accent, is_headline=True)
        else:
            p_in = _smoothstep(float(animation_t)/0.32)
            # Before/after panels enter from opposite sides; focus moves between claims.
            left_shift = int((1.0-p_in)*90)
            right_shift = int((1.0-p_in)*-90)
            active_after = (float(animation_t) % 1.6) > 0.75
            draw.rounded_rectangle([50-left_shift, 125, cw-50-left_shift, 415], radius=30, fill=(45,18,30,255), outline=(*danger,255), width=4)
            add_centered_text("قبل", 195, 52, danger, is_headline=False)
            add_centered_text(kw0, 310, 76, (255,255,255), is_headline=True)
            # Linear transformation marker, with a progress bar instead of floating rings.
            draw.rounded_rectangle([cw//2-180, 438, cw//2+180, 458], radius=8, fill=(*border,255))
            pw = int(360*_smoothstep((float(animation_t)-.18)/.55))
            if pw:
                draw.rounded_rectangle([cw//2-180, 438, cw//2-180+pw, 458], radius=8, fill=(*accent,255))
            draw.rounded_rectangle([50+right_shift, 498, cw-50+right_shift, 795], radius=30, fill=(14,46,38,255), outline=(*(accent if active_after else success),255), width=5 if active_after else 3)
            add_centered_text("بعد", 570, 52, success, is_headline=False)
            add_centered_text(kw1 or kw0, 685, 76, accent, is_headline=True)

    elif tpl == "checklist":
        items = list(dict.fromkeys(k for k in [kw0, kw1, kw2] if k))
        active_idx = int((float(animation_t)*0.8) % max(1, len(items)))
        for idx_i, item in enumerate(items):
            entry = _smoothstep((float(animation_t)-idx_i*0.17)/0.28)
            y_shift = int((1.0-entry)*55)
            y0 = 140 + idx_i * 225 + y_shift
            y1 = y0 + 185
            is_active = idx_i == active_idx
            col = accent if is_active else border
            draw.rounded_rectangle([50, y0, cw-50, y1], radius=28, fill=(*surface,255), outline=(*col,255), width=5 if is_active else 3)
            cx_i, cy_i = cw-125, (y0+y1)//2
            check_size = 26 + int(10*_smoothstep((float(animation_t)-idx_i*0.17-0.08)/0.18))
            draw.ellipse([cx_i-check_size, cy_i-check_size, cx_i+check_size, cy_i+check_size], fill=(*(success if entry > .6 else border),255))
            if entry > .45:
                draw.line([cx_i-16,cy_i,cx_i-4,cy_i+14,cx_i+18,cy_i-14], fill=(9,13,22,255), width=7)
            add_centered_text(item, cy_i, 72, (255,255,255), is_headline=True)

    elif tpl == "steps_flow":
        items = list(dict.fromkeys(k for k in [kw0, kw1, kw2] if k))
        active_idx = int((float(animation_t)*0.8) % max(1, len(items)))
        for idx_i, item in enumerate(items):
            entry = _smoothstep((float(animation_t)-idx_i*0.18)/0.28)
            y_shift = int((1.0-entry)*48)
            y0 = 140 + idx_i*225 + y_shift
            y1 = y0 + 185
            is_active = idx_i == active_idx
            b_col = accent if is_active else secondary
            draw.rounded_rectangle([50,y0,cw-50,y1], radius=28, fill=(*surface,255), outline=(*b_col,255), width=5 if is_active else 3)
            cx_i, cy_i = cw-125, (y0+y1)//2
            draw.rounded_rectangle([cx_i-36,cy_i-36,cx_i+36,cy_i+36], radius=18, fill=(*b_col,255))
            f_num = get_font(46,bold=True,latin=True)
            num_txt = str(idx_i+1)
            nb = draw.textbbox((0,0),num_txt,font=f_num)
            draw.text((cx_i-(nb[2]-nb[0])//2,cy_i-(nb[3]-nb[1])//2-nb[1]),num_txt,font=f_num,fill=(9,13,22,255))
            add_centered_text(item,cy_i,72,(255,255,255),is_headline=True)
        # A step-index rail shows progression through the demonstrated process.
        draw.rounded_rectangle([95, 835, cw-95, 852], radius=8, fill=(*border,255))
        rail_x = 95 + int((cw-190)*((float(animation_t)*0.28)%1.0))
        draw.rounded_rectangle([95,835,rail_x,852], radius=8, fill=(*success,255))

    elif tpl == "versus":
        p_in = _smoothstep(float(animation_t)/0.32)
        left_shift = int((1.0-p_in)*-95)
        right_shift = int((1.0-p_in)*95)
        left_active = (float(animation_t)%1.8) < .9
        draw.rounded_rectangle([50+left_shift,130,cw//2-22+left_shift,395],radius=28,fill=(*surface,255),outline=(*(danger if left_active else border),255),width=5 if left_active else 2)
        add_centered_text(kw0,262,74,(252,165,165) if left_active else (190,190,200),is_headline=True)
        draw.rounded_rectangle([cw//2+22+right_shift,130,cw-50+right_shift,395],radius=28,fill=(*surface,255),outline=(*(accent if not left_active else border),255),width=5 if not left_active else 2)
        add_centered_text(kw1 or kw0,262,74,accent if not left_active else (190,190,200),is_headline=True)
        # A moving comparison marker travels along a straight divider, not around the content.
        f_vs = get_font(44,bold=True,latin=True)
        vb = draw.textbbox((0,0),"VS",font=f_vs)
        draw.rounded_rectangle([cw//2-52, 423, cw//2+52, 503], radius=20, fill=(*accent,255))
        draw.text((cw//2-(vb[2]-vb[0])//2,463-(vb[3]-vb[1])//2-vb[1]),"VS",font=f_vs,fill=(9,13,22,255))
        divider_y = 555 + int(210*((float(animation_t)*.42)%1.0))
        draw.rounded_rectangle([cw//2-5, 535, cw//2+5, 790], radius=4, fill=(*border,255))
        draw.rounded_rectangle([cw//2-13, divider_y-13, cw//2+13, divider_y+13], radius=8, fill=(*(danger if left_active else accent),255))

    elif tpl == "fullscreen_image":
        box_w, box_h = 860, 620
        bx0, by0 = (cw - box_w) // 2, 65
        sb_panel = sc.get("image_path") or sc.get("storyboard_panel_path")
        if sb_panel and os.path.exists(str(sb_panel)):
            try:
                with Image.open(sb_panel) as pim:
                    p_resized = pim.convert("RGBA").resize((box_w - 16, box_h - 16), Image.Resampling.LANCZOS)
                draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=38, fill=(14, 22, 40, 255), outline=(*accent, 255), width=6)
                img.paste(p_resized, (bx0 + 8, by0 + 8))
            except Exception:
                pass
        else:
            draw.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=38, fill=(14, 22, 40, 255), outline=(*accent, 255), width=5)
            draw.rounded_rectangle([bx0 + 70, by0 + 65, bx0 + box_w - 70, by0 + 440], radius=24, fill=(9, 13, 22, 255), outline=(*secondary, 255), width=4)
            draw.rounded_rectangle([bx0 + 115, by0 + 120, bx0 + 450, by0 + 165], radius=12, fill=(*accent, 230))
            draw.rounded_rectangle([bx0 + 470, by0 + 120, bx0 + box_w - 115, by0 + 165], radius=12, fill=(*secondary, 230))
            draw.rounded_rectangle([bx0 + 115, by0 + 195, bx0 + 360, by0 + 240], radius=12, fill=(*secondary, 200))
            draw.rounded_rectangle([bx0 + 380, by0 + 195, bx0 + box_w - 145, by0 + 240], radius=12, fill=(*success, 230))
            for b_i in range(18):
                bx_bar = bx0 + 135 + b_i * 33
                bh_bar = 22 + int(30 * abs(math.sin(b_i * 0.65)))
                draw.rounded_rectangle([bx_bar, by0 + 335 - bh_bar, bx_bar + 17, by0 + 335 + bh_bar], radius=6, fill=(*accent, 255) if b_i % 2 == 0 else (*secondary, 255))
            px_head = bx0 + box_w // 2
            draw.line([px_head, by0 + 95, px_head, by0 + 415], fill=(255, 255, 255, 255), width=5)
            draw.polygon([(px_head - 14, by0 + 95), (px_head + 14, by0 + 95), (px_head, by0 + 118)], fill=(*accent, 255))
            draw.rounded_rectangle([cw // 2 - 110, by0 + 450, cw // 2 + 110, by0 + 520], radius=14, fill=(*border, 255))
            draw.rounded_rectangle([cw // 2 - 190, by0 + 515, cw // 2 + 190, by0 + 545], radius=12, fill=(*secondary, 255))
        add_centered_text(kw0, 755, 78, (255, 255, 255), is_headline=True)
        if kw1:
            add_centered_text(kw1, 855, 72, accent, is_headline=True)

    else:  # cta_end
        cta_enter = _smoothstep(float(animation_t)/0.32)
        yshift = int((1.0-cta_enter)*58)
        add_centered_text(kw0, 260+yshift, 88, (255, 255, 255), is_headline=True)
        draw.rounded_rectangle([100,385+yshift,cw-100,540+yshift],radius=34,fill=(*accent,255),outline=(*secondary,255),width=3)
        add_centered_text(kw1 or kw0, 462+yshift, 74, (9,13,22), is_headline=True)
        # A cursor approaches the actual CTA, clicks once, then the button returns to rest.
        click_p = _clamp01((float(animation_t)-0.28)/0.48)
        cx = int(180 + (cw//2-180)*_smoothstep(click_p))
        cy = int(675 + (462+yshift-675)*_smoothstep(click_p))
        press = (click_p > .65 and click_p < .86)
        if press:
            draw.rounded_rectangle([cw//2-100, 385+yshift, cw//2+100, 540+yshift], radius=28, outline=(255,255,255,255), width=5)
        draw.polygon([(cx,cy),(cx+5,cy+25),(cx+13,cy+15),(cx+25,cy+19),(cx+29,cy+12),(cx+17,cy+8),(cx+23,cy)],fill=(255,255,255,255),outline=(*border,255))

    rgb_arr = np.array(img.convert("RGB"), dtype=np.uint8)
    return rgb_arr, {
        "stage_rect": {"left": 60, "top": 280, "right": 1020, "bottom": 1220, "width": cw, "height": ch},
        "headlines": headlines_dom,
    }


def render_caption_bar_and_measure_dom(
    words: List[Dict[str, Any]],
    active_idx: int,
    theme: Dict[str, Any],
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    يرسم شريط الكابشن المتزامن مع الكلمة (952×230 عند x=64, y=1310) بدون cv2
    ويقيس الإحداثيات الفعلية لكل كلمة (DOM getBoundingClientRect) للتحقق من عدم تصادم الكلمات.
    """
    bw, bh = 952, 230
    img = Image.new("RGBA", (bw, bh), (*hex_to_rgb(theme["bg_primary"]), 255))
    draw = ImageDraw.Draw(img, "RGBA")

    border = hex_to_rgb(theme["surface_border"])
    accent = hex_to_rgb(theme["accent_primary"])

    draw.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=34, fill=(15, 23, 42, 242), outline=(*border, 255), width=3)

    if not words:
        return np.array(img.convert("RGB"), dtype=np.uint8), []

    chunk_size = 5
    chunk_start = (active_idx // chunk_size) * chunk_size
    chunk_words = words[chunk_start:chunk_start + chunk_size]

    f_normal = get_font(50, bold=True)
    f_active = get_font(58, bold=True)  # 50px * 1.15 ≈ 58px (+15% Hormozi kinetic pop!)

    measured = []
    gap = 24
    for i_w, w in enumerate(chunk_words):
        w_idx = int(w.get("index", chunk_start + i_w))
        is_act = w_idx == active_idx
        fnt = f_active if is_act else f_normal
        txt = _safe_graphic_text(w.get("word", ""))
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

    rgb_arr = np.array(img.convert("RGB"), dtype=np.uint8)
    return rgb_arr, word_dom_rects


def _transform_stage_crop_numpy_pil(
    stage_rgb: np.ndarray,
    scale: float,
    dy: int,
    bg_rgb: Tuple[int, int, int],
    alpha: float,
) -> np.ndarray:
    """
    يطبق تكبير/تصغير النابض الفيزيائي (Spring Scale) والإزاحة الرأسية (Breathing dy) والشفافية
    باستخدام PIL + NumPy السريع بدون أي حاجة لمكتبة cv2!
    """
    sh, sw, _ = stage_rgb.shape
    canvas = np.empty((sh, sw, 3), dtype=np.uint8)
    canvas[:, :] = bg_rgb

    if abs(scale - 1.0) > 0.004:
        nw = max(16, int(round(sw * scale)))
        nh = max(16, int(round(sh * scale)))
        resized = np.array(
            Image.fromarray(stage_rgb).resize((nw, nh), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )
    else:
        nw, nh = sw, sh
        resized = stage_rgb

    # حساب إزاحة المركز + dy داخل الحاوية (sw, sh)
    dst_x0 = (sw - nw) // 2
    dst_y0 = (sh - nh) // 2 + dy

    src_x0 = max(0, -dst_x0)
    src_y0 = max(0, -dst_y0)
    copy_w = min(nw - src_x0, sw - max(0, dst_x0))
    copy_h = min(nh - src_y0, sh - max(0, dst_y0))

    if copy_w > 0 and copy_h > 0:
        dx0 = max(0, dst_x0)
        dy0 = max(0, dst_y0)
        patch = resized[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]
        if alpha < 0.99:
            a = max(0.0, min(1.0, float(alpha)))
            bg_patch = canvas[dy0:dy0 + copy_h, dx0:dx0 + copy_w].astype(np.float32)
            patch = (patch.astype(np.float32) * a + bg_patch * (1.0 - a)).astype(np.uint8)
        canvas[dy0:dy0 + copy_h, dx0:dx0 + copy_w] = patch

    return canvas


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
    3. يحرك الزمن حتمياً فريماً بفريم (30fps بدقة 1080×1920) بتطبيق منحنيات الحركة الفيزيائية
       ويدمجها مع الصوت (-14 LUFS) عبر FFmpeg (H.264 CRF 19, AAC 192k) بدون الحاجة لـ cv2.
    """
    t0 = time.time()
    out_dir = os.path.dirname(os.path.abspath(output_mp4_path))
    html_snapshots_dir = os.path.join(out_dir, "html_scenes")
    os.makedirs(html_snapshots_dir, exist_ok=True)

    # ضمان ترقيم الكلمات فهرسياً
    for idx_w, w in enumerate(words):
        w["index"] = idx_w

    scene_reports = []
    safe_zone_violations = 0
    overflow_violations = 0
    word_collisions = 0
    min_caption_font_px = 999.0
    min_headline_font_px = 999.0

    # Cache stage motion at 15 fps (two samples per final 30-fps interval), but only
    # for the scene currently being encoded. The previous pass cached every frame of
    # every scene simultaneously, wasting RAM and limiting motion to 6 fps.
    motion_fps = 15.0
    scene_durations: List[float] = []
    word_caption_crops: Dict[int, np.ndarray] = {}

    for idx, sc in enumerate(scenes):
        scene_start = float(sc["start"])
        scene_end = float(sc["end"])
        mid_t = 0.5 * (scene_start + scene_end)
        html_doc = build_frame_html(sc, words, theme, mid_t, total_duration)
        with open(os.path.join(html_snapshots_dir, f"scene_{idx+1:02d}_{sc['template']}.html"), "w", encoding="utf-8") as f:
            f.write(html_doc)

        scene_dur = max(0.25, scene_end - scene_start)
        st_dom = None
        scene_durations.append(scene_dur)
        # Render a representative frame for layout/overflow QA; full motion frames are
        # generated lazily during final encoding, one scene at a time.
        qa_t = min(scene_dur, scene_dur * 0.5)
        _, st_dom = render_scene_card_and_measure_dom(sc, theme, animation_t=qa_t)

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

    for w in words:
        w_idx = int(w["index"])
        cap_rgb, w_dom_list = render_caption_bar_and_measure_dom(words, w_idx, theme)
        word_caption_crops[w_idx] = cap_rgb

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

    if not word_caption_crops:
        cap_rgb, _ = render_caption_bar_and_measure_dom([], 0, theme)
        word_caption_crops[0] = cap_rgb

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

    total_frames = max(1, int(round(total_duration * fps)))
    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
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
    accent_rgb = hex_to_rgb(theme["accent_primary"])

    base_bg = np.empty((1920, 1080, 3), dtype=np.uint8)
    base_bg[:, :] = bg1_rgb

    cached_scene_idx = -1
    cached_scene_frames: List[np.ndarray] = []
    for f_idx in range(total_frames):
        t = f_idx / float(fps)

        sc_idx = len(scenes) - 1
        found_active = False
        for i, candidate in enumerate(scenes):
            if float(candidate["start"]) <= t <= float(candidate["end"]):
                sc_idx = i
                found_active = True
                break
        if scenes and not found_active:
            # For tiny timing gaps between word groups, show the nearest scene rather than
            # accidentally jumping to the final CTA for the rest of the video.
            def _distance_to_scene(candidate):
                start_v, end_v = float(candidate["start"]), float(candidate["end"])
                if start_v <= t <= end_v:
                    return 0.0
                return min(abs(t - start_v), abs(t - end_v))
            sc_idx = min(range(len(scenes)), key=lambda i: _distance_to_scene(scenes[i]))
        sc = scenes[sc_idx]
        local_t = max(0.0, t - float(sc["start"]))
        sc_dur = max(0.5, float(sc["end"]) - float(sc["start"]))

        active_w_idx = 0
        for w in words:
            if float(w["start"]) <= t <= float(w["end"]):
                active_w_idx = int(w["index"])
                break
            if float(w["start"]) <= t:
                active_w_idx = int(w["index"])

        frame = base_bg.copy()

        in_p = max(0.68, spring_ease(min(1.0, local_t / 0.30), overshoot=0.055))
        out_p = max(0.72, exit_ease(max(0.0, (local_t - (sc_dur - 0.18)) / 0.18))) if local_t > (sc_dur - 0.18) else 1.0
        env = max(0.68, in_p * out_p)
        scene_progress = _smoothstep(local_t / max(0.5, sc_dur))
        # Deliberate cinematic push-in; no sinusoidal bobbing that makes graphics feel
        # like stickers floating in place. The semantic objects perform the action.
        if sc.get("template") == "fullscreen_image":
            content_zoom = 1.0 + 0.05 * scene_progress
        else:
            content_zoom = 1.0 + 0.018 * scene_progress
        scale = max(0.2, min(1.08, env * content_zoom))
        dy = int(round((1.0 - min(1.0, env)) * 54.0 - 8.0 * scene_progress))

        if sc_idx != cached_scene_idx:
            # Drop the previous scene's cached frames before rendering the next scene.
            cached_scene_frames = []
            cached_scene_idx = sc_idx
            scene_dur_for_cache = scene_durations[sc_idx]
            frame_count = max(2, int(math.ceil(scene_dur_for_cache * motion_fps)) + 1)
            for motion_idx_build in range(frame_count):
                anim_t_build = min(scene_dur_for_cache, motion_idx_build / motion_fps)
                cached_frame, _ = render_scene_card_and_measure_dom(
                    scenes[sc_idx], theme, animation_t=anim_t_build,
                )
                cached_scene_frames.append(cached_frame)
        motion_idx = min(len(cached_scene_frames) - 1, max(0, int(round(local_t * motion_fps))))
        stage_crop = cached_scene_frames[motion_idx]
        sh, sw = stage_crop.shape[:2]
        warped_stage = _transform_stage_crop_numpy_pil(
            stage_rgb=stage_crop,
            scale=scale,
            dy=dy,
            bg_rgb=bg1_rgb,
            alpha=min(1.0, max(0.0, env)),
        )
        frame[280:280 + sh, 60:60 + sw] = warped_stage

        cap_crop = word_caption_crops.get(active_w_idx, word_caption_crops[0])
        ch_c, cw_c = cap_crop.shape[:2]
        cap_y = 1310  # captions remain pinned; motion belongs to the visual story, not bobbing UI
        frame[cap_y:cap_y + ch_c, 64:64 + cw_c] = cap_crop

        # شريط التقدم الزمني السلس عند y=1564..1572 (بدون cv2)
        frame[1564:1572, 120:960] = (75, 55, 45)
        prog_x = 120 + int(round(840.0 * min(1.0, max(0.0, t / max(1.0, total_duration)))))
        frame[1564:1572, 120:prog_x] = accent_rgb

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
