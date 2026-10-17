"""
app.py - الواجهة التفاعلية لنظام أتمتة المونتاج، الموشن جرافيك السياقي، والعمل المستمر في الخلفية
====================================================================================================
التحديثات الجوهرية:
1. محرك العمل المستمر في الخلفية وحفظ الجلسة التلقائي (`PersistentBackgroundJobManager` مدمج بالكامل):
   - يستمر السيرفر في رندرة الفيديو حتى لو خرج المستخدم من متصفح Google Chrome أو أغلق شاشة الهاتف أو انقطع الإنترنت!
   - بمجرد عودة المستخدم وفتح الموقع مرة أخرى، يسترجع النظام تلقائياً شريط التقدم الحي أو يعرض الفيديو المكتمل الجاهز للتحميل فوراً!
2. حماية الذاكرة القصوى (Zero-OOM Upload & Streaming Engine):
   - حفظ الفيديوهات المرفوعة (55MB و100MB+) بالتدفق المجزأ (512KB Chunks) بدون نسخها في الـ RAM (`getvalue()`)،
     وتطبيعها فورياً عبر FFmpeg أحادي الخيط مع تحرير ذاكرة نظام التشغيل (`glibc malloc_trim`).
3. مخ التحليل السياقي والسردي ذو المرحلتين (`Two-Pass Contextual & Narrative Brain`) + استيراد مشاهد B-Roll خالية من حقوق الملكية.
"""

import sys
import os
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
from typing import Dict, Any, Optional, Callable

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    "auto_cut",
    "transcriber",
    "stock_video_finder",
    "motion_text",
    "smart_analyzer",
    "dynamic_edit",
    "manim_generator"
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
        background: linear-gradient(90deg, #38BDF8, #FBBF24);
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
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.16), rgba(2, 132, 199, 0.16));
        border: 1px solid rgba(16, 185, 129, 0.45);
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

