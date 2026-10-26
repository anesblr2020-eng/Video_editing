# -*- coding: utf-8 -*-
"""Optional per-scene image generation via Gemini image-capable generateContent API.
Images are cached per prompt hash. Missing keys/network/provider errors fail soft and leave the
existing renderer usable; prompts are never marked as generated unless a valid image is saved.
"""
import os, json, base64, hashlib, time
from typing import Dict, Any, List
import requests
from PIL import Image
from io import BytesIO

MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')
API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'

def _safe_image(data: bytes, path: str) -> bool:
    try:
        im = Image.open(BytesIO(data)).convert('RGB')
        if im.width < 256 or im.height < 256: return False
        # Normalize to portrait 9:16; center crop to preserve predictable motion-safe framing.
        target = 9 / 16
        w, h = im.size
        if w / h > target:
            nw = int(h * target); left = (w - nw) // 2; im = im.crop((left, 0, left + nw, h))
        else:
            nh = int(w / target); top = (h - nh) // 2; im = im.crop((0, top, w, top + nh))
        im = im.resize((768, 1365), Image.Resampling.LANCZOS)
        im.save(path, 'JPEG', quality=90, optimize=True)
        return True
    except Exception:
        return False

def generate_scene_images(out_dir: str, prompts_path: str, api_key: str = '', progress=None) -> Dict[str, Any]:
    api_key = (api_key or os.environ.get('GEMINI_API_KEY', '')).strip()
    report = {'enabled': bool(api_key), 'model': MODEL, 'generated': 0, 'cached': 0, 'failed': 0, 'reason': None}
    if not os.path.exists(prompts_path):
        report['reason'] = 'scene prompts file not found'; return report
    with open(prompts_path, encoding='utf-8') as f: payload = json.load(f)
    scenes = payload.get('scenes', [])
    image_dir = os.path.join(out_dir, 'scene_images'); os.makedirs(image_dir, exist_ok=True)
    if not api_key:
        report['reason'] = 'GEMINI_API_KEY not configured'; return report
    session = requests.Session()
    for i, scene in enumerate(scenes):
        prompt = str(scene.get('image_prompt') or '').strip()
        if not prompt: report['failed'] += 1; continue
        digest = hashlib.sha256((MODEL + prompt).encode('utf-8')).hexdigest()[:20]
        path = os.path.join(image_dir, f'scene_{int(scene.get("scene_index", i+1)):03d}_{digest}.jpg')
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            scene['image_path'] = path; scene['generation_status'] = 'cached'; report['cached'] += 1; continue
        url = API_BASE.format(model=MODEL) + '?key=' + api_key
        body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}}
        try:
            r = session.post(url, json=body, timeout=(20, 180))
            if r.status_code >= 400: raise RuntimeError(f'HTTP {r.status_code}: {r.text[:300]}')
            result = r.json(); image_bytes = None
            for cand in result.get('candidates', []):
                for part in cand.get('content', {}).get('parts', []):
                    inline = part.get('inlineData') or part.get('inline_data')
                    if inline and inline.get('data'):
                        image_bytes = base64.b64decode(inline['data']); break
                if image_bytes: break
            if not image_bytes or not _safe_image(image_bytes, path): raise RuntimeError('provider returned no valid image data')
            scene['image_path'] = path; scene['generation_status'] = 'generated'; report['generated'] += 1
        except Exception as e:
            scene['image_path'] = None; scene['generation_status'] = 'failed'; scene['error'] = str(e)[:350]; report['failed'] += 1
        if callable(progress):
            try: progress((i+1)/max(1,len(scenes)), f'إنشاء صور المشاهد: {i+1}/{len(scenes)}')
            except Exception: pass
        # Persist incremental state so interruption does not lose completed images.
        with open(prompts_path, 'w', encoding='utf-8') as f: json.dump(payload, f, ensure_ascii=False, indent=2)
    report['image_dir'] = image_dir
    report['reason'] = None if report['generated'] or report['cached'] else 'no images generated; inspect per-scene errors in scene_image_prompts.json'
    with open(os.path.join(out_dir, 'image_generation_report.json'), 'w', encoding='utf-8') as f: json.dump(report, f, ensure_ascii=False, indent=2)
    return report
