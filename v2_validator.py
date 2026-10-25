"""
v2/validator.py — المدقق الدلالي الصارم (Semantic Validator).
يضمن:
1. إذا كانت confidence < 0.7 للتطابق مع الكلام -> يتحول القالب فوراً إلى kinetic_hook.
2. منع أي رقم غير منطوق فعلياً في speech.
3. منع جميع عبارات الحشو من القائمة السوداء (+44، Pro Tips، أداء احترافي، AI STUDIO READY، 10x FAST، 4K 60FPS).
4. منع تكرار نفس القالب أو نفس الكلمات المفتاحية في مشهدين متتاليين.
5. منع تكرار نص الكابشن حرفياً في الكلمات المفتاحية العلوية.
"""
import re
from typing import List, Dict, Any, Tuple

BLACKLIST_PATTERNS = [
    r"\+44",
    r"44\+",
    r"\+84",
    r"84\+",
    r"pro\s*tips?",
    r"أداء\s*احترافي",
    r"اداء\s*احترافي",
    r"ai\s*studio\s*ready",
    r"ai\s*auto\s*studio",
    r"10x\s*fast",
    r"4k\s*60fps",
    r"max\s*2\.4k",
    r"جودة\s*استوديو",
]

ALLOWED_TEMPLATES = {
    "kinetic_hook",
    "concept_icon",
    "big_number",
    "phone_reel_mockup",
    "before_after",
    "checklist",
    "steps_flow",
    "versus",
    "fullscreen_image",
    "cta_end",
}

SPOKEN_NUMBER_MAP = {
    "واحد": "1", "أول": "1", "الأول": "1",
    "زوج": "2", "اثنين": "2", "ثاني": "2", "الثاني": "2",
    "ثلاثة": "3", "ثلاث": "3", "ثالث": "3",
    "أربعة": "4", "خمسة": "5", "عشرة": "10",
    "مية": "100%", "مائة": "100%",
}


def contains_blacklisted_text(text: str) -> bool:
    if not text:
        return False
    low = text.lower().strip()
    for pat in BLACKLIST_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def extract_spoken_numbers(speech: str) -> List[str]:
    found = re.findall(r"\d+(?:[.,]\d+)?%?", speech)
    for word, num_str in SPOKEN_NUMBER_MAP.items():
        if word in speech and num_str not in found:
            found.append(num_str)
    return found


def validate_scene_plan(scenes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    يدقق خطة المشاهد (Scene Plan) ويصلح أي مخالفة لقواعد الجودة الصارمة،
    ويعيد (المشاهد المدققة، سجل التدقيق).
    """
    validated: List[Dict[str, Any]] = []
    audit_log: List[str] = []
    prev_template = None
    prev_kw_joined = ""

    for idx, sc in enumerate(scenes):
        scene = dict(sc)
        speech = str(scene.get("speech", "")).strip()
        tpl = str(scene.get("template", "kinetic_hook")).strip()
        conf = float(scene.get("confidence", 0.0))

        # 1. التحقق من أن القالب ضمن القوالب العشرة المعتمدة
        if tpl not in ALLOWED_TEMPLATES:
            audit_log.append(f"Scene #{idx+1}: Unknown template '{tpl}' -> fallback to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 2. قاعدة الثقة الصارمة: confidence < 0.7 -> kinetic_hook فوراً
        if conf < 0.70 and tpl != "kinetic_hook":
            audit_log.append(f"Scene #{idx+1}: Low confidence ({conf:.2f} < 0.70) for '{tpl}' -> downgraded to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 3. التحقق من الأرقام المنطوقة فقط
        spoken_nums = extract_spoken_numbers(speech)
        raw_nums = [str(n) for n in scene.get("numbers", []) if str(n) in spoken_nums]
        scene["numbers"] = raw_nums
        if tpl == "big_number" and not raw_nums:
            audit_log.append(f"Scene #{idx+1}: 'big_number' requested without spoken number in '{speech}' -> downgraded to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 4. تنظيف الكلمات المفتاحية من القائمة السوداء ومن تكرار الكابشن
        raw_keywords = [str(k).strip() for k in scene.get("keywords", []) if str(k).strip()]
        clean_keywords = []
        speech_tokens = {
            re.sub(r"[^\w\u0600-\u06FF]", "", t).strip().lower()
            for t in speech.split()
        }
        speech_tokens.discard("")
        for kw in raw_keywords:
            if contains_blacklisted_text(kw):
                audit_log.append(f"Scene #{idx+1}: Removed blacklisted keyword '{kw}'")
                continue
            # Reject titles that are unrelated to this scene's spoken clause.
            kw_tokens = {
                re.sub(r"[^\w\u0600-\u06FF]", "", t).strip().lower()
                for t in kw.split()
            }
            kw_tokens.discard("")
            if kw_tokens and not (kw_tokens & speech_tokens):
                audit_log.append(f"Scene #{idx+1}: Removed ungrounded headline '{kw}'")
                continue
            # منع وجود أرقام غير منطوقة داخل الكلمات المفتاحية
            kw_digits = re.findall(r"\d+%?", kw)
            if any(d not in spoken_nums for d in kw_digits):
                audit_log.append(f"Scene #{idx+1}: Removed ungrounded number in keyword '{kw}'")
                continue
            clean_keywords.append(kw)

        if not clean_keywords:
            # Ground fallback labels in actual speech; never substitute generic marketing copy.
            filler = {"السلام", "عليكم", "على", "بالي", "بلي", "راك", "ما", "في", "من", "مع", "باش", "لي", "لك", "هذا", "هاذ", "اللي", "كاين", "تاع", "عموما", "عمومًا", "يعني", "وش", "واش"}
            tokens = [
                t.strip("،,.;:!?؟") for t in speech.split()
                if len(re.sub(r"[^\w\u0600-\u06FF]", "", t)) > 2
                and re.sub(r"[^\w\u0600-\u06FF]", "", t).lower() not in filler
            ][:3]
            if not tokens:
                tokens = speech.split()[:3]
            clean_keywords = [" ".join(tokens)] if tokens else []
            audit_log.append(f"Scene #{idx+1}: Rebuilt headline from spoken words because no grounded keyword remained.")

        # ضمان عدم تطابق الكلمات المفتاحية العلوية حرفياً مع جملة الكابشن الكاملة
        kw_joined = " ".join(clean_keywords)
        if len(speech.split()) > 3 and kw_joined.strip() == speech.strip():
            clean_keywords = clean_keywords[:2]
            kw_joined = " ".join(clean_keywords)

        # 5. منع تكرار نفس القالب في مشهدين متتاليين
        if prev_template is not None and tpl == prev_template:
            fallback_order = ["concept_icon", "kinetic_hook", "versus", "before_after", "checklist"]
            for alt in fallback_order:
                if alt != prev_template:
                    audit_log.append(f"Scene #{idx+1}: Prevented consecutive template '{tpl}' -> switched to '{alt}'")
                    tpl = alt
                    break

        # 6. منع تكرار نفس النص المفتاحي في مشهدين متتاليين
        if kw_joined == prev_kw_joined and len(speech.split()) >= 2:
            clean_keywords = speech.split()[-2:]
            kw_joined = " ".join(clean_keywords)

        scene["template"] = tpl
        scene["keywords"] = clean_keywords[:3]
        prev_template = tpl
        prev_kw_joined = kw_joined
        validated.append(scene)

    return validated, audit_log
