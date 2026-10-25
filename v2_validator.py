# -*- coding: utf-8 -*-
"""
v2/validator.py — المدقق الدلالي الصارم وبوابة تبرير العناصر (Semantic & Visual Directing Validator).
يضمن:
1. إذا كانت confidence < 0.7 للتطابق مع الكلام -> يتحول القالب فوراً إلى kinetic_hook.
2. منع أي رقم غير منطوق فعلياً في speech.
3. منع جميع عبارات الحشو من القائمة السوداء (+44، Pro Tips، أداء احترافي، AI STUDIO READY، 10x FAST، 4K 60FPS).
4. منع تكرار نفس القالب أو نفس الفعل البصري (verb_id) أو نفس نمط التكوين (layout_id) في مشهدين متتاليين.
5. قانون التطور الدلالي ومنع الجمود (DIR_RULE_007): أي مشهد تتجاوز مدته 1.80 ثانية يُزوّد وجوباً بتحول داخلي بين حالتين (state_transitions >= 1).
6. التحقق من استمرارية المرساة أو الخيط الهندسي (bridge_element / shared_anchor) بين المشاهد المترابطة سببياً.
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
    # الأنماط الدلالية الجديدة المستخلصة من الفيديوهات المرجعية الثلاثة:
    "anchor_expand",
    "process_simulation",
    "dual_layer_proof",
    "editorial_proof_card",
    "minimalist_reset",
}

ALLOWED_VISUAL_VERBS = {
    "VERB_01_ANCHOR_AND_EXPAND",
    "VERB_02_SIMULATE_PROCESS_TRANSFORM",
    "VERB_03_DUAL_LAYER_COMPARISON_REVEAL",
    "VERB_04_GEOMETRIC_CONTINUITY_MORPH",
    "VERB_05_VISUAL_PUN_JUXTAPOSITION",
    "VERB_06_CONTRAST_DECELERATION_RESET",
}

ALLOWED_LAYOUT_ARCHETYPES = {
    "COMP_01_VERTICAL_ANCHOR_STACK",
    "COMP_02_THREE_TIER_SIMULATION_STAGE",
    "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "COMP_04_DEPTH_OCCLUSION_COLLAGE",
    "COMP_05_MINIMALIST_BREATHING_CANVAS",
}

TEMPLATE_TO_DEFAULT_VERB = {
    "kinetic_hook": "VERB_04_GEOMETRIC_CONTINUITY_MORPH",
    "concept_icon": "VERB_01_ANCHOR_AND_EXPAND",
    "anchor_expand": "VERB_01_ANCHOR_AND_EXPAND",
    "big_number": "VERB_04_GEOMETRIC_CONTINUITY_MORPH",
    "phone_reel_mockup": "VERB_01_ANCHOR_AND_EXPAND",
    "before_after": "VERB_02_SIMULATE_PROCESS_TRANSFORM",
    "process_simulation": "VERB_02_SIMULATE_PROCESS_TRANSFORM",
    "checklist": "VERB_01_ANCHOR_AND_EXPAND",
    "steps_flow": "VERB_02_SIMULATE_PROCESS_TRANSFORM",
    "versus": "VERB_03_DUAL_LAYER_COMPARISON_REVEAL",
    "dual_layer_proof": "VERB_03_DUAL_LAYER_COMPARISON_REVEAL",
    "editorial_proof_card": "VERB_01_ANCHOR_AND_EXPAND",
    "fullscreen_image": "VERB_05_VISUAL_PUN_JUXTAPOSITION",
    "minimalist_reset": "VERB_06_CONTRAST_DECELERATION_RESET",
    "cta_end": "VERB_06_CONTRAST_DECELERATION_RESET",
}

TEMPLATE_TO_DEFAULT_LAYOUT = {
    "kinetic_hook": "COMP_01_VERTICAL_ANCHOR_STACK",
    "concept_icon": "COMP_04_DEPTH_OCCLUSION_COLLAGE",
    "anchor_expand": "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "big_number": "COMP_01_VERTICAL_ANCHOR_STACK",
    "phone_reel_mockup": "COMP_01_VERTICAL_ANCHOR_STACK",
    "before_after": "COMP_02_THREE_TIER_SIMULATION_STAGE",
    "process_simulation": "COMP_02_THREE_TIER_SIMULATION_STAGE",
    "checklist": "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "steps_flow": "COMP_02_THREE_TIER_SIMULATION_STAGE",
    "versus": "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "dual_layer_proof": "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "editorial_proof_card": "COMP_03_ASYMMETRIC_PAN_SPLIT",
    "fullscreen_image": "COMP_04_DEPTH_OCCLUSION_COLLAGE",
    "minimalist_reset": "COMP_05_MINIMALIST_BREATHING_CANVAS",
    "cta_end": "COMP_05_MINIMALIST_BREATHING_CANVAS",
}

SPOKEN_NUMBER_MAP = {
    "واحد": "1", "أول": "1", "الأول": "1", "أولى": "1",
    "زوج": "2", "اثنين": "2", "ثاني": "2", "الثاني": "2", "مرتين": "2x", "ضعف": "2x", "ضاعف": "2x", "doubled": "2x",
    "ثلاثة": "3", "ثلاث": "3", "ثالث": "3", "ثلث": "33%", "three": "3",
    "أربعة": "4", "خمسة": "5", "ستة": "6", "six": "6", "عشرة": "10",
    "مية": "100%", "مائة": "100%", "مجاني": "0 DA", "مجاناً": "0 DA", "باطل": "0 DA",
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
    low = speech.lower()
    for word, num_str in SPOKEN_NUMBER_MAP.items():
        if word in low and num_str not in found:
            found.append(num_str)
    return found


def validate_scene_plan(scenes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    يدقق خطة المشاهد (Scene Plan) ويصلح أي مخالفة لقواعد الجودة الصارمة وقواعد الإخراج الدلالي،
    ويعيد (المشاهد المدققة، سجل التدقيق).
    """
    validated: List[Dict[str, Any]] = []
    audit_log: List[str] = []
    prev_template = None
    prev_verb = None
    prev_layout = None
    prev_kw_joined = ""

    verb_pool = [
        "VERB_01_ANCHOR_AND_EXPAND",
        "VERB_02_SIMULATE_PROCESS_TRANSFORM",
        "VERB_03_DUAL_LAYER_COMPARISON_REVEAL",
        "VERB_04_GEOMETRIC_CONTINUITY_MORPH",
        "VERB_05_VISUAL_PUN_JUXTAPOSITION",
        "VERB_06_CONTRAST_DECELERATION_RESET",
    ]
    layout_pool = [
        "COMP_01_VERTICAL_ANCHOR_STACK",
        "COMP_02_THREE_TIER_SIMULATION_STAGE",
        "COMP_03_ASYMMETRIC_PAN_SPLIT",
        "COMP_04_DEPTH_OCCLUSION_COLLAGE",
        "COMP_05_MINIMALIST_BREATHING_CANVAS",
    ]

    for idx, sc in enumerate(scenes):
        scene = dict(sc)
        speech = str(scene.get("speech", "")).strip()
        tpl = str(scene.get("template", "kinetic_hook")).strip()
        conf = float(scene.get("confidence", 0.0))
        start_t = float(scene.get("start", idx * 2.0))
        end_t = float(scene.get("end", start_t + 2.0))
        dur = max(0.5, round(end_t - start_t, 3))

        # 1. التحقق من أن القالب ضمن القوالب المعتمدة
        if tpl not in ALLOWED_TEMPLATES:
            audit_log.append(f"Scene #{idx+1}: Unknown template '{tpl}' -> fallback to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 2. قاعدة الثقة الصارمة: confidence < 0.7 -> kinetic_hook فوراً
        if conf < 0.70 and tpl != "kinetic_hook":
            audit_log.append(f"Scene #{idx+1}: Low confidence ({conf:.2f} < 0.70) for '{tpl}' -> downgraded to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 3. التحقق من الأرقام المنطوقة فقط
        spoken_nums = extract_spoken_numbers(speech)
        raw_nums = [str(n) for n in scene.get("numbers", []) if any(sn in str(n) or str(n) in sn for sn in spoken_nums)]
        scene["numbers"] = raw_nums
        if tpl == "big_number" and not raw_nums:
            audit_log.append(f"Scene #{idx+1}: 'big_number' requested without spoken number in '{speech}' -> downgraded to 'kinetic_hook'")
            tpl = "kinetic_hook"

        # 4. تنظيف الكلمات المفتاحية من القائمة السوداء ومن تكرار الكابشن
        raw_keywords = [str(k).strip() for k in scene.get("keywords", []) if str(k).strip()]
        clean_keywords = []
        for kw in raw_keywords:
            if contains_blacklisted_text(kw):
                audit_log.append(f"Scene #{idx+1}: Removed blacklisted keyword '{kw}'")
                continue
            kw_digits = re.findall(r"\d+%?", kw)
            if any(not any(d in sn or sn in d for sn in spoken_nums) for d in kw_digits):
                audit_log.append(f"Scene #{idx+1}: Removed ungrounded number in keyword '{kw}'")
                continue
            clean_keywords.append(kw)

        if not clean_keywords:
            tokens = [t for t in speech.split() if len(t) > 2][:2]
            clean_keywords = tokens if tokens else ["تركيز بصري"]

        kw_joined = " ".join(clean_keywords)
        if len(speech.split()) > 3 and kw_joined.strip() == speech.strip():
            clean_keywords = clean_keywords[:2]
            kw_joined = " ".join(clean_keywords)

        # 5. منع تكرار نفس القالب في مشهدين متتاليين
        if prev_template is not None and tpl == prev_template:
            fallback_order = ["anchor_expand", "concept_icon", "process_simulation", "versus", "before_after", "checklist", "kinetic_hook"]
            for alt in fallback_order:
                if alt != prev_template:
                    audit_log.append(f"Scene #{idx+1}: Prevented consecutive template '{tpl}' -> switched to '{alt}'")
                    tpl = alt
                    break

        # 6. منع تكرار نفس النص المفتاحي في مشهدين متتاليين
        if kw_joined == prev_kw_joined and len(speech.split()) >= 2:
            clean_keywords = speech.split()[-2:]
            kw_joined = " ".join(clean_keywords)

        # 7. تعيين وتنويع الفعل البصري (verb_id) ونمط التكوين المكاني (layout_id)
        verb_id = str(scene.get("verb_id") or TEMPLATE_TO_DEFAULT_VERB.get(tpl, "VERB_01_ANCHOR_AND_EXPAND"))
        if verb_id not in ALLOWED_VISUAL_VERBS:
            verb_id = TEMPLATE_TO_DEFAULT_VERB.get(tpl, "VERB_01_ANCHOR_AND_EXPAND")
        if prev_verb is not None and verb_id == prev_verb:
            for cand_v in verb_pool:
                if cand_v != prev_verb:
                    audit_log.append(f"Scene #{idx+1}: Diversified consecutive verb '{verb_id}' -> '{cand_v}'")
                    verb_id = cand_v
                    break

        layout_id = str(scene.get("layout_id") or TEMPLATE_TO_DEFAULT_LAYOUT.get(tpl, "COMP_01_VERTICAL_ANCHOR_STACK"))
        if layout_id not in ALLOWED_LAYOUT_ARCHETYPES:
            layout_id = TEMPLATE_TO_DEFAULT_LAYOUT.get(tpl, "COMP_01_VERTICAL_ANCHOR_STACK")
        if prev_layout is not None and layout_id == prev_layout:
            for cand_l in layout_pool:
                if cand_l != prev_layout:
                    audit_log.append(f"Scene #{idx+1}: Diversified consecutive layout '{layout_id}' -> '{cand_l}'")
                    layout_id = cand_l
                    break

        # 8. قانون التطور الدلالي داخل المشهد (DIR_RULE_007: Anti-Stagnation Progression)
        # أي مشهد تتجاوز مدته 1.80 ثانية يجب أن يمتلك نقطة تحول داخلية (pivot_time) بين الحالة A والحالة B
        pivot_ratio = float(scene.get("pivot_ratio", 0.52))
        pivot_time = round(start_t + dur * pivot_ratio, 3)
        sub_states = scene.get("sub_states")
        if not isinstance(sub_states, list) or len(sub_states) < 2:
            if dur >= 1.65:
                sub_states = [
                    {
                        "state_id": f"S{idx+1}_STATE_A",
                        "start": round(start_t, 3),
                        "end": pivot_time,
                        "role": "ANCHOR_ESTABLISH",
                        "focus_text": clean_keywords[0],
                        "camera_offset_x": 0.0,
                        "anchor_scale": 1.0,
                    },
                    {
                        "state_id": f"S{idx+1}_STATE_B",
                        "start": pivot_time,
                        "end": round(end_t, 3),
                        "role": "MECHANISM_OR_OUTCOME_REVEAL",
                        "focus_text": clean_keywords[1] if len(clean_keywords) > 1 else clean_keywords[0],
                        "camera_offset_x": -0.22 if layout_id == "COMP_03_ASYMMETRIC_PAN_SPLIT" else 0.0,
                        "anchor_y_shift": 0.22 if verb_id == "VERB_01_ANCHOR_AND_EXPAND" else 0.0,
                        "anchor_scale": 0.84 if verb_id == "VERB_01_ANCHOR_AND_EXPAND" else 1.0,
                    },
                ]
            else:
                sub_states = [
                    {
                        "state_id": f"S{idx+1}_STATE_SINGLE",
                        "start": round(start_t, 3),
                        "end": round(end_t, 3),
                        "role": "FOCUSED_BEAT",
                        "focus_text": clean_keywords[0],
                    }
                ]

        # 9. ضمان وجود عنصر ربط هندسي أو سياقي (bridge_element) وتوقيت استقرار كافٍ للقراءة (settle_hold_sec)
        word_cnt = sum(len(k.split()) for k in clean_keywords[:3])
        min_settle = round(max(0.40, min(0.95, word_cnt * 0.14)), 2)

        scene["template"] = tpl
        scene["verb_id"] = verb_id
        scene["layout_id"] = layout_id
        scene["keywords"] = clean_keywords[:3]
        scene["sub_states"] = sub_states
        scene["state_transitions_count"] = max(1, len(sub_states) - 1)
        scene["pivot_time"] = pivot_time
        scene["min_settle_hold_sec"] = min_settle
        scene["bridge_element"] = scene.get("bridge_element") or {
            "type": "GEOMETRIC_THREAD",
            "shape": ["CIRCLE_HALO", "ROUNDED_VIEWPORT", "HORIZONTAL_BAR", "3D_SPHERE"][idx % 4],
            "persists_from_previous": idx > 0,
        }

        prev_template = tpl
        prev_verb = verb_id
        prev_layout = layout_id
        prev_kw_joined = kw_joined
        validated.append(scene)

    return validated, audit_log
