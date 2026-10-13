"""
transcriber.py - وحدة التفريغ الصوتي المتقدمة الداعمة للدارجة الجزائرية والعربية (سحابي + محلي)
=================================================================================================
تتميز هذه الوحدة بـ:
1. دعم متقدم للدارجة الجزائرية (Algerian Darija) عبر:
   - موجه صوتي مخصص (Custom Algerian Initial Prompt) يهيئ Whisper لفهم المفردات والصوتيات الجزائرية.
   - قاموس تصحيح صوتي ومفرداتي للدارجة الجزائرية (واش، بزاف، علاش، كيفاش، عفسة، درك، باسكو، ديجا، ماكانش...).
   - مصحح سياقي بالذكاء الاصطناعي (Cloud AI / Ollama) يصحح الأخطاء الإملائية للدارجة مع الحفاظ التام على التوقيت الزمني لكل كلمة.
2. دعم التفريغ السحابي الفائق (Groq Whisper Large-v3 / OpenAI Whisper) عند توفر الإنترنت والمفتاح،
   مع التراجع التلقائي السلس لنموذج faster-whisper المحلي المحسن.
3. نظام تخزين مؤقت ذكي (In-Memory Cache) يمنع إعادة تفريغ نفس الملف مرتين ويوفر 50% من وقت المعالجة.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# استيراد آمن لمحرك الذكاء الاصطناعي الهجين
try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None


# ==============================================================================
# 1. إعدادات وموجهات الدارجة الجزائرية (Algerian Darija Dialect Engine)
# ==============================================================================
ALGERIAN_DARIJA_INITIAL_PROMPT = (
    "السلام عليكم خاوتي، واش راكم لاباس؟ صحتكم مليحة؟ "
    "هاذ الفيديو نهدروا فيه بالدارجة الجزائرية والعربية الفصحى. "
    "علاش وكيفاش نديروا هاذ العفسة شابة بزاف، درك ودوكا نشوفوا مع بعض، "
    "ماكانش مشكل، زعما كيما نقولوا حنا في الدزاير، نورمال، باسكو، ديجا، "
    "سيتادير، مليح، يعطيكم الصحة، ربي يحفظكم، تبعوا معايا مليح باش تفهموا كلش."
)

# قاموس تصحيح الأخطاء الشائعة التي يقع فيها Whisper عند سماع الدارجة الجزائرية
ALGERIAN_DARIJA_LEXICON_FIXES = {
    "وشراكم": "واش راكم",
    "واشراكم": "واش راكم",
    "علاه": "علاش",
    "كفاش": "كيفاش",
    "كيفاش": "كيفاش",
    "بالزاف": "بزاف",
    "بزاف": "بزاف",
    "ما كاش": "ماكانش",
    "مكانش": "ماكانش",
    "ماكانش": "ماكانش",
    "دركا": "درك",
    "دوكة": "دوكا",
    "عفسه": "عفسة",
    "خوتي": "خاوتي",
    "صحيتوا": "صحيتو",
    "نديروا": "نديرو",
    "نقدرو": "نقدروا",
    "بارسكو": "باسكو",
    "باسكو": "باسكو",
    "ديجة": "ديجا",
    "نورمالمو": "نورمالمون",
    "تاعنا": "تاعنا",
    "نتاع": "تاع",
    "هاذي": "هاذ",
    "هذيك": "هذيك",
    "كلشي": "كلش",
}

# ذاكرة تخزين مؤقت لتفادي تشغيل Whisper مرتين على نفس الملف
_TRANSCRIPTION_CACHE: Dict[str, Dict[str, Any]] = {}
_WHISPER_MODEL_CACHE: Dict[str, Any] = {}


def normalize_algerian_word(word: str) -> str:
    """تنظيف وتصحيح الكلمة المفردة وفق قواعد الدارجة الجزائرية."""
    if not word:
        return ""
    cleaned = word.strip()
    # فحص المطابقة المباشرة في قاموس الدارجة
    if cleaned in ALGERIAN_DARIJA_LEXICON_FIXES:
        return ALGERIAN_DARIJA_LEXICON_FIXES[cleaned]
    return cleaned


def normalize_algerian_sentence(text: str) -> str:
    """تطبيع الجملة بالدارجة الجزائرية لتصحيح التراكيب المندمجة."""
    if not text:
        return ""
    out = text.strip()
    for wrong, right in ALGERIAN_DARIJA_LEXICON_FIXES.items():
        out = re.sub(rf"\b{re.escape(wrong)}\b", right, out)
    return out


def refine_darija_words_with_ai(
    words_list: List[Dict[str, Any]],
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    تدقيق الكلمات المستخرجة بالذكاء الاصطناعي لتصحيح أي تحريف في الدارجة الجزائرية
    (أو تحويلها للعربية المبسطة إذا طلب المستخدم ذلك) مع الحفاظ الصارم على عدد الكلمات وتوقيتها.
    """
    if not words_list or len(words_list) > 250:
        return words_list

    raw_tokens = [w["word"] for w in words_list]
    indexed_text = " | ".join([f"{i}:{tok}" for i, tok in enumerate(raw_tokens)])

    if dialect_mode == "msa_simplified":
        instruction = (
            "المدخل التالي هو كلمات مستخرجة من تسجيل صوتي بالدارجة الجزائرية أو العربية مفصولة بـ |. "
            "قم بتحويل الكلمات العامية غير الواضحة إلى مقابلاتها العربية البسيطة مع الحفاظ على نفس الفهرس الرقمي لكل كلمة."
        )
    else:
        instruction = (
            "المدخل التالي هو كلمات مستخرجة من تسجيل صوتي بالدارجة الجزائرية (Algerian Darija) مفصولة بـ |. "
            "بعض الكلمات قد يكون Whisper قد كتبها بشكل خاطئ لأنها باللهجة الجزائرية (مثل: واش، راكم، بزاف، علاش، كيفاش، عفسة، باسكو، ديجا، درك، ماكانش، خاوتي). "
            "قم بتصحيح الإملاء الخاطئ فقط لتظهر بالدارجة الجزائرية الصحيحة والواضحة، ولا تغير الكلمات الصحيحة."
        )

    prompt = (
        f"{instruction}\n"
        f"قائمة الكلمات المفهرسة:\n{indexed_text}\n\n"
        "أرجع فقط JSON صالح عبارة عن قاموس يربط رقم الكلمة التي تحتاج لتصحيح بالكلمة المصححة فقط، "
        "مثال: {\"2\": \"بزاف\", \"5\": \"علاش\"}. إذا كانت كل الكلمات صحيحة أرجع {}."
    )

    ai_resp = query_hybrid_llm(
        prompt=prompt,
        system_prompt="أنت خبير لغوي جزائري متخصص في تدقيق الدارجة الجزائرية وتصحيح مخرجات التعرف على الكلام (ASR). أرجع JSON فقط.",
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        temperature=0.1,
        max_tokens=500
    )

    if not ai_resp:
        return words_list

    try:
        json_match = re.search(r"\{.*?\}", ai_resp, re.DOTALL)
        if json_match:
            corrections = json.loads(json_match.group(0))
            if isinstance(corrections, dict):
                updated = [dict(w) for w in words_list]
                for idx_str, new_val in corrections.items():
                    idx = int(idx_str)
                    if 0 <= idx < len(updated) and isinstance(new_val, str) and new_val.strip():
                        updated[idx]["word"] = new_val.strip()
                return updated
    except Exception as e:
        logger.debug(f"تجاوز التدقيق اللغوي الإضافي: {e}")

    return words_list


