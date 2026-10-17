"""
transcriber.py - محرك التفريغ الصوتي الثلاثي الهجين والتقسيم الدلالي السياقي للجمل (Contextual Semantic Segmentation)
=======================================================================================================================
يعالج هذا الملف فهم الدارجة الجزائرية والعربية وتقسيم الكلام حسب السياق والمعنى الكامل للجملة (وليس كلمة بكلمة):
1. محرك التعرف الجزائري المباشر (Google Speech-to-Text `ar-DZ` + دعم Gemini Audio و Groq Whisper-Large-v3).
2. محرك `faster-whisper` بمعايرة خاصة للدارجة السريعة.
3. خوارزمية التجميع الدلالي السياقي (`split_words_into_micro_scenes` / `group_words_into_semantic_clauses`):
   - تجمع الكلمات في وحدات معنوية وجمل متكاملة السياق (5 إلى 9 كلمات، بمدة 2.8 إلى 4.5 ثانية للمشهد)
     وتمنع تقطيع الجمل إلى شظايا صغيرة من كلمة أو كلمتين (مثل "أهلاً أنا" أو "وقاعد أحاول" أو "المنصة").
"""

import sys
import os
import gc
import ctypes
import subprocess

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import re
import json
import math
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def _force_free_ram():
    try:
        _force_free_ram()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None


# ==============================================================================
# 1. إعدادات وموجهات الدارجة الجزائرية ومصطلحات التجارة الإلكترونية والتقنية
# ==============================================================================
ALGERIAN_DARIJA_INITIAL_PROMPT = (
    "تسجيل بالدارجة الجزائرية والعربية: واش راكم، كاين بزاف ناس، درك، دوكا، علاش، كيفاش، بزاف، ماكانش، "
    "حاجة شابة، مليح، خاوتي، صحيتو، نقدروا نديرو، معنتها، باسكو، ديجا، نورمالمون، قاع، والو، مرحبا بكم، "
    "شفت، سمعت، هكذا، هاد، هادي، هذا، هاد الشي، كاين، كاينين، شكراً، يعطيكم الصحة."
)

ALGERIAN_DARIJA_LEXICON_FIXES = {
    "أصبر": "اصبر",
    "أصبر،": "اصبر،",
    "استكش": "ما حبستكش",
    "ماحبستكش": "ما حبستكش",
    "محبستكش": "ما حبستكش",
    "حبستكش": "ما حبستكش",
    "علاجال": "على جال",
    "علاجلك": "على جال",
    "تيبسي": "تيب سي",
    "تايبسي": "تيب سي",
    "سيرفر": "سيبور",
    "سيبورت": "سيبور",
    "سبور": "سيبور",
    "تشارجي": "تشارجي",
    "تشرجي": "تشارجي",
    "شارجي": "تشارجي",
    "معناتها": "معنتها",
    "معنتها": "معنتها",
    "ومتخافش": "وما تخافش",
    "ماتخافش": "ما تخافش",
    "متخافش": "ما تخافش",
    "كاع": "قاع",
    "قاع": "قاع",
    "المتوفرس": "متوفر",
    "متوفرس": "متوفر",
    "أكموان": "اكموندي",
    "اكموان": "اكموندي",
    "أكموندي": "اكموندي",
    "كوموندي": "اكموندي",
    "كموندي": "اكموندي",
    "لنلو": "أهلاً",
    "لنلو،": "أهلاً،",
    "اهلا": "أهلاً",
                        "سنه": "سنة",
    "منصه": "منصة",
    "المنصه": "المنصة",
        "استناعي": "اصطناعي",
    "إستناعي": "اصطناعي",
    "بذكاء": "بالذكاء",
    "اوتوماتيكي": "أوتوماتيكي",
    "أغالب": "أغلب",
    "اغالب": "أغلب",
    "اغلب": "أغلب",
    "لان": "لأن",
    "هنده": "عندها",
    "عنده": "عندها",
    "ريز": "ريلز",
    "ريز،": "ريلز،",
    "الريز": "الريلز",
                        "وشراكم": "واش راكم",
    "واشراكم": "واش راكم",
    "علاه": "علاش",
    "كفاش": "كيفاش",
    "بالزاف": "بزاف",
    "ما كاش": "ماكانش",
    "مكانش": "ماكانش",
    "دركا": "درك",
    "دوكة": "دوكا",
    "عفسه": "عفسة",
    "خوتي": "خاوتي",
    "صحيتوا": "صحيتو",
    "نديروا": "نديرو",
    "نقدرو": "نقدروا",
    "بارسكو": "باسكو",
    "ديجة": "ديجا",
    "نورمالمو": "نورمالمون",
    "نتاع": "تاع",
    "هاذي": "هاذ",
    "كلشي": "كلش",
    "ليفريزو": "ليفريزون",
}

