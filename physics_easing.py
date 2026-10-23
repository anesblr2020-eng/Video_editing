# -*- coding: utf-8 -*-
"""
physics_easing.py - محرك الفيزياء الحقيقية، منحنيات الحركة، التحريك المتتابع، وضبابية الحركة الاتجاهية
=========================================================================================================
Principal Video DSP & Motion Graphics Physics Engine (Zero-OOM Vectorized NumPy Architecture):
1. دوال المنحنيات الحركية وفيزياء الزنبرك (Analytical Damped Harmonic Oscillator & Bezier/Elastic Curves):
   - `spring_damper(t, stiffness=180.0, damping=12.0, mass=1.0)`
   - `spring_velocity(t, stiffness=180.0, damping=12.0, mass=1.0)`
   - `ease_out_back(t, overshoot=1.70158)`
   - `ease_in_out_expo(t)`
   - `ease_out_elastic(t, amplitude=1.0, period=0.3)`
   - `cubic_bezier(t, p1x, p1y, p2x, p2y)`
2. محرك التحريك المتتابع (Staggered Keyframe Sequencer):
   - يحسب الموقع `(x, y)`، الحجم `(scale)`، الدوران `(rotation)`، الشفافية `(opacity)`، والسرعة اللحظية `(vx, vy)`
     لكل عنصر فرعي (إطار البطاقة، الأيقونة، العنوان، العناصر الفرعية، الكلمات) بتأخير متدرج `stagger_delay = 0.04s`.
3. ضبابية الحركة الاتجاهية السريعة (Fast Directional Motion Blur):
   - تلتف عبر مصفوفات `NumPy` أحادية البعد الموجهة بالسرعة اللحظية باستهلاك ذاكرة صفري، وتتوقف فور استقرار العنصر.
"""

import math
import gc
import ctypes
from typing import Dict, Any, List, Tuple, Union, Optional
import numpy as np
from PIL import Image


def force_free_ram() -> None:
    """تحرير الذاكرة العشوائية في بايثون وإرجاع الصفحات المحررة لنظام لينكس (glibc malloc_trim)."""
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# ==============================================================================
# 1. دوال المنحنيات الحركية والفيزياء الرياضية (Spring Damper & Easing Functions)
# ==============================================================================
def spring_damper(
    t: Union[float, np.ndarray],
    stiffness: float = 180.0,
    damping: float = 12.0,
    mass: float = 1.0,
    initial_velocity: float = 0.0
) -> Union[float, np.ndarray]:
    """
    محاكاة فيزيائية دقيقة لحركة الزنبرك المخمّد (Hooke's Law Damped Harmonic Oscillator):
        m * x''(t) + c * x'(t) + k * x(t) = k
    تدعم القيم المفردة (`float`) والمصفوفات المتجهية (`np.ndarray`) وتنتج ارتداداً طبيعياً
    مشابهاً لمحرك After Effects / Apple visionOS قبل الاستقرار عند 1.0.
    """
    is_scalar = np.isscalar(t)
    t_arr = np.asarray(t, dtype=np.float64)
    t_clamped = np.clip(t_arr, 0.0, 1.0)

    k = max(1.0, float(stiffness))
    c = max(0.1, float(damping))
    m = max(0.05, float(mass))

    omega_n = math.sqrt(k / m)
    zeta = c / (2.0 * math.sqrt(k * m))

    # معايرة الزمن الفيزيائي بحيث يستقر النابض تماماً عند نهاية الفترة [0, 1]
    t_phys = t_clamped * (6.2 / max(4.0, zeta * omega_n))

    if zeta < 1.0 - 1e-5:
        omega_d = omega_n * math.sqrt(1.0 - zeta * zeta)
        env = np.exp(-zeta * omega_n * t_phys)
        cos_term = np.cos(omega_d * t_phys)
        sin_coeff = (zeta * omega_n - float(initial_velocity)) / max(1e-6, omega_d)
        sin_term = sin_coeff * np.sin(omega_d * t_phys)
        out = 1.0 - env * (cos_term + sin_term)
    elif abs(zeta - 1.0) <= 1e-5:
        env = np.exp(-omega_n * t_phys)
        out = 1.0 - env * (1.0 + (omega_n - float(initial_velocity)) * t_phys)
    else:
        sqrt_term = math.sqrt(zeta * zeta - 1.0)
        r1 = -omega_n * (zeta - sqrt_term)
        r2 = -omega_n * (zeta + sqrt_term)
        c2 = (float(initial_velocity) + r1) / max(1e-6, (r1 - r2))
        c1 = -1.0 - c2
        out = 1.0 + c1 * np.exp(r1 * t_phys) + c2 * np.exp(r2 * t_phys)

    out = np.where(t_arr <= 0.0, 0.0, out)
    out = np.where(t_arr >= 1.0, 1.0, out)
    return float(out) if is_scalar else out


