# -*- coding: utf-8 -*-
"""Semantic visual planning helpers. Creates a per-video visual bible and per-scene image prompts.
Image generation is deliberately a separate provider step; this module never pretends a prompt is an image.
"""
import json, os, re
from typing import Any, Dict, List


def _clean(text: Any, limit: int = 700) -> str:
    return re.sub(r'\s+', ' ', str(text or '')).strip()[:limit]


def build_visual_bible(theme_name: str, theme: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One consistent art direction for the entire video, while allowing semantic scene variety."""
    palette = theme.get('colors') or theme.get('palette') or {}
    if not isinstance(palette, dict):
        palette = {'theme_description': str(palette)}
    visual_bible = {
        'theme_name': theme_name,
        'format': 'vertical 9:16 social video, cinematic editorial illustration, high visual clarity',
        'palette': palette,
        'style_lock': 'Use one coherent visual language, consistent lighting, material rendering, contrast, grain/sharpness, and camera language across every scene.',
        'continuity_rules': [
            'Keep the same palette and art direction across all scenes; do not randomly switch between 2D, 3D, photography, and collage.',
            'Each scene must depict the actual meaning of its spoken line, not a generic icon or unrelated decorative symbol.',
            'Prefer a complete readable visual situation with foreground, subject, and environment over a lone floating icon.',
            'Vary composition, subject action, camera framing, and environment according to meaning while preserving the style lock.',
            'No embedded text, captions, logos, watermarks, UI labels, or fake lettering in generated art; text is composited separately.',
            'Keep the central subject inside the middle 70 percent of the vertical frame to allow crop and motion.',
        ],
        'scene_count': len(scenes),
    }
    return visual_bible


def build_scene_image_prompts(scenes: List[Dict[str, Any]], bible: Dict[str, Any]) -> List[Dict[str, Any]]:
    prompts = []
    palette_text = json.dumps(bible.get('palette', {}), ensure_ascii=False)
    for i, sc in enumerate(scenes):
        speech = _clean(sc.get('speech') or sc.get('text'))
        keywords = sc.get('keywords') or []
        semantic = _clean('، '.join(map(str, keywords)) if keywords else sc.get('visual_query', ''), 240)
        intent = _clean(sc.get('intent', 'explanation'), 100)
        # Explicitly avoid template-driven repetition: prompt is grounded in the actual sentence.
        prompt = (
            f"Create one original vertical 9:16 editorial illustration for this exact spoken idea: '{speech}'. "
            f"Concrete semantic direction: {semantic}. Narrative intent: {intent}. "
            f"Visual direction: {bible.get('format')}. Palette guidance: {palette_text}. "
            f"Maintain continuity: {bible.get('style_lock')} Depict a specific scene with an intentional environment, "
            "clear subject/action, layered depth, and a composition that communicates the sentence at a glance. "
            "Choose the setting and objects from the sentence meaning, not from a fixed icon library. "
            "No text, letters, numbers, captions, logos, watermarks, or generic waveform/hourglass unless the sentence truly concerns them."
        )
        prompts.append({
            'scene_index': i + 1,
            'start': sc.get('start', 0), 'end': sc.get('end', 0),
            'speech': speech, 'semantic_direction': semantic,
            'image_prompt': prompt,
            'generation_status': 'prompt_ready_not_generated',
            'image_path': None,
        })
    return prompts


def write_visual_plan(out_dir: str, theme_name: str, theme: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    bible = build_visual_bible(theme_name, theme, scenes)
    prompts = build_scene_image_prompts(scenes, bible)
    bible_path = os.path.join(out_dir, 'visual_bible.json')
    prompts_path = os.path.join(out_dir, 'scene_image_prompts.json')
    with open(bible_path, 'w', encoding='utf-8') as f:
        json.dump(bible, f, ensure_ascii=False, indent=2)
    with open(prompts_path, 'w', encoding='utf-8') as f:
        json.dump({'scene_count': len(prompts), 'scenes': prompts}, f, ensure_ascii=False, indent=2)
    return {'visual_bible': bible_path, 'scene_image_prompts': prompts_path}
