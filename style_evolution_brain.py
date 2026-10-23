# -*- coding: utf-8 -*-
"""
style_evolution_brain.py - محرك استنساخ تصميم الفيديوهات المرجعية، توليد الستايلات الاحترافية المتجددة، والناقد البصري الذاتي
================================================================================================================================
Principal Video DSP & Self-Evolving Visual Intelligence Engine (Zero-OOM Architecture):
1. محلل ومستنسخ التصميم الكامل للفيديو المرجعي (`extract_reference_video_dna` - "سوي لي نفس التصميم بالضبط"):
   - يقرأ الفيديو المرجعي عبر أنبوب `FFmpeg` أحادي الخيط بدقة مصغرة (`160x284 @ 6fps`) باستهلاك ذاكرة `< 3MB`.
   - يستخرج البصمة اللونية المتعددة المراحل (`Multi-Act Scene Palettes`: المرحلة الافتتاحية، مرحلة الشرح والخطوات، ومرحلة الخاتمة)
     بحيث يستنسخ الفيديوهات التي تغير خلفياتها وألوانها داخل الفيديو الواحد (مثل انتقال `6873.mp4` من الكحلي الداكن إلى السيان المشرق ثم الأبيض النظيف).
   - يكتشف هندسة التصميم المرجعي (`design_family`: بطاقات الوكالة البيضاء المائلة مع ستيكر الكلمات `byw_cyan_agency`،
     أو المخطط الهندسي السماوي مع الخطوات المرقمة `mazen_blueprint_collage`، أو مختبر الإعلانات البنفسجي الفاخر ذي التبويبات العلوية `baghdadi_luxury_plum`).
2. محرك تنويع وتوليد الستايلات الاحترافية التلقائي (`PRO_STUDIO_STYLE_FAMILIES` & `get_or_rotate_pro_style_plan`):
   - يضم 6 عائلات تصميم أستوديو فائقة الحداثة مستنسخة هندسياً من أجمل فيديوهات الموشن جرافيك (`6873.mp4`, `6842.mp4`, `6871.mp4`).
   - يغير الستايل تلقائياً في كل مرة يُنتج فيها فيديو جديد (`Auto-Vary Per Run`)، وينوّع أطوار التصميم والخلفيات والبطاقات
     بين مشاهد الفيديو نفسه بسلاسة تامة دون أي تكرار ممل.
3. محرك الهوية البصرية واستخراج ألوان اللوقو أو الباليت (`extract_brand_palette_from_image` & `apply_custom_brand_colors`).
4. الناقد البصري وحلقة التطور التلقائي (`evaluate_and_evolve_frame` + `outputs/evolution_memory.json`).
"""

