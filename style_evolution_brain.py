# -*- coding: utf-8 -*-
"""
style_evolution_brain.py - محرك استنساخ الفيديوهات المرجعية (الألوان + الأشكال + الرسومات + الأنيميشن) وتوليد الستايل الموحد لكل فيديو
========================================================================================================================================
Principal Video DSP & Self-Evolving Visual Intelligence Engine (Zero-OOM Architecture):
1. محلل ومستنسخ الفيديو المرجعي الشامل (`extract_reference_video_dna` - زر واحد ينسخ التصميم والرسومات والأنيميشن):
   - يحلل الفيديو المرجعي عبر أنبوب `FFmpeg` منخفض الذاكرة ليستخرج:
     أ) البصمة اللونية والضوئية المتكاملة (`theme_palette`, `is_light_bg`, `contrast_std`).
     ب) هندسة الأشكال والرسومات (`shape_geometry_profile`: شكل البطاقات، زوايا الميلان، الترويسة العلوية، نوع التمييز النصي، كثافة الرسوم البيانية).
     ج) فيزياء الحركة والأنيميشن (`motion_physics_profile`: سرعة الزنبرك `spring_stiffness`، التخميد `spring_damping`، التتابع `stagger_delay_sec`، حركة الكاميرا).
     د) تسلسل الرسومات والأنفوجرافيك (`cloned_archetype_sequence`) لتطبيق نفس الأشكال والرسومات والتحريك بما يناسب الفيديو أو التعليق الصوتي للمستخدم.
2. نظام الستايل الموحد لكل فيديو (`Single Cohesive Studio Style Per Video`):
   - عند اختيار الوضع العشوائي/التلقائي (`auto_vary_pro`)، يختار النظام **ستايلاً واحداً متكاملاً ومتناغماً لكامل الفيديو**
     (دون خلط خلفيات متضاربة داخل نفس الفيديو)، وفي الفيديو التالي يختار ستايلاً احترافياً جديداً مختلفاً.
   - داخل الفيديو الواحد، تتنوع **الأشكال والرسومات والأنيميشن (12 Archetypes)** في كل مشهد حسب معنى الكلام ضمن نفس الهوية اللونية الموحدة!
3. محرك الهوية البصرية واستخراج ألوان اللوقو (`extract_brand_palette_from_image` & `apply_custom_brand_colors`).
4. الناقد البصري وحلقة التطور التلقائي (`evaluate_and_evolve_frame` + `outputs/evolution_memory.json`).
"""

import os
import re
import sys
import gc
import json
import math
import time
import random
import ctypes
import hashlib
import logging
import subprocess
from typing import Dict, Any, List, Tuple, Optional, Callable
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
EVOLUTION_MEMORY_PATH = os.path.join(_CURRENT_DIR, "outputs", "evolution_memory.json")


def force_free_ram() -> None:
    """تحرير الذاكرة العشوائية في بايثون وإرجاعها لنظام التشغيل."""
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """تحويل لون RGB إلى صيغة Hex مثل #38BDF8."""
    r, g, b = [max(0, min(255, int(c))) for c in rgb[:3]]
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_rgb(hex_str: str, fallback: Tuple[int, int, int] = (56, 189, 248)) -> Tuple[int, int, int]:
    """تحويل صيغة Hex إلى Tuple RGB."""
    if not hex_str:
        return fallback
    s = str(hex_str).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback


# ==============================================================================
# 0. كتالوج الستايلات الاحترافية الموحدة (6 Cohesive Pro Studio Styles)
#    ملاحظة جوهرية: كل ستايل يملك هوية لونية وخلفية موحدة طوال الفيديو لمنع التشتت،
#    ويدعم رسم جميع الـ 12 نمطاً من الرسومات والأنيميشن التفاعلية!
# ==============================================================================
ALL_DYNAMIC_VISUAL_ARCHETYPES: List[str] = [
    # --- المجموعة أ: 16 رسمة ومجسم فيكتور تعبيري مخصص 100% للكلام المنطوق (Open-Canvas Speech-Matched Hero Illustrations) ---
    "web_dynamic_scene",               # 0. مشهد الفيكتور الحي المجلوب من الإنترنت والملون بثيم الفيديو النشط
    "hero_smartphone_reels",           # 1. مجسم الهاتف الذكي ومشغل الريلز التفاعلي ثلاثي الأبعاد
    "hero_camera_production",          # 2. عدسة الكاميرا السينمائية وشفرات الإضاءة ومؤشر التسجيل REC
    "hero_waveform_scissors",          # 3. مقص الليزر الذكي يقطع فجوات الصمت والأخطاء من الموجة الصوتية
    "hero_ai_neural_core",             # 4. معالج ونواة الذكاء الاصطناعي العصبية لتحويل الصوت والصورة
    "hero_chrono_speedometer",         # 5. عداد السرعة والزمن التوربيني لاختصار الساعات إلى ثوانٍ
    "hero_sound_wave_mixer",           # 6. مايكروفون الاستوديو الاحترافي وموجات الساوند ديزاين الترددية
    "hero_viral_rocket_chart",         # 7. صاروخ الانتشار الفيروسي ومنحنى مضاعفة الإنتاجية والمشاهدات
    "hero_power_cable_stand",          # 8. مجسم كابل الشحن السريع المقوى بالقماش وحامل الهاتف المدمج
    "hero_shield_durability",          # 9. الدرع السداسي المدرع لضمان الجودة والمتانة والحماية 100%
    "hero_commerce_delivery",          # 10. خريطة التوصيل السريع لـ 58 ولاية وبطاقة السعر والطلب الفوري
    "hero_creative_palette_pen",       # 11. لوحة التصميم الذكية وعجلة الألوان وقلم الرسم المتجهي Bezier
    "hero_problem_radar_fix",          # 12. رادار تشخيص المشكلة وتحويلها الفوري إلى مسار حل أخضر مضيء
    "hero_platform_workspace",         # 13. منصة العمل العائمة ثلاثية الأبعاد مع زر التوليد الذكي بضغطة واحدة
    "hero_roadmap_milestones",         # 14. مسار الخطوات المنحني المضيء عبر الفضاء البصري المفتوح
    "hero_comparison_duel",            # 15. مواجهة بصرية حية (الطريقة التقليدية البطيئة مقابل الذكية الفورية)
    "hero_cta_magnet_finale",          # 16. مغناطيس الجذب التفاعلي وزر الدعوة لاتخاذ إجراء (CTA)
    # --- المجموعة ب: 16 قالب موشن جرافيك استوديو تفاعلي (Choreographed Studio Motion Templates) ---
    "chrono_ring_3d_counter",          # 17. الحلقة ثلاثية الأبعاد والعداد الدائري الحي المتزامن مع النطق
    "pack_3d_extruding_pillars",       # 18. صندوق الأصول ثلاثي الأبعاد والأعمدة الملونة المنبثقة بالتتابع
    "macos_folder_counter_list",       # 19. قائمة المجلدات الزرقاء ثلاثية الأبعاد مع العداد الخلفي المتصاعد
    "reels_6card_showcase_grid",       # 20. معرض الفيديوهات والبطاقات الستة المتحركة (2×3)
    "dark_cinema_fanned_cards",        # 21. المسرح السينمائي الداكن والبطاقات المروحية ثلاثية الأبعاد
    "interactive_profile_follow_card", # 22. بطاقة الحساب التفاعلية وزر المتابعة الحي
    "bezier_growth_nodes",             # 23. مخطط المنحنى الصاعد المرسوم تدريجياً مع العقد المضيئة
    "live_magnifier_scanner",          # 24. المكبّر الفاحص المتحرك الذي يمسح ويكبّر البطاقات تحته حياً
    "damped_balance_scale",            # 25. الميزان الفيزيائي المتأرجح للمقارنة بين المشكلة والحل
    "nle_timeline_matrix",             # 26. جدول ومخطط التايملاين التفاعلي مع مؤشر القراءة المتحرك
    "radar_target_sweep",              # 27. رادار الاستهداف الدوار بشعاع مسح 360°
    "floating_3d_stat_Compare",        # 28. كبسولات المقارنة ثلاثية الأبعاد المتقابلة مع مؤشر السرعة
    "step_cascade_ribbon_cards",       # 29. شرائط الخطوات المتدرجة ثلاثية الأبعاد بعلامات التحقق المتتابعة
    "neural_hub_spoke_network",        # 30. شبكة العقد الذكية المتصلة بنبضات ضوئية متحركة
    "dual_metric_gauge_pods",          # 31. عدادان مزدوجان متزامنان للأداء والنتائج
    "kinetic_quote_dm_finale"          # 32. الخاتمة الحركية السريعة بعلامات التنصيص المضيئة والـ CTA المتتابع
]

ARCHETYPE_LABELS_AR: Dict[str, str] = {
    "web_dynamic_scene": "🌐 موشن جرافيك وفيكتور حي من الإنترنت بلون الثيم (Live Web Vector & Motion)",
    "hero_smartphone_reels": "📱 مجسم الهاتف ومشغل الريلز التفاعلي (Hero Smartphone & Reels)",
    "hero_camera_production": "🎥 عدسة الكاميرا السينمائية والتصوير (Hero Cinema Camera Lens)",
    "hero_waveform_scissors": "✂️ مقص الليزر الذكي وقص الصمت من الموجة (Hero Waveform & Scissors)",
    "hero_ai_neural_core": "🧠 نواة ومعالج الذكاء الاصطناعي للصوت والصورة (Hero AI Neural Core)",
    "hero_chrono_speedometer": "⏱️ عداد السرعة والزمن التوربيني (Hero Chrono Speedometer)",
    "hero_sound_wave_mixer": "🎙️ مايكروفون الاستوديو وموجات الساوند ديزاين (Hero Studio Mic & Waves)",
    "hero_viral_rocket_chart": "🚀 صاروخ الانتشار الفيروسي ومضاعفة الإنتاجية (Hero Viral Rocket)",
    "hero_power_cable_stand": "🔌 مجسم كابل الشحن السريع وحامل الهاتف (Hero Power Cable & Stand)",
    "hero_shield_durability": "🛡️ الدرع السداسي للمتانة والضمان 100% (Hero Armored Shield)",
    "hero_commerce_delivery": "🚚 خريطة التوصيل السريع 58 ولاية وبطاقة الطلب (Hero Express Delivery)",
    "hero_creative_palette_pen": "🎨 لوحة التصميم وعجلة الألوان وقلم الفيكتور (Hero Creative Palette)",
    "hero_problem_radar_fix": "⚡ رادار كشف المشكلة وتحويلها لحل فوري (Hero Problem -> Fix Radar)",
    "hero_platform_workspace": "💻 واجهة المنصة الذكية العائمة وزر التوليد (Hero AI Platform Deck)",
    "hero_roadmap_milestones": "🗺️ مسار الخطوات المنحني المضيء (Hero S-Curve Roadmap)",
    "hero_comparison_duel": "⚔️ مواجهة بصرية حية: تقليدي مقابل ذكي (Hero VS Comparison Duel)",
    "hero_cta_magnet_finale": "🧲 مغناطيس الجذب التفاعلي وزر الإجراء (Hero Magnet CTA Finale)",
    "chrono_ring_3d_counter": "⭕ الحلقة ثلاثية الأبعاد والعداد الدائري الحي (3D Chrono Ring)",
    "pack_3d_extruding_pillars": "📦 صندوق الأصول والأعمدة الملونة المنبثقة (3D Extruding Pillars)",
    "macos_folder_counter_list": "📁 قائمة المجلدات التفاعلية والعداد الخلفي (3D Folders & Counter)",
    "reels_6card_showcase_grid": "🎞️ معرض الفيديوهات والبطاقات الستة (Reels 6-Card Grid)",
    "dark_cinema_fanned_cards": "🃏 البطاقات المروحية السينمائية ثلاثية الأبعاد (3D Fanned Cards)",
    "interactive_profile_follow_card": "👤 بطاقة الحساب التفاعلية وزر المتابعة (Interactive Profile Card)",
    "bezier_growth_nodes": "📈 منحنى النمو الصاعد والعقد المضيئة (Bezier Growth Curve)",
    "live_magnifier_scanner": "🔍 المكبّر الفاحص المتحرك حياً (Live Magnifier Scanner)",
    "damped_balance_scale": "⚖️ الميزان الفيزيائي المتأرجح للمقارنة (Physics Balance Scale)",
    "nle_timeline_matrix": "🎬 مصفوفة التايملاين ومؤشر المونتاج (NLE Timeline Matrix)",
    "radar_target_sweep": "🎯 رادار الاستهداف الدوار 360° (Radar Target Sweep)",
    "floating_3d_stat_Compare": "📊 كبسولات المقارنة المزدوجة بالعدادات (Dual Stat Compare)",
    "step_cascade_ribbon_cards": "📑 شرائط الخطوات المتدرجة بعلامات التحقق (Cascade Step Ribbons)",
    "neural_hub_spoke_network": "🕸️ شبكة العقد الذكية المتصلة بنبضات ضوئية (Neural Hub Network)",
    "dual_metric_gauge_pods": "🎛️ عدادا الأداء المزدوجان (Dual Gauge Pods)",
    "kinetic_quote_dm_finale": "💬 الخاتمة الحركية بعلامات التنصيص وزر التفاعل (Kinetic Quote Finale)",
}


