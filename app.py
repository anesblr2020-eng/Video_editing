"""
app.py - الواجهة التفاعلية لنظام أتمتة المونتاج والموشن جرافيك الهجين (سحابي + محلي)
====================================================================================
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy لمنع خطأ 'PIL.Image' has no attribute 'ANTIALIAS'
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
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
    page_title="استوديو المونتاج والموشن جرافيك الذكي (الدارجة الجزائرية والعربية)",
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
    .analysis-box {
        background-color: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 12px;
        padding: 14px 18px;
        margin-top: 10px;
        margin-bottom: 14px;
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

st.markdown('<div class="main-title">🎬 استوديو المونتاج الذكي والموشن جرافيك الهجين (سحابي + محلي)</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">تحليل ذكي للفيديو والصوت • دعم متكامل للدارجة الجزائرية 🇩🇿 والعربية • موشن جرافيك احترافي ودمج شامل للأدوار</div>',
    unsafe_allow_html=True
)

# ==============================================================================
# 3. الشريط الجانبي: إعدادات الذكاء الاصطناعي والدارجة الجزائرية والتحكم التلقائي
# ==============================================================================
with st.sidebar:
    st.header("⚙️ الإعدادات الذكية والاتصال")

    auto_optimize = st.toggle(
        "🤖 تحديد أفضل الموديلات والإعدادات تلقائياً (موصى به)",
        value=True,
        help="يقوم النظام بتحليل مستوى الصوت والضجيج ونوع الملف لاختيار أفضل عتبة صمت وأفضل موديل تلقائياً."
    )

    st.subheader("🇩🇿 إعدادات اللغة واللهجة")
    dialect_choice_label = st.selectbox(
        "نمط فهم الكلام والكتابة:",
        options=[
            "الدارجة الجزائرية + العربية (دقيق جداً 🇩🇿)",
            "تحويل تلقائي للعربية المبسطة"
        ],
        index=0,
        help="يهيئ نموذج الصوت والذكاء الاصطناعي لفهم مفردات الدارجة الجزائرية بدقة عالية."
    )
    dialect_mode = "algerian_darija" if "الدارجة" in dialect_choice_label else "msa_simplified"

    st.markdown("---")
    st.subheader("🌐 محرك الذكاء الاصطناعي (الإنترنت / السحابة)")
    with st.expander("🔑 مفاتيح سحابية اختيارية (لأقصى سرعة وجودة)", expanded=False):
        st.caption("يعمل النظام بالإنترنت مجاناً بشكل تلقائي! ويمكنك اختيارياً وضع مفتاح Groq أو Gemini لتسريع التفريغ بـ Whisper Large-v3 السحابي:")
        groq_api_key = st.text_input("Groq API Key (اختياري - مجاني وسريع جداً):", type="password", value=os.environ.get("GROQ_API_KEY", ""))
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
    st.subheader("🎚️ إعدادات الصوت والموديلات")
    if auto_optimize:
        st.caption("✅ **الضبط التلقائي مفعّل:** سيتم حساب عتبة الصمت (dBFS) وهامش الأمان وحجم نموذج Whisper تلقائياً فور رفع الملف.")
        silence_threshold = -38.0
        chunk_size = 10
        padding_ms = 110
        whisper_model_choice = "small"
    else:
        silence_threshold = st.slider("عتبة الصمت (dBFS)", min_value=-60.0, max_value=-15.0, value=-38.0, step=1.0)
        chunk_size = st.slider("دقة الفحص (Chunk Size ms)", min_value=5, max_value=50, value=10, step=5)
        padding_ms = st.slider("هامش الأمان قبل وبعد الكلام (ms)", min_value=0, max_value=300, value=110, step=10)
        whisper_model_choice = st.selectbox(
            "حجم نموذج Whisper المحلي:",
            options=["tiny", "base", "small", "medium", "large-v3"],
            index=2
        )

    ollama_model_choice = st.text_input("نموذج Ollama المحلي (عند عدم توفر إنترنت):", value="llama3")
    manim_quality_choice = st.selectbox(
        "دقة رندرة الموشن الهندسي (Manim):",
        options=["-qh (1080p عالية)", "-qm (720p متوسطة)", "-ql (480p سريعة)"],
        index=0
    )
    manim_flag = manim_quality_choice.split()[0]


# ==============================================================================
# 4. القسم الرئيسي: رفع ملف (فيديو / صوت بكافة الصيغ) أو تسجيل صوتي مباشر
# ==============================================================================
col1, col2 = st.columns([1.08, 1.0], gap="large")

with col1:
    st.subheader("1. رفع الفيديو أو الملف الصوتي / تسجيل مباشر")

    tab_upload, tab_record = st.tabs([
        "📁 رفع ملف (فيديو أو صوت بجميع الصيغ)",
        "🎙️ تسجيل صوتي مباشر من المايكروفون"
    ])

    raw_media_bytes = None
    raw_media_name = None

    with tab_upload:
        allow_any_ext = st.checkbox(
            "🔓 السماح برفع أي ملف بدون تقييد المتصفح (فعّل هذا الخيار إذا كان هاتفك لا يرفع التسجيلات الصوتية)",
            value=False
        )
        uploaded_file = st.file_uploader(
            "اختر ملف فيديو (MP4, MOV, MKV...) أو ملف/تسجيل صوتي (MP3, WAV, M4A, OGG, OPUS, AAC, AMR, WEBM...)",
            type=None if allow_any_ext else ALL_SUPPORTED_EXTENSIONS,
            help="يدعم جميع صيغ الفيديو والتسجيلات الصوتية من الهواتف وواتساب وتيليجرام."
        )
        if uploaded_file is not None:
            raw_media_bytes = uploaded_file.getvalue()
            raw_media_name = uploaded_file.name

    with tab_record:
        st.caption("سجّل صوتك مباشرة من المتصفح بالدارجة الجزائرية أو العربية ليتم تحويله فوراً إلى فيديو موشن جرافيك:")
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

        if not os.path.exists(saved_input_path):
            with open(saved_input_path, "wb") as f:
                f.write(raw_media_bytes)

        playable_path, is_vid = ensure_playable_audio_or_video(saved_input_path, INPUTS_DIR)
        active_input_path = playable_path

        cache_analysis_key = f"analysis_{file_hash}"
        if cache_analysis_key not in st.session_state:
            with st.spinner("🔍 جاري فحص الملف وتحليل خصائص الصوت والفيديو تلقائياً..."):
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

        with st.expander("📊 تقرير التحليل الذكي للملف والإعدادات التلقائية المختارة", expanded=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("متوسط الصوت", f"{media_analysis['mean_dbfs']} dBFS")
            m2.metric("عتبة الصمت المثلى", f"{media_analysis['optimal_silence_threshold']} dBFS")
            m3.metric("نسبة الصمت", f"{media_analysis['silence_percent']}%")
            m4.metric("موديل التفريغ", media_analysis["optimal_whisper_model"].upper())

            st.markdown("**📌 المعايير التي استند إليها المحلل الذكي:**")
            for reason in media_analysis.get("criteria_reasons", []):
                st.markdown(f"- {reason}")

with col2:
    st.subheader("2. اختيار نمط الإخراج والموشن جرافيك")

    style_options = [
        "✨ النمط التلقائي الذكي - يدمج كل الأدوار بمعايير علمية (Smart Director All-in-One)",
        "🎨 دمج الموشن جرافيك بالفيديو الأصلي (Motion Graphics Overlay on Video)",
        "🚀 موشن جرافيك نصي وأنفوجرافيك احترافي (Studio Kinetic Typography)",
        "📐 موشن جرافيك هندسي ذكي (Manim + AI Infographics)",
        "🔍 مونتاج ديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)",
        "✂️ قص الصمت وتنظيف الصوت فقط (Smart Jump-cuts)"
    ]

    selected_style = st.selectbox(
        "اختر أسلوب المونتاج المطلوب:",
        options=style_options,
        index=0
    )

    if selected_style == style_options[0]:
        st.info(
            "🧠 **المخرج الذكي الشامل (All-in-One):** لا يختار بشكل عشوائي، بل يحلل كل جملة في الفيديو أو الصوت "
            "ويوزع الأدوار تلقائياً: يقص الصمت بعتبة مُعايرة، يطبق الزوم السينمائي، يدمج بطاقات الموشن جرافيك والأيقونات الفيكتور "
            "في الجمل المهمة، ويضيف كابشن الدارجة الجزائرية/العربية المتزامن."
        )
    elif selected_style == style_options[1]:
        st.info(
            "🎨 **دمج الموشن جرافيك بالفيديو الأصلي:** يحافظ على الفيديو الأصلي للمتحدث مع قص الصمت، "
            "ويضيف فوقه بطاقات أنفوجرافيك زجاجية، أيقونات فيكتور مرسومة بالذكاء الاصطناعي لكل فكرة، وكابشن تفاعلي في الثلث السفلي."
        )
    elif selected_style == style_options[2]:
        st.info(
            "🚀 **موشن جرافيك نصي وأنفوجرافيك متكامل:** مثالي للتسجيلات الصوتية والفيديوهات القصيرة؛ يصنع خلفية أستوديو "
            "متعددة الثيمات مع أيقونات فيكتور ديناميكية، شارة عنوان علوي، وبطاقات كلمات مضيئة مع سياق الجملة."
        )
    elif selected_style == style_options[3]:
        st.info(
            "📐 **موشن جرافيك هندسي (Manim + AI):** يولد مشاهد هندسية ومخططات بيانية وشبكات ذكية متحركة تعبر عن محتوى الكلام "
            "باستخدام الذكاء الاصطناعي السحابي/المحلي مع دمج الصوت والكابشن العربي."
        )
    elif selected_style == style_options[4]:
        st.info(
            "🔍 **مونتاج ديناميكي سريع:** يطبق قص الصمت مع تقريب الكاميرا (15% Auto-Zoom) بالتناوب بين الجمل "
            "وكابشن تيك توك الأصفر الساطع (يعمل الآن على الفيديوهات والملفات الصوتية معاً!)."
        )
    elif selected_style == style_options[5]:
        st.info(
            "✂️ **قص الصمت الذكي:** يكتشف فترات التوقف والضوضاء الخلفية ويحذفها بدقة ملي-ثانية مع تنقية مستوى الصوت."
        )

    st.markdown("<br>", unsafe_allow_html=True)
    start_btn = st.button("🚀 بدء المعالجة وصناعة الفيديو (Start Processing)", use_container_width=True)


# ==============================================================================
# 5. منطق المعالجة والتنفيذ عند الضغط على الزر
# ==============================================================================
if start_btn:
    if active_input_path is None or not os.path.exists(active_input_path):
        st.warning("⚠️ يرجى رفع ملف فيديو أو صوت (أو تسجيل صوتك من التبويب الثاني) أولاً قبل بدء المعالجة.")
    else:
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
        only_silence_cut = (selected_style == style_options[5])
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
            with st.spinner("🎬 جاري تشغيل محرك المونتاج والموشن جرافيك الذكي..."):
                if selected_style == style_options[0]:
                    from dynamic_edit import apply_smart_director_all_in_one

                    processed_path, final_analysis = apply_smart_director_all_in_one(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        media_analysis=media_analysis,
                        whisper_model=eff_whisper_model,
                        ollama_model=ollama_model_choice,
                        dialect_mode=dialect_mode,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key,
                        progress_callback=update_ui_progress
                    )

                elif selected_style == style_options[1]:
                    from dynamic_edit import apply_motion_overlay_on_video

                    processed_path = apply_motion_overlay_on_video(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        silence_threshold=eff_silence_thresh,
                        chunk_size=eff_chunk_size,
                        padding_ms=eff_padding_ms,
                        whisper_model=eff_whisper_model,
                        ollama_model=ollama_model_choice,
                        dialect_mode=dialect_mode,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key,
                        progress_callback=update_ui_progress
                    )

                elif selected_style == style_options[2]:
                    from motion_text import create_kinetic_typography_video

                    processed_path = create_kinetic_typography_video(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        whisper_model=eff_whisper_model,
                        ollama_model=ollama_model_choice,
                        dialect_mode=dialect_mode,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key,
                        progress_callback=update_ui_progress
                    )

                elif selected_style == style_options[3]:
                    from manim_generator import generate_manim_motion_graphics

                    processed_path = generate_manim_motion_graphics(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        whisper_model=eff_whisper_model,
                        ollama_model=ollama_model_choice,
                        quality_flag=manim_flag,
                        dialect_mode=dialect_mode,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key,
                        progress_callback=update_ui_progress
                    )

                elif selected_style == style_options[4]:
                    from dynamic_edit import apply_dynamic_edit

                    processed_path = apply_dynamic_edit(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        silence_threshold=eff_silence_thresh,
                        chunk_size=eff_chunk_size,
                        padding_ms=eff_padding_ms,
                        zoom_factor=1.15,
                        whisper_model=eff_whisper_model,
                        dialect_mode=dialect_mode,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key,
                        progress_callback=update_ui_progress
                    )

                else:
                    processed_path = remove_silence(
                        input_path=active_input_path,
                        output_path=output_file_path,
                        silence_threshold=eff_silence_thresh,
                        chunk_size=eff_chunk_size,
                        padding_ms=eff_padding_ms,
                        progress_callback=update_ui_progress
                    )

                st.success("🎉 اكتملت صناعة ورندرة العمل النهائي بنجاح!")
                st.markdown("### 🎬 النتيجة النهائية:")
                if processed_path.lower().endswith((".mp3", ".wav", ".ogg", ".m4a")):
                    st.audio(processed_path)
                    mime_type = "audio/mpeg"
                else:
                    st.video(processed_path)
                    mime_type = "video/mp4"

                with open(processed_path, "rb") as file_bytes:
                    st.download_button(
                        label="📥 تحميل الملف النهائي بجودة كاملة",
                        data=file_bytes,
                        file_name=os.path.basename(processed_path),
                        mime=mime_type,
                        use_container_width=True
                    )

        except Exception as err:
            st.error(f"❌ حدث خطأ أثناء المعالجة: {str(err)}")

        finally:
            cleanup_temp_directory(TEMP_DIR)
            update_ui_progress(1.0, "تم تنظيف الملفات المؤقتة وإتمام دورة المعالجة بنجاح.")
