# -*- coding: utf-8 -*-
"""
stock_video_finder.py - محرك Pexels API للقطات B-Roll السياقية مع تقريب بطيء (100% -> 105%) وضبابية خفيفة (Gaussian Blur)
=============================================================================================================================
متطلبات الهندسة المعمارية (Alex Hormozi Visual Control & B-Roll Engine):
1. ربط النظام بواجهة `Pexels API` لسحب لقطات فيديو فعلية (`B-Roll`) تتناسب مباشرة مع الكلمات المفتاحية للجملة المنطوقة
   (`search_query` أو الكلمات المفتاحية العربية/الدارجة المترجمة آلياً إلى استعلامات Pexels دقيقة).
2. تطبيق تأثير تقريب بطيء (`Slow Zoom-in` من `100%` إلى `105%`) مع ضبابية خفيفة (`Gaussian Blur`) وتعتيم سينمائي مدروس
   على خلفية الـ B-Roll عبر دالة `apply_hormozi_broll_slow_zoom_and_blur` لإبراز النصوص والأيقونات الأمامية بوضوح فائق.
3. تغيير المشهد أو الزاوية البصرية كل `2.5` إلى `3` ثوانٍ لكسر الملل (Visual Pacing).
"""

import sys
import os
import gc
import ctypes
import subprocess

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import re
import time
import math
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

# تعطيل استيراد cv2 تماماً والاعتماد على PIL + NumPy السريع لمنع تعليق fork/subprocess في الحاويات السحابية
cv2 = None
_HAS_CV2 = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _free_ram():
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


CURATED_DIRECT_STOCK_VIDEOS = {
    'ecommerce_showcase': [
        'https://assets.mixkit.co/videos/preview/mixkit-hands-holding-a-smartphone-with-a-blank-screen-41719-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-typing-on-a-laptop-keyboard-41315-large.mp4'
    ],
    'delivery_express': [
        'https://assets.mixkit.co/videos/preview/mixkit-young-man-using-a-smartphone-in-the-city-43180-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-hands-holding-a-smartphone-with-a-blank-screen-41719-large.mp4'
    ],
    'video_editor': [
        'https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-working-on-a-computer-43407-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-typing-on-a-laptop-keyboard-41315-large.mp4'
    ],
    'ai_technology': [
        'https://assets.mixkit.co/videos/preview/mixkit-digital-animation-of-screens-with-data-41526-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-network-connections-and-technology-screens-41524-large.mp4'
    ],
    'busy_no_time': [
        'https://assets.mixkit.co/videos/preview/mixkit-sand-flowing-through-an-hourglass-42861-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-tired-man-rubbing-his-eyes-at-work-43405-large.mp4'
    ],
    'smartphone_reels': [
        'https://assets.mixkit.co/videos/preview/mixkit-young-man-using-a-smartphone-in-the-city-43180-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-holding-a-smartphone-with-a-green-screen-41719-large.mp4'
    ],
    'developer_coding': [
        'https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-typing-on-a-laptop-keyboard-41315-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-man-working-on-a-desktop-computer-43408-large.mp4'
    ],
    'creator_studio': [
        'https://assets.mixkit.co/videos/preview/mixkit-man-working-with-headphones-on-in-an-office-43411-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-young-man-using-a-smartphone-in-the-city-43180-large.mp4'
    ]
}


# قاموس تحويل الكلمات المفتاحية العربية والدارجة إلى استعلامات Pexels API إنجليزية دقيقة
ARABIC_KEYWORD_TO_PEXELS_QUERY: List[Tuple[Tuple[str, ...], str]] = [
    (("يمونتي", "نيمونتي", "تمونتي", "مونتاج", "تعديل فيديو", "بريمير", "كاب كات", "فيديو"), "video editing timeline computer studio"),
    (("ما عندوش وقت", "ماعندوش وقت", "ما عندها وقت", "وقت", "ساعة", "مشغول", "تأخير", "سرعة"), "hourglass clock time lapse busy working"),
    (("ذكاء اصطناعي", "ذكاء", "خوارزمية", "روبوت", "أوتوماتيكي", "تلقائي", "نظام"), "artificial intelligence neural network technology"),
    (("منصة", "تطبيق", "موقع", "كود", "برمجة", "سيرفر", "تطوير"), "software developer coding laptop screen"),
    (("ريلز", "تيك توك", "شورتس", "انستغرام", "سوشيال ميديا", "موبايل", "هاتف", "تلفون"), "person scrolling smartphone social media reels"),
    (("مشاهدات", "انتشار", "فايرل", "مبيعات", "أرباح", "نمو", "نتائج", "إحصائيات"), "business analytics growth chart screen"),
    (("صانع محتوى", "محتوى", "مايكروفون", "كاميرا", "تصوير", "تسجيل", "استوديو"), "content creator recording microphone studio"),
    (("توصيل", "شحن", "طلبية", "منتج", "سلعة", "شراء", "متجر"), "ecommerce package delivery courier"),
]


