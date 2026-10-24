"""
v2/audio.py — هندسة الصوت المرتبطة بأحداث الحركة (Event-Driven Sound Design) + ضبط الجهارة القياسية (-14 LUFS).
القواعد الصارمة (القسم 5):
- صوت المتحدث يُضبط عند -14 LUFS.
- المؤثرات الصوتية أخفض من المتحدث بـ 12–18 dB (نضبطها عند -15.5 dB تحت المتحدث).
- لا مؤثر عند كل حركة، بل فقط عند الأحداث المهمة (بداية مشهد جديد / ظهور رقم أو دعوة لإجراء).
"""
import os
import wave
import subprocess
import numpy as np
from typing import List, Dict, Any

SFX_ROOT = "/working_dir/c_cda938a3b05fdfd4/artifacts/file_generation/ttl=63d/output/assets/sfx_pack"


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
        voice = np.zeros(int(23.6 * sr), dtype=np.float32)

    voice_rms = float(np.sqrt(np.mean(voice ** 2))) if len(voice) > 0 else 0.12
    # -15.5 dB below voice RMS (10^(-15.5 / 20) ≈ 0.168)
    target_sfx_rms = max(0.008, voice_rms * 0.168)

    whoosh_path = os.path.join(SFX_ROOT, "6_whooch", "studio_organic_6_whooch_v1.wav")
    pop_path = os.path.join(SFX_ROOT, "1_click", "studio_organic_1_click_v1.wav")
    riser_path = os.path.join(SFX_ROOT, "5_riser", "studio_organic_5_riser_v1.wav")

    whoosh_samples = load_wav_mono_44k(whoosh_path)
    pop_samples = load_wav_mono_44k(pop_path)
    riser_samples = load_wav_mono_44k(riser_path)

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
        tpl = sc.get("template", "kinetic_hook")
        pos = int(start_t * sr)

        # 1. عند الانتقال بين المشاهد (ليس في الثانية 0): إضافة Whoosh ناعم
        if idx > 0 and len(whoosh_scaled) > 0 and pos < len(mix):
            end_pos = min(len(mix), pos + len(whoosh_scaled))
            mix[pos:end_pos] += whoosh_scaled[: end_pos - pos]
            sfx_events.append({"time": round(start_t, 2), "type": "transition_whoosh", "rel_db": -15.5})

        # 2. فقط عند القوالب ذات الحدث البارز (big_number, before_after, cta_end): إضافة Pop خفيف بعد 0.18s
        if tpl in {"big_number", "before_after", "cta_end"} and len(pop_scaled) > 0:
            pop_pos = int((start_t + 0.18) * sr)
            if pop_pos < len(mix):
                end_pos = min(len(mix), pop_pos + len(pop_scaled))
                mix[pop_pos:end_pos] += pop_scaled[: end_pos - pop_pos]
                sfx_events.append({"time": round(start_t + 0.18, 2), "type": f"accent_pop_{tpl}", "rel_db": -17.0})

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
    os.makedirs(os.path.dirname(output_aac_or_wav_path), exist_ok=True)
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
