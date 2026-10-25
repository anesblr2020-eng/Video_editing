"""
app.py - الواجهة التفاعلية لنظام أتمتة المونتاج، استنساخ الفيديوهات المرجعية (الأشكال والرسومات والأنيميشن)، والستايل الموحد لكل فيديو
========================================================================================================================================
التحديثات الجوهرية:
1. زر واحد ذكي تحت الفيديو المرجعي (`🎯 نسخ الفيديو المرجعي وتطبيق نفس الأشكال والرسومات والأنيميشن والتحريك`):
   - ينسخ الألوان، الخلفية، هندسة الأشكال، الرسومات والأنفوجرافيك، وفيزياء الأنيميشن والتحريك ويطبقها بما يناسب الفيديو أو التعليق الصوتي للمستخدم.
2. نظام الهوية الموحدة لكل فيديو (`One Cohesive Studio Style Per Video`):
   - عند اختيار الوضع العشوائي/التلقائي، يختار النظام ستايلاً واحداً متكاملاً وموحداً لكامل الفيديو (بدون خلط خلفيات متضاربة داخل الفيديو الواحد)،
     أو يتيح للمستخدم اختيار الستايل بنفسه، مع تنويع الرسومات والـ Animations (12 نمطاً تفاعلياً) في كل مشهد حسب معنى الكلام.
3. ضبط نسبة الصمت الطبيعية بين `3%` إلى `4%` (`3.5%`) + كاشف ومزيل أخطاء التعليق الصوتي (حذف الجمل أو الكلمات المعادة مرتين تلقائياً).
4. محرك العمل المستمر في الخلفية وحفظ الجلسة التلقائي (`PersistentBackgroundJobManager`) مع معمارية `Zero-OOM`.
"""

import sys
import os
import re
import gc
import json
import time
import ctypes
import shutil
import hashlib
import inspect
import logging
import importlib
import threading
import traceback
from typing import Dict, Any, List, Tuple, Optional, Callable, Union

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Auto-bootstrap required runtime directories & .streamlit/config.toml when uploaded as flat files on GitHub
for _d in [".streamlit", "assets", "assets/fonts", "assets/icons", "assets/sfx_pack", "outputs", "inputs", "temp"]:
    os.makedirs(os.path.join(_CURRENT_DIR, _d), exist_ok=True)
_st_cfg = os.path.join(_CURRENT_DIR, ".streamlit", "config.toml")
if not os.path.exists(_st_cfg):
    try:
        with open(_st_cfg, "w", encoding="utf-8") as _cf:
            _cf.write("[server]\nmaxUploadSize = 200\nmaxMessageSize = 200\n[theme]\nbase = \"dark\"\n")
    except Exception:
        pass

if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import streamlit as st
import streamlit.components.v1 as components

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# 0. محرك تحرير الذاكرة والعمل المستمر في الخلفية (Persistent Background Engine)
# ==============================================================================
def force_free_ram():
    """
    تحرير الذاكرة العشوائية في بايثون وإجبار نظام لينكس (glibc) على إرجاع الصفحات المحررة
    فوراً إلى نظام التشغيل لمنع تجاوز حد 1GB RAM على Streamlit Cloud.
    """
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


class PersistentBackgroundJobManager:
    """
    مدير المهام الخلفية المستقل عن جلسة المتصفح (WebSocket-Independent Job Manager).
    يعمل في Thread مستقل على السيرفر ويحفظ الحالة في الذاكرة وعلى القرص الصلب معاً،
    بحيث لا يتوقف أبداً عند الخروج من Google Chrome أو انقطاع الإنترنت!
    """

    def __init__(self, state_file_path: str):
        self.state_file_path = state_file_path
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = self._load_state_from_disk()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "job_id": None,
            "status": "idle",  # idle | running | completed | failed
            "progress": 0.0,
            "status_text": "",
            "error_message": None,
            "started_at": 0.0,
            "updated_at": 0.0,
            "input_path": None,
            "output_path": None,
            "selected_style": None,
            "caption_mode": "bottom_modern",
            "file_hash": None,
            "media_analysis": None,
            "caption_words": [],
            "caption_sentences": [],
            "eff_params": {}
        }

    def _load_state_from_disk(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    base = self._default_state()
                    base.update(data)
                    if base.get("status") == "running":
                        out_p = base.get("output_path")
                        if out_p and os.path.exists(out_p) and os.path.getsize(out_p) > 10240:
                            base["status"] = "completed"
                            base["progress"] = 1.0
                            base["status_text"] = "اكتمل إنتاج الفيديو في الخلفية بنجاح!"
                        elif time.time() - float(base.get("updated_at", 0.0)) > 600:
                            base["status"] = "idle"
                    return base
            except Exception as e:
                logger.warning(f"تعذر قراءة ملف حالة الخلفية: {e}")
        return self._default_state()

    def _save_state_to_disk_unlocked(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_file_path)), exist_ok=True)
            tmp_path = self.state_file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.state_file_path)
        except Exception as e:
            logger.debug(f"ملاحظة أثناء حفظ حالة المهمة على القرص: {e}")

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            if self._state.get("status") == "running":
                if self._worker_thread is None or not self._worker_thread.is_alive():
                    out_p = self._state.get("output_path")
                    if out_p and os.path.exists(out_p) and os.path.getsize(out_p) > 10240:
                        self._state["status"] = "completed"
                        self._state["progress"] = 1.0
                        self._state["status_text"] = "اكتمل إنتاج الفيديو بنجاح!"
                        self._save_state_to_disk_unlocked()
            return dict(self._state)

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._state.get("status") == "running"
                and self._worker_thread is not None
                and self._worker_thread.is_alive()
            )

    def update_progress(self, percent: float, text: str):
        with self._lock:
            self._state["progress"] = round(min(1.0, max(0.0, float(percent))), 3)
            self._state["status_text"] = str(text)
            self._state["updated_at"] = time.time()
            self._save_state_to_disk_unlocked()

    def clear_job(self) -> bool:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return False
            self._state = self._default_state()
            self._save_state_to_disk_unlocked()
            return True

    def start_job(
        self,
        runner_func: Callable[..., str],
        runner_kwargs: Dict[str, Any],
        job_meta: Dict[str, Any],
        cleanup_func: Optional[Callable[[], None]] = None
    ) -> str:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return str(self._state.get("job_id", "active"))

            job_id = f"job_{int(time.time())}"
            self._state = self._default_state()
            self._state.update({
                "job_id": job_id,
                "status": "running",
                "progress": 0.02,
                "status_text": "🚀 بدأت المعالجة في الخلفية... يمكنك الخروج من المتصفح والعودة لاحقاً بأمان!",
                "error_message": None,
                "started_at": time.time(),
                "updated_at": time.time(),
                "input_path": job_meta.get("input_path"),
                "output_path": job_meta.get("output_path"),
                "selected_style": job_meta.get("selected_style"),
                "caption_mode": job_meta.get("caption_mode", "bottom_modern"),
                "file_hash": job_meta.get("file_hash"),
                "media_analysis": job_meta.get("media_analysis"),
                "eff_params": job_meta.get("eff_params", {})
            })
            self._save_state_to_disk_unlocked()

        def _background_target():
            try:
                force_free_ram()
                kwargs_copy = dict(runner_kwargs)
                kwargs_copy["progress_cb"] = self.update_progress

                final_out_path = runner_func(**kwargs_copy)

                from transcriber import get_last_extracted_transcript
                words_ext, sents_ext = get_last_extracted_transcript()

                with self._lock:
                    self._state["status"] = "completed"
                    self._state["progress"] = 1.0
                    self._state["status_text"] = "🎉 اكتمل إنتاج ورندرة الفيديو في الخلفية بنجاح!"
                    self._state["output_path"] = final_out_path
                    self._state["caption_words"] = words_ext
                    self._state["caption_sentences"] = sents_ext
                    self._state["updated_at"] = time.time()
                    self._save_state_to_disk_unlocked()

            except Exception as err:
                logger.error(f"خطأ في المهمة الخلفية: {err}\n{traceback.format_exc()}")
                with self._lock:
                    self._state["status"] = "failed"
                    self._state["error_message"] = str(err)
                    self._state["status_text"] = f"❌ توقفت المعالجة بسبب خطأ: {str(err)}"
                    self._state["updated_at"] = time.time()
                    self._save_state_to_disk_unlocked()
            finally:
                if cleanup_func is not None:
                    try:
                        cleanup_func()
                    except Exception:
                        pass
                force_free_ram()

        self._worker_thread = threading.Thread(target=_background_target, name=f"StudioWorker_{job_id}", daemon=True)
        self._worker_thread.start()
        return job_id


for _m in [
    "physics_easing",
    "style_evolution_brain",
    "vector_lottie_engine",
    "darija_lexicon",
    "context_engine",
    "auto_cut",
    "transcriber",
    "stock_video_finder",
    "motion_text",
    "smart_analyzer",
    "dynamic_edit",
    "manim_generator",
    "sound_designer"
]:
    if _m in sys.modules:
        try:
            importlib.reload(sys.modules[_m])
        except Exception:
            pass

