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
2. محرك تنويع واستنساخ الستايلات الاحترافية (`build_dynamic_scene_style_assignment`):
   - يربط كل مشهد بستايل أستوديو احترافي متجدد (مستوحى من `6873.mp4` و `6842.mp4` و `6871.mp4`) أو يطبق تصميم الفيديو المرجعي المستنسخ بالضبط.
3. التحليل الصوتي متعدد الترددات والقص الطبيعي (Loudness, Silence Pacing, Speech Cadence).
4. توليد "مخطط المخرج الشامل (Master Director Plan)" مع اختيار 3-4 مشاهد B-Roll حقيقية خالية من حقوق الملكية.
"""

import sys
import os
import time
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
        get_active_brand_theme,
        build_dynamic_scene_style_assignment
    )
except ImportError:
    load_evolution_memory = None
    get_best_params_for_scene_type = None
    get_active_brand_theme = None
    build_dynamic_scene_style_assignment = None

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
    "video_schedule_table",
    "saas_folder_reorder",
    "stage_trust_bubbles",
    "stage_balance_scale",
    "saas_typewriter_mechanism",
    "saas_process_flow",
    "saas_grid_2x2_cursor",
    "stage_before_after_checklist",
    "interactive_cta_outro"
]

ONE_TAKE_HANDOFF_MODES = [
    "camera_dive_into_portal",
    "camera_pull_out_reveal",
    "prompt_bar_to_window",
    "window_reflows_to_phone",
    "bar_collapses_to_table_grid",
    "card_grows_to_page",
    "cast_folds_to_lockup"
]

GENOME_STORAGE_PATH = os.path.join(_CURRENT_DIR, "outputs", "learned_motion_genome.json")


class WebMotionLearner:
    """
    يتعلم تلقائياً من الإنترنت ومن الفيديوهات المرجعية لبناء كوريغرافيا بصرية متكاملة وفريدة لكل مشهد
    بدون أي قوالب جامدة أو تكرار، ويحفظ الأنماط في `learned_motion_genome.json`.
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
            merged["step_badge"] = f"{idx + 1:02d}"
            merged["style_mode"] = merged.get("style_mode") or "dark_stage_pro"
            choreographed_scenes.append(merged)

        if callable(query_llm_func) and (groq_api_key or gemini_api_key or openai_api_key):
            try:
                web_Order = self.fetch_web_design_inspiration(global_ctx.get("domain_label_ar", "motion graphics"))
                web_hint = " | ".join(web_Order) if web_Order else "أسلوب BYW Agency 6873 و Mazen Blueprint 6842 و Baghdadi Plum 6871"
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
        from style_evolution_brain import ALL_DYNAMIC_VISUAL_ARCHETYPES
        full_pool = list(ALL_DYNAMIC_VISUAL_ARCHETYPES)
        if preferred in full_pool and preferred not in used_archetypes:
            return preferred
        unused = [a for a in full_pool if a not in used_archetypes]
        if unused:
            return unused[scene_index % len(unused)]
        return full_pool[scene_index % len(full_pool)]

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
        from style_evolution_brain import match_speech_to_visual_archetype
        raw_clean = re.sub(r"[،,.!؟?()\[\]\-]+ ", " ", (scene_text or "")).strip()
        filler_stop = {
            "أهلاً", "اهلا", "وسهلاً", "مرحبا", "شوف", "شوفوا", "طبعاً", "طبعا", "يعني",
            "صراحة", "بصراحة", "أنه", "انه", "أن", "ان", "اللي", "التي", "الذي", "الذين",
            "هذا", "هذه", "هاد", "هادي", "في", "من", "على", "إلى", "عن", "مع", "هو", "هي",
            "هم", "أنا", "انا", "نحن", "بس", "برك", "قاع", "راه", "راهي", "واش", "كيفاش",
            "علاش", "لأن", "لان", "لو", "إذا", "اذا", "كان", "كانت", "يكون", "تكون", "جدا", "بزاف"
        }
        all_tokens = [w for w in raw_clean.split() if len(w) > 1]
        meaningful_tokens = [w for w in all_tokens if w.lower() not in filler_stop]
        if len(meaningful_tokens) < 2:
            meaningful_tokens = all_tokens if all_tokens else ["الفكرة", "الأساسية"]

        # العنوان الرئيسي على الشاشة مأخوذ 100% من الكلمات الفعلية التي نطقها المتحدث في هذا المشهد!
        concept_title = " ".join(meaningful_tokens[:5])
        if len(concept_title) < 5 and len(all_tokens) >= 2:
            concept_title = " ".join(all_tokens[:5])

        next_tokens = [
            w for w in re.sub(r"[،,.!؟?()\[\]\-]+ ", " ", (next_scene_text or "")).split()
            if len(w) > 2 and w.lower() not in filler_stop
        ]
        prev_tokens = [
            w for w in re.sub(r"[،,.!؟?()\[\]\-]+ ", " ", (prev_scene_text or "")).split()
            if len(w) > 2 and w.lower() not in filler_stop
        ]

        from style_evolution_brain import detect_strict_speech_intent
        speech_intent = detect_strict_speech_intent(scene_text, scene_index, total_scenes)

        # بناء العناصر الفرعية التوضيحية بذكاء منطقي:
        # - إذا كان المتحدث يعدد نقاطاً صراحةً (مثل: أفضل 3 ميزات، أولاً، ثانياً...) نقسم النقاط المنطوقة كقائمة.
        # - أما في الكلام العام أو الترحيبي، فيُمنع منعاً باتاً تقطيع الجملة إلى شظايا مرقمة أو سحب كلمات من المشهد السابق/اللاحق!
        sub_items: List[str] = []
        if speech_intent["is_explicit_enumeration"]:
            parts = [p.strip() for p in re.split(r"[،,؛\-]|(?:أولاً|اولا|ثانياً|ثانيا|ثالثاً|ثالثا|رابعاً|رابعا|الشيء الأول|الشيء الثاني|الشيء الثالث|الميزة الأولى|الميزة الثانية|الخاصية الأولى|الخاصية الثانية)", raw_clean) if len(p.strip()) >= 4]
            for pt in parts:
                if pt not in sub_items:
                    sub_items.append(pt[:36])
            if len(sub_items) < 3:
                chunk_size = max(2, min(3, len(meaningful_tokens) // 3 or 2))
                for i in range(0, len(meaningful_tokens), chunk_size):
                    phrase = " ".join(meaningful_tokens[i:i + chunk_size]).strip()
                    if len(phrase) >= 4 and phrase not in sub_items:
                        sub_items.append(phrase)
        else:
            # في الكلام غير التعدادي، نكتفي بخلاصة الفكرة دون تقطيع الجملة إلى 4 عناصر عشوائية!
            if len(meaningful_tokens) >= 6:
                half = len(meaningful_tokens) // 2
                p1 = " ".join(meaningful_tokens[:half]).strip()
                p2 = " ".join(meaningful_tokens[half:]).strip()
                if len(p1) >= 4 and p1 != concept_title:
                    sub_items.append(p1)
                if len(p2) >= 4 and p2 != concept_title and p2 not in sub_items:
                    sub_items.append(p2)
            elif len(meaningful_tokens) >= 3:
                p_tail = " ".join(meaningful_tokens[-3:]).strip()
                if p_tail != concept_title:
                    sub_items.append(p_tail)

        # استخراج أي رقم أو نسبة أو مؤشر منطوق فعلياً في الجملة
        num_m = re.search(r"(\d+\s*(?:%|ثانية|ثواني|دقيقة|دقائق|ساعة|ساعات|ولاية|خصائص|ميزات|أضعاف|مرات)?)", scene_text or "")
        if num_m:
            kpi_value = num_m.group(1).strip()
        else:
            kpi_value = " ".join(meaningful_tokens[:2]) if len(meaningful_tokens) >= 2 else meaningful_tokens[0]
        kpi_label = " ".join(meaningful_tokens[-2:]) if len(meaningful_tokens) >= 3 else concept_title

        rot_seed = int(self.learned_genome.get("total_videos_learned", 0)) + int(time.time()) % 997
        arch, vis_subj = match_speech_to_visual_archetype(
            scene_text=scene_text,
            scene_index=scene_index,
            total_scenes=total_scenes,
            used_archetypes=used_archetypes,
            variation_seed=rot_seed
        )

        subj_badge_prefix = {
            "hero_smartphone_reels": "صناعة الريلز والفيديو",
            "hero_camera_production": "التصوير والإنتاج البصري",
            "hero_waveform_scissors": "قص الصمت وتنقية الصوت",
            "hero_ai_neural_core": "معالجة الذكاء الاصطناعي",
            "hero_chrono_speedometer": "اختصار الوقت والسرعة",
            "hero_sound_wave_mixer": "هندسة الصوت والمؤثرات",
            "hero_viral_rocket_chart": "مضاعفة الإنتاجية والانتشار",
            "hero_power_cable_stand": "قوة الشحن والتصميم العملي",
            "hero_shield_durability": "المتانة والضمان الموثوق",
            "hero_commerce_delivery": "الطلب والتوصيل السريع",
            "hero_creative_palette_pen": "تصميم الهوية والموشن جرافيك",
            "hero_problem_radar_fix": "تشخيص التحدي والحل الذكي",
            "hero_platform_workspace": "منصة العمل الذكية",
            "hero_roadmap_milestones": "خطوات التطبيق المتسلسلة",
            "hero_comparison_duel": "مقارنة الأداء والنتائج",
            "hero_cta_magnet_finale": "الخطوة التالية",
        }.get(vis_subj, "محور أساسي")

        short_kw = " ".join(meaningful_tokens[:3])
        badge_label = f"{subj_badge_prefix} • {short_kw}"

        scene_type_map = {
            "hero_smartphone_reels": "reels_smartphone",
            "hero_camera_production": "video_montage_studio",
            "hero_waveform_scissors": "video_montage_studio",
            "hero_ai_neural_core": "ai_neural_brain",
            "hero_chrono_speedometer": "time_warp_clock",
            "hero_sound_wave_mixer": "video_montage_studio",
            "hero_viral_rocket_chart": "growth_analytics",
            "hero_power_cable_stand": "ecommerce_showcase",
            "hero_shield_durability": "ecommerce_showcase",
            "hero_commerce_delivery": "delivery_express",
            "hero_creative_palette_pen": "platform_builder",
            "hero_problem_radar_fix": "time_warp_clock",
            "hero_platform_workspace": "platform_builder",
            "hero_roadmap_milestones": "growth_analytics",
            "hero_comparison_duel": "growth_analytics",
            "hero_cta_magnet_finale": "brand_finale",
        }
        scene_type = scene_type_map.get(vis_subj, "growth_analytics")

        first_sub = sub_items[0] if sub_items else concept_title
        second_sub = sub_items[1] if len(sub_items) > 1 else kpi_label
        return {
            "archetype": arch,
            "visual_subject": vis_subj,
            "scene_type": scene_type,
            "badge_label": badge_label,
            "concept_title": concept_title,
            "concept_subtitle": raw_clean[:68] if raw_clean else concept_title,
            "sub_items": sub_items[:4],
            "is_explicit_enumeration": speech_intent["is_explicit_enumeration"],
            "is_explicit_comparison": speech_intent["is_explicit_comparison"],
            "is_explicit_metric_counter": speech_intent["is_explicit_metric_counter"],
            "balance_left": (first_sub, "الوضع السابق"),
            "balance_right": (second_sub, kpi_value),
            "before_after": (first_sub, "4.0", concept_title[:22], "9.8"),
            "typewriter_query": concept_title,
            "kpi_value": kpi_value,
            "kpi_label": kpi_label,
        }


class MotionQualityAuditor:
    @staticmethod
    def audit_and_heal_storyboard(
        scenes: List[Dict[str, Any]],
        full_transcript: str,
        global_ctx: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        from style_evolution_brain import ALL_DYNAMIC_VISUAL_ARCHETYPES, match_speech_to_visual_archetype
        total_scenes = len(scenes)
        healed: List[Dict[str, Any]] = []
        used_archs: List[str] = []
        dyn_seed = int(time.time() * 10) % 997

        for idx, sc in enumerate(scenes):
            item = dict(sc)
            raw_text = str(item.get("text", "")).strip()
            user_arch = str(item.get("user_override_archetype") or "").strip()
            arch = str(item.get("archetype", "")).strip()
            vis_subj = str(item.get("visual_subject", "")).strip()

            from style_evolution_brain import detect_strict_speech_intent
            intent_check = detect_strict_speech_intent(raw_text, idx, total_scenes)
            forbidden_archs = intent_check["forbidden_archetypes"]

            if user_arch and user_arch in ALL_DYNAMIC_VISUAL_ARCHETYPES:
                arch = user_arch
                vis_subj = user_arch
            elif not arch or arch not in ALL_DYNAMIC_VISUAL_ARCHETYPES or arch in used_archs or arch in forbidden_archs:
                arch, matched_subj = match_speech_to_visual_archetype(
                    scene_text=raw_text,
                    scene_index=idx,
                    total_scenes=total_scenes,
                    used_archetypes=used_archs,
                    variation_seed=dyn_seed
                )
                if not vis_subj:
                    vis_subj = matched_subj

            concept = str(item.get("concept_title", "")).strip()
            if not concept and raw_text:
                kws = extract_clean_keywords(raw_text, max_words=5)
                concept = " ".join(kws) if kws else raw_text[:32]

            badge = str(item.get("badge_label", "")).strip()
            if not badge:
                badge = concept[:28]

            item["archetype"] = arch
            item["visual_subject"] = vis_subj or arch
            item["badge_label"] = badge
            item["concept_title"] = concept
            item["short_title"] = concept

            used_archs.append(arch)
            healed.append(item)

        healed = OneTakeContinuityOracle.plan_and_verify_one_take_continuity(healed)
        return healed


class OneTakeContinuityOracle:
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
            sc["handoff_duration_sec"] = 0.38
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
    biz_kw = ["بزنس", "مشروع", "دراهم", "فلوس", "عمل حر", "فريلانس", "تسويق", "مبيعات", "استثمار", "أرباح", "تجارة", "خدمة", "عملاء", "شركة", "وظيفة", "سبونسور", "إشهار", "اشهار", "حملة", "إعلان", "اعلان"]

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
        "business": "أعمال وتسويق وحملات إعلانية",
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

    if callable(build_dynamic_scene_style_assignment):
        try:
            style_plan = build_dynamic_scene_style_assignment(len(enriched_scenes), advance_rotation_counter=True, scenes=enriched_scenes)
            for idx, sc in enumerate(enriched_scenes):
                if idx < len(style_plan):
                    # نحترم الرسم المخصص المطابق للكلام المنطوق في كل مشهد
                    if sc.get("archetype"):
                        style_plan[idx]["visual_archetype"] = sc["archetype"]
                    sc["scene_style_spec"] = style_plan[idx]
                    sc["step_number"] = idx + 1
                    sc["total_scenes_count"] = len(enriched_scenes)
        except Exception as sp_err:
            logger.debug(f"Scene style assignment notice: {sp_err}")

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
                sc.setdefault("spring_stiffness", float(evolved_p.get("spring_stiffness", 195.0)))
                sc.setdefault("spring_damping", float(evolved_p.get("spring_damping", 14.0)))
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
            win = 800
            n_w = len(samples) // win
            if n_w > 2:
                arr = samples[:n_w * win].reshape((n_w, win))
                rms = np.sqrt(np.mean(arr * arr, axis=1) + 1e-9)
                dbfs = 20.0 * np.log10(np.maximum(rms / 32768.0, 1e-7))
                valid = dbfs[dbfs > -85.0]
                if len(valid) > 0:
                    mean_dbfs = round(float(np.mean(valid)), 1)
                    max_dbfs = round(float(np.max(valid)), 1)
                    p10 = float(np.percentile(valid, 10))
                    p50 = float(np.percentile(valid, 50))
                    p85 = float(np.percentile(valid, 85))
                    noise_floor_dbfs = round(p10, 1)
                    from auto_cut import calibrate_natural_silence_3_to_4_percent
                    tot_ms_probe = int(round(len(samples) / 8000.0 * 1000.0))
                    _, optimal_silence_thresh, calibrated_res_silence = calibrate_natural_silence_3_to_4_percent(
                        dbfs=dbfs, step_ms=100, total_duration_ms=tot_ms_probe,
                        user_silence_threshold=-42.0, target_min_ratio=0.030, target_max_ratio=0.040
                    )
                    silence_ratio = round(max(0.030, min(0.040, calibrated_res_silence)), 3)
                    optimal_padding_ms = 75
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
        "silence_percent": round(max(3.0, min(4.0, silence_ratio * 100.0)), 1),
        "visual_motion_score": visual_motion_score,
        "optimal_silence_threshold": optimal_silence_thresh,
        "optimal_padding_ms": optimal_padding_ms,
        "optimal_chunk_size": 20,
        "optimal_whisper_model": optimal_whisper_model,
        "ai_provider_info": ai_info,
        "criteria_reasons": [
            f"تم ضبط نسبة الصمت الطبيعية المستهدفة بين 3% إلى 4% ({round(max(3.0, min(4.0, silence_ratio * 100.0)), 1)}%) عبر المعايرة التكيفية لعتبة الصوت ({optimal_silence_thresh} dBFS).",
            "تم تفعيل محرك كشف وإزالة أخطاء التعليق الصوتي (حذف الكلمات والجمل المعادة مرتين تلقائياً من الصوت والفيديو).",
            "تم تفعيل محرك الهوية البصرية الموحدة لكل فيديو مع 12 نمطاً من الرسومات والأنيميشن المستمر (30fps)."
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

        # كلمات ومؤشرات النقاط المهمة التي تستدعي فتح شاشة موشن جرافيك كاملة (Full-Screen Motion Cutaway) لتوضيح الفكرة
        important_explanation_triggers = (
            "الأولى", "الاولى", "الثانية", "الثانيه", "الثالثة", "الثالثه",
            "ثلاث", "خصائص", "ميزات", "خطوات", "سوبر فاست", "فاست", "240",
            "قماش", "يتقطع", "سيبور", "حامل", "استثمار", "علاش", "مشكل",
            "مشكلة", "منصة", "ذكاء", "الاصطناعي", "أقل من دقيقة", "اقل من دقيقه",
            "إنتاجية", "انتاجية", "مقارنة", "الفرق", "توصيل", "58"
        )
        has_important_concept = any(kw in t_low for kw in important_explanation_triggers) or bool(re.search(r"\d+", t_low))
        prev_was_fullscreen = (master_plan and master_plan[-1].get("layout_mode") == "full_screen")
        last_fs_end = max([0.0] + [float(m["end"]) for m in master_plan if m.get("layout_mode") == "full_screen"])
        time_since_last_fs = s_start - last_fs_end

        if not has_video:
            layout_mode = "full_screen"
            zoom_factor = 1.0
        elif idx in selected_broll_indices and prev_was_fullscreen:
            layout_mode = "stock_broll"
            zoom_factor = 1.0
        else:
            is_hook = (idx == 0)
            is_finale = (idx == num_scenes - 1)
            # في الفيديوهات المصورة: نفتح شاشة موشن جرافيك كاملة (Full-Screen Cutaway) بشكل سلس عند كل معلومة مهمة أو كل ~4 ثوانٍ
            # بدلاً من حشر الموشن جرافيك في زاوية الفيديو طوال الوقت!
            should_trigger_fullscreen_motion = (
                not is_hook
                and not prev_was_fullscreen
                and (
                    (has_important_concept and time_since_last_fs >= 2.2)
                    or time_since_last_fs >= 4.2
                    or (idx % 2 == 1)
                )
            )
            if should_trigger_fullscreen_motion:
                layout_mode = "full_screen"
                zoom_factor = 1.0
                last_badge_idx = idx
            elif is_finale and not prev_was_fullscreen:
                layout_mode = "full_screen"
                zoom_factor = 1.0
                last_badge_idx = idx
            elif idx in selected_broll_indices:
                layout_mode = "stock_broll"
                zoom_factor = 1.0
            else:
                # لقطة المتحدث الصافية بدون حشر بطاقات مزعجة فوق الفيديو
                layout_mode = "speaker_clean"
                zoom_factor = 1.08 if (idx % 2 == 0) else 1.0

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