# قوائم الحظر المنطقي الصارم لمنع وضع قوالب مرقمة أو مقارنات أو عدادات في مشاهد الكلام العام
ENUMERATION_ONLY_ARCHETYPES = {
    "macos_folder_counter_list",
    "step_cascade_ribbon_cards",
    "nle_timeline_matrix",
    "hero_roadmap_milestones",
    "live_magnifier_scanner",
}

COMPARISON_ONLY_ARCHETYPES = {
    "damped_balance_scale",
    "floating_3d_stat_Compare",
    "hero_comparison_duel",
}

METRIC_COUNTER_ONLY_ARCHETYPES = {
    "chrono_ring_3d_counter",
    "dual_metric_gauge_pods",
}


def detect_strict_speech_intent(
    scene_text: str,
    scene_index: int = 0,
    total_scenes: int = 1
) -> Dict[str, Any]:
    """
    محرك المنطق الدلالي الصارم (`Strict Semantic Intent Gatekeeper`):
    يحلل الجملة المنطوقة ليحدد بدقة متى يكون المتحدث يعدد نقاطاً فعلياً (أولاً، ثانياً، ثلاث ميزات...)،
    ومتى يقارن بين شيئين، ومتى يذكر رقماً حقيقياً، ومتى يتحدث بشكل عام أو ترحيبي.
    يمنع منعاً باتاً تحويل الكلام العام (مثل "السلام عليكم كيف الحال" أو "الحل هو منصة...") إلى لوحة مرقمة 1-2-3-4!
    """
    t = re.sub(r'[،,.!؟?()\[\]\-":؛]', " ", str(scene_text or "")).strip().lower()

    # 1. كشف التعداد الصريح فقط (Explicit Enumeration Markers)
    enum_patterns = [
        r"\b(أولا|اولا|ثانيا|ثالثا|رابعا|خامسا)\b",
        r"\b(الشيء الأول|الشيء الاول|الشيء الثاني|الشيء الثالث)\b",
        r"\b(الميزة الأولى|الميزه الاولى|الميزة الثانية|الميزه الثانيه|الميزة الثالثة)\b",
        r"\b(الخاصية الأولى|الخاصيه الاولى|الخاصية الثانية|الخاصيه الثانيه|الخاصية الثالثة)\b",
        r"\b(الخطوة الأولى|الخطوه الاولى|الخطوة الثانية|الخطوه الثانيه|الخطوة الثالثة)\b",
        r"\b(ثلاث ميزات|ثلاث خصائص|3 ميزات|3 خصائص|أربع ميزات|اربع خصائص|عدة خطوات|خطوات)\b",
        r"\b(رقم واحد|رقم 1|رقم اثنين|رقم 2|النقطة الأولى|النقطه الاولى)\b",
    ]
    is_explicit_enumeration = any(re.search(pat, t) for pat in enum_patterns)

    # 2. كشف المقارنة الصريحة فقط (Explicit Comparison Markers)
    comp_patterns = [
        r"\b(مقابل|الفرق بين|فرق بين|مقارنة ب|عكس|قبل وبعد|بدل ما|أفضل من|افضل من|أحسن من|احسن من)\b"
    ]
    is_explicit_comparison = any(re.search(pat, t) for pat in comp_patterns)

    # 3. كشف الأرقام والمقاييس المنطوقة فعلياً (Explicit Metric / Number Markers)
    # نتحقق من وجود رقم صريح غير رقم عمر تعريفي بسيط في جملة الترحيب
    has_digits = bool(re.search(r"\b(\d+)\s*(%|ثانية|ثواني|دقيقة|دقائق|ساعة|ساعات|ولاية|أضعاف|مرات|يوم|أيام)\b", t))
    has_verbal_metric = any(kw in t for kw in ["أقل من دقيقة", "اقل من دقيقه", "58 ولاية", "100%", "مئة بالمئة"])
    is_explicit_metric_counter = bool(has_digits or has_verbal_metric)

    # 4. كشف الجمل الترحيبية أو التعريفية العامة (Greeting / Intro / General Conversational Speech)
    greeting_keywords = ["السلام عليكم", "أهلا", "اهلا", "مرحبا", "كيف الحال", "واش راكم", "طيبين", "عمري", "اسمي", "معكم"]
    is_greeting_or_intro = (scene_index == 0 and any(gk in t for gk in greeting_keywords)) or any(
        gk in t for gk in ["السلام عليكم", "كيف الحال", "واش راكم", "طيبين"]
    )

    # القوالب الممنوعة منطقياً لهذا المشهد
    forbidden_archetypes = set()
    if not is_explicit_enumeration or is_greeting_or_intro:
        forbidden_archetypes.update(ENUMERATION_ONLY_ARCHETYPES)
    if not is_explicit_comparison or is_greeting_or_intro:
        forbidden_archetypes.update(COMPARISON_ONLY_ARCHETYPES)
    if not is_explicit_metric_counter or is_greeting_or_intro:
        forbidden_archetypes.update(METRIC_COUNTER_ONLY_ARCHETYPES)

    return {
        "is_explicit_enumeration": is_explicit_enumeration,
        "is_explicit_comparison": is_explicit_comparison,
        "is_explicit_metric_counter": is_explicit_metric_counter,
        "is_greeting_or_intro": is_greeting_or_intro,
        "forbidden_archetypes": forbidden_archetypes,
    }


