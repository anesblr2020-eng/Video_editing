"""
app.py - الواجهة التفاعلية لنظام أتمتة تحرير الفيديو والموشن جرافيك
==================================================================
نظام متكامل ومجاني 100% يعمل محلياً بالكامل لتحرير الفيديوهات وصناعة الموشن جرافيك:
- النمط 1: قص الصمت وتنظيف الصوت فقط (Jump-cuts)
- النمط 2: مونتاج ديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)
- النمط 3: موشن جرافيك نصي (Kinetic Typography)
- النمط 4: موشن جرافيك هندسي (Manim + Ollama)
"""

import sys
import os

# إضافة مسار المجلد الحالي إلى أولويات البحث لضمان تعرف كل ملف على الملفات المجاورة في الاستضافة
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)


import os
import shutil
import time
import streamlit as st

# استيراد وحدة قص الصمت والتحقق من نوع الملف
from auto_cut import remove_silence, is_video_file

# ==============================================================================
# 1. إعداد مسارات المجلدات وضمان وجودها تلقائياً
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUTS_DIR = os.path.join(BASE_DIR, "inputs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ICONS_DIR = os.path.join(BASE_DIR, "assets", "icons")

REQUIRED_DIRS = [INPUTS_DIR, OUTPUTS_DIR, TEMP_DIR, ICONS_DIR]

for directory in REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)