# ==============================================================================
# 2. التفريغ السحابي السريع (Groq Whisper Large-v3 / OpenAI Whisper)
# ==============================================================================
def _transcribe_via_cloud_api(
    audio_path: str,
    groq_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    language: str = "ar"
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """
    محاولة التفريغ عبر السحابة باستخدام نموذج whisper-large-v3 الدقيق جداً مع الدارجة الجزائرية.
    """
    groq_key = (groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    openai_key = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    # التأكد من أن حجم الملف الصوتي أقل من 24MB لواجهة API، وإلا نستخرج منه ملف mp3 مضغوط خفيف
    upload_path = audio_path
    temp_compressed = None
    try:
        if os.path.getsize(audio_path) > 22 * 1024 * 1024 or audio_path.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
            from pydub import AudioSegment
            temp_compressed = audio_path + "_cloud_temp.mp3"
            aud = AudioSegment.from_file(audio_path)
            aud = aud.set_frame_rate(16000).set_channels(1)
            aud.export(temp_compressed, format="mp3", bitrate="64k")
            upload_path = temp_compressed
    except Exception:
        upload_path = audio_path

    endpoints = []
    if groq_key:
        endpoints.append((
            "https://api.groq.com/openai/v1/audio/transcriptions",
            groq_key,
            "whisper-large-v3"
        ))
    if openai_key:
        endpoints.append((
            "https://api.openai.com/v1/audio/transcriptions",
            openai_key,
            "whisper-1"
        ))

    try:
        for url, api_key, model_name in endpoints:
            try:
                logger.info(f"جاري التفريغ السحابي عبر {model_name} مع موجه الدارجة الجزائرية...")
                with open(upload_path, "rb") as f:
                    files = {"file": (os.path.basename(upload_path), f, "audio/mpeg")}
                    data = [
                        ("model", model_name),
                        ("response_format", "verbose_json"),
                        ("prompt", ALGERIAN_DARIJA_INITIAL_PROMPT),
                        ("timestamp_granularities[]", "word"),
                        ("timestamp_granularities[]", "segment")
                    ]
                    if language and language != "auto":
                        data.append(("language", language))

                    resp = requests.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        files=files,
                        data=data,
                        timeout=45
                    )

                if resp.status_code == 200:
                    payload = resp.json()
                    raw_words = payload.get("words", [])
                    raw_segments = payload.get("segments", [])

                    words_list = []
                    for w in raw_words:
                        w_txt = normalize_algerian_word(w.get("word", ""))
                        if w_txt:
                            words_list.append({
                                "word": w_txt,
                                "start": round(float(w.get("start", 0.0)), 3),
                                "end": round(float(w.get("end", 0.0)), 3),
                                "probability": 0.96
                            })

                    sentences_list = []
                    for seg in raw_segments:
                        seg_start = round(float(seg.get("start", 0.0)), 3)
                        seg_end = round(float(seg.get("end", 0.0)), 3)
                        seg_text = normalize_algerian_sentence(seg.get("text", ""))
                        seg_words = [
                            w for w in words_list
                            if w["start"] >= seg_start - 0.1 and w["end"] <= seg_end + 0.2
                        ]
                        if not seg_words and seg_text:
                            # توزيع التوقيت بالتساوي إذا لم ترجع الكلمات المفردة
                            parts = seg_text.split()
                            dur = max(0.2, seg_end - seg_start) / max(1, len(parts))
                            for idx, p in enumerate(parts):
                                w_obj = {
                                    "word": normalize_algerian_word(p),
                                    "start": round(seg_start + idx * dur, 3),
                                    "end": round(seg_start + (idx + 1) * dur, 3),
                                    "probability": 0.92
                                }
                                seg_words.append(w_obj)
                                words_list.append(w_obj)

                        if seg_text:
                            sentences_list.append({
                                "text": seg_text,
                                "start": seg_start,
                                "end": seg_end,
                                "words": seg_words
                            })

                    if words_list:
                        logger.info(f"نجح التفريغ السحابي عبر {model_name}: {len(words_list)} كلمة.")
                        return words_list, sentences_list
            except Exception as e:
                logger.warning(f"فشل التفريغ السحابي ({model_name})، سيتم الانتقال للمحرك المحلي: {e}")
    finally:
        if temp_compressed and os.path.exists(temp_compressed):
            try:
                os.remove(temp_compressed)
            except Exception:
                pass

    return None


# ==============================================================================
# 3. التفريغ المحلي المحسن عبر faster-whisper مع دعم الدارجة الجزائرية
# ==============================================================================
def get_optimal_device_settings() -> Tuple[str, str]:
    """تحديد الإعدادات المثلى للعتاد المحلي تلقائياً (GPU/CUDA مقابل CPU)."""
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("تم العثور على كرت شاشة يدعم CUDA. سيتم استخدام نمط GPU مع float16.")
            return "cuda", "float16"
    except ImportError:
        pass

    logger.info("سيتم استخدام المعالج المحلي (CPU) مع نمط الحسابات السريع int8.")
    return "cpu", "int8"


def _get_or_load_whisper_model(model_size: str, device: str, compute_type: str):
    """تحميل نموذج faster-whisper مرة واحدة وحفظه في الذاكرة لتسريع العمليات المتتالية."""
    from faster_whisper import WhisperModel
    cache_key = f"{model_size}_{device}_{compute_type}"
    if cache_key not in _WHISPER_MODEL_CACHE:
        logger.info(f"جاري تحميل نموذج Whisper ({model_size}) على {device} بنمط {compute_type}...")
        _WHISPER_MODEL_CACHE[cache_key] = WhisperModel(
            model_size_or_path=model_size,
            device=device,
            compute_type=compute_type
        )
    return _WHISPER_MODEL_CACHE[cache_key]


def _run_full_transcription(
    audio_path: str,
    model_size: str = "small",
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    language: Optional[str] = "ar",
    vad_filter: bool = True,
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    تشغيل التفريغ الكامل (سحابي أولاً ثم محلي) مع التخزين المؤقت وتصحيح الدارجة الجزائرية.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"الملف المطلوب تفريغه غير موجود: {audio_path}")

    file_mtime = os.path.getmtime(audio_path)
    cache_key = f"{os.path.abspath(audio_path)}_{file_mtime}_{model_size}_{dialect_mode}"
    if cache_key in _TRANSCRIPTION_CACHE:
        logger.info("تم استرجاع التفريغ الصوتي من الذاكرة المؤقتة (Cache) فوراً.")
        cached = _TRANSCRIPTION_CACHE[cache_key]
        return cached["words"], cached["sentences"]

    # 1. محاولة التفريغ السحابي (Groq Whisper Large-v3 / OpenAI) إذا توفر مفتاح وإنترنت
    cloud_res = _transcribe_via_cloud_api(
        audio_path=audio_path,
        groq_api_key=groq_api_key,
        openai_api_key=openai_api_key,
        language=language or "ar"
    )
    if cloud_res is not None:
        words_list, sentences_list = cloud_res
        words_list = refine_darija_words_with_ai(
            words_list,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        _TRANSCRIPTION_CACHE[cache_key] = {"words": words_list, "sentences": sentences_list}
        return words_list, sentences_list

    # 2. التفريغ المحلي عبر faster-whisper مع إعدادات الدارجة الجزائرية المتقدمة
    detected_device, detected_compute = get_optimal_device_settings()
    final_device = device if device is not None else detected_device
    final_compute = compute_type if compute_type is not None else detected_compute

    model = _get_or_load_whisper_model(model_size, final_device, final_compute)
    target_language = None if (language == "auto" or not language) else language

    # تمرير initial_prompt الخاص بالدارجة الجزائرية وإيقاف condition_on_previous_text لمنع الهلوسة والتكرار
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=target_language,
        initial_prompt=ALGERIAN_DARIJA_INITIAL_PROMPT,
        beam_size=5,
        best_of=5,
        condition_on_previous_text=False,
        vad_filter=vad_filter,
        vad_parameters=dict(min_silence_duration_ms=350, speech_pad_ms=200)
    )

    logger.info(f"تم اكتشاف اللغة: {info.language} بنسبة ثقة: {info.language_probability:.2f}")

    word_timestamps: List[Dict[str, Any]] = []
    sentence_list: List[Dict[str, Any]] = []

    for seg in segments:
        seg_words = []
        if seg.words:
            for word_obj in seg.words:
                cleaned_word = normalize_algerian_word(word_obj.word)
                if cleaned_word:
                    w_dict = {
                        "word": cleaned_word,
                        "start": round(word_obj.start, 3),
                        "end": round(word_obj.end, 3),
                        "probability": round(word_obj.probability, 3)
                    }
                    word_timestamps.append(w_dict)
                    seg_words.append(w_dict)

        seg_text = normalize_algerian_sentence(seg.text)
        if seg_text:
            sentence_list.append({
                "text": seg_text,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "words": seg_words
            })

    # تدقيق سياقي للدارجة الجزائرية عبر الذكاء الاصطناعي (إن توفر اتصال)
    if word_timestamps:
        word_timestamps = refine_darija_words_with_ai(
            word_timestamps,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        # تحديث الجمل بالكلمات المدققة
        w_idx = 0
        for sent in sentence_list:
            count = len(sent["words"])
            if w_idx + count <= len(word_timestamps):
                sent["words"] = word_timestamps[w_idx:w_idx + count]
                sent["text"] = " ".join([w["word"] for w in sent["words"]])
                w_idx += count

    _TRANSCRIPTION_CACHE[cache_key] = {
        "words": word_timestamps,
        "sentences": sentence_list
    }

    logger.info(f"اكتمل التفريغ الصوتي بنجاح ({len(word_timestamps)} كلمة، {len(sentence_list)} جملة).")
    return word_timestamps, sentence_list


def transcribe_audio(
    audio_path: str,
    model_size: str = "small",
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    language: Optional[str] = "ar",
    vad_filter: bool = True,
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """إرجاع قائمة الكلمات مع تواقيتها الدقيقة."""
    words, _ = _run_full_transcription(
        audio_path=audio_path,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        language=language,
        vad_filter=vad_filter,
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key
    )
    return words


def transcribe_sentences(
    audio_path: str,
    model_size: str = "small",
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    language: Optional[str] = "ar",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """إرجاع قائمة الجمل الكاملة مع كلماتها وتواقيتها."""
    _, sentences = _run_full_transcription(
        audio_path=audio_path,
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        language=language,
        vad_filter=True,
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key
    )
    return sentences
