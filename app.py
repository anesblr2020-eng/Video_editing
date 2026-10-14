"""
app.py - الواجهة التفاعلية لنظام أتمتة المونتاج والموشن جرافيك ومحرر الكابشن التفاعلي
====================================================================================
التحديثات الجوهرية:
1. محرر كابشن تفاعلي شامل يظهر بعد انتهاء المعالجة في جميع الأنماط (تعديل جملة بجملة أو كلمة بكلمة مع التوقيت الزمني وإعادة تحديث الفيديو بضغطة زر دون إعادة تشغيل Whisper).
2. قص صمت طبيعي ككلام الإنسان (Natural Human Cadence) يحمي مخارج الحروف الضعيفة والتنفس الطبيعي ولا يلصق الكلام ببعضه.
3. نمط مونتاج إعلانات المنتجات (E-Commerce & Product Ads) + النمط التلقائي الشامل + دمج الموشن جرافيك بالفيديو الأصلي.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy لمنع خطأ 'PIL.Image' has no attribute 'ANTIALIAS'
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
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

PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import shutil
import time
import hashlib
import streamlit as st

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

# ==============================================================================
# 1. إعداد مسارات المجلدات وضمان وجودها تلقائياً
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ICONS_DIR = os.path.join(BASE_DIR, "assets", "icons")
FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")

for directory in [INPUTS_DIR, OUTPUTS_DIR, TEMP_DIR, ICONS_DIR, FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)


def cleanup_temp_directory(temp_path: str = TEMP_DIR):
    """تنظيف مجلد temp بعد اكتمال المعالجة."""
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


# ==============================================================================
# 2. إعدادات واجهة Streamlit والتصميم البصري
# ==============================================================================
st.set_page_config(
    page_title="استوديو المونتاج وإعلانات المنتجات الذكي",
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
        font-size: 1.08rem;
        text-align: center;
        color: #94A3B8;
        margin-bottom: 1.6rem;
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

st.markdown('<div class="main-title">🎬 استوديو المونتاج الذكي وإعلانات المنتجات التجارية</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">مونتاج احترافي لإعلانات المنتجات • قص صمت طبيعي ككلام الإنسان • تعديل الكابشن بعد ظهور النتيجة في كل الأنماط • دعم الدارجة الجزائرية 🇩🇿</div>',
    unsafe_allow_html=True
)

# ==============================================================================
# 3. الشريط الجانبي: إعدادات الذكاء الاصطناعي والدارجة الجزائرية
# ==============================================================================
with st.sidebar:
    st.header("⚙️ الإعدادات الذكية والاتصال")

    auto_optimize = st.toggle(
        "🤖 تحديد أفضل الموديلات والإعدادات تلقائياً (موصى به)",
        value=True,
        help="يقوم النظام بتحليل الصوت والضجيج لضبط عتبة صمت طبيعية تحمي مخارج الحروف وتنفس المتحدث."
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
    st.subheader("🌐 محرك الذكاء الاصطناعي (الإنترنت / السحابة)")
    with st.expander("🔑 مفاتيح سحابية اختيارية (لأقصى سرعة وجودة)", expanded=False):
        st.caption("يعمل النظام بالإنترنت مجاناً بشكل تلقائي! ويمكنك اختيارياً وضع مفتاح Groq أو Gemini:")
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
        st.caption("✅ **القص البشري الطبيعي مفعّل:** يحمي بدايات ونهايات الكلمات والتنفس الطبيعي (250ms) ولا يقص إلا السكوت الطويل (> 700ms).")
        silence_threshold = -42.0
        chunk_size = 10
        padding_ms = 250
        whisper_model_choice = "small"
    else:
        silence_threshold = st.slider("عتبة الصمت (dBFS)", min_value=-60.0, max_value=-20.0, value=-42.0, step=1.0)
        chunk_size = st.slider("دقة الفحص (Chunk Size ms)", min_value=5, max_value=50, value=10, step=5)
        padding_ms = st.slider(
            "هامش حماية الكلام الطبيعي قبل وبعد الجمل (ms)",
            min_value=150,
            max_value=450,
            value=250,
            step=10,
            help="كلما زادت القيمة كان تدفق الكلام أكثر طبيعية وهدوءاً دون أي بتر للحروف."
        )
        whisper_model_choice = st.selectbox(
            "حجم نموذج Whisper المحلي:",
            options=["tiny", "base", "small", "medium", "large-v3"],
            index=2
        )

    ollama_model_choice = st.text_input("نموذج Ollama المحلي:", value="llama3")
    manim_quality_choice = st.selectbox(
        "دقة رندرة الموشن الهندسي (Manim):",
        options=["-qh (1080p عالية)", "-qm (720p متوسطة)", "-ql (480p سريعة)"],
        index=0
    )
    manim_flag = manim_quality_choice.split()[0]


# ==============================================================================
# 4. دالة موحدة لتشغيل أي نمط مونتاج (تستخدم عند البدء وعند تحديث الكابشن)
# ==============================================================================
STYLE_OPTIONS = [
    "🛍️ نمط إعلانات المنتجات والتجارة الإلكترونية (E-Commerce & Product Ads)",
    "✨ النمط التلقائي الذكي - يدمج كل الأدوار بمعايير علمية (Smart Director All-in-One)",
    "🎨 دمج الموشن جرافيك بالفيديو الأصلي (Motion Graphics Overlay on Video)",
    "🚀 موشن جرافيك نصي وأنفوجرافيك احترافي (Studio Kinetic Typography)",
    "📐 موشن جرافيك هندسي ذكي (Manim + AI Infographics)",
    "🔍 مونتاج ديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)",
    "✂️ قص الصمت الطبيعي وتنظيف الصوت فقط (Natural Jump-cuts)"
]


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
    groq_key: str,
    gemini_key: str,
    openai_key: str,
    product_hook: str,
    product_cta: str,
    progress_cb,
    force_caption_overlay_on_cut_mode: bool = False
) -> str:
    """تشغيل مسار المعالجة المختار وإرجاع مسار الملف النهائي مع ضمان استخراج الكابشن للتعديل."""
    if style_name == STYLE_OPTIONS[0]:
        from dynamic_edit import apply_product_ad_mode
        out, _ = apply_product_ad_mode(
            input_path=input_path,
            output_path=output_path,
            product_name_override=product_hook,
            cta_override=product_cta,
            silence_threshold=eff_silence_thresh,
            padding_ms=eff_padding_ms,
            whisper_model=eff_whisper_model,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb
        )
        return out

    elif style_name == STYLE_OPTIONS[1]:
        from dynamic_edit import apply_smart_director_all_in_one
        out, _ = apply_smart_director_all_in_one(
            input_path=input_path,
            output_path=output_path,
            media_analysis=media_analysis,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb
        )
        return out

    elif style_name == STYLE_OPTIONS[2]:
        from dynamic_edit import apply_motion_overlay_on_video
        return apply_motion_overlay_on_video(
            input_path=input_path,
            output_path=output_path,
            silence_threshold=eff_silence_thresh,
            chunk_size=eff_chunk_size,
            padding_ms=eff_padding_ms,
            whisper_model=eff_whisper_model,
            ollama_model=ollama_model,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb
        )

    elif style_name == STYLE_OPTIONS[3]:
        from motion_text import create_kinetic_typography_video
        return create_kinetic_typography_video(
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

    elif style_name == STYLE_OPTIONS[4]:
        from manim_generator import generate_manim_motion_graphics
        return generate_manim_motion_graphics(
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

    elif style_name == STYLE_OPTIONS[5] or force_caption_overlay_on_cut_mode:
        from dynamic_edit import apply_dynamic_edit
        return apply_dynamic_edit(
            input_path=input_path,
            output_path=output_path,
            silence_threshold=eff_silence_thresh,
            chunk_size=eff_chunk_size,
            padding_ms=eff_padding_ms,
            zoom_factor=1.0 if force_caption_overlay_on_cut_mode else 1.15,
            whisper_model=eff_whisper_model,
            dialect_mode=dialect,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            openai_api_key=openai_key,
            progress_callback=progress_cb
        )

    else:
        # نمط قص الصمت الطبيعي: نقص الصمت ونفرغ النص أيضاً لتمكين المستخدم من مراجعة وتعديل الكابشن إن أراد
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
# 5. القسم الرئيسي: رفع ملف أو تسجيل صوتي مباشر
# ==============================================================================
col1, col2 = st.columns([1.08, 1.0], gap="large")

with col1:
    st.subheader("1. رفع الفيديو أو الملف الصوتي / تسجيل مباشر")

    tab_upload, tab_record = st.tabs([
        "📁 رفع فيديو أو صوت (بجميع الصيغ)",
        "🎙️ تسجيل صوتي مباشر من المايكروفون"
    ])

    raw_media_bytes = None
    raw_media_name = None

    with tab_upload:
        allow_any_ext = st.checkbox(
            "🔓 السماح برفع أي ملف بدون تقييد المتصفح",
            value=False
        )
        uploaded_file = st.file_uploader(
            "اختر ملف فيديو (MP4, MOV, MKV...) أو التسجيل الصوتي",
            type=None if allow_any_ext else ALL_SUPPORTED_EXTENSIONS,
            help="يدعم جميع صيغ الفيديو والتسجيلات الصوتية."
        )
        if uploaded_file is not None:
            raw_media_bytes = uploaded_file.getvalue()
            raw_media_name = uploaded_file.name

    with tab_record:
        st.caption("سجّل صوتك مباشرة بالدارجة الجزائرية أو العربية:")
        if hasattr(st, "audio_input"):
            recorded_audio = st.audio_input("اضغط للتسجيل الصوتي المباشر")
            if recorded_audio is not None:
                raw_media_bytes = recorded_audio.getvalue()
                raw_media_name = f"voice_record_{int(time.time())}.wav"
        else:
            st.info("يرجى استخدام تبويب رفع الملفات لرفع تسجيلك الصوتي.")

    active_input_path = None
    media_analysis = None

    if raw_media_bytes and raw_media_name:
        file_hash = hashlib.md5(raw_media_bytes[:65536] + str(len(raw_media_bytes)).encode()).hexdigest()[:10]
        safe_ext = os.path.splitext(raw_media_name)[1].lower() or ".wav"
        saved_input_path = os.path.join(INPUTS_DIR, f"media_{file_hash}{safe_ext}")

        # إذا قام المستخدم برفع ملف جديد، نصفر الكابشن المعدل السابق
        if st.session_state.get("last_file_hash") != file_hash:
            clear_custom_caption_override()
            st.session_state["last_file_hash"] = file_hash
            st.session_state.pop("processed_result_path", None)

        if not os.path.exists(saved_input_path):
            with open(saved_input_path, "wb") as f:
                f.write(raw_media_bytes)

        playable_path, is_vid = ensure_playable_audio_or_video(saved_input_path, INPUTS_DIR)
        active_input_path = playable_path

        cache_analysis_key = f"analysis_{file_hash}"
        if cache_analysis_key not in st.session_state:
            with st.spinner("🔍 جاري فحص وتحليل خصائص الصوت والفيديو تلقائياً..."):
                st.session_state[cache_analysis_key] = analyze_media_file(
                    active_input_path,
                    groq_api_key=groq_api_key,
                    gemini_api_key=gemini_api_key,
                    openai_api_key=openai_api_key
                )
        media_analysis = st.session_state[cache_analysis_key]

        st.success(
            f"✅ **تم استلام وتجهيز الملف بنجاح!** ({media_analysis['media_type_ar']} | "
            f"المدة: `{media_analysis['duration_sec']} ثانية` | الحجم: `{media_analysis['file_size_mb']} MB`)"
        )

        if media_analysis["has_video"]:
            st.video(active_input_path)
        else:
            st.audio(active_input_path)

        with st.expander("📊 تقرير التحليل الذكي ومعايير المونتاج", expanded=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("متوسط الصوت", f"{media_analysis['mean_dbfs']} dBFS")
            m2.metric("عتبة الصمت الآمنة", f"{media_analysis['optimal_silence_threshold']} dBFS")
            m3.metric("نسبة الصمت", f"{media_analysis['silence_percent']}%")
            m4.metric("موديل التفريغ", media_analysis["optimal_whisper_model"].upper())

            st.markdown("**📌 المعايير المطبقة لحماية الكلام الطبيعي:**")
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
            "🛍️ **مونتاج إعلانات المنتجات 100% احترافي وغير عشوائي:**\n"
            "- **قص السكوت الطبيعي:** يزيل فترات السكوت الطويلة فقط مع الحفاظ التام على مخارج الحروف والتنفس الطبيعي.\n"
            "- **الخطاف البصري (Hook 0-3s):** زوم مفاجئ (1.18x) ولافتة علوية ساطعة لإيقاف التمرير.\n"
            "- **إبراز المشكلة والمميزات وشارات الثقة (توصيل 58 ولاية 🚚 / الدفع عند الاستلام 💵) ولافتة الشراء CTA.**"
        )
        with st.expander("📝 تخصيص نصوص الإعلان (اختياري)", expanded=False):
            product_custom_hook = st.text_input("عنوان الخطاف العلوي (Hook Banner):", placeholder="مثال: 🔥 المنتج الأقوى والأكثر طلباً في الجزائر!")
            product_custom_cta = st.text_input("نص نداء الشراء السفلي (Call To Action):", placeholder="مثال: 🛒 اطلب الآن والدفع عند الاستلام حتى لباب دارك!")
    elif selected_style == STYLE_OPTIONS[1]:
        st.info("🧠 **المخرج الذكي الشامل (All-in-One):** يحلل كل جملة ويوزع الأدوار بين الزوم وبطاقات الموشن والكابشن مع قص صمت طبيعي.")
    elif selected_style == STYLE_OPTIONS[2]:
        st.info("🎨 **دمج الموشن جرافيك بالفيديو الأصلي:** بطاقات زجاجية وأيقونات فيكتور علوية وكابشن بالثلث السفلي.")
    elif selected_style == STYLE_OPTIONS[3]:
        st.info("🚀 **موشن جرافيك نصي احترافي:** خلفية أستوديو سينمائية وأيقونات فيكتور مع كابشن كاريوكي.")
    elif selected_style == STYLE_OPTIONS[4]:
        st.info("📐 **موشن جرافيك هندسي (Manim + AI):** رسوم ومخططات بيانية متحركة مع كابشن متزامن.")
    elif selected_style == STYLE_OPTIONS[5]:
        st.info("🔍 **مونتاج ديناميكي:** قص صمت طبيعي مع زوم 15% متناوب وكابشن أصفر.")
    else:
        st.info("✂️ **قص الصمت الطبيعي:** إزالة فترات السكوت الطويلة مع الحفاظ على طبيعية الكلام البشري (ويمكنك إضافة وتعديل الكابشن بعد ظهور النتيجة!).")

    st.markdown("<br>", unsafe_allow_html=True)
    start_btn = st.button("🚀 بدء صناعة ومونتاج الفيديو (Start Processing)", use_container_width=True)


# ==============================================================================
# 6. تنفيذ المعالجة الأولية عند الضغط على زر البدء
# ==============================================================================
if start_btn:
    if active_input_path is None or not os.path.exists(active_input_path):
        st.warning("⚠️ يرجى رفع ملف فيديو أو صوت (أو تسجيل صوتك) أولاً قبل بدء المعالجة.")
    else:
        # عند الضغط على بدء جديد، نعيد ضبط التعديلات اليدوية السابقة للكابشن
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

        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_ui_progress(percent: float, text: str):
            progress_bar.progress(min(1.0, max(0.0, float(percent))))
            status_text.markdown(f"**⏳ الحالة الجارية:** {text}")

        try:
            with st.spinner("🎬 جاري تشغيل محرك المونتاج الذكي..."):
                processed_path = run_selected_pipeline(
                    style_name=selected_style,
                    input_path=active_input_path,
                    output_path=output_file_path,
                    media_analysis=media_analysis,
                    eff_silence_thresh=eff_silence_thresh,
                    eff_padding_ms=eff_padding_ms,
                    eff_chunk_size=eff_chunk_size,
                    eff_whisper_model=eff_whisper_model,
                    ollama_model=ollama_model_choice,
                    manim_quality=manim_flag,
                    dialect=dialect_mode,
                    groq_key=groq_api_key,
                    gemini_key=gemini_api_key,
                    openai_key=openai_api_key,
                    product_hook=product_custom_hook,
                    product_cta=product_custom_cta,
                    progress_cb=update_ui_progress
                )

                words_extracted, sentences_extracted = get_last_extracted_transcript()
                st.session_state["processed_result_path"] = processed_path
                st.session_state["processed_style"] = selected_style
                st.session_state["caption_words"] = words_extracted
                st.session_state["caption_sentences"] = sentences_extracted
                st.session_state["eff_params"] = {
                    "silence_thresh": eff_silence_thresh,
                    "padding_ms": eff_padding_ms,
                    "chunk_size": eff_chunk_size,
                    "whisper_model": eff_whisper_model
                }

        except Exception as err:
            st.error(f"❌ حدث خطأ أثناء المعالجة: {str(err)}")
        finally:
            cleanup_temp_directory(TEMP_DIR)
            update_ui_progress(1.0, "اكتملت المعالجة بنجاح!")


# ==============================================================================
# 7. عرض النتيجة النهائية + محرر الكابشن التفاعلي (يعمل في جميع الأنماط!)
# ==============================================================================
result_path = st.session_state.get("processed_result_path")
if result_path and os.path.exists(result_path):
    st.markdown("---")
    st.success("🎉 **الفيديو الجاهز للعرض والتحميل (يمكنك تعديل الكابشن بالأسفل في أي وقت!):**")

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
        st.markdown("### ✏️ تعديل الكابشن والنصوص في الفيديو (في جميع الأنماط)")
        st.caption(
            "عدّل أي كلمة أو جملة مكتوبة في الفيديو بكل سهولة، ثم اضغط على زر التحديث بالأسفل ليتم تعديل الكابشن والبطاقات في الفيديو فوراً بدون إعادة التفريغ الصوتي!"
        )

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
                    st.markdown("**عدّل نص أي جملة بالدارجة الجزائرية أو العربية ثم اضغط زر التحديث بالأسفل:**")
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

                    apply_sent_btn = st.form_submit_button("🔄 تطبيق تعديلات الجمل وتحديث الفيديو فوراً")

                if apply_sent_btn and active_input_path:
                    new_w, new_s = set_custom_caption_override(custom_sentences=edited_sentences_list)
                    st.session_state["caption_words"] = new_w
                    st.session_state["caption_sentences"] = new_s

                    params = st.session_state.get("eff_params", {
                        "silence_thresh": -42.0, "padding_ms": 250, "chunk_size": 10, "whisper_model": "small"
                    })
                    new_out_path = os.path.join(OUTPUTS_DIR, f"edited_captions_{int(time.time())}.mp4")
                    prog_edit = st.progress(0.0)
                    stat_edit = st.empty()

                    def _edit_cb(p: float, txt: str):
                        prog_edit.progress(min(1.0, max(0.0, float(p))))
                        stat_edit.markdown(f"**⏳ جاري تحديث الفيديو بالكابشن الجديد:** {txt}")

                    try:
                        with st.spinner("✨ جاري تحديث الكابشن وإعادة إنتاج الفيديو في ثوانٍ..."):
                            chosen_style = st.session_state.get("processed_style", selected_style)
                            force_cap = (chosen_style == STYLE_OPTIONS[6])
                            updated_video_path = run_selected_pipeline(
                                style_name=chosen_style,
                                input_path=active_input_path,
                                output_path=new_out_path,
                                media_analysis=media_analysis,
                                eff_silence_thresh=params["silence_thresh"],
                                eff_padding_ms=params["padding_ms"],
                                eff_chunk_size=params["chunk_size"],
                                eff_whisper_model=params["whisper_model"],
                                ollama_model=ollama_model_choice,
                                manim_quality=manim_flag,
                                dialect=dialect_mode,
                                groq_key=groq_api_key,
                                gemini_key=gemini_api_key,
                                openai_key=openai_api_key,
                                product_hook=product_custom_hook,
                                product_cta=product_custom_cta,
                                progress_cb=_edit_cb,
                                force_caption_overlay_on_cut_mode=force_cap
                            )
                            st.session_state["processed_result_path"] = updated_video_path
                            st.rerun()
                    finally:
                        cleanup_temp_directory(TEMP_DIR)

        with edit_tab_words:
            if not current_words:
                st.info("لا توجد كلمات مستخرجة حالياً.")
            else:
                with st.form("word_caption_editor_form"):
                    st.markdown("**عدّل الكلمات المفردة أو تواقيتها الزمنية:**")
                    edited_words_list = []
                    for w_idx, w_obj in enumerate(current_words):
                        wc1, wc2, wc3 = st.columns([2.2, 1.0, 1.0])
                        with wc1:
                            new_w_txt = st.text_input(
                                f"الكلمة #{w_idx + 1}",
                                value=str(w_obj.get("word", "")),
                                key=f"w_txt_{w_idx}"
                            )
                        with wc2:
                            new_w_start = st.number_input(
                                f"البداية (ث) #{w_idx + 1}",
                                value=float(w_obj.get("start", 0.0)),
                                step=0.05,
                                format="%.2f",
                                key=f"w_start_{w_idx}"
                            )
                        with wc3:
                            new_w_end = st.number_input(
                                f"النهاية (ث) #{w_idx + 1}",
                                value=float(w_obj.get("end", 0.2)),
                                step=0.05,
                                format="%.2f",
                                key=f"w_end_{w_idx}"
                            )
                        if new_w_txt.strip():
                            edited_words_list.append({
                                "word": new_w_txt.strip(),
                                "start": round(new_w_start, 3),
                                "end": round(max(new_w_start + 0.08, new_w_end), 3)
                            })

                    apply_words_btn = st.form_submit_button("🔄 تطبيق تعديلات الكلمات وتحديث الفيديو فوراً")

                if apply_words_btn and active_input_path:
                    new_w, new_s = set_custom_caption_override(custom_words=edited_words_list)
                    st.session_state["caption_words"] = new_w
                    st.session_state["caption_sentences"] = new_s

                    params = st.session_state.get("eff_params", {
                        "silence_thresh": -42.0, "padding_ms": 250, "chunk_size": 10, "whisper_model": "small"
                    })
                    new_out_path = os.path.join(OUTPUTS_DIR, f"edited_words_{int(time.time())}.mp4")
                    prog_edit2 = st.progress(0.0)
                    stat_edit2 = st.empty()

                    def _edit_cb2(p: float, txt: str):
                        prog_edit2.progress(min(1.0, max(0.0, float(p))))
                        stat_edit2.markdown(f"**⏳ جاري تحديث الفيديو بالكابشن الجديد:** {txt}")

                    try:
                        with st.spinner("✨ جاري تحديث الكابشن وإعادة إنتاج الفيديو في ثوانٍ..."):
                            chosen_style = st.session_state.get("processed_style", selected_style)
                            force_cap = (chosen_style == STYLE_OPTIONS[6])
                            updated_video_path = run_selected_pipeline(
                                style_name=chosen_style,
                                input_path=active_input_path,
                                output_path=new_out_path,
                                media_analysis=media_analysis,
                                eff_silence_thresh=params["silence_thresh"],
                                eff_padding_ms=params["padding_ms"],
                                eff_chunk_size=params["chunk_size"],
                                eff_whisper_model=params["whisper_model"],
                                ollama_model=ollama_model_choice,
                                manim_quality=manim_flag,
                                dialect=dialect_mode,
                                groq_key=groq_api_key,
                                gemini_key=gemini_api_key,
                                openai_key=openai_api_key,
                                product_hook=product_custom_hook,
                                product_cta=product_custom_cta,
                                progress_cb=_edit_cb2,
                                force_caption_overlay_on_cut_mode=force_cap
                            )
                            st.session_state["processed_result_path"] = updated_video_path
                            st.rerun()
                    finally:
                        cleanup_temp_directory(TEMP_DIR)
