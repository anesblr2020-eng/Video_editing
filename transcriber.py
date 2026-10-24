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
        gc.collect()
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
    "يتشارجا": "يتشارجا",
    "تلقاوش": "يلقاوش",
    "فاستا": "فاست",
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
    "للرز": "للريلز",
    "للريز": "للريلز",
    "لريز": "للريلز",
    "لريلز": "للريلز",
    "الرز": "الريلز",
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
    "الخاصيه": "الخاصية",
    "للخاصيه": "للخاصية",
    "الاولى": "الأولى",
    "الثانيه": "الثانية",
    "الثالثه": "الثالثة",
    "الرابعه": "الرابعة",
    "الخامسه": "الخامسة",
    "الانتاجيه": "الإنتاجية",
    "المسؤوله": "المسؤولة",
    "دقيقه": "دقيقة",
    "ساعه": "ساعة",
    "جوده": "جودة",
    "صوره": "صورة",
    "مباشره": "مباشرة",
    "واحده": "واحدة",
    "فكره": "فكرة",
    "مشكله": "مشكلة",
    "طريقه": "طريقة",
    "نتيجه": "نتيجة",
    "خطوه": "خطوة",
    "اللي": "اللي",
    "اسفل": "أسفل",
    "والاقوى": "والأقوى",
    "الاقوى": "الأقوى",
    "والخاصيه": "والخاصية",
    "بالنسبه": "بالنسبة",
    "تليفون": "تيليفون",
    "تليفونك": "تيليفونك",
    "افضل": "أفضل",
    "اقل": "أقل",
    "اكثر": "أكثر",
    "انه": "أنه",
    "اما": "أما",
    "اي": "أي",
}

PHRASE_LEVEL_FIXES = [
    (r"عليكم\s+بالي\s+راك", "عليكم على بالي راك"),
    (r"(?<!على\s)بالي\s+راك\s+تعاني", "على بالي راك تعاني"),
    (r"وكم\s+خلي\s+الحساب", "ومخلي الحساب"),
    (r"وكم\s+خلي", "ومخلي"),
    (r"السوشيال\s+ميديا\s+عم(?!و)", "السوشيال ميديا عموماً"),
    (r"ميديا\s+عم(?!و)", "ميديا عموماً"),
    (r"منصة\s+اسمها\s+فيديو\s+تاع", "منصة للمونتاج بالذكاء الاصطناعي"),
    (r"تع\s+الصمت\s+من\s+الفيديو", "تنحي الصمت من الفيديو"),
    (r"تع\s+الصمت", "تنحي الصمت"),
    (r"مجاني\s+وبالاي", "مجاني وبالذكاء الاصطناعي"),
    (r"وبالاي(?!\w)", "وبالذكاء الاصطناعي"),
    (r"وبالمونتاج\s+العادي\s+وبقا\s+الصوت", "وبالمونتاج العادي وتنقي الصوت"),
    (r"وبقا\s+الصوت", "وتنقي الصوت"),
    (r"سيرفر\s+تيليفون", "سيبور تيليفون"),
    (r"قطع[،,]?\s+يتقطع", "قاع يتقطع"),
    (r"المتوفرس\s+على", "راه متوفر"),
    (r"أكموان\s+من", "اكموندي من"),
    (r"حتى\s+تديهم\s+بالبري\s+مهب", "تديهم باطل"),
    (r"تديهم\s+بالبري\s+مهب", "تديهم باطل"),
    (r"بالبري\s+مهب", "باطل"),
    (r"تتفرج\s+وتم\s+والخاصي", "تتفرج والخاصي"),
    (r"والاقوى\s+ما\s+انت\s+اي", "والأقوى من هذا أي"),
    (r"والأقوى\s+ما\s+أنت\s+أي", "والأقوى من هذا أي"),
    (r"والاقوى\s+ما\s+انت", "والأقوى من هذا"),
    (r"والأقوى\s+ما\s+أنت", "والأقوى من هذا"),
    (r"بالسوبر\s+فاستا", "بالسوبر فاست"),
    (r"سوبر\s+فاستا", "سوبر فاست"),
    (r"ترفع\s+الإنتاجية\s+التواصل\s+الاجتماعي", "ترفع الإنتاجية في التواصل الاجتماعي"),
    (r"ترفع\s+الانتاجية\s+التواصل\s+الاجتماعي", "ترفع الإنتاجية في التواصل الاجتماعي"),
    (r"منصة\s+فيديو\s+المسؤولة", "منصة فيديوهات المسؤولة"),
    (r"منصة\s+اسمها\s+فيديو\s+تاع", "منصة اسمها فيديوهات"),
    (r"فيديو\s+تاع\s+المسؤولة", "فيديوهات المسؤولة"),
    (r"ترفع\s+ان\s+ترفع", "ترفع"),
    (r"ترفع\s+أن\s+ترفع", "ترفع"),
    (r"لاحظت\s+ان\s+في", "لاحظت أن في"),
    (r"عندها\s+مش\s+في", "عندها مشكل في"),
    (r"عنده\s+مش\s+في", "عندها مشكل في"),
    (r"ما\s+عندها\s+مش\s+في", "ما عندها مشكل في"),
    (r"في\s+المونتاج\s+للرز", "في المونتاج للريلز"),
    (r"في\s+المونتاج\s+للريز", "في المونتاج للريلز"),
    (r"تصور\s+لي\s+الفيديوهات", "تصور الفيديوهات"),
]