def build_pexels_query_from_scene_keywords(
    scene_text: str = "",
    concept_title: str = "",
    kpi_value: str = "",
    category: str = "video_editor"
) -> str:
    """
    يبني استعلام بحث `Pexels API` دقيق باللغة الإنجليزية من الكلمات المفتاحية التي عدلها المستخدم
    (`kpi_value`, `concept_title`) أو من الكلام المنطوق في المشهد (`scene_text`).
    """
    combined = f"{kpi_value} {concept_title} {scene_text}".strip().lower()

    # إذا كتب المستخدم كلمات إنجليزية مباشرة في الكلمات المفتاحية، نستخدمها فوراً
    en_tokens = re.findall(r"[a-zA-Z]{3,}", f"{kpi_value} {concept_title}")
    if len(en_tokens) >= 2:
        return " ".join(en_tokens[:5])

    matched_queries: List[str] = []
    for kw_tuple, pexels_q in ARABIC_KEYWORD_TO_PEXELS_QUERY:
        if any(kw in combined for kw in kw_tuple):
            matched_queries.append(pexels_q)
            if len(matched_queries) >= 2:
                break

    if matched_queries:
        return matched_queries[0]

    query_map = {
        'ecommerce_showcase': 'charging cable phone accessories ecommerce',
        'delivery_express': 'delivery courier package box',
        'video_editor': 'video editing computer timeline studio',
        'ai_technology': 'artificial intelligence technology abstract screen',
        'busy_no_time': 'time lapse clock hourglass busy work',
        'smartphone_reels': 'person using smartphone social media',
        'developer_coding': 'developer coding keyboard dark screen',
        'creator_studio': 'content creator microphone studio desk'
    }
    return query_map.get(category.lower(), 'video editing computer creator studio')


def map_scene_to_stock_category(scene_type: str, scene_text: str) -> str:
    t = (scene_text or "").lower()
    if any(w in t for w in ('يمونتي', 'نيمونتي', 'تمونتي', 'مونتاج', 'تعديل', 'قص', 'فيديو', 'محرر')):
        return 'video_editor'
    if any(w in t for w in ('وقت', 'ساعة', 'ما عندها وقت', 'ما عندوش وقت', 'ماعندوش وقت', 'مشغول', 'ساعات', 'تأخير')):
        return 'busy_no_time'
    if any(w in t for w in ('ذكاء', 'اصطناعي', 'خوارزمية', 'أوتوماتيكي', 'ai', 'neural')):
        return 'ai_technology'
    if any(w in t for w in ('كابل', 'شاحن', 'سيبور', 'منتج', 'سلعة', 'توصيل', 'شراء', 'تشارجي')):
        return 'ecommerce_showcase'
    if any(w in t for w in ('انستغرام', 'انستقرام', 'ريلز', 'تيك توك', 'شورتس', 'سوشيال', 'هاتف', 'تلفون', 'موبايل', 'smartphone')):
        return 'smartphone_reels'
    if any(w in t for w in ('كود', 'برمجة', 'أبني', 'تطبيق', 'موقع', 'منصة', 'developer', 'code')):
        return 'developer_coding'
    if any(w in t for w in ('استوديو', 'صانع محتوى', 'مبدع', 'كاميرا', 'تسجيل', 'ميكروفون', 'creator')):
        return 'creator_studio'

    type_map = {
        'ecommerce_showcase': 'ecommerce_showcase',
        'delivery_express': 'delivery_express',
        'time_warp_clock': 'busy_no_time',
        'ai_neural_brain': 'ai_technology',
        'cloud_database': 'ai_technology',
        'reels_smartphone': 'smartphone_reels',
        'platform_builder': 'developer_coding',
        'creator_profile': 'creator_studio',
        'age_number_counter': 'creator_studio',
        'brand_finale': 'creator_studio',
        'video_montage_studio': 'video_editor',
        'audio_waveform': 'video_editor',
        'growth_analytics': 'developer_coding'
    }
    if scene_type in type_map:
        return type_map[scene_type]
    return 'video_editor'