st.markdown('<div class="main-title">🎬 استوديو المونتاج الذكي والموشن جرافيك السياقي</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">محرك كوريغرافيا ذاتي التعلم (Clean SaaS & Split-Screen Stage 30fps) • يفهم السياق والدارجة بلا بتر • يعمل في الخلفية</div>',
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
        "🤖 تحديد أفضل الموديلات والإعدادات تلقائياً (موصى به)",
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
    st.subheader("🎚️ إعدادات قص الصمت الطبيعي والموديلات")
    if auto_optimize:
        st.caption("✅ **القص البشري الطبيعي + حماية الذاكرة مفعّلة:** عتبة آمنة (250ms) تحمي مخارج الحروف.")
        silence_threshold = -42.0
        chunk_size = 20
        padding_ms = 250
        whisper_model_choice = "base"
    else:
        silence_threshold = st.slider("عتبة الصمت (dBFS)", min_value=-60.0, max_value=-20.0, value=-42.0, step=1.0)
        chunk_size = st.slider("دقة الفحص (Chunk Size ms)", min_value=10, max_value=50, value=20, step=5)
        padding_ms = st.slider("هامش حماية الكلام الطبيعي (ms)", min_value=150, max_value=450, value=250, step=10)
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
            "✨ كابشن ريلز عصري متفاعل (أسفل الشاشة - سطر واحد تفاعلي Karaoke)",
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
    "🚀 موشن جرافيك نصي وأنفوجرافيك احترافي (Studio Kinetic Typography)",
    "📐 موشن جرافيك هندسي ذكي (Manim + AI Infographics)",
    "🔍 مونتاج ديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)",
    "✂️ قص الصمت الطبيعي وتنظيف الصوت فقط (Natural Jump-cuts)"
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
    caption_mode: str = "bottom_modern"
) -> str:
    force_free_ram()

    if style_name == STYLE_OPTIONS[0]:
        from dynamic_edit import apply_smart_director_all_in_one
        res = _safe_call(
            apply_smart_director_all_in_one,
            input_path=input_path,
            output_path=output_path,
            media_analysis=media_analysis,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            dialect_mode=dialect,
            pexels_api_key=pexels_key,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb,
            caption_mode=caption_mode
        )
        return _unwrap_path(res)

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
            caption_mode=caption_mode
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
            caption_mode=caption_mode
        )
        return _unwrap_path(res)

    elif style_name == STYLE_OPTIONS[3]:
        from motion_text import create_kinetic_typography_video
        res = _safe_call(
            create_kinetic_typography_video,
            input_path=input_path,
            output_path=output_path,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb
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
            progress_callback=progress_cb
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
            caption_mode=caption_mode
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
# 5. جسم الصفحة: رفع ملف ومحرر الإعدادات (باستهلاك ذاكرة صفري للرفع!)
# ==============================================================================
col1, col2 = st.columns([1.08, 1.0], gap="large")

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
            with st.spinner("🔍 جاري فحص وتحليل خصائص الصوت والفيديو تلقائياً..."):
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
            f"المدة: `{media_analysis['duration_sec']} ثانية` | حجم العمل الرشيق: `{media_analysis['file_size_mb']} MB`)"
        )

        if media_analysis["has_video"]:
            st.video(active_input_path)
        else:
            st.audio(active_input_path)

        with st.expander("📊 تقرير التحليل الذكي ومخطط المخرج الشامل", expanded=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("متوسط الصوت", f"{media_analysis['mean_dbfs']} dBFS")
            m2.metric("عتبة الصمت الآمنة", f"{media_analysis['optimal_silence_threshold']} dBFS")
            m3.metric("نسبة الصمت", f"{media_analysis['silence_percent']}%")
            m4.metric("موديل التفريغ", media_analysis["optimal_whisper_model"].upper())

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
            "- **مخ تحليل سياقي:** يفهم القصة الكاملة للفيديو ومعنى الجمل المترابطة.\n"
            "- **استيراد 3-4 مشاهد B-Roll حقيقية خالية من حقوق الملكية** في اللحظات المناسبة لكسر الملل.\n"
            "- **يعمل في الخلفية:** يمكنك الخروج من كروم والعودة لاحقاً لتجد الفيديو جاهزاً."
        )
    elif selected_style == STYLE_OPTIONS[1]:
        st.info("🛍️ **إعلانات المنتجات والتجارة الإلكترونية:** خطاف Hook 0-3s، إبراز المشكلة، ميزات المنتج، شارات الثقة (58 ولاية / دفع عند الاستلام)، ولافتة الشراء CTA.")
        with st.expander("📝 تخصيص نصوص الإعلان (اختياري)", expanded=False):
            product_custom_hook = st.text_input("عنوان الخطاف العلوي (Hook Banner):", placeholder="مثال: 🔥 المنتج الأقوى في الجزائر!")
            product_custom_cta = st.text_input("نص نداء الشراء السفلي (Call To Action):", placeholder="مثال: 🛒 اطلب الآن والدفع عند الاستلام!")
    elif selected_style == STYLE_OPTIONS[2]:
        st.info("🎨 **دمج الموشن جرافيك وB-Roll بالفيديو الأصلي:** بطاقات زجاجية علوية ومشاهد B-Roll واقعية وكابشن بالثلث السفلي.")
    elif selected_style == STYLE_OPTIONS[3]:
        st.info("🚀 **موشن جرافيك نصي احترافي موجه بالسياق:** بطاقات Bento زجاجية ورسومات فيكتور تعبر عن الفكرة الكاملة للجملة.")
    elif selected_style == STYLE_OPTIONS[4]:
        st.info("📐 **موشن جرافيك هندسي (Manim + AI):** رسوم ومخططات بيانية متحركة.")
    elif selected_style == STYLE_OPTIONS[5]:
        st.info("🔍 **مونتاج ديناميكي:** قص صمت طبيعي مع زوم 15% متناوب وكابشن أصفر.")
    else:
        st.info("✂️ **قص الصمت الطبيعي:** إزالة فترات السكوت الطويلة مع الحفاظ على طبيعية الكلام البشري.")

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
        st.markdown("### ✏️ تعديل الكابشن والنصوص في الفيديو")
        st.caption("عدّل أي كلمة أو جملة ثم اضغط زر التحديث ليتم تعديل الكابشن في الخلفية فوراً.")

        current_words = st.session_state.get("caption_words", [])
        current_sentences = st.session_state.get("caption_sentences", [])

        edit_tab_sent, edit_tab_words = st.tabs([
            "📝 التعديل السريع جملة بجملة (موصى به)",
            "🔤 التعديل التفصيلي كلمة بكلمة مع التوقيت"
        ])

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
                        "silence_thresh": -42.0, "padding_ms": 250, "chunk_size": 20, "whisper_model": "base"
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
                        "silence_thresh": -42.0, "padding_ms": 250, "chunk_size": 20, "whisper_model": "base"
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