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

# Configure the ordered model cascade in Streamlit Secrets with GEMINI_IMAGE_MODELS.
# The first usable model is preferred; quota/rate-limit/provider failures trigger fallback.
# Unknown/unavailable model IDs are skipped automatically and recorded in the report.
DEFAULT_MODELS = [
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
]

def _configured_models():
    raw = os.environ.get("GEMINI_IMAGE_MODELS", "").strip()
    if not raw:
        # Backward compatibility with the prior single-model setting.
        raw = os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
    models = [x.strip() for x in raw.split(",") if x.strip()] if raw else DEFAULT_MODELS[:]
    # De-duplicate while preserving preference order.
    return list(dict.fromkeys(models)) or DEFAULT_MODELS[:]

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
    models = _configured_models()
    report = {
        'enabled': bool(api_key), 'model': models[0], 'models_tried': models,
        'generated': 0, 'cached': 0, 'failed': 0, 'fallback_count': 0,
        'model_usage': {}, 'model_errors': [], 'reason': None,
    }
    if not os.path.exists(prompts_path):
        report['reason'] = 'scene prompts file not found'; return report
    with open(prompts_path, encoding='utf-8') as f: payload = json.load(f)
    scenes = payload.get('scenes', [])
    image_dir = os.path.join(out_dir, 'scene_images'); os.makedirs(image_dir, exist_ok=True)
    if not api_key:
        report['reason'] = 'GEMINI_API_KEY not configured'; return report
    session = requests.Session()
    stop_all_models = False
    for i, scene in enumerate(scenes):
        prompt = str(scene.get('image_prompt') or '').strip()
        if not prompt:
            report['failed'] += 1; scene['generation_status'] = 'failed'
            scene['error'] = 'empty image prompt'; continue
        image_bytes = None
        final_error = None
        selected_model = None
        # Reuse any existing valid scene image cache, regardless of which model made it.
        existing = scene.get('image_path')
        if existing and os.path.exists(existing) and os.path.getsize(existing) > 10000:
            try:
                with Image.open(existing) as im:
                    if im.width >= 256 and im.height >= 256:
                        scene['generation_status'] = 'cached'; report['cached'] += 1
                        report['model_usage']['cached_existing'] = report['model_usage'].get('cached_existing', 0) + 1
                        continue
            except Exception:
                pass
        # Search per-model cache before spending another API call.
        for model in models:
            digest = hashlib.sha256((model + prompt).encode('utf-8')).hexdigest()[:20]
            path = os.path.join(image_dir, f'scene_{int(scene.get("scene_index", i+1)):03d}_{digest}.jpg')
            if os.path.exists(path) and os.path.getsize(path) > 10000:
                scene['image_path'] = path; scene['generation_status'] = 'cached'
                scene['model_used'] = model; report['cached'] += 1
                report['model_usage'][model] = report['model_usage'].get(model, 0) + 1
                selected_model = model
                break
            url = API_BASE.format(model=model)
            body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}}
            try:
                r = session.post(url, headers={'x-goog-api-key': api_key}, json=body, timeout=(20, 180))
                if r.status_code >= 400:
                    err = f'HTTP {r.status_code}: {r.text[:500]}'
                    report['model_errors'].append({'scene': int(scene.get('scene_index', i+1)), 'model': model, 'error': err[:550]})
                    final_error = err
                    # Quota, rate limits, unsupported models and transient server errors can try a fallback.
                    if r.status_code in (400, 401, 403, 404, 429, 500, 502, 503, 504):
                        continue
                    stop_all_models = True
                    break
                result = r.json(); candidate_bytes = None
                for cand in result.get('candidates', []):
                    for part in cand.get('content', {}).get('parts', []):
                        inline = part.get('inlineData') or part.get('inline_data')
                        if inline and inline.get('data'):
                            candidate_bytes = base64.b64decode(inline['data']); break
                    if candidate_bytes: break
                if not candidate_bytes:
                    final_error = f'{model}: provider returned no image data'
                    report['model_errors'].append({'scene': int(scene.get('scene_index', i+1)), 'model': model, 'error': final_error})
                    continue
                if not _safe_image(candidate_bytes, path):
                    final_error = f'{model}: provider returned invalid or too-small image data'
                    report['model_errors'].append({'scene': int(scene.get('scene_index', i+1)), 'model': model, 'error': final_error})
                    continue
                image_bytes = candidate_bytes; selected_model = model
                scene['image_path'] = path; scene['generation_status'] = 'generated'; scene['model_used'] = model
                report['generated'] += 1
                report['model_usage'][model] = report['model_usage'].get(model, 0) + 1
                if models.index(model) > 0: report['fallback_count'] += 1
                break
            except requests.RequestException as e:
                final_error = f'{model}: network/request error: {str(e)[:350]}'
                report['model_errors'].append({'scene': int(scene.get('scene_index', i+1)), 'model': model, 'error': final_error})
                continue
            except Exception as e:
                final_error = f'{model}: {str(e)[:350]}'
                report['model_errors'].append({'scene': int(scene.get('scene_index', i+1)), 'model': model, 'error': final_error})
                continue
        if not selected_model:
            scene['image_path'] = None; scene['generation_status'] = 'failed'
            scene['error'] = (final_error or 'all configured image models failed')[:550]
            report['failed'] += 1
        if callable(progress):
            try: progress((i+1)/max(1,len(scenes)), f'إنشاء صور المشاهد: {i+1}/{len(scenes)}')
            except Exception: pass
        # Persist incremental state so interruption does not lose completed images.
        with open(prompts_path, 'w', encoding='utf-8') as f: json.dump(payload, f, ensure_ascii=False, indent=2)
        if stop_all_models:
            # Do not keep sending requests after an unexpected non-recoverable status.
            for pending in scenes[i+1:]:
                pending['image_path'] = None
                pending['generation_status'] = 'failed'
                pending['error'] = 'generation stopped after a non-recoverable provider error'
                report['failed'] += 1
            break
    report['image_dir'] = image_dir
    report['errors'] = [str(x.get('error'))[:550] for x in scenes if x.get('generation_status') == 'failed' and x.get('error')]
    report['reason'] = None if report['generated'] or report['cached'] else 'no images generated; all configured models failed; inspect model_errors in image_generation_report.json'
    with open(os.path.join(out_dir, 'image_generation_report.json'), 'w', encoding='utf-8') as f: json.dump(report, f, ensure_ascii=False, indent=2)
    return report