def apply_hormozi_broll_slow_zoom_and_blur(
    frame_rgb: np.ndarray,
    scene_progress: float,
    target_w: int,
    target_h: int,
    start_zoom: float = 1.00,
    end_zoom: float = 1.05,
    gaussian_sigma: float = 2.2,
    darken_factor: float = 0.82
) -> np.ndarray:
    """
    تطبيق معالجة الخلفية السينمائية بأسلوب (Alex Hormozi B-Roll Treatment):
    1. تقريب بطيء ومستمر (`Slow Zoom-in` من `100%` إلى `105%`) طوال مدة المشهد (`scene_progress` من `0.0` إلى `1.0`).
    2. ضبابية غاوسية خفيفة (`Subtle Gaussian Blur`) لفصل خلفية الـ B-Roll عن النصوص والأيقونات الأمامية.
    3. تعتيم سينمائي خفيف (`darken_factor=0.82`) لإبراز النص الأصفر/الأخضر الفاقع والأيقونات بوضوح 100%.
    """
    if frame_rgb is None or frame_rgb.ndim != 3:
        return frame_rgb

    u = max(0.0, min(1.0, float(scene_progress)))
    zoom_now = float(start_zoom) + (float(end_zoom) - float(start_zoom)) * u

    fh, fw, _ = frame_rgb.shape
    cw = max(16, int(round(fw / max(1.0, zoom_now))))
    ch = max(16, int(round(fh / max(1.0, zoom_now))))
    x1 = max(0, (fw - cw) // 2)
    y1 = max(0, (fh - ch) // 2)
    cropped = frame_rgb[y1:y1 + ch, x1:x1 + cw]

    if _HAS_CV2 and cv2 is not None:
        resized = cv2.resize(cropped, (int(target_w), int(target_h)), interpolation=cv2.INTER_LINEAR)
        if gaussian_sigma > 0.2:
            ksize = max(3, int(round(gaussian_sigma * 2.5)) | 1)
            blurred = cv2.GaussianBlur(resized, (ksize, ksize), sigmaX=float(gaussian_sigma))
        else:
            blurred = resized
    else:
        pil_img = Image.fromarray(cropped).resize((int(target_w), int(target_h)), Image.Resampling.BILINEAR)
        if gaussian_sigma > 0.2:
            pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=float(gaussian_sigma)))
        blurred = np.asarray(pil_img, dtype=np.uint8)

    if 0.1 < darken_factor < 0.99:
        blurred = np.clip(blurred.astype(np.float32) * float(darken_factor), 0, 255).astype(np.uint8)

    return blurred


def download_video_file(url: str, output_path: str, timeout: int = 12) -> bool:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, stream=True, timeout=timeout)
        if resp.status_code == 200:
            max_bytes = 15 * 1024 * 1024
            written = 0
            with open(output_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=131072):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        if written > max_bytes:
                            break
            if os.path.exists(output_path) and os.path.getsize(output_path) > 40000:
                return True
    except Exception as e:
        logger.debug(f'Download failed: {e}')
    return False


def fetch_pexels_stock_video(query: str, api_key: str, cache_dir: str, orientation: str = 'portrait') -> Optional[str]:
    if not api_key:
        return None
    try:
        url = 'https://api.pexels.com/videos/search'
        headers = {'Authorization': api_key}
        params = {'query': query, 'per_page': 5, 'orientation': orientation}
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            videos = resp.json().get('videos', [])
            for vid in videos:
                files = [f for f in vid.get('video_files', []) if f.get('link') and f.get('file_type') == 'video/mp4']
                files.sort(key=lambda x: abs(int(x.get('width') or 720) - 540))
                for f_info in files:
                    link = f_info.get('link')
                    q_hash = hashlib.md5((query + link).encode()).hexdigest()[:10]
                    dest = os.path.join(cache_dir, f'pexels_{q_hash}.mp4')
                    if os.path.exists(dest) and os.path.getsize(dest) > 40000:
                        return dest
                    if download_video_file(link, dest):
                        return dest
    except Exception as e:
        logger.warning(f'Pexels API exception: {e}')
    return None