def spring_velocity(
    t: Union[float, np.ndarray],
    stiffness: float = 180.0,
    damping: float = 12.0,
    mass: float = 1.0
) -> Union[float, np.ndarray]:
    """
    حساب السرعة اللحظية المشتقة `dx/dt` للزنبرك لتغذية محرك ضبابية الحركة الاتجاهية (`Motion Blur`).
    تصل السرعة إلى ذروتها أثناء الانطلاق وتهبط إلى `0.0` فور استقرار العنصر.
    """
    dt = 0.004
    t_arr = np.asarray(t, dtype=np.float64)
    p1 = spring_damper(np.clip(t_arr - dt, 0.0, 1.0), stiffness=stiffness, damping=damping, mass=mass)
    p2 = spring_damper(np.clip(t_arr + dt, 0.0, 1.0), stiffness=stiffness, damping=damping, mass=mass)
    vel = (p2 - p1) / (2.0 * dt)
    vel = np.where((t_arr <= 0.0) | (t_arr >= 0.98), 0.0, vel)
    return float(vel) if np.isscalar(t) else vel


def ease_out_back(t: Union[float, np.ndarray], overshoot: float = 1.70158) -> Union[float, np.ndarray]:
    """منحنى دخول بارتداد خلفي ناعم (`Ease-Out Back`) مثالي للأيقونات والشارات."""
    is_scalar = np.isscalar(t)
    x = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    c1 = float(overshoot)
    c3 = c1 + 1.0
    xm1 = x - 1.0
    out = 1.0 + c3 * (xm1 ** 3) + c1 * (xm1 ** 2)
    return float(out) if is_scalar else out


def ease_in_out_expo(t: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """منحنى أسي مزدوج فائق السلاسة (`Ease-In-Out Exponential`) لحركة الكاميرا والانتقالات."""
    is_scalar = np.isscalar(t)
    x = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    out = np.where(
        x <= 0.0,
        0.0,
        np.where(
            x >= 1.0,
            1.0,
            np.where(
                x < 0.5,
                np.power(2.0, 20.0 * x - 10.0) / 2.0,
                (2.0 - np.power(2.0, -20.0 * x + 10.0)) / 2.0
            )
        )
    )
    return float(out) if is_scalar else out


def ease_out_elastic(
    t: Union[float, np.ndarray],
    amplitude: float = 1.0,
    period: float = 0.32
) -> Union[float, np.ndarray]:
    """منحنى مرن عالي الحيوية (`Ease-Out Elastic`) للعناصر التفاعلية البارزة."""
    is_scalar = np.isscalar(t)
    x = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)
    p = max(0.08, float(period))
    a = max(1.0, float(amplitude))
    s = p / (2.0 * math.pi) * math.asin(1.0 / a)
    out = np.where(
        x <= 0.0,
        0.0,
        np.where(
            x >= 1.0,
            1.0,
            a * np.power(2.0, -10.0 * x) * np.sin((x - s) * (2.0 * math.pi) / p) + 1.0
        )
    )
    return float(out) if is_scalar else out


def cubic_bezier(
    t: Union[float, np.ndarray],
    p1x: float = 0.22,
    p1y: float = 1.0,
    p2x: float = 0.36,
    p2y: float = 1.0
) -> Union[float, np.ndarray]:
    """محلل منحنيات بيزيير التكعيبية (`Cubic Bezier Solver` بطريقة نيوتن-رافسون)."""
    is_scalar = np.isscalar(t)
    x_target = np.clip(np.asarray(t, dtype=np.float64), 0.0, 1.0)

    cx = 3.0 * p1x
    bx = 3.0 * (p2x - p1x) - cx
    ax = 1.0 - cx - bx

    cy = 3.0 * p1y
    by = 3.0 * (p2y - p1y) - cy
    ay = 1.0 - cy - by

    u = x_target.copy()
    for _ in range(5):
        x_est = ((ax * u + bx) * u + cx) * u - x_target
        dx = (3.0 * ax * u + 2.0 * bx) * u + cx
        u = np.clip(u - x_est / np.where(np.abs(dx) < 1e-6, 1e-6, dx), 0.0, 1.0)

    y_out = ((ay * u + by) * u + cy) * u
    return float(y_out) if is_scalar else y_out


