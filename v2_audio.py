"""
v2/audio.py — هندسة الصوت المرتبطة بأحداث الحركة (Event-Driven Sound Design) + ضبط الجهارة القياسية (-14 LUFS).
القواعد الصارمة (القسم 5):
- صوت المتحدث يُضبط عند -14 LUFS.
- المؤثرات الصوتية أخفض من المتحدث بـ 12–18 dB (نضبطها عند -15.5 dB تحت المتحدث).
- لا مؤثر عند كل حركة، بل فقط عند الأحداث المهمة:
  1. الانتقال بين المشاهد (Transition Whoosh).
  2. لحظة التحول الدلالي داخل المشهد (Intra-scene State B Pivot Pop عند pivot_time).
  3. التمهيد قبل مشهد الخاتمة (CTA Riser).
- يدعم التوليد الفيزيائي الدافئ (Synthesized Studio Organic SFX) تلقائياً عند عدم توفر حزمة WAV خارجية.
"""
import os
import wave
import math
import subprocess
import numpy as np
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SFX_CANDIDATE_ROOTS = [
    os.path.join(BASE_DIR, "assets", "sfx_pack"),
    "/working_dir/c_cda938a3b05fdfd4/artifacts/file_generation/ttl=63d/output/assets/sfx_pack",
]


def _synth_warm_whoosh(sr: int = 44100, dur: float = 0.22) -> np.ndarray:
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    env = np.sin(np.pi * (t / dur)) ** 1.8
    freq = np.linspace(190.0, 95.0, n, dtype=np.float32)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    tone = 0.65 * np.sin(phase) + 0.35 * np.sin(phase * 1.5)
    return (tone * env * 0.35).astype(np.float32)


def _synth_warm_pop(sr: int = 44100, dur: float = 0.09) -> np.ndarray:
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    env = np.exp(-t * 38.0) * np.sin(np.pi * np.minimum(1.0, t / 0.015))
    freq = np.linspace(185.0, 365.0, n, dtype=np.float32)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    return (np.sin(phase) * env * 0.40).astype(np.float32)


def _synth_warm_riser(sr: int = 44100, dur: float = 0.34) -> np.ndarray:
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    env = (t / dur) ** 2.0 * np.sin(np.pi * (t / dur))
    freq = np.linspace(120.0, 310.0, n, dtype=np.float32)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    return (np.sin(phase) * env * 0.32).astype(np.float32)


def load_wav_mono_44k(path: str) -> np.ndarray:
    if not path or not os.path.exists(path):
        return np.zeros(0, dtype=np.float32)
    tmp_wav = "/tmp/_v2_sfx_tmp.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", "44100", "-f", "wav", tmp_wav],
        check=False,
    )
    if not os.path.exists(tmp_wav):
        return np.zeros(0, dtype=np.float32)
    with wave.open(tmp_wav, "rb") as wf:
        n = wf.getnframes()
        raw = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    return raw


def _resolve_or_synth_sfx(rel_subpath: str, kind: str, sr: int = 44100) -> np.ndarray:
    for root in SFX_CANDIDATE_ROOTS:
        cand = os.path.join(root, rel_subpath)
        if os.path.exists(cand):
            arr = load_wav_mono_44k(cand)
            if len(arr) > 0:
                return arr
    if kind == "whoosh":
        return _synth_warm_whoosh(sr=sr)
    if kind == "pop":
        return _synth_warm_pop(sr=sr)
    return _synth_warm_riser(sr=sr)


