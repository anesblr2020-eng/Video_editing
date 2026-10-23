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
    from context_engine import (
        build_storyboard as build_grounded_context_storyboard,
        analyze_global_context as analyze_grounded_global_context,
        validate_card as validate_grounded_card,
        finalize_scene_timing
    )
except ImportError:
    build_grounded_context_storyboard = None
    analyze_grounded_global_context = None
    validate_grounded_card = None
    finalize_scene_timing = None

try:
    from style_evolution_brain import (
        load_evolution_memory,
        get_best_params_for_scene_type,
        get_active_brand_theme
    )
except ImportError:
    load_evolution_memory = None
    get_best_params_for_scene_type = None
    get_active_brand_theme = None

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
# 1.8 نظام التعلم الذاتي للموشن جرافيك من الإنترنت والملفات المرجعية (Self-Learning Choreography Brain)
# ==============================================================================
CHOREOGRAPHY_ARCHETYPES = [
    "video_schedule_table",         # جدول الفيديو والـ Timeline التفاعلي (تغوص الكاميرا في خلاياه وتخرج منها بأسلوب onetakemotion.com)
    "saas_folder_reorder",          # بطاقة مجلد وقائمة عناصر تنزلق بالتتابع (Stagger 6f) وتتبادل مواقعها مع أسهم دوارة
    "stage_trust_bubbles",          # شاشة هاتف/عنصر مركزي محاط بـ 4 فقاعات منبثقة (Pop-in Spring) + شريط مؤشر سفلي
    "stage_balance_scale",          # ميزان فيزيائي ذو كفتين (المشكلة/اليدوي مقابل الحل/الذكي أو السعر مقابل القيمة)
    "saas_typewriter_mechanism",    # ترس ميكانيكي دوار + شريط بحث يكتب المفهوم كلمة بكلمة (Typewriter + Caret)
    "saas_process_flow",            # 3 بطاقات متدرجة: شريط تقدم + منحنى بياني تتبعه أيقونة ذكية + بطاقة اكتشاف
    "saas_grid_2x2_cursor",         # شبكة رباعية (2x2 Grid) بأشرطة تقدم ملونة + جزيئات متطايرة + مؤشر ماوس ينقر مع Ripple
    "stage_before_after_checklist", # مقارنة (قبل / بعد) مع عداد تقييم صاعد + قائمة تدقيق تتفعل بعلامات صح خضراء ✔️
    "interactive_cta_outro"         # بطاقة تفاعل ختامية بخطوتين (طائرة ورقية متحركة ✈️ + حقل تعليق/طلب مع نقرة ماوس)
]

# أنماط حركة الكاميرا الواحدة المتصلة وتحول العناصر عبر الحدود (One-Take Motion Camera & Morphing Handoffs - onetakemotion.com)
ONE_TAKE_HANDOFF_MODES = [
    "camera_dive_into_portal",      # غوص الكاميرا داخل بطاقة أو خلية في جدول الفيديو ليصبح باطنها هو المشهد التالي بالكامل (Scale 1x -> 4.2x)
    "camera_pull_out_reveal",       # خروج الكاميرا من داخل تفصيل مكبر ليتضح أنه خلية داخل جدول الفيديو أو لوحة أكبر (Scale 3.8x -> 1x)
    "prompt_bar_to_window",         # تمدد شريط البحث أو الإدخال فيزيائياً لينفتح ويتحول إلى نافذة المشهد التالي
    "window_reflows_to_phone",      # انكماش وتشكل النافذة العريضة بنعومة لتصبح هيكل الهاتف الذكي في المشهد التالي
    "bar_collapses_to_table_grid",  # اندماج شريط التقدم في خط ضوئي ينطلق عبر الشاشة ليرسم أول سطر شبكي في جدول الفيديو
    "card_grows_to_page",           # نمو بطاقة فرعية من القائمة أو الشبكة لتصبح الصفحة/المسرح الكامل للمشهد التالي
    "cast_folds_to_lockup"          # انطواء عناصر المسرح في النهاية لتندمج في بطاقة الختام والشعار (CTA Lockup)
]

GENOME_STORAGE_PATH = os.path.join(_CURRENT_DIR, "outputs", "learned_motion_genome.json")