# ==============================================================================
# 2. محرك التحريك المتتابع (Staggered Keyframe Sequencer)
# ==============================================================================
class StaggeredKeyframeSequencer:
    """
    يدير التحريك المتتابع لعناصر المشهد الواحد (الإطار الزجاجي -> الأيقونة -> العنوان -> العناصر الفرعية -> الكلمات)
    بتأخير زمني قياسي `stagger_delay = 0.04s` مع حساب الموقع، الحجم، الدوران، الشفافية، والسرعة اللحظية.
    """

    def __init__(
        self,
        stagger_delay: float = 0.04,
        entry_duration: float = 0.42,
        exit_duration: float = 0.24,
        stiffness: float = 185.0,
        damping: float = 13.0,
        mass: float = 1.0
    ):
        self.stagger_delay = max(0.01, float(stagger_delay))
        self.entry_duration = max(0.12, float(entry_duration))
        self.exit_duration = max(0.08, float(exit_duration))
        self.stiffness = float(stiffness)
        self.damping = float(damping)
        self.mass = float(mass)

    def evaluate_element(
        self,
        scene_elapsed_sec: float,
        scene_total_sec: float,
        element_index: int = 0,
        entry_offset_xy: Tuple[float, float] = (0.0, 38.0),
        start_scale: float = 0.76,
        start_rotation_deg: float = -4.5,
        easing_mode: str = "spring",
        enable_exit_animation: bool = False
    ) -> Dict[str, float]:
        """
        حساب الحالة الحركية الكاملة لعنصر فرعي رقم `element_index` في اللحظة `scene_elapsed_sec`:
        ترجع:
          - `x_offset`, `y_offset`: الإزاحة بالبكسل عن الموقع النهائي.
          - `scale`: معامل التكبير اللحظي.
          - `rotation`: زاوية الدوران بالدرجات.
          - `opacity`: الشفافية `[0.0 .. 1.0]`.
          - `progress`: تقدم الدخول الفيزيائي.
          - `velocity_x`, `velocity_y`, `speed`: السرعة اللحظية بالبكسل/ثانية لتشغيل `Motion Blur`.
        """
        delay_sec = element_index * self.stagger_delay
        local_entry_t = (scene_elapsed_sec - delay_sec) / self.entry_duration
        clamped_t = max(0.0, min(1.0, local_entry_t))

        if easing_mode == "back":
            prog = float(ease_out_back(clamped_t, overshoot=1.65))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping))
        elif easing_mode == "elastic":
            prog = float(ease_out_elastic(clamped_t))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping))
        elif easing_mode == "expo":
            prog = float(ease_in_out_expo(clamped_t))
            vel_norm = float(math.sin(clamped_t * math.pi) * 2.2) if 0.0 < clamped_t < 1.0 else 0.0
        else:
            prog = float(spring_damper(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))

        # حساب الخروج الاختياري في نهاية المشهد
        exit_mult = 1.0
        if enable_exit_animation and scene_total_sec > (self.entry_duration + self.exit_duration + 0.4):
            rem_sec = scene_total_sec - scene_elapsed_sec - (element_index * self.stagger_delay * 0.5)
            if rem_sec < self.exit_duration:
                exit_t = max(0.0, min(1.0, rem_sec / self.exit_duration))
                exit_mult = float(ease_in_out_expo(exit_t))

        inv_p = 1.0 - prog
        dx = float(entry_offset_xy[0]) * inv_p + (1.0 - exit_mult) * (-float(entry_offset_xy[0]) * 0.6)
        dy = float(entry_offset_xy[1]) * inv_p + (1.0 - exit_mult) * (-24.0)

        scale = (float(start_scale) + (1.0 - float(start_scale)) * prog) * (0.88 + 0.12 * exit_mult)
        rotation = float(start_rotation_deg) * inv_p
        opacity = max(0.0, min(1.0, min(1.0, clamped_t * 2.6) * exit_mult))

        vx = -float(entry_offset_xy[0]) * vel_norm / max(0.1, self.entry_duration)
        vy = -float(entry_offset_xy[1]) * vel_norm / max(0.1, self.entry_duration)
        speed = math.hypot(vx, vy)

        return {
            "x_offset": round(dx, 2),
            "y_offset": round(dy, 2),
            "scale": round(max(0.05, scale), 4),
            "rotation": round(rotation, 2),
            "opacity": round(opacity, 4),
            "progress": round(prog, 4),
            "velocity_x": round(vx, 2),
            "velocity_y": round(vy, 2),
            "speed": round(speed, 2)
        }

    def sequence_group(
        self,
        count: int,
        scene_elapsed_sec: float,
        scene_total_sec: float,
        entry_offset_xy: Tuple[float, float] = (0.0, 36.0),
        start_scale: float = 0.78,
        easing_mode: str = "spring"
    ) -> List[Dict[str, float]]:
        """توليد مصفوفة الحالات الحركية لمجموعة عناصر متتابعة (مثل كلمات العنوان أو عناصر القائمة)."""
        return [
            self.evaluate_element(
                scene_elapsed_sec=scene_elapsed_sec,
                scene_total_sec=scene_total_sec,
                element_index=i,
                entry_offset_xy=entry_offset_xy,
                start_scale=start_scale,
                easing_mode=easing_mode
            )
            for i in range(max(1, int(count)))
        ]