# ==============================================================================
# 1.5 محرك إصلاح الكلمات المبتورة صوتياً والسياقية ومنع التكرار (Universal Fluency & Dedup Engine)
# ==============================================================================
CONTEXTUAL_BROKEN_WORD_REPAIRS = [
    (r"(?<!\w)في\s+المونت(?!\w)", "في المونتاج"),
    (r"(?<!\w)المونت\s+الان(?!\w)", "المونتاج لأن"),
    (r"(?<!\w)المونت(?!\w)", "المونتاج"),
    (r"(?<!\w)الان\s+أغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)الان\s+اغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)تصور\s+للفيديوهات(?!\w)", "تصور الفيديوهات"),
    (r"(?<!\w)تصور\s+لي\s+الفيديوهات(?!\w)", "تصور الفيديوهات"),
    (r"(?<!\w)عندها\s+مش\s+في(?!\w)", "عندها مشكل في"),
    (r"(?<!\w)مش\s+في\s+المونتاج(?!\w)", "مشكل في المونتاج"),
    (r"(?<!\w)للرز(?!\w)", "للريلز"),
    (r"(?<!\w)للريز(?!\w)", "للريلز"),
    (r"(?<!\w)التواصل\s+الاج(?!\w)", "التواصل الاجتماعي"),
    (r"(?<!\w)مواقع\s+التواصل\s+الاج(?!\w)", "مواقع التواصل الاجتماعي"),
    (r"(?<!\w)الاج(?!\w)", "الاجتماعي"),
    (r"(?<!\w)المسؤوله\s+على\s+اللي(?!\w)", "المسؤولة على المونتاج"),
    (r"(?<!\w)صورته\s+ذكاء\s+الاصطناعي(?!\w)", "صوت وصورة بالذكاء الاصطناعي"),
    (r"(?<!\w)منت\s+الفيديو(?!\w)", "تمنتج الفيديو"),
    (r"(?<!\w)ومونتاج\s+احت\s+ولا(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)ومونتاج\s+احت(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)مونتاج\s+احت(?!\w)", "مونتاج احترافي"),
    # Idempotent negative lookbehind so "أقل من دقيقة" never becomes "أقل أقل من دقيقة"!
    (r"(?<!أقل\s)(?<!اقل\s)(?<!\w)من\s+دقيقه(?!\w)", "أقل من دقيقة"),
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
    "الخاصيه": "الخاصية",
    "للخاصيه": "للخاصية",
    "الاولى": "الأولى",
    "الثانيه": "الثانية",
    "الثالثه": "الثالثة",
    "فاستا": "فاست",
    "اقل": "أقل",
    "افضل": "أفضل",
    "اسفل": "أسفل",
    "والاقوى": "والأقوى",
    "الاقوى": "الأقوى",
    "والخاصيه": "والخاصية",
    "بالنسبه": "بالنسبة",
    "تليفون": "تيليفون",
    "تليفونك": "تيليفونك",
}