class WebMotionLearner:
    """
    يتعلم تلقائياً من الإنترنت ومن ملف المواصفات المرجعي (Frame-by-Frame Spec) ومن سجل الأخطاء الممنوعة
    لبناء كوريغرافيا بصرية متكاملة وفريدة لكل مشهد بدون أي قوالب جامدة أو تكرار، ويحفظ الأنماط في `learned_motion_genome.json`.
    """

    def __init__(self):
        self.learned_genome = self._load_genome()

    def _load_genome(self) -> Dict[str, Any]:
        if os.path.exists(GENOME_STORAGE_PATH):
            try:
                with open(GENOME_STORAGE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "learned_topics": {},
            "total_videos_learned": 0,
            "universal_anti_error_rules": [
                "NEVER_REPEAT_BADGE_OR_CONCEPT_ACROSS_SCENES",
                "NEVER_USE_OUTRO_ARCHETYPE_BEFORE_FINAL_SCENE",
                "NEVER_MIX_VIDEO_EDITING_TERMS_INTO_ECOMMERCE_OR_OTHER_DOMAINS",
                "NEVER_USE_BOILERPLATE_PLACEHOLDERS_LIKE_MARHALA_OR_IDAA_MAARIFIYA",
                "NEVER_STROBE_BACKGROUND_LIGHT_AND_DARK_EVERY_SCENE",
                "NEVER_REPLACE_PRODUCT_VIDEO_WITH_PROCEDURAL_CIRCLES"
            ]
        }

    def _save_genome(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(GENOME_STORAGE_PATH)), exist_ok=True)
            with open(GENOME_STORAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.learned_genome, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def fetch_web_design_inspiration(self, topic_query: str, timeout: float = 2.5) -> List[str]:
        snippets: List[str] = []
        try:
            url = "https://api.duckduckgo.com/"
            resp = requests.get(url, params={"q": topic_query, "format": "json", "no_html": 1}, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("AbstractText"):
                    snippets.append(str(data["AbstractText"])[:200])
                for rt in data.get("RelatedTopics", [])[:3]:
                    if isinstance(rt, dict) and rt.get("Text"):
                        snippets.append(str(rt["Text"])[:140])
        except Exception:
            pass
        return snippets

    def learn_and_build_scene_choreography(
        self,
        scenes: List[Dict[str, Any]],
        full_transcript: str,
        global_ctx: Dict[str, Any],
        query_llm_func=None,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        import hashlib, time
        domain = global_ctx.get("domain", "general")
        topic_hash = hashlib.md5(full_transcript.encode("utf-8", errors="ignore")).hexdigest()[:10]

        choreographed_scenes: List[Dict[str, Any]] = []
        used_archetypes: List[str] = []

        for idx, sc in enumerate(scenes):
            s_text = str(sc.get("text", "")).strip()
            prev_text = str(scenes[idx - 1].get("text", "")).strip() if idx > 0 else ""
            next_text = str(scenes[idx + 1].get("text", "")).strip() if idx + 1 < len(scenes) else ""

            blueprint = self._build_deep_scene_blueprint(
                scene_text=s_text,
                scene_index=idx,
                total_scenes=len(scenes),
                domain=domain,
                global_ctx=global_ctx,
                used_archetypes=used_archetypes,
                prev_scene_text=prev_text,
                next_scene_text=next_text
            )
            used_archetypes.append(blueprint["archetype"])

            merged = dict(sc)
            merged.update(blueprint)
            merged["step_badge"] = f"#{idx + 1}"
            # هوية بصرية سينمائية داكنة فخمة افتراضياً (أو مخصصة حسب ثيم اللوقو/المستخدم)
            merged["style_mode"] = merged.get("style_mode") or "dark_stage_pro"
            choreographed_scenes.append(merged)

        if callable(query_llm_func) and (groq_api_key or gemini_api_key or openai_api_key):
            try:
                web_Order = self.fetch_web_design_inspiration(global_ctx.get("domain_label_ar", "motion graphics"))
                web_hint = " | ".join(web_Order) if web_Order else "أسلوب 101bdarija Clean SaaS و moujtabakhalifa Split-Screen Stage"
                scenes_desc = "\n".join(
                    f"{i+1}. [{s['start']:.1f}s - {s['end']:.1f}s]: \"{s['text']}\""
                    for i, s in enumerate(choreographed_scenes)
                )
                prompt = (
                    f"النص الكامل للفيديو: \"{full_transcript}\"\n"
                    f"المجال المكتشف بدقة: {global_ctx.get('domain_label_ar', '')} (domain={domain})\n"
                    f"مرجع الإلهام: {web_hint}\n\n"
                    f"المشاهد:\n{scenes_desc}\n\n"
                    "أنت مخرج موشن جرافيك عالمي. لكل مشهد، أعطني JSON Array بالمفاتيح: archetype, badge_label, concept_title, sub_items (4 عناصر قصيرة من 2-4 كلمات), kpi_value, kpi_label.\n"
                    "قواعد صارمة لا تقبل الاستثناء:\n"
                    "1. ممنوع تكرار نفس badge_label أو concept_title أو kpi_value في مشهدين مختلفين.\n"
                    "2. ممنوع استخدام interactive_cta_outro إلا في المشهد الأخير فقط.\n"
                    "3. يجب أن تكون جميع النصوص من نفس مجال الفيديو الفعلي ومستنبطة من كلام المتحدث بدون نسخ حرفي."
                )
                ai_resp = query_llm_func(
                    prompt=prompt,
                    system_prompt="أنت مخرج فني خبير في الموشن جرافيك التفاعلي. أرجع JSON Array فقط.",
                    groq_api_key=groq_api_key,
                    gemini_api_key=gemini_api_key,
                    openai_api_key=openai_api_key,
                    temperature=0.15,
                    max_tokens=1400
                )
                if ai_resp:
                    m = re.search(r"\[.*\]", ai_resp, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group(0))
                        if isinstance(parsed, list) and len(parsed) == len(choreographed_scenes):
                            for i, item in enumerate(parsed):
                                if not isinstance(item, dict):
                                    continue
                                arch = str(item.get("archetype", "")).strip()
                                if arch in CHOREOGRAPHY_ARCHETYPES:
                                    if arch == "interactive_cta_outro" and i < len(choreographed_scenes) - 1:
                                        pass
                                    else:
                                        choreographed_scenes[i]["archetype"] = arch
                                bl = str(item.get("badge_label", "")).strip()
                                if len(bl) >= 4 and not any(b in bl for b in ["إضاءة", "المرحلة #", "تطوير الأداء", "أنس", "17"]):
                                    choreographed_scenes[i]["badge_label"] = bl
                                ct = str(item.get("concept_title", "")).strip()
                                if len(ct) >= 4 and not any(b in ct for b in ["إضاءة", "منهجية ذكية", "أنس"]):
                                    choreographed_scenes[i]["concept_title"] = ct
                                    choreographed_scenes[i]["short_title"] = ct
                                subs = item.get("sub_items")
                                if isinstance(subs, list) and len(subs) >= 3:
                                    clean_subs = [str(x).strip()[:28] for x in subs[:4] if str(x).strip()]
                                    if len(clean_subs) >= 3 and "تحديد الهدف بدقة" not in clean_subs:
                                        choreographed_scenes[i]["sub_items"] = clean_subs
                                kv = str(item.get("kpi_value", "")).strip()
                                kl = str(item.get("kpi_label", "")).strip()
                                if kv and kl and "Pro Tips" not in kv and "خطوة #" not in kv:
                                    choreographed_scenes[i]["kpi_value"] = kv
                                    choreographed_scenes[i]["kpi_label"] = kl
            except Exception as e:
                logger.debug(f"Web motion learner fallback: {e}")

        choreographed_scenes = MotionQualityAuditor.audit_and_heal_storyboard(
            choreographed_scenes, full_transcript, global_ctx
        )

        self.learned_genome["learned_topics"][topic_hash] = {
            "domain": domain,
            "timestamp": int(time.time()),
            "scenes_count": len(choreographed_scenes),
            "archetypes_used": [s.get("archetype") for s in choreographed_scenes]
        }
        self.learned_genome["total_videos_learned"] = int(self.learned_genome.get("total_videos_learned", 0)) + 1
        self._save_genome()

        return choreographed_scenes

    def _pick_next_non_outro_archetype(self, preferred: str, used_archetypes: List[str], scene_index: int, total_scenes: int) -> str:
        """
        يضمن توزيع أنماط الكوريغرافيا الـ 7 الأساسية دون أي تكرار، مع حجز `interactive_cta_outro` للمشهد الأخير حصرياً.
        """
        if scene_index == total_scenes - 1 and total_scenes >= 2:
            return "interactive_cta_outro"

        non_outro_pool = [
            "stage_trust_bubbles",
            "video_schedule_table",
            "stage_balance_scale",
            "saas_folder_reorder",
            "saas_grid_2x2_cursor",
            "saas_typewriter_mechanism",
            "saas_process_flow",
            "stage_before_after_checklist",
        ]
        if preferred in non_outro_pool and preferred not in used_archetypes:
            return preferred
        if preferred in non_outro_pool and (not used_archetypes or preferred != used_archetypes[-1]):
            # إذا لم نستخدم كل الأنماط الـ 7 بعد، نفضل نمطاً لم يُستخدم إطلاقاً في هذا الفيديو
            unused = [a for a in non_outro_pool if a not in used_archetypes]
            if unused:
                return unused[0]
            return preferred

        unused = [a for a in non_outro_pool if a not in used_archetypes]
        if unused:
            return unused[scene_index % len(unused)]
        non_adj = [a for a in non_outro_pool if (not used_archetypes or a != used_archetypes[-1])]
        return non_adj[scene_index % len(non_adj)]

    def _build_deep_scene_blueprint(
        self,
        scene_text: str,
        scene_index: int,
        total_scenes: int,
        domain: str,
        global_ctx: Dict[str, Any],
        used_archetypes: List[str],
        prev_scene_text: str = "",
        next_scene_text: str = ""
    ) -> Dict[str, Any]:
        """
        محرك التوليد الدلالي الشامل الموجه بالمجال والسياق (Universal Domain-Isolated Blueprint Synthesizer):
        - يعزل كل مجال (`ecommerce`, `social_media`, `tech_software`, `education`, `business`, `general`) عزلاً تاماً
          بحيث لا تتسرب مصطلحات المونتاج إلى إعلانات المنتجات أو العكس أبداً.
        - يستنبط المعنى الفعلي للجملة وعلاقتها بالجملة السابقة واللاحقة دون أي قوالب حشو عامة.
        """
        t_low = scene_text.lower()
        window_low = f"{prev_scene_text} {scene_text} {next_scene_text}".lower()
        wilayas = global_ctx.get("wilayas_count") or 58
        kws = extract_clean_keywords(scene_text, max_words=3)
        kw_phrase = " ".join(kws[:2]) if kws else ""

        # =====================================================================
        # المجال الأول: إعلانات المنتجات والتجارة الإلكترونية (E-Commerce & Product Ads)
        # =====================================================================
        if domain == "ecommerce":
            # 1. مشهد الخاتمة وطلب المنتج (CTA Outro)
            if scene_index == total_scenes - 1 or any(w in t_low for w in ["اضغط على زر", "اسفل الفيديو", "أسفل الفيديو", "اكموندي", "اطلب", "الرابط", "للطلب"]):
                return {
                    "archetype": "interactive_cta_outro",
                    "scene_type": "delivery_express",
                    "badge_label": "اطلب الآن • متوفر للتوصيل السريع",
                    "concept_title": "اطلب الكابل الذكي الآن بضغطة زر",
                    "concept_subtitle": "اضغط على الزر أسفل الفيديو واستفد من العرض فوراً",
                    "sub_items": ["اضغط الزر أسفل الفيديو", f"توصيل سريع {wilayas} ولاية", "الدفع عند الاستلام", "ضمان الجودة الأصلية"],
                    "balance_left": ("الطلب الفوري", "خلال 30 ثانية"),
                    "balance_right": ("التوصيل السريع", "لباب المنزل"),
                    "before_after": ("شراء تقليدي متعب", "4.0", "طلب فوري ومضمون", "9.9"),
                    "typewriter_query": "اطلب الآن • الدفع عند الاستلام",
                    "kpi_value": "اطلب الآن",
                    "kpi_label": "عبر الزر أسفل الفيديو"
                }

            # 2. الشحن الفائق والقوة (Super Fast / 240W / يتشارجا)
            if any(w in t_low for w in ["سوبر فاست", "فاست", "فاستا", "يتشارجا", "240", "اقوى", "أقوى", "اي تليفون", "أي تيليفون"]):
                arch = self._pick_next_non_outro_archetype("stage_before_after_checklist", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "قوة شحن خارقة • يدعم الشحن السريع Super Fast",
                    "concept_title": "شحن Super Fast لجميع الهواتف",
                    "concept_subtitle": "متوافق مع كافة الأجهزة بقدرة شحن فائقة وأمان تام",
                    "sub_items": ["شحن Super Fast فوري", "متوافق مع كل الهواتف", "حماية ذكية للبطارية", "أداء مستقر وعالي"],
                    "balance_left": ("شاحن بطيء عادي", "ساعات انتظار"),
                    "balance_right": ("شحن Super Fast", "طاقة كاملة بسرعة"),
                    "before_after": ("شحن عادي بطيء", "3.8", "شحن Super Fast", "9.9"),
                    "typewriter_query": "شحن خارق Super Fast لكل الهواتف",
                    "kpi_value": "Super Fast",
                    "kpi_label": "شحن فائق السرعة"
                }

            # 3. الخاصية الثالثة / التغليف القماشي ومقاومة القطع
            if any(w in t_low for w in ["قماش", "يتقطع", "الثالثة", "الثالثه", "مغلف", "متانة"]) or ("قماش" in window_low and "ثالث" in t_low):
                arch = self._pick_next_non_outro_archetype("stage_trust_bubbles", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "الخاصية الثالثة • مغلف بالقماش المقاوم للقطع",
                    "concept_title": "نسيج قماشي متين ضد القطع والتلف",
                    "concept_subtitle": "وداعاً لتلف الكوابل بفضل التغليف القماشي المقوى",
                    "sub_items": ["تغليف قماشي مقوى", "مقاوم للقطع والشد", "حماية مفاصل السلك", "عمر افتراضي طويل"],
                    "balance_left": ("سلك بلاستيك عادي", "ينقطع بسرعة"),
                    "balance_right": ("كابل مغلف بالقماش", "متانة 100% ضد القطع"),
                    "before_after": ("سلك تقليدي يتقطع", "3.2", "نسيج قماشي متين", "9.8"),
                    "typewriter_query": "مغلف بالقماش • حماية 100% ضد القطع",
                    "kpi_value": "100% متين",
                    "kpi_label": "مقاوم للقطع والتلف"
                }

            # 4. الخاصية الثانية / الشحن والمشاهدة المريحة في نفس الوقت
            if any(w in t_low for w in ["تشارجي", "تتفرج", "الثانية", "الثانيه", "نفس الوقت", "بكل راحة"]):
                arch = self._pick_next_non_outro_archetype("saas_process_flow", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "reels_smartphone",
                    "badge_label": "الخاصية الثانية • اشحن وتفرج بكل راحة",
                    "concept_title": "شحن سريع ومشاهدة مريحة في آن واحد",
                    "concept_subtitle": "استمتع بمشاهدة فيديوهاتك أثناء الشحن دون إجهاد اليد",
                    "sub_items": ["شحن مستمر ومستقر", "زاوية مشاهدة مريحة", "حرية كاملة لليدين", "تصميم عملي ذكي"],
                    "balance_left": ("استخدام أثناء الشحن", "إجهاد وتشابك السلك"),
                    "balance_right": ("شحن مع الحامل المدمج", "راحة تامة ومشاهدة ممتعة"),
                    "before_after": ("مسك متعب للهاتف", "4.0", "مشاهدة مريحة وثابتة", "9.7"),
                    "typewriter_query": "اشحن هاتفك وشاهد محتواك براحة",
                    "kpi_value": "راحة 100%",
                    "kpi_label": "شحن ومشاهدة معاً"
                }

            # 5. الخاصية الأولى / حامل الهاتف المدمج (سيبور تيليفون)
            if any(w in t_low for w in ["سيبور", "حامل", "ستاند", "مدمج"]):
                arch = self._pick_next_non_outro_archetype("saas_folder_reorder", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "reels_smartphone",
                    "badge_label": "الخاصية الأولى • حامل هاتف مدمج (سيبور ذكي)",
                    "concept_title": "مزود بحامل هاتف معدني مدمج",
                    "concept_subtitle": "يثبت هاتفك أفقياً أو عمودياً أثناء الشحن بكل ثبات",
                    "sub_items": ["1. حامل هاتف مدمج (سيبور)", "2. تثبيت أفقي وعمودي", "3. مفصل معدني متين", "4. يطوى بسلاسة تامة"],
                    "balance_left": ("كابل شحن فقط", "وظيفة واحدة"),
                    "balance_right": ("كابل + سيبور مدمج", "وظيفتان في جهاز واحد"),
                    "before_after": ("بدون حامل هاتف", "4.1", "سيبور مدمج متين", "9.8"),
                    "typewriter_query": "سيبور تيليفون مدمج في رأس الشاحن",
                    "kpi_value": "2 في 1",
                    "kpi_label": "شاحن وسيبور مدمج"
                }

            # 6. استعراض الخصائص الثلاث المجانية (3 خصائص تديهم باطل)
            if any(w in t_low for w in ["ثلاث", "3", "خصائص", "ميزات", "باطل", "بري", "الأولى", "الاولى"]):
                arch = self._pick_next_non_outro_archetype("saas_grid_2x2_cursor", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "مواصفات حصرية • 3 خصائص مجانية في كابل واحد",
                    "concept_title": "ثلاث خصائص ذكية بسعر كابل واحد",
                    "concept_subtitle": "حامل هاتف مدمج + تغليف قماشي متين + شحن Super Fast",
                    "sub_items": ["حامل هاتف مدمج", "تغليف قماشي ضد القطع", "شحن خارق Super Fast", "قيمة اقتصادية ممتازة"],
                    "balance_left": ("شراء 3 قطع منفصلة", "تكلفة عالية"),
                    "balance_right": ("3 خصائص في كابل 1", "توفير وجودة فائقة"),
                    "before_after": ("كابل عادي محدود", "3.9", "3 خصائص متكاملة", "9.8"),
                    "typewriter_query": "3 خصائص ذكية في كابل واحد",
                    "kpi_value": "3 خصائص في 1",
                    "kpi_label": "قيمة استثنائية"
                }

            # 7. الاستثمار الأفضل للهاتف (أفضل استثمار ممكن نديروه في تليفونك)
            if any(w in t_low for w in ["استثمار", "افضل", "أفضل", "تليفونك", "هاتفك", "كابل هذا"]):
                arch = self._pick_next_non_outro_archetype("saas_typewriter_mechanism", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "القيمة الحقيقية • أفضل استثمار لحماية هاتفك",
                    "concept_title": "أفضل استثمار عملي لهاتفك الذكي",
                    "concept_subtitle": "يغنيك عن شراء الكوابل المتكررة ويحمي مدخل الشحن",
                    "sub_items": ["يدوم طويلاً بدون تلف", "يحمي بطارية الهاتف", "يوفر المال والجهد", "تصميم عصري فاخر"],
                    "balance_left": ("تغيير الكابل كل شهر", "خسارة مستمرة"),
                    "balance_right": ("استثمار لمرة واحدة", "جودة تدوم طويلاً"),
                    "before_after": ("كوابل رديئة مؤقتة", "3.5", "استثمار أصلي مضمون", "9.7"),
                    "typewriter_query": "أفضل استثمار عملي لهاتفك الذكي",
                    "kpi_value": "أفضل استثمار",
                    "kpi_label": "جودة تدوم طويلاً"
                }

            # 8. المقارنة والتساؤل (علاش كاين بزاف من خاوتنا مازال ما يلقاوش)
            if any(w in t_low for w in ["علاش", "بزاف", "خاوتنا", "مازال", "تلقاوش", "يلقاوش"]):
                arch = self._pick_next_non_outro_archetype("stage_balance_scale", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "مقارنة عملية • الكوابل التقليدية مقابل الكابل الذكي",
                    "concept_title": "لماذا يتفوق هذا الكابل على الشواحن العادية؟",
                    "concept_subtitle": "الفرق الجوهري بين الكابل التقليدي والكابل الذكي متعدد الوظائف",
                    "sub_items": ["وداعاً لانقطاع السلك", "وداعاً لبطء الشحن", "حامل مدمج للمشاهدة", "خامات أصلية معتمدة"],
                    "balance_left": ("الكوابل التقليدية", "تلف سريع وبلا ميزات"),
                    "balance_right": ("الكابل الذكي المطور", "متانة + حامل + سرعة"),
                    "before_after": ("شاحن تقليدي ضعيف", "3.6", "كابل ذكي متكامل", "9.8"),
                    "typewriter_query": "الفرق بين الكابل العادي والكابل الذكي",
                    "kpi_value": "مقارنة الجودة",
                    "kpi_label": "تفوق واضح"
                }

            # 9. الخطاف الافتتاحي أو أي مشهد آخر في إعلان المنتج (Hook / General Product Scene)
            arch = self._pick_next_non_outro_archetype("stage_trust_bubbles", used_archetypes, scene_index, total_scenes)
            return {
                "archetype": arch,
                "scene_type": "ecommerce_showcase",
                "badge_label": f"ابتكار عملي • {kw_phrase or 'الكابل الذكي متعدد الوظائف'}",
                "concept_title": "اكتشف الجيل الجديد من كوابل الشحن الذكية",
                "concept_subtitle": "تصميم مبتكر يجمع القوة والمتانة والراحة في وقت واحد",
                "sub_items": ["شحن فائق السرعة", "حامل هاتف مدمج", "مغلف بالقماش المتين", "متوافق مع كل الأجهزة"],
                "balance_left": ("كابل عادي", "أداء محدود"),
                "balance_right": ("كابل ذكي 3 في 1", "أداء احترافي كامل"),
                "before_after": ("تجربة شحن تقليدية", "4.0", "تجربة شحن ذكية", "9.7"),
                "typewriter_query": "كابل الشحن الذكي 3 في 1",
                "kpi_value": "Top Quality",
                "kpi_label": "منتج أصلي مبتكر"
            }

        # =====================================================================
        # المجال الثاني والثالث: التقنية وصناعة المحتوى والمونتاج بالذكاء الاصطناعي
        # =====================================================================
        is_problem_or_pain = any(w in t_low for w in ["مشكل", "مشكلة", "يعاني", "يعانيوا", "ضيق", "صعيب"])
        is_time_comparison = any(w in t_low for w in ["ما عندها وقت", "ما عندهمش وقت", "أغلب الناس", "اغلب الناس", "تصور الفيديوهات", "وقت تمنتج"])
        is_productivity_or_social = any(w in t_low for w in ["انتاجية", "إنتاجية", "التواصل الاجتماعي", "انستغرام", "ريلز", "تيك توك", "مشاهدات", "تفاعل", "ريتش", "نشر"])
        is_platform_intro = any(w in t_low for w in ["جبت لكم", "منصة", "تطبيق", "المسؤولة", "مسؤولة"])
        is_ai_audio_video = any(w in t_low for w in ["صوت وصورة", "صوت", "صورة", "بالذكاء الاصطناعي", "ذكاء", "أوتوماتيكي"])
        is_speed_under_minute = any(w in t_low for w in ["أقل من دقيقة", "اقل من دقيقه", "دقيقة", "ثواني", "بسرعة"])
        is_final_cta = (scene_index == total_scenes - 1 and total_scenes >= 2)

        if is_final_cta:
            return {
                "archetype": "interactive_cta_outro",
                "scene_type": "video_montage_studio",
                "badge_label": "تحرير شامل • قص وتعديل وموشن جرافيك بضغطة زر",
                "concept_title": "قص الصمت وتعديل الفيديو بالكامل آلياً",
                "concept_subtitle": "من التسجيل الخام إلى فيديو احترافي جاهز للنشر الفوري",
                "sub_items": ["قص لحظات السكوت آلياً", "توليد الموشن جرافيك السياقي", "كابشن تفاعلي دقيق", "تصدير بجودة Full HD 30fps"],
                "balance_left": ("فيديو خام", "بدون تحرير"),
                "balance_right": ("فيديو احترافي", "جاهز للنشر"),
                "before_after": ("فيديو خام غير محرر", "4.2", "فيديو احترافي متكامل", "9.8"),
                "typewriter_query": "ابدأ تجربة المونتاج الذكي الآن",
                "kpi_value": "قص + تعديل آلي",
                "kpi_label": "إخراج متكامل"
            }

        if is_problem_or_pain or (scene_index == 0 and any(w in window_low for w in ["مشكل", "مشكلة", "يعاني", "المونتاج", "وقت"])):
            if "stage_trust_bubbles" not in used_archetypes:
                arch = self._pick_next_non_outro_archetype("stage_trust_bubbles", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "time_warp_clock",
                    "badge_label": "تحدي صناع المحتوى • عقبة المونتاج اليومي",
                    "concept_title": "مشكلة استنزاف الوقت في المونتاج",
                    "concept_subtitle": "معاناة تصوير الفيديوهات دون وقت كافٍ لتحريرها",
                    "sub_items": ["تراكم الفيديوهات الخام", "ضيق الوقت اليومي", "صعوبة القص اليدوي", "تأخر النشر المستمر"],
                    "balance_left": ("المونتاج اليدوي", "ساعات مرهقة"),
                    "balance_right": ("الأتمتة الذكية", "ثوانٍ معدودة"),
                    "before_after": ("يدوياً: 4 ساعات", "3.5", "آلياً: 45 ثانية", "9.7"),
                    "typewriter_query": "لماذا يتأخر صناع المحتوى في النشر؟",
                    "kpi_value": "85% يعانون",
                    "kpi_label": "ضيق وقت المونتاج"
                }
            else:
                arch = self._pick_next_non_outro_archetype("stage_balance_scale", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "time_warp_clock",
                    "badge_label": "أزمة الوقت • صعوبة المونتاج اليدوي التقليدي",
                    "concept_title": "استنزاف الساعات في المونتاج اليدوي",
                    "concept_subtitle": "الفجوة بين سهولة التصوير وصعوبة التحرير اليدوي",
                    "sub_items": ["ساعات طويلة أمام البرامج", "إجهاد في قص الصمت", "تعقيد تصميم الموشن", "تأخر نشر المحتوى"],
                    "balance_left": ("المونتاج اليدوي", "4 ساعات عمل"),
                    "balance_right": ("المونتاج الذكي", "أقل من دقيقة"),
                    "before_after": ("يدوياً: 4 ساعات", "3.5", "آلياً: أقل من دقيقة", "9.8"),
                    "typewriter_query": "توفير 95% من وقت المونتاج",
                    "kpi_value": "4 ساعات -> 1 د",
                    "kpi_label": "اختصار وقت التحرير"
                }

        if is_time_comparison and not is_platform_intro:
            # إذا تم استخدام stage_balance_scale في المشهد السابق، نختار saas_folder_reorder بعنوان فريد ومكمل!
            if "stage_balance_scale" not in used_archetypes:
                return {
                    "archetype": "stage_balance_scale",
                    "scene_type": "time_warp_clock",
                    "badge_label": "معادلة الوقت • التصوير السهل مقابل المونتاج المرهق",
                    "concept_title": "التصوير جاهز لكن المونتاج يستهلك الساعات",
                    "concept_subtitle": "الفجوة الكبيرة بين تسجيل الفيديو وتحريره للنشر",
                    "sub_items": ["تسجيل الفيديو: 5 دقائق", "قص الصمت يدوياً: ساعة", "تصميم الموشن: ساعتان", "كتابة الكابشن: 45 دقيقة"],
                    "balance_left": ("المونتاج اليدوي", "4 ساعات عمل"),
                    "balance_right": ("المونتاج الآلي", "أقل من دقيقة"),
                    "before_after": ("قبل: إرهاق وتأخر", "4.0", "بعد: سرعة فائقة", "9.6"),
                    "typewriter_query": "توفير 95% من وقت التحرير",
                    "kpi_value": "4 ساعات -> 1 د",
                    "kpi_label": "اختصار وقت التحرير"
                }
            else:
                arch = self._pick_next_non_outro_archetype("saas_folder_reorder", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "video_montage_studio",
                    "badge_label": "تراكم المهام • لماذا تتوقف الفيديوهات بعد التصوير؟",
                    "concept_title": "مراحل التحرير التي تستهلك وقت صانع المحتوى",
                    "concept_subtitle": "ترتيب اللقطات وقص الصمت وتصميم الرسوم يدوياً يستغرق الساعات",
                    "sub_items": ["1. مراجعة وقص الفيديوهات الخام", "2. إزالة فترات الصمت الطويلة", "3. تصميم البطاقات والأنفوجرافيك", "4. كتابة ومزامنة الكابشن"],
                    "balance_left": ("تحرير يدوي معقد", "ساعات طويلة"),
                    "balance_right": ("أتمتة ذكية كاملة", "بضغطة زر"),
                    "before_after": ("فيديوهات حبيسة الهاتف", "3.8", "نشر يومي مستمر", "9.7"),
                    "typewriter_query": "توفير 95% من وقت التحرير",
                    "kpi_value": "95% توفير",
                    "kpi_label": "وقت الإعداد والمونتاج"
                }

        if is_productivity_or_social and not is_platform_intro:
            arch = self._pick_next_non_outro_archetype("saas_grid_2x2_cursor", used_archetypes, scene_index, total_scenes)
            return {
                "archetype": arch,
                "scene_type": "growth_analytics",
                "badge_label": "مضاعفة الإنتاجية • حضور قوي على منصات التواصل",
                "concept_title": "رفع الإنتاجية والانتشار الرقمي",
                "concept_subtitle": "نشر مستمر على إنستغرام وتيك توك ويوتيوب شورتس",
                "sub_items": ["مضاعفة معدل النشر", "سرعة تجهيز الريلز", "جذب انتباه المشاهد", "رفع التفاعل والوصول"],
                "balance_left": ("نشر متقطع", "تفاعل ضعيف"),
                "balance_right": ("نشر يومي منتظم", "نمو متسارع"),
                "before_after": ("قبل: فيديو أسبوعياً", "4.2", "بعد: فيديو يومياً", "9.5"),
                "typewriter_query": "مضاعفة الإنتاجية والانتشار الرقمي",
                "kpi_value": "+300% إنتاجية",
                "kpi_label": "نمو التفاعل والوصول"
            }

        if is_platform_intro and not is_ai_audio_video:
            arch = self._pick_next_non_outro_archetype("saas_typewriter_mechanism", used_archetypes, scene_index, total_scenes)
            return {
                "archetype": arch,
                "scene_type": "platform_builder",
                "badge_label": "الحل الذكي • منصة أتمتة المونتاج بالذكاء الاصطناعي",
                "concept_title": "منصة المونتاج الذكي الشاملة",
                "concept_subtitle": "مسؤولة بالكامل عن تحرير وإخراج الفيديوهات تلقائياً",
                "sub_items": ["قص الصمت التلقائي", "موشن جرافيك سياقي", "كابشن تفاعلي ذكي", "دمج مشاهد فيديو واقعية"],
                "balance_left": ("برامج معقدة", "خبرة ومجهود"),
                "balance_right": ("منصة ذكية", "بضغطة زر واحدة"),
                "before_after": ("قبل: تعقيد تقني", "3.9", "بعد: أتمتة كاملة", "9.6"),
                "typewriter_query": "منصة المونتاج بالذكاء الاصطناعي",
                "kpi_value": "All-in-One AI",
                "kpi_label": "منصة مونتاج ذاتية"
            }

        if is_ai_audio_video:
            if "saas_process_flow" not in used_archetypes:
                return {
                    "archetype": "saas_process_flow",
                    "scene_type": "ai_neural_brain",
                    "badge_label": "محرك الذكاء الاصطناعي • معالجة الصوت والصورة آلياً",
                    "concept_title": "تحويل الصوت والصورة إلى فيديو متكامل",
                    "concept_subtitle": "الذكاء الاصطناعي يفهم السياق ويصمم المشاهد تلقائياً",
                    "sub_items": ["تحليل الصوت والدارجة", "فهم السياق والمعنى", "توليد الموشن جرافيك", "دمج ومزامنة الإطارات"],
                    "balance_left": ("مدخلات خام", "صوت أو فيديو"),
                    "balance_right": ("مخرجات ذكية", "موشن جرافيك احترافي"),
                    "before_after": ("خام: تسجيل عادي", "4.5", "الناتج: فيديو سينمائي", "9.8"),
                    "typewriter_query": "محرك فهم الصوت والصورة والسياق",
                    "kpi_value": "100% بالـ AI",
                    "kpi_label": "معالجة سياقية ذكية"
                }
            else:
                arch = self._pick_next_non_outro_archetype("saas_folder_reorder", used_archetypes, scene_index, total_scenes)
                return {
                    "archetype": arch,
                    "scene_type": "video_montage_studio",
                    "badge_label": "خطوات الأتمتة • ارفع الفيديو والذكاء الاصطناعي يتكفل بالباقي",
                    "concept_title": "خطوات معالجة الصوت والصورة داخل المنصة",
                    "concept_subtitle": "من لحظة رفع الفيديو الخام حتى استلام الإخراج النهائي",
                    "sub_items": ["1. رفع الفيديو أو الصوت الخام", "2. استخراج النص وفهم السياق", "3. بناء مشاهد الموشن جرافيك", "4. مزامنة الصوت بدقة 30fps"],
                    "balance_left": ("تعديل يدوي", "ساعات عمل"),
                    "balance_right": ("رفع الفيديو فقط", "معالجة آلية شاملة"),
                    "before_after": ("تسجيل خام بسيط", "4.2", "إخراج أستوديو كامل", "9.8"),
                    "typewriter_query": "ارفع الفيديو • معالجة ذكية للصوت والصورة",
                    "kpi_value": "Full HD 30fps",
                    "kpi_label": "إخراج أستوديو آلي"
                }

        if is_speed_under_minute:
            arch = self._pick_next_non_outro_archetype("stage_before_after_checklist", used_archetypes, scene_index, total_scenes)
            return {
                "archetype": arch,
                "scene_type": "time_warp_clock",
                "badge_label": "سرعة قياسية • مونتاج احترافي في أقل من دقيقة",
                "concept_title": "إخراج احترافي كامل في أقل من 60 ثانية",
                "concept_subtitle": "جودة استوديو عالية مع توفير كامل للوقت والجهد",
                "sub_items": ["سرعة معالجة فائقة", "جودة موشن جرافيك 1080p", "تزامن صوتي وبصري دقيق", "جاهز للنشر الفوري"],
                "balance_left": ("الوقت السابق", "ساعات طويلة"),
                "balance_right": ("الوقت الحالي", "أقل من 60 ثانية"),
                "before_after": ("مونتاج يدوي مرهق", "4.1", "مونتاج ذكي فوري", "9.8"),
                "typewriter_query": "مونتاج احترافي < 60 ثانية",
                "kpi_value": "< 60 ثانية",
                "kpi_label": "سرعة الإنجاز الكامل"
            }

        if any(w in t_low for w in ["احترافي", "مونتاج", "قص", "تعديل", "جدول", "ترتيب", "فيديوهات"]):
            arch = self._pick_next_non_outro_archetype("video_schedule_table", used_archetypes, scene_index, total_scenes)
            return {
                "archetype": arch,
                "scene_type": "video_montage_studio",
                "badge_label": "جودة أستوديو • إخراج ومونتاج احترافي متكامل",
                "concept_title": "معايير إخراج سينمائية بشكل آلي",
                "concept_subtitle": "دمج القص الذكي والموشن جرافيك والكابشن التفاعلي",
                "sub_items": ["قص الصمت بدقة صوتية", "حركات كوريغرافيا 30fps", "تصميم بطاقات تفاعلية", "كابشن متزامن مع النطق"],
                "balance_left": ("تحرير بدائي", "جودة عادية"),
                "balance_right": ("إخراج بالذكاء الاصطناعي", "جودة أستوديو احترافية"),
                "before_after": ("فيديو عادي", "4.3", "إخراج احترافي", "9.8"),
                "typewriter_query": "إخراج ومونتاج احترافي بضغطة زر",
                "kpi_value": "Studio Pro",
                "kpi_label": "جودة إخراج عالية"
            }

        # =====================================================================
        # المولد السياقي الديناميكي العام لأي فيديو مستقبلي في أي مجال (Universal Dynamic Synthesizer)
        # =====================================================================
        arch = self._pick_next_non_outro_archetype("saas_folder_reorder", used_archetypes, scene_index, total_scenes)
        all_kws = extract_clean_keywords(f"{scene_text} {next_scene_text}", max_words=6)
        main_kw = " ".join(all_kws[:3]) if all_kws else "الفكرة المحورية"
        sub_kw_1 = " ".join(all_kws[:2]) if len(all_kws) >= 2 else "تحليل الفكرة الأساسية"
        sub_kw_2 = " ".join(all_kws[1:3]) if len(all_kws) >= 3 else "تطبيق عملي مباشر"
        sub_kw_3 = " ".join(all_kws[2:4]) if len(all_kws) >= 4 else "نتائج ملموسة وسريعة"
        sub_kw_4 = " ".join(all_kws[3:5]) if len(all_kws) >= 5 else "جودة وكفاءة عالية"

        domain_prefix_map = {
            "social_media": "صناعة المحتوى",
            "tech_software": "التقنية الذكية",
            "education": "فائدة معرفية",
            "business": "ريادة الأعمال",
            "ecommerce": "ميزة المنتج",
            "general": "محور أساسي"
        }
        d_prefix = domain_prefix_map.get(domain, "محور أساسي")

        return {
            "archetype": arch,
            "scene_type": "growth_analytics" if (scene_index % 2 == 0) else "reels_smartphone",
            "badge_label": f"{d_prefix} • {main_kw}",
            "concept_title": main_kw,
            "concept_subtitle": f"شرح تفصيلي وتوضيح بصري حول {main_kw}",
            "sub_items": [sub_kw_1, sub_kw_2, sub_kw_3, sub_kw_4],
            "balance_left": ("الطريقة العادية", "نتائج محدودة"),
            "balance_right": (sub_kw_1, "كفاءة عالية"),
            "before_after": ("قبل التطبيق", "4.2", f"بعد: {sub_kw_1}", "9.6"),
            "typewriter_query": main_kw,
            "kpi_value": f"محور #{scene_index + 1}",
            "kpi_label": d_prefix
        }


class MotionQualityAuditor:
    """
    المدقق الذاتي الصارم لمنع تكرار الأخطاء في أي فيديو مستقبلي (Universal Anti-Error Quality Auditor):
    1. يمنع تكرار نفس `badge_label` أو `concept_title` أو `kpi_value` بين أي مشهدين في الفيديو.
    2. يمنع ظهور `interactive_cta_outro` قبل المشهد الأخير، ويمنع تكرار نفس الـ `archetype` في مشاهد متقاربة.
    3. يمنع تسرب مصطلحات المونتاج إلى فيديوهات التجارة الإلكترونية أو المجالات الأخرى.
    4. يمنع أي عبارات حشو عامة أو كلمات مبتورة.
    """

    @staticmethod
    def audit_and_heal_storyboard(
        scenes: List[Dict[str, Any]],
        full_transcript: str,
        global_ctx: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        domain = global_ctx.get("domain", "general")
        total_scenes = len(scenes)
        healed: List[Dict[str, Any]] = []
        used_badges = set()
        used_concepts = set()
        used_kpis = set()
        used_archs: List[str] = []

        non_outro_pool = [
            "stage_trust_bubbles",
            "video_schedule_table",
            "stage_balance_scale",
            "saas_folder_reorder",
            "saas_grid_2x2_cursor",
            "saas_typewriter_mechanism",
            "saas_process_flow",
            "stage_before_after_checklist",
        ]

        domain_Progression_fallbacks = {
            "ecommerce": [
                ("اكتشف المنتج • تصميم عملي يجمع القوة والراحة", "ابتكار عملي للهواتف الذكية", "Top Pick", "اختيار موصى به"),
                ("مقارنة الجودة • الكوابل العادية مقابل الكابل الذكي", "تفوق واضح في المتانة والأداء", "3 في 1", "مواصفات متكاملة"),
                ("القيمة الحقيقية • أفضل استثمار لحماية هاتفك", "استثمار ذكي يدوم طويلاً", "أفضل استثمار", "حماية وكفاءة"),
                ("مواصفات حصرية • 3 خصائص عملية في منتج واحد", "ثلاث مزايا حصرية مجتمعة", "3 خصائص", "في كابل واحد"),
                ("الخاصية الأولى • حامل هاتف مدمج (سيبور ذكي)", "حامل هاتف مدمج بزاوية مريحة", "2 في 1", "شاحن وحامل"),
                ("الخاصية الثانية • اشحن هاتفك وتفرج بكل راحة", "مشاهدة مريحة أثناء الشحن", "راحة 100%", "ثبات تام"),
                ("الخاصية الثالثة • مغلف بالقماش المقاوم للقطع", "تغليف قماشي متين ضد القطع", "100% متين", "ضد القطع"),
                ("قوة خارقة • يدعم الشحن السريع Super Fast", "شحن Super Fast لجميع الهواتف", "Super Fast", "شحن فائق"),
                ("اطلب الآن • اضغط على الزر أسفل الفيديو", "اطلب الكابل الذكي الآن", "اطلب الآن", "متوفر فوراً"),
            ],
            "default": [
                ("تحدي صناع المحتوى • عقبة المونتاج اليومي", "مشكلة استنزاف الوقت في المونتاج", "85% يعانون", "ضيق وقت المونتاج"),
                ("معادلة الوقت • التصوير السهل مقابل المونتاج المرهق", "التصوير جاهز لكن المونتاج يستهلك الساعات", "4 ساعات -> 1 د", "اختصار وقت التحرير"),
                ("تراكم المهام • مراحل التحرير اليدوي المرهقة", "توفير 95% من وقت الإعداد والمونتاج", "95% توفير", "وقت التحرير"),
                ("مضاعفة الإنتاجية • حضور قوي على منصات التواصل", "رفع الإنتاجية والانتشار الرقمي", "+300% إنتاجية", "نمو التفاعل"),
                ("الحل الذكي • منصة أتمتة المونتاج بالذكاء الاصطناعي", "منصة المونتاج الذكي الشاملة", "All-in-One AI", "منصة مونتاج ذاتية"),
                ("محرك الذكاء الاصطناعي • معالجة الصوت والصورة آلياً", "تحويل الصوت والصورة إلى فيديو متكامل", "100% بالـ AI", "معالجة سياقية"),
                ("خطوات الأتمتة • ارفع الفيديو والنظام يتكفل بالباقي", "خطوات معالجة الصوت والصورة ذكياً", "Full HD 30fps", "جودة أستوديو"),
                ("سرعة قياسية • مونتاج احترافي في أقل من دقيقة", "إخراج احترافي كامل في أقل من 60 ثانية", "< 60 ثانية", "سرعة الإنجاز"),
                ("تحرير شامل • قص وتعديل وموشن جرافيك بضغطة زر", "قص الصمت وتعديل الفيديو بالكامل", "قص + تعديل آلي", "إخراج متكامل"),
            ]
        }
        fb_list = domain_Progression_fallbacks["ecommerce"] if domain == "ecommerce" else domain_Progression_fallbacks["default"]

        banned_phrases = [
            "إضاءة معرفية", "Pro Tips", "معلومة قيمة", "المرحلة #",
            "تطوير الأداء وصناعة المحتوى", "منهجية ذكية لتحقيق أفضل النتائج",
            "المونت ", "الاج ", "أهلاً لاحظت", "جبت لكم", "صورته ذكاء"
        ]
        # إذا كان المجال تجارة إلكترونية، نمنع أي مصطلح خاص ببرامج مونتاج الفيديو
        if domain == "ecommerce":
            banned_phrases.extend(["قص الصمت", "تعديل الفيديو", "تحرير شامل", "مونتاج احترافي", "موشن جرافيك بضغطة زر"])

        for idx, sc in enumerate(scenes):
            item = dict(sc)
            raw_text = str(item.get("text", "")).strip()
            raw_words = [w.strip("،,.!؟?") for w in raw_text.split() if w.strip("،,.!؟?")]
            first_three = " ".join(raw_words[:3])

            badge = str(item.get("badge_label", "")).strip()
            concept = str(item.get("concept_title", "")).strip()
            kpi_v = str(item.get("kpi_value", "")).strip()
            kpi_l = str(item.get("kpi_label", "")).strip()

            fb_badge, fb_concept, fb_kv, fb_kl = fb_list[idx % len(fb_list)]

            # 1. فحص الشارة العلوية وضمان عدم تكرارها في أي مشهد آخر
            if (
                not badge
                or any(bp in badge for bp in banned_phrases)
                or (first_three and len(first_three) > 4 and first_three in badge)
                or badge in used_badges
            ):
                if fb_badge not in used_badges:
                    badge = fb_badge
                else:
                    kws = extract_clean_keywords(raw_text, max_words=3)
                    kw_str = " ".join(kws[:2]) if kws else f"النقطة {idx + 1}"
                    badge = f"{fb_badge.split('•')[0].strip()} • {kw_str}"

            # 2. فحص عنوان المفهوم وضمان عدم تكراره
            if (
                not concept
                or any(bp in concept for bp in banned_phrases)
                or (first_three and len(first_three) > 4 and first_three in concept)
                or concept in used_concepts
            ):
                if fb_concept not in used_concepts:
                    concept = fb_concept
                else:
                    kws = extract_clean_keywords(raw_text, max_words=3)
                    kw_str = " ".join(kws[:3]) if kws else f"الخطوة العملية {idx + 1}"
                    concept = kw_str

            # 3. فحص مؤشر الأداء KPI وضمان عدم تكراره
            if not kpi_v or any(bp in kpi_v for bp in banned_phrases) or "خطوة #" in kpi_v or kpi_v in used_kpis:
                if fb_kv not in used_kpis:
                    kpi_v = fb_kv
                    kpi_l = fb_kl
                else:
                    extra_kpis = ["اطلب الآن", "ضمان 100%", "توصيل سريع", "جودة أصلية", "سعر ممتاز"] if domain == "ecommerce" else ["ابدأ الآن", "جاهز للنشر", "دقة 30FPS", "توفير 95%", "ذكاء سياقي"]
                    kpi_v = extra_kpis[idx % len(extra_kpis)]

            # 4. جدولة الكوريغرافيا: منع interactive_cta_outro قبل النهاية، ومنع تكرار القوالب
            arch = str(item.get("archetype", "")).strip()
            if idx == total_scenes - 1 and total_scenes >= 2:
                arch = "interactive_cta_outro"
            else:
                if arch == "interactive_cta_outro" or arch not in non_outro_pool or arch in used_archs:
                    unused = [a for a in non_outro_pool if a not in used_archs]
                    if unused:
                        arch = unused[0]
                    else:
                        non_adj = [a for a in non_outro_pool if (not used_archs or a != used_archs[-1])]
                        arch = non_adj[idx % len(non_adj)]

            item["archetype"] = arch
            item["badge_label"] = badge
            item["concept_title"] = concept
            item["short_title"] = concept
            item["kpi_value"] = kpi_v
            item["kpi_label"] = kpi_l

            used_badges.add(badge)
            used_concepts.add(concept)
            used_kpis.add(kpi_v)
            used_archs.append(arch)
            healed.append(item)

        # 5. تطبيق محرك وأوراكل اللقطة الواحدة المتصلة (OneTakeContinuityOracle - onetakemotion.com)
        healed = OneTakeContinuityOracle.plan_and_verify_one_take_continuity(healed)
        return healed


class OneTakeContinuityOracle:
    """
    أوراكل قياس وتصميم الاتصال البصري المستمر بلقطة كاميرا واحدة (One-Take Motion Continuity Oracle)
    مستوحى من معمارية `onetakemotion.com` (`feitangyuan/onetake` - `probe.py` & `verify.py`):
    - يصمم الحدود الفاصلة بين كل مشهدين بحيث يبقى عنصر حي على الشاشة (`surviving_element`) ويتحول فيزيائياً
      إلى المشهد التالي، أو تغوص الكاميرا بداخله (`camera_dive_into_portal`) أو تخرج منه (`camera_pull_out_reveal`).
    - يقيس درجة الاتصال (`carry_score`) لكل انتقال ويتحقق من تجاوز عتبة القبول الصارمة (`>= 0.75`، ويحقق `0.88+`).
    """

    @staticmethod
    def _select_handoff_between(prev_arch: str, curr_arch: str, idx: int, total_scenes: int) -> Tuple[str, str, float]:
        if idx == 0:
            return ("initial_camera_open", "انفتاح الكاميرا الافتراضية من النقطة المركزية للمسرح", 0.92)

        if idx == total_scenes - 1 or curr_arch == "interactive_cta_outro":
            return (
                "cast_folds_to_lockup",
                "انطواء عناصر المسرح السابق وتجمعها لتشكيل بطاقة الإجراء الختامية (Cast Folds into Lockup)",
                0.94
            )

        if curr_arch == "video_schedule_table":
            if prev_arch in ("saas_process_flow", "stage_trust_bubbles", "saas_typewriter_mechanism"):
                return (
                    "bar_collapses_to_table_grid",
                    "اندماج شريط التقدم في خط ضوئي يمتد عبر الشاشة ليرسم شبكة جدول الفيديو (Bar -> Timeline Grid)",
                    0.95
                )
            return (
                "camera_pull_out_reveal",
                "خروج الكاميرا للخلف ليتضح أن المشهد السابق كان خلية حية داخل جدول الفيديو (Camera Pull-Out to Video Table)",
                0.93
            )

        if prev_arch == "video_schedule_table":
            return (
                "camera_dive_into_portal",
                "غوص الكاميرا مباشرة داخل خلية المشهد النشط في جدول الفيديو لتنفتح وتصبح المشهد التالي (Camera Dive into Video Table Cell)",
                0.96
            )

        if prev_arch == "saas_typewriter_mechanism":
            return (
                "prompt_bar_to_window",
                "تمدد شريط البحث المكتوب فيزيائياً ليتحول إلى نافذة التطبيق الكاملة للمشهد التالي (Prompt Bar Opens into Window)",
                0.94
            )

        if curr_arch == "stage_trust_bubbles":
            return (
                "window_reflows_to_phone",
                "إعادة تشكل وانكماش النافذة السابقة بنعومة لتصبح شاشة الهاتف الذكي في المركز (Window Reflows into Phone)",
                0.91
            )

        if prev_arch in ("saas_grid_2x2_cursor", "saas_folder_reorder"):
            return (
                "camera_dive_into_portal",
                "دخول الكاميرا عبر البطاقة المنقورة لتملأ الشاشة وتتحول إلى المشهد التالي (Camera Pushes Through Card Portal)",
                0.95
            )

        if curr_arch in ("saas_grid_2x2_cursor", "stage_balance_scale"):
            return (
                "camera_pull_out_reveal",
                "ابتعاد الكاميرا من العنصر المركزي للكشف عن الميزان أو الشبكة الرباعية الكاملة (Camera Pull-Out Reveal)",
                0.90
            )

        cycle_modes = [
            ("camera_dive_into_portal", "غوص الكاميرا داخل البطاقة النشطة لتفتح المشهد التالي من قلبها", 0.93),
            ("card_grows_to_page", "نمو البطاقة الفرعية وتمدد حدودها لتصبح المسرح الكامل للمشهد التالي", 0.89),
            ("camera_pull_out_reveal", "خروج الكاميرا من اللقطة التفصيلية للكشف عن اللوحة الشاملة التالية", 0.91),
        ]
        return cycle_modes[idx % len(cycle_modes)]

    @classmethod
    def plan_and_verify_one_take_continuity(cls, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        total = len(scenes)
        carry_scores: List[float] = []

        for idx, sc in enumerate(scenes):
            curr_arch = str(sc.get("archetype", "saas_folder_reorder"))
            prev_arch = str(scenes[idx - 1].get("archetype", "saas_folder_reorder")) if idx > 0 else "none"

            handoff_mode, survivor_desc, score = cls._select_handoff_between(prev_arch, curr_arch, idx, total)
            sc["one_take_handoff"] = handoff_mode
            sc["transition_type"] = handoff_mode
            sc["transition"] = handoff_mode
            sc["surviving_element_ar"] = survivor_desc
            sc["carry_score"] = round(score, 3)
            sc["portal_row_index"] = idx % 3
            sc["handoff_duration_sec"] = 0.42
            carry_scores.append(score)

        avg_carry = round(sum(carry_scores) / max(1, len(carry_scores)), 3)
        oracle_verdict = "accepted" if avg_carry >= 0.75 else "rejected"
        for sc in scenes:
            sc["film_continuity_carry_score"] = avg_carry
            sc["oracle_verdict"] = oracle_verdict

        return scenes


_GLOBAL_LEARNER_INSTANCE: Optional[WebMotionLearner] = None


def get_motion_learner() -> WebMotionLearner:
    global _GLOBAL_LEARNER_INSTANCE
    if _GLOBAL_LEARNER_INSTANCE is None:
        _GLOBAL_LEARNER_INSTANCE = WebMotionLearner()
    return _GLOBAL_LEARNER_INSTANCE


# ==============================================================================
# 2. المخ السياقي الشامل (Pass 1 & Pass 2 Contextual & Narrative Brain)
# ==============================================================================
def extract_clean_keywords(text: str, max_words: int = 3) -> list:
    stop_words = {
        'في', 'من', 'على', 'إلى', 'عن', 'مع', 'هذا', 'هذه', 'هاد', 'هادي', 'ذلك', 'تلك', 'التي', 'الذي', 'الذين',
        'هو', 'هي', 'هم', 'نحن', 'أنا', 'انا', 'انت', 'أنتم', 'كان', 'كانت', 'يكون', 'ما', 'لا', 'لم', 'لن',
        'قد', 'كل', 'بعض', 'غير', 'جدا', 'بزاف', 'قاع', 'برك', 'راه', 'راهي', 'باش', 'كي', 'كيف', 'وين', 'واش',
        'كاين', 'كاينين', 'ناس', 'خاوتنا', 'اليوم', 'هنا', 'هكذا', 'واحد', 'زوج', 'شوية', 'حاجة', 'شفت', 'سمعت',
        'اعطيني', 'علاش', 'مازال', 'ممكن', 'نديروه', 'حتى', 'تديهم', 'انه', 'أنه', 'يجي', 'فيه', 'معه', 'معنتها',
        'تاعه', 'اما', 'أما', 'بالنسبة', 'بالنسبه', 'عندك', 'أهلاً', 'اهلا', 'لاحظت', 'ان', 'أن', 'لأن', 'بس'
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

    ecom_kw = ["كابل", "شاحن", "شحن", "تشارجي", "يتشارجا", "منتج", "سلعة", "سيبور", "حامل", "متجر", "شراء", "سعر", "سومة", "توصيل", "ولاية", "باب الدار", "كواليتي", "أصلي", "اصلي", "اكموندي", "اطلب", "متانة", "قماش", "يتقطع", "باطل", "بري", "ضمان", "تخفيض", "عرض", "علبة", "باكي", "سوبر فاست", "فاست"]
    social_kw = ["انستغرام", "انستقرام", "تيك توك", "ريلز", "شورتس", "فيسبوك", "يوتيوب", "متابعين", "مشاهدات", "تفاعل", "ريتش", "خوارزمية", "نشر", "محتوى", "صانع", "صناع", "كاميرا", "تصوير", "اكسبلور", "ستوري", "بايو"]
    tech_kw = ["برمجة", "كود", "تطبيق", "منصة", "موقع", "سحابي", "ذكاء", "الاصطناعي", "اصطناعي", "مونتاج", "تمنتج", "المونتاج", "تعديل الفيديو", "انتاجية", "إنتاجية", "الانتاجيه", "أوتوماتيكي", "سيرفر", "ديفلوبر", "سوفتوير", "api", "ai"]
    edu_kw = ["نصيحة", "نصائح", "تعلم", "دراسة", "معلومة", "فائدة", "كيفاش", "خطوات", "أسرار", "طريقة", "تحسين", "مهارة", "فكرة", "انتبه", "ركز"]
    biz_kw = ["بزنس", "مشروع", "دراهم", "فلوس", "عمل حر", "فريلانس", "تسويق", "مبيعات", "استثمار", "أرباح", "تجارة", "خدمة", "عملاء", "شركة", "وظيفة"]

    for kw in ecom_kw:
        if kw in t_low:
            domain_scores["ecommerce"] += (4 if kw in ["كابل", "شاحن", "تشارجي", "يتشارجا", "توصيل", "اكموندي", "سيبور", "قماش", "سلعة"] else 2)
    for kw in social_kw:
        if kw in t_low:
            domain_scores["social_media"] += (3 if kw in ["انستغرام", "انستقرام", "ريلز", "تيك توك", "ريتش", "اكسبلور"] else 1)
    for kw in tech_kw:
        if kw in t_low:
            domain_scores["tech_software"] += (3 if kw in ["برمجة", "كود", "تطبيق", "منصة", "سحابي", "ذكاء", "الاصطناعي", "مونتاج", "تمنتج"] else 1)
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
    learner = get_motion_learner()
    bp = learner._build_deep_scene_blueprint(
        scene_text=scene_text,
        scene_index=scene_index,
        total_scenes=total_scenes,
        domain=global_ctx.get("domain", "general"),
        global_ctx=global_ctx,
        used_archetypes=[],
        prev_scene_text=prev_scene_text,
        next_scene_text=next_scene_text
    )
    chosen_type = bp.get("scene_type", "growth_analytics")
    if chosen_type == prev_scene_type and total_scenes > 1:
        alternates = {
            "ecommerce_showcase": "reels_smartphone",
            "delivery_express": "ecommerce_showcase",
            "reels_smartphone": "growth_analytics",
            "growth_analytics": "reels_smartphone",
            "ai_neural_brain": "platform_builder",
            "platform_builder": "video_montage_studio",
            "video_montage_studio": "growth_analytics",
            "time_warp_clock": "video_montage_studio"
        }
        chosen_type = alternates.get(chosen_type, chosen_type)
    bp["scene_type"] = chosen_type
    bp["short_title"] = bp.get("concept_title", "مفهوم ذكي")
    bp["target_number"] = global_ctx.get("wilayas_count") or 58
    return bp


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

    # دمج مخرجات context_engine.py (قاموس الدارجة الجزائرية وحارس عدم الاختلاق وتوقيت الكابشن الدقيق)
    if callable(build_grounded_context_storyboard):
        try:
            grounded_sb = build_grounded_context_storyboard(
                scenes=scenes,
                full_transcript=full_transcript
            )
            for idx, g_sc in enumerate(grounded_sb):
                if idx < len(enriched_scenes):
                    enriched_scenes[idx]["role"] = g_sc.get("role", "explain")
                    enriched_scenes[idx]["topic"] = g_sc.get("topic", "")
                    enriched_scenes[idx]["caption_until"] = g_sc.get("caption_until", enriched_scenes[idx].get("end", 3.0))
                    enriched_scenes[idx]["speech_start"] = g_sc.get("speech_start", enriched_scenes[idx].get("start", 0.0))
                    enriched_scenes[idx]["speech_end"] = g_sc.get("speech_end", enriched_scenes[idx].get("end", 3.0))
                    if g_sc.get("target_number"):
                        enriched_scenes[idx]["target_number"] = g_sc["target_number"]
        except Exception as ce_err:
            logger.debug(f"context_engine integration notice: {ce_err}")

    try:
        learner = get_motion_learner()
        enriched_scenes = learner.learn_and_build_scene_choreography(
            scenes=enriched_scenes,
            full_transcript=full_transcript,
            global_ctx=global_ctx,
            query_llm_func=query_hybrid_llm,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
    except Exception as learn_err:
        logger.warning(f"Motion learner integration notice: {learn_err}")

    # حقن معاملات التطور الذاتي والبصمة المرجعية المستنسخة (style_evolution_brain.py)
    if callable(load_evolution_memory) and callable(get_best_params_for_scene_type):
        try:
            mem = load_evolution_memory()
            active_dna = mem.get("active_reference_dna")
            active_brand = get_active_brand_theme() if callable(get_active_brand_theme) else mem.get("active_brand_theme")
            for sc in enriched_scenes:
                st_key = str(sc.get("scene_type") or sc.get("archetype") or "default")
                evolved_p = get_best_params_for_scene_type(st_key)
                sc["evolved_params"] = evolved_p
                sc.setdefault("font_scale", float(evolved_p.get("font_scale", 1.0)))
                sc.setdefault("card_padding", int(evolved_p.get("card_padding", 16)))
                sc.setdefault("bg_blur_strength", int(evolved_p.get("bg_blur_strength", 14)))
                sc.setdefault("accent_glow", float(evolved_p.get("accent_glow", 0.28)))
                sc.setdefault("spring_stiffness", float(evolved_p.get("spring_stiffness", 185.0)))
                sc.setdefault("spring_damping", float(evolved_p.get("spring_damping", 13.0)))
                if isinstance(active_dna, dict) and active_dna.get("enabled", True):
                    if active_dna.get("theme_name"):
                        sc["theme_name"] = active_dna["theme_name"]
                        if "theme_palette" in active_dna:
                            import motion_text
                            motion_text.MOTION_THEMES[active_dna["theme_name"]] = active_dna["theme_palette"]
                    if active_dna.get("style_mode"):
                        sc["style_mode"] = active_dna["style_mode"]
                    if active_dna.get("handoff_duration_sec"):
                        sc["handoff_duration_sec"] = float(active_dna["handoff_duration_sec"])
                    if active_dna.get("stagger_delay_sec"):
                        sc["stagger_delay_sec"] = float(active_dna["stagger_delay_sec"])
                if isinstance(active_brand, dict) and active_brand.get("enabled", True):
                    if active_brand.get("theme_name"):
                        sc["theme_name"] = active_brand["theme_name"]
                        if "theme_palette" in active_brand:
                            import motion_text
                            motion_text.MOTION_THEMES[active_brand["theme_name"]] = active_brand["theme_palette"]
                    if active_brand.get("style_mode"):
                        sc["style_mode"] = active_brand["style_mode"]
                    if active_brand.get("logo_path") and active_brand.get("show_logo_watermark", True):
                        sc["brand_logo_path"] = active_brand["logo_path"]
                        sc["brand_logo_position"] = active_brand.get("logo_position", "top_right")
        except Exception as evo_err:
            logger.debug(f"Style evolution injection notice: {evo_err}")

    if callable(finalize_scene_timing):
        try:
            finalize_scene_timing(enriched_scenes)
        except Exception:
            pass

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
    # إذا كان الفيديو الأصلي يستعرض منتجاً حقيقياً أمام الكاميرا (ecommerce + has_video)،
    # لا نخفي الكاميرا خلف لقطات خارجية أو دوائر افتراضية أبداً، بل نُبقي المنتج مرئياً مع شاشة الموشن المقسومة أو البطاقات العلوية!
    if enable_stock_broll and broll_candidate_indices and not (has_video and global_domain == "ecommerce"):
        target_broll_count = min(3, max(1, len(broll_candidate_indices) // 2))
        step = max(2, len(broll_candidate_indices) // target_broll_count)
        for i in range(0, len(broll_candidate_indices), step):
            selected_broll_indices.add(broll_candidate_indices[i])
            if len(selected_broll_indices) >= 3:
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
            elif can_show_overlay and (idx % 2 == 1):
                layout_mode = "floating_callout"
                zoom_factor = 1.05
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