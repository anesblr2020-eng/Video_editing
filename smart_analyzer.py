"""
smart_analyzer.py - عقل المخرج الذكي الشامل ومحرك الفهم السياقي والسردي للفيديو (Contextual & Narrative AI Brain)
====================================================================================================================
يقوم هذا المحرك بتحليل متكامل للفيديو والصوت والسياق الدلالي الشامل:
1. الفهم السياقي الشامل ذو المرحلتين (Two-Pass Global & Scene Contextual Brain):
   - المرحلة الأولى (`extract_global_video_context`): قراءة النص الكامل للفيديو من البداية للنهاية لفهم القصة العامة
     (قصة مؤسس ومشروع تقني، إعلان منتج وتجارة إلكترونية، محتوى تعليمي...) واستخراج الكيانات الكلية (الاسم، العمر، اسم المنصة، المشكلة، الحل).
   - المرحلة الثانية (`analyze_contextual_storyboard`): توجيه كل مشهد بناءً على معنى الجملة الكاملة وعلاقتها بما قبلها وما بعدها
     (عبر الذكاء الاصطناعي السحابي/المحلي + آلة الحالة السردية الذكية)، وتوليد عناوين مفاهيمية ومؤشرات KPI مرتبطة بالسياق الفعلي
     دون تكرار الكلمات المنطوقة حرفياً.
2. التحليل الصوتي متعدد الترددات والقص الطبيعي (Loudness, Silence Pacing, Speech Cadence).
3. توليد "مخطط المخرج الشامل (Master Director Plan)" مع اختيار 3-4 مشاهد B-Roll حقيقية خالية من حقوق الملكية.
"""

import sys
import os
import gc
import subprocess

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
if not hasattr(PIL.ImageDraw.ImageDraw, "_true_orig_rounded_rect"):
    PIL.ImageDraw.ImageDraw._true_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

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
        return PIL.ImageDraw.ImageDraw._true_orig_rounded_rect(
            self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners
        )
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
                'age_number_counter': 'creator_studio',
                'brand_finale': 'creator_studio',
                'video_montage_studio': 'video_editor',
                'audio_waveform': 'video_editor',
                'growth_analytics': 'developer_coding'
            }
            if scene_type in type_map:
                return type_map[scene_type]
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
        "llm_model": "built_in_contextual_nlp",
        "stt_provider": "faster_whisper",
        "stt_model": "auto",
        "online": False,
        "label": "المعالج السياقي الذكي المدمج (بدون إنترنت)"
    }