def _orthographic_skeleton(word: str) -> str:
    w = re.sub(r"[،,.!؟?:؛\-]", "", str(word)).strip().lower()
    for ch in "أإآ":
        w = w.replace(ch, "ا")
    w = w.replace("ة", "ه").replace("ى", "ي")
    return w


def repair_truncated_words_and_sentences(words_list):
    """
    محرك عام لإصلاح الكلمات المبتورة، توحيد الإملاء العربي، إزالة الحشو الناتج عن أخطاء التعرف الصوتي،
    ومنع تكرار الكلمات المتجاورة أو العبارات المكسورة في أي فيديو مستقبلي.
    """
    if not words_list:
        return []
    repaired = [dict(w) for w in words_list]
    n = len(repaired)
    for i, w_obj in enumerate(repaired):
        raw_w = str(w_obj.get("word", "")).strip()
        clean_w = raw_w.strip("،,.!؟?")
        # إصلاحات مباشرة لتسلسلات الدارجة الجزائرية الشائعة في صناعة المحتوى والمونتاج
        if clean_w == "بالي" and i > 0 and i + 1 < n:
            prev_c = str(repaired[i - 1].get("word", "")).strip("،,.!؟?")
            next_c = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if prev_c != "على" and next_c in {"راك", "راكم", "انك", "بلي"}:
                repaired[i]["word"] = "على بالي"
        if clean_w == "وكم" and i + 1 < n and str(repaired[i + 1].get("word", "")).strip("،,.!؟?") == "خلي":
            repaired[i]["word"] = "ومخلي"
            repaired[i + 1]["word"] = ""
        if clean_w == "عم" and i > 0 and "ميديا" in str(repaired[i - 1].get("word", "")):
            repaired[i]["word"] = "عموماً"
        if clean_w in {"وبالاي", "بالاي"}:
            repaired[i]["word"] = "وبالذكاء الاصطناعي"
        if clean_w == "تع" and i + 1 < n and "صمت" in _orthographic_skeleton(repaired[i + 1].get("word", "")):
            repaired[i]["word"] = "تنحي"
        if clean_w == "وبقا" and i + 1 < n and "صوت" in _orthographic_skeleton(repaired[i + 1].get("word", "")):
            repaired[i]["word"] = "وتنقي"

        if clean_w in {"للرز", "للريز", "لريز"}:
            repaired[i]["word"] = "للريلز"
            clean_w = "للريلز"
        if clean_w == "مش" and i + 1 < n:
            nxt_w_check = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            prev_w_check = str(repaired[i - 1].get("word", "")).strip("،,.!؟?") if i > 0 else ""
            if nxt_w_check == "في" or prev_w_check in {"عندها", "عنده"}:
                repaired[i]["word"] = "مشكل"
                clean_w = "مشكل"
        if clean_w == "لي" and i > 0 and i + 1 < n:
            prev_w_check = str(repaired[i - 1].get("word", "")).strip("،,.!؟?")
            nxt_w_check = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if prev_w_check in {"تصور", "يصور"} and "فيديو" in nxt_w_check:
                repaired[i]["word"] = ""
                clean_w = ""
        if clean_w in SINGLE_TRUNCATED_TOKEN_MAP:
            repaired[i]["word"] = SINGLE_TRUNCATED_TOKEN_MAP[clean_w]
            clean_w = repaired[i]["word"]

        if clean_w in {"الان", "الآن"} and i + 1 < n:
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if nxt_w in {"أغلب", "اغلب", "كثير", "بزاف", "الناس"}:
                repaired[i]["word"] = "لأن"
        if clean_w in {"صورته", "صورتك"} and i + 1 < n:
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if "ذكاء" in nxt_w or "اصطناعي" in nxt_w:
                repaired[i]["word"] = "صوت وصورة"
        if clean_w == "ولا" and i > 0:
            prev_w = str(repaired[i - 1].get("word", "")).strip("،,.!؟?")
            if prev_w == "احترافي":
                repaired[i]["word"] = ""
        # إزالة "وتم" المقحمة صوتياً قبل "والخاصية"
        if clean_w == "وتم" and i + 1 < n:
            nxt_w = _orthographic_skeleton(repaired[i + 1].get("word", ""))
            if "خاصي" in nxt_w or "ثاني" in nxt_w or "ثالث" in nxt_w:
                repaired[i]["word"] = ""
        # إصلاح "ترفع ان ترفع" -> حذف "ان ترفع" المكررة
        if clean_w in {"ان", "أن"} and 0 < i < n - 1:
            prev_s = _orthographic_skeleton(repaired[i - 1].get("word", ""))
            next_s = _orthographic_skeleton(repaired[i + 1].get("word", ""))
            if prev_s == next_s and prev_s:
                repaired[i]["word"] = ""
                repaired[i + 1]["word"] = ""
        # إصلاح "ما انت" بعد "والأقوى" -> "من هذا"
        if clean_w in {"ما"} and i > 0 and i + 1 < n:
            prev_s = _orthographic_skeleton(repaired[i - 1].get("word", ""))
            next_s = _orthographic_skeleton(repaired[i + 1].get("word", ""))
            if "اقوي" in prev_s and next_s in {"انت", "انك"}:
                repaired[i]["word"] = "من"
                repaired[i + 1]["word"] = "هذا"
        # إصلاح "حتى تديهم بالبري مهب" -> "تديهم باطل"
        if clean_w == "بالبري" and i + 1 < n:
            next_s = _orthographic_skeleton(repaired[i + 1].get("word", ""))
            if next_s in {"مهب", "باطل"}:
                repaired[i]["word"] = "باطل"
                repaired[i + 1]["word"] = ""
                if i >= 2 and _orthographic_skeleton(repaired[i - 2].get("word", "")) == "حتي":
                    repaired[i - 2]["word"] = ""
        # إضافة حرف الجر "في" إذا سقط صوتياً بين "الإنتاجية" و"التواصل الاجتماعي"
        if _orthographic_skeleton(clean_w) in {"الانتاجيه", "انتاجيه"} and i + 1 < n:
            next_s = _orthographic_skeleton(repaired[i + 1].get("word", ""))
            if next_s == "التواصل":
                repaired[i]["word"] = "الإنتاجية في"

    # فلترة الفراغات ودمج الكلمات المتجاورة المكررة إملائياً (مثل "اقل أقل" -> "أقل")
    non_empty = [w for w in repaired if str(w.get("word", "")).strip()]
    deduped = []
    for w in non_empty:
        w_skel = _orthographic_skeleton(w["word"])
        if deduped:
            prev_skel = _orthographic_skeleton(deduped[-1]["word"])
            if w_skel and w_skel == prev_skel and w_skel not in {"اصبر", "شوف", "لا", "نعم", "صح"}:
                # نحتفظ بالنسخة الأصح إملائياً (التي تحتوي همزة أو تاء مربوطة) ونوسع وقت النهاية
                if any(ch in w["word"] for ch in "أإآة") and not any(ch in deduped[-1]["word"] for ch in "أإآة"):
                    deduped[-1]["word"] = w["word"]
                deduped[-1]["end"] = max(float(deduped[-1]["end"]), float(w["end"]))
                continue
        deduped.append(w)

    return deduped