PHRASE_LEVEL_FIXES = [
                                                        (r"سيرفر\s+تيليفون", "سيبور تيليفون"),
    (r"قطع[،,]?\s+يتقطع", "قاع يتقطع"),
    (r"المتوفرس\s+على", "راه متوفر"),
    (r"أكموان\s+من", "اكموندي من"),
]


# ==============================================================================
# 1.5 محرك إصلاح الكلمات المبتورة صوتياً والسياقية (Anti-Truncation Morphological Repair)
# ==============================================================================
CONTEXTUAL_BROKEN_WORD_REPAIRS = [
    (r"(?<!\w)في\s+المونت(?!\w)", "في المونتاج"),
    (r"(?<!\w)المونت\s+الان(?!\w)", "المونتاج لأن"),
    (r"(?<!\w)المونت(?!\w)", "المونتاج"),
    (r"(?<!\w)الان\s+أغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)الان\s+اغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)تصور\s+للفيديوهات(?!\w)", "تصور الفيديوهات"),
    (r"(?<!\w)التواصل\s+الاج(?!\w)", "التواصل الاجتماعي"),
    (r"(?<!\w)مواقع\s+التواصل\s+الاج(?!\w)", "مواقع التواصل الاجتماعي"),
    (r"(?<!\w)الاج(?!\w)", "الاجتماعي"),
    (r"(?<!\w)المسؤوله\s+على\s+اللي(?!\w)", "المسؤولة على المونتاج"),
    (r"(?<!\w)صورته\s+ذكاء\s+الاصطناعي(?!\w)", "صوت وصورة بالذكاء الاصطناعي"),
    (r"(?<!\w)منت\s+الفيديو(?!\w)", "تمنتج الفيديو"),
    (r"(?<!\w)ومونتاج\s+احت\s+ولا(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)ومونتاج\s+احت(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)مونتاج\s+احت(?!\w)", "مونتاج احترافي"),
    (r"(?<!\w)من\s+دقيقه(?!\w)", "أقل من دقيقة"),
    (r"(?<!\w)قص\s+تعديل\s+الفيديو(?!\w)", "قص وتعديل الفيديو"),
]

SINGLE_TRUNCATED_TOKEN_MAP = {
    "المونت": "المونتاج",
    "الاج": "الاجتماعي",
    "منت": "تمنتج",
    "احت": "احترافي",
    "الانتاجيه": "الإنتاجية",
    "المسؤوله": "المسؤولة",
    "دقيقه": "دقيقة",
    "للفيديوهات": "الفيديوهات",
}

def repair_truncated_words_and_sentences(words_list):
    if not words_list:
        return []
    repaired = [dict(w) for w in words_list]
    for i, w_obj in enumerate(repaired):
        raw_w = str(w_obj.get("word", "")).strip()
        clean_w = raw_w.strip("،,.!؟?")
        if clean_w in SINGLE_TRUNCATED_TOKEN_MAP:
            repaired[i]["word"] = SINGLE_TRUNCATED_TOKEN_MAP[clean_w]
        if clean_w in {"الان", "الآن"} and i + 1 < len(repaired):
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if nxt_w in {"أغلب", "اغلب", "كثير", "بزاف", "الناس"}:
                repaired[i]["word"] = "لأن"
        if clean_w in {"صورته", "صورتك"} and i + 1 < len(repaired):
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if "ذكاء" in nxt_w or "اصطناعي" in nxt_w:
                repaired[i]["word"] = "صوت وصورة"
        if clean_w == "ولا" and i > 0:
            prev_w = str(repaired[i - 1].get("word", "")).strip("،,.!؟?")
            if prev_w == "احترافي":
                repaired[i]["word"] = ""
    return [w for w in repaired if str(w.get("word", "")).strip()]

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
# 2. تقسيم الكلمات إلى مشاهد دلالية سياقية متكاملة (Complete Semantic Clauses)
# ==============================================================================
def ensure_word_timestamp_continuity(
    words_list: List[Dict[str, Any]],
    total_duration: Optional[float] = None
) -> List[Dict[str, Any]]:
    """ضمان اتصال التوقيت الزمني بين الكلمات لمنع اختفاء الكابشن المفاجئ."""
    if not words_list:
        return []

    smoothed: List[Dict[str, Any]] = [dict(w) for w in words_list]
    for i in range(len(smoothed)):
        w_s = float(smoothed[i].get("start", 0.0))
        w_e = float(smoothed[i].get("end", w_s + 0.25))
        if w_e <= w_s + 0.08:
            w_e = w_s + 0.22

        if i + 1 < len(smoothed):
            next_s = float(smoothed[i + 1].get("start", w_e))
            gap = next_s - w_e
            if 0.0 <= gap <= 0.45:
                w_e = next_s
            elif gap < 0.0:
                w_e = max(w_s + 0.08, next_s)
        elif total_duration is not None:
            if 0.0 < total_duration - w_e <= 0.45:
                w_e = total_duration

        smoothed[i]["start"] = round(w_s, 3)
        smoothed[i]["end"] = round(w_e, 3)

    return smoothed