def build_master_audio(
    voice_wav_path: str,
    scenes: List[Dict[str, Any]],
    output_aac_or_wav_path: str,
) -> Dict[str, Any]:
    """
    يدمج صوت المتحدث مع مؤثرات صوتية خفيفة ومرتبطة بالأحداث المهمة فقط (-15.5 dB تحت المتحدث)،
    ثم يطبق فلتر EBU R128 loudnorm لضبط الجهارة النهائية عند -14.0 LUFS.
    """
    voice = load_wav_mono_44k(voice_wav_path)
    sr = 44100
    if len(voice) == 0:
        # إذا لم يتوفر ملف صوت خام، نولد تردداً صوتياً دافئاً يحاكي الكلام للاختبار التقني
        dur_est = max(5.0, float(scenes[-1].get("end", 15.0)) if scenes else 15.0)
        t_arr = np.linspace(0.0, dur_est, int(dur_est * sr), dtype=np.float32)
        mod = 0.55 + 0.45 * np.sin(2.0 * np.pi * 3.2 * t_arr)
        voice = (0.14 * mod * (0.65 * np.sin(2.0 * np.pi * 165.0 * t_arr) + 0.35 * np.sin(2.0 * np.pi * 330.0 * t_arr))).astype(np.float32)

    voice_rms = float(np.sqrt(np.mean(voice ** 2))) if len(voice) > 0 else 0.12
    if voice_rms < 0.005:
        voice_rms = 0.10
    # -15.5 dB below voice RMS (10^(-15.5 / 20) ≈ 0.168)
    target_sfx_rms = max(0.008, voice_rms * 0.168)

    whoosh_samples = _resolve_or_synth_sfx(os.path.join("6_whooch", "studio_organic_6_whooch_v1.wav"), "whoosh", sr=sr)
    pop_samples = _resolve_or_synth_sfx(os.path.join("1_click", "studio_organic_1_click_v1.wav"), "pop", sr=sr)
    riser_samples = _resolve_or_synth_sfx(os.path.join("5_riser", "studio_organic_5_riser_v1.wav"), "riser", sr=sr)

    def scale_sfx(arr: np.ndarray, db_offset: float = 0.0) -> np.ndarray:
        if len(arr) == 0:
            return arr
        cur_rms = float(np.sqrt(np.mean(arr ** 2))) + 1e-7
        factor = (target_sfx_rms / cur_rms) * (10.0 ** (db_offset / 20.0))
        return np.clip(arr * factor, -0.45, 0.45)

    whoosh_scaled = scale_sfx(whoosh_samples, 0.0)
    pop_scaled = scale_sfx(pop_samples, -1.5)
    riser_scaled = scale_sfx(riser_samples, -2.0)

    mix = voice.copy()
    sfx_events = []

    for idx, sc in enumerate(scenes):
        start_t = float(sc.get("start", 0.0))
        end_t = float(sc.get("end", start_t + 2.0))
        pivot_t = float(sc.get("pivot_time", (start_t + end_t) * 0.5))
        tpl = sc.get("template", "kinetic_hook")
        pos = int(start_t * sr)

        # 1. عند الانتقال بين المشاهد (ليس في الثانية 0): إضافة Whoosh ناعم مع تبكير بصري (-0.08s)
        if idx > 0 and len(whoosh_scaled) > 0 and pos < len(mix):
            w_pos = max(0, int((start_t - 0.06) * sr))
            end_pos = min(len(mix), w_pos + len(whoosh_scaled))
            mix[w_pos:end_pos] += whoosh_scaled[: end_pos - w_pos]
            sfx_events.append({"time": round(start_t, 2), "type": "transition_whoosh", "rel_db": -15.5})

        # 2. عند نقطة التحول الدلالي داخل المشهد (pivot_time: State A -> State B) أو ظهور رقم/نتيجة
        if tpl in {"process_simulation", "anchor_expand", "dual_layer_proof", "editorial_proof_card", "big_number", "before_after", "cta_end"} and len(pop_scaled) > 0:
            pop_time = pivot_t if tpl in {"process_simulation", "anchor_expand", "dual_layer_proof", "editorial_proof_card", "before_after"} else (start_t + 0.18)
            pop_pos = int(pop_time * sr)
            if 0 <= pop_pos < len(mix):
                end_pos = min(len(mix), pop_pos + len(pop_scaled))
                mix[pop_pos:end_pos] += pop_scaled[: end_pos - pop_pos]
                sfx_events.append({"time": round(pop_time, 2), "type": f"pivot_accent_pop_{tpl}", "rel_db": -17.0})

        # 3. تمهيد خفيف (Riser) قبل مشهد الختام CTA
        if tpl == "cta_end" and len(riser_scaled) > 0:
            r_pos = max(0, int((start_t - 0.35) * sr))
            if r_pos < len(mix):
                end_pos = min(len(mix), r_pos + len(riser_scaled))
                mix[r_pos:end_pos] += riser_scaled[: end_pos - r_pos]
                sfx_events.append({"time": round(start_t - 0.35, 2), "type": "cta_riser", "rel_db": -17.5})

    mix = np.clip(mix, -0.98, 0.98)
    raw_mix_wav = "/tmp/_v2_raw_mix.wav"
    with wave.open(raw_mix_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((mix * 32767.0).astype(np.int16).tobytes())

    # تطبيق تطبيع الجهارة القياسي -14 LUFS عبر FFmpeg loudnorm
    os.makedirs(os.path.dirname(os.path.abspath(output_aac_or_wav_path)), exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", raw_mix_wav,
            "-af", "loudnorm=I=-14.0:TP=-1.5:LRA=11.0",
            "-ar", "44100", "-ac", "2",
            output_aac_or_wav_path,
        ],
        check=True,
    )

    return {
        "target_lufs": -14.0,
        "sfx_relative_db": -15.5,
        "sfx_events_count": len(sfx_events),
        "sfx_events": sfx_events,
        "output_audio_path": output_aac_or_wav_path,
    }