def match_speech_to_visual_archetype(
    scene_text: str,
    scene_index: int,
    total_scenes: int,
    used_archetypes: Optional[List[str]] = None,
    variation_seed: int = 0
) -> Tuple[str, str]:
    """
    يربط الكلمات المنطوقة في الجملة مباشرة بالرسمة/المجسم التعبيري المتوافق معها 100%
    أو بمشهد الفيكتور الحي المجلوب من الإنترنت (`web_dynamic_scene`) مع تطبيق بوابة المنطق الصارم
    (`detect_strict_speech_intent`) التي تمنع ظهور القوائم المرقمة (1-2-3-4) أو العدادات الوهمية في الكلام العام!
    """
    used = set(used_archetypes or [])
    t_low = (scene_text or "").lower()
    intent = detect_strict_speech_intent(scene_text, scene_index, total_scenes)
    forbidden = intent["forbidden_archetypes"]

    # إذا كان المتحدث يعدد نقاطاً صراحةً (مثل: "أفضل ثلاث ميزات..." أو "الشيء الأول...")
    if intent["is_explicit_enumeration"]:
        enum_cands = ["hero_roadmap_milestones", "step_cascade_ribbon_cards", "macos_folder_counter_list"]
        for ec in enum_cands:
            if ec not in used:
                return ec, "hero_roadmap_milestones"

    # إذا كان المتحدث يقارن صراحةً بين شيئين
    if intent["is_explicit_comparison"]:
        comp_cands = ["hero_comparison_duel", "damped_balance_scale", "floating_3d_stat_Compare"]
        for cc in comp_cands:
            if cc not in used:
                return cc, "hero_comparison_duel"

    rules: List[Tuple[str, List[str], List[str]]] = [
        (
            "hero_power_cable_stand",
            ["كابل", "شاحن", "تشارجي", "يتشارجا", "سوبر فاست", "بطارية", "سيبور", "حامل", "ستاند", "سلك"],
            ["hero_power_cable_stand", "web_dynamic_scene", "pack_3d_extruding_pillars"]
        ),
        (
            "hero_shield_durability",
            ["قماش", "يتقطع", "مغلف", "متين", "متانة", "ضمان", "أصلي", "اصلي", "حماية", "مقاوم", "جودة"],
            ["hero_shield_durability", "radar_target_sweep", "web_dynamic_scene"]
        ),
        (
            "hero_commerce_delivery",
            ["توصيل", "ولاية", "58", "باب الدار", "سعر", "سومة", "بري", "دينار", "مجاني", "باطل", "اكموندي", "اطلب"],
            ["hero_commerce_delivery", "web_dynamic_scene", "hero_cta_magnet_finale"]
        ),
        (
            "hero_waveform_scissors",
            ["قص", "تقطيع", "صمت", "سكوت", "فراغات", "أخطاء", "غلط", "يحذف", "يشيل", "تنقية"],
            ["hero_waveform_scissors", "web_dynamic_scene", "dark_cinema_fanned_cards"]
        ),
        (
            "hero_camera_production",
            ["تصور", "تصوير", "كاميرا", "عدسة", "لقطة", "سجل", "تسجيل", "إضاءة", "استوديو"],
            ["hero_camera_production", "web_dynamic_scene", "reels_6card_showcase_grid"]
        ),
        (
            "hero_ai_neural_core",
            ["ذكاء", "اصطناعي", "الاصطناعي", "آلي", "تلقائي", "يفهم", "يحلل", "خوارزمية", "محرك", "ai"],
            ["hero_ai_neural_core", "neural_hub_spoke_network", "web_dynamic_scene"]
        ),
        (
            "hero_chrono_speedometer",
            ["وقت", "ساعات", "ساعة", "دقيقة", "دقيقه", "ثواني", "ثانية", "سرعة", "سريع", "أقل من", "اقل من", "توفير"],
            ["hero_chrono_speedometer", "chrono_ring_3d_counter", "web_dynamic_scene"]
        ),
        (
            "hero_sound_wave_mixer",
            ["صوت", "تعليق", "مايك", "ساوند", "مؤثرات", "ووش", "نغمة", "تردد", "سمع"],
            ["hero_sound_wave_mixer", "dark_cinema_fanned_cards", "web_dynamic_scene"]
        ),
        (
            "hero_viral_rocket_chart",
            ["إنتاجية", "انتاجية", "انتشار", "مشاهدات", "تفاعل", "ريتش", "نمو", "يرفع", "ترفع", "مضاعفة", "نتائج", "نجاح"],
            ["hero_viral_rocket_chart", "bezier_growth_nodes", "web_dynamic_scene"]
        ),
        (
            "hero_smartphone_reels",
            ["ريلز", "للريلز", "تيك توك", "شورتس", "انستغرام", "يوتيوب", "التواصل الاجتماعي", "فيديوهات", "مقطع", "تليفون", "هاتف"],
            ["hero_smartphone_reels", "reels_6card_showcase_grid", "web_dynamic_scene"]
        ),
        (
            "hero_creative_palette_pen",
            ["تصميم", "ألوان", "الوان", "ثيم", "لوقو", "شعار", "موشن", "جرافيك", "غرافيك", "أشكال", "رسومات", "ستايل"],
            ["hero_creative_palette_pen", "web_dynamic_scene", "pack_3d_extruding_pillars"]
        ),
        (
            "hero_problem_radar_fix",
            ["مشكل", "مشكلة", "معاناة", "يعاني", "صعب", "صعيب", "متعب", "ممل", "مشتت", "ضيق", "تعب"],
            ["hero_problem_radar_fix", "radar_target_sweep", "web_dynamic_scene"]
        ),
        (
            "hero_platform_workspace",
            ["منصة", "تطبيق", "موقع", "برنامج", "نظام", "مسؤولة", "المسؤولة", "جبت لكم", "جيت لكم", "الحل", "أداة", "أبني", "ابني"],
            ["hero_platform_workspace", "web_dynamic_scene", "interactive_profile_follow_card"]
        ),
        (
            "hero_cta_magnet_finale",
            ["رابط", "أسفل", "اسفل", "تابع", "اشترك", "شارك", "تواصل", "جرب", "ابدأ", "الآن"],
            ["hero_cta_magnet_finale", "kinetic_quote_dm_finale", "interactive_profile_follow_card"]
        ),
    ]

    if scene_index == total_scenes - 1 and total_scenes >= 3:
        outro_pool = ["hero_cta_magnet_finale", "kinetic_quote_dm_finale", "hero_commerce_delivery"]
        for cand in outro_pool:
            if cand not in used:
                return cand, cand

    best_subj = None
    best_candidates: List[str] = []
    best_score = 0

    for subj, kw_list, cand_archs in rules:
        hits = sum(2 if kw in t_low else 0 for kw in kw_list)
        if hits > best_score:
            best_score = hits
            best_subj = subj
            best_candidates = [c for c in cand_archs if c not in forbidden]

    text_hash = int(hashlib.md5((scene_text or f"s_{scene_index}").encode("utf-8", errors="ignore")).hexdigest()[:6], 16)
    seed_val = int(variation_seed) + scene_index * 13 + text_hash

    if best_candidates:
        unused_hero_cands = [c for c in best_candidates if (c.startswith("hero_") or c == "web_dynamic_scene") and c not in used]
        if unused_hero_cands:
            return unused_hero_cands[0], (best_subj or unused_hero_cands[0])
        unused_cands = [c for c in best_candidates if c not in used]
        if unused_cands:
            return unused_cands[seed_val % len(unused_cands)], (best_subj or unused_cands[0])

    # للجمل الترحيبية أو الكلام العام الذي لا يطابق قاعدة متخصصة، نفضل دائماً مشاهد الفيكتور الحي من الإنترنت والرسومات التعبيرية المفتوحة
    safe_general_pool = [
        a for a in ALL_DYNAMIC_VISUAL_ARCHETYPES
        if a not in forbidden and a not in used and (a == "web_dynamic_scene" or a.startswith("hero_"))
    ]
    if not safe_general_pool:
        safe_general_pool = [a for a in ALL_DYNAMIC_VISUAL_ARCHETYPES if a not in forbidden and a not in used]
    if safe_general_pool:
        # إذا كان المشهد ترحيبياً عاماً، نستخدم مشهد الفيكتور الحي من الإنترنت مباشرةً إن لم يُستخدم بعد
        if intent["is_greeting_or_intro"] and "web_dynamic_scene" in safe_general_pool:
            return "web_dynamic_scene", (best_subj or "web_dynamic_scene")
        chosen = safe_general_pool[seed_val % len(safe_general_pool)]
        return chosen, (best_subj or chosen)

    return "web_dynamic_scene", (best_subj or "web_dynamic_scene")