def split_words_into_micro_scenes(
    words_list: List[Dict[str, Any]],
    max_words_per_scene: int = 8,
    max_duration_per_scene: float = 4.2,
    min_words_per_scene: int = 4
) -> List[Dict[str, Any]]:
    """
    تقسيم الكلمات حسب السياق والمعنى الكامل للجملة (Semantic Clause Grouping):
    - يجمع الكلمات في جمل وأفكار مترابطة (من 4 إلى 8 كلمات، بمدة 2.5 إلى 4.2 ثانية)
      بحيث يعبر كل مشهد موشن جرافيك عن فكرة كاملة ومفهومة (وليس كلمة بكلمة!).
    - يدمج تلقائياً أي شظايا قصيرة (أقل من 4 كلمات) مع الجملة المرتبطة بها سياقياً.
    """
    if not words_list:
        return []

    # ترقية الحدود الدنيا تلقائياً حتى لو تم استدعاء الدالة بمعاملات قديمة صغيرة (مثل 4 كلمات و 2.0 ثانية)
    eff_max_words = max(7, int(max_words_per_scene))
    eff_max_dur = max(3.6, float(max_duration_per_scene))
    eff_min_words = max(4, int(min_words_per_scene))

    words_list = ensure_word_timestamp_continuity(words_list)
    raw_scenes: List[Dict[str, Any]] = []
    current_group: List[Dict[str, Any]] = []

    # الروابط السياقية الكبرى التي تبدأ جملة/فكرة جديدة فقط عندما تكتمل الفكرة السابقة
    major_clause_starters = {
        "لأن", "لان", "علاش", "كيفاش", "واسم", "لكن", "باش",
        "التوصيل", "اكموندي", "اطلب", "المشكل", "الحل", "ومغلف", "معنتها"
    }

    # كلمات لا يجوز أبداً فصلها عن الكلمة التي تليها (تمنع قطع المضاف والمضاف إليه أو الفعل وفاعله)
    non_breaking_end_words = {
        "أنا", "انا", "عمري", "وقاعد", "أحاول", "احاول", "أبني", "ابني",
        "تعمل", "بشكل", "لأن", "لان", "أغلب", "اغلب", "ما", "عندها",
        "تمنتج", "تبدل", "وترفع", "كل", "واسم", "اسم", "منصة", "المنصة",
        "فيديو", "بالذكاء", "بذكاء", "على", "جال", "كابل", "سيبور", "في", "نفس"
    }

    for idx, w in enumerate(words_list):
        w_txt = str(w.get("word", "")).strip()
        if not w_txt:
            continue
        w_clean = w_txt.strip("،,.!؟?")

        if current_group:
            grp_start = float(current_group[0]["start"])
            grp_dur = float(w["end"]) - grp_start
            prev_word_txt = str(current_group[-1]["word"]).strip()
            prev_clean = prev_word_txt.strip("،,.!؟?")
            gap = float(w["start"]) - float(current_group[-1]["end"])

            ends_with_strong_punct = any(prev_word_txt.endswith(p) for p in [".", "!", "؟", "?"])
            is_clause_starter = (w_clean in major_clause_starters and len(current_group) >= eff_min_words)
            prev_is_non_breaking = (prev_clean in non_breaking_end_words)

            should_split = False
            if gap >= 0.55 and len(current_group) >= 3:
                should_split = True
            elif ends_with_strong_punct and len(current_group) >= eff_min_words:
                should_split = True
            elif is_clause_starter and not prev_is_non_breaking:
                should_split = True
            elif (len(current_group) >= eff_max_words or grp_dur >= eff_max_dur) and not prev_is_non_breaking:
                should_split = True
            elif len(current_group) >= eff_max_words + 2:
                should_split = True

            if should_split:
                raw_scenes.append({
                    "text": " ".join(x["word"] for x in current_group),
                    "start": round(float(current_group[0]["start"]), 3),
                    "end": round(float(current_group[-1]["end"]), 3),
                    "words": list(current_group)
                })
                current_group = []

        current_group.append(dict(w))

    if current_group:
        raw_scenes.append({
            "text": " ".join(x["word"] for x in current_group),
            "start": round(float(current_group[0]["start"]), 3),
            "end": round(float(current_group[-1]["end"]), 3),
            "words": list(current_group)
        })

    # المرحلة الثانية: دمج أي شظايا قصيرة (أقل من 4 كلمات أو أقل من 1.8 ثانية) مع الجملة المناسبة سياقياً
    merged_scenes: List[Dict[str, Any]] = []
    for sc in raw_scenes:
        sc_words = sc.get("words", [])
        sc_dur = float(sc["end"]) - float(sc["start"])
        if merged_scenes and (len(sc_words) < 3 or sc_dur < 1.5):
            # ادمج الشظية القصيرة مع المشهد السابق إذا كان المشهد السابق لا يتجاوز 9 كلمات
            prev_sc = merged_scenes[-1]
            if len(prev_sc["words"]) + len(sc_words) <= 10:
                prev_sc["words"].extend(sc_words)
                prev_sc["end"] = sc["end"]
                prev_sc["text"] = " ".join(x["word"] for x in prev_sc["words"])
                continue
        merged_scenes.append(sc)

    # فحص عكسي: إذا كان المشهد الأول قصيراً جداً (مثل "أهلاً أنا أنس" 3 كلمات ويليه "عمري 17 سنة" 3 كلمات) ندمجهما في جملة تعريفية متكاملة!
    final_scenes: List[Dict[str, Any]] = []
    i = 0
    while i < len(merged_scenes):
        curr = merged_scenes[i]
        if i + 1 < len(merged_scenes):
            nxt = merged_scenes[i + 1]
            curr_w_count = len(curr["words"])
            nxt_w_count = len(nxt["words"])
            combined_dur = float(nxt["end"]) - float(curr["start"])
            # دمج الجمل القصيرة المتجاورة لتكوين فكرة سياقية كاملة
            if (curr_w_count <= 3 and nxt_w_count <= 5 and combined_dur <= 5.0) or (nxt_w_count <= 2 and combined_dur <= 5.5):
                combined_words = curr["words"] + nxt["words"]
                final_scenes.append({
                    "text": " ".join(x["word"] for x in combined_words),
                    "start": curr["start"],
                    "end": nxt["end"],
                    "words": combined_words
                })
                i += 2
                continue
        final_scenes.append(curr)
        i += 1

    # سد أي فجوة صغيرة بين نهاية مشهد وبداية المشهد التالي لعدم اختفاء الرسومات
    for idx in range(len(final_scenes) - 1):
        gap = final_scenes[idx + 1]["start"] - final_scenes[idx]["end"]
        if 0.0 < gap <= 0.60:
            final_scenes[idx]["end"] = final_scenes[idx + 1]["start"]
            if final_scenes[idx]["words"]:
                final_scenes[idx]["words"][-1]["end"] = final_scenes[idx + 1]["start"]

    return final_scenes


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
        for sent in custom_sentences:
            s_text = str(sent.get("text", "")).strip()
            s_start = round(float(sent.get("start", 0.0)), 3)
            s_end = round(float(sent.get("end", s_start + 1.0)), 3)
            if not s_text:
                continue

            new_tokens = [t.strip() for t in s_text.split() if t.strip()]
            orig_words = sent.get("words", [])

            if len(new_tokens) == len(orig_words) and orig_words:
                for tok, ow in zip(new_tokens, orig_words):
                    synced_words.append({
                        "word": tok,
                        "start": round(float(ow.get("start", s_start)), 3),
                        "end": round(float(ow.get("end", s_end)), 3),
                        "probability": 1.0
                    })
            elif new_tokens:
                total_chars = max(1, sum(len(t) for t in new_tokens))
                dur = max(0.15, s_end - s_start)
                cursor = s_start
                for idx, tok in enumerate(new_tokens):
                    w_dur = dur * (len(tok) / total_chars)
                    w_end_t = s_end if idx == len(new_tokens) - 1 else round(cursor + w_dur, 3)
                    synced_words.append({
                        "word": tok,
                        "start": round(cursor, 3),
                        "end": max(round(cursor + 0.08, 3), w_end_t),
                        "probability": 1.0
                    })
                    cursor = w_end_t

        synced_words = ensure_word_timestamp_continuity(synced_words)
        synced_sentences = split_words_into_micro_scenes(synced_words)

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

        cleaned_words = ensure_word_timestamp_continuity(cleaned_words)
        updated_sentences = split_words_into_micro_scenes(cleaned_words)
        _CUSTOM_CAPTION_OVERRIDE["enabled"] = True
        _CUSTOM_CAPTION_OVERRIDE["words"] = cleaned_words
        _CUSTOM_CAPTION_OVERRIDE["sentences"] = updated_sentences
        _LAST_EXTRACTED_TRANSCRIPT["words"] = cleaned_words
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = updated_sentences
        return cleaned_words, updated_sentences

    return base_words, base_sentences