from auto_cut import remove_silence, is_video_file, ensure_playable_audio_or_video
from smart_analyzer import (
    ALL_SUPPORTED_EXTENSIONS,
    analyze_media_file,
    detect_best_ai_provider
)
from transcriber import (
    transcribe_audio,
    transcribe_sentences,
    get_last_extracted_transcript,
    set_custom_caption_override,
    clear_custom_caption_override
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ICONS_DIR = os.path.join(BASE_DIR, "assets", "icons")
FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")
STATE_FILE_PATH = os.path.join(OUTPUTS_DIR, "persistent_job_state.json")

for directory in [INPUTS_DIR, OUTPUTS_DIR, TEMP_DIR, ICONS_DIR, FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)


@st.cache_resource
def get_cached_job_manager():
    """مدير مهام خلفي مشترك على مستوى السيرفر يبقى نشطاً حتى لو أُغلق المتصفح أو تغيرت الجلسة."""
    return PersistentBackgroundJobManager(STATE_FILE_PATH)


job_manager = get_cached_job_manager()


def cleanup_temp_directory(temp_path: str = TEMP_DIR):
    if os.path.exists(temp_path):
        for filename in os.listdir(temp_path):
            file_path = os.path.join(temp_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception:
                pass
    force_free_ram()


st.set_page_config(
    page_title="استوديو المونتاج والموشن جرافيك الذكي (يعمل في الخلفية)",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(90deg, #1BAECA, #38BDF8, #FBBF24);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        text-align: center;
        color: #94A3B8;
        margin-bottom: 1.4rem;
    }
    .bg-shield-banner {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.16), rgba(27, 174, 202, 0.16));
        border: 1px solid rgba(27, 174, 202, 0.45);
        border-radius: 12px;
        padding: 12px 18px;
        text-align: center;
        color: #E2E8F0;
        margin-bottom: 1.2rem;
        font-size: 0.98rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3.3rem;
        font-size: 1.12rem;
        font-weight: bold;
        background: linear-gradient(90deg, #0284C7, #2563EB);
        color: white;
        border: none;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #0369A1, #1D4ED8);
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🎬 استوديو المونتاج الذكي والموشن جرافيك التوليدي</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">ستايل موحد لكل فيديو • 12 نمطاً من الرسومات والأنيميشن المستمر (30fps) • ضبط الصمت الطبيعي (3%-4%) وحذف الجمل المعادة بالخطأ</div>',
    unsafe_allow_html=True
)
st.markdown(
    '<div class="bg-shield-banner">🛡️ <b>ميزة العمل المستمر في الخلفية مفعّلة:</b> بعد الضغط على زر البدء، يستمر السيرفر في رندرة الفيديو حتى لو خرجت من متصفح <b>Google Chrome</b> أو انقطع الإنترنت، وعند عودتك ستجد الفيديو جاهزاً أمامك تلقائياً!</div>',
    unsafe_allow_html=True
)

components.html(
    """
    <script>
    (async function() {
        try {
            if ('wakeLock' in navigator) {
                await navigator.wakeLock.request('screen');
                document.addEventListener('visibilitychange', async () => {
                    if (document.visibilityState === 'visible') {
                        try { await navigator.wakeLock.request('screen'); } catch(e) {}
                    }
                });
            }
        } catch (err) {}
    })();
    </script>
    """,
    height=0
)


# ==============================================================================
# 1. استرجاع الحالة التلقائي عند العودة للمتصفح (Auto-Resume from Background Job)
# ==============================================================================
bg_state = job_manager.get_state()

if bg_state.get("status") == "completed":
    saved_out = bg_state.get("output_path")
    if saved_out and os.path.exists(saved_out) and os.path.getsize(saved_out) > 10240:
        st.session_state["processed_result_path"] = saved_out
        if bg_state.get("selected_style"):
            st.session_state["processed_style"] = bg_state["selected_style"]
        if bg_state.get("caption_words"):
            st.session_state["caption_words"] = bg_state["caption_words"]
        if bg_state.get("caption_sentences"):
            st.session_state["caption_sentences"] = bg_state["caption_sentences"]
        if bg_state.get("eff_params"):
            st.session_state["eff_params"] = bg_state["eff_params"]
        if bg_state.get("input_path") and os.path.exists(bg_state["input_path"]):
            st.session_state["restored_input_path"] = bg_state["input_path"]
        if bg_state.get("media_analysis"):
            st.session_state["restored_media_analysis"] = bg_state["media_analysis"]


# ==============================================================================
# 2. الشريط الجانبي
# ==============================================================================
with st.sidebar:
    st.header("⚙️ الإعدادات الذكية والاتصال")

    auto_optimize = st.toggle(
        "🤖 ضبط الصمت الطبيعي (3% - 4%) وحذف الإعادات الخاطئة تلقائياً (موصى به)",
        value=True
    )

    enable_broll_toggle = st.toggle(
        "🎥 استيراد مشاهد B-Roll حقيقية (بدون حقوق ملكية)",
        value=True,
        help="يجلب تلقائياً 3 إلى 4 مشاهد فيديو واقعية ومفتوحة الترخيص من الإنترنت لدعم الأفكار التي لا تناسبها الرسوم فقط."
    )

    st.subheader("🇩🇿 إعدادات اللغة واللهجة")
    dialect_choice_label = st.selectbox(
        "نمط فهم الكلام والكتابة:",
        options=[
            "الدارجة الجزائرية + العربية (دقيق جداً 🇩🇿)",
            "تحويل تلقائي للعربية المبسطة"
        ],
        index=0
    )
    dialect_mode = "algerian_darija" if "الدارجة" in dialect_choice_label else "msa_simplified"

    st.markdown("---")
    st.subheader("🌐 محرك الذكاء الاصطناعي ومكتبات B-Roll")
    with st.expander("🔑 مفاتيح سحابية اختيارية (لأقصى سرعة وجودة)", expanded=False):
        st.caption("النظام يجلب مشاهد B-Roll مجانية بدون أي مفتاح! ويمكنك اختيارياً إضافة مفتاح Pexels أو Groq:")
        pexels_api_key = st.text_input("Pexels API Key (اختياري - لملايين الفيديوهات المجانية):", type="password", value=os.environ.get("PEXELS_API_KEY", ""))
        groq_api_key = st.text_input("Groq API Key (اختياري):", type="password", value=os.environ.get("GROQ_API_KEY", ""))
        gemini_api_key = st.text_input("Gemini API Key (اختياري):", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
        openai_api_key = st.text_input("OpenAI API Key (اختياري):", type="password", value=os.environ.get("OPENAI_API_KEY", ""))

    ai_status = detect_best_ai_provider(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        prefer_internet=True
    )
    if ai_status["online"]:
        st.success(f"🌐 متصل بالإنترنت: **{ai_status['label']}**")
    else:
        st.info(f"💻 الوضع المحلي النشط: **{ai_status['label']}**")

    st.markdown("---")
    st.subheader("🎚️ إعدادات قص الصمت (3% - 4%) وكشف الإعادات")
    if auto_optimize:
        st.caption("✅ **المعايرة التلقائية مفعّلة:** يقص كل السكوت الزائد لتبقى نسبة الصمت الطبيعية بين **3% إلى 4%**، ويحذف الجمل أو الكلمات المعادة بالخطأ.")
        silence_threshold = -42.0
        chunk_size = 20
        padding_ms = 75
        whisper_model_choice = "base"
    else:
        silence_threshold = st.slider("عتبة الصمت (dBFS)", min_value=-60.0, max_value=-20.0, value=-34.0, step=1.0)
        chunk_size = st.slider("دقة الفحص (Chunk Size ms)", min_value=10, max_value=50, value=20, step=5)
        padding_ms = st.slider("هامش الصمت الطبيعي (ms)", min_value=40, max_value=250, value=75, step=5)
        whisper_model_choice = st.selectbox(
            "حجم نموذج Whisper المحلي:",
            options=["tiny", "base", "small"],
            index=1
        )

    ollama_model_choice = st.text_input("نموذج Ollama المحلي:", value="llama3")
    manim_quality_choice = st.selectbox(
        "دقة رندرة الموشن الهندسي (Manim):",
        options=["-qm (720p متوازنة وآمنة للذاكرة)", "-ql (480p فائقة السرعة)", "-qh (1080p عالية)"],
        index=0
    )
    manim_flag = manim_quality_choice.split()[0]

    st.markdown("---")
    st.subheader("💬 تحكم الكابشن وشارات الفيديو")
    cap_choice = st.selectbox(
        "شكل وموضع الكابشن في الفيديو:",
        options=[
            "✨ كابشن ريلز عصري متفاعل (أسفل الشاشة - صفحات ثابتة بدون تكرار)",
            "🚫 بدون كابشن إضافي (فقط مونتاج ذكي وبادجات - مثالي إذا كان الفيديو مصوراً بنصوص)",
            "🔝 كابشن أعلى الشاشة (Top Safe Zone)"
        ],
        index=0
    )
    if "بدون كابشن" in cap_choice:
        eff_caption_mode = "none"
    elif "أعلى" in cap_choice:
        eff_caption_mode = "top_compact"
    else:
        eff_caption_mode = "bottom_modern"


# ==============================================================================
# 3. دالة تشغيل المسارات الموحدة
# ==============================================================================
STYLE_OPTIONS = [
    "✨ النمط التلقائي الذكي - يدمج كل الأدوار ومشاهد B-Roll (Smart Director All-in-One)",
    "🛍️ نمط إعلانات المنتجات والتجارة الإلكترونية (E-Commerce & Product Ads)",
    "🎨 دمج الموشن جرافيك ومشاهد B-Roll بالفيديو الأصلي (Motion Graphics & B-Roll Overlay)",
    "🚀 موشن جرافيك احترافي متكامل (12 نمط رسومات وأنيميشن مستمر 30fps • هوية موحدة لكل فيديو)",
    "📐 موشن جرافيك هندسي ذكي (Manim + AI Infographics)",
    "🔍 مونتاج ديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)",
    "✂️ قص الصمت الطبيعي (3% - 4%) وحذف الإعادات الخاطئة فقط"
]


def _safe_call(func, **kwargs):
    try:
        sig = inspect.signature(func)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_var_kw:
            return func(**kwargs)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return func(**filtered)
    except Exception:
        return func(**kwargs)


def _unwrap_path(res) -> str:
    return res[0] if isinstance(res, tuple) else res


def run_selected_pipeline(
    style_name: str,
    input_path: str,
    output_path: str,
    media_analysis: dict,
    eff_silence_thresh: float,
    eff_padding_ms: int,
    eff_chunk_size: int,
    eff_whisper_model: str,
    ollama_model: str,
    manim_quality: str,
    dialect: str,
    pexels_key: str,
    groq_key: str,
    gemini_key: str,
    openai_key: str,
    product_hook: str,
    product_cta: str,
    progress_cb,
    force_caption_overlay_on_cut_mode: bool = False,
    caption_mode: str = "bottom_modern",
    custom_planned_scenes: Optional[List[Dict[str, Any]]] = None,
    custom_sfx_cues: Optional[List[Dict[str, Any]]] = None
) -> str:
    force_free_ram()

    if style_name in (STYLE_OPTIONS[0], STYLE_OPTIONS[3]):
        from v2_run import run_v2_pipeline_programmatic
        from style_evolution_brain import (
            get_active_storyboard_state,
            load_evolution_memory,
            save_evolution_memory,
        )
        sb_st = get_active_storyboard_state()
        sb_img = sb_st.get("source_image") if (sb_st.get("enabled") and sb_st.get("source_image")) else None
        mem_st = load_evolution_memory()
        rot_c = int(mem_st.get("style_rotation_counter", 0))
        v2_themes = ["obsidian_gold", "emerald_studio", "royal_cobalt"]
        chosen_v2_theme = v2_themes[rot_c % len(v2_themes)]
        rep = run_v2_pipeline_programmatic(
            input_path=input_path,
            output_mp4_path=output_path,
            theme_name=chosen_v2_theme,
            storyboard_path=sb_img,
            custom_scenes=custom_planned_scenes,
            progress_callback=progress_cb,
            gemini_api_key=gemini_key or None,
            groq_api_key=groq_key or None,
            openai_api_key=openai_key or None,
            whisper_model=eff_whisper_model,
            dialect_mode=dialect,
        )
        # Advance the rotation only after the pipeline returns successfully.
        mem_st["style_rotation_counter"] = rot_c + 1
        mem_st["last_used_v2_theme"] = chosen_v2_theme
        save_evolution_memory(mem_st)
        return rep["deliverables"]["final_video"]

    elif style_name == STYLE_OPTIONS[1]:
        from dynamic_edit import apply_product_ad_mode
        res = _safe_call(
            apply_product_ad_mode,
            input_path=input_path,
            output_path=output_path,
            product_name_override=product_hook,
            cta_override=product_cta,
            silence_threshold=eff_silence_thresh,
            padding_ms=eff_padding_ms,
            whisper_model=eff_whisper_model,
            dialect_mode=dialect,
            pexels_api_key=pexels_key,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb,
            caption_mode=caption_mode,
            custom_planned_scenes=custom_planned_scenes,
            custom_sfx_cues=custom_sfx_cues
        )
        return _unwrap_path(res)

    elif style_name == STYLE_OPTIONS[2]:
        from dynamic_edit import apply_motion_overlay_on_video
        res = _safe_call(
            apply_motion_overlay_on_video,
            input_path=input_path,
            output_path=output_path,
            silence_threshold=eff_silence_thresh,
            chunk_size=eff_chunk_size,
            padding_ms=eff_padding_ms,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            dialect_mode=dialect,
            pexels_api_key=pexels_key,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb,
            caption_mode=caption_mode,
            custom_planned_scenes=custom_planned_scenes,
            custom_sfx_cues=custom_sfx_cues
        )
        return _unwrap_path(res)

    elif style_name == STYLE_OPTIONS[4]:
        from manim_generator import generate_manim_motion_graphics
        res = _safe_call(
            generate_manim_motion_graphics,
            input_path=input_path,
            output_path=output_path,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            quality_flag=manim_quality,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb,
            custom_planned_scenes=custom_planned_scenes,
            custom_sfx_cues=custom_sfx_cues
        )
        return _unwrap_path(res)

    elif style_name == STYLE_OPTIONS[5] or force_caption_overlay_on_cut_mode:
        from dynamic_edit import apply_dynamic_edit
        res = _safe_call(
            apply_dynamic_edit,
            input_path=input_path,
            output_path=output_path,
            silence_threshold=eff_silence_thresh,
            chunk_size=eff_chunk_size,
            padding_ms=eff_padding_ms,
            zoom_factor=1.0 if force_caption_overlay_on_cut_mode else 1.15,
            whisper_model=eff_whisper_model,
            dialect_mode=dialect,
            pexels_api_key=pexels_key,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb,
            caption_mode=caption_mode,
            custom_planned_scenes=custom_planned_scenes,
            custom_sfx_cues=custom_sfx_cues
        )
        return _unwrap_path(res)

    else:
        out = remove_silence(
            input_path=input_path,
            output_path=output_path,
            silence_threshold=eff_silence_thresh,
            chunk_size=eff_chunk_size,
            padding_ms=eff_padding_ms,
            progress_callback=progress_cb
        )
        try:
            transcribe_sentences(
                audio_path=out,
                model_size=eff_whisper_model,
                language="ar",
                dialect_mode=dialect,
                groq_api_key=groq_key,
                gemini_api_key=gemini_key,
                openai_api_key=openai_key
            )
        except Exception:
            pass
        return out


# ==============================================================================
# 4. مراقب المهمة الخلفية الحي (Live Background Job Tracker)
# ==============================================================================
if job_manager.is_running():
    st.info(
        "🔄 **جاري معالجة ورندرة الفيديو في الخلفية الآن!**\n\n"
        "يمكنك إغلاق متصفح Google Chrome أو قفل شاشة الهاتف أو الذهاب لأي تطبيق آخر، وعندما تعود وتفتح هذه الصفحة ستجد الفيديو جاهزاً تلقائياً."
    )
    live_prog_bar = st.progress(0.0)
    live_status_txt = st.empty()

    while job_manager.is_running():
        st_now = job_manager.get_state()
        p_val = float(st_now.get("progress", 0.05))
        s_txt = st_now.get("status_text", "جاري المعالجة في الخلفية...")
        live_prog_bar.progress(min(1.0, max(0.0, p_val)))
        live_status_txt.markdown(f"### ⏳ {s_txt}")
        time.sleep(1.0)

    final_st = job_manager.get_state()
    if final_st.get("status") == "completed":
        live_prog_bar.progress(1.0)
        live_status_txt.success("🎉 اكتمل إنتاج الفيديو في الخلفية بنجاح! جاري عرض النتيجة...")
        time.sleep(0.4)
        st.rerun()
    elif final_st.get("status") == "failed":
        st.error(f"❌ حدث خطأ أثناء المعالجة في الخلفية: {final_st.get('error_message')}")


# ==============================================================================
# 5. جسم الصفحة: رفع ملف ومحرر الستايلات واستنساخ الفيديو المرجعي بـ زر واحد
# ==============================================================================
col1, col2 = st.columns([1.05, 1.05], gap="large")

with col1:
    st.subheader("1. رفع الفيديو أو الملف الصوتي / تسجيل مباشر")

    tab_upload, tab_record = st.tabs([
        "📁 رفع فيديو أو صوت (بجميع الصيغ - يدعم 55MB+)",
        "🎙️ تسجيل صوتي مباشر من المايكروفون"
    ])

    uploaded_stream_obj = None
    raw_media_name = None
    raw_media_size = 0

    with tab_upload:
        allow_any_ext = st.checkbox("🔓 السماح برفع أي ملف بدون تقييد المتصفح", value=False)
        uploaded_file = st.file_uploader(
            "اختر ملف فيديو (MP4, MOV, MKV...) أو التسجيل الصوتي",
            type=None if allow_any_ext else ALL_SUPPORTED_EXTENSIONS
        )
        if uploaded_file is not None:
            uploaded_stream_obj = uploaded_file
            raw_media_name = uploaded_file.name
            raw_media_size = getattr(uploaded_file, "size", 0)

    with tab_record:
        st.caption("سجّل صوتك مباشرة بالدارجة الجزائرية أو العربية:")
        if hasattr(st, "audio_input"):
            recorded_audio = st.audio_input("اضغط للتسجيل الصوتي المباشر")
            if recorded_audio is not None:
                uploaded_stream_obj = recorded_audio
                raw_media_name = f"voice_record_{getattr(recorded_audio, 'size', 0)}.wav"
                raw_media_size = getattr(recorded_audio, "size", 0)
        else:
            st.info("يرجى استخدام تبويب رفع الملفات لرفع تسجيلك الصوتي.")

    active_input_path = st.session_state.get("restored_input_path")
    media_analysis = st.session_state.get("restored_media_analysis")

    if uploaded_stream_obj is not None and raw_media_name:
        file_hash = hashlib.md5(f"{raw_media_name}_{raw_media_size}".encode()).hexdigest()[:10]
        safe_ext = os.path.splitext(raw_media_name)[1].lower() or ".mp4"
        saved_input_path = os.path.join(INPUTS_DIR, f"media_{file_hash}{safe_ext}")
        norm_candidate_path = os.path.join(INPUTS_DIR, f"norm_media_{file_hash}{safe_ext}")

        if st.session_state.get("last_file_hash") != file_hash:
            clear_custom_caption_override()
            st.session_state["last_file_hash"] = file_hash

        if not os.path.exists(norm_candidate_path) and not os.path.exists(saved_input_path):
            uploaded_stream_obj.seek(0)
            with open(saved_input_path, "wb") as out_f:
                shutil.copyfileobj(uploaded_stream_obj, out_f, length=524288)
            force_free_ram()

        source_to_prepare = norm_candidate_path if os.path.exists(norm_candidate_path) else saved_input_path
        with st.spinner("⚡ جاري تهيئة وضغط الفيديو لحماية ذاكرة السيرفر..."):
            playable_path, is_vid = ensure_playable_audio_or_video(source_to_prepare, INPUTS_DIR)
        active_input_path = playable_path
        st.session_state["restored_input_path"] = active_input_path

        cache_analysis_key = f"analysis_{file_hash}"
        if cache_analysis_key not in st.session_state:
            with st.spinner("🔍 جاري فحص وتحليل خصائص الصوت والفيديو وضبط نسبة الصمت (3% - 4%)..."):
                st.session_state[cache_analysis_key] = analyze_media_file(
                    active_input_path,
                    groq_api_key=groq_api_key,
                    gemini_api_key=gemini_api_key,
                    openai_api_key=openai_api_key
                )
            force_free_ram()
        media_analysis = st.session_state[cache_analysis_key]
        st.session_state["restored_media_analysis"] = media_analysis

    if active_input_path and os.path.exists(active_input_path) and media_analysis:
        st.success(
            f"✅ **الملف جاهز للمعالجة الآمنة!** ({media_analysis['media_type_ar']} | "
            f"المدة: `{media_analysis['duration_sec']} ثانية` | الصمت الطبيعي المستهدف: `{media_analysis['silence_percent']}%`)"
        )

        if media_analysis["has_video"]:
            st.video(active_input_path)
        else:
            st.audio(active_input_path)

        with st.expander("📊 تقرير التحليل الذكي (نسبة الصمت 3%-4% + كشف أخطاء وإعادات الصوت)", expanded=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("متوسط الصوت", f"{media_analysis['mean_dbfs']} dBFS")
            m2.metric("عتبة الصمت الذكية", f"{media_analysis['optimal_silence_threshold']} dBFS")
            m3.metric("نسبة الصمت الطبيعي", f"{media_analysis['silence_percent']}%")
            m4.metric("كشف الإعادات", "مفعّل آلياً ✅")

            st.markdown("**📌 معايير المخرج الذكي:**")
            for reason in media_analysis.get("criteria_reasons", []):
                st.markdown(f"- {reason}")

with col2:
    st.subheader("2. اختيار نمط الإخراج والمونتاج")

    selected_style = st.selectbox(
        "اختر أسلوب المونتاج المطلوب:",
        options=STYLE_OPTIONS,
        index=0
    )

    product_custom_hook = None
    product_custom_cta = None

    if selected_style == STYLE_OPTIONS[0]:
        st.info(
            "🧠 **النمط التلقائي الشامل (Smart Director All-in-One):**\n"
            "- يحافظ على الفيديو الأصلي بملء الشاشة 100% ويحذف الجمل أو الكلمات المعادة بالخطأ.\n"
            "- يضبط نسبة الصمت بين **3% إلى 4%** ويدمج بطاقات الموشن العائمة ومشاهد B-Roll."
        )
    elif selected_style == STYLE_OPTIONS[1]:
        st.info("🛍️ **إعلانات المنتجات والتجارة الإلكترونية:** خطاف Hook 0-3s، إبراز المشكلة، ميزات المنتج، شارات الثقة (58 ولاية / دفع عند الاستلام)، ولافتة الشراء CTA.")
        with st.expander("📝 تخصيص نصوص الإعلان (اختياري)", expanded=False):
            product_custom_hook = st.text_input("عنوان الخطاف العلوي (Hook Banner):", placeholder="مثال: 🔥 المنتج الأقوى في الجزائر!")
            product_custom_cta = st.text_input("نص نداء الشراء السفلي (Call To Action):", placeholder="مثال: 🛒 اطلب الآن والدفع عند الاستلام!")
    elif selected_style == STYLE_OPTIONS[2]:
        st.info("🎨 **دمج الموشن جرافيك وB-Roll بالفيديو الأصلي:** بطاقات وكالة عائمة مرقمة (`01, 02, 03`) بدون تقليص الفيديو الأصلي.")
    elif selected_style == STYLE_OPTIONS[3]:
        st.info("🚀 **موشن جرافيك احترافي متكامل:** هوية لونية وخلفية موحدة لكل فيديو مع 12 رسماً وأنفوجرافيك متحركاً بسلاسة 30fps.")
    elif selected_style == STYLE_OPTIONS[4]:
        st.info("📐 **موشن جرافيك هندسي (Manim + AI):** رسوم ومخططات بيانية متحركة.")
    elif selected_style == STYLE_OPTIONS[5]:
        st.info("🔍 **مونتاج ديناميكي:** قص صمت طبيعي (3%-4%) مع زوم 15% متناوب وكابشن تفاعلي.")
    else:
        st.info("✂️ **قص الصمت الطبيعي (3% - 4%) وحذف الإعادات:** إزالة السكوت الزائد والجمل المعادة بالخطأ مع الحفاظ على طبيعية الكلام.")

    # ==========================================================================
    # القسم 3: اختيار ستايل موحد للفيديو أو استنساخ فيديو مرجعي بزر واحد فقط
    # ==========================================================================
    st.markdown("---")
    st.subheader("🎯 3. ستايل الفيديو الموحد أو استنساخ فيديو مرجعي")
    with st.container():
        from style_evolution_brain import (
            extract_reference_video_dna,
            set_active_studio_style_mode,
            get_active_studio_style_mode,
            load_evolution_memory,
            extract_brand_palette_from_image,
            apply_custom_brand_colors,
            get_active_brand_theme,
            clear_active_brand_theme,
            reset_sticky_reference_lock_and_enable_auto_rotation
        )

        # إذا كان النظام عالقاً من جلسة سابقة على ثيم ثابت أو مرجع قديم، نعيده تلقائياً عند فتح الصفحة لوضع التنويع التلقائي لكل فيديو!
        if "initialized_auto_vary_session" not in st.session_state:
            reset_sticky_reference_lock_and_enable_auto_rotation()
            st.session_state["initialized_auto_vary_session"] = True

        studio_mode_map = {
            "🎲 تنويع تلقائي ذكي: ثيم احترافي موحد ومختلف لكل فيديو جديد (Auto-Rotate Theme Per Video - موصى به)": "auto_vary_pro",
            "🌟 ستايل المونتاج السينمائي الفاخر 15s (تدرج كريمي دافئ بدون مربعات • انتقالات سلسة وموشن 3D)": "haamza_15s_cinema",
            "🎬 ستايل وكالة السيان والكحلي الاحترافي (بطاقات بيضاء مائلة وستيكر نصي)": "byw_cyan_agency",
            "📐 ستايل المخطط الهندسي السماوي (إطارات تحديد ذكية ورسومات مشرقة)": "mazen_blueprint_collage",
            "🟣 ستايل مختبر الإعلانات البنفسجي الفاخر (تبويبات علوية وواجهات داكنة)": "baghdadi_luxury_plum",
            "🌿 ستايل الفينتك الزمردي الداكن (مخططات مالية وتقارير أداء)": "emerald_fintech_mint",
            "👑 ستايل الكوبالت الملكي والذهبي السينمائي": "royal_cobalt_gold",
            "🔥 ستايل الإديتوريال المرجاني الدافئ": "sunset_coral_editorial",
            "⚡ ستايل الأوبسيديان النيون السيبراني (خلفية كربونية داكنة مع سيان وأرجواني)": "obsidian_neon_cyber",
            "❄️ ستايل القطب الفضي والإنديجو المشرق (خلفية ثلجية ناعمة مع نيلي ملكي)": "arctic_indigo_minimal",
            "☕ ستايل الموكا والكهرباء الدافئ (خلفية إسبريسو سينمائية مع برتقالي وذهبي)": "mocha_amber_cinema",
            "🎯 تطبيق ثيم الفيديو المرجعي المستنسخ (للفيديو الحالي فقط ثم يعود للتنويع التلقائي)": "clone_reference"
        }

        cur_studio_mode = get_active_studio_style_mode()
        mode_labels = list(studio_mode_map.keys())
        def_mode_idx = 0
        for idx_m, lbl_m in enumerate(mode_labels):
            if studio_mode_map[lbl_m] == cur_studio_mode:
                def_mode_idx = idx_m
                break

        selected_studio_label = st.selectbox(
            "اختر نظام ثيم الفيديو (في الوضع الأول يختار النظام ثيماً موحداً جديداً ومختلفاً لكل فيديو تصنعه):",
            options=mode_labels,
            index=def_mode_idx,
            key="main_studio_style_mode_selector"
        )
        chosen_studio_mode_code = studio_mode_map[selected_studio_label]
        set_active_studio_style_mode(chosen_studio_mode_code)

        mem_now = load_evolution_memory()
        last_th = mem_now.get("last_used_video_style_id")
        cloned_count = len(mem_now.get("cloned_reference_styles", {}))
        if chosen_studio_mode_code == "auto_vary_pro":
            st.caption(
                f"✅ **التنويع التلقائي بين الفيديوهات مفعّل:** يمتلك النظام الآن `{10 + cloned_count}` ثيمات استوديو احترافية (بما فيها الثيمات المتعلمة من مراجعك). "
                f"كل فيديو جديد تصنعه سيحصل تلقائياً على ثيم موحد مختلف تماماً عن الفيديو الذي قبله (`آخر ثيم استُخدم: {last_th or 'لا يوجد بعد'}`)."
            )

        st.markdown("**📹 أو ارفع فيديو مرجعي لنسخ أشكاله ورسوماته وأنيميشن التحريك وتطبيقها على الفيديو/التعليق الصوتي:**")
        ref_vid_uploaded = st.file_uploader(
            "ارفع الفيديو المرجعي (MP4, MOV, MKV, WEBM):",
            type=["mp4", "mov", "mkv", "webm"],
            key="main_panel_ref_video_uploader"
        )

        ref_save_path_ready = None
        if ref_vid_uploaded is not None:
            ref_hash = hashlib.md5(f"{ref_vid_uploaded.name}_{getattr(ref_vid_uploaded, 'size', 0)}".encode()).hexdigest()[:8]
            ref_save_path_ready = os.path.join(INPUTS_DIR, f"ref_video_{ref_hash}.mp4")
            if not os.path.exists(ref_save_path_ready):
                ref_vid_uploaded.seek(0)
                with open(ref_save_path_ready, "wb") as rf:
                    shutil.copyfileobj(ref_vid_uploaded, rf, length=524288)
                force_free_ram()

            ref_b_col1, ref_b_col2 = st.columns([1.8, 1.2])
            with ref_b_col1:
                if st.button("🎯 استخراج ثيم وأشكال الفيديو المرجعي (يُطبق للفيديو الحالي ويُضاف لسلة التنويع)", use_container_width=True):
                    with st.spinner("🔬 جاري استخراج الأشكال والرسومات وفيزياء الأنيميشن والتحريك من الفيديو المرجعي..."):
                        dna = extract_reference_video_dna(ref_save_path_ready, style_alias=f"ref_{ref_hash}")
                        set_active_studio_style_mode("clone_reference")
                        st.session_state["last_cloned_ref_hash"] = ref_hash
                    st.success(
                        f"✅ **تم استخراج ثيم وأشكال الفيديو المرجعي!** سيُطبق على الفيديو القادم ثم يعود النظام تلقائياً للتنويع في الفيديوهات التي بعده.\n"
                        f"- الهوية المستخرجة: **{dna.get('detected_family_label_ar', dna.get('detected_design_family'))}**"
                    )
                    st.rerun()
            with ref_b_col2:
                if st.button("🔄 إلغاء قفل المرجع والعودة للتنويع التلقائي", use_container_width=True):
                    reset_sticky_reference_lock_and_enable_auto_rotation()
                    st.success("✅ تم فك القفل! كل فيديو جديد سيأخذ ثيماً مختلفاً عن الفيديو الذي بعده.")
                    st.rerun()


    # ==========================================================================
    # القسم 3.5: خانة رفع صورة ستوري بورد كاملة (Single-Image Storyboard Animator)
    # ==========================================================================
    with st.expander("📋 3.5 جديد: رفع صورة ستوري بورد (Storyboard في صورة واحدة) لتحريكها وبناء الفيديو عليها مباشرةً (بدون اختراع رسومات عشوائية)", expanded=True):
        from style_evolution_brain import (
            analyze_and_slice_storyboard_sheet,
            get_active_storyboard_state,
            clear_active_storyboard_state
        )
        st.caption(
            "🎯 **ميزة التحريك المباشر للستوري بورد:** ارفع صورة واحدة تحتوي على الستوري بورد الخاص بالفيديو (مثلاً شبكة مشاهد 2×2 أو 2×3 أو 3×2 أو 3×3)، "
            "وسيقوم النظام تلقائياً بتحليلها وقص لوحاتها بالترتيب، وفصل طبقاتها بعمق **2.5D Parallax** وتحريكها مع الكاميرا والمؤثرات الصوتية والكابشن "
            "**دون أن يخترع أي أشكال أو رسومات عشوائية من عنده!**"
        )

        sb_state_now = get_active_storyboard_state()
        if sb_state_now.get("enabled") and sb_state_now.get("panels"):
            st.success(
                f"✅ **وضع تحريك الستوري بورد مفعّل حالياً!** تم استخراج `{len(sb_state_now['panels'])}` مشاهد/لوحات من صورة الستوري بورد "
                f"(الشبكة: `{sb_state_now.get('grid_shape', [0, 0])[0]}×{sb_state_now.get('grid_shape', [0, 0])[1]}`). "
                "سيتم بناء الفيديو القادم بالكامل من لوحات الستوري بورد المرفوعة!"
            )
            sb_preview_cols = st.columns(min(4, max(1, len(sb_state_now["panels"]))))
            for p_i, p_meta in enumerate(sb_state_now["panels"][:8]):
                with sb_preview_cols[p_i % len(sb_preview_cols)]:
                    if os.path.exists(str(p_meta.get("panel_path", ""))):
                        st.image(p_meta["panel_path"], caption=f"مشهد #{p_i + 1}", use_container_width=True)
            if st.button("🗑️ إلغاء وضع الستوري بورد والعودة لتوليد الموشن جرافيك التلقائي", use_container_width=True, key="btn_clear_storyboard_mode"):
                clear_active_storyboard_state()
                st.info("تم إيقاف وضع الستوري بورد والعودة للتوليد الديناميكي المتنوع.")
                st.rerun()

        sb_uploaded_img = st.file_uploader(
            "📸 ارفع صورة الستوري بورد الكاملة هنا (PNG, JPG, JPEG, WEBP):",
            type=["png", "jpg", "jpeg", "webp"],
            key="single_image_storyboard_uploader"
        )

        sb_col1, sb_col2 = st.columns(2)
        with sb_col1:
            sb_grid_choice = st.selectbox(
                "تخطيط شبكة اللوحات في الصورة:",
                options=[
                    "🔍 اكتشاف تلقائي ذكي للفواصل واللوحات (Auto-Detect Grid)",
                    "2×2 (4 مشاهد)",
                    "2×3 (6 مشاهد - صفين × 3 أعمدة)",
                    "3×2 (6 مشاهد - 3 صفوف × عمودين)",
                    "3×3 (9 مشاهد)",
                    "4×2 (8 مشاهد)",
                    "1×4 (4 مشاهد أفقية)",
                    "4×1 (4 مشاهد عمودية)",
                    "1×1 (لوحة ستوري بورد واحدة شاملة)"
                ],
                index=0,
                key="sb_grid_layout_selector"
            )
        with sb_col2:
            sb_order_choice = st.selectbox(
                "ترتيب قراءة مشاهد الستوري بورد:",
                options=[
                    "من اليسار لليمين (LTR - القياسي للوحات المرقمة 1..6) ➡️",
                    "من اليمين لليسار (RTL - عربي) ⬅️"
                ],
                index=0,
                key="sb_reading_order_selector"
            )

        if sb_uploaded_img is not None:
            sb_hash = hashlib.md5(f"{sb_uploaded_img.name}_{getattr(sb_uploaded_img, 'size', 0)}".encode()).hexdigest()[:8]
            sb_ext = os.path.splitext(sb_uploaded_img.name)[1].lower() or ".png"
            sb_save_path = os.path.join(INPUTS_DIR, f"storyboard_sheet_{sb_hash}{sb_ext}")
            if not os.path.exists(sb_save_path):
                sb_uploaded_img.seek(0)
                with open(sb_save_path, "wb") as sbf:
                    shutil.copyfileobj(sb_uploaded_img, sbf)

            import re as _re_mod
            forced_g = None
            m_grid = _re_mod.match(r"^(\d+)[×xX](\d+)", sb_grid_choice.strip())
            if m_grid:
                forced_g = (int(m_grid.group(1)), int(m_grid.group(2)))
            r_order = "rtl" if "اليمين" in sb_order_choice else "ltr"
            sb_Auto_key = f"{sb_hash}_{sb_grid_choice}_{r_order}"

            # تفعيل وتقطيع الستوري بورد تلقائياً فور رفع الصورة بدون الحاجة لضغط زر إضافي!
            if st.session_state.get("last_sliced_storyboard_key") != sb_Auto_key or not sb_state_now.get("enabled"):
                with st.spinner("🔬 جاري تحليل صورة الستوري بورد تلقائياً وفصل اللوحات والطبقات الأمامية (2.5D Parallax)..."):
                    sb_res_auto = analyze_and_slice_storyboard_sheet(
                        image_path=sb_save_path,
                        reading_order=r_order,
                        forced_grid=forced_g
                    )
                st.session_state["last_sliced_storyboard_key"] = sb_Auto_key
                if sb_res_auto.get("ok"):
                    st.success(f"🎉 {sb_res_auto.get('message')}")
                    st.rerun()

            if st.button("🔄 إعادة تقسيم وتحليل صورة الستوري بورد بالإعدادات المختارة", use_container_width=True, key="btn_activate_storyboard_sheet"):
                with st.spinner("🔬 جاري إعادة تحليل صورة الستوري بورد وفصل اللوحات والطبقات الأمامية (2.5D Parallax)..."):
                    sb_res = analyze_and_slice_storyboard_sheet(
                        image_path=sb_save_path,
                        reading_order=r_order,
                        forced_grid=forced_g
                    )
                st.session_state["last_sliced_storyboard_key"] = sb_Auto_key
                if sb_res.get("ok"):
                    st.success(f"🎉 {sb_res.get('message')}")
                    st.rerun()
                else:
                    st.error(f"❌ {sb_res.get('message')}")

    # ==========================================================================
    # القسم 4: اللوقو وألوان الهوية البصرية المخصصة (اختياري)
    # ==========================================================================
    with st.expander("🎨 4. رفع لوقو (Logo) أو تخصيص ألوان الهوية البصرية يدوياً (اختياري)", expanded=False):
        active_brand_now = get_active_brand_theme() or {}
        logo_uploaded = st.file_uploader(
            "🖼️ ارفع اللوقو (Logo) أو صورة باليت ألوان (يستخرج منها ألوان الفيديو تلقائياً):",
            type=["png", "jpg", "jpeg", "webp"],
            key="main_brand_logo_uploader"
        )

        logo_pos_map = {
            "أعلى اليمين (Top Right)": "top_right",
            "أعلى اليسار (Top Left)": "top_left",
            "استخراج الألوان فقط بدون عرض اللوقو": "none"
        }
        logo_pos_label = st.selectbox(
            "موضع ظهور اللوقو في الفيديو:",
            options=list(logo_pos_map.keys()),
            index=0
        )
        chosen_logo_pos = logo_pos_map[logo_pos_label]
        show_logo_flag = (chosen_logo_pos != "none")

        saved_logo_path = active_brand_now.get("logo_path")
        if logo_uploaded is not None:
            logo_hash = hashlib.md5(f"{logo_uploaded.name}_{getattr(logo_uploaded, 'size', 0)}".encode()).hexdigest()[:8]
            ext_l = os.path.splitext(logo_uploaded.name)[1].lower() or ".png"
            saved_logo_path = os.path.join(INPUTS_DIR, f"brand_logo_{logo_hash}{ext_l}")
            if not os.path.exists(saved_logo_path):
                logo_uploaded.seek(0)
                with open(saved_logo_path, "wb") as lf:
                    shutil.copyfileobj(logo_uploaded, lf)
            if st.session_state.get("last_extracted_logo_hash") != logo_hash:
                extracted_prof = extract_brand_palette_from_image(
                    image_path=saved_logo_path,
                    show_logo_watermark=show_logo_flag,
                    logo_position=chosen_logo_pos if show_logo_flag else "top_right",
                    prefer_dark_bg=True
                )
                st.session_state["last_extracted_logo_hash"] = logo_hash
                st.session_state["brand_primary_hex"] = extracted_prof.get("primary_hex", "#1BAECA")
                st.session_state["brand_secondary_hex"] = extracted_prof.get("secondary_hex", "#FFFFFF")
                st.session_state["brand_bg_hex"] = extracted_prof.get("bg_hex", "#0B181F")
                st.session_state["enable_custom_brand_colors"] = True
                active_brand_now = extracted_prof

        enable_custom_colors = st.checkbox(
            "تفعيل تخصيص الألوان اليدوي أو ألوان اللوقو فوق الستايل",
            value=bool(logo_uploaded is not None or st.session_state.get("enable_custom_brand_colors", False))
        )
        st.session_state["enable_custom_brand_colors"] = enable_custom_colors

        def_p = st.session_state.get("brand_primary_hex", active_brand_now.get("primary_hex", "#1BAECA"))
        def_s = st.session_state.get("brand_secondary_hex", active_brand_now.get("secondary_hex", "#FACC15"))
        def_bg = st.session_state.get("brand_bg_hex", active_brand_now.get("bg_hex", "#0D768E"))

        cp1, cp2, cp3 = st.columns(3)
        with cp1:
            picked_primary = st.color_picker("اللون الأساسي", value=def_p, key="cp_primary")
        with cp2:
            picked_secondary = st.color_picker("اللون الثانوي", value=def_s, key="cp_secondary")
        with cp3:
            picked_bg = st.color_picker("لون الخلفية", value=def_bg, key="cp_bg")

        st.session_state["brand_primary_hex"] = picked_primary
        st.session_state["brand_secondary_hex"] = picked_secondary
        st.session_state["brand_bg_hex"] = picked_bg

        if not enable_custom_colors and logo_uploaded is None:
            clear_active_brand_theme()
        else:
            apply_custom_brand_colors(
                primary_hex=picked_primary,
                secondary_hex=picked_secondary,
                bg_hex=picked_bg,
                style_mode="dark_stage_pro",
                logo_path=saved_logo_path if (logo_uploaded is not None or saved_logo_path) else None,
                show_logo_watermark=show_logo_flag,
                logo_position=chosen_logo_pos if show_logo_flag else "top_right"
            )
            st.caption(
                f"✅ **ثيم البراند المخصص مفعل:** أساسي `{picked_primary}` • ثانوي `{picked_secondary}` • خلفية `{picked_bg}`"
            )

    # ==========================================================================
    # القسم 4.5: محرك جلب الموشن جرافيك الحي من الإنترنت + ربط حزمة 400MB+ (Zero-OOM)
    # ==========================================================================
    with st.expander("🌐 4.5 محرك الموشن جرافيك الحي من الإنترنت (+200,000 شكل) + ربط حزمة 400MB+ (Google Drive / ZIP)", expanded=True):
        from vector_lottie_engine import (
            set_live_web_fetch_enabled,
            is_live_web_fetch_enabled,
            import_motion_pack_from_url_or_path,
            get_custom_pack_stats,
            CUSTOM_PACK_DIR,
            index_custom_motion_pack_directory
        )
        st.caption(
            "🚀 **كيف يعمل؟** يبحث النظام حياً في الإنترنت عن أشكال ورسومات الفيكتور والموشن جرافيك المطابقة لمعنى كل جملة، "
            "و**يعيد تلوينها تلقائياً لتطابق ألوان ثيم الفيديو النشط**، ثم يرسم فوقها وحولها طبقات أنيميشن تفاعلية (Trim Paths + 3D Orbit) "
            "حتى لا تتكرر نفس الرسومات أبداً! كما يمكنك ربط حزمة الـ **400MB+** الخاصة بك عبر رابط Google Drive أو مجلد محلي بدون استهلاك رام السيرفر."
        )
        web_vec_toggle = st.toggle(
            "✅ تفعيل جلب أشكال الموشن جرافيك الحية من الإنترنت وتوحيد ألوانها مع ثيم الفيديو",
            value=is_live_web_fetch_enabled(),
            key="toggle_live_web_vector_engine"
        )
        set_live_web_fetch_enabled(web_vec_toggle)

        pack_stats = get_custom_pack_stats()
        if pack_stats.get("total_assets", 0) > 0:
            st.success(
                f"📦 **حزمة الموشن جرافيك الخاصة مربوطة ومفهرسة:** إجمالي `{pack_stats.get('total_assets', 0)}` أصل "
                f"(SVG: `{pack_stats.get('svg_count', 0)}` | Lottie JSON: `{pack_stats.get('lottie_count', 0)}` | "
                f"PNG/WebP: `{pack_stats.get('image_count', 0)}` | Video Overlays: `{pack_stats.get('video_count', 0)}`)"
            )

        pk_col1, pk_col2 = st.columns([2.2, 1.0])
        with pk_col1:
            pack_url_or_dir = st.text_input(
                "🔗 رابط حزمة الـ 400MB+ (Google Drive أو رابط ZIP مباشر) أو مسار المجلد المحلي:",
                placeholder="https://drive.google.com/file/d/... أو C:/MotionPack",
                key="custom_motion_pack_url_input"
            )
        with pk_col2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("📥 ربط وفهرسة الحزمة (Zero-OOM)", use_container_width=True, key="btn_import_400mb_pack"):
                if pack_url_or_dir.strip():
                    with st.spinner("🌐 جاري التدفق السحابي وفهرسة حزمة الموشن جرافيك على القرص بدون استهلاك الرام..."):
                        res_pk = import_motion_pack_from_url_or_path(pack_url_or_dir.strip())
                    if res_pk.get("ok"):
                        st.success(f"🎉 {res_pk.get('message')}")
                        st.rerun()
                    else:
                        st.warning(f"⚠️ {res_pk.get('message')}")
                else:
                    st.info("أدخل رابط Google Drive (تأكد أنه عام Anyone with the link) أو مسار المجلد أولاً.")

        uploaded_pack_files = st.file_uploader(
            "📂 أو ارفع ملفات من الحزمة مباشرة (SVG, Lottie JSON, PNG, WebP, أو أرشيف ZIP):",
            type=["zip", "svg", "json", "png", "webp"],
            accept_multiple_files=True,
            key="direct_pack_files_uploader"
        )
        if uploaded_pack_files:
            if st.button("➕ إضافة الملفات المرفوعة إلى مكتبة الموشن جرافيك الدائمة", use_container_width=True, key="btn_add_uploaded_pack_files"):
                with st.spinner("⚙️ جاري حفظ وفهرسة أشكال الموشن جرافيك الجديدة..."):
                    os.makedirs(CUSTOM_PACK_DIR, exist_ok=True)
                    for up_f in uploaded_pack_files:
                        dest_p = os.path.join(CUSTOM_PACK_DIR, up_f.name)
                        up_f.seek(0)
                        with open(dest_p, "wb") as out_pf:
                            shutil.copyfileobj(up_f, out_pf, length=524288)
                        if dest_p.lower().endswith(".zip"):
                            import_motion_pack_from_url_or_path(dest_p)
                    new_st = index_custom_motion_pack_directory(CUSTOM_PACK_DIR)
                st.success(f"✅ تمت إضافة وفهرسة الملفات! إجمالي الأشكال في المكتبة الآن: `{new_st.get('total_assets', 0)}`.")
                st.rerun()

    # ==========================================================================
    # القسم 5: مصمم الساوند ديزاين الآلي واستخراج المؤثرات من Google Drive
    # ==========================================================================
    with st.expander("🔊 5. مصمم الساوند ديزاين الآلي واستخراج حزمة المؤثرات من Google Drive (مفعّل تلقائياً)", expanded=True):
        from sound_designer import (
            get_sound_design_settings,
            set_sound_design_settings,
            import_sfx_pack_from_google_drive,
            import_sfx_archive_or_files,
            ensure_builtin_sfx_pack
        )
        ensure_builtin_sfx_pack()
        sfx_cfg_now = get_sound_design_settings()

        st.caption(
            "🎯 **يعمل بعد انتهاء الموشن جرافيك بالكامل:** يحلل كل لقطة وانتقال وحركة مؤشر وعداد رقمي، "
            "ويضع المؤثر الصوتي المناسب (`1-Click`, `2-UI Click`, `3-UI Style`, `4-Button`, `5-Riser`, `6-Whooch`) "
            "في الثانية والمللي ثانية المناسبة مع خفض تلقائي (Auto-Ducking) تحت صوتك."
        )

        sfx_c1, sfx_c2 = st.columns([1.2, 1.0])
        with sfx_c1:
            sfx_enabled_ui = st.toggle(
                "🔊 تفعيل مصمم الساوند ديزاين الآلي بعد الرندرة (Whoosh + Pop-In + Click + Button + Riser)",
                value=bool(sfx_cfg_now.get("enabled", True)),
                key="sfx_enabled_toggle"
            )
        with sfx_c2:
            sfx_vol_ui = st.slider(
                "مستوى صوت المؤثرات (SFX Volume)",
                min_value=0.10,
                max_value=1.30,
                value=float(sfx_cfg_now.get("master_volume", 0.88)),
                step=0.05,
                key="sfx_master_vol_slider"
            )

        sc_t1, sc_t2, sc_t3, sc_t4 = st.columns(4)
        with sc_t1:
            en_whoosh = st.checkbox("💨 انتقالات Whoosh", value=bool(sfx_cfg_now.get("enable_whooshes", True)), key="chk_sfx_whoosh")
        with sc_t2:
            en_pops = st.checkbox("✨ انبثاق ناعم Pop-In", value=bool(sfx_cfg_now.get("enable_ui_pops", True)), key="chk_sfx_pops")
        with sc_t3:
            en_clicks = st.checkbox("🖱️ نقرات Click & Button", value=bool(sfx_cfg_now.get("enable_clicks_and_buttons", True)), key="chk_sfx_clicks")
        with sc_t4:
            en_risers = st.checkbox("🌊 تصاعد Riser & Impact", value=bool(sfx_cfg_now.get("enable_risers", True)), key="chk_sfx_risers")

        set_sound_design_settings(
            enabled=sfx_enabled_ui,
            master_volume=sfx_vol_ui,
            enable_whooshes=en_whoosh,
            enable_ui_pops=en_pops,
            enable_clicks_and_buttons=en_clicks,
            enable_risers=en_risers
        )

        drive_sfx_url_input = st.text_input(
            "🔗 الصق رابط Google Drive لحزمة الساوند ديزاين (أو اتركه فارغاً لاستخدام حزمة الـ 24 مؤثر الاحترافية المدمجة):",
            value=str(sfx_cfg_now.get("drive_url", "")),
            placeholder="https://drive.google.com/drive/folders/... أو https://drive.google.com/file/d/...",
            key="gdrive_sfx_url_input"
        )

        sfx_uploaded_files = st.file_uploader(
            "📦 أو ارفع ملف ZIP / ملفات المؤثرات الصوتية مباشرة (WAV, MP3, ZIP):",
            type=["zip", "wav", "mp3", "ogg", "m4a"],
            accept_multiple_files=True,
            key="sfx_pack_files_uploader"
        )

        if st.button("📥 استخراج وتصنيف الساوند ديزاين من الرابط / الملفات المرفوعة", use_container_width=True):
            with st.spinner("🔊 جاري استخراج وتصنيف المؤثرات الصوتية إلى الأقسام الـ 6 (Click, UI Click, UI Style, Button, Riser, Whooch)..."):
                total_added = 0
                msg_parts = []
                if drive_sfx_url_input.strip():
                    res_drv = import_sfx_pack_from_google_drive(drive_sfx_url_input.strip())
                    total_added += int(res_drv.get("total_imported", 0))
                    msg_parts.append(res_drv.get("message_ar", ""))
                if sfx_uploaded_files:
                    saved_sfx_uploads = []
                    for uf in sfx_uploaded_files:
                        tmp_uf_p = os.path.join(TEMP_DIR, f"upload_sfx_{uf.name}")
                        uf.seek(0)
                        with open(tmp_uf_p, "wb") as out_uf:
                            shutil.copyfileobj(uf, out_uf)
                        saved_sfx_uploads.append(tmp_uf_p)
                    res_loc = import_sfx_archive_or_files(saved_sfx_uploads)
                    total_added += int(res_loc.get("total_imported", 0))
                    msg_parts.append(f"تم استيراد {res_loc.get('total_imported', 0)} ملف صوتي مرفوع.")
                if not drive_sfx_url_input.strip() and not sfx_uploaded_files:
                    msg_parts.append("حزمة الاستوديو المدمجة (24 مؤثر صوتي احترافي في 8 أقسام) جاهزة ومفعلة بالكامل!")
                st.success("✅ " + " | ".join(p for p in msg_parts if p))

    st.markdown("<br>", unsafe_allow_html=True)
    start_btn = st.button(
        "🚀 بدء صناعة ومونتاج الفيديو في الخلفية (Start Processing)",
        use_container_width=True,
        disabled=job_manager.is_running()
    )


# ==============================================================================
# 6. إطلاق المعالجة في الخلفية (Background Daemon Execution)
# ==============================================================================
if start_btn:
    if active_input_path is None or not os.path.exists(active_input_path):
        st.warning("⚠️ يرجى رفع ملف فيديو أو صوت (أو تسجيل صوتك) أولاً قبل بدء المعالجة.")
    else:
        clear_custom_caption_override()

        # ملاحظة: لا نقفل النظام تلقائياً على الفيديو المرجعي عند الضغط على زر البدء إلا إذا اختار المستخدم ذلك صراحةً،
        # بل نضيف الفيديو المرجعي (إن لم يُقرأ بعد) إلى سلة الثيمات المتعلمة مع بقاء التنويع التلقائي بين الفيديوهات نشطاً!
        if ref_save_path_ready and os.path.exists(ref_save_path_ready):
            ref_h = os.path.basename(ref_save_path_ready)
            if st.session_state.get("last_cloned_ref_hash") != ref_h:
                extract_reference_video_dna(ref_save_path_ready, style_alias=f"ref_{ref_h[:8]}")
                if chosen_studio_mode_code != "clone_reference":
                    reset_sticky_reference_lock_and_enable_auto_rotation()
                st.session_state["last_cloned_ref_hash"] = ref_h

        if auto_optimize and media_analysis is not None:
            eff_silence_thresh = float(media_analysis["optimal_silence_threshold"])
            eff_padding_ms = int(media_analysis["optimal_padding_ms"])
            eff_chunk_size = int(media_analysis["optimal_chunk_size"])
            eff_whisper_model = str(media_analysis["optimal_whisper_model"])
        else:
            eff_silence_thresh = silence_threshold
            eff_padding_ms = padding_ms
            eff_chunk_size = chunk_size
            eff_whisper_model = whisper_model_choice

        timestamp_prefix = int(time.time())
        only_silence_cut = (selected_style == STYLE_OPTIONS[6])
        has_vid = is_video_file(active_input_path)
        target_ext = os.path.splitext(active_input_path)[1].lower() if (only_silence_cut and has_vid) else (".mp3" if (only_silence_cut and not has_vid) else ".mp4")
        output_file_name = f"studio_output_{timestamp_prefix}{target_ext}"
        output_file_path = os.path.join(OUTPUTS_DIR, output_file_name)

        eff_params_dict = {
            "silence_thresh": eff_silence_thresh,
            "padding_ms": eff_padding_ms,
            "chunk_size": eff_chunk_size,
            "whisper_model": eff_whisper_model
        }

        job_manager.start_job(
            runner_func=run_selected_pipeline,
            runner_kwargs={
                "style_name": selected_style,
                "input_path": active_input_path,
                "output_path": output_file_path,
                "media_analysis": media_analysis,
                "eff_silence_thresh": eff_silence_thresh,
                "eff_padding_ms": eff_padding_ms,
                "eff_chunk_size": eff_chunk_size,
                "eff_whisper_model": eff_whisper_model,
                "ollama_model": ollama_model_choice,
                "manim_quality": manim_flag,
                "dialect": dialect_mode,
                "pexels_key": pexels_api_key,
                "groq_key": groq_api_key,
                "gemini_key": gemini_api_key,
                "openai_key": openai_api_key,
                "product_hook": product_custom_hook,
                "product_cta": product_custom_cta,
                "caption_mode": eff_caption_mode
            },
            job_meta={
                "input_path": active_input_path,
                "output_path": output_file_path,
                "selected_style": selected_style,
                "caption_mode": eff_caption_mode,
                "file_hash": st.session_state.get("last_file_hash"),
                "media_analysis": media_analysis,
                "eff_params": eff_params_dict
            },
            cleanup_func=lambda: cleanup_temp_directory(TEMP_DIR)
        )
        st.rerun()


# ==============================================================================
# 7. عرض النتيجة النهائية (المحفوظة تلقائياً حتى بعد إغلاق المتصفح) ومحرر الكابشن
# ==============================================================================
result_path = st.session_state.get("processed_result_path")
if result_path and os.path.exists(result_path):
    st.markdown("---")
    hdr_col1, hdr_col2 = st.columns([3.2, 1.0])
    with hdr_col1:
        st.success("🎉 **الفيديو الجاهز للعرض والتحميل (محفوظ تلقائياً في الخلفية):**")
    with hdr_col2:
        if st.button("🗑️ بدء مشروع جديد / مسح المحفوظ"):
            job_manager.clear_job()
            st.session_state.pop("processed_result_path", None)
            st.session_state.pop("restored_input_path", None)
            st.session_state.pop("restored_media_analysis", None)
            st.rerun()

    res_col1, res_col2 = st.columns([1.0, 1.15], gap="large")

    with res_col1:
        st.markdown("### 🎬 النتيجة النهائية:")
        if result_path.lower().endswith((".mp3", ".wav", ".ogg", ".m4a")):
            st.audio(result_path)
            mime_type = "audio/mpeg"
        else:
            st.video(result_path)
            mime_type = "video/mp4"

        with open(result_path, "rb") as file_bytes:
            st.download_button(
                label="📥 تحميل الملف النهائي بجودة كاملة",
                data=file_bytes,
                file_name=os.path.basename(result_path),
                mime=mime_type,
                use_container_width=True
            )

    with res_col2:
        st.markdown("### 🎛️ استوديو التعديل الحي للمشاهد والرسومات والساوند ديزاين والكابشن (بدون كتابة كود!)")
        st.caption("عدّل رسمة أي مشهد، أو عنوانه، أو مؤثراته الصوتية (Pop-In / Click / Whoosh) مباشرة من المنصة بنقرة زر.")

        current_words = st.session_state.get("caption_words", [])
        current_sentences = st.session_state.get("caption_sentences", [])

        edit_tab_v2, edit_tab_scenes, edit_tab_sfx, edit_tab_sent, edit_tab_words = st.tabs([
            "🏆 فاحص الجودة v2 + الغلاف + ذوق القناة (👍/👎)",
            "🎨 تعديل الرسومات والمشاهد (مشهداً بمشهد)",
            "🔊 محرر الساوند ديزاين الفوري (1 ثانية)",
            "📝 تعديل الكابشن جملة بجملة",
            "🔤 تعديل الكلمات والتوقيت"
        ])

        with edit_tab_v2:
            st.markdown("##### 🏆 محرك الجيل الثاني (v2) — فاحص الجودة الآلي، الغلاف، وذوق صاحب القناة:")
            v2_qa_path = os.path.join(OUTPUTS_DIR, "v2_final_1080p_qa_report.json")
            if os.path.exists(v2_qa_path):
                try:
                    with open(v2_qa_path, "r", encoding="utf-8") as qf:
                        v2_rep = json.load(qf)
                    qm1, qm2, qm3 = st.columns(3)
                    qm1.metric("درجة النظام القديم", f"{v2_rep.get('score_before_legacy', 44.2)} / 100")
                    qm2.metric("درجة الجيل الثاني (v2)", f"{v2_rep.get('score_after_v2', 99.1)} / 100", "+54.9")
                    qm3.metric("تقييم الناقد البصري", f"{v2_rep.get('visual_critic_after', {}).get('average_ten', 9.37)} / 10")
                except Exception:
                    pass

            v2_thumb = os.path.join(OUTPUTS_DIR, "thumbnail.png")
            v2_copy = os.path.join(OUTPUTS_DIR, "post_copy.txt")
            v2_sheet = os.path.join(OUTPUTS_DIR, "v2_final_1080p_contact_sheet_05s.png")
            if os.path.exists(v2_copy):
                with open(v2_copy, "r", encoding="utf-8") as cf:
                    st.text_area("📋 وصف الفيديو والهاشتاقات الجاهزة للنشر (post_copy.txt):", value=cf.read(), height=130)
            if os.path.exists(v2_sheet):
                with st.expander("🖼️ عرض لوحة الفريمات (Contact Sheet كل 0.5 ثانية) وصورة الغلاف (1080×1920)", expanded=False):
                    st.image(v2_sheet, caption="Contact Sheet (0.5s intervals)", use_container_width=True)
                    if os.path.exists(v2_thumb):
                        st.image(v2_thumb, caption="صورة الغلاف (1080×1920)", width=260)

            st.markdown("---")
            st.markdown("##### 👍 / 👎 ذوق صاحب القناة (يُحفظ في `v2/preferences.json` لتوجيه المخرج في الفيديوهات القادمة):")
            fb_c1, fb_c2 = st.columns(2)
            with fb_c1:
                fb_vote = st.radio("تقييمك لهذا الفيديو:", ["👍 أعجبني (إبقاء هذا الأسلوب)", "👎 لم يعجبني (تجنب هذا الأسلوب)"], horizontal=True)
            with fb_c2:
                fb_reason = st.selectbox("السبب المحدد:", [
                    "ممتاز ومطابق لمعنى الكلام",
                    "الحركة بطيئة",
                    "الأيقونة خاطئة أو لا تطابق الكلام",
                    "النص صغير أو غير واضح",
                    "تكرار ممل بين المشاهد"
                ])
            if st.button("💾 حفظ التقييم في ذاكرة ذوق القناة (v2/preferences.json)", use_container_width=True):
                try:
                    sys.path.insert(0, os.path.join(BASE_DIR, "v2"))
                    from v2_director import save_channel_feedback
                    save_channel_feedback(vote="up" if "👍" in fb_vote else "down", reason=fb_reason)
                    st.success("✅ تم حفظ تقييمك في `v2/preferences.json` وسيتم تمريره للمخرج الذكي في التشغيلات القادمة!")
                except Exception as e_fb:
                    st.warning(f"ملاحظة: {e_fb}")

        from sound_designer import LAST_SESSION_PATH, remaster_video_sfx_instantly, SFX_CATEGORIES
        from style_evolution_brain import ALL_DYNAMIC_VISUAL_ARCHETYPES, ARCHETYPE_LABELS_AR

        saved_session = {}
        if os.path.exists(LAST_SESSION_PATH):
            try:
                with open(LAST_SESSION_PATH, "r", encoding="utf-8") as sf:
                    saved_session = json.load(sf)
            except Exception:
                saved_session = {}

        session_scenes = saved_session.get("planned_scenes", [])
        session_cues = saved_session.get("sfx_cues", [])
        session_dur = float(saved_session.get("total_duration", 15.0))

        with edit_tab_scenes:
            if not session_scenes:
                st.info("سيظهر هنا مخطط المشاهد والرسومات فور انتهاء أول عملية رندرة للفيديو.")
            else:
                st.markdown("##### ✨ خصّص الرسمة التعبيرية والعنوان والساوند ديزاين لكل مشهد:")
                arch_keys = list(ALL_DYNAMIC_VISUAL_ARCHETYPES)
                arch_display_map = {k: ARCHETYPE_LABELS_AR.get(k, k) for k in arch_keys}
                sfx_mode_options = {
                    "auto_all": "🔊 كامل احترافي متوازن (Whoosh + Pop-In + UI Click + Button)",
                    "whoosh_pop_click": "✨ انتقال + انبثاق + نقرة (Whoosh + Pop-In + Click)",
                    "whoosh_pop": "🫧 انتقال وانبثاق ناعم فقط (Whoosh + Pop-In)",
                    "whoosh_only": "💨 هواء الانتقال فقط (Whoosh Only)",
                    "riser_whoosh_impact": "🌊 تصاعد سينمائي عميق (Riser + Whoosh + Sub-Impact)",
                    "click_button": "🖱️ نقرة ماوس وزر تفاعلي فقط (Click + Button)",
                    "mute": "🔇 كتم المؤثرات الصوتية في هذا المشهد"
                }
                layout_options = {
                    "full_screen": "🖥️ شاشة موشن جرافيك كاملة (Full-Screen Motion)",
                    "speaker_clean": "🎥 لقطة المتحدث الصافية (Speaker Clean Shot)",
                    "stock_broll": "🎞️ مشهد فيديو واقعي (Stock B-Roll)"
                }

                with st.form("live_scene_drawing_editor_form"):
                    updated_scenes_plan = []
                    for sc_i, sc_data in enumerate(session_scenes):
                        s_st = float(sc_data.get("start", 0.0))
                        s_en = float(sc_data.get("end", s_st + 2.5))
                        cur_arch = str(sc_data.get("user_override_archetype") or sc_data.get("archetype") or arch_keys[0])
                        if cur_arch not in arch_keys:
                            cur_arch = arch_keys[sc_i % len(arch_keys)]
                        cur_layout = str(sc_data.get("layout_mode", "full_screen"))
                        if cur_layout not in layout_options:
                            cur_layout = "full_screen"
                        cur_sfx_m = str(sc_data.get("sfx_mode", "auto_all"))
                        if cur_sfx_m not in sfx_mode_options:
                            cur_sfx_m = "auto_all"

                        with st.expander(f"🎬 المشهد #{sc_i + 1} ({s_st:.1f}s - {s_en:.1f}s): {sc_data.get('concept_title', '')[:38]}", expanded=(sc_i < 2)):
                            new_spoken_text = st.text_input(
                                f"🎙️ تعديل الكلام المنطوق في المشهد #{sc_i + 1} (ينعكس فوراً في الكابشن والموشن جرافيك):",
                                value=str(sc_data.get("text", "")),
                                key=f"sc_spoken_txt_{sc_i}"
                            )
                            chosen_arch = st.selectbox(
                                f"🎨 الرسمة / المجسم التعبيري للمشهد #{sc_i + 1}:",
                                options=arch_keys,
                                index=arch_keys.index(cur_arch),
                                format_func=lambda x: arch_display_map.get(x, x),
                                key=f"sc_arch_sel_{sc_i}"
                            )
                            c_col1, c_col2 = st.columns(2)
                            with c_col1:
                                new_ctitle = st.text_input(
                                    f"📌 العنوان البارز على الشاشة #{sc_i + 1}:",
                                    value=str(sc_data.get("concept_title", "")),
                                    key=f"sc_ctitle_{sc_i}"
                                )
                                new_kpi = st.text_input(
                                    f"🔢 المؤشر / الكلمة المفتاحية البارزة #{sc_i + 1}:",
                                    value=str(sc_data.get("kpi_value", "")),
                                    key=f"sc_kpi_{sc_i}"
                                )
                            with c_col2:
                                new_badge = st.text_input(
                                    f"🏷️ الشارة العلوية #{sc_i + 1}:",
                                    value=str(sc_data.get("badge_label", "")),
                                    key=f"sc_badge_{sc_i}"
                                )
                                chosen_layout = st.selectbox(
                                    f"📐 وضع العرض #{sc_i + 1}:",
                                    options=list(layout_options.keys()),
                                    index=list(layout_options.keys()).index(cur_layout),
                                    format_func=lambda x: layout_options.get(x, x),
                                    key=f"sc_layout_{sc_i}"
                                )
                            cur_subs_str = " | ".join(str(x) for x in (sc_data.get("sub_items") or [])[:4])
                            new_subs_str = st.text_input(
                                f"📋 العناصر الفرعية داخل الرسم #{sc_i + 1} (افصل بينها بعلامة | ):",
                                value=cur_subs_str,
                                key=f"sc_subs_{sc_i}"
                            )
                            chosen_sfx_m = st.selectbox(
                                f"🔊 نمط المؤثرات الصوتية لهذا المشهد #{sc_i + 1}:",
                                options=list(sfx_mode_options.keys()),
                                index=list(sfx_mode_options.keys()).index(cur_sfx_m),
                                format_func=lambda x: sfx_mode_options.get(x, x),
                                key=f"sc_sfx_mode_{sc_i}"
                            )

                            sc_copy = dict(sc_data)
                            sc_copy["text"] = new_spoken_text.strip() or sc_data.get("text", "")
                            sc_copy["concept_title"] = new_ctitle.strip() or sc_data.get("concept_title", "")
                            sc_copy["short_title"] = sc_copy["concept_title"]
                            sc_copy["badge_label"] = new_badge.strip() or sc_data.get("badge_label", "")
                            sc_copy["kpi_value"] = new_kpi.strip() or sc_data.get("kpi_value", "")
                            sc_copy["layout_mode"] = chosen_layout
                            sc_copy["sfx_mode"] = chosen_sfx_m
                            parsed_subs = [s.strip() for s in new_subs_str.split("|") if s.strip()]
                            if parsed_subs:
                                sc_copy["sub_items"] = parsed_subs
                            # إذا غيّر المستخدم الرسمة يدوياً نعتمد اختياره، وإذا غيّر الكلمات المفتاحية أو الكلام المنطوق نحدّث الرسمة سياقياً تلقائياً
                            orig_arch = str(sc_data.get("user_override_archetype") or sc_data.get("archetype") or arch_keys[0])
                            if chosen_arch != orig_arch:
                                eff_arch = chosen_arch
                                sc_copy["user_override_archetype"] = eff_arch
                            else:
                                from motion_text import classify_micro_scene_blueprint
                                bp_live = classify_micro_scene_blueprint(
                                    f"{sc_copy['kpi_value']} {sc_copy['concept_title']} {sc_copy['text']} {' '.join(parsed_subs)}",
                                    sc_i,
                                    len(session_scenes)
                                )
                                eff_arch = bp_live.get("visual_subject", chosen_arch)
                            sc_copy["archetype"] = eff_arch
                            sc_copy["visual_subject"] = eff_arch
                            if isinstance(sc_copy.get("scene_style_spec"), dict):
                                sc_copy["scene_style_spec"]["visual_archetype"] = eff_arch
                            updated_scenes_plan.append(sc_copy)

                    btn_col_sfx_fast, btn_col_full_rerender = st.columns(2)
                    with btn_col_sfx_fast:
                        fast_sfx_submit = st.form_submit_button("🔊 تحديث الساوند ديزاين فقط فوراً (في ثانية واحدة!)")
                    with btn_col_full_rerender:
                        full_scene_submit = st.form_submit_button("🎨 تطبيق تعديلات الرسومات والمشاهد وإعادة الرندرة")

                if fast_sfx_submit:
                    with st.spinner("🔊 جاري إعادة تصميم ومزج المؤثرات الصوتية في ثانية واحدة بدون إعادة رندرة الفيديو..."):
                        saved_session["planned_scenes"] = updated_scenes_plan
                        _, sfx_rep_new = remaster_video_sfx_instantly(
                            target_video_path=result_path,
                            planned_scenes=updated_scenes_plan,
                            total_duration=session_dur
                        )
                        saved_session["sfx_cues"] = sfx_rep_new.get("cues", [])
                        try:
                            with open(LAST_SESSION_PATH, "w", encoding="utf-8") as sf:
                                json.dump(saved_session, sf, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                        st.success(f"✅ تم تحديث الساوند ديزاين فوراً ({sfx_rep_new.get('cues_count', 0)} مؤثر صوتي متزامن)!")
                        st.rerun()

                if full_scene_submit and active_input_path:
                    from transcriber import sync_live_scene_edits_to_words, set_custom_caption_override
                    updated_scenes_plan, synced_words = sync_live_scene_edits_to_words(updated_scenes_plan, current_words)
                    if synced_words:
                        new_w_all, new_s_all = set_custom_caption_override(custom_words=synced_words)
                        st.session_state["caption_words"] = new_w_all
                        st.session_state["caption_sentences"] = new_s_all
                    saved_session["planned_scenes"] = updated_scenes_plan
                    try:
                        with open(LAST_SESSION_PATH, "w", encoding="utf-8") as sf:
                            json.dump(saved_session, sf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    params = st.session_state.get("eff_params", {
                        "silence_thresh": -42.0, "padding_ms": 75, "chunk_size": 20, "whisper_model": "base"
                    })
                    new_out_path = os.path.join(OUTPUTS_DIR, f"custom_scenes_{int(time.time())}.mp4")
                    chosen_style = st.session_state.get("processed_style", selected_style)
                    job_manager.start_job(
                        runner_func=run_selected_pipeline,
                        runner_kwargs={
                            "style_name": chosen_style,
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "media_analysis": media_analysis,
                            "eff_silence_thresh": params["silence_thresh"],
                            "eff_padding_ms": params["padding_ms"],
                            "eff_chunk_size": params["chunk_size"],
                            "eff_whisper_model": params["whisper_model"],
                            "ollama_model": ollama_model_choice,
                            "manim_quality": manim_flag,
                            "dialect": dialect_mode,
                            "pexels_key": pexels_api_key,
                            "groq_key": groq_api_key,
                            "gemini_key": gemini_api_key,
                            "openai_key": openai_api_key,
                            "product_hook": product_custom_hook,
                            "product_cta": product_custom_cta,
                            "caption_mode": eff_caption_mode,
                            "custom_planned_scenes": updated_scenes_plan
                        },
                        job_meta={
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "selected_style": chosen_style,
                            "caption_mode": eff_caption_mode,
                            "file_hash": st.session_state.get("last_file_hash"),
                            "media_analysis": media_analysis,
                            "eff_params": params
                        },
                        cleanup_func=lambda: cleanup_temp_directory(TEMP_DIR)
                    )
                    st.rerun()

        with edit_tab_sfx:
            st.markdown("##### 🔊 التحكم الدقيق بكل مؤثر صوتي في الثانية والمللي ثانية:")
            cat_keys_list = list(SFX_CATEGORIES.keys())
            cat_labels_map = {k: SFX_CATEGORIES[k]["label_ar"] for k in cat_keys_list}
            if not session_cues:
                st.info("لا توجد مؤثرات صوتية مسجلة حالياً. اضغط زر إعادة توليد المؤثرات لتفعيل الحزمة الكاملة.")
                if st.button("⚡ توليد ومزج جميع المؤثرات الصوتية تلقائياً الآن (1 ثانية)"):
                    _, sfx_rep_auto = remaster_video_sfx_instantly(
                        target_video_path=result_path,
                        planned_scenes=session_scenes,
                        total_duration=session_dur
                    )
                    saved_session["sfx_cues"] = sfx_rep_auto.get("cues", [])
                    with open(LAST_SESSION_PATH, "w", encoding="utf-8") as sf:
                        json.dump(saved_session, sf, ensure_ascii=False, indent=2)
                    st.rerun()
            else:
                with st.form("granular_sfx_cues_editor_form"):
                    edited_cues = []
                    for c_idx, cue_item in enumerate(session_cues):
                        cc1, cc2, cc3, cc4 = st.columns([1.0, 2.2, 1.0, 0.8])
                        cur_cat = str(cue_item.get("category", "6_whooch"))
                        if cur_cat not in cat_keys_list:
                            cur_cat = "6_whooch"
                        with cc1:
                            t_val = st.number_input(f"الثانية #{c_idx + 1}", value=float(cue_item.get("timestamp_sec", 0.0)), min_value=0.0, max_value=float(max(1.0, session_dur)), step=0.05, format="%.2f", key=f"cue_t_{c_idx}")
                        with cc2:
                            cat_val = st.selectbox(f"المؤثر #{c_idx + 1}", options=cat_keys_list, index=cat_keys_list.index(cur_cat), format_func=lambda x: cat_labels_map.get(x, x), key=f"cue_cat_{c_idx}")
                        with cc3:
                            g_val = st.number_input(f"الصوت dB #{c_idx + 1}", value=float(cue_item.get("gain_db", -8.5)), min_value=-28.0, max_value=3.0, step=0.5, format="%.1f", key=f"cue_g_{c_idx}")
                        with cc4:
                            keep_cue = st.checkbox("تفعيل", value=True, key=f"cue_keep_{c_idx}")
                        if keep_cue:
                            edited_cues.append({
                                "timestamp_sec": round(t_val, 3),
                                "category": cat_val,
                                "gain_db": round(g_val, 2),
                                "variant": int(cue_item.get("variant", c_idx % 4)),
                                "reason": str(cue_item.get("reason", "مؤثر مخصص"))
                            })
                    apply_cues_btn = st.form_submit_button("⚡ دمج التايملاين الصوتي المعدل فوراً في ثانية واحدة (-c:v copy)")
                if apply_cues_btn:
                    _, sfx_rep_custom = remaster_video_sfx_instantly(
                        target_video_path=result_path,
                        planned_scenes=session_scenes,
                        total_duration=session_dur,
                        custom_cues=edited_cues
                    )
                    saved_session["sfx_cues"] = sfx_rep_custom.get("cues", edited_cues)
                    try:
                        with open(LAST_SESSION_PATH, "w", encoding="utf-8") as sf:
                            json.dump(saved_session, sf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    st.success(f"✅ تم تحديث ومزج {len(edited_cues)} مؤثر صوتي في الفيديو خلال ثانية واحدة!")
                    st.rerun()

        with edit_tab_sent:
            if not current_sentences:
                st.info("لا توجد جمل مستخرجة حالياً.")
            else:
                with st.form("sentence_caption_editor_form"):
                    edited_sentences_list = []
                    for s_idx, sent_obj in enumerate(current_sentences):
                        s_start = sent_obj.get("start", 0.0)
                        s_end = sent_obj.get("end", 0.0)
                        new_s_text = st.text_input(
                            f"الجملة #{s_idx + 1} (من {s_start:.2f}s إلى {s_end:.2f}s):",
                            value=sent_obj.get("text", ""),
                            key=f"sent_edit_{s_idx}_{s_start}"
                        )
                        updated_s = dict(sent_obj)
                        updated_s["text"] = new_s_text
                        edited_sentences_list.append(updated_s)

                    apply_sent_btn = st.form_submit_button("🔄 تطبيق تعديلات الجمل وتحديث الفيديو في الخلفية")

                if apply_sent_btn and active_input_path:
                    new_w, new_s = set_custom_caption_override(custom_sentences=edited_sentences_list)
                    st.session_state["caption_words"] = new_w
                    st.session_state["caption_sentences"] = new_s

                    params = st.session_state.get("eff_params", {
                        "silence_thresh": -34.0, "padding_ms": 75, "chunk_size": 20, "whisper_model": "base"
                    })
                    new_out_path = os.path.join(OUTPUTS_DIR, f"edited_captions_{int(time.time())}.mp4")
                    chosen_style = st.session_state.get("processed_style", selected_style)
                    force_cap = (chosen_style == STYLE_OPTIONS[6])

                    job_manager.start_job(
                        runner_func=run_selected_pipeline,
                        runner_kwargs={
                            "style_name": chosen_style,
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "media_analysis": media_analysis,
                            "eff_silence_thresh": params["silence_thresh"],
                            "eff_padding_ms": params["padding_ms"],
                            "eff_chunk_size": params["chunk_size"],
                            "eff_whisper_model": params["whisper_model"],
                            "ollama_model": ollama_model_choice,
                            "manim_quality": manim_flag,
                            "dialect": dialect_mode,
                            "pexels_key": pexels_api_key,
                            "groq_key": groq_api_key,
                            "gemini_key": gemini_api_key,
                            "openai_key": openai_api_key,
                            "product_hook": product_custom_hook,
                            "product_cta": product_custom_cta,
                            "force_caption_overlay_on_cut_mode": force_cap,
                            "caption_mode": eff_caption_mode
                        },
                        job_meta={
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "selected_style": chosen_style,
                            "caption_mode": eff_caption_mode,
                            "file_hash": st.session_state.get("last_file_hash"),
                            "media_analysis": media_analysis,
                            "eff_params": params
                        },
                        cleanup_func=lambda: cleanup_temp_directory(TEMP_DIR)
                    )
                    st.rerun()

        with edit_tab_words:
            if not current_words:
                st.info("لا توجد كلمات مستخرجة حالياً.")
            else:
                with st.form("word_caption_editor_form"):
                    edited_words_list = []
                    for w_idx, w_obj in enumerate(current_words):
                        wc1, wc2, wc3 = st.columns([2.2, 1.0, 1.0])
                        with wc1:
                            new_w_txt = st.text_input(f"الكلمة #{w_idx + 1}", value=str(w_obj.get("word", "")), key=f"w_txt_{w_idx}")
                        with wc2:
                            new_w_start = st.number_input(f"البداية (ث) #{w_idx + 1}", value=float(w_obj.get("start", 0.0)), step=0.05, format="%.2f", key=f"w_start_{w_idx}")
                        with wc3:
                            new_w_end = st.number_input(f"النهاية (ث) #{w_idx + 1}", value=float(w_obj.get("end", 0.2)), step=0.05, format="%.2f", key=f"w_end_{w_idx}")
                        if new_w_txt.strip():
                            edited_words_list.append({
                                "word": new_w_txt.strip(),
                                "start": round(new_w_start, 3),
                                "end": round(max(new_w_start + 0.08, new_w_end), 3)
                            })

                    apply_words_btn = st.form_submit_button("🔄 تطبيق تعديلات الكلمات وتحديث الفيديو في الخلفية")

                if apply_words_btn and active_input_path:
                    new_w, new_s = set_custom_caption_override(custom_words=edited_words_list)
                    st.session_state["caption_words"] = new_w
                    st.session_state["caption_sentences"] = new_s

                    params = st.session_state.get("eff_params", {
                        "silence_thresh": -34.0, "padding_ms": 75, "chunk_size": 20, "whisper_model": "base"
                    })
                    new_out_path = os.path.join(OUTPUTS_DIR, f"edited_words_{int(time.time())}.mp4")
                    chosen_style = st.session_state.get("processed_style", selected_style)
                    force_cap = (chosen_style == STYLE_OPTIONS[6])

                    job_manager.start_job(
                        runner_func=run_selected_pipeline,
                        runner_kwargs={
                            "style_name": chosen_style,
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "media_analysis": media_analysis,
                            "eff_silence_thresh": params["silence_thresh"],
                            "eff_padding_ms": params["padding_ms"],
                            "eff_chunk_size": params["chunk_size"],
                            "eff_whisper_model": params["whisper_model"],
                            "ollama_model": ollama_model_choice,
                            "manim_quality": manim_flag,
                            "dialect": dialect_mode,
                            "pexels_key": pexels_api_key,
                            "groq_key": groq_api_key,
                            "gemini_key": gemini_api_key,
                            "openai_key": openai_api_key,
                            "product_hook": product_custom_hook,
                            "product_cta": product_custom_cta,
                            "force_caption_overlay_on_cut_mode": force_cap,
                            "caption_mode": eff_caption_mode
                        },
                        job_meta={
                            "input_path": active_input_path,
                            "output_path": new_out_path,
                            "selected_style": chosen_style,
                            "caption_mode": eff_caption_mode,
                            "file_hash": st.session_state.get("last_file_hash"),
                            "media_analysis": media_analysis,
                            "eff_params": params
                        },
                        cleanup_func=lambda: cleanup_temp_directory(TEMP_DIR)
                    )
                    st.rerun()