PRO_STUDIO_STYLE_FAMILIES: Dict[str, Dict[str, Any]] = {
    "haamza_15s_cinema": {
        "style_id": "haamza_15s_cinema",
        "label_ar": "🌟 ستايل المونتاج السينمائي الفاخر 15s (تدرج كريمي دافئ ومخملي بدون مربعات • انتقالات سلسة وموشن ثلاثي الأبعاد)",
        "design_family": "haamza_15s_cinema",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "none_clean",
        "headline_style": "gold_accent_clean",
        "card_tilt_deg": 1.8,
        "preferred_archetypes": [
            "chrono_ring_3d_counter", "pack_3d_extruding_pillars", "macos_folder_counter_list",
            "reels_6card_showcase_grid", "dark_cinema_fanned_cards", "interactive_profile_follow_card",
            "bezier_growth_nodes", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (253, 250, 241),
            "bottom_bg": (244, 231, 198),
            "glow": (234, 179, 8),
            "primary": (217, 155, 28),
            "secondary": (37, 99, 235),
            "accent": (16, 185, 129),
            "card_bg": (255, 255, 255),
            "is_light_bg": True,
            "sticker_bg": (234, 179, 8),
            "sticker_txt": (24, 24, 27),
            "headline_txt": (24, 24, 27)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (253, 250, 241),
                "bottom_bg": (244, 231, 198),
                "glow": (234, 179, 8),
                "primary": (217, 155, 28),
                "secondary": (37, 99, 235),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (234, 179, 8),
                "sticker_txt": (24, 24, 27),
                "headline_txt": (24, 24, 27)
            },
            "body_steps": {
                "top_bg": (253, 250, 241),
                "bottom_bg": (244, 231, 198),
                "glow": (234, 179, 8),
                "primary": (217, 155, 28),
                "secondary": (37, 99, 235),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (234, 179, 8),
                "sticker_txt": (24, 24, 27),
                "headline_txt": (24, 24, 27)
            },
            "outro_finale": {
                "top_bg": (253, 250, 241),
                "bottom_bg": (244, 231, 198),
                "glow": (234, 179, 8),
                "primary": (217, 155, 28),
                "secondary": (37, 99, 235),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (234, 179, 8),
                "sticker_txt": (24, 24, 27),
                "headline_txt": (24, 24, 27)
            }
        }
    },
    "byw_cyan_agency": {
        "style_id": "byw_cyan_agency",
        "label_ar": "🎬 ستايل وكالة السيان والكحلي الاحترافي (بطاقات بيضاء مائلة وستيكر نصي بارز)",
        "design_family": "byw_cyan_agency",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "step_dots_pill",
        "headline_style": "sticker_highlight",
        "card_tilt_deg": 1.5,
        "preferred_archetypes": [
            "chrono_ring_3d_counter", "bezier_growth_nodes", "live_magnifier_scanner",
            "radar_target_sweep", "pack_3d_extruding_pillars", "reels_6card_showcase_grid",
            "dark_cinema_fanned_cards", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (13, 118, 142),
            "bottom_bg": (7, 68, 86),
            "glow": (56, 219, 248),
            "primary": (27, 174, 202),
            "secondary": (250, 204, 21),
            "accent": (16, 185, 129),
            "card_bg": (255, 255, 255),
            "is_light_bg": False,
            "sticker_bg": (255, 255, 255),
            "sticker_txt": (11, 24, 31),
            "headline_txt": (255, 255, 255)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (11, 32, 44),
                "bottom_bg": (9, 58, 74),
                "glow": (27, 174, 202),
                "primary": (27, 174, 202),
                "secondary": (255, 255, 255),
                "accent": (244, 63, 94),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (27, 174, 202),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (16, 138, 164),
                "bottom_bg": (8, 82, 102),
                "glow": (255, 255, 255),
                "primary": (11, 24, 31),
                "secondary": (27, 174, 202),
                "accent": (250, 204, 21),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (255, 255, 255),
                "sticker_txt": (11, 24, 31),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (14, 112, 136),
                "bottom_bg": (8, 64, 82),
                "glow": (56, 219, 248),
                "primary": (27, 174, 202),
                "secondary": (250, 204, 21),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (11, 24, 31),
                "headline_txt": (255, 255, 255)
            }
        }
    },
    "mazen_blueprint_collage": {
        "style_id": "mazen_blueprint_collage",
        "label_ar": "📐 ستايل المخطط الهندسي السماوي (إطارات تحديد ذكية ورسومات تقنية مشرقة)",
        "design_family": "mazen_blueprint_collage",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "corner_punctuation_watermark",
        "headline_style": "selection_box_handle",
        "card_tilt_deg": 0.0,
        "preferred_archetypes": [
            "macos_folder_counter_list", "damped_balance_scale", "reels_6card_showcase_grid",
            "interactive_profile_follow_card", "bezier_growth_nodes", "live_magnifier_scanner",
            "nle_timeline_matrix", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (172, 214, 248),
            "bottom_bg": (208, 232, 252),
            "glow": (2, 132, 199),
            "primary": (2, 132, 199),
            "secondary": (15, 23, 42),
            "accent": (37, 99, 235),
            "card_bg": (255, 255, 255),
            "is_light_bg": True,
            "sticker_bg": (2, 132, 199),
            "sticker_txt": (255, 255, 255),
            "headline_txt": (15, 23, 42)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (178, 218, 250),
                "bottom_bg": (206, 230, 252),
                "glow": (2, 132, 199),
                "primary": (2, 132, 199),
                "secondary": (15, 23, 42),
                "accent": (37, 99, 235),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (2, 132, 199),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            },
            "body_steps": {
                "top_bg": (168, 212, 246),
                "bottom_bg": (204, 230, 252),
                "glow": (37, 99, 235),
                "primary": (2, 132, 199),
                "secondary": (30, 58, 138),
                "accent": (14, 165, 233),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (37, 99, 235),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            },
            "outro_finale": {
                "top_bg": (182, 220, 250),
                "bottom_bg": (212, 234, 254),
                "glow": (2, 132, 199),
                "primary": (2, 132, 199),
                "secondary": (15, 23, 42),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (15, 23, 42),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            }
        }
    },
    "baghdadi_luxury_plum": {
        "style_id": "baghdadi_luxury_plum",
        "label_ar": "🟣 ستايل مختبر الإعلانات البنفسجي الفاخر (تبويبات علوية وواجهات زجاجية داكنة)",
        "design_family": "baghdadi_luxury_plum",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "segmented_3tabs",
        "headline_style": "sticker_highlight",
        "card_tilt_deg": 1.0,
        "preferred_archetypes": [
            "dark_cinema_fanned_cards", "radar_target_sweep", "bezier_growth_nodes",
            "pack_3d_extruding_pillars", "damped_balance_scale", "reels_6card_showcase_grid",
            "live_magnifier_scanner", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (18, 15, 36),
            "bottom_bg": (36, 24, 64),
            "glow": (139, 92, 246),
            "primary": (139, 92, 246),
            "secondary": (216, 180, 254),
            "accent": (16, 185, 129),
            "card_bg": (28, 22, 52),
            "is_light_bg": False,
            "sticker_bg": (139, 92, 246),
            "sticker_txt": (255, 255, 255),
            "headline_txt": (255, 255, 255)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (18, 15, 36),
                "bottom_bg": (36, 24, 64),
                "glow": (139, 92, 246),
                "primary": (139, 92, 246),
                "secondary": (216, 180, 254),
                "accent": (244, 63, 94),
                "card_bg": (28, 22, 52),
                "is_light_bg": False,
                "sticker_bg": (139, 92, 246),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (20, 17, 40),
                "bottom_bg": (40, 27, 70),
                "glow": (124, 58, 237),
                "primary": (139, 92, 246),
                "secondary": (196, 181, 253),
                "accent": (16, 185, 129),
                "card_bg": (30, 24, 56),
                "is_light_bg": False,
                "sticker_bg": (139, 92, 246),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (16, 14, 34),
                "bottom_bg": (44, 30, 76),
                "glow": (167, 139, 250),
                "primary": (139, 92, 246),
                "secondary": (250, 204, 21),
                "accent": (16, 185, 129),
                "card_bg": (28, 22, 52),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (16, 14, 34),
                "headline_txt": (255, 255, 255)
            }
        }
    },
    "emerald_fintech_mint": {
        "style_id": "emerald_fintech_mint",
        "label_ar": "🌿 ستايل الفينتك الزمردي الداكن (مخططات مالية وتقارير أداء عالية التباين)",
        "design_family": "emerald_fintech_mint",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "step_dots_pill",
        "headline_style": "sticker_highlight",
        "card_tilt_deg": 1.2,
        "preferred_archetypes": [
            "bezier_growth_nodes", "pack_3d_extruding_pillars", "damped_balance_scale",
            "reels_6card_showcase_grid", "chrono_ring_3d_counter", "radar_target_sweep",
            "nle_timeline_matrix", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (9, 32, 26),
            "bottom_bg": (13, 56, 45),
            "glow": (16, 185, 129),
            "primary": (16, 185, 129),
            "secondary": (250, 204, 21),
            "accent": (56, 189, 248),
            "card_bg": (255, 255, 255),
            "is_light_bg": False,
            "sticker_bg": (16, 185, 129),
            "sticker_txt": (255, 255, 255),
            "headline_txt": (255, 255, 255)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (9, 30, 24),
                "bottom_bg": (13, 52, 42),
                "glow": (16, 185, 129),
                "primary": (16, 185, 129),
                "secondary": (250, 204, 21),
                "accent": (245, 158, 11),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (16, 185, 129),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (10, 36, 29),
                "bottom_bg": (14, 62, 49),
                "glow": (52, 211, 153),
                "primary": (16, 185, 129),
                "secondary": (250, 204, 21),
                "accent": (56, 189, 248),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (9, 26, 22),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (9, 32, 26),
                "bottom_bg": (15, 64, 50),
                "glow": (16, 185, 129),
                "primary": (16, 185, 129),
                "secondary": (250, 204, 21),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (16, 185, 129),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            }
        }
    },
    "royal_cobalt_gold": {
        "style_id": "royal_cobalt_gold",
        "label_ar": "👑 ستايل الكوبالت الملكي والذهبي السينمائي (لوحات زجاجية وتوهج ذهبي)",
        "design_family": "royal_cobalt_gold",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "segmented_3tabs",
        "headline_style": "sticker_highlight",
        "card_tilt_deg": 1.2,
        "preferred_archetypes": [
            "interactive_profile_follow_card", "reels_6card_showcase_grid", "bezier_growth_nodes",
            "radar_target_sweep", "damped_balance_scale", "pack_3d_extruding_pillars",
            "dark_cinema_fanned_cards", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (11, 20, 44),
            "bottom_bg": (20, 38, 82),
            "glow": (59, 130, 246),
            "primary": (59, 130, 246),
            "secondary": (250, 204, 21),
            "accent": (16, 185, 129),
            "card_bg": (22, 34, 68),
            "is_light_bg": False,
            "sticker_bg": (250, 204, 21),
            "sticker_txt": (11, 20, 44),
            "headline_txt": (255, 255, 255)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (11, 20, 44),
                "bottom_bg": (20, 38, 82),
                "glow": (59, 130, 246),
                "primary": (59, 130, 246),
                "secondary": (250, 204, 21),
                "accent": (244, 63, 94),
                "card_bg": (22, 34, 68),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (11, 20, 44),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (13, 24, 52),
                "bottom_bg": (23, 44, 94),
                "glow": (56, 189, 248),
                "primary": (59, 130, 246),
                "secondary": (250, 204, 21),
                "accent": (16, 185, 129),
                "card_bg": (24, 38, 76),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (11, 20, 44),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (11, 20, 44),
                "bottom_bg": (25, 48, 102),
                "glow": (250, 204, 21),
                "primary": (59, 130, 246),
                "secondary": (250, 204, 21),
                "accent": (16, 185, 129),
                "card_bg": (22, 34, 68),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (11, 20, 44),
                "headline_txt": (255, 255, 255)
            }
        }
    },
    "sunset_coral_editorial": {
        "style_id": "sunset_coral_editorial",
        "label_ar": "🔥 ستايل الإديتوريال المرجاني الدافئ (بطاقات SaaS نظيفة وتباين ديناميكي)",
        "design_family": "sunset_coral_editorial",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "step_dots_pill",
        "headline_style": "sticker_highlight",
        "card_tilt_deg": 1.0,
        "preferred_archetypes": [
            "chrono_ring_3d_counter", "macos_folder_counter_list", "live_magnifier_scanner",
            "dark_cinema_fanned_cards", "reels_6card_showcase_grid", "pack_3d_extruding_pillars",
            "bezier_growth_nodes", "kinetic_quote_dm_finale"
        ],
        "unified_palette": {
            "top_bg": (26, 14, 24),
            "bottom_bg": (52, 22, 40),
            "glow": (244, 63, 94),
            "primary": (244, 63, 94),
            "secondary": (251, 191, 36),
            "accent": (16, 185, 129),
            "card_bg": (255, 255, 255),
            "is_light_bg": False,
            "sticker_bg": (244, 63, 94),
            "sticker_txt": (255, 255, 255),
            "headline_txt": (255, 255, 255)
        },
        "acts": {
            "hook_problem": {
                "top_bg": (26, 14, 24),
                "bottom_bg": (52, 22, 40),
                "glow": (244, 63, 94),
                "primary": (244, 63, 94),
                "secondary": (251, 191, 36),
                "accent": (244, 63, 94),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (244, 63, 94),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (30, 16, 28),
                "bottom_bg": (58, 25, 44),
                "glow": (251, 113, 133),
                "primary": (244, 63, 94),
                "secondary": (251, 191, 36),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (251, 191, 36),
                "sticker_txt": (26, 14, 24),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (26, 14, 24),
                "bottom_bg": (54, 24, 42),
                "glow": (251, 191, 36),
                "primary": (244, 63, 94),
                "secondary": (251, 191, 36),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (244, 63, 94),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            }
        }
    }
}


# ==============================================================================
# 1. إدارة ذاكرة التطور المستديمة على القرص (outputs/evolution_memory.json)
# ==============================================================================
def _default_evolution_memory() -> Dict[str, Any]:
    return {
        "version": "5.0",
        "total_evaluations": 0,
        "total_evolutions_triggered": 0,
        "average_quality_score": 0.95,
        "style_rotation_counter": 0,
        "active_studio_style_mode": "auto_vary_pro",  # auto_vary_pro | clone_reference | byw_cyan_agency | ...
        "active_reference_dna": None,
        "active_brand_theme": None,
        "cloned_reference_styles": {},
        "scene_type_best_params": {
            "default": {
                "font_scale": 1.0,
                "card_padding": 18,
                "bg_blur_strength": 16,
                "accent_glow": 0.28,
                "spring_stiffness": 210.0,
                "spring_damping": 13.5,
                "contrast_boost": 1.0,
                "best_score": 0.95,
                "samples": 1
            }
        }
    }


def load_evolution_memory(memory_path: str = EVOLUTION_MEMORY_PATH) -> Dict[str, Any]:
    if os.path.exists(memory_path):
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base = _default_evolution_memory()
                base.update(data)
                return base
        except Exception as e:
            logger.debug(f"Could not read evolution_memory.json: {e}")
    return _default_evolution_memory()


def save_evolution_memory(memory: Dict[str, Any], memory_path: str = EVOLUTION_MEMORY_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(memory_path)), exist_ok=True)
        tmp_path = memory_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, memory_path)
    except Exception as e:
        logger.debug(f"Could not save evolution_memory.json: {e}")


def set_active_studio_style_mode(style_mode: str) -> Dict[str, Any]:
    """
    ضبط وضع الستايل الاحترافي النشط:
    - `auto_vary_pro`: يختار لكل فيديو جديد ستايلاً واحداً متكاملاً وموحداً، وينوّع الأشكال والرسومات والـ Animations داخل المشاهد.
    - `clone_reference`: يطبق ستايل وأشكال ورسومات وأنيميشن الفيديو المرجعي المرفوع.
    - أو ستايل محدد يختاره المستخدم من `PRO_STUDIO_STYLE_FAMILIES`.
    """
    mem = load_evolution_memory()
    mem["active_studio_style_mode"] = str(style_mode or "auto_vary_pro")
    save_evolution_memory(mem)
    return mem


def get_active_studio_style_mode() -> str:
    mem = load_evolution_memory()
    return str(mem.get("active_studio_style_mode") or "auto_vary_pro")


def _select_non_repeating_archetype_sequence(
    num_scenes: int,
    preferred_pool: List[str],
    rotation_seed: int = 0
) -> List[str]:
    """
    يبني تسلسلاً فريداً وغير متكرر 100% من الرسومات والأنيميشن (`Visual Archetypes`):
    - يخلط كل الـ 15 نمطاً التفاعلية ببذرة متغيرة في كل فيديو جديد (`rotation_seed`)
      بحيث لا تتكرر نفس الرسومات بين الفيديوهات ولا يتكرر أي شكل داخل الفيديو الواحد!
    """
    full_non_outro = [a for a in ALL_DYNAMIC_VISUAL_ARCHETYPES if a != "kinetic_quote_dm_finale"]
    rng = random.Random(int(rotation_seed) * 9973 + int(num_scenes) * 37)
    shuffled = list(full_non_outro)
    rng.shuffle(shuffled)

    seq: List[str] = []
    for idx in range(max(1, num_scenes)):
        if idx == num_scenes - 1 and num_scenes >= 2:
            seq.append("kinetic_quote_dm_finale")
        else:
            cand = shuffled[idx % len(shuffled)]
            if seq and cand == seq[-1]:
                cand = shuffled[(idx + 1) % len(shuffled)]
            seq.append(cand)
    return seq


