"""
smart_analyzer.py - المحلل الذكي للوسائط، محرك الذكاء الاصطناعي الهجين (سحابي/محلي)، والمخرج التلقائي
====================================================================================================
يوفر هذا الملف:
1. الاتصال الذكي بالإنترنت والنماذج السحابية (Groq, Gemini, OpenAI, Pollinations Free Cloud AI) مع التراجع السلس لـ Ollama المحلي أو القواعد الذكية.
2. التحليل الهندسي للصوت والفيديو (مستوى الضجيج، ديسيبل الصوت، نسبة الصمت، حركة الكاميرا، سرعة الكلام) لضبط أفضل الإعدادات والموديلات تلقائياً.
3. اختيار أفضل نمط مونتاج بناءً على معايير علمية واضحة، أو توزيع الأدوار (المخرج الذكي الشامل All-in-One) على جمل الفيديو.
"""

import os
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
# 1. إعدادات الصيغ المدعومة (شاملة لكل صيغ الصوت والتسجيلات الصوتية والفيديو)
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
# 2. فحص الاتصال بالإنترنت وتحديد أفضل مزود ذكاء اصطناعي (Cloud + Local)
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
    """
    تحديد أفضل مزود ذكاء اصطناعي (للنص والصوت) بناءً على حالة الإنترنت والمفاتيح المتاحة.
    يعطي الأولوية للإنترنت للحصول على أعلى جودة كما طلب المستخدم، مع دعم العمل المجاني السحابي بدون مفتاح.
    """
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
        # اتصال مجاني بالإنترنت بدون الحاجة لأي مفتاح API
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
    system_prompt: str = "أنت خبير في تحرير الفيديو، الموشن جرافيك، والدارجة الجزائرية والعربية.",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    ollama_model: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    temperature: float = 0.25,
    max_tokens: int = 800
) -> Optional[str]:
    """
    استدعاء الذكاء الاصطناعي الهجين:
    1. يجرب Groq أو Gemini أو OpenAI إذا توفرت مفاتيحها.
    2. يجرب الذكاء السحابي المجاني عبر الإنترنت (Pollinations AI OpenAI-compatible API) بدون مفتاح.
    3. يجرب خادم Ollama المحلي إذا كان متاحاً.
    """
    groq_key = (groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    gemini_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    openai_key = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    # 1. Groq Cloud API
    if groq_key:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=15
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content:
                    return content
        except Exception as e:
            logger.warning(f"Groq API warning: {e}")

    # 2. Google Gemini API
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
            except Exception as e:
                logger.warning(f"Gemini API warning ({gem_model}): {e}")

    # 3. OpenAI API
    if openai_key:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=15
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content:
                    return content
        except Exception as e:
            logger.warning(f"OpenAI API warning: {e}")

    # 4. Free Cloud AI (Pollinations OpenAI-compatible Endpoint - Works with Internet without any API key)
    try:
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            headers={"Content-Type": "application/json"},
            json={
                "model": "openai",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
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
    except Exception as e:
        logger.debug(f"Free Cloud AI endpoint not reachable: {e}")

    # 5. Local Ollama Fallback
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
# 3. التحليل الهندسي الذكي للصوت والفيديو واختيار أفضل الإعدادات تلقائياً
# ==============================================================================
def analyze_media_file(
    file_path: str,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    تحليل شامل للملف المرفوع (صوت أو فيديو) لاستخلاص:
    - هل يحتوي على مسار فيديو فعلي أم صوت فقط؟
    - شدة الصوت (dBFS)، أرضية الضوضاء (Noise Floor)، ونسبة الصمت.
    - أفضل عتبة صمت تلقائية (Auto Silence Threshold) وهامش أمان (Padding).
    - أفضل حجم لنموذج Whisper بناءً على العتاد والمدة والاتصال.
    - درجة الحركة البصرية في الفيديو (Visual Motion Score) لتحديد مدى الحاجة للزوم والموشن جرافيك.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"الملف غير موجود: {file_path}")

    _, ext = os.path.splitext(file_path.lower())
    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

    # 1. التحقق من وجود مسار فيديو فعلي وحساب الحركة البصرية
    has_video_stream = False
    width, height, fps = 1080, 1920, 24
    visual_motion_score = 0.0
    video_duration = 0.0

    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        try:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(file_path)
            if clip.w and clip.h and clip.duration and clip.duration > 0.1:
                # فحص إطار للتأكد من أنه ليس ملف صوت بامتداد mp4/webm
                frame0 = clip.get_frame(0)
                if frame0 is not None and frame0.size > 0:
                    has_video_stream = True
                    width, height = int(clip.w), int(clip.h)
                    fps = int(clip.fps) if clip.fps and clip.fps > 1 else 24
                    video_duration = float(clip.duration)

                    # حساب درجة التغير البصري بين عدة إطارات (Visual Activity)
                    sample_times = np.linspace(0.1, max(0.2, video_duration - 0.1), min(8, max(2, int(video_duration))))
                    prev_small = None
                    diffs = []
                    for t in sample_times:
                        frm = clip.get_frame(t)
                        # تصغير الإطار بالخطوة لتسريع الحساب
                        small = frm[::8, ::8].astype(np.float32)
                        if prev_small is not None and small.shape == prev_small.shape:
                            diffs.append(float(np.mean(np.abs(small - prev_small))))
                        prev_small = small
                    if diffs:
                        visual_motion_score = round(float(np.mean(diffs)), 2)
            clip.close()
        except Exception as e:
            logger.warning(f"ملاحظة أثناء فحص مسار الفيديو (سيتم التعامل معه كملف صوتي): {e}")
            has_video_stream = False

    # 2. تحليل الإشارة الصوتية عبر Pydub
    duration_sec = video_duration
    mean_dbfs = -28.0
    max_dbfs = -6.0
    noise_floor_dbfs = -48.0
    optimal_silence_thresh = -38.0
    silence_ratio = 0.20
    optimal_padding_ms = 120
    optimal_chunk_size = 10

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
        duration_sec = round(len(audio) / 1000.0, 2)
        if duration_sec > 0 and audio.dBFS != - float("inf"):
            mean_dbfs = round(float(audio.dBFS), 1)
            max_dbfs = round(float(audio.max_dBFS), 1)

            # تقسيم الصوت إلى نوافذ 100ms لحساب توزيع الطاقة الصوتية وأرضية الضجيج
            step_ms = 100
            chunk_levels = [
                c.dBFS for c in audio[::step_ms]
                if c.dBFS != -float("inf") and c.dBFS > -85.0
            ]
            if chunk_levels:
                p15 = float(np.percentile(chunk_levels, 15))
                p50 = float(np.percentile(chunk_levels, 50))
                p85 = float(np.percentile(chunk_levels, 85))
                noise_floor_dbfs = round(p15, 1)

                # معادلة ذكية لضبط عتبة الصمت بين أرضية الضجيج ومتوسط الكلام
                raw_thresh = p15 + 0.32 * (p85 - p15)
                # ضمان وقوع العتبة في نطاق آمن يحمي الكلام الهامس ويعزل الضوضاء
                optimal_silence_thresh = round(max(-50.0, min(-25.0, raw_thresh, mean_dbfs - 5.5)), 1)

                silent_chunks = sum(1 for lvl in chunk_levels if lvl < optimal_silence_thresh)
                silence_ratio = round(silent_chunks / max(1, len(chunk_levels)), 2)

                # ضبط هامش الأمان (Padding) بناءً على نسبة الصمت
                if silence_ratio > 0.35:
                    optimal_padding_ms = 130
                elif silence_ratio < 0.12:
                    optimal_padding_ms = 90
                else:
                    optimal_padding_ms = 110
    except Exception as e:
        logger.warning(f"تعذر تحليل تفاصيل dBFS الدقيقة، سيتم استخدام القيم القياسية الذكية: {e}")

    # 3. اختيار أفضل نموذج تفريغ (Whisper) ومزود الذكاء الاصطناعي
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

    if has_cuda:
        optimal_whisper_model = "medium"
    elif duration_sec <= 120:
        # للمقاطع القصيرة والمتوسطة نستخدم small لأنه سريع ودقيق مع موجه الدارجة الجزائرية
        optimal_whisper_model = "small"
    else:
        optimal_whisper_model = "small"

    # 4. تحديد النمط الأنسب مبدئياً بناءً على المعايير الفيزيائية
    recommendation = recommend_editing_style(
        has_video=has_video_stream,
        duration_sec=duration_sec,
        silence_ratio=silence_ratio,
        visual_motion_score=visual_motion_score,
        aspect_ratio="vertical" if height >= width else "horizontal"
    )

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
        "recommended_style": recommendation["style_key"],
        "recommended_style_name": recommendation["style_name"],
        "criteria_reasons": recommendation["reasons"]
    }


def recommend_editing_style(
    has_video: bool,
    duration_sec: float,
    silence_ratio: float,
    visual_motion_score: float,
    aspect_ratio: str,
    transcript_text: str = ""
) -> Dict[str, Any]:
    """
    اختيار أفضل نمط مونتاج بناءً على معايير علمية واضحة (وليس عشوائياً):
    1. نوع الوسائط (صوت فقط أم فيديو).
    2. درجة ثبات الكاميرا والحركة البصرية (Visual Motion Score).
    3. نسبة الصمت والتوقفات (Silence Ratio).
    4. طبيعة المحتوى النصي (تعليمي/هندسي، شرح ومعلومات، أم حديث مباشر).
    """
    reasons = []

    # فحص الكلمات الدلالية في النص إن وجد
    math_tech_keywords = {"معادلة", "هندسة", "خوارزمية", "حساب", "رياضيات", "دالة", "بيانات", "احصائيات", "نسبة", "برمجة", "فيزياء"}
    has_math_tech = any(kw in transcript_text for kw in math_tech_keywords) if transcript_text else False

    if not has_video:
        reasons.append("الملف المرفوع عبارة عن تسجيل صوتي فقط بدون مسار فيديو، لذا يحتاج إلى توليد بصري كامل.")
        if has_math_tech:
            reasons.append("المحتوى يحتوي على مفاهيم تقنية/تحليلية تناسب الرسوم الهندسية والمخططات المتحركة.")
            return {
                "style_key": "all_in_one",
                "style_name": "النمط التلقائي الذكي - دمج كل الأدوار (Smart Director All-in-One)",
                "sub_mode_for_audio": "kinetic_plus_manim",
                "reasons": reasons
            }
        else:
            reasons.append("تم تفعيل الموشن جرافيك النصي الاحترافي مع الأيقونات الديناميكية والخلفيات المتحركة المتفاعلة مع الصوت.")
            return {
                "style_key": "motion_text",
                "style_name": "موشن جرافيك نصي احترافي (Kinetic Typography & Icons)",
                "sub_mode_for_audio": "motion_text",
                "reasons": reasons
            }

    # في حال كان الملف فيديو:
    if silence_ratio >= 0.25:
        reasons.append(f"نسبة التوقفات والصمت في التسجيل تبلغ {int(silence_ratio*100)}%، مما يستدعي تفعيل القص الذكي (Jump-cuts) لرفع الإيقاع.")
    else:
        reasons.append(f"تدفق الكلام متواصل بنسبة صمت منخفضة ({int(silence_ratio*100)}%)، مما يسمح بانتقالات سلسة.")

    if visual_motion_score < 12.0:
        reasons.append(
            f"مؤشر الحركة البصرية في الفيديو منخفض ({visual_motion_score}) أي أن الكاميرا شبه ثابتة (Talking Head)، "
            "لذلك تم دمج الزوم السينمائي مع بطاقات الموشن جرافيك والانفوجرافيك لكسر الجمود البصري."
        )
    else:
        reasons.append(
            f"الفيديو يحتوي على حركة بصرية نشطة ({visual_motion_score})، "
            "لذلك سيتم تراكب الموشن جرافيك والكابشن التفاعلي في الثلث السفلي والزوايا دون التشويش على المشهد."
        )

    return {
        "style_key": "all_in_one",
        "style_name": "النمط التلقائي الذكي - دمج كل الأدوار (Smart Director All-in-One)",
        "reasons": reasons
    }


def plan_smart_director_segments(
    sentences: List[Dict[str, Any]],
    has_video: bool,
    visual_motion_score: float = 8.0
) -> List[Dict[str, Any]]:
    """
    توزيع الأدوار السينمائية (Role Assignment) على كل جملة في نمط "دمج كل الأدوار"
    بناءً على معايير محددة:
    - الجملة الافتتاحية (Hook) أو الجمل التي تحتوي على أرقام/مفاهيم قوية -> تأخذ بطاقة موشن جرافيك بارزة (Infographic Callout) أو فاصل بصري (Visual Burst).
    - الجمل الحوارية المتتالية -> تتناوب بين التكبير الديناميكي (Zoom + Karaoke) واللقطة العادية مع كابشن احترافي.
    """
    planned = []
    emphasis_markers = {
        "مهم", "سر", "أول", "ثاني", "ثالث", "لازم", "ضروري", "بزاف", "خطير", "نتيجة",
        "الحل", "الطريقة", "علاش", "كيفاش", "نصيحة", "قاعدة", "مثال", "فكرة", "مشكل",
        "1", "2", "3", "٪", "%", "مليون", "ألف", "دينار", "دولار"
    }

    for idx, sent in enumerate(sentences):
        text = sent.get("text", "")
        duration = max(0.2, sent.get("end", 0.0) - sent.get("start", 0.0))
        words_count = len(sent.get("words", [])) or len(text.split())
        wps = words_count / duration  # سرعة الكلمات في الثانية

        has_emphasis = any(m in text for m in emphasis_markers) or ("؟" in text) or ("!" in text)

        if not has_video:
            # إذا كان الملف صوتياً فقط: ندمج بين الموشن جرافيك النصي واللوحات البيانية الهندسية
            role = "kinetic_infographic" if (idx == 0 or has_emphasis or idx % 2 == 0) else "kinetic_minimal"
            zoom = 1.12 if idx % 2 == 1 else 1.0
        else:
            # إذا كان الملف فيديو: ندمج كل الأدوار بذكاء
            if idx == 0 and duration >= 1.2:
                # الجملة الافتتاحية (Hook): زوم + بطاقة عنوان موشن جرافيك علوية + كابشن تفاعلي
                role = "hook_motion_overlay"
                zoom = 1.14
            elif has_emphasis and duration >= 1.8 and idx % 3 == 1:
                # جملة محورية: فاصل موشن جرافيك مدمج (Picture-in-Picture / Split Graphic Burst)
                role = "graphic_burst_overlay"
                zoom = 1.16 if visual_motion_score < 14.0 else 1.06
            elif has_emphasis or idx % 2 == 1:
                # جملة مهمة: تراكب بطاقة موشن جرافيك وأيقونة ديناميكية فوق الفيديو الأصلي + زوم
                role = "motion_card_overlay"
                zoom = 1.14 if visual_motion_score < 14.0 else 1.05
            else:
                # جملة انتقالية هادئة لراحة العين: لقطة أصلية صافية مع كابشن كاريوكي أنيق
                role = "clean_karaoke"
                zoom = 1.0

        enriched = dict(sent)
        enriched["director_role"] = role
        enriched["zoom_factor"] = zoom
        enriched["speech_rate_wps"] = round(wps, 2)
        enriched["is_emphasis"] = has_emphasis
        planned.append(enriched)

    return planned