# ==============================================================================
# 4. تطبيع وتدقيق الدارجة الجزائرية والسياق الصوتي
# ==============================================================================
def normalize_algerian_word(word: str) -> str:
    if not word:
        return ""
    cleaned = word.strip()
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
    for pattern, replacement in CONTEXTUAL_BROKEN_WORD_REPAIRS:
        out = re.sub(pattern, replacement, out)
    return out


def apply_phrase_fixes_to_words(words_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """تطبيق التصحيحات المركبة والسياقية وفك الكلمات المدمجة مع الحفاظ على التوقيت."""
    if not words_list:
        return words_list

    expanded: List[Dict[str, Any]] = []
    for w in words_list:
        w_copy = dict(w)
        w_copy["word"] = normalize_algerian_word(w_copy["word"])
        parts = w_copy["word"].split()
        if len(parts) > 1:
            dur = max(0.12, float(w_copy["end"]) - float(w_copy["start"])) / len(parts)
            for idx, p in enumerate(parts):
                expanded.append({
                    "word": p,
                    "start": round(float(w_copy["start"]) + idx * dur, 3),
                    "end": round(float(w_copy["start"]) + (idx + 1) * dur, 3),
                    "probability": w_copy.get("probability", 0.95)
                })
        else:
            expanded.append(w_copy)

    # فحص سياقي للعبارات المركبة (مثل "تبدل الفيديو" -> "تمنتج الفيديوهات" في سياق المونتاج والريلز)
    full_joined = " ".join(x["word"] for x in expanded)
    is_video_editing_context = any(k in full_joined for k in ["مونتاج", "ريلز", "إيديتينج", "ذكاء", "منصة"])

    for i in range(len(expanded)):
        w_curr = expanded[i]["word"].strip("،,.")
        if w_curr in {"لنلو"}:
            expanded[i]["word"] = "أهلاً"

    deduped = []
    for w in expanded:
        w_clean = w["word"].strip("،,.")
        if deduped and deduped[-1]["word"].strip("،,.") == w_clean and w_clean not in {"اصبر", "أصبر"}:
            deduped[-1]["end"] = w["end"]
            deduped[-1]["word"] = w["word"]
        else:
            deduped.append(w)
    repaired = repair_truncated_words_and_sentences(deduped)
    # Re-expand any multi-word repairs (like 'صوت وصورة') while preserving timestamps
    final_expanded = []
    for w in repaired:
        parts = str(w.get("word", "")).split()
        if len(parts) > 1:
            dur = max(0.12, float(w["end"]) - float(w["start"])) / len(parts)
            for idx, p in enumerate(parts):
                final_expanded.append({
                    "word": p,
                    "start": round(float(w["start"]) + idx * dur, 3),
                    "end": round(float(w["start"]) + (idx + 1) * dur, 3),
                    "probability": w.get("probability", 0.96)
                })
        else:
            final_expanded.append(w)
    return ensure_word_timestamp_continuity(final_expanded)


# ==============================================================================
# 5. المحرك الأول: Google Speech Recognition (ar-DZ الجزائر) مجاناً بدون مفتاح!
# ==============================================================================
def _transcribe_via_google_ar_dz_chunks(audio_path: str) -> Optional[List[Dict[str, Any]]]:
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
    except ImportError as e:
        logger.debug(f"مكتبة speech_recognition غير متوفرة ({e}).")
        return None

    temp_16k = audio_path + "_16k_mono.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-threads", "1", "-i", audio_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-threads", "1", temp_16k],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
        )
        if os.path.exists(temp_16k) and os.path.getsize(temp_16k) > 512:
            audio = AudioSegment.from_wav(temp_16k)
        else:
            audio = AudioSegment.from_file(audio_path).set_frame_rate(16000).set_channels(1).set_sample_width(2)
        total_ms = len(audio)
        if total_ms < 200:
            return None

        thresh = max(-50.0, min(-30.0, float(audio.dBFS) - 9.0)) if audio.dBFS != -float("inf") else -40.0
        raw_chunks = detect_nonsilent(audio, min_silence_len=320, silence_thresh=thresh, seek_step=10)
        if not raw_chunks:
            raw_chunks = [[0, total_ms]]

        merged_chunks: List[List[int]] = []
        for s_ms, e_ms in raw_chunks:
            s_pad = max(0, s_ms - 150)
            e_pad = min(total_ms, e_ms + 180)
            if not merged_chunks:
                merged_chunks.append([s_pad, e_pad])
            else:
                prev_s, prev_e = merged_chunks[-1]
                if (s_pad - prev_e < 250 and (e_pad - prev_s) < 5200) or (prev_e - prev_s < 1400 and (e_pad - prev_s) < 5500):
                    merged_chunks[-1][1] = e_pad
                else:
                    merged_chunks.append([s_pad, e_pad])

        # تقسيم المقاطع الطويلة عند أهدأ نقطة صمت بين الكلمات (Acoustic Valley Splitting) لمنع بتر أي كلمة في المنتصف!
        final_chunks: List[Tuple[int, int]] = []
        for s_ms, e_ms in merged_chunks:
            cur_s = s_ms
            while (e_ms - cur_s) > 7200:
                search_start = cur_s + 3400
                search_end = min(e_ms - 1200, cur_s + 6400)
                best_split = cur_s + 4800
                min_rms = float("inf")
                for probe_ms in range(search_start, search_end, 25):
                    win_slice = audio[probe_ms:probe_ms + 50]
                    if win_slice.rms < min_rms:
                        min_rms = win_slice.rms
                        best_split = probe_ms + 25
                final_chunks.append((cur_s, min(e_ms, best_split + 40)))
                cur_s = max(cur_s + 1000, best_split - 40)
            if e_ms - cur_s >= 180:
                final_chunks.append((cur_s, e_ms))

        recognizer = sr.Recognizer()
        all_words: List[Dict[str, Any]] = []

        for c_start_ms, c_end_ms in final_chunks:
            chunk_audio = audio[c_start_ms:c_end_ms]
            raw_wav_bytes = chunk_audio.raw_data
            audio_data = sr.AudioData(raw_wav_bytes, 16000, 2)

            try:
                text_dz = recognizer.recognize_google(audio_data, language="ar-DZ")
            except sr.UnknownValueError:
                continue
            except Exception as e:
                logger.warning(f"تعذر الاتصال بمحرك ar-DZ: {e}")
                return None

            if not text_dz or not text_dz.strip():
                continue

            cleaned_sentence = normalize_algerian_sentence(text_dz.strip())
            tokens = [normalize_algerian_word(t) for t in cleaned_sentence.split() if t.strip()]
            if not tokens:
                continue

            c_start_sec = c_start_ms / 1000.0
            c_end_sec = c_end_ms / 1000.0
            sub_nonsilent = detect_nonsilent(chunk_audio, min_silence_len=120, silence_thresh=thresh - 2.0, seek_step=10)
            if sub_nonsilent:
                speech_s_sec = c_start_sec + (sub_nonsilent[0][0] / 1000.0)
                speech_e_sec = c_start_sec + (sub_nonsilent[-1][1] / 1000.0)
            else:
                speech_s_sec, speech_e_sec = c_start_sec, c_end_sec

            speech_dur = max(0.18, speech_e_sec - speech_s_sec)
            weights = [max(2.0, float(len(tok)) ** 0.85) for tok in tokens]
            total_weight = sum(weights)

            cursor = speech_s_sec
            for idx, (tok, w_weight) in enumerate(zip(tokens, weights)):
                w_dur = speech_dur * (w_weight / total_weight)
                w_end = speech_e_sec if idx == len(tokens) - 1 else (cursor + w_dur)
                all_words.append({
                    "word": tok,
                    "start": round(cursor, 3),
                    "end": round(max(cursor + 0.08, w_end), 3),
                    "probability": 0.95
                })
                cursor = w_end

        if all_words:
            logger.info(f"نجح التعرف الصوتي باللهجة الجزائرية (ar-DZ): {len(all_words)} كلمة.")
            return ensure_word_timestamp_continuity(all_words)

    except Exception as e:
        logger.warning(f"ملاحظة في محرك ar-DZ: {e}")
    finally:
        if os.path.exists(temp_16k):
            try:
                os.remove(temp_16k)
            except Exception:
                pass
        _force_free_ram()

    return None