# ==============================================================================
# 3. ضبابية الحركة الاتجاهية السريعة (Fast Vectorized Directional Motion Blur)
# ==============================================================================
def apply_fast_directional_motion_blur(
    image_or_array: Union[Image.Image, np.ndarray],
    velocity_xy: Tuple[float, float],
    max_kernel_size: int = 13,
    velocity_scale: float = 0.035
) -> Union[Image.Image, np.ndarray]:
    """
    تطبيق تمويه حركي اتجاهي سريع جداً وخفيف على الذاكرة عبر `NumPy` عندما تكون سرعة العنصر عالية،
    ويتوقف تلقائياً (No-Op) فور استقرار العنصر (`speed < 18 px/s`).
    """
    vx, vy = float(velocity_xy[0]), float(velocity_xy[1])
    speed = math.hypot(vx, vy)
    blur_px = int(round(min(float(max_kernel_size), speed * velocity_scale)))
    if blur_px <= 1:
        return image_or_array

    is_pil = isinstance(image_or_array, Image.Image)
    pil_mode = image_or_array.mode if is_pil else "RGBA"
    arr = np.asarray(image_or_array)
    if arr.ndim < 2 or min(arr.shape[0], arr.shape[1]) < 8:
        return image_or_array

    h, w = arr.shape[0], arr.shape[1]
    num_samples = min(7, max(3, (blur_px // 2) + 2))
    dx_total = (vx / max(1e-5, speed)) * blur_px
    dy_total = (vy / max(1e-5, speed)) * blur_px

    acc = np.zeros_like(arr, dtype=np.float32)
    weights_sum = 0.0

    # أخذ عينات خطية على طول متجه السرعة اللحظية (180° Shutter Directional Integration)
    for si in range(num_samples):
        u = (si / float(num_samples - 1)) - 0.5
        sx = int(round(u * dx_total))
        sy = int(round(u * dy_total))
        w_factor = 1.0 - 0.35 * abs(u)

        shifted = np.roll(arr, shift=(sy, sx), axis=(0, 1))
        if sy > 0:
            shifted[:sy, :] = arr[:1, :]
        elif sy < 0:
            shifted[sy:, :] = arr[-1:, :]
        if sx > 0:
            shifted[:, :sx] = shifted[:, sx:sx + 1]
        elif sx < 0:
            shifted[:, sx:] = shifted[:, sx - 1:sx]

        acc += shifted.astype(np.float32) * w_factor
        weights_sum += w_factor

    out_arr = np.clip(acc / max(1e-5, weights_sum), 0, 255).astype(np.uint8)
    del acc
    return Image.fromarray(out_arr, mode=pil_mode) if is_pil else out_arr