# ==============================================================================
# AI Video Automation - Royalty-Free Stock Video Finder & Low-RAM B-Roll Pipeline
# ==============================================================================
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
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _free_ram():
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


CURATED_DIRECT_STOCK_VIDEOS = {
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


def map_scene_to_stock_category(scene_type: str, scene_text: str) -> str:
    type_map = {
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

    t = scene_text.lower()
    if any(w in t for w in ('ذكاء', 'اصطناعي', 'خوارزمية', 'أوتوماتيكي', 'ai', 'neural')):
        return 'ai_technology'
    if any(w in t for w in ('وقت', 'ساعة', 'ما عندها وقت', 'ما عندهمش وقت', 'مشغول', 'ساعات', 'دقيقة', 'تأخير')):
        return 'busy_no_time'
    if any(w in t for w in ('ريلز', 'تيك توك', 'شورتس', 'سوشيال', 'هاتف', 'تلفون', 'موبايل', 'smartphone')):
        return 'smartphone_reels'
    if any(w in t for w in ('كود', 'برمجة', 'أبني', 'تطبيق', 'موقع', 'منصة', 'developer', 'code')):
        return 'developer_coding'
    if any(w in t for w in ('استوديو', 'صانع محتوى', 'مبدع', 'كاميرا', 'تسجيل', 'ميكروفون', 'creator')):
        return 'creator_studio'
    return 'video_editor'


def download_video_file(url: str, output_path: str, timeout: int = 12) -> bool:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, stream=True, timeout=timeout)
        if resp.status_code == 200:
            max_bytes = 15 * 1024 * 1024  # سقف 15MB لأي مقطع B-Roll لمنع امتلاء الذاكرة
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
        params = {'query': query, 'per_page': 4, 'orientation': orientation}
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            videos = resp.json().get('videos', [])
            for vid in videos:
                files = [f for f in vid.get('video_files', []) if f.get('link') and f.get('file_type') == 'video/mp4']
                # اختيار النسخة الخفيفة SD/HD (بعرض قريب من 540px) وتجنب ملفات 4K UHD الثقيلة التي تسقط ذاكرة السيرفر!
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
    import numpy as np
    from PIL import Image, ImageDraw

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


def get_stock_broll_clip(category: str, target_duration: float, cache_dir: str, width: int = 540, height: int = 960, pexels_api_key: Optional[str] = None) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    cat_key = category.lower()
    is_portrait = (height >= width)
    orientation = 'portrait' if is_portrait else 'landscape'

    if pexels_api_key:
        query_map = {
            'video_editor': 'video editing computer',
            'ai_technology': 'artificial intelligence technology',
            'busy_no_time': 'time lapse clock laptop',
            'smartphone_reels': 'person using smartphone',
            'developer_coding': 'developer coding keyboard',
            'creator_studio': 'content creator desk'
        }
        q = query_map.get(cat_key, 'technology digital screen')
        vid_p = fetch_pexels_stock_video(q, pexels_api_key, cache_dir, orientation=orientation)
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

    proc_file = os.path.join(cache_dir, f'proc_{cat_key}_{int(target_duration)}.mp4')
    if os.path.exists(proc_file) and os.path.getsize(proc_file) > 10000:
        return proc_file

    return generate_procedural_broll_clip(cat_key, proc_file, width=width, height=height, duration=max(2.5, target_duration))


def process_broll_clip_for_timeline(raw_video_path: str, target_duration: float, width: int, height: int):
    return raw_video_path
