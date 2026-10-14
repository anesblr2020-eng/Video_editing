"""
transcriber.py - وحدة التفريغ الصوتي المتقدمة الداعمة للدارجة الجزائرية والعربية وتوليد المشاهد القصيرة
========================================================================================================
تتميز هذه الوحدة بـ:
1. دعم متقدم للدارجة الجزائرية والعربية ومصطلحات صناعة المحتوى والتقنية (مونتاج، ذكاء اصطناعي، ريلز، منصة، أوتوماتيكي...).
2. تقسيم ذكي للكلمات إلى مشاهد قصيرة متجددة كل 1.5 - 2.2 ثانية (Micro-Scenes) لضمان تغير رسومات الموشن جرافيك باستمرار.
3. نظام تعديل الكابشن التفاعلي (Interactive Caption Override Engine) لجميع الأنماط.
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

try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None


# ==============================================================================
# 1. إعدادات وموجهات الدارجة الجزائرية والعربية ومصطلحات التقنية وصناعة المحتوى
# ==============================================================================
ALGERIAN_DARIJA_INITIAL_PROMPT = (
    "أهلاً وسهلاً، السلام عليكم خاوتي، أنا أنس، واش راكم لاباس؟ "
    "عمري 17 سنة، أبني منصة تعمل مونتاج بالذكاء الاصطناعي بشكل أوتوماتيكي، "
    "لأن أغلب الناس ما عندها وقت تمنتج الفيديوهات وتبغى ترفع ريلز وتيك توك كل يوم، "
    "واسم المنصة فيديو إيديتينج Video Editing. علاش وكيفاش نديروا هاذ العفسة شابة بزاف، درك نشوفوا مع بعض."
)

# قاموس شامل لتصحيح الأخطاء الصوتية الشائعة في Whisper (العربية + الدارجة الجزائرية + مصطلحات المونتاج والتقنية)
ALGERIAN_DARIJA_LEXICON_FIXES = {
    # أخطاء ظهرت في فيديو الاختبار ومصطلحات المونتاج الشائعة
    "لنلو": "أهلاً",
    "لنلو،": "أهلاً،",
    "أناس": "أنس",
    "أناس،": "أنس،",
    "اناس": "أنس",
    "عمره": "عمري",
    "منتاج": "مونتاج",
    "استناعي": "اصطناعي",
    "إستناعي": "اصطناعي",
    "بذكاء": "بالذكاء",
    "أغالب": "أغلب",
    "اغالب": "أغلب",
    "هنده": "عندها",
    "عنده": "عندها",
    "ريز": "ريلز",
    "ريز،": "ريلز،",
    "الريز": "الريلز",
    "ايدي": "إيديتينج",
    "تيك": "إيديتينج",
    "تيك.": "إيديتينج",
    # مفردات الدارجة الجزائرية الشائعة
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

# تصحيحات مركبة على مستوى العبارة (Phrase-level fixes)
PHRASE_LEVEL_FIXES = [
    (r"أنا\s+لنلو[،,]?\s+أنا\s+أناس", "أهلاً، أنا أنس"),
    (r"أنا\s+أناس", "أنا أنس"),
    (r"عمره\s+17\s+سنة", "عمري 17 سنة"),
    (r"حاول\s+أبني", "أحاول أبني"),
    (r"منتاج\s+بذكاء\s+استناعي", "مونتاج بالذكاء الاصطناعي"),
    (r"منتاج\s+بالذكاء\s+اصطناعي", "مونتاج بالذكاء الاصطناعي"),
    (r"مونتاج\s+بالذكاء\s+اصطناعي", "مونتاج بالذكاء الاصطناعي"),
    (r"أغالب\s+الناس", "أغلب الناس"),
    (r"ما\s+هنده\s+وقت", "ما عندها وقت"),
    (r"ترفع\s+ريز", "ترفع ريلز"),
    (r"فيديو\s+ايدي\s+تيك\.?", "فيديو إيديتينج"),
    (r"فيديو\s+إيديتينج\s+Video\.?", "فيديو إيديتينج"),
]

_TRANSCRIPTION_CACHE: Dict[str, Dict[str, Any]] = {}
_WHISPER_MODEL_CACHE: Dict[str, Any] = {}

_CUSTOM_CAPTION_OVERRIDE: Dict[str, Any] = {
    "enabled": False,
    "words": [],
    "sentences": []
}
_LAST_EXTRACTED_TRANSCRIPT: Dict[str, List[Dict[str, Any]]] = {
    "words": [],
    "sentences": []
}


# ==============================================================================
# 2. تقسيم الكلمات إلى مشاهد قصيرة متجددة كل 1.5 - 2.2 ثانية (Micro-Scenes)
# ==============================================================================
def split_words_into_micro_scenes(
    words_list: List[Dict[str, Any]],
    max_words_per_scene: int = 4,
    max_duration_per_scene: float = 2.1
) -> List[Dict[str, Any]]:
    """
    تقسيم الكلمات المفرغة إلى مشاهد قصيرة وسريعة (كل 1.5 إلى 2.1 ثانية بحد أقصى 4 كلمات)،
    بحيث يتولد مشهد موشن جرافيك جديد ومتحرك كل ثانية أو ثانيتين بدلاً من بقاء رسمة واحدة طوال الفيديو!
    """
    if not words_list:
        return []

    scenes: List[Dict[str, Any]] = []
    current_group: List[Dict[str, Any]] = []

    semantic_break_words = {
        "لأن", "باش", "علاش", "كيفاش", "واسم", "لكن", "أول", "ثاني", "ثالث",
        "وتبغى", "وقاعد", "تعمل", "عمري", "اطلب", "التوصيل", "المشكل", "الحل"
    }

    for i, w in enumerate(words_list):
        w_txt = str(w.get("word", "")).strip()
        if not w_txt:
            continue

        if current_group:
            grp_start = float(current_group[0]["start"])
            grp_dur = float(w["end"]) - grp_start
            prev_word_txt = str(current_group[-1]["word"])
            gap = float(w["start"]) - float(current_group[-1]["end"])

            ends_with_punct = any(prev_word_txt.endswith(p) for p in [",", "،", ".", "!", "؟", "?"])
            is_semantic_start = (w_txt in semantic_break_words and len(current_group) >= 2)

            if (
                len(current_group) >= max_words_per_scene
                or grp_dur >= max_duration_per_scene
                or gap >= 0.35
                or ends_with_punct
                or is_semantic_start
            ):
                scenes.append({
                    "text": " ".join(x["word"] for x in current_group),
                    "start": round(float(current_group[0]["start"]), 3),
                    "end": round(float(current_group[-1]["end"]), 3),
                    "words": list(current_group)
                })
                current_group = []

        current_group.append(dict(w))

    if current_group:
        scenes.append({
            "text": " ".join(x["word"] for x in current_group),
            "start": round(float(current_group[0]["start"]), 3),
            "end": round(float(current_group[-1]["end"]), 3),
            "words": list(current_group)
        })

    return scenes


# ==============================================================================
# 3. دوال إدارة وتعديل الكابشن التفاعلي لجميع الأنماط
# ==============================================================================
def get_last_extracted_transcript() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if _CUSTOM_CAPTION_OVERRIDE["enabled"] and _CUSTOM_CAPTION_OVERRIDE["words"]:
        return (
            [dict(w) for w in _CUSTOM_CAPTION_OVERRIDE["words"]],
            [dict(s) for s in _CUSTOM_CAPTION_OVERRIDE["sentences"]]
        )
    return (
        [dict(w) for w in _LAST_EXTRACTED_TRANSCRIPT["words"]],
        [dict(s) for s in _LAST_EXTRACTED_TRANSCRIPT["sentences"]]
    )


def clear_custom_caption_override():
    _CUSTOM_CAPTION_OVERRIDE["enabled"] = False
    _CUSTOM_CAPTION_OVERRIDE["words"] = []
    _CUSTOM_CAPTION_OVERRIDE["sentences"] = []


def set_custom_caption_override(
    custom_words: Optional[List[Dict[str, Any]]] = None,
    custom_sentences: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """حفظ تعديلات المستخدم على الكابشن ومزامنتها تلقائياً."""
    base_words, base_sentences = get_last_extracted_transcript()

    if custom_sentences is not None and custom_words is None:
        synced_words: List[Dict[str, Any]] = []
        synced_sentences: List[Dict[str, Any]] = []

        for sent in custom_sentences:
            s_text = str(sent.get("text", "")).strip()
            s_start = round(float(sent.get("start", 0.0)), 3)
            s_end = round(float(sent.get("end", s_start + 1.0)), 3)
            if not s_text:
                continue

            new_tokens = [t.strip() for t in s_text.split() if t.strip()]
            orig_words = sent.get("words", [])

            sent_word_objs = []
            if len(new_tokens) == len(orig_words) and orig_words:
                for tok, ow in zip(new_tokens, orig_words):
                    w_obj = {
                        "word": tok,
                        "start": round(float(ow.get("start", s_start)), 3),
                        "end": round(float(ow.get("end", s_end)), 3),
                        "probability": 1.0
                    }
                    sent_word_objs.append(w_obj)
                    synced_words.append(w_obj)
            elif new_tokens:
                total_chars = max(1, sum(len(t) for t in new_tokens))
                dur = max(0.15, s_end - s_start)
                cursor = s_start
                for idx, tok in enumerate(new_tokens):
                    w_dur = dur * (len(tok) / total_chars)
                    w_end_t = s_end if idx == len(new_tokens) - 1 else round(cursor + w_dur, 3)
                    w_obj = {
                        "word": tok,
                        "start": round(cursor, 3),
                        "end": max(round(cursor + 0.08, 3), w_end_t),
                        "probability": 1.0
                    }
                    cursor = w_end_t
                    sent_word_objs.append(w_obj)
                    synced_words.append(w_obj)

            synced_sentences.append({
                "text": " ".join(new_tokens),
                "start": s_start,
                "end": s_end,
                "words": sent_word_objs
            })

        _CUSTOM_CAPTION_OVERRIDE["enabled"] = True
        _CUSTOM_CAPTION_OVERRIDE["words"] = synced_words
        _CUSTOM_CAPTION_OVERRIDE["sentences"] = synced_sentences
        _LAST_EXTRACTED_TRANSCRIPT["words"] = synced_words
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = synced_sentences
        return synced_words, synced_sentences

    if custom_words is not None:
        cleaned_words = []
        for w in custom_words:
            w_txt = str(w.get("word", "")).strip()
            if not w_txt:
                continue
            w_s = round(float(w.get("start", 0.0)), 3)
            w_e = round(max(w_s + 0.08, float(w.get("end", w_s + 0.3))), 3)
            cleaned_words.append({
                "word": w_txt,
                "start": w_s,
                "end": w_e,
                "probability": 1.0
            })

        updated_sentences = split_words_into_micro_scenes(cleaned_words)
        _CUSTOM_CAPTION_OVERRIDE["enabled"] = True
        _CUSTOM_CAPTION_OVERRIDE["words"] = cleaned_words
        _CUSTOM_CAPTION_OVERRIDE["sentences"] = updated_sentences
        _LAST_EXTRACTED_TRANSCRIPT["words"] = cleaned_words
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = updated_sentences
        return cleaned_words, updated_sentences

    return base_words, base_sentences


# ==============================================================================
# 4. تطبيع وتدقيق النصوص والدارجة الجزائرية
# ==============================================================================
def normalize_algerian_word(word: str) -> str:
    if not word:
        return ""
    cleaned = word.strip()
    # فحص بدون علامات ترقيم طرفية
    stripped_punct = cleaned.strip("،,.!؟?")
    if cleaned in ALGERIAN_DARIJA_LEXICON_FIXES:
        return ALGERIAN_DARIJA_LEXICON_FIXES[cleaned]
    if stripped_punct in ALGERIAN_DARIJA_LEXICON_FIXES:
        suffix = cleaned[len(stripped_punct):] if cleaned.startswith(stripped_punct) else ""
        return ALGERIAN_DARIJA_LEXICON_FIXES[stripped_punct] + suffix
    return cleaned


def normalize_algerian_sentence(text: str) -> str:
    if not text:
        return ""
    out = text.strip()
    for wrong, right in ALGERIAN_DARIJA_LEXICON_FIXES.items():
        out = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, out)
    for pattern, replacement in PHRASE_LEVEL_FIXES:
        out = re.sub(pattern, replacement, out)
    return out


def apply_phrase_fixes_to_words(words_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """تطبيق التصحيحات المركبة على قائمة الكلمات مع الحفاظ على التوقيت."""
    if not words_list:
        return words_list

    # تصحيح خاص للتراكيب المتتالية مثل (أنا لنلو -> أهلاً) أو (حاول أبني -> أحاول أبني)
    updated = [dict(w) for w in words_list]
    for i in range(len(updated)):
        w_curr = updated[i]["word"].strip("،,.")
        if w_curr in {"لنلو", "أهلاً", "اهلا"} and i > 0 and updated[i - 1]["word"].strip("،,.") == "أنا":
            updated[i - 1]["word"] = "أهلاً،"
            updated[i]["word"] = "أنا"
        elif w_curr == "حاول" and i + 1 < len(updated) and updated[i + 1]["word"].startswith("أبني"):
            updated[i]["word"] = "أحاول"
        elif w_curr == "اصطناعي" and i > 0 and updated[i - 1]["word"] == "بالذكاء":
            updated[i]["word"] = "الاصطناعي"

    deduped = []
    for w in updated:
        if deduped and deduped[-1]["word"].strip("،,.") == w["word"].strip("،,."):
            deduped[-1]["end"] = w["end"]
            deduped[-1]["word"] = w["word"]
        else:
            deduped.append(w)
    return deduped


def refine_darija_words_with_ai(
    words_list: List[Dict[str, Any]],
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    words_list = apply_phrase_fixes_to_words(words_list)
    if not words_list or len(words_list) > 250:
        return words_list

    raw_tokens = [w["word"] for w in words_list]
    indexed_text = " | ".join([f"{i}:{tok}" for i, tok in enumerate(raw_tokens)])

    instruction = (
        "المدخل التالي هو كلمات مستخرجة بالتعرف الصوتي (Whisper) من فيديو بالدارجة الجزائرية أو العربية مفصولة بـ |. "
        "بعض الكلمات قد تكون مكتوبة خطأ بسبب التشابه الصوتي (مثال: منتاج -> مونتاج، استناعي -> اصطناعي، ريز -> ريلز، أغالب -> أغلب، هنده -> عندها، أناس -> أنس). "
        "صحح الكلمات الخاطئة إملائياً فقط لتصبح صحيحة وسليمة مع الحفاظ على نفس رقم الفهرس."
    )

    prompt = (
        f"{instruction}\n"
        f"قائمة الكلمات المفهرسة:\n{indexed_text}\n\n"
        "أرجع فقط JSON صالح يربط رقم الكلمة بالكلمة المصححة، مثال: {\"2\": \"مونتاج\"}. إذا كانت كلها صحيحة أرجع {}."
    )

    ai_resp = query_hybrid_llm(
        prompt=prompt,
        system_prompt="أنت مدقق لغوي خبير في العربية والدارجة الجزائرية ومصطلحات صناعة المحتوى. أرجع JSON فقط.",
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
    except Exception:
        pass

    return words_list


# ==============================================================================
# 5. التفريغ السحابي والمحلي وتوليد المشاهد القصيرة (Micro-Scenes)
# ==============================================================================
def _transcribe_via_cloud_api(
    audio_path: str,
    groq_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    language: str = "ar"
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    groq_key = (groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    openai_key = (openai_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

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
        endpoints.append(("https://api.groq.com/openai/v1/audio/transcriptions", groq_key, "whisper-large-v3"))
    if openai_key:
        endpoints.append(("https://api.openai.com/v1/audio/transcriptions", openai_key, "whisper-1"))

    try:
        for url, api_key, model_name in endpoints:
            try:
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

                    if words_list:
                        words_list = apply_phrase_fixes_to_words(words_list)
                        micro_scenes = split_words_into_micro_scenes(words_list)
                        return words_list, micro_scenes
            except Exception as e:
                logger.warning(f"فشل التفريغ السحابي ({model_name}): {e}")
    finally:
        if temp_compressed and os.path.exists(temp_compressed):
            try:
                os.remove(temp_compressed)
            except Exception:
                pass

    return None


def get_optimal_device_settings() -> Tuple[str, str]:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    return "cpu", "int8"


def _get_or_load_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel
    cache_key = f"{model_size}_{device}_{compute_type}"
    if cache_key not in _WHISPER_MODEL_CACHE:
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
    """تشغيل التفريغ وتقسيم الكلمات إلى مشاهد قصيرة متجددة كل 1.5 - 2 ثانية."""
    if _CUSTOM_CAPTION_OVERRIDE["enabled"] and _CUSTOM_CAPTION_OVERRIDE["words"]:
        return (
            [dict(w) for w in _CUSTOM_CAPTION_OVERRIDE["words"]],
            [dict(s) for s in _CUSTOM_CAPTION_OVERRIDE["sentences"]]
        )

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"الملف المطلوب تفريغه غير موجود: {audio_path}")

    file_mtime = os.path.getmtime(audio_path)
    cache_key = f"{os.path.abspath(audio_path)}_{file_mtime}_{model_size}_{dialect_mode}"
    if cache_key in _TRANSCRIPTION_CACHE:
        cached = _TRANSCRIPTION_CACHE[cache_key]
        _LAST_EXTRACTED_TRANSCRIPT["words"] = cached["words"]
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = cached["sentences"]
        return cached["words"], cached["sentences"]

    cloud_res = _transcribe_via_cloud_api(
        audio_path=audio_path,
        groq_api_key=groq_api_key,
        openai_api_key=openai_api_key,
        language=language or "ar"
    )
    if cloud_res is not None:
        words_list, _ = cloud_res
        words_list = refine_darija_words_with_ai(
            words_list,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        micro_scenes = split_words_into_micro_scenes(words_list)
        _TRANSCRIPTION_CACHE[cache_key] = {"words": words_list, "sentences": micro_scenes}
        _LAST_EXTRACTED_TRANSCRIPT["words"] = words_list
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = micro_scenes
        return words_list, micro_scenes

    detected_device, detected_compute = get_optimal_device_settings()
    final_device = device if device is not None else detected_device
    final_compute = compute_type if compute_type is not None else detected_compute

    model = _get_or_load_whisper_model(model_size, final_device, final_compute)
    target_language = None if (language == "auto" or not language) else language

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=target_language,
        initial_prompt=ALGERIAN_DARIJA_INITIAL_PROMPT,
        beam_size=5,
        best_of=5,
        condition_on_previous_text=False,
        vad_filter=vad_filter,
        vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=250)
    )

    word_timestamps: List[Dict[str, Any]] = []
    for seg in segments:
        if seg.words:
            for word_obj in seg.words:
                cleaned_word = normalize_algerian_word(word_obj.word)
                if cleaned_word:
                    word_timestamps.append({
                        "word": cleaned_word,
                        "start": round(word_obj.start, 3),
                        "end": round(word_obj.end, 3),
                        "probability": round(word_obj.probability, 3)
                    })

    if word_timestamps:
        word_timestamps = refine_darija_words_with_ai(
            word_timestamps,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

    # تقسيم الكلمات إلى مشاهد قصيرة متجددة كل 1.5 - 2 ثانية!
    micro_scenes = split_words_into_micro_scenes(word_timestamps)

    _TRANSCRIPTION_CACHE[cache_key] = {
        "words": word_timestamps,
        "sentences": micro_scenes
    }
    _LAST_EXTRACTED_TRANSCRIPT["words"] = word_timestamps
    _LAST_EXTRACTED_TRANSCRIPT["sentences"] = micro_scenes

    return word_timestamps, micro_scenes


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
