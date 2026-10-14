# ==============================================================================
# AI Video Automation - Royalty-Free Stock Video Finder & B-Roll Pipeline
# ==============================================================================
import sys
import os

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

def download_video_file(url: str, output_path: str, timeout: int = 15) -> bool:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, stream=True, timeout=timeout)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=131072):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
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
                files = vid.get('video_files', [])
                for f_info in files:
                    link = f_info.get('link')
                    if link and f_info.get('file_type') == 'video/mp4':
                        q_hash = hashlib.md5((query + link).encode()).hexdigest()[:10]
                        dest = os.path.join(cache_dir, f'pexels_{q_hash}.mp4')
                        if os.path.exists(dest) and os.path.getsize(dest) > 50000:
                            return dest
                        if download_video_file(link, dest):
                            return dest
    except Exception as e:
        logger.warning(f'Pexels API exception: {e}')
    return None

def generate_procedural_broll_clip(category: str, output_path: str, width: int = 1080, height: int = 1920, duration: float = 3.0) -> str:
    from moviepy.editor import VideoClip
    import numpy as np
    from PIL import Image, ImageDraw

    def make_frame(t: float) -> np.ndarray:
        img = Image.new('RGB', (width, height), (10, 16, 32))
        draw = ImageDraw.Draw(img)
        cx = width // 2
        cy = height // 2

        for y in range(0, height, 4):
            ratio = float(y) / height
            r = int(14 + 18 * ratio)
            g = int(22 + 32 * ratio)
            b = int(48 + 40 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b), width=4)

        if category in ('developer_coding', 'video_editor'):
            for row in range(12):
                ry = int(height * 0.22) + row * 85
                rw = int(width * (0.35 + 0.5 * math.sin(t * 3.0 + row)))
                col = (56, 189, 248) if row % 3 == 0 else (255, 220, 0)
                draw.rounded_rectangle([(int(width * 0.12), ry), (int(width * 0.12) + rw, ry + 32)], radius=8, fill=col)
        elif category == 'ai_technology':
            for i in range(16):
                ang = math.radians(i * 22.5 + t * 45)
                dr = int(min(width, height) * 0.35 * (0.8 + 0.2 * math.sin(t * 4 + i)))
                dx = cx + int(dr * math.cos(ang))
                dy = cy + int(dr * math.sin(ang))
                draw.line([(cx, cy), (dx, dy)], fill=(0, 245, 212), width=3)
                draw.ellipse([(dx - 12, dy - 12), (dx + 12, dy + 12)], fill=(255, 220, 0))
        else:
            for ring in range(4):
                rr = int(min(width, height) * (0.18 + ring * 0.12 + 0.03 * math.sin(t * 4 + ring)))
                draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], outline=(255, 220, 0), width=4)

        return np.array(img)

    clip = VideoClip(make_frame, duration=duration)
    clip.write_videofile(output_path, fps=24, codec='libx264', audio=False, preset='ultrafast', threads=2, logger=None)
    clip.close()
    return output_path

def get_stock_broll_clip(category: str, target_duration: float, cache_dir: str, width: int = 1080, height: int = 1920, pexels_api_key: Optional[str] = None) -> str:
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
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 50000:
            return cached_file
        if download_video_file(url, cached_file):
            return cached_file

    proc_file = os.path.join(cache_dir, f'proc_{cat_key}_{int(target_duration)}.mp4')
    if os.path.exists(proc_file) and os.path.getsize(proc_file) > 10000:
        return proc_file

    return generate_procedural_broll_clip(cat_key, proc_file, width=width, height=height, duration=max(2.5, target_duration))

def process_broll_clip_for_timeline(raw_video_path: str, target_duration: float, width: int, height: int):
    from moviepy.editor import VideoFileClip

    clip = VideoFileClip(raw_video_path).without_audio()
    orig_w, orig_h = clip.size

    scale = max(width / float(orig_w), height / float(orig_h))
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    resized = clip.resize((new_w, new_h))
    x1 = max(0, (new_w - width) // 2)
    y1 = max(0, (new_h - height) // 2)
    cropped = resized.crop(x1=x1, y1=y1, width=width, height=height)

    if cropped.duration < target_duration:
        from moviepy.editor import vfx
        cropped = cropped.fx(vfx.loop, duration=target_duration)
    else:
        cropped = cropped.subclip(0, target_duration)

    return cropped