def build_dynamic_scene_style_assignment(
    num_scenes: int,
    force_style_mode: Optional[str] = None,
    advance_rotation_counter: bool = True,
    scenes: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    يبني خطة التصميم البصري والأنيميشن لكل مشهد في الفيديو مع ضمان **وحدة الستايل والهوية البصرية طوال الفيديو الواحد**:
    - لا يتم أبداً خلط خلفيات متضاربة (مثل أزرق فاتح ثم بنفسجي داكن ثم أخضر) داخل نفس الفيديو!
    - في وضع `auto_vary_pro`: يتم اختيار **ستايل واحد متكامل** لكامل الفيديو الحالي، وفي الفيديو القادم ينتقل العداد
      ليختار ستايلاً جديداً للفيديو الجديد.
    - في وضع `clone_reference`: يطبق ألوان وأشكال ورسومات وفيزياء حركة الفيديو المرجعي المستنسخ على جميع المشاهد.
    - داخل الفيديو الواحد، تتنوع **الأشكال والرسومات والـ Animations (`visual_archetype`)** من مشهد لآخر بما يناسب الكلام!
    """
    mem = load_evolution_memory()
    mode = str(force_style_mode or mem.get("active_studio_style_mode") or "auto_vary_pro")
    rot_idx = int(mem.get("style_rotation_counter", 0))

    if advance_rotation_counter:
        rot_idx += 1
        mem["style_rotation_counter"] = rot_idx
        save_evolution_memory(mem)

    style_aliases = {
        "warm_editorial_cream": "editorial_cream",
        "obsidian_gold_exec": "editorial_dark",
        "crimson_velvet_studio": "editorial_crimson",
        "mint_sage_broadcast": "editorial_mint",
        "royal_cobalt": "royal_cobalt_gold",
    }
    if force_style_mode in style_aliases:
        force_style_mode = style_aliases[force_style_mode]
    family_keys = list(PRO_STUDIO_STYLE_FAMILIES.keys())
    active_ref = mem.get("active_reference_dna")

    # 1. وضع استنساخ الفيديو المرجعي ("نسخ الفيديو المرجعي وتطبيق نفس الأشكال والرسومات والأنيميشن")
    if mode == "clone_reference" and isinstance(active_ref, dict) and active_ref.get("enabled", True):
        detected_fam_key = str(active_ref.get("detected_design_family") or "byw_cyan_agency")
        base_fam = json.loads(json.dumps(PRO_STUDIO_STYLE_FAMILIES.get(detected_fam_key, PRO_STUDIO_STYLE_FAMILIES["byw_cyan_agency"])))

        # توحيد باليت الفيديو المرجعي المستنسخ لمنع أي قفزات لونية مزعجة
        cloned_unified_pal = dict(base_fam.get("unified_palette", base_fam["acts"]["body_steps"]))
        if "multi_act_palettes" in active_ref and isinstance(active_ref["multi_act_palettes"], dict):
            body_p = active_ref["multi_act_palettes"].get("body_steps")
            if isinstance(body_p, dict):
                cloned_unified_pal.update(body_p)

        cloned_arch_seq = active_ref.get("cloned_archetype_sequence")
        if not isinstance(cloned_arch_seq, list) or not cloned_arch_seq:
            cloned_arch_seq = _select_non_repeating_archetype_sequence(
                num_scenes, base_fam.get("preferred_archetypes", ALL_DYNAMIC_VISUAL_ARCHETYPES), rotation_seed=rot_idx
            )

        plan: List[Dict[str, Any]] = []
        used_in_plan: List[str] = []
        dyn_seed = rot_idx + int(time.time() * 10) % 997
        for idx in range(max(1, num_scenes)):
            act_name = "hook_problem" if idx == 0 else ("outro_finale" if (idx == num_scenes - 1 and num_scenes >= 2) else "body_steps")
            sc_obj = scenes[idx] if (isinstance(scenes, list) and idx < len(scenes) and isinstance(scenes[idx], dict)) else {}
            sc_txt = str(sc_obj.get("text", "")).strip()
            user_arch = str(sc_obj.get("user_override_archetype") or "").strip()
            if user_arch and user_arch in ALL_DYNAMIC_VISUAL_ARCHETYPES:
                arch_for_scene = user_arch
            elif sc_txt:
                arch_for_scene, _ = match_speech_to_visual_archetype(sc_txt, idx, num_scenes, used_in_plan, variation_seed=dyn_seed)
            else:
                arch_for_scene = "kinetic_quote_dm_finale" if (idx == num_scenes - 1 and num_scenes >= 2) else cloned_arch_seq[idx % len(cloned_arch_seq)]
            used_in_plan.append(arch_for_scene)
            plan.append({
                "style_family_id": base_fam["style_id"],
                "design_family": base_fam["design_family"],
                "act_name": act_name,
                "step_number": idx + 1,
                "visual_archetype": arch_for_scene,
                "has_grid": False,
                "has_floating_diamonds": False,
                "has_giant_bg_numbers": False,
                "header_style": str(active_ref.get("header_style", base_fam["header_style"])),
                "headline_style": str(active_ref.get("headline_style", base_fam["headline_style"])),
                "card_tilt_deg": float(active_ref.get("card_tilt_deg", base_fam.get("card_tilt_deg", 1.2))),
                "palette": dict(cloned_unified_pal),
                "spring_stiffness": float(active_ref.get("spring_stiffness", 215.0)),
                "spring_damping": float(active_ref.get("spring_damping", 13.5)),
                "stagger_delay_sec": float(active_ref.get("stagger_delay_sec", 0.042)),
                "camera_float_amp": float(active_ref.get("camera_float_amp", 6.5)),
                "card_variant_index": idx % 12
            })
        return plan

    # 2. اختيار ستايل واحد متكامل للفيديو بالكامل (إما باختيار المستخدم أو باختيار النظام العشوائي/التلقائي لكل فيديو جديد)
    if mode in PRO_STUDIO_STYLE_FAMILIES:
        chosen_fam = PRO_STUDIO_STYLE_FAMILIES[mode]
    else:
        chosen_fam_key = family_keys[rot_idx % len(family_keys)]
        chosen_fam = PRO_STUDIO_STYLE_FAMILIES[chosen_fam_key]

    unified_pal = dict(chosen_fam.get("unified_palette", chosen_fam["acts"]["body_steps"]))
    arch_seq = _select_non_repeating_archetype_sequence(
        num_scenes,
        chosen_fam.get("preferred_archetypes", ALL_DYNAMIC_VISUAL_ARCHETYPES),
        rotation_seed=rot_idx
    )

    plan = []
    used_in_plan = []
    dyn_seed = rot_idx + int(time.time() * 10) % 997
    for idx in range(max(1, num_scenes)):
        act_name = "hook_problem" if idx == 0 else ("outro_finale" if (idx == num_scenes - 1 and num_scenes >= 2) else "body_steps")
        sc_obj = scenes[idx] if (isinstance(scenes, list) and idx < len(scenes) and isinstance(scenes[idx], dict)) else {}
        sc_txt = str(sc_obj.get("text", "")).strip()
        user_arch = str(sc_obj.get("user_override_archetype") or "").strip()
        if user_arch and user_arch in ALL_DYNAMIC_VISUAL_ARCHETYPES:
            arch_for_scene = user_arch
        elif sc_txt:
            arch_for_scene, _ = match_speech_to_visual_archetype(sc_txt, idx, num_scenes, used_in_plan, variation_seed=dyn_seed)
        else:
            arch_for_scene = arch_seq[idx]
        used_in_plan.append(arch_for_scene)
        plan.append({
            "style_family_id": chosen_fam["style_id"],
            "design_family": chosen_fam["design_family"],
            "act_name": act_name,
            "step_number": idx + 1,
            "visual_archetype": arch_for_scene,
            "has_grid": chosen_fam["has_grid"],
            "has_floating_diamonds": chosen_fam["has_floating_diamonds"],
            "has_giant_bg_numbers": False,
            "header_style": chosen_fam["header_style"],
            "headline_style": chosen_fam["headline_style"],
            "card_tilt_deg": float(chosen_fam.get("card_tilt_deg", 1.2)),
            "palette": dict(unified_pal),
            "spring_stiffness": 215.0,
            "spring_damping": 13.5,
            "stagger_delay_sec": 0.042,
            "camera_float_amp": 6.0,
            "card_variant_index": (idx + rot_idx) % 12
        })
    return plan


def get_best_params_for_scene_type(scene_type: str) -> Dict[str, Any]:
    """استرجاع أفضل معاملات تصميم تطور إليها النظام سابقاً لهذا النوع من المشاهد مع احترام الثيم المخصص."""
    mem = load_evolution_memory()
    best_map = mem.get("scene_type_best_params", {})
    params = dict(best_map.get("default", _default_evolution_memory()["scene_type_best_params"]["default"]))
    if scene_type in best_map and isinstance(best_map[scene_type], dict):
        params.update(best_map[scene_type])

    active_ref = mem.get("active_reference_dna")
    if isinstance(active_ref, dict) and active_ref.get("enabled", True):
        if "spring_stiffness" in active_ref:
            params["spring_stiffness"] = float(active_ref["spring_stiffness"])
        if "spring_damping" in active_ref:
            params["spring_damping"] = float(active_ref["spring_damping"])
        if "theme_name" in active_ref:
            params["cloned_theme_name"] = str(active_ref["theme_name"])

    active_brand = mem.get("active_brand_theme")
    if isinstance(active_brand, dict) and active_brand.get("enabled", True):
        if "theme_name" in active_brand:
            params["cloned_theme_name"] = str(active_brand["theme_name"])
        if "style_mode" in active_brand:
            params["style_mode"] = str(active_brand["style_mode"])
        if "logo_path" in active_brand and active_brand.get("show_logo_watermark", True):
            params["brand_logo_path"] = active_brand.get("logo_path")
            params["brand_logo_position"] = active_brand.get("logo_position", "top_right")
    return params


def get_evolution_status_summary() -> Dict[str, Any]:
    """ملخص حالة تطور الذاكرة البصرية والهوية اللونية لعرضه في واجهة Streamlit."""
    mem = load_evolution_memory()
    best_map = mem.get("scene_type_best_params", {})
    learned_types = [k for k in best_map.keys() if k != "default"]
    cloned_styles = mem.get("cloned_reference_styles", {})
    scores = [float(v.get("best_score", 0.95)) for v in best_map.values() if isinstance(v, dict)]
    avg_score = round(sum(scores) / max(1, len(scores)), 3) if scores else float(mem.get("average_quality_score", 0.95))
    return {
        "learned_scene_types_count": max(len(learned_types), len(best_map)) + len(ALL_DYNAMIC_VISUAL_ARCHETYPES),
        "cloned_reference_count": len(cloned_styles),
        "total_evaluations": int(mem.get("total_evaluations", 0)),
        "total_evolutions_triggered": int(mem.get("total_evolutions_triggered", 0)),
        "average_quality_score": avg_score,
        "active_studio_style_mode": mem.get("active_studio_style_mode", "auto_vary_pro"),
        "style_rotation_counter": int(mem.get("style_rotation_counter", 0)),
        "active_reference_dna": mem.get("active_reference_dna"),
        "active_brand_theme": mem.get("active_brand_theme"),
        "cloned_styles_list": list(cloned_styles.keys())
    }


# ==============================================================================
# 2. محرك استخراج الهوية البصرية من اللوقو / باليت الألوان ومنتقي الألوان اليدوي
# ==============================================================================
def _fast_numpy_kmeans_palette(pixels_rgb: np.ndarray, k: int = 5, max_iters: int = 10) -> np.ndarray:
    """خوارزمية K-Means متجهية سريعة عبر NumPy لاستخراج الألوان السائدة بدون استهلاك ذاكرة."""
    if pixels_rgb.shape[0] < k:
        return np.array([[15, 23, 42], [27, 174, 202], [250, 204, 21], [16, 185, 129], [241, 245, 249]], dtype=np.uint8)

    rng = np.random.default_rng(42)
    indices = np.linspace(0, pixels_rgb.shape[0] - 1, k, dtype=int)
    centers = pixels_rgb[indices].astype(np.float32)

    for _ in range(max_iters):
        dists = np.sum((pixels_rgb[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(dists, axis=1)
        new_centers = np.zeros_like(centers)
        for ci in range(k):
            mask = (labels == ci)
            if np.any(mask):
                new_centers[ci] = np.mean(pixels_rgb[mask], axis=0)
            else:
                new_centers[ci] = pixels_rgb[rng.integers(0, pixels_rgb.shape[0])]
        if np.allclose(centers, new_centers, atol=1.5):
            centers = new_centers
            break
        centers = new_centers

    counts = np.array([np.sum(labels == ci) for ci in range(k)])
    order = np.argsort(-counts)
    return np.clip(centers[order], 0, 255).astype(np.uint8)


def _saturation_and_luma(rgb: Tuple[int, int, int]) -> Tuple[float, float]:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / max(1e-5, mx) if mx > 0 else 0.0
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return sat, luma


def extract_brand_palette_from_image(
    image_path: str,
    style_alias: Optional[str] = None,
    show_logo_watermark: bool = True,
    logo_position: str = "top_right",
    prefer_dark_bg: bool = True,
    register_in_themes: bool = True
) -> Dict[str, Any]:
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"صورة اللوقو أو الباليت غير موجودة: {image_path}")

    with Image.open(image_path) as im:
        im_rgba = im.convert("RGBA")
        im_small = im_rgba.resize((160, 160), Image.Resampling.BILINEAR)
        arr = np.array(im_small, dtype=np.uint8)

    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]
    valid_mask = alpha >= 64
    valid_pixels = rgb[valid_mask] if np.any(valid_mask) else rgb.reshape((-1, 3))

    if valid_pixels.shape[0] > 30:
        r_f = valid_pixels[:, 0].astype(np.float32) / 255.0
        g_f = valid_pixels[:, 1].astype(np.float32) / 255.0
        b_f = valid_pixels[:, 2].astype(np.float32) / 255.0
        mx = np.maximum(np.maximum(r_f, g_f), b_f)
        mn = np.minimum(np.minimum(r_f, g_f), b_f)
        sat = (mx - mn) / np.maximum(1e-5, mx)
        luma = 0.2126 * r_f + 0.7152 * g_f + 0.0722 * b_f
        brand_mask = (sat > 0.14) & (luma > 0.08) & (luma < 0.93)
        brand_pixels = valid_pixels[brand_mask] if np.sum(brand_mask) >= 25 else valid_pixels
    else:
        brand_pixels = valid_pixels

    palette = _fast_numpy_kmeans_palette(brand_pixels.astype(np.float32), k=5)
    colors_list = [tuple(int(x) for x in c) for c in palette]

    scored_colors = sorted(
        colors_list,
        key=lambda c: (_saturation_and_luma(c)[0] * 0.75 + 0.25 * (1.0 - abs(_saturation_and_luma(c)[1] - 0.55))),
        reverse=True
    )
    primary_c = scored_colors[0]
    secondary_c = scored_colors[1] if len(scored_colors) > 1 else primary_c
    for cand in scored_colors[1:]:
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(primary_c, cand)))
        if dist >= 48.0:
            secondary_c = cand
            break

    accent_c = scored_colors[min(2, len(scored_colors) - 1)]

    if prefer_dark_bg:
        top_bg = (
            max(8, min(28, int(primary_c[0] * 0.12 + 8))),
            max(12, min(34, int(primary_c[1] * 0.12 + 12))),
            max(22, min(48, int(primary_c[2] * 0.16 + 22)))
        )
        bottom_bg = (
            max(12, min(38, int(secondary_c[0] * 0.15 + 12))),
            max(16, min(44, int(secondary_c[1] * 0.15 + 16))),
            max(28, min(60, int(secondary_c[2] * 0.20 + 26)))
        )
        style_mode = "dark_stage_pro"
        card_bg = (255, 255, 255)
    else:
        top_bg = (
            min(252, int(242 + primary_c[0] * 0.04)),
            min(253, int(245 + primary_c[1] * 0.03)),
            min(255, int(249 + primary_c[2] * 0.02))
        )
        bottom_bg = (228, 236, 246)
        style_mode = "clean_saas_light"
        card_bg = (255, 255, 255)

    theme_key = style_alias or "custom_brand_theme"
    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": accent_c,
        "card_bg": card_bg
    }

    brand_profile = {
        "theme_name": theme_key,
        "enabled": True,
        "source_image": os.path.basename(image_path),
        "logo_path": os.path.abspath(image_path),
        "show_logo_watermark": bool(show_logo_watermark),
        "logo_position": str(logo_position or "top_right"),
        "style_mode": style_mode,
        "is_light_mode": not prefer_dark_bg,
        "primary_hex": rgb_to_hex(primary_c),
        "secondary_hex": rgb_to_hex(secondary_c),
        "accent_hex": rgb_to_hex(accent_c),
        "bg_hex": rgb_to_hex(top_bg),
        "palette_hex": [rgb_to_hex(c) for c in colors_list],
        "theme_palette": theme_dict,
        "updated_at": int(time.time())
    }

    if register_in_themes:
        try:
            import motion_text
            motion_text.MOTION_THEMES[theme_key] = theme_dict
        except Exception:
            pass

    mem = load_evolution_memory()
    mem["active_brand_theme"] = brand_profile
    save_evolution_memory(mem)
    force_free_ram()
    return brand_profile


def apply_custom_brand_colors(
    primary_hex: str,
    secondary_hex: str,
    bg_hex: str = "#0B1325",
    style_mode: str = "dark_stage_pro",
    logo_path: Optional[str] = None,
    show_logo_watermark: bool = True,
    logo_position: str = "top_right",
    theme_key: str = "custom_brand_theme"
) -> Dict[str, Any]:
    primary_c = hex_to_rgb(primary_hex, (27, 174, 202))
    secondary_c = hex_to_rgb(secondary_hex, (250, 204, 21))
    top_bg = hex_to_rgb(bg_hex, (11, 24, 31))

    _, bg_luma = _saturation_and_luma(top_bg)
    is_light = (bg_luma >= 0.58) or (style_mode == "clean_saas_light")

    if is_light:
        bottom_bg = (
            max(200, top_bg[0] - 14),
            max(206, top_bg[1] - 12),
            max(216, top_bg[2] - 8)
        )
        card_bg = (255, 255, 255)
        eff_style_mode = "clean_saas_light"
    else:
        bottom_bg = (
            min(255, int(top_bg[0] * 0.85 + secondary_c[0] * 0.12 + 6)),
            min(255, int(top_bg[1] * 0.85 + secondary_c[1] * 0.12 + 8)),
            min(255, int(top_bg[2] * 0.85 + secondary_c[2] * 0.15 + 12))
        )
        card_bg = (
            max(12, min(42, top_bg[0] + 8)),
            max(18, min(52, top_bg[1] + 10)),
            max(32, min(72, top_bg[2] + 14))
        )
        eff_style_mode = "dark_stage_pro"

    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": secondary_c,
        "card_bg": card_bg
    }

    mem = load_evolution_memory()
    prev_brand = mem.get("active_brand_theme") or {}
    eff_logo = logo_path if logo_path is not None else prev_brand.get("logo_path")

    brand_profile = {
        "theme_name": theme_key,
        "enabled": True,
        "logo_path": eff_logo if (eff_logo and os.path.exists(str(eff_logo))) else None,
        "show_logo_watermark": bool(show_logo_watermark),
        "logo_position": str(logo_position or "top_right"),
        "style_mode": eff_style_mode,
        "is_light_mode": is_light,
        "primary_hex": rgb_to_hex(primary_c),
        "secondary_hex": rgb_to_hex(secondary_c),
        "bg_hex": rgb_to_hex(top_bg),
        "palette_hex": prev_brand.get("palette_hex", [rgb_to_hex(primary_c), rgb_to_hex(secondary_c), rgb_to_hex(top_bg)]),
        "theme_palette": theme_dict,
        "updated_at": int(time.time())
    }

    try:
        import motion_text
        motion_text.MOTION_THEMES[theme_key] = theme_dict
    except Exception:
        pass

    mem["active_brand_theme"] = brand_profile
    save_evolution_memory(mem)
    return brand_profile


def get_active_brand_theme() -> Optional[Dict[str, Any]]:
    mem = load_evolution_memory()
    brand = mem.get("active_brand_theme")
    if isinstance(brand, dict) and brand.get("enabled", True):
        try:
            import motion_text
            t_name = brand.get("theme_name", "custom_brand_theme")
            if "theme_palette" in brand:
                motion_text.MOTION_THEMES[t_name] = brand["theme_palette"]
        except Exception:
            pass
        return brand
    return None


def clear_active_brand_theme() -> None:
    mem = load_evolution_memory()
    mem["active_brand_theme"] = None
    save_evolution_memory(mem)


# ==============================================================================
# 3. محلل ومستنسخ الفيديو المرجعي الشامل (Colors + Shapes + Illustrations + Animation Physics)
# ==============================================================================
def _classify_shot_visual_archetype(frm_rgb: np.ndarray, shot_idx: int) -> str:
    """
    تحليل البنية الهندسية وتوزيع الأشكال داخل اللقطة المرجعية لاختيار الرسمة والأنيميشن المقابل لها:
    يفحص: التناظر الأفقي (مقارنات قبل/بعد أو ميزان)، التركز الدائري في المنتصف (رادار أو عدسة)،
    تعدد الصفوف الأفقية (قائمة خطوات مرقمة أو تايملاين)، أو الشبكة الرباعية.
    """
    sh, sw, _ = frm_rgb.shape
    stage = frm_rgb[int(sh * 0.22):int(sh * 0.78), int(sw * 0.08):int(sw * 0.92), :].astype(np.float32)
    gray = 0.299 * stage[:, :, 0] + 0.587 * stage[:, :, 1] + 0.114 * stage[:, :, 2]

    gx = np.abs(np.diff(gray, axis=1))[:-1, :]
    gy = np.abs(np.diff(gray, axis=0))[:, :-1]
    edges = gx + gy

    h_mid, w_mid = edges.shape[0] // 2, edges.shape[1] // 2
    left_e = float(np.mean(edges[:, :w_mid - 6]))
    right_e = float(np.mean(edges[:, w_mid + 6:]))
    center_col_e = float(np.mean(edges[:, max(0, w_mid - 8):min(edges.shape[1], w_mid + 8)]))

    # فحص عدد القمم الأفقية (الصفوف المرقمة أو القوائم)
    row_profile = np.mean(edges, axis=1)
    row_thresh = float(np.mean(row_profile) + 0.35 * np.std(row_profile))
    above = row_profile > row_thresh
    row_peaks = int(np.sum(np.diff(above.astype(int)) == 1))

    # فحص وجود بطاقة بيضاء كبيرة في المركز
    bright_ratio = float(np.mean(gray > 205.0))

    candidates = [
        "bezier_growth_nodes",
        "live_magnifier_scanner",
        "radar_target_sweep",
        "pack_3d_extruding_pillars",
        "macos_folder_counter_list",
        "damped_balance_scale",
        "dark_cinema_fanned_cards",
        "reels_6card_showcase_grid",
        "interactive_profile_follow_card",
        "chrono_ring_3d_counter",
        "nle_timeline_matrix"
    ]

    if row_peaks >= 4:
        return "macos_folder_counter_list" if (shot_idx % 2 == 0) else "nle_timeline_matrix"
    if abs(left_e - right_e) < 3.5 and center_col_e < min(left_e, right_e) * 0.82:
        return "dark_cinema_fanned_cards" if (shot_idx % 2 == 0) else "damped_balance_scale"
    if bright_ratio >= 0.28:
        bright_choices = ["chrono_ring_3d_counter", "bezier_growth_nodes", "live_magnifier_scanner", "pack_3d_extruding_pillars"]
        return bright_choices[shot_idx % len(bright_choices)]
    return candidates[shot_idx % len(candidates)]


def _build_act_palette_from_pixels(px_chunk: np.ndarray, fallback_family: Dict[str, Any], act_key: str) -> Dict[str, Any]:
    base_act = dict(fallback_family["acts"][act_key])
    if px_chunk is None or px_chunk.shape[0] < 20:
        return base_act

    pal = _fast_numpy_kmeans_palette(px_chunk.astype(np.float32), k=5)
    colors = [tuple(int(x) for x in c) for c in pal]

    by_sat = sorted(colors, key=lambda c: (_saturation_and_luma(c)[0] * 0.75 + 0.25 * (1.0 - abs(_saturation_and_luma(c)[1] - 0.52))), reverse=True)

    top_bg = colors[0]
    bottom_bg = colors[1] if len(colors) > 1 else colors[0]
    primary_c = by_sat[0]
    secondary_c = by_sat[1] if len(by_sat) > 1 else (255, 255, 255)

    _, top_luma = _saturation_and_luma(top_bg)
    is_light = (top_luma >= 0.56)
    headline_txt = (15, 23, 42) if is_light else (255, 255, 255)
    sticker_bg = (255, 255, 255) if (not is_light and _saturation_and_luma(top_bg)[0] > 0.35) else primary_c
    _, st_luma = _saturation_and_luma(sticker_bg)
    sticker_txt = (11, 24, 31) if st_luma >= 0.55 else (255, 255, 255)

    base_act.update({
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "card_bg": (255, 255, 255) if (is_light or _saturation_and_luma(top_bg)[0] > 0.25) else (24, 22, 46),
        "is_light_bg": is_light,
        "sticker_bg": sticker_bg,
        "sticker_txt": sticker_txt,
        "headline_txt": headline_txt
    })
    return base_act


def extract_reference_video_dna(
    reference_video_path: str,
    style_alias: Optional[str] = None,
    max_sample_seconds: float = 40.0,
    sample_fps: int = 6,
    register_in_themes: bool = True
) -> Dict[str, Any]:
    """
    تحليل واستنساخ الفيديو المرجعي بالكامل (الألوان + الأشكال + الرسومات + الأنيميشن والتحريك):
    1. يستخرج البصمة اللونية والضوئية الموحدة.
    2. يحلل كل لقطة في الفيديو المرجعي لاستخراج تسلسل الأشكال والرسومات (`cloned_archetype_sequence`)
       وهندسة البطاقات (`header_style`, `headline_style`, `card_tilt_deg`).
    3. يقيس سرعة الحركة البصرية والارتداد لضبط فيزياء الزنبرك (`spring_stiffness`, `spring_damping`, `stagger_delay_sec`).
    """
    if not reference_video_path or not os.path.exists(reference_video_path):
        raise FileNotFoundError(f"الفيديو المرجعي غير موجود: {reference_video_path}")

    sw, sh = 160, 284
    frame_bytes = sw * sh * 3
    cmd = [
        "ffmpeg", "-v", "error", "-threads", "1",
        "-t", str(float(max_sample_seconds)),
        "-i", reference_video_path,
        "-vf", f"scale={sw}:{sh},fps={int(sample_fps)}",
        "-threads", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
    ]

    proc = None
    frame_diffs: List[float] = []
    cut_timestamps: List[float] = [0.0]
    per_frame_bg_pixels: List[np.ndarray] = []
    representative_shot_frames: List[np.ndarray] = []
    top_edge_energy = 0.0
    mid_edge_energy = 0.0
    bot_edge_energy = 0.0
    n_frames = 0
    prev_gray: Optional[np.ndarray] = None

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes)
        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            frm = np.frombuffer(raw, dtype=np.uint8).reshape((sh, sw, 3)).copy()
            gray = (0.299 * frm[:, :, 0] + 0.587 * frm[:, :, 1] + 0.114 * frm[:, :, 2]).astype(np.float32)

            if prev_gray is not None:
                diff = float(np.mean(np.abs(gray - prev_gray)))
                frame_diffs.append(diff)
                if diff > 22.0 and (n_frames / float(sample_fps) - cut_timestamps[-1]) >= 0.65:
                    cut_timestamps.append(round(n_frames / float(sample_fps), 2))
                    representative_shot_frames.append(frm)

            if n_frames == 2:
                representative_shot_frames.append(frm)

            prev_gray = gray

            gx = np.abs(np.diff(gray, axis=1))
            gy = np.abs(np.diff(gray, axis=0))
            grad_mag = gx[:-1, :] + gy[:, :-1]
            h3 = grad_mag.shape[0] // 3
            top_edge_energy += float(np.mean(grad_mag[:h3, :]))
            mid_edge_energy += float(np.mean(grad_mag[h3:2 * h3, :]))
            bot_edge_energy += float(np.mean(grad_mag[2 * h3:, :]))

            if n_frames % 2 == 0:
                sub_px = frm[::6, ::6, :].reshape((-1, 3))
                per_frame_bg_pixels.append(sub_px)

            n_frames += 1
            if n_frames >= int(max_sample_seconds * sample_fps):
                break
    finally:
        if proc is not None:
            try:
                if proc.stdout:
                    proc.stdout.close()
                proc.kill()
            except Exception:
                pass
        force_free_ram()

    total_sampled_sec = max(1.0, n_frames / float(max(1, sample_fps)))
    mean_velocity = float(np.mean(frame_diffs)) if frame_diffs else 9.5
    p90_velocity = float(np.percentile(frame_diffs, 90)) if frame_diffs else 18.0
    num_cuts = max(1, len(cut_timestamps))
    avg_shot_dur = round(total_sampled_sec / float(num_cuts), 2)

    energy_norm = max(0.0, min(1.0, (mean_velocity - 3.0) / 18.0))
    recommended_stiffness = round(195.0 + 95.0 * energy_norm, 1)
    recommended_damping = round(14.5 - 3.2 * energy_norm, 1)
    recommended_handoff_sec = round(max(0.28, min(0.45, 0.40 - 0.10 * energy_norm)), 2)

    if per_frame_bg_pixels:
        all_px = np.vstack(per_frame_bg_pixels).astype(np.float32)
        n_chunks = len(per_frame_bg_pixels)
        c1 = max(1, n_chunks // 4)
        c2 = max(c1 + 1, (n_chunks * 3) // 4)
        body_px = np.vstack(per_frame_bg_pixels[c1:c2]) if c2 > c1 else all_px
        palette = _fast_numpy_kmeans_palette(all_px, k=5)
        mean_luma = float(np.mean(all_px)) / 255.0
        contrast_std = float(np.std(all_px)) / 255.0
    else:
        palette = np.array([[13, 118, 142], [27, 174, 202], [255, 255, 255], [7, 68, 86], [250, 204, 21]], dtype=np.uint8)
        body_px = palette.astype(np.float32)
        mean_luma = 0.35
        contrast_std = 0.28

    colors_list = [tuple(int(x) for x in c) for c in palette]
    by_sat = sorted(colors_list, key=lambda c: (_saturation_and_luma(c)[0] * (0.4 + _saturation_and_luma(c)[1])), reverse=True)
    primary_c = by_sat[0]
    secondary_c = by_sat[min(1, len(by_sat) - 1)]
    accent_c = by_sat[min(2, len(by_sat) - 1)]

    r_m, g_m, b_m = float(np.mean(body_px[:, 0])), float(np.mean(body_px[:, 1])), float(np.mean(body_px[:, 2]))
    if g_m > r_m + 18 and b_m > r_m + 18:
        detected_family = "byw_cyan_agency"
    elif r_m < 65 and b_m > g_m + 10 and mean_luma < 0.28:
        detected_family = "baghdadi_luxury_plum"
    elif b_m > r_m + 15 and mean_luma >= 0.42:
        detected_family = "mazen_blueprint_collage"
    else:
        detected_family = "byw_cyan_agency"

    base_fam_spec = PRO_STUDIO_STYLE_FAMILIES[detected_family]
    unified_body_pal = _build_act_palette_from_pixels(body_px, base_fam_spec, "body_steps")
    multi_act_palettes = {
        "hook_problem": dict(unified_body_pal),
        "body_steps": dict(unified_body_pal),
        "outro_finale": dict(unified_body_pal)
    }

    # استخراج تسلسل الأشكال والرسومات (Visual Archetypes) من لقطات الفيديو المرجعي الفعلية!
    cloned_archetypes: List[str] = []
    for s_idx, s_frm in enumerate(representative_shot_frames[:12]):
        arch = _classify_shot_visual_archetype(s_frm, s_idx)
        if cloned_archetypes and arch == cloned_archetypes[-1]:
            pref = base_fam_spec.get("preferred_archetypes", ALL_DYNAMIC_VISUAL_ARCHETYPES)
            arch = pref[(s_idx + 1) % len(pref)]
        cloned_archetypes.append(arch)

    if len(cloned_archetypes) < 6:
        for extra_a in base_fam_spec.get("preferred_archetypes", ALL_DYNAMIC_VISUAL_ARCHETYPES):
            if not cloned_archetypes or extra_a != cloned_archetypes[-1]:
                cloned_archetypes.append(extra_a)
            if len(cloned_archetypes) >= 8:
                break

    is_light_ref = bool(unified_body_pal.get("is_light_bg", False))
    top_bg = unified_body_pal["top_bg"]
    bottom_bg = unified_body_pal["bottom_bg"]

    tot_e = max(1e-5, top_edge_energy + mid_edge_energy + bot_edge_energy)
    top_w = round(top_edge_energy / tot_e, 3)
    mid_w = round(mid_edge_energy / tot_e, 3)
    bot_w = round(bot_edge_energy / tot_e, 3)

    preferred_caption = "bottom_modern" if bot_w >= top_w * 0.85 else "top_compact"
    file_hash = hashlib.md5(f"{os.path.basename(reference_video_path)}_{os.path.getsize(reference_video_path)}".encode()).hexdigest()[:8]
    theme_key = style_alias or f"ref_cloned_{file_hash}"

    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": accent_c,
        "card_bg": unified_body_pal.get("card_bg", (255, 255, 255))
    }

    dna_profile = {
        "style_id": theme_key,
        "source_video": os.path.basename(reference_video_path),
        "extracted_at": int(time.time()),
        "enabled": True,
        "detected_design_family": detected_family,
        "detected_family_label_ar": base_fam_spec["label_ar"],
        "has_grid": base_fam_spec["has_grid"],
        "has_floating_diamonds": base_fam_spec["has_floating_diamonds"],
        "header_style": base_fam_spec["header_style"],
        "headline_style": base_fam_spec["headline_style"],
        "card_tilt_deg": base_fam_spec.get("card_tilt_deg", 1.2),
        "cloned_archetype_sequence": cloned_archetypes,
        "multi_act_palettes": multi_act_palettes,
        "theme_name": theme_key,
        "theme_palette": theme_dict,
        "style_mode": "clean_saas_light" if is_light_ref else "dark_stage_pro",
        "is_light_mode": is_light_ref,
        "frame_diff_velocity": round(mean_velocity, 2),
        "peak_optical_velocity": round(p90_velocity, 2),
        "avg_shot_duration_sec": avg_shot_dur,
        "spring_stiffness": recommended_stiffness,
        "spring_damping": recommended_damping,
        "handoff_duration_sec": recommended_handoff_sec,
        "stagger_delay_sec": round(max(0.032, min(0.055, 0.050 - 0.018 * energy_norm)), 3),
        "camera_float_amp": round(5.5 + 3.0 * energy_norm, 2),
        "brightness_mean": round(mean_luma, 3),
        "contrast_std": round(contrast_std, 3),
        "layout_safe_zones": {
            "top_zone_weight": top_w,
            "center_zone_weight": mid_w,
            "bottom_zone_weight": bot_w,
            "preferred_caption_mode": preferred_caption
        }
    }

    if register_in_themes:
        try:
            import motion_text
            motion_text.MOTION_THEMES[theme_key] = theme_dict
        except Exception:
            pass

    mem = load_evolution_memory()
    mem["active_reference_dna"] = dna_profile
    mem["active_studio_style_mode"] = "clone_reference"
    mem.setdefault("cloned_reference_styles", {})[theme_key] = dna_profile
    save_evolution_memory(mem)
    force_free_ram()
    return dna_profile


def activate_cloned_reference_style(style_id: Optional[str]) -> Optional[Dict[str, Any]]:
    mem = load_evolution_memory()
    if not style_id or style_id == "none":
        mem["active_reference_dna"] = None
        if mem.get("active_studio_style_mode") == "clone_reference":
            mem["active_studio_style_mode"] = "auto_vary_pro"
        save_evolution_memory(mem)
        return None
    styles = mem.get("cloned_reference_styles", {})
    if style_id in styles:
        dna = dict(styles[style_id])
        dna["enabled"] = True
        mem["active_reference_dna"] = dna
        mem["active_studio_style_mode"] = "clone_reference"
        save_evolution_memory(mem)
        try:
            import motion_text
            if "theme_palette" in dna:
                motion_text.MOTION_THEMES[style_id] = dna["theme_palette"]
        except Exception:
            pass
        return dna
    return None


# ==============================================================================
# 4. الناقد البصري وحلقة التطور التلقائي (Self-Evolving Visual Critic & Healer)
# ==============================================================================
def _compute_wcag_contrast_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    stage_crop = frame_rgb[int(h * 0.10):int(h * 0.88), int(w * 0.06):int(w * 0.94), :].astype(np.float32) / 255.0
    luma = 0.2126 * stage_crop[:, :, 0] + 0.7152 * stage_crop[:, :, 1] + 0.0722 * stage_crop[:, :, 2]
    p92 = float(np.percentile(luma, 92))
    p08 = float(np.percentile(luma, 8))
    contrast_ratio = (p92 + 0.05) / (p08 + 0.05)
    return round(min(1.0, max(0.2, contrast_ratio / 6.5)), 4)


def _compute_visual_clutter_score(frame_rgb: np.ndarray) -> Tuple[float, float]:
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edges = (gx[:-1, :] + gy[:, :-1]) > 28.0
    clutter_ratio = float(np.mean(edges))

    if 0.020 <= clutter_ratio <= 0.16:
        score = 0.97
    elif clutter_ratio > 0.16:
        score = max(0.40, 0.97 - (clutter_ratio - 0.16) * 3.0)
    else:
        score = max(0.55, 0.55 + (clutter_ratio / 0.020) * 0.42)
    return round(score, 4), round(clutter_ratio, 4)


def _compute_safe_margin_clearance_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    margin_x = max(4, int(w * 0.028))
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    left_strip = np.abs(np.diff(gray[:, :margin_x], axis=0))
    right_strip = np.abs(np.diff(gray[:, w - margin_x:], axis=0))
    sharp_edge_ratio = float(np.mean(left_strip > 42.0) + np.mean(right_strip > 42.0)) * 0.5
    return round(max(0.40, min(1.0, 1.0 - sharp_edge_ratio * 4.5)), 4)


def _compute_visual_mass_balance_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    salience = np.abs(gray - np.median(gray))
    mid_x = w // 2
    left_mass = float(np.mean(salience[:, :mid_x]))
    right_mass = float(np.mean(salience[:, mid_x:]))
    imbalance = abs(left_mass - right_mass) / max(1.0, left_mass + right_mass)
    return round(max(0.55, min(1.0, 1.0 - imbalance * 0.9)), 4)


def evaluate_and_evolve_frame(
    rendered_frame_rgb: np.ndarray,
    scene_meta: Dict[str, Any],
    render_callback: Optional[Callable[[Dict[str, Any]], np.ndarray]] = None,
    llm_vision_fn: Optional[Callable[..., Any]] = None,
    quality_threshold: float = 0.85,
    persist_to_disk: bool = True
) -> Tuple[np.ndarray, Dict[str, Any]]:
    curr_frame = rendered_frame_rgb
    curr_meta = dict(scene_meta or {})
    scene_type = str(curr_meta.get("scene_type") or curr_meta.get("archetype") or "default")

    best_params = get_best_params_for_scene_type(scene_type)
    for k, v in best_params.items():
        curr_meta.setdefault(k, v)

    evolution_triggered = False
    attempt = 0
    max_attempts = 2 if callable(render_callback) else 0

    while True:
        c_score = _compute_wcag_contrast_score(curr_frame)
        clutter_score, clutter_ratio = _compute_visual_clutter_score(curr_frame)
        margin_score = _compute_safe_margin_clearance_score(curr_frame)
        balance_score = _compute_visual_mass_balance_score(curr_frame)

        overall_score = round(
            0.36 * c_score +
            0.28 * clutter_score +
            0.20 * margin_score +
            0.16 * balance_score,
            4
        )

        report = {
            "overall_score": overall_score,
            "wcag_contrast_score": c_score,
            "clutter_score": clutter_score,
            "clutter_ratio": clutter_ratio,
            "safe_margin_score": margin_score,
            "mass_balance_score": balance_score,
            "evolution_triggered": evolution_triggered,
            "attempts": attempt + 1
        }

        if overall_score >= quality_threshold or attempt >= max_attempts or not callable(render_callback):
            break

        evolution_triggered = True
        attempt += 1
        if c_score < 0.80:
            curr_meta["contrast_boost"] = round(float(curr_meta.get("contrast_boost", 1.0)) * 1.18, 2)
            curr_meta["bg_blur_strength"] = min(24, int(curr_meta.get("bg_blur_strength", 16)) + 4)
            curr_meta["accent_glow"] = round(min(0.55, float(curr_meta.get("accent_glow", 0.28)) + 0.08), 2)
        if margin_score < 0.82 or clutter_ratio > 0.16:
            curr_meta["font_scale"] = round(max(0.84, float(curr_meta.get("font_scale", 1.0)) * 0.92), 3)
            curr_meta["card_padding"] = min(28, int(curr_meta.get("card_padding", 18)) + 4)
        if clutter_ratio < 0.020:
            curr_meta["font_scale"] = round(min(1.14, float(curr_meta.get("font_scale", 1.0)) * 1.08), 3)
            curr_meta["accent_glow"] = round(min(0.50, float(curr_meta.get("accent_glow", 0.28)) + 0.06), 2)

        try:
            new_frame = render_callback(curr_meta)
            if isinstance(new_frame, np.ndarray) and new_frame.shape == curr_frame.shape:
                curr_frame = new_frame
        except Exception as e:
            logger.debug(f"Render callback during evolution failed: {e}")
            break

    if persist_to_disk:
        try:
            mem = load_evolution_memory()
            mem["total_evaluations"] = int(mem.get("total_evaluations", 0)) + 1
            if evolution_triggered:
                mem["total_evolutions_triggered"] = int(mem.get("total_evolutions_triggered", 0)) + 1

            best_map = mem.setdefault("scene_type_best_params", {})
            prev_entry = best_map.get(scene_type, {})
            prev_best = float(prev_entry.get("best_score", 0.0))

            if overall_score >= prev_best - 0.02:
                best_map[scene_type] = {
                    "font_scale": float(curr_meta.get("font_scale", 1.0)),
                    "card_padding": int(curr_meta.get("card_padding", 18)),
                    "bg_blur_strength": int(curr_meta.get("bg_blur_strength", 16)),
                    "accent_glow": float(curr_meta.get("accent_glow", 0.28)),
                    "spring_stiffness": float(curr_meta.get("spring_stiffness", 210.0)),
                    "spring_damping": float(curr_meta.get("spring_damping", 13.5)),
                    "contrast_boost": float(curr_meta.get("contrast_boost", 1.0)),
                    "best_score": round(max(prev_best, overall_score), 4),
                    "samples": int(prev_entry.get("samples", 0)) + 1
                }

            all_scores = [float(v.get("best_score", 0.95)) for v in best_map.values() if isinstance(v, dict)]
            if all_scores:
                mem["average_quality_score"] = round(sum(all_scores) / len(all_scores), 4)
            save_evolution_memory(mem)
        except Exception as e:
            logger.debug(f"Evolution memory persistence notice: {e}")

    return curr_frame, report