def cleanup_temp_directory(temp_path: str = TEMP_DIR):
    """
    تنظيف مجلد temp بالكامل بعد اكتمال المعالجة أو عند حدوث أي خطأ،
    لضمان عدم استهلاك مساحة القرص بالملفات المؤقتة.
    """
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
# 2. إعدادات واجهة Streamlit
# ==============================================================================
st.set_page_config(
    page_title="محرر الفيديو الذكي والموشن جرافيك المحلي",
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
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        color: #78909C;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3.2rem;
        font-size: 1.1rem;
        font-weight: bold;
        background-color: #1E88E5;
        color: white;
    }
    .stButton>button:hover {
        background-color: #1565C0;
        border-color: #1565C0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🎬 نظام أتمتة المونتاج والموشن جرافيك المحلي</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">تحرير الفيديوهات تلقائياً بالذكاء الاصطناعي وبدون اتصال بالإنترنت</div>', unsafe_allow_html=True)

# ==============================================================================
# 3. الشريط الجانبي: إعدادات متقدمة
# ==============================================================================
with st.sidebar:
    st.header("⚙️ إعدادات التحكم")
    st.markdown("---")
    
    st.subheader("إعدادات عتبة الصوت (Silence Cut)")
    silence_threshold = st.slider(
        "عتبة الصمت (dBFS)",
        min_value=-60.0,
        max_value=-15.0,
        value=-40.0,
        step=1.0,
        help="الأصوات ذات الديسيبل الأقل من هذه القيمة سيتم حذفها."
    )
    
    chunk_size = st.slider(
        "دقة الفحص (Chunk Size بالملي ثانية)",
        min_value=5,
        max_value=50,
        value=10,
        step=5,
        help="كلما صغرت القيمة زادت الدقة واستغرقت وقتاً أطول قليلاً."
    )
    
    padding_ms = st.slider(
        "هامش الأمان قبل وبعد الكلام (ملي ثانية)",
        min_value=0,
        max_value=300,
        value=100,
        step=20,
        help="يحمي أطراف الكلمات من البتر المفاجئ لضمان طبيعية تدفق الكلام."
    )
    
    st.markdown("---")
    st.subheader("إعدادات نموذج التفريغ (Whisper)")
    whisper_model_choice = st.selectbox(
        "حجم نموذج faster-whisper:",
        options=["tiny", "base", "small", "medium"],
        index=2,
        help="النموذج 'small' يوفر توازناً مثالياً بين الدقة والسرعة المحلية."
    )

    st.markdown("---")
    st.subheader("إعدادات الذكاء الاصطناعي المحلي (Ollama)")
    ollama_model_choice = st.text_input("اسم نموذج Ollama:", value="llama3")

    st.subheader("جودة رندرة Manim")
    manim_quality_choice = st.selectbox(
        "دقة فيديو Manim:",
        options=["-qh (1080p عالية)", "-qm (720p متوسطة)", "-ql (480p سريعة)"],
        index=0
    )
    manim_flag = manim_quality_choice.split()[0]

    st.markdown("---")
    st.info("💡 **ملاحظة:** يتم تشغيل كافة النماذج محلياً بنسبة 100% دون إرسال أي بيانات لخوادم خارجية.")

# ==============================================================================
# 4. جسم الصفحة الرئيسي: رفع الملف واختيار نمط المونتاج
# ==============================================================================
col1, col2 = st.columns([1, 1], gap="medium")

with col1:
    st.subheader("1. رفع الملف المصدر")
    uploaded_file = st.file_uploader(
        "اختر ملف فيديو (MP4) أو ملف صوت (MP3)",
        type=["mp4", "mp3", "wav", "mov", "m4a"],
        help="يدعم النظام جميع صيغ الفيديو والصوت الشائعة."
    )

    if uploaded_file is not None:
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext in [".mp4", ".mov"]:
            st.video(uploaded_file)
        else:
            st.audio(uploaded_file)

with col2:
    st.subheader("2. تخصيص نمط المونتاج")
    
    style_options = [
        "قص الصمت وتنظيف الصوت فقط (Jump-cuts)",
        "مونتاج ديناميكي (Auto-Zoom + Jump-cuts)",
        "موشن جرافيك نصي (Kinetic Typography)",
        "موشن جرافيك هندسي (Manim)"
    ]
    
    selected_style = st.selectbox(
        "اختر أسلوب المونتاج المطلوب:",
        options=style_options,
        index=0
    )
    
    if selected_style == style_options[0]:
        st.caption("✂️ يكتشف فترات التوقف والصمت، ويقوم بقصها بدقة متناهية مع الاحتفاظ بنقاء الصوت وتدفق الأفكار.")
    elif selected_style == style_options[1]:
        st.caption("🔍 يطبق تقريب ديناميكي (15% Auto-Zoom) مع كل جملة جديدة، بالإضافة لطباعة نصوص التيك توك التفاعلية الصفراء في المنتصف.")
    elif selected_style == style_options[2]:
        st.caption("🎨 خلفية تدرج لوني سينمائية مع نصوص متحركة Pop-up وكلمات مفتاحية مستخرجة محلياً عبر Llama 3 وأيقونات من assets/icons/.")
    elif selected_style == style_options[3]:
        st.caption("📐 توليد رسوم هندسية وموشن تعليمي تلقائي عبر Manim بواسطة كود برمجي يصنعه Llama 3 محلياً مع دمج الصوت الأصلي.")

    st.markdown("<br>", unsafe_allow_html=True)
    start_btn = st.button("🚀 Start Processing (بدء المعالجة)", use_container_width=True)

# ==============================================================================
# 5. منطق المعالجة والتنفيذ عند الضغط على الزر
# ==============================================================================
if start_btn:
    if uploaded_file is None:
        st.warning("⚠️ يرجى رفع ملف فيديو أو صوت أولاً قبل بدء المعالجة.")
    else:
        # حفظ الملف في مجلد inputs/
        timestamp_prefix = int(time.time())
        clean_file_name = f"{timestamp_prefix}_{uploaded_file.name}"
        input_file_path = os.path.join(INPUTS_DIR, clean_file_name)
        
        with open(input_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        base_name, ext = os.path.splitext(clean_file_name)
        # للفيديوهات المولدة (الموشن) نضمن تصدير mp4 دائماً
        target_ext = ".mp4" if selected_style != "قص الصمت وتنظيف الصوت فقط (Jump-cuts)" and not is_video_file(input_file_path) else ext
        output_file_name = f"processed_{base_name}{target_ext}"
        output_file_path = os.path.join(OUTPUTS_DIR, output_file_name)

        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_ui_progress(percent: float, text: str):
            progress_bar.progress(percent)
            status_text.markdown(f"**الحالة:** {text}")

        try:
            with st.spinner("جاري تنفيذ العمليات الحسابية والمعالجة..."):
                # النمط 1: قص الصمت فقط
                if selected_style == "قص الصمت وتنظيف الصوت فقط (Jump-cuts)":
                    update_ui_progress(0.05, "بدء وحدة قص الصمت التلقائي...")
                    
                    processed_path = remove_silence(
                        input_path=input_file_path,
                        output_path=output_file_path,
                        silence_threshold=silence_threshold,
                        chunk_size=chunk_size,
                        padding_ms=padding_ms,
                        progress_callback=update_ui_progress
                    )
                    
                    st.success("🎉 تم الانتهاء من قص الصمت وإخراج العمل بنجاح!")
                    st.markdown("### النتيجة النهائية:")
                    if is_video_file(processed_path):
                        st.video(processed_path)
                    else:
                        st.audio(processed_path)

                    with open(processed_path, "rb") as file_bytes:
                        st.download_button(
                            label="📥 تحميل الملف النهائي",
                            data=file_bytes,
                            file_name=os.path.basename(processed_path),
                            mime="video/mp4" if is_video_file(processed_path) else "audio/mpeg",
                            use_container_width=True
                        )

                # النمط 2: المونتاج الديناميكي
                elif selected_style == "مونتاج ديناميكي (Auto-Zoom + Jump-cuts)":
                    update_ui_progress(0.05, "بدء مسار المونتاج الديناميكي التفاعلي...")
                    from dynamic_edit import apply_dynamic_edit

                    processed_path = apply_dynamic_edit(
                        input_path=input_file_path,
                        output_path=output_file_path,
                        silence_threshold=silence_threshold,
                        chunk_size=chunk_size,
                        padding_ms=padding_ms,
                        zoom_factor=1.15,
                        whisper_model=whisper_model_choice,
                        progress_callback=update_ui_progress
                    )

                    st.success("🎉 تم إنجاز المونتاج الديناميكي والكابشن التفاعلي بنجاح!")
                    st.markdown("### النتيجة النهائية:")
                    st.video(processed_path)

                    with open(processed_path, "rb") as file_bytes:
                        st.download_button(
                            label="📥 تحميل الفيديو الديناميكي النهائي",
                            data=file_bytes,
                            file_name=os.path.basename(processed_path),
                            mime="video/mp4",
                            use_container_width=True
                        )

                # النمط 3: الموشن جرافيك النصي (Kinetic Typography)
                elif selected_style == "موشن جرافيك نصي (Kinetic Typography)":
                    update_ui_progress(0.05, "بدء مسار الموشن جرافيك النصي (Kinetic Typography)...")
                    from motion_text import create_kinetic_typography_video

                    processed_path = create_kinetic_typography_video(
                        input_path=input_file_path,
                        output_path=output_file_path,
                        whisper_model=whisper_model_choice,
                        ollama_model=ollama_model_choice,
                        progress_callback=update_ui_progress
                    )

                    st.success("🎉 تم إنتاج فيديو الموشن جرافيك النصي بنجاح!")
                    st.markdown("### النتيجة النهائية:")
                    st.video(processed_path)

                    with open(processed_path, "rb") as file_bytes:
                        st.download_button(
                            label="📥 تحميل فيديو الموشن جرافيك النصي",
                            data=file_bytes,
                            file_name=os.path.basename(processed_path),
                            mime="video/mp4",
                            use_container_width=True
                        )

                # النمط 4: الموشن جرافيك الهندسي (Manim + Ollama)
                elif selected_style == "موشن جرافيك هندسي (Manim)":
                    update_ui_progress(0.05, "بدء مسار الموشن جرافيك الهندسي (Manim + Ollama)...")
                    from manim_generator import generate_manim_motion_graphics

                    processed_path = generate_manim_motion_graphics(
                        input_path=input_file_path,
                        output_path=output_file_path,
                        whisper_model=whisper_model_choice,
                        ollama_model=ollama_model_choice,
                        quality_flag=manim_flag,
                        progress_callback=update_ui_progress
                    )

                    st.success("🎉 تم إنتاج فيديو Manim الهندسي ودمجه مع الصوت بنجاح!")
                    st.markdown("### النتيجة النهائية:")
                    st.video(processed_path)

                    with open(processed_path, "rb") as file_bytes:
                        st.download_button(
                            label="📥 تحميل فيديو Manim النهائي",
                            data=file_bytes,
                            file_name=os.path.basename(processed_path),
                            mime="video/mp4",
                            use_container_width=True
                        )

        except Exception as err:
            st.error(f"❌ حدث خطأ أثناء المعالجة: {str(err)}")

        finally:
            # التنظيف التلقائي لمجلد temp بعد انتهاء الرندرة فوراً
            cleanup_temp_directory(TEMP_DIR)
            update_ui_progress(1.0, "تم تنظيف الملفات المؤقتة وإتمام دورة المعالجة.")
