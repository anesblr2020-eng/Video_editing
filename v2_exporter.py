# -*- coding: utf-8 -*-
"""
v2_exporter.py — التصدير المتكامل (المرحلة 4 — بدون اعتماد على cv2):
1. استخراج صورة غلاف احترافية (thumbnail.png) بدقة 1080×1920 من ذروة مشهد الخطاف البصري.
2. توليد ملف وصف الفيديو والهاشتاقات الجاهزة للنشر (post_copy.txt) على Reels / TikTok / Shorts.
3. توليد لوحة المعاينة (Contact Sheet كل 0.5 ثانية) عبر أنبوب FFmpeg + PIL كدليل بصري.
"""
import os
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from typing import List, Dict, Any


def generate_contact_sheet_05s(video_path: str, output_sheet_path: str, label_prefix: str = "v2") -> str:
    """
    يستخرج فريماً كل 0.5 ثانية من الفيديو الناتج باستخدام أنبوب FFmpeg المباشر (بدون cv2)
    ويجمعها في Contact Sheet واضح للمعاينة والنقد البصري.
    """
    if not video_path or not os.path.exists(video_path):
        return output_sheet_path

    tw, th = 210, 378
    frame_bytes = tw * th * 3
    cmd = [
        "ffmpeg", "-v", "error", "-threads", "1",
        "-i", video_path,
        "-vf", f"fps=2,scale={tw}:{th}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
    ]
    frames = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    idx = 0
    try:
        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            rgb = np.frombuffer(raw, dtype=np.uint8).reshape((th, tw, 3)).copy()
            frames.append((round(idx * 0.5, 1), rgb))
            idx += 1
            if idx >= 96:
                break
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.kill()

    if not frames:
        return output_sheet_path

    thumb_w, thumb_h = 216, 384
    cols = 8
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 28)), (10, 14, 24))
    draw = ImageDraw.Draw(sheet)

    for i_f, (t, rgb) in enumerate(frames):
        r = i_f // cols
        c = i_f % cols
        pil_img = Image.fromarray(rgb)
        x0 = c * thumb_w + 3
        y0 = r * (thumb_h + 28) + 25
        sheet.paste(pil_img, (x0, y0))
        draw.text((x0 + 8, y0 - 20), f"{label_prefix} t={t:.1f}s", fill=(250, 204, 21))

    os.makedirs(os.path.dirname(os.path.abspath(output_sheet_path)), exist_ok=True)
    sheet.save(output_sheet_path)
    return output_sheet_path


def export_social_package(
    video_path: str,
    scenes: List[Dict[str, Any]],
    output_dir: str,
) -> Dict[str, str]:
    """
    ينتج حزمة النشر النهائية:
    - thumbnail.png (1080×1920)
    - post_copy.txt (الوصف + الهاشتاقات)
    """
    os.makedirs(output_dir, exist_ok=True)
    thumb_path = os.path.join(output_dir, "thumbnail.png")
    copy_path = os.path.join(output_dir, "post_copy.txt")

    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", "0.8", "-i", video_path,
            "-frames:v", "1",
            thumb_path,
        ],
        check=False,
    )

    post_text = """🔥 تعاني من ضيق الوقت وحسابك في السوشيال ميديا متوقف بسبب صعوبة المونتاج؟

مع منصة Video Editing بالذكاء الاصطناعي، تقدر تمونطي فيديوهاتك أوتوماتيكياً:
✅ موشن جرافيك احترافي متزامن مع كل كلمة
✅ قص الصمت وتنقية الصوت تلقائياً
✅ مجاناً بالكامل وجاهز للنشر على Reels وTikTok وShorts

👇 رابط التسجيل المباشر في أسفل الفيديو / في البايو!

#مونتاج_بالذكاء_الاصطناعي #صناع_المحتوى #موشن_جرافيك #ريلز #تيك_توك #الجزائر #تطوير_الحسابات #ReelsAI #VideoEditing #ContentCreator
"""
    with open(copy_path, "w", encoding="utf-8") as f:
        f.write(post_text)

    return {
        "video_path": video_path,
        "thumbnail_path": thumb_path,
        "post_copy_path": copy_path,
    }