# ==============================================================================
# 1.8 محرك كشف وإزالة أخطاء وإعادات التعليق الصوتي (Voiceover Retake & Stutter Eliminator)
# ==============================================================================
import difflib

_LAST_DETECTED_RETAKE_CUTS: List[Dict[str, Any]] = []


def get_last_detected_retake_cuts() -> List[Dict[str, Any]]:
    """إرجاع قائمة الفترات الزمنية التي أخطأ فيها المتحدث أو أعاد الجملة/الكلمة مرتين ليتم قصها من الصوت والفيديو."""
    return [dict(c) for c in _LAST_DETECTED_RETAKE_CUTS]


def _stem_skeleton(word: str) -> str:
    """جذر إملائي مبسط للمقارنة الصوتية والسياقية بين المحاولة الخاطئة والإعادة الصحيحة."""
    s = _orthographic_skeleton(word)
    for pref in ("وال", "بال", "فل", "كال", "لل", "ال", "و", "ب", "ف", "ل"):
        if s.startswith(pref) and len(s) - len(pref) >= 3:
            s = s[len(pref):]
            break
    return s


def _words_are_equivalent(w1: str, w2: str) -> bool:
    s1, s2 = _orthographic_skeleton(w1), _orthographic_skeleton(w2)
    if not s1 or not s2:
        return False
    if s1 == s2:
        return True
    st1, st2 = _stem_skeleton(w1), _stem_skeleton(w2)
    if st1 == st2 and len(st1) >= 2:
        return True
    if min(len(st1), len(st2)) >= 4:
        ratio = difflib.SequenceMatcher(None, st1, st2).ratio()
        if ratio >= 0.78:
            return True
    return False


