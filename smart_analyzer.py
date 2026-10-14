"""
smart_analyzer.py - المحلل الذكي للوسائط، محرك الذكاء الاصطناعي الهجين، ومخرج الإعلانات التجارية المتقدم
========================================================================================================
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import re
import json
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. إعدادات الصيغ المدعومة
# ==============================================================================
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
# 2. فحص الاتصال بالإنترنت ومزودي الذكاء الاصطناعي
# ==============================================================================
def check_internet_connection(timeout: float = 3.0) -> bool:
    """التحقق السريع من توفر اتصال بالإنترنت."""
    test_urls = [
        "https://text.pollinations.ai",
        "https://www.google.com",
        "https://1.1.1.1"
    ]
    for url in test_urls:
        try:
            resp = requests.head(url, timeout=timeout)
            if resp.status_code < 500:
                return True
        except Exception:
            continue
    return False


def check_ollama_available(ollama_url: str = "http://localhost:11434", timeout: float = 1.5) -> bool:
    """التحقق مما إذا كان خادم Ollama المحلي يعمل."""
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
    """تحديد أفضل مزود ذكاء اصطناعي."""
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
            "label": "الذكاء السحابي المجاني المتصل بالإنترنت (Cloud AI + Faster-Whisper Enhanced)"
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
    system_prompt: str = "أنت خبير في تحرير الفيديو، إعلانات التجارة الإلكترونية، والدارجة الجزائرية والعربية.",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    ollama_model: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    temperature: float = 0.25,
    max_tokens: int = 800
) -> Optional[str]:
    """استدعاء الذكاء الاصطناعي الهجين."""
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
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content:
                    return content
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
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content:
                    return content
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
                content = data["choices"][0].get("message", {}).get("content", "").strip()
                if content:
                    return content
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
            content = resp.json().get("response", "").strip()
            if content:
                return content
    except Exception:
        pass

    return None


# ==============================================================================
# 3. التحليل الهندسي الذكي للصوت والفيديو (مع حماية الكلام البشري الطبيعي)
# ==============================================================================
def analyze_media_file(
    file_path: str,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """تحليل شامل للملف المرفوع مع ضبط عتبة صمت تحافظ على مخارج الحروف والتنفس الطبيعي."""
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

                    sample_times = np.linspace(0.1, max(0.2, video_duration - 0.1), min(8, max(2, int(video_duration))))
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
    optimal_padding_ms = 250  # هامش أمان بشري طبيعي يمنع بتر الحروف أو التصاق الكلمات
    optimal_chunk_size = 10

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

                # وضع العتبة قريباً من أرضية الضجيج (18% فقط من المدى) لحماية كل همس أو نهاية كلمة
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

    return {
        "file_path": file_path,
        "file_size_mb": file_size_mb,
        "has_video": has_video_stream,
        "media_type_ar": "فيديو مع صوت 🎬" if has_video_stream else "تسجيل / ملف صوتي فقط 🎙️",
        "duration_sec": duration_sec,
        "width": width,
        "height": height,
        "fps": fps,
        "aspect_ratio": "عمودي (9:16)" if height >= width else "أفقي (16:9)",
        "mean_dbfs": mean_dbfs,
        "max_dbfs": max_dbfs,
        "noise_floor_dbfs": noise_floor_dbfs,
        "silence_ratio": silence_ratio,
        "silence_percent": int(silence_ratio * 100),
        "visual_motion_score": visual_motion_score,
        "optimal_silence_threshold": optimal_silence_thresh,
        "optimal_padding_ms": optimal_padding_ms,
        "optimal_chunk_size": optimal_chunk_size,
        "optimal_whisper_model": optimal_whisper_model,
        "ai_provider_info": ai_info,
        "recommended_style": "product_ad",
        "recommended_style_name": "🛍️ نمط إعلانات المنتجات والتجارة الإلكترونية (E-Commerce Ad)",
        "criteria_reasons": [
            f"ضبط عتبة الصمت عند ({optimal_silence_thresh} dBFS) وهامش أمان بشري ({optimal_padding_ms}ms) لحماية مخارج الحروف والتنفس الطبيعي ومنع التصاق الكلمات.",
            "توزيع بصري احترافي لهيكل الإعلان (خطاف Hook، إبراز المشكلة، كشف مميزات المنتج، شارات الثقة، ونداء الشراء CTA)."
        ]
    }


# ==============================================================================
# 4. محرك تحليل وهيكلة إعلانات المنتجات التجارية (E-Commerce Ad Intelligence)
# ==============================================================================
def plan_product_ad_segments(
    sentences: List[Dict[str, Any]],
    total_duration: float,
    product_title_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """تخطيط ومونتاج فيديو إعلان المنتج وفق معايير تسويقية صارمة."""
    if not sentences:
        return []

    problem_keywords = [
        "مشكل", "تعبت", "ديما", "يخسر", "بطيء", "يتكسر", "غالي", "حرت", "صعيب", "ضياع",
        "تضييع", "تلف", "قلق", "يفسد", "معاناة", "رديء", "فاشل", "مقلد", "مغشوش"
    ]
    trust_keywords = [
        "توصيل", "ولاية", "58", "باب الدار", "ضمان", "كوندوسيو", "أصلية", "استرجاع",
        "مجاني", "الدفع عند الاستلام", "دفع", "كاش", "سريع", "لباب", "مضمون", "ثقة"
    ]
    cta_keywords = [
        "اطلب", "الرابط", "البايو", "السعر", "سومة", "تخفيض", "كمية محدودة", "كليكي",
        "برومو", "عرض", "تواصل", "رقم", "سارع", "احجز", "موقع", "صفحة", "للطلب"
    ]

    planned = []
    num_sentences = len(sentences)

    for idx, sent in enumerate(sentences):
        text = sent.get("text", "")
        t_start = float(sent.get("start", 0.0))
        t_end = float(sent.get("end", 0.0))

        is_hook = (idx == 0 or t_start < 3.2)
        is_cta = (idx == num_sentences - 1 or t_end >= total_duration - 4.5 or any(k in text for k in cta_keywords))
        is_trust = any(k in text for k in trust_keywords)
        is_problem = any(k in text for k in problem_keywords) and not is_hook and not is_cta

        if is_hook:
            ad_role = "ad_hook"
            zoom = 1.18
            badge_title = product_title_override or "🔥 عفسة هبال لازم تشوفها!"
            icon_cat = "warning"
        elif is_cta:
            ad_role = "ad_cta"
            zoom = 1.14
            badge_title = cta_override or "🛒 اطلب الآن والدفع عند الاستلام!"
            icon_cat = "money"
        elif is_trust:
            ad_role = "ad_trust"
            zoom = 1.08
            if any(w in text for w in ["توصيل", "ولاية", "58", "باب"]):
                badge_title = "🚚 توصيل سريع متوفر لـ 58 ولاية"
                icon_cat = "time"
            elif any(w in text for w in ["دفع", "استلام", "كاش"]):
                badge_title = "💵 الدفع عند الاستلام بعد المعاينة"
                icon_cat = "money"
            else:
                badge_title = "🛡️ ضمان الجودة والاستبدال 100%"
                icon_cat = "success"
        elif is_problem:
            ad_role = "ad_problem"
            zoom = 1.06
            badge_title = "❌ المشكلة الشائعة"
            icon_cat = "warning"
        else:
            ad_role = "ad_feature"
            zoom = 1.13 if (idx % 2 == 1) else 1.05
            words = text.split()
            clean_feat = " ".join(words[:3]) if len(words) >= 3 else text
            badge_title = f"✨ {clean_feat}"
            icon_cat = "idea" if any(w in text for w in ["ذكاء", "فكرة", "حل"]) else "success"

        enriched = dict(sent)
        enriched["ad_role"] = ad_role
        enriched["zoom_factor"] = zoom
        enriched["badge_title"] = badge_title
        enriched["icon_cat"] = icon_cat
        planned.append(enriched)

    return planned


def plan_smart_director_segments(
    sentences: List[Dict[str, Any]],
    has_video: bool,
    visual_motion_score: float = 8.0
) -> List[Dict[str, Any]]:
    """توزيع الأدوار للمخرج الذكي العام."""
    planned = []
    emphasis_markers = {
        "مهم", "سر", "أول", "ثاني", "ثالث", "لازم", "ضروري", "بزاف", "خطير", "نتيجة",
        "الحل", "الطريقة", "علاش", "كيفاش", "نصيحة", "قاعدة", "مثال", "فكرة", "مشكل",
        "1", "2", "3", "٪", "%", "مليون", "ألف", "دينار", "دولار"
    }

    for idx, sent in enumerate(sentences):
        text = sent.get("text", "")
        duration = max(0.2, sent.get("end", 0.0) - sent.get("start", 0.0))
        has_emphasis = any(m in text for m in emphasis_markers) or ("؟" in text) or ("!" in text)

        if not has_video:
            role = "kinetic_infographic" if (idx == 0 or has_emphasis or idx % 2 == 0) else "kinetic_minimal"
            zoom = 1.12 if idx % 2 == 1 else 1.0
        else:
            if idx == 0 and duration >= 1.2:
                role = "hook_motion_overlay"
                zoom = 1.14
            elif has_emphasis and duration >= 1.8 and idx % 3 == 1:
                role = "graphic_burst_overlay"
                zoom = 1.16 if visual_motion_score < 14.0 else 1.06
            elif has_emphasis or idx % 2 == 1:
                role = "motion_card_overlay"
                zoom = 1.14 if visual_motion_score < 14.0 else 1.05
            else:
                role = "clean_karaoke"
                zoom = 1.0

        enriched = dict(sent)
        enriched["director_role"] = role
        enriched["zoom_factor"] = zoom
        planned.append(enriched)

    return planned
