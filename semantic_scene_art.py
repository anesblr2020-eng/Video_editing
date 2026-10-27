# -*- coding: utf-8 -*-
"""Low-cost semantic editorial scene illustrations used when image generation is unavailable.

These are contextual illustrated environments, not claims of AI-generated or photorealistic images.
They are deliberately full-frame compositions (environment + subject + props + depth) rather than a
single centered icon. The caller should record their use as a programmatic fallback.
"""
from __future__ import annotations

import hashlib
import math
import numpy as np
from typing import Any, Dict, Tuple
from PIL import Image, ImageDraw, ImageFilter


def _text(meta: Dict[str, Any]) -> str:
    parts = [meta.get(k, "") for k in ("speech", "text", "clause_a", "clause_b", "concept_title", "visual_query", "visual_subject", "archetype", "intent")]
    parts.extend(meta.get("keywords", []) if isinstance(meta.get("keywords"), list) else [])
    return " ".join(str(x) for x in parts if x).lower()


def _category(meta: Dict[str, Any]) -> str:
    s = _text(meta)
    groups = {
        "delivery": ("توصيل", "شحن", "طرد", "طلبية", "طلبات", "delivery", "package", "parcel", "shipping", "store order"),
        "creator": ("مونتاج", "فيديو", "صانع محتوى", "كاميرا", "ريلز", "creator", "editing", "video", "content", "camera"),
        "social": ("انستغرام", "إنستغرام", "انستجرام", "مشاهدات", "متابع", "تفاعل", "social", "instagram", "followers", "engagement"),
        "audio": ("صوت", "صوتية", "مايك", "ميكروفون", "تسجيل", "بودكاست", "audio", "microphone", "recording", "podcast"),
        "health": ("مريض", "طبي", "صحة", "تشخيص", "مستشفى", "طبيب", "health", "patient", "medical", "diagnosis"),
        "commerce": ("متجر", "زبون", "عميل", "بيع", "شراء", "منتج", "تجارة", "shop", "customer", "sales", "product", "commerce"),
        "ai": ("ذكاء اصطناعي", "الذكاء", "اصطناعي", "نموذج", "أتمتة", "ai", "artificial intelligence", "automation", "neural"),
        "finance": ("مال", "دينار", "سعر", "ربح", "خسارة", "استثمار", "finance", "money", "price", "profit", "investment"),
        "learning": ("تعلم", "درس", "شرح", "مدرسة", "جامعة", "بحث", "كتاب", "learn", "education", "research", "study"),
    }
    for category, words in groups.items():
        if any(word in s for word in words):
            return category
    return "workspace"


def _gradient(size: Tuple[int, int], top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    w, h = size
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)
    t = t * t * (3.0 - 2.0 * t)  # eased gradient, no harsh banding
    top_arr = np.asarray(top, dtype=np.float32)[None, None, :]
    bottom_arr = np.asarray(bottom, dtype=np.float32)[None, None, :]
    blend = top_arr * (1.0 - t[:, None, None]) + bottom_arr * t[:, None, None]
    pixels = np.repeat(np.clip(blend, 0, 255).astype(np.uint8), w, axis=1)
    return Image.fromarray(pixels, mode="RGB")


def _shadow(draw: ImageDraw.ImageDraw, box, radius=30, fill=(12, 24, 44, 70), offset=(0, 24)):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]), radius=radius, fill=fill)