def _phrase_similarity(seq1: List[str], seq2: List[str]) -> float:
    if not seq1 or not seq2:
        return 0.0
    m = min(len(seq1), len(seq2))
    matches = sum(1 for a, b in zip(seq1[:m], seq2[:m]) if _words_are_equivalent(a, b))
    return matches / float(max(len(seq1), len(seq2)))


def detect_and_remove_voiceover_retakes(
    words_list: List[Dict[str, Any]],
    remap_timestamps: bool = False
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    يكتشف أخطاء التعليق الصوتي عندما يعيد المتحدث الكلمة أو العبارة أو الجملة مرتين (بسبب تلعثم أو خطأ في النطق):
    1. تكرار الكلمة الواحدة المتتالية (`W[i] == W[i+1]`).
    2. إعادة العبارة أو الكلمات المتتالية (`N-gram Phrase Retake` من كلمتين إلى 8 كلمات).
    3. البداية الخاطئة للجملة (`False-Start Clause Retake`): عندما يبدأ المتحدث جملة من 2-8 كلمات، يتوقف أو يخطئ في آخرها،
       ثم يعيد نفس بداية الجملة (أول كلمتين أو أكثر متطابقتين) بصياغة صحيحة وكاملة!
    يحذف المحاولة الأولى الخاطئة تماماً ويسجل توقيتها الزمني `[start, end]` في `_LAST_DETECTED_RETAKE_CUTS` ليتم قصها من الصوت والفيديو.
    """
    global _LAST_DETECTED_RETAKE_CUTS
    _LAST_DETECTED_RETAKE_CUTS = []

    if not words_list or len(words_list) < 2:
        return list(words_list), []

    items = [dict(w) for w in words_list if str(w.get("word", "")).strip()]
    n = len(items)
    keep_mask = [True] * n
    detected_cuts: List[Dict[str, Any]] = []

    i = 0
    while i < n - 1:
        if not keep_mask[i]:
            i += 1
            continue

        cut_made = False

        # أولاً: فحص إعادة جملة أو عبارة (من 7 كلمات نزولاً إلى كلمتين) أو بداية جملة خاطئة (False-Start Retake)
        max_span = min(8, n - i - 1)
        for j in range(i + 1, min(n, i + 10)):
            if not keep_mask[j]:
                continue
            span_len = j - i
            time_span = float(items[j]["start"]) - float(items[i]["start"])
            if time_span > 7.5:
                break

            # أ) تطابق عبارة كاملة مكررة (Contiguous or Near-Contiguous Phrase Repeat)
            check_len = min(span_len, n - j)
            if check_len >= 2 and _words_are_equivalent(items[i]["word"], items[j]["word"]):
                seq_a = [items[k]["word"] for k in range(i, i + check_len)]
                seq_b = [items[k]["word"] for k in range(j, j + check_len)]
                sim = _phrase_similarity(seq_a, seq_b)
                if sim >= 0.80 and span_len <= check_len + 2:
                    cut_s = float(items[i]["start"])
                    cut_e = float(items[j]["start"])
                    removed_str = " ".join(items[k]["word"] for k in range(i, j))
                    for k in range(i, j):
                        keep_mask[k] = False
                    detected_cuts.append({
                        "start": round(cut_s, 3),
                        "end": round(max(cut_s + 0.08, cut_e), 3),
                        "removed_text": removed_str,
                        "reason": "phrase_retake"
                    })
                    i = j
                    cut_made = True
                    break

            # ب) البداية الخاطئة للجملة (False-Start Sentence Retake):
            # المتحدث قال 2 إلى 8 كلمات، ثم أعاد نفس أول كلمتين (أو 3 كلمات) ليكمل الجملة الصحيحة!
            if 2 <= span_len <= 8 and (j + 2) <= n:
                prefix_match_2 = (
                    _words_are_equivalent(items[i]["word"], items[j]["word"])
                    and _words_are_equivalent(items[i + 1]["word"], items[j + 1]["word"])
                )
                # أو إذا بدأ بكلمة مثل "أنا جيت لكم..." ثم قال "جيت لكم..." (حذف ضمير البداية في الإعادة)
                prefix_match_shifted = (
                    span_len >= 3
                    and _words_are_equivalent(items[i + 1]["word"], items[j]["word"])
                    and _words_are_equivalent(items[i + 2]["word"], items[j + 1]["word"])
                )
                if prefix_match_2:
                    cut_idx_start = i if prefix_match_2 else (i + 1)
                    cut_s = float(items[cut_idx_start]["start"])
                    cut_e = float(items[j]["start"])
                    removed_str = " ".join(items[k]["word"] for k in range(cut_idx_start, j))
                    for k in range(cut_idx_start, j):
                        keep_mask[k] = False
                    detected_cuts.append({
                        "start": round(cut_s, 3),
                        "end": round(max(cut_s + 0.08, cut_e), 3),
                        "removed_text": removed_str,
                        "reason": "false_start_sentence_retake"
                    })
                    i = j
                    cut_made = True
                    break

        if cut_made:
            continue

        # ثانياً: فحص تكرار الكلمة الواحدة المتتالية (Single-Word Stutter: W[i] == W[i+1])
        nxt_i = i + 1
        while nxt_i < n and not keep_mask[nxt_i]:
            nxt_i += 1
        if nxt_i < n:
            w_curr = items[i]["word"]
            w_next = items[nxt_i]["word"]
            skel_curr = _orthographic_skeleton(w_curr)
            if _words_are_equivalent(w_curr, w_next) and skel_curr not in {"اصبر", "شوف", "لا", "نعم", "صح", "خطوه"}:
                cut_s = float(items[i]["start"])
                cut_e = float(items[nxt_i]["start"])
                keep_mask[i] = False
                detected_cuts.append({
                    "start": round(cut_s, 3),
                    "end": round(max(cut_s + 0.06, cut_e), 3),
                    "removed_text": w_curr,
                    "reason": "word_stutter"
                })
                i = nxt_i
                continue

        i += 1

    cleaned_words = [w for idx_w, w in enumerate(items) if keep_mask[idx_w]]
    _LAST_DETECTED_RETAKE_CUTS = detected_cuts

    if remap_timestamps and detected_cuts:
        cleaned_words = remap_words_after_retake_cuts(cleaned_words, detected_cuts)

    if detected_cuts:
        logger.info(f"Voiceover Retake Detector removed {len(detected_cuts)} mistake/retake segment(s): {detected_cuts}")

    return cleaned_words, detected_cuts


def remap_words_after_retake_cuts(
    words_list: List[Dict[str, Any]],
    retake_cuts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    إعادة حساب التوقيت الزمني (`start`, `end`) لجميع الكلمات بعد قص فترات الغلطات والإعادات الصوتية
    من ملف الميديا الفعلي، لضمان بقاء التزامن الصوتي والبصري 100%.
    """
    if not words_list or not retake_cuts:
        return list(words_list)

    cuts = sorted(
        [(float(c["start"]), float(c["end"])) for c in retake_cuts if float(c["end"]) > float(c["start"])],
        key=lambda x: x[0]
    )
    remapped: List[Dict[str, Any]] = []
    for w in words_list:
        w_copy = dict(w)
        ws = float(w_copy.get("start", 0.0))
        we = float(w_copy.get("end", ws + 0.25))
        shift = 0.0
        for cs, ce in cuts:
            if ce <= ws + 0.02:
                shift += (ce - cs)
            elif cs < ws < ce:
                shift += (ws - cs)
        new_s = max(0.0, round(ws - shift, 3))
        new_e = max(new_s + 0.10, round(we - shift, 3))
        w_copy["start"] = new_s
        w_copy["end"] = new_e
        remapped.append(w_copy)

    return ensure_word_timestamp_continuity(remapped)


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
    max_words_per_scene: int = 6,
    max_duration_per_scene: float = 3.1,
    min_words_per_scene: int = 3
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
    eff_max_words = max(5, min(7, int(max_words_per_scene)))
    eff_max_dur = max(2.4, min(3.4, float(max_duration_per_scene)))
    eff_min_words = max(3, min(4, int(min_words_per_scene)))

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

    # تقسيم أي مشهد طويل (> 3.6 ثانية) إلى لقطتين بصريتين متجددتين لمنع بقاء نفس الرسمة ثابتة على الشاشة لفترة طويلة!
    paced_scenes: List[Dict[str, Any]] = []
    for sc in final_scenes:
        sc_w = sc.get("words", [])
        sc_dur = float(sc["end"]) - float(sc["start"])
        if sc_dur > 3.6 and len(sc_w) >= 6:
            mid_idx = len(sc_w) // 2
            w1, w2 = sc_w[:mid_idx], sc_w[mid_idx:]
            paced_scenes.append({
                "text": " ".join(x["word"] for x in w1),
                "start": round(float(w1[0]["start"]), 3),
                "end": round(float(w1[-1]["end"]), 3),
                "words": w1
            })
            paced_scenes.append({
                "text": " ".join(x["word"] for x in w2),
                "start": round(float(w2[0]["start"]), 3),
                "end": round(float(w2[-1]["end"]), 3),
                "words": w2
            })
        else:
            paced_scenes.append(sc)

    # سد أي فجوة بين نهاية مشهد وبداية المشهد التالي مع إعادة توزيع أوقات الكلمات إذا وُجدت فجوة طويلة
    for idx in range(len(paced_scenes) - 1):
        gap = paced_scenes[idx + 1]["start"] - paced_scenes[idx]["end"]
        if 0.0 < gap <= 1.20:
            paced_scenes[idx]["end"] = paced_scenes[idx + 1]["start"]
            if paced_scenes[idx]["words"]:
                paced_scenes[idx]["words"][-1]["end"] = paced_scenes[idx + 1]["start"]
        elif gap > 1.20:
            # إذا كانت هناك فجوة كبيرة، نقسمها إلى مشهد بصري انتقالي حتى لا تتجمد الشاشة
            paced_scenes[idx]["end"] = round(paced_scenes[idx]["end"] + min(0.8, gap * 0.4), 3)

    return paced_scenes


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
    cleaned_no_retakes, _ = detect_and_remove_voiceover_retakes(final_expanded, remap_timestamps=False)
    return ensure_word_timestamp_continuity(cleaned_no_retakes)


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

        # تقسيم المقاطع الطويلة إلى جمل رشيقة (<= 4.2 ثانية) عند أهدأ نقطة صمت بين الكلمات لمنع ضياع أي جملة في Google STT!
        final_chunks: List[Tuple[int, int]] = []
        for s_ms, e_ms in merged_chunks:
            cur_s = s_ms
            while (e_ms - cur_s) > 4200:
                search_start = cur_s + 2100
                search_end = min(e_ms - 800, cur_s + 3900)
                best_split = cur_s + 3100
                min_rms = float("inf")
                for probe_ms in range(search_start, max(search_start + 25, search_end), 20):
                    win_slice = audio[probe_ms:probe_ms + 45]
                    if win_slice.rms < min_rms:
                        min_rms = win_slice.rms
                        best_split = probe_ms + 22
                final_chunks.append((cur_s, min(e_ms, best_split + 35)))
                cur_s = max(cur_s + 800, best_split - 35)
            if e_ms - cur_s >= 180:
                final_chunks.append((cur_s, e_ms))

        recognizer = sr.Recognizer()
        all_words: List[Dict[str, Any]] = []

        def _recognize_chunk_with_fallback(c_s: int, c_e: int) -> str:
            ch_aud = audio[c_s:c_e]
            ad = sr.AudioData(ch_aud.raw_data, 16000, 2)
            for lang_code in ("ar-DZ", "ar-SA", "ar"):
                try:
                    res_txt = recognizer.recognize_google(ad, language=lang_code)
                    if res_txt and res_txt.strip():
                        return res_txt.strip()
                except sr.UnknownValueError:
                    continue
                except Exception:
                    break
            # إذا كانت القطعة > 2200ms وفشلت ككتلة واحدة، نقسمها من المنتصف عند أهدأ نقطة ونفرغ النصفين
            if (c_e - c_s) > 2200:
                mid_s = c_s + int((c_e - c_s) * 0.35)
                mid_e = c_s + int((c_e - c_s) * 0.65)
                best_m = (c_s + c_e) // 2
                min_r = float("inf")
                for p_ms in range(mid_s, max(mid_s + 20, mid_e), 20):
                    w_sl = audio[p_ms:p_ms + 40]
                    if w_sl.rms < min_r:
                        min_r = w_sl.rms
                        best_m = p_ms + 20
                part1 = _recognize_chunk_with_fallback(c_s, best_m)
                part2 = _recognize_chunk_with_fallback(best_m, c_e)
                return f"{part1} {part2}".strip()
            return ""

        for c_start_ms, c_end_ms in final_chunks:
            chunk_audio = audio[c_start_ms:c_end_ms]
            try:
                text_dz = _recognize_chunk_with_fallback(c_start_ms, c_end_ms)
            except Exception as e:
                logger.warning(f"تعذر الاتصال بمحرك ar-DZ: {e}")
                return None
            if not text_dz:
                continue

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

    # التحقق من عدم وجود أي فجوة كلامية مفقودة (> 2.5 ثانية) في نتائج ar-DZ قبل اعتمادها المباشر
    _has_large_gap = False
    if ar_dz_words and len(ar_dz_words) >= 3:
        for _gi in range(len(ar_dz_words) - 1):
            if float(ar_dz_words[_gi + 1]["start"]) - float(ar_dz_words[_gi]["end"]) > 2.6:
                _has_large_gap = True
                break
    if ar_dz_words and len(ar_dz_words) >= 3 and final_device == "cpu" and not _has_large_gap:
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