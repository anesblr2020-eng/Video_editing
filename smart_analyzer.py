"""
smart_analyzer.py - عقل المخرج الذكي الشامل ومحرك التحليل متعدد الأبعاد للفيديو والصوت
========================================================================================
يقوم هذا المحرك بتحليل متكامل للفيديو والصوت والنص الدلالي:
1. التحليل الصوتي متعدد الترددات (Loudness, Energy Peaks, Silence Pacing, Speech Cadence).
2. التحليل البصري لحركة الكاميرا وتمركز المتحدث وأبعاد الإطار (9:16 Reels vs 16:9 Landscape).
3. الفهم الدلالي لمحتوى الكلام واستخراج اللحظات المحورية لمشاهد الـ B-Roll والموشن جرافيك.
4. توليد "مخطط المخرج الشامل (Master Director Plan)" الذي يصدر أوامر دقيقة لكل ثانية:
   - يختار بذكاء 3 إلى 4 مشاهد فيديو B-Roll حقيقية خالية من حقوق الملكية في اللحظات المناسبة تماماً
     (شاشة مونتاج، شخص يعمل على حاسوب، هاتف وسوشيال ميديا، ساعة وضيق وقت) لكسر الملل دون إزعاج.
   - يوزع بقية اللقطات بين: شاشة موشن جرافيك كاملة، بطاقة علوية، شارة سفلية، ولقطة متحدث صافية.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

def _safe_rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, *, corners=None):
    try:
        if isinstance(xy[0], (list, tuple)):
            (x0, y0), (x1, y1) = xy
        else:
            x0, y0, x1, y1 = xy
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        if x_max - x_min < 1:
            x_max = x_min + 1
        if y_max - y_min < 1:
            y_max = y_min + 1
        safe_r = max(0, min(int(radius), int((x_max - x_min) // 2), int((y_max - y_min) // 2)))
        return _orig_rounded_rect(self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners)
    except Exception:
        pass

PIL.ImageDraw.ImageDraw.rounded_rectangle = _safe_rounded_rectangle

import re
import json
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import requests

try:
    from stock_video_finder import map_scene_to_stock_category
except ImportError:
    import importlib.util
    _cur = os.path.dirname(os.path.abspath(__file__))
    if _cur not in sys.path:
        sys.path.insert(0, _cur)
    _stock_path = os.path.join(_cur, "stock_video_finder.py")
    if os.path.exists(_stock_path):
        _spec = importlib.util.spec_from_file_location("stock_video_finder", _stock_path)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["stock_video_finder"] = _mod
        _spec.loader.exec_module(_mod)
        map_scene_to_stock_category = getattr(_mod, "map_scene_to_stock_category")
    else:
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
            if any(w in t for w in ('ذكاء', 'اصطناعي', 'خوارزمية', 'أوتوماتيكي', 'ai')):
                return 'ai_technology'
            if any(w in t for w in ('وقت', 'ساعة', 'مشغول', 'سرعة', 'تأخير')):
                return 'busy_no_time'
            if any(w in t for w in ('ريلز', 'تيك توك', 'شورتس', 'سوشيال', 'هاتف', 'تيليفون', 'سيبور')):
                return 'smartphone_reels'
            if any(w in t for w in ('كود', 'برمجة', 'تطبيق', 'موقع', 'منصة')):
                return 'developer_coding'
            if any(w in t for w in ('استوديو', 'صانع محتوى', 'مبدع', 'كاميرا')):
                return 'creator_studio'
            return 'video_editor'


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".ts", ".wmv", ".flv"
}

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".opus", ".aac", ".flac", ".wma", ".amr",
    ".mpga", ".mpeg", ".weba", ".caf", ".aiff"
}

ALL_SUPPORTED_EXTENSIONS = [
    ext.replace(".", "") for ext in sorted(SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS)
]


# ==============================================================================
# 1. الاتصال بمزودي الذكاء الاصطناعي الهجين
# ==============================================================================
def check_internet_connection(timeout: float = 2.5) -> bool:
    for url in ["https://text.pollinations.ai", "https://www.google.com", "https://1.1.1.1"]:
        try:
            resp = requests.head(url, timeout=timeout)
            if resp.status_code < 500:
                return True
        except Exception:
            continue
    return False


def check_ollama_available(ollama_url: str = "http://localhost:11434", timeout: float = 1.2) -> bool:
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def detect_best_ai_provider(
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    prefer_internet: bool = True
) -> Dict[str, Any]:
    groq_key = (groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    gemini_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    openai_key = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    has_internet = check_internet_connection() if prefer_internet else False
    has_ollama = check_ollama_available()

    if has_internet:
        if groq_key:
            return {
                "provider": "groq",
                "llm_model": "llama-3.3-70b-versatile",
                "stt_provider": "groq_whisper",
                "stt_model": "whisper-large-v3",
                "online": True,
                "label": "سحابي فائق السرعة (Groq Whisper Large-v3 + Llama 3.3 70B)"
            }
        if gemini_key:
            return {
                "provider": "gemini",
                "llm_model": "gemini-2.5-flash",
                "stt_provider": "faster_whisper",
                "stt_model": "medium",
                "online": True,
                "label": "سحابي متقدم (Google Gemini Flash + Enhanced Whisper)"
            }
        if openai_key:
            return {
                "provider": "openai",
                "llm_model": "gpt-4o-mini",
                "stt_provider": "openai_whisper",
                "stt_model": "whisper-1",
                "online": True,
                "label": "سحابي احترافي (OpenAI GPT-4o-mini + Whisper)"
            }
        return {
            "provider": "cloud_free",
            "llm_model": "openai-large",
            "stt_provider": "faster_whisper",
            "stt_model": "auto",
            "online": True,
            "label": "الذكاء السحابي المجاني المتصل بالإنترنت (Cloud AI + Whisper)"
        }

    if has_ollama:
        return {
            "provider": "ollama",
            "llm_model": "llama3",
            "stt_provider": "faster_whisper",
            "stt_model": "auto",
            "online": False,
            "label": "محلي عبر Ollama (Llama 3 + Faster-Whisper)"
        }

    return {
        "provider": "local_smart",
        "llm_model": "built_in_arabic_nlp",
        "stt_provider": "faster_whisper",
        "stt_model": "auto",
        "online": False,
        "label": "المعالج الذكي المدمج (بدون إنترنت)"
    }


def query_hybrid_llm(
    prompt: str,
    system_prompt: str = "أنت مخرج فيديو ومحلل محتوى سينمائي وإعلاني خبير في الدارجة الجزائرية والعربية.",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    ollama_model: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    temperature: float = 0.25,
    max_tokens: int = 800
) -> Optional[str]:
    groq_key = (groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    gemini_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    openai_key = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    if groq_key:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=15
            )
            if resp.status_code == 200:
                c = resp.json()["choices"][0]["message"]["content"].strip()
                if c:
                    return c
        except Exception:
            pass

    if gemini_key:
        for gem_model in ["gemini-2.5-flash", "gemini-1.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gem_model}:generateContent?key={gemini_key}"
                resp = requests.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
                    },
                    timeout=15
                )
                if resp.status_code == 200:
                    candidates = resp.json().get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
            except Exception:
                pass

    if openai_key:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=15
            )
            if resp.status_code == 200:
                c = resp.json()["choices"][0]["message"]["content"].strip()
                if c:
                    return c
        except Exception:
            pass

    try:
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            headers={"Content-Type": "application/json"},
            json={
                "model": "openai",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                "temperature": temperature,
                "seed": 42
            },
            timeout=14
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "choices" in data and data["choices"]:
                c = data["choices"][0].get("message", {}).get("content", "").strip()
                if c:
                    return c
    except Exception:
        pass

    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "prompt": f"{system_prompt}\n\n{prompt}",
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens}
            },
            timeout=8
        )
        if resp.status_code == 200:
            c = resp.json().get("response", "").strip()
            if c:
                return c
    except Exception:
        pass

    return None


# ==============================================================================
# 2. أداة التحليل الهندسي المتقدم للصوت والفيديو
# ==============================================================================
def analyze_media_file(
    file_path: str,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"الملف غير موجود: {file_path}")

    _, ext = os.path.splitext(file_path.lower())
    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

    has_video_stream = False
    width, height, fps = 1080, 1920, 24
    visual_motion_score = 0.0
    video_duration = 0.0

    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        try:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(file_path)
            if clip.w and clip.h and clip.duration and clip.duration > 0.1:
                frame0 = clip.get_frame(0)
                if frame0 is not None and frame0.size > 0:
                    has_video_stream = True
                    width, height = int(clip.w), int(clip.h)
                    fps = int(clip.fps) if clip.fps and clip.fps > 1 else 24
                    video_duration = float(clip.duration)

                    sample_times = np.linspace(0.1, max(0.2, video_duration - 0.1), min(10, max(2, int(video_duration))))
                    prev_small = None
                    diffs = []
                    for t in sample_times:
                        frm = clip.get_frame(t)
                        small = frm[::8, ::8].astype(np.float32)
                        if prev_small is not None and small.shape == prev_small.shape:
                            diffs.append(float(np.mean(np.abs(small - prev_small))))
                        prev_small = small
                    if diffs:
                        visual_motion_score = round(float(np.mean(diffs)), 2)
            clip.close()
        except Exception:
            has_video_stream = False

    duration_sec = video_duration
    mean_dbfs = -28.0
    max_dbfs = -6.0
    noise_floor_dbfs = -48.0
    optimal_silence_thresh = -42.0
    silence_ratio = 0.18
    optimal_padding_ms = 250

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
        duration_sec = round(len(audio) / 1000.0, 2)
        if duration_sec > 0 and audio.dBFS != -float("inf"):
            mean_dbfs = round(float(audio.dBFS), 1)
            max_dbfs = round(float(audio.max_dBFS), 1)

            step_ms = 100
            chunk_levels = [
                c.dBFS for c in audio[::step_ms]
                if c.dBFS != -float("inf") and c.dBFS > -85.0
            ]
            if chunk_levels:
                p15 = float(np.percentile(chunk_levels, 15))
                p85 = float(np.percentile(chunk_levels, 85))
                noise_floor_dbfs = round(p15, 1)

                raw_thresh = p15 + 0.18 * (p85 - p15)
                optimal_silence_thresh = round(max(-54.0, min(-32.0, raw_thresh, mean_dbfs - 11.0)), 1)
                silent_chunks = sum(1 for lvl in chunk_levels if lvl < optimal_silence_thresh)
                silence_ratio = round(silent_chunks / max(1, len(chunk_levels)), 2)
                optimal_padding_ms = 260 if silence_ratio > 0.25 else 240
    except Exception:
        pass

    ai_info = detect_best_ai_provider(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        prefer_internet=True
    )

    has_cuda = False
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        pass

    optimal_whisper_model = "medium" if has_cuda else "small"
    is_vertical = (height >= width)

    return {
        "file_path": file_path,
        "file_size_mb": file_size_mb,
        "has_video": has_video_stream,
        "media_type_ar": "فيديو مع صوت 🎬" if has_video_stream else "تسجيل / ملف صوتي فقط 🎙️",
        "duration_sec": duration_sec,
        "width": width,
        "height": height,
        "fps": fps,
        "aspect_ratio": "عمودي (9:16)" if is_vertical else "أفقي (16:9)",
        "mean_dbfs": mean_dbfs,
        "max_dbfs": max_dbfs,
        "noise_floor_dbfs": noise_floor_dbfs,
        "silence_ratio": silence_ratio,
        "silence_percent": int(silence_ratio * 100),
        "visual_motion_score": visual_motion_score,
        "optimal_silence_threshold": optimal_silence_thresh,
        "optimal_padding_ms": optimal_padding_ms,
        "optimal_chunk_size": 10,
        "optimal_whisper_model": optimal_whisper_model,
        "ai_provider_info": ai_info,
        "criteria_reasons": [
            f"تم ضبط عتبة السكوت الطبيعية عند ({optimal_silence_thresh} dBFS) وهامش حماية مخارج الحروف ({optimal_padding_ms}ms) لضمان تدفق بشري طبيعي.",
            f"المخرج الشامل سيختار تلقائياً 3 إلى 4 مشاهد B-Roll حقيقية خالية من حقوق الملكية تدعم المحتوى بدون إزعاج أو ملل."
        ]
    }


# ==============================================================================
# 3. عقل المخرج الذكي الشامل: تخطيط المشاهد واختيار 3-4 مشاهد B-Roll حقيقية
# ==============================================================================
def generate_master_director_plan(
    sentences_or_micro_scenes: List[Dict[str, Any]],
    total_duration: float,
    has_video: bool,
    visual_motion_score: float = 8.0,
    enable_stock_broll: bool = True,
    product_name_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    توليد مخطط المخرج الشامل:
    - يحدد بدقة 3 إلى 4 مشاهد B-roll واقعية خالية من حقوق الملكية عبر الفيديو في اللحظات المناسبة
      (مثال: شاشة مونتاج، شخص يعمل على حاسوب، هاتف وتيك توك، ضيق وقت وساعة).
    - يوزع بقية اللقطات بين: شاشة كاملة موشن جرافيك، بطاقات علوية، شارات سفلية، ولقطات متحدث صافية.
    """
    if not sentences_or_micro_scenes:
        return []

    from motion_text import classify_micro_scene_blueprint, MOTION_THEMES
    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    num_scenes = len(sentences_or_micro_scenes)
    master_plan = []
    prev_scene_type = None

    # تحديد مؤشرات المشاهد المؤهلة لتكون مقاطع B-Roll واقعية (نستهدف 3 إلى 4 مشاهد فقط كما طلب المستخدم)
    broll_candidate_indices = []
    for idx, sc in enumerate(sentences_or_micro_scenes):
        t_low = str(sc.get("text", "")).lower()
        # نستبعد المشهد الأول (الخطاف الأولي نفضل فيه الهوية/الوجه) والمشهد الأخير (الختام)
        if 0 < idx < num_scenes - 1:
            if any(w in t_low for w in ["مونتاج", "تمنتج", "فيديو", "إيديتينج", "وقت", "ساعة", "ريلز", "تيك توك", "أبني", "منصة", "حاسوب"]):
                broll_candidate_indices.append(idx)

    # اختيار 3 إلى 4 لقطات متباعدة زمنياً بدقة
    selected_broll_indices = set()
    if enable_stock_broll and broll_candidate_indices:
        target_broll_count = min(4, max(2, len(broll_candidate_indices)))
        # توزيع منتظم للـ 3 أو 4 لقطات
        step = max(1, len(broll_candidate_indices) // target_broll_count)
        for i in range(0, len(broll_candidate_indices), step):
            selected_broll_indices.add(broll_candidate_indices[i])
            if len(selected_broll_indices) >= 4:
                break

    lower_third_triggers = {
        "توصيل", "ولاية", "58", "باب الدار", "شحن", "مجاني",
        "دفع", "كاش", "استلام", "ضمان", "أصلية", "سعر", "سومة", "تخفيض",
        "اطلب", "الرابط", "البايو", "كليكي", "للطلب"
    }

    last_badge_idx = -99
    for idx, sc in enumerate(sentences_or_micro_scenes):
        s_text = str(sc.get("text", "")).strip()
        t_low = s_text.lower()
        s_start = max(0.0, float(sc.get("start", 0.0)))
        s_end = min(total_duration, float(sc.get("end", s_start + 1.8)))
        dur = max(0.2, s_end - s_start)

        bp = classify_micro_scene_blueprint(
            scene_text=s_text,
            scene_index=idx,
            total_scenes=num_scenes,
            prev_scene_type=prev_scene_type
        )
        prev_scene_type = bp["scene_type"]
        scene_type = bp["scene_type"]

        stock_category = map_scene_to_stock_category(scene_type, s_text)

        # تحديد نمط التراكب المكاني (Layout Mode)
        if idx in selected_broll_indices:
            # اللقطات الـ 3 أو 4 المختارة كـ B-Roll واقعي بدون حقوق ملكية!
            layout_mode = "stock_broll"
            zoom_factor = 1.0
        elif not has_video:
            layout_mode = "full_screen"
            zoom_factor = 1.0
        else:
            is_hook = (idx == 0 and s_start < 2.8)
            is_finale = (idx == num_scenes - 1 or s_end >= total_duration - 2.8)
            has_lower_trigger = any(trig in t_low for trig in lower_third_triggers)

            can_show_overlay = (idx - last_badge_idx) >= 2

            if is_hook:
                layout_mode = "top_overlay"
                zoom_factor = 1.08
                last_badge_idx = idx
            elif is_finale:
                layout_mode = "lower_third"
                zoom_factor = 1.0
                last_badge_idx = idx
            elif has_lower_trigger and can_show_overlay:
                layout_mode = "lower_third"
                zoom_factor = 1.0
                last_badge_idx = idx
            elif can_show_overlay and any(w in t_low for w in ["ميزة", "شحن", "سيبور", "جودة", "قوة", "ضمان", "توصيل", "سرعة", "مهم", "خاصية"]):
                layout_mode = "top_overlay"
                zoom_factor = 1.08
                last_badge_idx = idx
            else:
                layout_mode = "speaker_clean"
                zoom_factor = 1.08 if (idx % 3 == 1) else 1.0

        theme_name = theme_keys[idx % len(theme_keys)]
        transition = transitions[idx % len(transitions)]

        words = sc.get("words", [])
        word_strings = [w.get("word", "") for w in words]
        words_only = [w for w in re.findall(r"[\w\u0621-\u064A]+", s_text) if len(w) > 2]
        primary_kw = words_only[0] if words_only else (word_strings[0] if word_strings else "فكرة")

        badge_label = bp["badge_label"]
        if product_name_override and (idx == 0):
            badge_label = product_name_override
        if cta_override and (idx == num_scenes - 1):
            badge_label = cta_override

        directive = {
            "layout_mode": layout_mode,
            "scene_type": scene_type,
            "stock_category": stock_category,
            "badge_label": badge_label,
            "short_title": bp["short_title"],
            "primary_keyword": primary_kw,
            "target_number": bp.get("target_number", 17),
            "zoom_factor": zoom_factor,
            "theme_name": theme_name,
            "transition": transition
        }

        entry = dict(sc)
        entry["index"] = idx
        entry["start"] = s_start
        entry["end"] = s_end
        entry["word_strings"] = word_strings
        entry.update(directive)
        master_plan.append(entry)

    return master_plan


def plan_product_ad_segments(
    sentences: List[Dict[str, Any]],
    total_duration: float,
    product_title_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    return generate_master_director_plan(
        sentences_or_micro_scenes=sentences,
        total_duration=total_duration,
        has_video=True,
        visual_motion_score=8.0,
        enable_stock_broll=True,
        product_name_override=product_title_override,
        cta_override=cta_override,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key
    )


def plan_smart_director_segments(
    sentences: List[Dict[str, Any]],
    has_video: bool,
    visual_motion_score: float = 8.0,
    **kwargs
) -> List[Dict[str, Any]]:
    return generate_master_director_plan(
        sentences_or_micro_scenes=sentences,
        total_duration=sentences[-1]["end"] if sentences else 10.0,
        has_video=has_video,
        visual_motion_score=visual_motion_score,
        enable_stock_broll=True
    )
