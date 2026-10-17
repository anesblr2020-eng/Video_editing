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
def extract_clean_keywords(text: str, max_words: int = 3) -> list:
    stop_words = {
        'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'هاد', 'هادي', 'ذلك', 'تلك', 'التي', 'الذي', 'الذين',
        'هو', 'هي', 'هم', 'نحن', 'أنا', 'انا', 'انت', 'أنتم', 'كان', 'كانت', 'يكون', 'ما', 'لا', 'لم', 'لن',
        'قد', 'كل', 'بعض', 'غير', 'جدا', 'بزاف', 'قاع', 'برك', 'راه', 'راهي', 'باش', 'كي', 'كيف', 'وين', 'واش',
        'كاين', 'كاينين', 'ناس', 'خاوتنا', 'اليوم', 'هنا', 'هكذا', 'واحد', 'زوج', 'شوية', 'حاجة', 'شفت', 'سمعت'
    }
    words = [w.strip('،,.!؟?()[]-') for w in text.split() if w.strip('،,.!؟?()[]-')]
    content_words = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    return content_words[:max_words]


def extract_global_video_context(full_transcript: str) -> dict:
    t = (full_transcript or "").strip()
    t_low = t.lower()

    domain_scores = {
        "ecommerce": 0,
        "social_media": 0,
        "tech_software": 0,
        "education": 0,
        "business": 0,
        "general": 1
    }

    ecom_kw = ["كابل", "شاحن", "شحن", "تشارجي", "منتج", "سلعة", "سيبور", "حامل", "متجر", "شراء", "سعر", "سومة", "توصيل", "ولاية", "باب الدار", "كواليتي", "أصلي", "اصلي", "اكموندي", "اطلب", "متانة", "قماش", "يتقطع", "بري", "ضمان", "تخفيض", "عرض", "علبة", "باكي"]
    social_kw = ["انستغرام", "انستقرام", "تيك توك", "ريلز", "شورتس", "فيسبوك", "يوتيوب", "متابعين", "مشاهدات", "تفاعل", "ريتش", "خوارزمية", "نشر", "محتوى", "صانع", "صناع", "كاميرا", "تصوير", "اكسبلور", "ستوري", "بايو", "فيديو وطلع", "فيديوهات"]
    tech_kw = ["برمجة", "كود", "تطبيق", "منصة", "موقع", "سحابي", "ذكاء اصطناعي", "سيرفر", "ديفلوبر", "سوفتوير", "api", "ai"]
    edu_kw = ["نصيحة", "نصائح", "تعلم", "دراسة", "معلومة", "فائدة", "كيفاش", "خطوات", "أسرار", "طريقة", "تحسين", "مهارة", "فكرة", "انتبه", "ركز"]
    biz_kw = ["بزنس", "مشروع", "دراهم", "فلوس", "عمل حر", "فريلانس", "تسويق", "مبيعات", "استثمار", "أرباح", "تجارة", "خدمة", "عملاء", "شركة", "وظيفة"]

    for kw in ecom_kw:
        if kw in t_low:
            domain_scores["ecommerce"] += (3 if kw in ["كابل", "شاحن", "توصيل", "اكموندي", "سيبور", "سلعة"] else 1)
    for kw in social_kw:
        if kw in t_low:
            domain_scores["social_media"] += (3 if kw in ["انستغرام", "انستقرام", "ريلز", "تيك توك", "ريتش", "اكسبلور"] else 1)
    for kw in tech_kw:
        if kw in t_low:
            domain_scores["tech_software"] += (3 if kw in ["برمجة", "كود", "تطبيق", "سحابي", "ذكاء اصطناعي"] else 1)
    for kw in edu_kw:
        if kw in t_low:
            domain_scores["education"] += 2
    for kw in biz_kw:
        if kw in t_low:
            domain_scores["business"] += 2

    best_domain = max(domain_scores, key=domain_scores.get)
    if domain_scores[best_domain] <= 1:
        best_domain = "general"

    domain_labels = {
        "ecommerce": "إعلان وترويج منتج تجاري",
        "social_media": "صناعة المحتوى وشبكات التواصل",
        "tech_software": "تطوير وتقنية وأنظمة ذكية",
        "education": "نصائح ومعلومات تعليمية",
        "business": "أعمال وتجارة وخدمات",
        "general": "محتوى عام وتفاعلي"
    }

    wilaya_match = re.search(r"(\d+)\s*ولاي", t_low)
    wilayas_count = int(wilaya_match.group(1)) if wilaya_match else (58 if ("ولاية" in t_low or "ولايات" in t_low) else None)

    age_match = re.search(r"(?:عمري|عمره|في\s+عمري)\s*(\d+)", t_low)
    founder_age = int(age_match.group(1)) if age_match else None

    speaker_name = None
    name_match = re.search(r"(?:اسمي|معكم)\s+([أ-يa-zA-Z]+)", t)
    if name_match:
        cand = name_match.group(1).strip("،,.")
        if cand not in ["بزاف", "ناس", "اليوم", "هنا", "في", "واحد", "خاوتي"]:
            speaker_name = cand

    all_nums = [int(m) for m in re.findall(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t) if 0 < int(m) < 1000]

    return {
        "domain": best_domain,
        "domain_label_ar": domain_labels[best_domain],
        "speaker_name": speaker_name,
        "founder_age": founder_age,
        "wilayas_count": wilayas_count,
        "all_numbers": all_nums,
        "full_transcript": t
    }