def _person(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, shirt, pants, skin=(196, 139, 104)):
    """Draw a seated/standing stylized person with a torso, head, limbs and hands."""
    r = int(72 * scale)
    draw.ellipse((x-r, y-r, x+r, y+r), fill=skin, outline=(255, 255, 255, 100), width=max(2, int(4*scale)))
    # Hair and neck
    draw.pieslice((x-r-5, y-r-10, x+r+5, y+r), 180, 355, fill=(35, 37, 48, 255))
    draw.rounded_rectangle((x-int(28*scale), y+int(45*scale), x+int(28*scale), y+int(100*scale)), radius=int(16*scale), fill=skin)
    # Torso
    bx0, by0, bx1, by1 = x-int(120*scale), y+int(85*scale), x+int(120*scale), y+int(390*scale)
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=int(60*scale), fill=shirt)
    # Arms and hands
    draw.line((bx0+int(20*scale), by0+int(60*scale), x-int(180*scale), y+int(270*scale)), fill=shirt, width=int(62*scale))
    draw.ellipse((x-int(205*scale), y+int(245*scale), x-int(160*scale), y+int(295*scale)), fill=skin)
    draw.line((bx1-int(20*scale), by0+int(60*scale), x+int(165*scale), y+int(250*scale)), fill=shirt, width=int(62*scale))
    draw.ellipse((x+int(145*scale), y+int(225*scale), x+int(195*scale), y+int(275*scale)), fill=skin)
    # Legs
    draw.rounded_rectangle((x-int(95*scale), by1-int(15*scale), x-int(12*scale), by1+int(210*scale)), radius=int(32*scale), fill=pants)
    draw.rounded_rectangle((x+int(12*scale), by1-int(15*scale), x+int(95*scale), by1+int(210*scale)), radius=int(32*scale), fill=pants)
    draw.rounded_rectangle((x-int(125*scale), by1+int(175*scale), x-int(2*scale), by1+int(235*scale)), radius=int(24*scale), fill=(33, 43, 59, 255))
    draw.rounded_rectangle((x+int(2*scale), by1+int(175*scale), x+int(125*scale), by1+int(235*scale)), radius=int(24*scale), fill=(33, 43, 59, 255))


def _plant(draw, x, y, scale=1.0):
    draw.rounded_rectangle((x-int(45*scale), y, x+int(45*scale), y+int(105*scale)), radius=int(18*scale), fill=(190, 113, 75, 255))
    draw.line((x, y+10, x, y-int(190*scale)), fill=(43, 104, 77, 255), width=int(14*scale))
    for dx, dy, flip in [(-65,-95,-1),(55,-140,1),(-48,-170,-1),(70,-65,1)]:
        x0 = x + dx * scale
        x1 = x + (dx + flip * 85) * scale
        y0 = y + (dy - 35) * scale
        y1 = y + (dy + 45) * scale
        leaf = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        draw.ellipse(tuple(int(v) for v in leaf), fill=(52, 137, 98, 255))