# ==============================================================================
# 6. المحرك الثاني: Gemini Multimodal Audio / Groq Whisper Large-v3
# ==============================================================================
def _transcribe_via_gemini_multimodal(
    audio_path: str,
    gemini_api_key: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    gem_key = (gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not gem_key:
        return None

    temp_mp3 = None
    try:
        from pydub import AudioSegment
        aud = AudioSegment.from_file(audio_path)
        total_dur = len(aud) / 1000.0
        temp_mp3 = audio_path + "_gem_temp.mp3"
        aud.set_frame_rate(16000).set_channels(1).export(temp_mp3, format="mp3", bitrate="64k")

        with open(temp_mp3, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            f"هذا ملف صوتي مدته {total_dur:.2f} ثانية باللهجة الجزائرية الدارجة (Algerian Darija) أو العربية. "
            "فرّغ كل كلمة منطوقة بدقة تامة كما قيلت بالدارجة الجزائرية. "
            "أرجع JSON فقط عبارة عن قائمة قواميس لكل كلمة: "
            "[{\"word\": \"الكلمة\", \"start\": 0.0, \"end\": 0.4}, ...]"
        )

        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gem_key}"
            resp = requests.post(
                url,
                json={
                    "contents": [{
                        "parts": [
                            {"inlineData": {"mimeType": "audio/mp3", "data": b64_audio}},
                            {"text": prompt}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000}
                },
                timeout=30
            )
            if resp.status_code == 200:
                candidates = resp.json().get("candidates", [])
                if candidates:
                    txt = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    match = re.search(r"\[.*\]", txt, re.DOTALL)
                    if match:
                        arr = json.loads(match.group(0))
                        words_out = []
                        for item in arr:
                            w_str = normalize_algerian_word(str(item.get("word", "")))
                            if w_str:
                                words_out.append({
                                    "word": w_str,
                                    "start": round(float(item.get("start", 0.0)), 3),
                                    "end": round(float(item.get("end", 0.3)), 3),
                                    "probability": 0.98
                                })
                        if words_out:
                            return ensure_word_timestamp_continuity(words_out, total_dur)
    except Exception as e:
        logger.warning(f"Gemini audio transcription fallback: {e}")
    finally:
        if temp_mp3 and os.path.exists(temp_mp3):
            try:
                os.remove(temp_mp3)
            except Exception:
                pass
    return None


def _transcribe_via_cloud_api(
    audio_path: str,
    groq_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    language: str = "ar"
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    gem_words = _transcribe_via_gemini_multimodal(audio_path, gemini_api_key=gemini_api_key)
    if gem_words:
        gem_words = apply_phrase_fixes_to_words(gem_words)
        return gem_words, split_words_into_micro_scenes(gem_words)

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


# ==============================================================================
# 7. الدمج الهجين بين محرك الجزائر (ar-DZ) وتوقيت faster-whisper
# ==============================================================================
def merge_ar_dz_with_whisper_timestamps(
    ar_dz_words: Optional[List[Dict[str, Any]]],
    whisper_words: List[Dict[str, Any]],
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    if ar_dz_words and len(ar_dz_words) >= max(3, int(len(whisper_words) * 0.75)):
        if whisper_words:
            dz_text = " ".join(w["word"] for w in ar_dz_words)
            wh_text = " ".join(w["word"] for w in whisper_words)
            prompt = (
                f"لدينا قراءتان لنفس التسجيل الصوتي بالدارجة الجزائرية:\n"
                f"القراءة الجزائرية (ar-DZ): \"{dz_text}\"\n"
                f"قراءة Whisper العام: \"{wh_text}\"\n"
                f"عدد كلمات القراءة الجزائرية هو {len(ar_dz_words)} كلمة.\n"
                "ادمج القراءتين لتصحيح أي كلمة غير مفهومة حسب سياق الفيديو العام، وأرجع النص الجزائري الصحيح فقط مفصولاً بمسافات."
            )
            merged_txt = query_hybrid_llm(
                prompt=prompt,
                system_prompt="أنت خبير في الدارجة الجزائرية وفهم سياق الكلام. أرجع النص المصحح فقط بدون أي شرح أو علامات تنصيص.",
                groq_api_key=groq_api_key,
                gemini_api_key=gemini_api_key,
                openai_api_key=openai_api_key,
                temperature=0.1,
                max_tokens=400
            )
            if merged_txt:
                clean_line = merged_txt.strip().strip("\"'")
                tokens = [normalize_algerian_word(t) for t in clean_line.split() if t.strip()]
                if len(tokens) == len(ar_dz_words):
                    for idx, tok in enumerate(tokens):
                        ar_dz_words[idx]["word"] = tok
        return apply_phrase_fixes_to_words(ar_dz_words)

    return apply_phrase_fixes_to_words(whisper_words)


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
        gemini_api_key=gemini_api_key,
        language=language or "ar"
    )
    if cloud_res is not None:
        words_list, micro_scenes = cloud_res
        _TRANSCRIPTION_CACHE[cache_key] = {"words": words_list, "sentences": micro_scenes}
        _LAST_EXTRACTED_TRANSCRIPT["words"] = words_list
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = micro_scenes
        return words_list, micro_scenes

    ar_dz_words = None
    if dialect_mode == "algerian_darija":
        ar_dz_words = _transcribe_via_google_ar_dz_chunks(audio_path)

    detected_device, detected_compute = get_optimal_device_settings()
    final_device = device if device is not None else detected_device
    final_compute = compute_type if compute_type is not None else detected_compute

    # إذا نجح محرك الجزائر السحابي المجاني (ar-DZ) على بيئة CPU المحدودة (مثل Streamlit Cloud)، نعتمد نتائجه مباشرة دون تحميل نموذج Whisper في الـ RAM!
    if ar_dz_words and len(ar_dz_words) >= 3 and final_device == "cpu":
        final_words = apply_phrase_fixes_to_words(ar_dz_words)
        micro_scenes = split_words_into_micro_scenes(final_words)
        if len(_TRANSCRIPTION_CACHE) > 2:
            _TRANSCRIPTION_CACHE.clear()
        _TRANSCRIPTION_CACHE[cache_key] = {"words": final_words, "sentences": micro_scenes}
        _LAST_EXTRACTED_TRANSCRIPT["words"] = final_words
        _LAST_EXTRACTED_TRANSCRIPT["sentences"] = micro_scenes
        _force_free_ram()
        return final_words, micro_scenes

    # على المعالج المركزي (CPU / Streamlit Cloud) نستخدم الموديل الرشيق base لتوفير 350MB من الـ RAM لمنع خطأ OOM في المرحلة 5
    eff_model_size = "base" if (final_device == "cpu" and model_size in ("small", "medium", "large-v3", "auto")) else model_size

    whisper_words: List[Dict[str, Any]] = []
    try:
        model = _get_or_load_whisper_model(eff_model_size, final_device, final_compute)
        target_language = None if (language == "auto" or not language) else language

        segments, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            language=target_language,
            initial_prompt=ALGERIAN_DARIJA_INITIAL_PROMPT,
            beam_size=2 if final_device == "cpu" else 5,
            best_of=2 if final_device == "cpu" else 5,
            condition_on_previous_text=False,
            compression_ratio_threshold=3.2,
            log_prob_threshold=-1.6,
            no_speech_threshold=0.85,
            vad_filter=vad_filter,
            vad_parameters=dict(threshold=0.25, min_speech_duration_ms=100, min_silence_duration_ms=650, speech_pad_ms=350)
        )

        for seg in segments:
            if seg.words:
                for word_obj in seg.words:
                    cleaned_word = normalize_algerian_word(word_obj.word)
                    if cleaned_word:
                        whisper_words.append({
                            "word": cleaned_word,
                            "start": round(word_obj.start, 3),
                            "end": round(word_obj.end, 3),
                            "probability": round(word_obj.probability, 3)
                        })

        del segments
        del model
        _WHISPER_MODEL_CACHE.clear()
        _force_free_ram()
    except Exception as wh_err:
        logger.warning(f"Whisper local fallback notice: {wh_err}")
        _WHISPER_MODEL_CACHE.clear()
        _force_free_ram()

    final_words = merge_ar_dz_with_whisper_timestamps(
        ar_dz_words=ar_dz_words,
        whisper_words=whisper_words,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key
    )

    micro_scenes = split_words_into_micro_scenes(final_words)

    _TRANSCRIPTION_CACHE[cache_key] = {
        "words": final_words,
        "sentences": micro_scenes
    }
    _LAST_EXTRACTED_TRANSCRIPT["words"] = final_words
    _LAST_EXTRACTED_TRANSCRIPT["sentences"] = micro_scenes

    return final_words, micro_scenes


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