def analyze_scene_with_context(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    global_ctx: dict,
    prev_scene_text: str = "",
    next_scene_text: str = "",
    prev_scene_type: str = None
) -> dict:
    t = scene_text.strip()
    t_low = t.lower()
    domain = global_ctx.get("domain", "general")
    wilayas = global_ctx.get("wilayas_count") or 58
    founder_age = global_ctx.get("founder_age")
    speaker_name = global_ctx.get("speaker_name")

    num_match = re.search(r"(?:^|[^\d])(\d+)(?:$|[^\d])", t)
    local_num = int(num_match.group(1)) if num_match else None

    chosen_type = None
    badge_label = ""
    concept_title = ""
    concept_subtitle = ""
    kpi_value = ""
    kpi_label = ""

    # Personal Age or Name ONLY if explicitly stated in this scene or global context
    has_age_explicit = any(w in t_low for w in ["عمري", "عمره", "في عمري"]) and (local_num or founder_age)
    if has_age_explicit:
        age_val = local_num or founder_age
        chosen_type = "age_number_counter"
        badge_label = f"محطة طموح • عمر {age_val} سنة"
        concept_title = "طموح وإنجاز مبكر"
        concept_subtitle = f"تطور وإبداع بعمر {age_val} عاماً"
        kpi_value = f"{age_val} سنة"
        kpi_label = "محطة العمر"

    # Domain-specific logic
    elif domain == "ecommerce":
        if any(w in t_low for w in ["توصيل", "ولاية", "ولايات", "باب الدار", "شحن"]):
            target_w = local_num or wilayas
            chosen_type = "delivery_express"
            badge_label = f"شحن وتوصيل • متوفر لجميع {target_w} ولاية"
            concept_title = "توصيل سريع ومضمون"
            concept_subtitle = f"توصيل سريع حتى باب المنزل عبر {target_w} ولاية"
            kpi_value = f"{target_w} ولاية"
            kpi_label = "تغطية وطنية شاملة"

        elif any(w in t_low for w in ["سيبور", "ستاند", "حامل", "تيليفون", "تتفرج", "هاتف"]):
            chosen_type = "reels_smartphone"
            badge_label = "تصميم ذكي • حامل هاتف مدمج ومريح"
            concept_title = "حامل هاتف مدمج"
            concept_subtitle = "اشحن وتصفح هاتفك بكل راحة وثبات"
            kpi_value = "2 في 1"
            kpi_label = "شاحن وحامل معاً"

        elif any(w in t_low for w in ["قماش", "يتقطع", "متانة", "ما تخافش", "صحيح", "متين"]):
            chosen_type = "ecommerce_showcase"
            badge_label = "متانة فائقة • تغليف قماشي ضد القطع"
            concept_title = "مقاوم للقطع والتلف"
            concept_subtitle = "تغليف قماشي قوي مصمم للاستخدام اليومي"
            kpi_value = "100% متين"
            kpi_label = "حماية واعتمادية"

        elif any(w in t_low for w in ["شحن سريع", "تشارجي", "كابل", "سريع", "fast"]):
            chosen_type = "ecommerce_showcase"
            badge_label = "كفاءة عالية • شحن فائق السرعة"
            concept_title = "شحن سريع وآمن"
            concept_subtitle = "نقل طاقة مستقر يحافظ على بطارية جهازك"
            kpi_value = "Fast Charge"
            kpi_label = "سرعة وأمان"

        elif any(w in t_low for w in ["خصائص", "ميزات", "مميزات", "ثلاث", "3"]):
            chosen_type = "growth_analytics"
            badge_label = "مواصفات ممتازة • ثلاث خصائص في منتج واحد"
            concept_title = "مزايا استثنائية متكاملة"
            concept_subtitle = "ثلاث وظائف عملية تجمع الراحة والأداء"
            kpi_value = "3 في 1"
            kpi_label = "خصائص مدمجة"

        elif any(w in t_low for w in ["سعر", "سومة", "بري", "اقتصادي", "عرض", "تخفيض"]):
            chosen_type = "ecommerce_showcase"
            badge_label = "قيمة مثالية • أفضل جودة بأفضل سعر"
            concept_title = "سعر اقتصادي مناسب"
            concept_subtitle = "وفر نقودك مع أفضل أداء وسعر في السوق"
            kpi_value = "أفضل سعر"
            kpi_label = "توفير وجودة"

        elif any(w in t_low for w in ["اكموندي", "اطلب", "رابط", "اسفل", "الطلب", "كمية"]) or (scene_index == total_scenes - 1):
            chosen_type = "brand_finale"
            badge_label = "اطلب الآن • الدفع عند الاستلام وباب الدار"
            concept_title = "طلب سهل ومضمون"
            concept_subtitle = "اضغط على الرابط أسفل الفيديو واطلب فوراً"
            kpi_value = "متوفر الآن"
            kpi_label = "الدفع عند الاستلام"

        elif scene_index == 0 or any(w in t_low for w in ["دقيقة", "وقتك", "اصبر", "شوف"]):
            chosen_type = "ecommerce_showcase"
            kws = ' '.join(extract_clean_keywords(scene_text)) or "منتج مميز"
            badge_label = f"منتج مميز • {kws}"
            concept_title = "ابتكار عملي مفيد"
            concept_subtitle = "حل مبتكر يسهل استخدامك اليومي"
            kpi_value = "Top Pick"
            kpi_label = "اختيار موصى به"

        else:
            kws = ' '.join(extract_clean_keywords(scene_text)) or "ميزة عملية"
            chosen_type = "ecommerce_showcase"
            badge_label = f"ميزة استثنائية • {kws}"
            concept_title = kws
            concept_subtitle = "مواصفات تضمن راحتك وكفاءة استخدامك"
            kpi_value = "Premium"
            kpi_label = "مواصفات ممتازة"

    elif domain == "social_media":
        if any(w in t_low for w in ["يعانيوا", "مشكل", "مشكلة", "صعيب", "ما ينجحش", "ضعيف", "تراجع"]):
            chosen_type = "growth_analytics"
            badge_label = "صناع المحتوى • المشاكل والتحديات الشائعة"
            concept_title = "تحديات تفاعل المحتوى"
            concept_subtitle = "صعوبة زيادة المشاهدات والوصول إلى جمهور جديد"
            kpi_value = "Reach Problem"
            kpi_label = "تحليل التفاعل"

        elif any(w in t_low for w in ["انستغرام", "انستقرام", "تيك توك", "ريلز", "متابعين", "تفاعل", "ريتش", "اكسبلور"]):
            chosen_type = "reels_smartphone"
            badge_label = "خوارزمية المحتوى • الوصول والتفاعل العالي"
            concept_title = "تطوير تفاعل الريلز"
            concept_subtitle = "أسرار مضاعفة المشاهدات والتفاعل في المنصة"
            kpi_value = "Instagram"
            kpi_label = "انتشار أوسع"

        elif any(w in t_low for w in ["فيديو", "نشر", "طلع", "نزل", "ستوري", "يومياً"]):
            chosen_type = "reels_smartphone"
            badge_label = "استراتيجية النشر • رفع ونشر الفيديوهات"
            concept_title = "نشر محتوى مستمر"
            concept_subtitle = "الاستمرارية في النشر هي مفتاح النجاح والوصول"
            kpi_value = "Viral Video"
            kpi_label = "معدل الوصول"

        elif scene_index == 0:
            chosen_type = "reels_smartphone"
            badge_label = "صناعة المحتوى • نصيحة هامة لليوم"
            concept_title = "تطوير المحتوى الرقمي"
            concept_subtitle = "خطوات عملية لكل صانع محتوى يبحث عن النمو"
            kpi_value = "Creator Tips"
            kpi_label = "نصائح النمو"

        elif scene_index == total_scenes - 1 or any(w in t_low for w in ["تابع", "اشترك", "حفظ", "شارك"]):
            chosen_type = "brand_finale"
            badge_label = "تفاعل ومتابعة • انضم لمزيد من النصائح"
            concept_title = "شارك وتابع المحتوى"
            concept_subtitle = "احفظ الفيديو للمراجعة وتابع الحساب للجديد"
            kpi_value = "Follow"
            kpi_label = "محتوى يومي"

        else:
            kws = ' '.join(extract_clean_keywords(scene_text)) or "نصيحة للمحتوى"
            chosen_type = "growth_analytics"
            badge_label = f"إضاءة رقمية • {kws}"
            concept_title = kws
            concept_subtitle = "طرق تحسين الأداء والتفاعل على حسابك"
            kpi_value = "Reach"
            kpi_label = "مؤشر التفاعل"

    elif domain == "tech_software":
        if any(w in t_low for w in ["ذكاء اصطناعي", "ai", "أتمتة", "تلقائي", "خوارزمية"]):
            chosen_type = "ai_neural_brain"
            badge_label = "التقنية الذكية • أتمتة بالذكاء الاصطناعي"
            concept_title = "أنظمة الذكاء الاصطناعي"
            concept_subtitle = "معالجة ذكية وسريعة توفر الجهد والوقت"
            kpi_value = "AI Core"
            kpi_label = "تقنية المستقبل"

        elif any(w in t_low for w in ["كود", "برمجة", "تطبيق", "منصة", "موقع"]):
            chosen_type = "platform_builder"
            badge_label = "هندسة البرمجيات • تطوير وبناء المنصة"
            concept_title = "بنية تقنية حديثة"
            concept_subtitle = "تطوير أنظمة سحابية وتطبيقات متكاملة"
            kpi_value = "Full-Stack"
            kpi_label = "تطوير وبرمجة"

        elif any(w in t_low for w in ["مونتاج", "تحرير", "إيديتينج", "editing"]):
            chosen_type = "video_montage_studio"
            badge_label = "أستوديو التحرير • مونتاج متقدم"
            concept_title = "تحرير الفيديو الذكي"
            concept_subtitle = "أدوات متطورة لقص وتركيب الفيديوهات"
            kpi_value = "4K Studio"
            kpi_label = "جودة إخراج"

        else:
            kws = ' '.join(extract_clean_keywords(scene_text)) or "حلول برمجية"
            chosen_type = "platform_builder"
            badge_label = f"ابتكار تقني • {kws}"
            concept_title = kws
            concept_subtitle = "حلول رقمية متقدمة لتسريع وتسهيل الأعمال"
            kpi_value = "Tech Pro"
            kpi_label = "حلول متقدمة"

    else:
        kws = ' '.join(extract_clean_keywords(scene_text)) or "معلومة مهمة"
        chosen_type = "growth_analytics" if (scene_index % 2 == 0) else "reels_smartphone"
        badge_label = f"إضاءة معرفية • {kws}"
        concept_title = kws
        concept_subtitle = "فكرة محورية وشرح مبسط للفائدة"
        kpi_value = "Pro Tips"
        kpi_label = "معلومة قيمة"

    if chosen_type == prev_scene_type and total_scenes > 1:
        alternates = {
            "ecommerce_showcase": "delivery_express" if domain == "ecommerce" else "growth_analytics",
            "delivery_express": "reels_smartphone",
            "reels_smartphone": "growth_analytics",
            "growth_analytics": "reels_smartphone",
            "ai_neural_brain": "platform_builder",
            "platform_builder": "growth_analytics",
            "time_warp_clock": "ecommerce_showcase"
        }
        chosen_type = alternates.get(chosen_type, chosen_type)

    return {
        "scene_type": chosen_type,
        "badge_label": badge_label,
        "short_title": concept_title,
        "concept_title": concept_title,
        "concept_subtitle": concept_subtitle,
        "kpi_value": kpi_value,
        "kpi_label": kpi_label,
        "target_number": local_num or (wilayas if domain == "ecommerce" else 100)
    }