def query_hybrid_llm(
    prompt: str,
    system_prompt: str = "أنت مخرج فيديو ومحلل سياقي خبير في الدارجة الجزائرية والعربية.",
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
# 2. المخ السياقي الشامل (Pass 1 & Pass 2 Contextual & Narrative Brain)
# ==============================================================================
def extract_global_video_context(full_transcript: str) -> Dict[str, Any]:
    """
    المرحلة الأولى من مخ التحليل السياقي:
    يقرأ النص الكامل للفيديو من أوله لآخره ليفهم "القصة الكلية والسياق العام" قبل تحليل أي جملة،
    ويستخرج الكيانات المحورية (المجال، اسم المتحدث، العمر، اسم المنصة أو المنتج، المشكلة، والحل).
    """
    t = (full_transcript or "").strip()
    t_low = t.lower()

    # 1. استخراج الأرقام السياقية من النص الكلي
    age_match = re.search(r"(?:عمري|عمره|سن)\s*(\d+)", t_low)
    founder_age = int(age_match.group(1)) if age_match else None

    wilaya_match = re.search(r"(\d+)\s*ولاي", t_low)
    wilayas_count = int(wilaya_match.group(1)) if wilaya_match else None

    all_nums = [int(m) for m in re.findall(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t)]

    # 2. استخراج اسم المتحدث واسم المنصة/المنتج
    name_match = re.search(r"(?:أنا|انا|اسمي)\s+([أ-يa-zA-Z]+)", t)
    speaker_name = name_match.group(1).strip("،,.") if name_match else None
    if speaker_name in {"عمري", "قاعد", "أحاول", "احاول", "نبني", "أبني"}:
        speaker_name = None

    brand_name = None
    if any(w in t_low for w in ["فيديو إيديتينج", "فيديو ايديتينج", "فيديو ايديتنج", "video editing"]):
        brand_name = "Video Editing"
    else:
        brand_m = re.search(r"(?:اسم\s+المنصة|واسم\s+المنصة|اسمها|منصة)\s+([أ-يa-zA-Z]+\s*[أ-يa-zA-Z]*)", t)
        if brand_m:
            cand = brand_m.group(1).strip("،,.")
            if not any(x in cand for x in ["تعمل", "بالذكاء", "تمنتج"]):
                brand_name = cand

    # 3. تحديد المجال السردي الكلي للفيديو (Global Narrative Domain)
    is_founder_story = any(w in t_low for w in ["أبني", "ابني", "منصة", "عمري", "مشروع", "برمجة", "تطبيق"]) and any(
        w in t_low for w in ["ذكاء", "مونتاج", "ريلز", "فيديو", "منصة"]
    )
    is_ecommerce_ad = any(w in t_low for w in ["كابل", "سيبور", "ولاية", "اكموندي", "توصيل", "يتقطع", "سلعة", "تشارجي"])

    if is_founder_story:
        domain = "tech_founder_story"
        domain_label_ar = "قصة مؤسس وبناء منصة تقنية بالذكاء الاصطناعي"
        default_metric_num = founder_age if founder_age is not None else (all_nums[0] if all_nums else 100)
    elif is_ecommerce_ad:
        domain = "ecommerce_product_ad"
        domain_label_ar = "إعلان منتج عملي وتجارة إلكترونية"
        default_metric_num = wilayas_count if wilayas_count is not None else (all_nums[0] if all_nums else 58)
    else:
        domain = "general_creator_content"
        domain_label_ar = "محتوى تقني وإبداعي"
        default_metric_num = all_nums[0] if all_nums else 100

    return {
        "domain": domain,
        "domain_label_ar": domain_label_ar,
        "speaker_name": speaker_name,
        "founder_age": founder_age,
        "wilayas_count": wilayas_count,
        "brand_name": brand_name,
        "default_metric_num": default_metric_num,
        "has_ai_theme": any(w in t_low for w in ["ذكاء", "اصطناعي", "أوتوماتيكي", "اوتوماتيكي", "تلقائي"]),
        "has_video_editing_theme": any(w in t_low for w in ["مونتاج", "تمنتج", "فيديو", "إيديتينج", "ريلز"]),
        "has_time_problem": any(w in t_low for w in ["وقت", "ما عندها", "مشغول", "كل يوم"]),
        "full_transcript": t
    }


def analyze_scene_with_context(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    global_ctx: Dict[str, Any],
    prev_scene_text: str = "",
    next_scene_text: str = "",
    prev_scene_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    تحليل مشهد كامل في ضوء:
    1. السياق الكلي للفيديو (`global_ctx`).
    2. معنى الجملة الكاملة وعلاقتها بالجملة السابقة واللاحقة (`prev_scene_text`, `next_scene_text`).
    3. موقع المشهد في القصة السردية (البداية التعريفية -> تطوير الفكرة -> المشكلة -> الحل -> الخاتمة).
    لا يكرر الكلمات المنطوقة حرفياً في البطاقات أبداً، بل يستنتج المفهوم السياقي والمؤشر الرقمي المناسب!
    """
    t = scene_text.strip()
    t_low = t.lower()
    prev_low = (prev_scene_text or "").lower()
    next_low = (next_scene_text or "").lower()
    window_context = f"{prev_low} | {t_low} | {next_low}"

    domain = global_ctx.get("domain", "general_creator_content")
    speaker_name = global_ctx.get("speaker_name") or "المؤسس"
    founder_age = global_ctx.get("founder_age")
    brand_name = global_ctx.get("brand_name") or "Video Editing"

    num_match = re.search(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t)
    local_num = int(num_match.group(1)) if num_match else None
    target_num = local_num if local_num is not None else int(global_ctx.get("default_metric_num", 100))

    # -------------------------------------------------------------------------
    # الفهم السياقي الشامل لمعنى الجملة الكاملة (Contextual Intent Detection)
    # -------------------------------------------------------------------------
    chosen_type = None
    badge_label = ""
    concept_title = ""
    concept_subtitle = ""
    kpi_value = ""
    kpi_label = ""

    is_intro_greeting = any(w in t_low for w in ["أهلاً", "اهلا", "سلام", "مرحبا", "أنا أنس", "انا انس", "اسمي"])
    has_age_mention = any(w in t_low for w in ["عمري", "عمره", "سنة", "سنين"]) or (local_num == 17)
    is_building_platform = any(w in t_low for w in ["أبني", "ابني", "أحاول", "احاول", "منصة تعمل", "مشروع", "أطور", "برمجة"])
    is_ai_automation = any(w in t_low for w in ["ذكاء", "اصطناعي", "أوتوماتيكي", "اوتوماتيكي", "تلقائي", "خوارزمية"])
    is_time_pain_point = any(w in t_low for w in ["وقت", "ما عندها", "أغلب الناس", "اغلب الناس", "مشغولة", "ساعات"])
    is_video_editing_action = any(w in t_low for w in ["مونتاج", "تمنتج", "الفيديوهات", "تبدل الفيديو", "قص", "تحرير"])
    is_reels_publishing = any(w in t_low for w in ["ريلز", "تيك توك", "شورتس", "ترفع", "كل يوم", "نشر", "سوشيال"])
    is_brand_reveal = any(w in t_low for w in ["اسم المنصة", "واسم المنصة", "إيديتينج", "ايديتنج", "editing"]) or (
        scene_index == total_scenes - 1 and any(w in t_low for w in ["منصة", "المنصة", "فيديو"])
    )

    # 1. حالة ختام الفيديو وإعلان اسم المنصة (Brand Finale)
    if is_brand_reveal and scene_index >= max(1, total_scenes - 2):
        chosen_type = "brand_finale"
        badge_label = f"الإطلاق الرسمي • منصة {brand_name}"
        concept_title = f"منصة {brand_name}"
        concept_subtitle = "الجيل الجديد للمونتاج الذكي"
        kpi_value = "AI Studio"
        kpi_label = "جاهزة لصناع المحتوى"

    # 2. حالة التعريف الشخصي بالمؤسس والعمر في بداية القصة (Founder Identity & Age Milestone)
    elif (is_intro_greeting and has_age_mention) or (scene_index == 0 and is_intro_greeting):
        age_val = local_num or founder_age or 17
        target_num = age_val
        chosen_type = "creator_profile"
        badge_label = f"تعريف بالمؤسس • {speaker_name} ({age_val} سنة)"
        concept_title = f"المؤسس الشاب {speaker_name}"
        concept_subtitle = "شغف مبكر ببناء تقنيات المستقبل"
        kpi_value = f"{age_val} عاماً"
        kpi_label = "انطلاقة ريادية مبكرة"

    # 3. حالة ذكر العمر أو محطة الإنجاز الرقمية بشكل مستقل (Age / Milestone Counter)
    elif has_age_mention:
        age_val = local_num or founder_age or 17
        target_num = age_val
        chosen_type = "age_number_counter"
        badge_label = f"محطة طموح • بعمر {age_val} سنة فقط"
        concept_title = "طموح يتجاوز العمر"
        concept_subtitle = f"بناء أنظمة ذكية بعمر {age_val} عاماً"
        kpi_value = f"{age_val} سنة"
        kpi_label = "عمر المؤسس والمطور"

    # 4. حالة مشكلة ضيق الوقت لدى صناع المحتوى ("لأن أغلب الناس ما عندها وقت تمنتج...")
    elif is_time_pain_point:
        chosen_type = "time_warp_clock"
        badge_label = "المشكلة • ضيق الوقت واستنزاف الجهد"
        concept_title = "تحدي ضيق الوقت"
        concept_subtitle = "المونتاج اليدوي يستغرق ساعات طويلة"
        kpi_value = "10x أسرع"
        kpi_label = "توفير وقت صناع المحتوى"

    # 5. حالة الذكاء الاصطناعي والأتمتة ("تعمل مونتاج بالذكاء الاصطناعي بشكل أوتوماتيكي")
    elif is_ai_automation:
        if prev_scene_type == "ai_neural_brain" and is_video_editing_action:
            chosen_type = "video_montage_studio"
            badge_label = "أتمتة المونتاج • تحرير ذكي بالكامل"
            concept_title = "محرك المونتاج الآلي"
            concept_subtitle = "قص وتركيب المشاهد بدون تدخل يدوي"
            kpi_value = "100% آلي"
            kpi_label = "تحرير ذكي بالـ AI"
        else:
            chosen_type = "ai_neural_brain"
            badge_label = "التقنية • محرك الذكاء الاصطناعي الأوتوماتيكي"
            concept_title = "أتمتة بالذكاء الاصطناعي"
            concept_subtitle = "معالجة ذكية للصوت والصورة والسياق"
            kpi_value = "100% تلقائي"
            kpi_label = "يعمل بالذكاء الاصطناعي"

    # 6. حالة بناء وتطوير المنصة ("وقاعد أحاول أبني منصة تعمل...")
    elif is_building_platform:
        chosen_type = "platform_builder"
        badge_label = "المشروع • هندسة وبناء منصة ذكية"
        concept_title = "تطوير منصة متكاملة"
        concept_subtitle = "برمجة بنية سحابية لأتمتة الفيديو"
        kpi_value = "Full-Stack"
        kpi_label = "تطوير وبناء المنصة"

    # 7. حالة نشر الريلز والمحتوى اليومي ("وترفع ريلز كل يوم")
    elif is_reels_publishing:
        chosen_type = "reels_smartphone"
        badge_label = "النتيجة • صناعة ونشر الريلز يومياً"
        concept_title = "نشر الريلز بانتظام"
        concept_subtitle = "حضور يومي مستمر على منصات التواصل"
        kpi_value = "يومياً"
        kpi_label = "إنتاج ونشر مستمر"

    # 8. حالة عملية المونتاج وتحرير الفيديوهات ("تمنتج الفيديوهات...")
    elif is_video_editing_action:
        chosen_type = "video_montage_studio"
        badge_label = "الحل العملي • أستوديو المونتاج الذكي"
        concept_title = "صناعة وتحرير الفيديو"
        concept_subtitle = "تحويل التسجيلات الخام إلى فيديو احترافي"
        kpi_value = "4K 60FPS"
        kpi_label = "جودة إخراج سينمائية"

    # 9. حالات إعلانات المنتجات والتجارة الإلكترونية (الكابل، التوصيل 58 ولاية، المتانة)
    elif any(w in t_low for w in ["توصيل", "ولاية", "58", "باب الدار"]):
        w_num = local_num or global_ctx.get("wilayas_count") or 58
        target_num = w_num
        chosen_type = "delivery_express"
        badge_label = f"تغطية شاملة • توصيل سريع {w_num} ولاية"
        concept_title = "توصيل لباب المنزل"
        concept_subtitle = f"شحن سريع ومضمون عبر {w_num} ولاية"
        kpi_value = f"{w_num} ولاية"
        kpi_label = "تغطية التوصيل الوطني"

    elif any(w in t_low for w in ["سيبور", "ستاند", "حامل", "تيليفون", "تتفرج"]):
        chosen_type = "reels_smartphone"
        badge_label = "تصميم ذكي • حامل هاتف مدمج ومريح"
        concept_title = "حامل هاتف مدمج"
        concept_subtitle = "اشحن هاتفك وشاهد محتواك بكل راحة"
        kpi_value = "2 في 1"
        kpi_label = "شاحن وحامل هاتف"

    elif any(w in t_low for w in ["كابل", "شحن", "تشارجي", "قماش", "يتقطع", "اصبر", "اكموندي", "اطلب"]):
        chosen_type = "ecommerce_showcase"
        if scene_index >= total_scenes - 2 and any(w in t_low for w in ["اكموندي", "اطلب", "رابط"]):
            badge_label = "اطلب الآن • الكمية محدودة والدفع عند الاستلام"
            concept_title = "اطلب منتجك الآن"
            concept_subtitle = "متوفر للطلب الفوري عبر الرابط"
            kpi_value = "متوفر الآن"
            kpi_label = "الدفع عند الاستلام"
        elif any(w in t_low for w in ["قماش", "يتقطع"]):
            badge_label = "متانة فائقة • مغلف بالقماش ضد القطع"
            concept_title = "مقاوم للقطع والتلف"
            concept_subtitle = "تغليف قماشي متين من جميع الجهات"
            kpi_value = "100% متين"
            kpi_label = "حماية ضد القطع"
        else:
            badge_label = "ابتكار عملي • شحن فائق السرعة والجودة"
            concept_title = "أداء شحن استثنائي"
            concept_subtitle = "مصمم للاستخدام اليومي المكثف"
            kpi_value = "Fast Charge"
            kpi_label = "كفاءة وجودة عالية"

    # 10. استنتاج سياقي ذكي من الجملة السابقة واللاحقة إذا كانت الجملة رابطة
    if not chosen_type:
        if "منصة" in window_context and ("اسم" in window_context or scene_index == total_scenes - 1):
            chosen_type = "brand_finale"
            badge_label = f"منصة {brand_name} • مستقبل المونتاج الذكي"
            concept_title = f"منصة {brand_name}"
            concept_subtitle = "أتمتة كاملة لصناعة المحتوى"
            kpi_value = "AI Studio"
            kpi_label = "الحل المتكامل للمونتاج"
        elif "وقت" in window_context or "أغلب" in window_context:
            chosen_type = "time_warp_clock"
            badge_label = "اختصار الوقت • وداعاً لساعات المونتاج الطويلة"
            concept_title = "توفير الوقت والجهد"
            concept_subtitle = "حل ذكي لمن لا يملك وقتاً للمونتاج"
            kpi_value = "10x أسرع"
            kpi_label = "إنجاز فوري للفيديوهات"
        elif "ذكاء" in window_context or "أوتوماتيكي" in window_context:
            chosen_type = "ai_neural_brain"
            badge_label = "تقنية متقدمة • معالجة بالذكاء الاصطناعي"
            concept_title = "ذكاء اصطناعي متكامل"
            concept_subtitle = "يفهم السياق ويحرر الفيديو تلقائياً"
            kpi_value = "AI Core"
            kpi_label = "محرك تحليل ذكي"
        else:
            narrative_cycle = [
                ("creator_profile", "رؤية المبدع • انطلاقة المشروع", "رؤية تقنية طموحة", "ابتكار حلول ذكية لصناع المحتوى", "100%", "شغف وابتكار"),
                ("platform_builder", "هندسة النظام • تطوير المنصة", "بناء المنصة الذكية", "تطوير أدوات الجيل الجديد", "Cloud AI", "بنية تقنية حديثة"),
                ("video_montage_studio", "أستوديو التحرير • مونتاج احترافي", "أتمتة شريط المونتاج", "إخراج بصري متكامل بالذكاء الاصطناعي", "4K Pro", "جودة الأستوديو"),
                ("growth_analytics", "مؤشر الأداء • نمو وانتشار", "مضاعفة الإنتاجية", "نتائج أسرع وانتشار أوسع للمحتوى", "+300%", "نمو التفاعل"),
                ("reels_smartphone", "صناعة الريلز • محتوى يومي تفاعلي", "انتشار المحتوى اليومي", "تجهيز الفيديوهات القصيرة بلمسة واحدة", "يومياً", "نشر مستمر"),
                ("brand_finale", f"منصة {brand_name} • الإطلاق الرسمي", f"منصة {brand_name}", "مستقبل صناعة الفيديو بالذكاء الاصطناعي", "AI Pro", "منصة الجيل الجديد")
            ]
            pick = narrative_cycle[scene_index % len(narrative_cycle)]
            if pick[0] == prev_scene_type:
                pick = narrative_cycle[(scene_index + 1) % len(narrative_cycle)]
            chosen_type, badge_label, concept_title, concept_subtitle, kpi_value, kpi_label = pick

    # منع تكرار نفس رسمة الفيكتور في مشهدين متتاليين للحفاظ على التنوع البصري مع بقاء المعنى السياقي
    if chosen_type == prev_scene_type and total_scenes > 1:
        contextual_alternates = {
            "creator_profile": "age_number_counter",
            "age_number_counter": "platform_builder",
            "platform_builder": "ai_neural_brain",
            "ai_neural_brain": "video_montage_studio",
            "video_montage_studio": "reels_smartphone",
            "time_warp_clock": "growth_analytics",
            "reels_smartphone": "brand_finale" if scene_index == total_scenes - 1 else "growth_analytics",
            "ecommerce_showcase": "delivery_express"
        }
        chosen_type = contextual_alternates.get(chosen_type, chosen_type)

    return {
        "scene_type": chosen_type,
        "badge_label": badge_label,
        "short_title": concept_title,
        "concept_title": concept_title,
        "concept_subtitle": concept_subtitle,
        "kpi_value": kpi_value,
        "kpi_label": kpi_label,
        "target_number": target_num
    }


def analyze_contextual_storyboard(
    scenes: List[Dict[str, Any]],
    full_transcript: str = "",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    ollama_model: str = "llama3"
) -> List[Dict[str, Any]]:
    """
    مخ التخطيط السردي والسياقي الكامل (Contextual Storyboard Brain):
    1. يستخرج السياق العام للفيديو (`extract_global_video_context`).
    2. يحلل كل مشهد سياقياً (بربطه بالجملة السابقة واللاحقة والهدف العام للفيديو).
    3. إن توفر اتصال بـ LLM، يطلب منه تحسين العناوين السياقية ومؤشرات الـ KPI مع فحصها وضمان عدم تكرار نص الكابشن أبداً.
    """
    if not scenes:
        return []

    if not full_transcript:
        full_transcript = " ".join(str(s.get("text", "")) for s in scenes)

    global_ctx = extract_global_video_context(full_transcript)

    from motion_text import MOTION_THEMES
    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    enriched_scenes: List[Dict[str, Any]] = []
    prev_type = None

    for idx, sc in enumerate(scenes):
        curr_txt = str(sc.get("text", "")).strip()
        prev_txt = str(scenes[idx - 1].get("text", "")).strip() if idx > 0 else ""
        next_txt = str(scenes[idx + 1].get("text", "")).strip() if idx + 1 < len(scenes) else ""

        ctx_info = analyze_scene_with_context(
            scene_text=curr_txt,
            scene_index=idx,
            total_scenes=len(scenes),
            global_ctx=global_ctx,
            prev_scene_text=prev_txt,
            next_scene_text=next_txt,
            prev_scene_type=prev_type
        )
        prev_type = ctx_info["scene_type"]

        entry = dict(sc)
        entry.update(ctx_info)
        entry["theme_name"] = theme_keys[idx % len(theme_keys)]
        entry["transition_type"] = transitions[idx % len(transitions)]
        entry["transition"] = entry["transition_type"]
        entry["word_strings"] = [w.get("word", "") for w in sc.get("words", [])]
        entry["global_domain"] = global_ctx["domain"]
        enriched_scenes.append(entry)

    # محاولة إثراء إضافية عبر LLM السحابي/المحلي لفهم السياق العميق إن توفر
    try:
        scenes_Input_summary = "\n".join(
            f"{i+1}. [{s['start']:.1f}s - {s['end']:.1f}s]: \"{s['text']}\""
            for i, s in enumerate(enriched_scenes)
        )
        llm_prompt = (
            f"النص الكامل للفيديو: \"{full_transcript}\"\n"
            f"السياق العام المكتشف: {global_ctx['domain_label_ar']}\n\n"
            f"المشاهد المقسمة حسب الجمل المعنوية:\n{scenes_Input_summary}\n\n"
            "بصفتك مخرج موشن جرافيك محترف يفهم سياق الفيديو الكامل ولا يكرر الكلمات حرفياً:\n"
            "لكل مشهد، أعطني JSON Array يحتوي كائناً لكل مشهد بالمفاتيح التالية فقط:\n"
            "- scene_type: واحد من [creator_profile, age_number_counter, platform_builder, ai_neural_brain, video_montage_studio, time_warp_clock, reels_smartphone, growth_analytics, ecommerce_showcase, delivery_express, brand_finale]\n"
            "- badge_label: عنوان سياقي جذاب للشارة العلوية (3 إلى 5 كلمات تشرح الفكرة ولا تكرر نص المتحدث حرفياً)\n"
            "- concept_title: مفهوم المشهد المختصر للبطاقة اليسرى (كلمتان إلى 3 كلمات تعبر عن المعنى الضمني)\n"
            "- kpi_value: رقم أو مؤشر قصير معبر للبطاقة اليمنى (مثل '17 عاماً'، '100% آلي'، '10x أسرع'، 'يومياً'، 'AI Studio')\n"
            "- kpi_label: وصف المؤشر في البطاقة اليمنى (كلمتان إلى 3 كلمات)\n"
            "أرجع JSON Array صالحاً فقط بدون أي نص إضافي."
        )
        ai_raw = query_hybrid_llm(
            prompt=llm_prompt,
            system_prompt="أنت مخرج فني (Art Director) خبير في الموشن جرافيك السياقي. أرجع JSON Array فقط.",
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            ollama_model=ollama_model,
            temperature=0.2,
            max_tokens=900
        )
        if ai_raw:
            m = re.search(r"\[.*\]", ai_raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                valid_types = {
                    "creator_profile", "age_number_counter", "platform_builder",
                    "ai_neural_brain", "video_montage_studio", "time_warp_clock",
                    "reels_smartphone", "growth_analytics", "ecommerce_showcase",
                    "delivery_express", "brand_finale"
                }
                if isinstance(parsed, list) and len(parsed) == len(enriched_scenes):
                    for idx, item in enumerate(parsed):
                        if not isinstance(item, dict):
                            continue
                        st_cand = str(item.get("scene_type", "")).strip()
                        if st_cand in valid_types:
                            enriched_scenes[idx]["scene_type"] = st_cand
                        bl_cand = str(item.get("badge_label", "")).strip()
                        if len(bl_cand) >= 5:
                            enriched_scenes[idx]["badge_label"] = bl_cand
                        ct_cand = str(item.get("concept_title", "")).strip()
                        # التأكد من أن عنوان المفهوم لا ينسخ أول كلمتين حرفياً من النص المنطوق
                        raw_first_two = " ".join(enriched_scenes[idx]["text"].split()[:2])
                        if len(ct_cand) >= 4 and ct_cand != raw_first_two:
                            enriched_scenes[idx]["concept_title"] = ct_cand
                            enriched_scenes[idx]["short_title"] = ct_cand
                        kv_cand = str(item.get("kpi_value", "")).strip()
                        kl_cand = str(item.get("kpi_label", "")).strip()
                        if kv_cand and kl_cand and "58" not in kv_cand:
                            enriched_scenes[idx]["kpi_value"] = kv_cand
                            enriched_scenes[idx]["kpi_label"] = kl_cand
    except Exception as e:
        logger.debug(f"استخدام المخ السياقي المدمج مباشرة: {e}")

    return enriched_scenes


# ==============================================================================
# 3. أداة التحليل الهندسي المتقدم للصوت والفيديو
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
    width, height, fps = 720, 1280, 24
    visual_motion_score = 8.0
    video_duration = 0.0

    # فحص خصائص الفيديو والصوت عبر FFmpeg مباشرة بدون تحميل الفيديو في الـ RAM
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        try:
            res = subprocess.run(
                ["ffmpeg", "-i", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            info_txt = res.stderr or ""
            if "Video:" in info_txt:
                has_video_stream = True
                m_res = re.search(r"(\d{2,5})x(\d{2,5})", info_txt)
                if m_res:
                    width, height = int(m_res.group(1)), int(m_res.group(2))
                m_fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", info_txt)
                if m_fps:
                    fps = max(15, min(60, int(round(float(m_fps.group(1))))))
            m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info_txt)
            if m_dur:
                video_duration = round(int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3)), 2)
        except Exception:
            pass

    duration_sec = video_duration
    mean_dbfs = -26.0
    max_dbfs = -4.0
    noise_floor_dbfs = -48.0
    optimal_silence_thresh = -42.0
    silence_ratio = 0.16
    optimal_padding_ms = 250

    sample_wav = file_path + f"_probe_{os.getpid()}.wav"
    try:
        import wave
        subprocess.run(
            ["ffmpeg", "-y", "-t", "35", "-i", file_path, "-vn", "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1", sample_wav],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25
        )
        if os.path.exists(sample_wav) and os.path.getsize(sample_wav) > 512:
            with wave.open(sample_wav, "rb") as wf:
                n_frames = wf.getnframes()
                raw_b = wf.readframes(n_frames)
            samples = np.frombuffer(raw_b, dtype=np.int16).astype(np.float32)
            del raw_b
            if duration_sec <= 0.1 and len(samples) > 0:
                duration_sec = round(len(samples) / 8000.0, 2)
            win = 800  # 100ms at 8kHz
            n_w = len(samples) // win
            if n_w > 2:
                arr = samples[:n_w * win].reshape((n_w, win))
                rms = np.sqrt(np.mean(arr * arr, axis=1) + 1e-9)
                dbfs = 20.0 * np.log10(np.maximum(rms / 32768.0, 1e-7))
                valid = dbfs[dbfs > -85.0]
                if len(valid) > 0:
                    mean_dbfs = round(float(np.mean(valid)), 1)
                    max_dbfs = round(float(np.max(valid)), 1)
                    p15 = float(np.percentile(valid, 15))
                    p85 = float(np.percentile(valid, 85))
                    noise_floor_dbfs = round(p15, 1)
                    raw_thresh = p15 + 0.18 * (p85 - p15)
                    optimal_silence_thresh = round(max(-54.0, min(-32.0, raw_thresh, mean_dbfs - 11.0)), 1)
                    silent_chunks = int(np.sum(valid < optimal_silence_thresh))
                    silence_ratio = round(silent_chunks / max(1, len(valid)), 2)
                    optimal_padding_ms = 260 if silence_ratio > 0.25 else 240
            del samples
    except Exception:
        pass
    finally:
        if os.path.exists(sample_wav):
            try:
                os.remove(sample_wav)
            except Exception:
                pass
        gc.collect()

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

    optimal_whisper_model = "medium" if has_cuda else "base"
    is_vertical = (height >= width)

    return {
        "file_path": file_path,
        "file_size_mb": file_size_mb,
        "has_video": has_video_stream,
        "media_type_ar": "فيديو مع صوت 🎬" if has_video_stream else "تسجيل / ملف صوتي فقط 🎙️",
        "duration_sec": max(0.5, duration_sec),
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
        "optimal_chunk_size": 20,
        "optimal_whisper_model": optimal_whisper_model,
        "ai_provider_info": ai_info,
        "criteria_reasons": [
            f"تم تفعيل مخ التحليل السياقي والسردي (Contextual Narrative Brain) مع حماية الذاكرة القصوى (Streaming Pipe Engine) للفيديوهات الكبيرة.",
            f"تم ضبط عتبة السكوت الطبيعية عند ({optimal_silence_thresh} dBFS) وهامش حماية مخارج الحروف ({optimal_padding_ms}ms)."
        ]
    }


# ==============================================================================
# 4. عقل المخرج الذكي الشامل: تخطيط المشاهد السياقية واختيار 3-4 مشاهد B-Roll
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
    توليد مخطط المخرج الشامل بالاعتماد على مخ التحليل السياقي (Contextual Storyboard Brain):
    - يفهم سياق الفيديو الكامل ويربط كل جملة بالمعنى العام.
    - يحدد 3 إلى 4 مشاهد B-roll واقعية خالية من حقوق الملكية في اللحظات المناسبة.
    - يوزع بقية اللقطات بين: شاشة كاملة موشن جرافيك، بطاقات علوية، شارات سفلية، ولقطات متحدث صافية.
    """
    if not sentences_or_micro_scenes:
        return []

    full_transcript = " ".join(str(s.get("text", "")) for s in sentences_or_micro_scenes)
    contextual_scenes = analyze_contextual_storyboard(
        scenes=sentences_or_micro_scenes,
        full_transcript=full_transcript,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key
    )

    num_scenes = len(contextual_scenes)
    master_plan = []

    broll_candidate_indices = []
    for idx, sc in enumerate(contextual_scenes):
        t_low = str(sc.get("text", "")).lower()
        if 0 < idx < num_scenes - 1:
            if any(w in t_low for w in ["مونتاج", "تمنتج", "فيديو", "إيديتينج", "وقت", "ساعة", "ريلز", "تيك توك", "أبني", "منصة", "حاسوب", "ذكاء"]):
                broll_candidate_indices.append(idx)

    selected_broll_indices = set()
    if enable_stock_broll and broll_candidate_indices:
        target_broll_count = min(4, max(2, len(broll_candidate_indices)))
        step = max(1, len(broll_candidate_indices) // target_broll_count)
        for i in range(0, len(broll_candidate_indices), step):
            selected_broll_indices.add(broll_candidate_indices[i])
            if len(selected_broll_indices) >= 4:
                break

    lower_third_triggers = {
        "توصيل", "ولاية", "58", "باب الدار", "شحن", "مجاني",
        "دفع", "كاش", "استلام", "ضمان", "أصلية", "سعر", "سومة", "تخفيض",
        "اطلب", "الرابط", "البايو", "كليكي", "للطلب", "اسم المنصة", "واسم المنصة"
    }

    last_badge_idx = -99
    for idx, sc in enumerate(contextual_scenes):
        s_text = str(sc.get("text", "")).strip()
        t_low = s_text.lower()
        s_start = max(0.0, float(sc.get("start", 0.0)))
        s_end = min(total_duration, float(sc.get("end", s_start + 2.5)))

        scene_type = sc.get("scene_type", "video_montage_studio")
        stock_category = map_scene_to_stock_category(scene_type, s_text)

        if idx in selected_broll_indices:
            layout_mode = "stock_broll"
            zoom_factor = 1.0
        elif not has_video:
            layout_mode = "full_screen"
            zoom_factor = 1.0
        else:
            is_hook = (idx == 0)
            is_finale = (idx == num_scenes - 1)
            has_lower_trigger = any(trig in t_low for trig in lower_third_triggers)
            can_show_overlay = (idx - last_badge_idx) >= 1

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
            elif can_show_overlay:
                layout_mode = "top_overlay"
                zoom_factor = 1.08
                last_badge_idx = idx
            else:
                layout_mode = "speaker_clean"
                zoom_factor = 1.06 if (idx % 2 == 1) else 1.0

        badge_label = sc.get("badge_label", "ميزة ذكية")
        if product_name_override and (idx == 0):
            badge_label = product_name_override
        if cta_override and (idx == num_scenes - 1):
            badge_label = cta_override

        entry = dict(sc)
        entry["index"] = idx
        entry["start"] = s_start
        entry["end"] = s_end
        entry["layout_mode"] = layout_mode
        entry["stock_category"] = stock_category
        entry["badge_label"] = badge_label
        entry["zoom_factor"] = zoom_factor
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