def _phone(draw, x, y, scale=1.0, accent=(79, 104, 235)):
    w, h = int(150*scale), int(300*scale)
    _shadow(draw, (x-w//2, y-h//2, x+w//2, y+h//2), radius=int(24*scale), offset=(0,int(18*scale)))
    draw.rounded_rectangle((x-w//2, y-h//2, x+w//2, y+h//2), radius=int(24*scale), fill=(26, 34, 52, 255), outline=(225, 232, 245, 255), width=max(3,int(6*scale)))
    draw.rounded_rectangle((x-w//2+12, y-h//2+18, x+w//2-12, y+h//2-18), radius=int(15*scale), fill=(242, 246, 252, 255))
    for i, col in enumerate((accent, (52, 181, 145), (244, 167, 63))):
        yy = y-h//2+int((65+i*70)*scale)
        draw.rounded_rectangle((x-w//2+int(24*scale), yy, x+w//2-int(24*scale), yy+int(35*scale)), radius=int(10*scale), fill=(*col,255))
    draw.ellipse((x-int(8*scale), y+h//2-int(13*scale), x+int(8*scale), y+h//2+int(3*scale)), fill=(110, 123, 145, 255))


def _laptop(draw, x, y, scale=1.0, accent=(79, 104, 235)):
    w, h = int(420*scale), int(270*scale)
    _shadow(draw, (x-w//2, y-h, x+w//2, y), radius=int(20*scale), offset=(0,int(20*scale)))
    draw.rounded_rectangle((x-w//2, y-h, x+w//2, y), radius=int(24*scale), fill=(43, 53, 73, 255), outline=(204, 215, 231, 255), width=max(3,int(5*scale)))
    draw.rounded_rectangle((x-w//2+18, y-h+18, x+w//2-18, y-18), radius=int(12*scale), fill=(226, 236, 249, 255))
    draw.rounded_rectangle((x-w//2+45, y-h+50, x+w//2-45, y-h+82), radius=int(8*scale), fill=(*accent,255))
    for i in range(3):
        yy=y-h+112+i*34
        draw.rounded_rectangle((x-w//2+45,yy,x+w//2-int((110+i*35)*scale),yy+12),radius=5,fill=(153,170,194,255))
    draw.polygon([(x-w//2-30,y),(x+w//2+30,y),(x+w//2+85,y+45),(x-w//2-85,y+45)], fill=(183, 195, 213, 255))
    draw.line((x-w//2-30,y,x+w//2+30,y), fill=(242,246,252,255), width=max(3,int(5*scale)))


def _boxes(draw, x, y, scale=1.0, accent=(215, 150, 89)):
    # Two perspective parcels, tape and folded edges.
    w, h = int(260*scale), int(235*scale)
    draw.polygon([(x-w//2,y-h),(x+w//2,y-h+int(35*scale)),(x+w//2,y+int(5*scale)),(x-w//2,y-int(30*scale))], fill=(204,148,93,255))
    draw.polygon([(x-w//2,y-h),(x,y-h-int(45*scale)),(x+w//2,y-h+int(35*scale)),(x,y-h+int(70*scale))], fill=(235,187,128,255))
    draw.polygon([(x,y-h+int(70*scale)),(x+w//2,y-h+int(35*scale)),(x+w//2,y+int(5*scale)),(x,y+int(65*scale))], fill=(169,111,66,255))
    draw.polygon([(x-w//2,y-h),(x,y-h-int(45*scale)),(x,y-h+int(20*scale)),(x-w//2,y-h+int(55*scale))], fill=(220,165,108,255))
    draw.polygon([(x-int(28*scale),y-h-int(25*scale)),(x+int(20*scale),y-h-int(5*scale)),(x+int(20*scale),y+int(40*scale)),(x-int(28*scale),y+int(15*scale))], fill=(*accent,255))


def build_semantic_scene_art(meta: Dict[str, Any], width: int = 1080, height: int = 1920) -> Image.Image:
    """Return a full-frame contextual illustration for a scene, deterministic for stable rerenders."""
    text = _text(meta)
    category = _category(meta)
    seed = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)
    # Palette by subject, with subtle per-scene variation while preserving a coherent look.
    palettes = {
        "delivery": ((244, 231, 210), (203, 219, 230), (50, 94, 123), (232, 151, 68)),
        "creator": ((227, 237, 246), (179, 201, 220), (54, 78, 113), (91, 104, 231)),
        "social": ((246, 226, 235), (210, 205, 241), (101, 69, 133), (226, 93, 133)),
        "audio": ((222, 230, 239), (157, 177, 201), (39, 51, 76), (77, 126, 177)),
        "health": ((224, 242, 238), (183, 220, 220), (45, 91, 95), (37, 164, 135)),
        "commerce": ((247, 235, 215), (227, 203, 164), (99, 69, 48), (224, 142, 59)),
        "ai": ((224, 235, 249), (186, 199, 238), (42, 57, 101), (93, 104, 234)),
        "finance": ((223, 238, 228), (175, 211, 191), (37, 79, 65), (46, 150, 112)),
        "learning": ((242, 234, 217), (210, 219, 229), (65, 77, 99), (219, 151, 63)),
        "workspace": ((232, 239, 246), (192, 207, 220), (49, 67, 92), (91, 111, 226)),
    }
    top, bottom, ink, accent = palettes[category]
    # Tiny deterministic palette variation avoids every fallback feeling identical.
    variation = (seed % 9) - 4
    top = tuple(max(0, min(255, c + variation)) for c in top)
    im = _gradient((width, height), top, bottom).convert("RGBA")
    d = ImageDraw.Draw(im, "RGBA")
    # Ambient light and architectural depth.
    d.ellipse((int(width*.48), int(height*.05), int(width*1.2), int(height*.42)), fill=(*accent, 30))
    d.rectangle((0, int(height*.58), width, height), fill=(39, 53, 74, 38))
    # Large window with soft mullions; background is an environment, not an isolated symbol.
    win=(int(width*.08), int(height*.08), int(width*.72), int(height*.46))
    _shadow(d, win, radius=22, fill=(28,43,63,35), offset=(0,16))
    d.rounded_rectangle(win, radius=22, fill=(215,235,247,145), outline=(255,255,255,190), width=8)
    wx0,wy0,wx1,wy1=win
    d.line((int((wx0+wx1)/2),wy0,int((wx0+wx1)/2),wy1),fill=(255,255,255,165),width=8)
    d.line((wx0,int((wy0+wy1)/2),wx1,int((wy0+wy1)/2)),fill=(255,255,255,140),width=8)
    # Distant building silhouettes through the window.
    for i in range(7):
        bw=int(width*(.045+(i%3)*.012)); bx=int(width*(.10+i*.083)); by=int(height*(.30+(i%4)*.022))
        d.rectangle((bx,by,bx+bw,int(height*.46)),fill=(*ink,22))
    # Floor and perspective seam lines.
    floor_y=int(height*.70)
    d.polygon([(0,floor_y),(width,floor_y-int(height*.04)),(width,height),(0,height)], fill=(ink[0],ink[1],ink[2],28))
    for i in range(1,7):
        xx=int(width*i/7)
        d.line((width//2,floor_y,xx,height),fill=(255,255,255,28),width=3)
    d.line((0,floor_y,width,floor_y-int(height*.04)),fill=(255,255,255,70),width=5)
    # Scene-specific props and subject placement.
    if category == "delivery":
        _boxes(d, int(width*.72), int(height*.73), .95, accent)
        _boxes(d, int(width*.82), int(height*.84), .55, (195,127,74))
        _person(d, int(width*.34), int(height*.43), .66, (65,117,151,255), (55,68,91,255))
        # counter / handoff table
        d.rounded_rectangle((int(width*.08),int(height*.65),int(width*.58),int(height*.69)),radius=18,fill=(90,112,132,220))
        d.rectangle((int(width*.12),int(height*.68),int(width*.16),int(height*.84)),fill=(74,91,110,220))
        d.rectangle((int(width*.50),int(height*.68),int(width*.54),int(height*.84)),fill=(74,91,110,220))
    elif category in ("creator", "social", "commerce", "finance", "learning", "workspace", "health"):
        shirt = (71, 107, 171, 255) if category not in ("health", "finance") else ((53,145,126,255) if category=="health" else (42,124,91,255))
        pants = (54, 67, 91, 255)
        _person(d, int(width*.30), int(height*.40), .62, shirt, pants)
        # desk runs across the composition to establish a real workspace.
        desk_y=int(height*.66)
        d.polygon([(int(width*.05),desk_y),(int(width*.83),desk_y-int(height*.018)),(int(width*.96),desk_y+int(height*.055)),(int(width*.13),desk_y+int(height*.075))],fill=(125,91,70,245))
        d.rectangle((int(width*.15),desk_y+int(height*.055),int(width*.19),desk_y+int(height*.20)),fill=(91,70,59,235))
        d.rectangle((int(width*.78),desk_y+int(height*.045),int(width*.82),desk_y+int(height*.20)),fill=(91,70,59,235))
        _laptop(d, int(width*.56), desk_y-int(height*.01), .72, accent)
        _plant(d, int(width*.87), int(height*.63), .62)
        if category == "social":
            _phone(d, int(width*.78), int(height*.49), .72, accent)
            # floating notification tiles as environmental details, not the main scene.
            for i,col in enumerate(((232,92,130),(92,115,234),(52,177,142))):
                x=int(width*(.70+(i%2)*.11)); y=int(height*(.20+i*.075))
                d.rounded_rectangle((x,y,x+95,y+66),radius=20,fill=(*col,205),outline=(255,255,255,180),width=3)
                d.ellipse((x+18,y+17,x+46,y+45),fill=(255,255,255,225))
        elif category == "health":
            # medical monitor and chart in the room
            d.rounded_rectangle((int(width*.67),int(height*.18),int(width*.91),int(height*.36)),radius=20,fill=(245,252,251,230),outline=(255,255,255,255),width=5)
            d.line([(int(width*.69),int(height*.28)),(int(width*.73),int(height*.28)),(int(width*.76),int(height*.23)),(int(width*.80),int(height*.32)),(int(width*.84),int(height*.25)),(int(width*.89),int(height*.25))],fill=(*accent,255),width=7)
        elif category == "learning":
            for i in range(4):
                bx=int(width*(.70+i*.045)); by=int(height*.50)
                d.rounded_rectangle((bx,by-int(height*.13),bx+int(width*.04),by),radius=6,fill=(235-i*13,190-i*8,115+i*8,240))
        elif category == "commerce":
            _boxes(d, int(width*.82), int(height*.55), .47, accent)
        elif category == "finance":
            # coin stack on the desk
            for i in range(5):
                yy=int(height*.64)-i*18
                d.ellipse((int(width*.78),yy,int(width*.90),yy+34),fill=(226,181,73,240),outline=(255,239,177,240),width=3)
    elif category == "audio":
        _person(d, int(width*.31), int(height*.43), .62, (51,67,94,255), (39,48,68,255))
        # acoustic panels and microphone boom
        for i in range(5):
            x=int(width*(.61+i*.065))
            d.rounded_rectangle((x,int(height*.15),x+int(width*.045),int(height*.43)),radius=10,fill=(39,52,75,95))
        d.line((int(width*.66),int(height*.37),int(width*.75),int(height*.29),int(width*.82),int(height*.33)),fill=(*ink,255),width=15)
        d.rounded_rectangle((int(width*.79),int(height*.28),int(width*.86),int(height*.42)),radius=28,fill=(34,45,63,255),outline=(228,235,245,255),width=5)
        for i in range(5):
            yy=int(height*(.31+i*.018))
            d.line((int(width*.80),yy,int(width*.85),yy),fill=(135,154,180,230),width=3)
        d.ellipse((int(width*.70),int(height*.43),int(width*.95),int(height*.54)),fill=(*accent,24))
    elif category == "ai":
        _person(d, int(width*.28), int(height*.43), .58, (72,99,168,255), (47,60,87,255))
        _laptop(d, int(width*.53), int(height*.66), .72, accent)
        # layered translucent data panels at the side of the environment.
        for i in range(3):
            x=int(width*(.68+i*.025)); y=int(height*(.19+i*.11))
            d.rounded_rectangle((x,y,x+int(width*.21),y+int(height*.095)),radius=18,fill=(246,249,255,155),outline=(*accent,95),width=3)
            for j in range(3):
                yy=y+int(height*(.025+j*.02))
                d.rounded_rectangle((x+18,yy,x+int(width*(.10+j*.015)),yy+8),radius=4,fill=(*ink,100))
    # Atmospheric grain-like dots, deliberately sparse.
    for i in range(24):
        x=(seed*(i+13)+i*173) % width
        y=(seed//(i+3)+i*257) % height
        r=2+(i%4)
        d.ellipse((x-r,y-r,x+r,y+r),fill=(255,255,255,20+(i%4)*6))
    # Subtle vignette to guide the eye toward the scene's center.
    vignette=Image.new("L",(width,height),0)
    vd=ImageDraw.Draw(vignette)
    vd.ellipse((-int(width*.15),-int(height*.05),int(width*1.15),int(height*1.05)),fill=210)
    vignette=vignette.filter(ImageFilter.GaussianBlur(max(12,int(width*.08))))
    dark=Image.new("RGBA",(width,height),(15,25,42,70))
    dark.putalpha(Image.eval(vignette, lambda px: 70-int(px*0.18)))
    im=Image.alpha_composite(im,dark)
    return im.convert("RGB")