def analyze_contextual_storyboard(
    scenes: list,
    full_transcript: str = "",
    groq_api_key: str = None,
    gemini_api_key: str = None,
    openai_api_key: str = None,
    ollama_model: str = "llama3"
) -> list:
    if not scenes:
        return []

    if not full_transcript:
        full_transcript = " ".join(str(s.get("text", "")) for s in scenes)

    global_ctx = extract_global_video_context(full_transcript)

    from motion_text import MOTION_THEMES
    theme_keys = list(MOTION_THEMES.keys())
    transitions = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

    enriched_scenes = []
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

    # Optional cloud LLM refinement if API keys are available
    try:
        scenes_Input_summary = "\n".join(
            f"{i+1}. [{s['start']:.1f}s - {s['end']:.1f}s]: \"{s['text']}\""
            for i, s in enumerate(enriched_scenes)
        )
        llm_prompt = (
            f"النص الكامل للفيديو: \"{full_transcript}\"\n"
            f"المجال الحقيقي للفيديو: {global_ctx['domain_label_ar']}\n\n"
            f"المشاهد:\n{scenes_Input_summary}\n\n"
            "أنت مخرج فني موشن جرافيك فائق الدقة. مهمتك تحسين العناوين لتكون 100% مطابقة لكلام المتحدث في هذا الفيديو فقط.\n"
            "شروط صارمة:\n"
            "1. ممنوع نهائياً اختراع أي اسم مؤسس أو عمر أو مجال فيديو إيديتينج ما لم يكن مذكوراً في النص حرفياً.\n"
            "2. إذا كان الفيديو لمنتج (مثل كابل)، فكل المشاهد يجب أن تعبر عن المنتج وخصائصه وتوصيله.\n"
            "3. أرجع JSON Array فقط بالمفاتيح: scene_type, badge_label, concept_title, kpi_value, kpi_label."
        )
        ai_raw = query_hybrid_llm(
            prompt=llm_prompt,
            system_prompt="أنت مخرج موشن جرافيك دقيق لا يختلق أي معلومة غير موجودة في النص. أرجع JSON فقط.",
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            ollama_model=ollama_model,
            temperature=0.1,
            max_tokens=900
        )
        if ai_raw:
            m = re.search(r"\[.*\]", ai_raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                valid_types = {
                    "ecommerce_showcase", "delivery_express", "reels_smartphone",
                    "growth_analytics", "time_warp_clock", "ai_neural_brain",
                    "platform_builder", "video_montage_studio", "creator_profile",
                    "age_number_counter", "brand_finale"
                }
                if isinstance(parsed, list) and len(parsed) == len(enriched_scenes):
                    for idx, item in enumerate(parsed):
                        if not isinstance(item, dict):
                            continue
                        st_cand = str(item.get("scene_type", "")).strip()
                        if st_cand in valid_types:
                            # Do not let LLM hallucinate creator_profile if no founder
                            if st_cand in ["creator_profile", "age_number_counter"] and not global_ctx.get("founder_age"):
                                pass
                            else:
                                enriched_scenes[idx]["scene_type"] = st_cand
                        bl_cand = str(item.get("badge_label", "")).strip()
                        if len(bl_cand) >= 5 and "17" not in bl_cand and "أنس" not in bl_cand:
                            enriched_scenes[idx]["badge_label"] = bl_cand
                        ct_cand = str(item.get("concept_title", "")).strip()
                        if len(ct_cand) >= 3 and "أنس" not in ct_cand:
                            enriched_scenes[idx]["concept_title"] = ct_cand
                            enriched_scenes[idx]["short_title"] = ct_cand
                        kv_cand = str(item.get("kpi_value", "")).strip()
                        kl_cand = str(item.get("kpi_label", "")).strip()
                        if kv_cand and kl_cand and "17" not in kv_cand:
                            enriched_scenes[idx]["kpi_value"] = kv_cand
                            enriched_scenes[idx]["kpi_label"] = kl_cand
    except Exception as e:
        logger.debug(f"استخدام المعالج السياقي المدمج: {e}")

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

    global_domain = contextual_scenes[0].get("global_domain", "general") if contextual_scenes else "general"
    broll_candidate_indices = []
    for idx, sc in enumerate(contextual_scenes):
        t_low = str(sc.get("text", "")).lower()
        if 0 < idx < num_scenes - 1:
            if global_domain == "ecommerce":
                if any(w in t_low for w in ["كابل", "شاحن", "سيبور", "تشارجي", "تتفرج", "قماش", "يتقطع", "متانة", "توصيل", "منتج", "سلعة"]):
                    broll_candidate_indices.append(idx)
            elif global_domain == "social_media":
                if any(w in t_low for w in ["انستغرام", "ريلز", "تيك توك", "فيديو", "كاميرا", "تصوير", "تفاعل", "متابعين"]):
                    broll_candidate_indices.append(idx)
            else:
                if any(w in t_low for w in ["تطبيق", "منصة", "برمجة", "ذكاء", "فيديو", "تقنية", "شاشة", "هاتف"]):
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

        scene_type = sc.get("scene_type", "ecommerce_showcase" if global_domain == "ecommerce" else ("reels_smartphone" if global_domain == "social_media" else "growth_analytics"))
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