import os
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
# 0. كتالوج عائلات الستايلات الاحترافية المستنسخة من الفيديوهات المرجعية (6873, 6842, 6871)
# ==============================================================================
PRO_STUDIO_STYLE_FAMILIES: Dict[str, Dict[str, Any]] = {
    "byw_cyan_agency": {
        "style_id": "byw_cyan_agency",
        "label_ar": "🎬 ستايل وكالة BYW الاحترافي (تدرج كحلي وسيان + بطاقات بيضاء مائلة وستيكر نصي - 6873)",
        "design_family": "byw_cyan_agency",
        "has_grid": True,
        "has_floating_diamonds": True,
        "has_giant_bg_numbers": True,
        "header_style": "step_dots_pill",
        "headline_style": "sticker_highlight",
        "acts": {
            "hook_problem": {
                "top_bg": (11, 24, 31),
                "bottom_bg": (16, 38, 48),
                "glow": (27, 174, 202),
                "primary": (27, 174, 202),
                "secondary": (255, 255, 255),
                "accent": (239, 68, 68),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (27, 174, 202),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (27, 174, 202),
                "bottom_bg": (8, 109, 133),
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
                "top_bg": (248, 252, 254),
                "bottom_bg": (228, 244, 250),
                "glow": (27, 174, 202),
                "primary": (27, 174, 202),
                "secondary": (11, 24, 31),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (27, 174, 202),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (11, 24, 31)
            }
        }
    },
    "mazen_blueprint_collage": {
        "style_id": "mazen_blueprint_collage",
        "label_ar": "📐 ستايل المخطط السماوي والخطوات المرقمة 1-2-3-4 (إطار تحديد الماوس وشارات زرقاء - 6842)",
        "design_family": "mazen_blueprint_collage",
        "has_grid": True,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": True,
        "header_style": "corner_punctuation_watermark",
        "headline_style": "selection_box_handle",
        "acts": {
            "hook_problem": {
                "top_bg": (212, 234, 252),
                "bottom_bg": (152, 198, 238),
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
                "top_bg": (147, 201, 242),
                "bottom_bg": (198, 226, 248),
                "glow": (37, 99, 235),
                "primary": (2, 132, 199),
                "secondary": (30, 58, 138),
                "accent": (14, 165, 233),
                "card_bg": (240, 248, 255),
                "is_light_bg": True,
                "sticker_bg": (37, 99, 235),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            },
            "outro_finale": {
                "top_bg": (224, 240, 254),
                "bottom_bg": (176, 214, 246),
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
        "label_ar": "🟣 ستايل مختبر الإعلانات البنفسجي الفاخر (شريط تبويبات علوي AIDA/PAS/BAB ومقارنات - 6871)",
        "design_family": "baghdadi_luxury_plum",
        "has_grid": False,
        "has_floating_diamonds": False,
        "has_giant_bg_numbers": False,
        "header_style": "segmented_3tabs",
        "headline_style": "dual_tone_glow",
        "acts": {
            "hook_problem": {
                "top_bg": (18, 16, 35),
                "bottom_bg": (34, 24, 58),
                "glow": (139, 92, 246),
                "primary": (139, 92, 246),
                "secondary": (216, 180, 254),
                "accent": (244, 63, 94),
                "card_bg": (28, 22, 50),
                "is_light_bg": False,
                "sticker_bg": (124, 58, 237),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (20, 18, 39),
                "bottom_bg": (41, 28, 69),
                "glow": (124, 58, 237),
                "primary": (139, 92, 246),
                "secondary": (196, 181, 253),
                "accent": (16, 185, 129),
                "card_bg": (32, 25, 56),
                "is_light_bg": False,
                "sticker_bg": (139, 92, 246),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (16, 14, 32),
                "bottom_bg": (48, 32, 80),
                "glow": (167, 139, 250),
                "primary": (139, 92, 246),
                "secondary": (250, 204, 21),
                "accent": (139, 92, 246),
                "card_bg": (28, 22, 50),
                "is_light_bg": False,
                "sticker_bg": (139, 92, 246),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            }
        }
    },
    "emerald_fintech_mint": {
        "style_id": "emerald_fintech_mint",
        "label_ar": "🌿 ستايل الفينتك الزمردي والأبيض النعناعي (بطاقات تقارير ذكية وتدرج زمردي احترافي)",
        "design_family": "byw_cyan_agency",
        "has_grid": True,
        "has_floating_diamonds": True,
        "has_giant_bg_numbers": True,
        "header_style": "step_dots_pill",
        "headline_style": "sticker_highlight",
        "acts": {
            "hook_problem": {
                "top_bg": (9, 26, 22),
                "bottom_bg": (14, 42, 35),
                "glow": (16, 185, 129),
                "primary": (16, 185, 129),
                "secondary": (255, 255, 255),
                "accent": (245, 158, 11),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (16, 185, 129),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (16, 165, 122),
                "bottom_bg": (6, 108, 78),
                "glow": (255, 255, 255),
                "primary": (9, 26, 22),
                "secondary": (16, 185, 129),
                "accent": (250, 204, 21),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (255, 255, 255),
                "sticker_txt": (9, 26, 22),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (242, 253, 249),
                "bottom_bg": (218, 246, 236),
                "glow": (16, 185, 129),
                "primary": (16, 185, 129),
                "secondary": (9, 26, 22),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (16, 185, 129),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (9, 26, 22)
            }
        }
    },
    "royal_cobalt_gold": {
        "style_id": "royal_cobalt_gold",
        "label_ar": "👑 ستايل الكوبالت الملكي والذهبي (تبويبات احترافية وبطاقات زجاجية عالية التباين)",
        "design_family": "baghdadi_luxury_plum",
        "has_grid": True,
        "has_floating_diamonds": True,
        "has_giant_bg_numbers": True,
        "header_style": "segmented_3tabs",
        "headline_style": "sticker_highlight",
        "acts": {
            "hook_problem": {
                "top_bg": (10, 18, 38),
                "bottom_bg": (18, 34, 68),
                "glow": (59, 130, 246),
                "primary": (59, 130, 246),
                "secondary": (250, 204, 21),
                "accent": (244, 63, 94),
                "card_bg": (20, 34, 66),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (10, 18, 38),
                "headline_txt": (255, 255, 255)
            },
            "body_steps": {
                "top_bg": (29, 78, 216),
                "bottom_bg": (17, 46, 138),
                "glow": (250, 204, 21),
                "primary": (250, 204, 21),
                "secondary": (255, 255, 255),
                "accent": (56, 189, 248),
                "card_bg": (255, 255, 255),
                "is_light_bg": False,
                "sticker_bg": (250, 204, 21),
                "sticker_txt": (10, 18, 38),
                "headline_txt": (255, 255, 255)
            },
            "outro_finale": {
                "top_bg": (244, 248, 255),
                "bottom_bg": (224, 236, 254),
                "glow": (37, 99, 235),
                "primary": (37, 99, 235),
                "secondary": (15, 23, 42),
                "accent": (250, 204, 21),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (37, 99, 235),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            }
        }
    },
    "sunset_coral_editorial": {
        "style_id": "sunset_coral_editorial",
        "label_ar": "🔥 ستايل الإديتوريال المرجاني والخطوات التفاعلية (بطاقات مرقمة 1-4 وتصميم مشرق)",
        "design_family": "mazen_blueprint_collage",
        "has_grid": True,
        "has_floating_diamonds": True,
        "has_giant_bg_numbers": True,
        "header_style": "corner_punctuation_watermark",
        "headline_style": "selection_box_handle",
        "acts": {
            "hook_problem": {
                "top_bg": (26, 14, 22),
                "bottom_bg": (48, 20, 36),
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
                "top_bg": (254, 242, 242),
                "bottom_bg": (254, 215, 215),
                "glow": (225, 29, 72),
                "primary": (225, 29, 72),
                "secondary": (15, 23, 42),
                "accent": (249, 115, 22),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (225, 29, 72),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            },
            "outro_finale": {
                "top_bg": (255, 251, 235),
                "bottom_bg": (254, 243, 199),
                "glow": (234, 88, 12),
                "primary": (225, 29, 72),
                "secondary": (15, 23, 42),
                "accent": (16, 185, 129),
                "card_bg": (255, 255, 255),
                "is_light_bg": True,
                "sticker_bg": (225, 29, 72),
                "sticker_txt": (255, 255, 255),
                "headline_txt": (15, 23, 42)
            }
        }
    }
}


# ==============================================================================
# 1. إدارة ذاكرة التطور المستديمة على القرص (outputs/evolution_memory.json)
# ==============================================================================
def _default_evolution_memory() -> Dict[str, Any]:
    return {
        "version": "4.0",
        "total_evaluations": 0,
        "total_evolutions_triggered": 0,
        "average_quality_score": 0.94,
        "style_rotation_counter": 0,
        "active_studio_style_mode": "auto_vary_pro",  # auto_vary_pro | clone_reference | byw_cyan_agency | mazen_blueprint_collage | baghdadi_luxury_plum | ...
        "active_reference_dna": None,
        "active_brand_theme": None,
        "cloned_reference_styles": {},
        "scene_type_best_params": {
            "default": {
                "font_scale": 1.0,
                "card_padding": 18,
                "bg_blur_strength": 16,
                "accent_glow": 0.28,
                "spring_stiffness": 195.0,
                "spring_damping": 14.0,
                "contrast_boost": 1.0,
                "best_score": 0.94,
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
    - `auto_vary_pro`: يولّد في كل مرة ستايل احترافي جديد وينوّع الستايلات داخل مشاهد الفيديو نفسه.
    - `clone_reference`: يطبق تصميم الفيديو المرجعي المستنسخ بالضبط.
    - أو اسم ستايل محدد من `PRO_STUDIO_STYLE_FAMILIES` (`byw_cyan_agency`, `mazen_blueprint_collage`, `baghdadi_luxury_plum`...).
    """
    mem = load_evolution_memory()
    mem["active_studio_style_mode"] = str(style_mode or "auto_vary_pro")
    save_evolution_memory(mem)
    return mem


def get_active_studio_style_mode() -> str:
    mem = load_evolution_memory()
    return str(mem.get("active_studio_style_mode") or "auto_vary_pro")


def build_dynamic_scene_style_assignment(
    num_scenes: int,
    force_style_mode: Optional[str] = None,
    advance_rotation_counter: bool = True
) -> List[Dict[str, Any]]:
    """
    يولّد خطة التصميم البصري لكل مشهد في الفيديو (`Scene-by-Scene Visual Style Plan`):
    1. إذا كان الوضع `clone_reference` وهناك فيديو مرجعي مستنسخ (`active_reference_dna`):
       يطبق التصميم المرجعي المستنسخ بمراحله اللونية الدقيقة (Hook -> Body Steps -> Finale) ونفس عائلة البطاقات.
    2. إذا كان الوضع عائلة محددة (مثل `byw_cyan_agency` أو `mazen_blueprint_collage` أو `baghdadi_luxury_plum`):
       يطبق تلك العائلة مع التدرج المرحلي الطبيعي داخل الفيديو (مقدمة -> خطوات مرقمة 01..04 -> خاتمة).
    3. إذا كان الوضع `auto_vary_pro` ("تغيير الستايلات تلقائياً في كل مرة وداخل الفيديو"):
       يرفع عداد التدوير (`style_rotation_counter`) ليضمن أن كل فيديو جديد يخرج بستايل مختلف تماماً عن الفيديو السابق،
       كما ينوّع الستايلات والخلفيات وأشكال البطاقات عبر فصول الفيديو نفسه بأسلوب احترافي متناغم!
    """
    mem = load_evolution_memory()
    mode = str(force_style_mode or mem.get("active_studio_style_mode") or "auto_vary_pro")
    rot_idx = int(mem.get("style_rotation_counter", 0))

    if advance_rotation_counter and mode == "auto_vary_pro":
        rot_idx += 1
        mem["style_rotation_counter"] = rot_idx
        save_evolution_memory(mem)

    family_keys = list(PRO_STUDIO_STYLE_FAMILIES.keys())
    active_ref = mem.get("active_reference_dna")

    # 1. وضع استنساخ الفيديو المرجعي بالضبط ("سوي لي نفس التصميم بالضبط")
    if mode == "clone_reference" and isinstance(active_ref, dict) and active_ref.get("enabled", True):
        detected_fam_key = str(active_ref.get("detected_design_family") or "byw_cyan_agency")
        base_fam = json.loads(json.dumps(PRO_STUDIO_STYLE_FAMILIES.get(detected_fam_key, PRO_STUDIO_STYLE_FAMILIES["byw_cyan_agency"])))
        if "multi_act_palettes" in active_ref and isinstance(active_ref["multi_act_palettes"], dict):
            for act_k, act_pal in active_ref["multi_act_palettes"].items():
                if act_k in base_fam["acts"] and isinstance(act_pal, dict):
                    base_fam["acts"][act_k].update(act_pal)
        plan: List[Dict[str, Any]] = []
        for idx in range(max(1, num_scenes)):
            if idx == 0 or (num_scenes >= 5 and idx == 1):
                act_name = "hook_problem"
            elif idx == num_scenes - 1 and num_scenes >= 2:
                act_name = "outro_finale"
            else:
                act_name = "body_steps"
            act_cfg = dict(base_fam["acts"][act_name])
            plan.append({
                "style_family_id": base_fam["style_id"],
                "design_family": base_fam["design_family"],
                "act_name": act_name,
                "step_number": max(1, idx),
                "has_grid": bool(active_ref.get("has_grid", base_fam["has_grid"])),
                "has_floating_diamonds": bool(base_fam["has_floating_diamonds"]),
                "has_giant_bg_numbers": bool(base_fam["has_giant_bg_numbers"]),
                "header_style": base_fam["header_style"],
                "headline_style": base_fam["headline_style"],
                "palette": act_cfg,
                "spring_stiffness": float(active_ref.get("spring_stiffness", 200.0)),
                "spring_damping": float(active_ref.get("spring_damping", 14.0)),
                "card_variant_index": (idx + rot_idx) % 5
            })
        return plan

    # 2. وضع عائلة محددة اختارها المستخدم
    if mode in PRO_STUDIO_STYLE_FAMILIES:
        fam = PRO_STUDIO_STYLE_FAMILIES[mode]
        plan = []
        for idx in range(max(1, num_scenes)):
            if idx == 0 or (num_scenes >= 6 and idx == 1):
                act_name = "hook_problem"
            elif idx == num_scenes - 1 and num_scenes >= 2:
                act_name = "outro_finale"
            else:
                act_name = "body_steps"
            plan.append({
                "style_family_id": fam["style_id"],
                "design_family": fam["design_family"],
                "act_name": act_name,
                "step_number": max(1, idx),
                "has_grid": fam["has_grid"],
                "has_floating_diamonds": fam["has_floating_diamonds"],
                "has_giant_bg_numbers": fam["has_giant_bg_numbers"],
                "header_style": fam["header_style"],
                "headline_style": fam["headline_style"],
                "palette": dict(fam["acts"][act_name]),
                "spring_stiffness": 205.0,
                "spring_damping": 14.0,
                "card_variant_index": (idx + rot_idx) % 5
            })
        return plan

    # 3. وضع التنويع الاحترافي المتجدد تلقائياً (`auto_vary_pro`)
    # يختار عائلة رئيسية مختلفة في كل تشغيلة فيديو، ويطعّم فصول الفيديو بعائلات متكاملة بحيث يتغير الستايل داخل الفيديو نفسه باحترافية!
    primary_fam_key = family_keys[rot_idx % len(family_keys)]
    secondary_fam_key = family_keys[(rot_idx + 1) % len(family_keys)]
    tertiary_fam_key = family_keys[(rot_idx + 2) % len(family_keys)]

    plan = []
    for idx in range(max(1, num_scenes)):
        if idx == 0:
            chosen_fam = PRO_STUDIO_STYLE_FAMILIES[primary_fam_key]
            act_name = "hook_problem"
        elif idx == num_scenes - 1 and num_scenes >= 2:
            chosen_fam = PRO_STUDIO_STYLE_FAMILIES[primary_fam_key]
            act_name = "outro_finale"
        elif idx % 3 == 1:
            chosen_fam = PRO_STUDIO_STYLE_FAMILIES[primary_fam_key]
            act_name = "body_steps"
        elif idx % 3 == 2:
            chosen_fam = PRO_STUDIO_STYLE_FAMILIES[secondary_fam_key]
            act_name = "body_steps"
        else:
            chosen_fam = PRO_STUDIO_STYLE_FAMILIES[tertiary_fam_key]
            act_name = "body_steps"

        plan.append({
            "style_family_id": chosen_fam["style_id"],
            "design_family": chosen_fam["design_family"],
            "act_name": act_name,
            "step_number": max(1, idx),
            "has_grid": chosen_fam["has_grid"],
            "has_floating_diamonds": chosen_fam["has_floating_diamonds"],
            "has_giant_bg_numbers": chosen_fam["has_giant_bg_numbers"],
            "header_style": chosen_fam["header_style"],
            "headline_style": chosen_fam["headline_style"],
            "palette": dict(chosen_fam["acts"][act_name]),
            "spring_stiffness": 205.0,
            "spring_damping": 14.0,
            "card_variant_index": (idx + rot_idx) % 5
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
    scores = [float(v.get("best_score", 0.94)) for v in best_map.values() if isinstance(v, dict)]
    avg_score = round(sum(scores) / max(1, len(scores)), 3) if scores else float(mem.get("average_quality_score", 0.94))
    return {
        "learned_scene_types_count": max(len(learned_types), len(best_map)) + len(PRO_STUDIO_STYLE_FAMILIES),
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
    """
    استخراج ألوان الهوية البصرية (Primary, Secondary, Accent, Background) تلقائياً من صورة لوقو
    أو صورة باليت ألوان (`PNG, JPG, WEBP`) مع تجاهل الخلفية الشفافة أو البيضاء المحيطة باللوقو.
    """
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
# 3. محلل ومستنسخ الفيديو المرجعي متعدد المراحل (Multi-Act Reference Video DNA Cloner)
# ==============================================================================
def _build_act_palette_from_pixels(px_chunk: np.ndarray, fallback_family: Dict[str, Any], act_key: str) -> Dict[str, Any]:
    base_act = dict(fallback_family["acts"][act_key])
    if px_chunk is None or px_chunk.shape[0] < 20:
        return base_act

    pal = _fast_numpy_kmeans_palette(px_chunk.astype(np.float32), k=5)
    colors = [tuple(int(x) for x in c) for c in pal]
    mean_luma = float(np.mean(px_chunk)) / 255.0
    is_light = (mean_luma >= 0.60)

    by_luma = sorted(colors, key=lambda c: _saturation_and_luma(c)[1])
    by_sat = sorted(colors, key=lambda c: (_saturation_and_luma(c)[0] * 0.75 + 0.25 * (1.0 - abs(_saturation_and_luma(c)[1] - 0.52))), reverse=True)

    top_bg = colors[0]
    bottom_bg = colors[1] if len(colors) > 1 else colors[0]
    primary_c = by_sat[0]
    secondary_c = by_sat[1] if len(by_sat) > 1 else (255, 255, 255)

    # ضمان تباين واضح بين الخلفية ولون الستيكر والعنوان
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
        "card_bg": (255, 255, 255) if (is_light or _saturation_and_luma(top_bg)[0] > 0.30) else (24, 22, 46),
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
    تحليل واستنساخ التصميم الكامل لأي فيديو مرجعي ("سوي لي نفس التصميم بالضبط"):
    1. يستخرج الألوان المتعددة المراحل عبر الزمن (`hook_problem`, `body_steps`, `outro_finale`)
       بحيث إذا كان الفيديو المرجعي يغير خلفيته (مثل `6873.mp4`: كحلي -> سيان -> أبيض)، يستنسخ المحرك المراحل الثلاث!
    2. يصنف العائلة الهندسية الأقرب (`byw_cyan_agency`, `mazen_blueprint_collage`, `baghdadi_luxury_plum`)
       بناءً على البصمة اللونية وتوزيع الحواف والتباين.
    3. يضبط سرعة النوابض (`spring_stiffness`, `spring_damping`) وإيقاع المشاهد، ويفعّل وضع `clone_reference` فوراً.
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
            frm = np.frombuffer(raw, dtype=np.uint8).reshape((sh, sw, 3))
            gray = (0.299 * frm[:, :, 0] + 0.587 * frm[:, :, 1] + 0.114 * frm[:, :, 2]).astype(np.float32)

            if prev_gray is not None:
                diff = float(np.mean(np.abs(gray - prev_gray)))
                frame_diffs.append(diff)
                if diff > 24.0 and (n_frames / float(sample_fps) - cut_timestamps[-1]) >= 0.65:
                    cut_timestamps.append(round(n_frames / float(sample_fps), 2))

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
    mean_velocity = float(np.mean(frame_diffs)) if frame_diffs else 8.5
    p90_velocity = float(np.percentile(frame_diffs, 90)) if frame_diffs else 16.0
    num_cuts = max(1, len(cut_timestamps))
    avg_shot_dur = round(total_sampled_sec / float(num_cuts), 2)

    energy_norm = max(0.0, min(1.0, (mean_velocity - 3.0) / 18.0))
    recommended_stiffness = round(175.0 + 115.0 * energy_norm, 1)
    recommended_damping = round(15.5 - 4.5 * energy_norm, 1)
    recommended_handoff_sec = round(max(0.28, min(0.48, 0.44 - 0.12 * energy_norm)), 2)

    if per_frame_bg_pixels:
        all_px = np.vstack(per_frame_bg_pixels).astype(np.float32)
        n_chunks = len(per_frame_bg_pixels)
        c1 = max(1, n_chunks // 4)
        c2 = max(c1 + 1, (n_chunks * 3) // 4)
        hook_px = np.vstack(per_frame_bg_pixels[:c1])
        body_px = np.vstack(per_frame_bg_pixels[c1:c2]) if c2 > c1 else all_px
        outro_px = np.vstack(per_frame_bg_pixels[c2:]) if c2 < n_chunks else all_px
        palette = _fast_numpy_kmeans_palette(all_px, k=5)
        mean_luma = float(np.mean(all_px)) / 255.0
        contrast_std = float(np.std(all_px)) / 255.0
    else:
        palette = np.array([[11, 24, 31], [27, 174, 202], [255, 255, 255], [8, 109, 133], [250, 204, 21]], dtype=np.uint8)
        hook_px = body_px = outro_px = palette.astype(np.float32)
        mean_luma = 0.35
        contrast_std = 0.28

    colors_list = [tuple(int(x) for x in c) for c in palette]
    by_sat = sorted(colors_list, key=lambda c: (_saturation_and_luma(c)[0] * (0.4 + _saturation_and_luma(c)[1])), reverse=True)
    primary_c = by_sat[0]
    secondary_c = by_sat[min(1, len(by_sat) - 1)]
    accent_c = by_sat[min(2, len(by_sat) - 1)]

    # تحديد العائلة البصرية الأقرب للفيديو المرجعي المرفوع
    r_m, g_m, b_m = float(np.mean(body_px[:, 0])), float(np.mean(body_px[:, 1])), float(np.mean(body_px[:, 2]))
    if g_m > r_m + 22 and b_m > r_m + 22:
        detected_family = "byw_cyan_agency"
    elif r_m < 65 and b_m > g_m + 10 and mean_luma < 0.28:
        detected_family = "baghdadi_luxury_plum"
    elif b_m > r_m + 15 and mean_luma >= 0.42:
        detected_family = "mazen_blueprint_collage"
    else:
        detected_family = "byw_cyan_agency"

    base_fam_spec = PRO_STUDIO_STYLE_FAMILIES[detected_family]
    multi_act_palettes = {
        "hook_problem": _build_act_palette_from_pixels(hook_px, base_fam_spec, "hook_problem"),
        "body_steps": _build_act_palette_from_pixels(body_px, base_fam_spec, "body_steps"),
        "outro_finale": _build_act_palette_from_pixels(outro_px, base_fam_spec, "outro_finale")
    }

    is_light_ref = (mean_luma >= 0.55)
    top_bg = multi_act_palettes["body_steps"]["top_bg"]
    bottom_bg = multi_act_palettes["body_steps"]["bottom_bg"]

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
        "card_bg": (255, 255, 255) if is_light_ref or detected_family in ("byw_cyan_agency", "mazen_blueprint_collage") else (28, 22, 50)
    }

    dna_profile = {
        "style_id": theme_key,
        "source_video": os.path.basename(reference_video_path),
        "extracted_at": int(time.time()),
        "enabled": True,
        "detected_design_family": detected_family,
        "detected_family_label_ar": base_fam_spec["label_ar"],
        "has_grid": base_fam_spec["has_grid"],
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
        "stagger_delay_sec": round(max(0.025, min(0.065, 0.055 - 0.025 * energy_norm)), 3),
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
    """تفعيل أو إلغاء تفعيل ستايل مرجعي مستنسخ محفوظ في الذاكرة."""
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
                    "spring_stiffness": float(curr_meta.get("spring_stiffness", 195.0)),
                    "spring_damping": float(curr_meta.get("spring_damping", 14.0)),
                    "contrast_boost": float(curr_meta.get("contrast_boost", 1.0)),
                    "best_score": round(max(prev_best, overall_score), 4),
                    "samples": int(prev_entry.get("samples", 0)) + 1
                }

            all_scores = [float(v.get("best_score", 0.94)) for v in best_map.values() if isinstance(v, dict)]
            if all_scores:
                mem["average_quality_score"] = round(sum(all_scores) / len(all_scores), 4)
            save_evolution_memory(mem)
        except Exception as e:
            logger.debug(f"Evolution memory persistence notice: {e}")

    return curr_frame, report