def generate_procedural_broll_clip(category: str, output_path: str, width: int = 540, height: int = 960, duration: float = 3.0) -> str:
    width = max(2, width - (width % 2))
    height = max(2, height - (height % 2))
    fps = 24
    total_frames = max(12, int(round(min(4.0, duration) * fps)))

    def make_frame(t: float) -> np.ndarray:
        img = Image.new("RGB", (width, height), (10, 16, 32))
        draw = ImageDraw.Draw(img)
        cx = width // 2
        cy = height // 2

        if category in ("developer_coding", "video_editor"):
            for row in range(10):
                ry = int(height * 0.22) + row * int(height * 0.055)
                rw = max(20, int(width * (0.35 + 0.45 * abs(math.sin(t * 3.0 + row)))))
                col = (56, 189, 248) if row % 3 == 0 else (255, 220, 0)
                draw.rounded_rectangle([(int(width * 0.12), ry), (int(width * 0.12) + rw, ry + 24)], radius=8, fill=col)
        elif category == "ai_technology":
            for i in range(12):
                ang = math.radians(i * 30.0 + t * 45)
                dr = int(min(width, height) * 0.35 * (0.8 + 0.2 * math.sin(t * 4 + i)))
                dx = cx + int(dr * math.cos(ang))
                dy = cy + int(dr * math.sin(ang))
                draw.line([(cx, cy), (dx, dy)], fill=(0, 245, 212), width=3)
                draw.ellipse([(dx - 10, dy - 10), (dx + 10, dy + 10)], fill=(255, 220, 0))
        else:
            for ring in range(4):
                rr = int(min(width, height) * (0.18 + ring * 0.10 + 0.03 * math.sin(t * 4 + ring)))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(255, 220, 0), width=4)

        return np.array(img, dtype=np.uint8)

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-threads", "1",
        "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-x264-params", "rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0",
        "-crf", "25", "-pix_fmt", "yuv420p", "-threads", "1",
        output_path
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for fi in range(total_frames):
            frm = make_frame(fi / float(fps))
            proc.stdin.write(frm.tobytes())
        proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.kill()
        except Exception:
            pass
        _free_ram()
    return output_path


def get_stock_broll_clip(
    category: str,
    target_duration: float,
    cache_dir: str,
    width: int = 540,
    height: int = 960,
    pexels_api_key: Optional[str] = None,
    allow_procedural_fallback: bool = False,
    custom_search_query: Optional[str] = None,
    scene_text: str = ""
) -> Optional[str]:
    """
    يسحب مقطع فيديو B-Roll فعلي من `Pexels API` (أو مكتبة المقاطع المباشرة الخالية من حقوق الملكية)
    بناءً على الكلمات المفتاحية للجملة المنطوقة أو تعديلات المستخدم (`custom_search_query`).
    """
    os.makedirs(cache_dir, exist_ok=True)
    cat_key = map_scene_to_stock_category(category, scene_text) if scene_text else category.lower()
    is_portrait = (height >= width)
    orientation = 'portrait' if is_portrait else 'landscape'

    eff_pexels_key = pexels_api_key or os.environ.get("PEXELS_API_KEY", "")
    if eff_pexels_key:
        q = (custom_search_query or "").strip() or build_pexels_query_from_scene_keywords(
            scene_text=scene_text,
            kpi_value=custom_search_query or "",
            category=cat_key
        )
        vid_p = fetch_pexels_stock_video(q, eff_pexels_key, cache_dir, orientation=orientation)
        if vid_p and os.path.exists(vid_p):
            return vid_p

    direct_candidates = CURATED_DIRECT_STOCK_VIDEOS.get(cat_key, CURATED_DIRECT_STOCK_VIDEOS['video_editor'])
    for url in direct_candidates:
        u_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        cached_file = os.path.join(cache_dir, f'stock_{cat_key}_{u_hash}.mp4')
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 40000:
            return cached_file
        if download_video_file(url, cached_file):
            return cached_file

    if not allow_procedural_fallback:
        return None

    proc_file = os.path.join(cache_dir, f'proc_{cat_key}_{int(target_duration)}.mp4')
    if os.path.exists(proc_file) and os.path.getsize(proc_file) > 10000:
        return proc_file

    return generate_procedural_broll_clip(cat_key, proc_file, width=width, height=height, duration=max(2.5, target_duration))


def process_broll_clip_for_timeline(raw_video_path: str, target_duration: float, width: int, height: int):
    return raw_video_path