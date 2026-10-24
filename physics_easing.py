# -*- coding: utf-8 -*-
"""
physics_easing.py - محرك الفيزياء الحقيقية (Spring Physics)، الارتداد الفوري (Alex Hormozi Pop)، وضبابية الحركة الاتجاهية
=============================================================================================================================
Principal Video DSP & Motion Graphics Physics Engine (Zero-OOM Vectorized NumPy Architecture):
1. إلغاء الحركة الخطية (Zero Linear Interpolation):
   - جميع دوال الظهور والتحجيم والانتقال تعتمد حصرياً على معادلات التفاضل الفيزيائية للزنبرك المخمّد
     (`Hooke's Law Damped Harmonic Oscillator: m*x'' + c*x' + k*x = k`).
2. خوارزميات مخصصة لأسلوب (Alex Hormozi High-Retention Spring Physics):
   - `hormozi_spring_pop(elapsed_sec, duration_sec=0.18, peak_scale=1.15, rest_scale=1.0)`:
     تكبير الكلمة المنطوقة حالياً بنسبة +15% (`1.15x`) مع ارتداد زنبركي فوري (`Spring Overshoot`) ثم استقرارها أو إعادتها لحجمها الطبيعي (`1.0x`) فور نطق الكلمة التالية.
   - `spring_overshoot_scale(t, start_scale=0.0, target_scale=1.0, stiffness=280.0, damping=14.0)`:
     لظهور الأيقونات والرسومات البصرية بحيوية وسرعة فائقة (Rapid Bounce Pop-In).
3. محرك التحريك المتتابع (Staggered Keyframe Sequencer) + ضبابية الحركة الاتجاهية السريعة (Fast Directional Motion Blur).
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
# 1. دوال المنحنيات الحركية وفيزياء الزنبرك (Spring Physics & Non-Linear Easing)
# ==============================================================================
def spring_damper(
    t: Union[float, np.ndarray],
    stiffness: float = 240.0,
    damping: float = 13.5,
    mass: float = 0.85,
    initial_velocity: float = 2.5
) -> Union[float, np.ndarray]:
    """
    محاكاة فيزيائية دقيقة لحركة الزنبرك المخمّد (Hooke's Law Damped Harmonic Oscillator):
        m * x''(t) + c * x'(t) + k * x(t) = k
    تلغي الحركة الخطية تماماً وتنتج ارتداداً حيوياً سريعاً (Overshoot & Settle)
    مشابهاً لأسلوب Alex Hormozi ومحركات After Effects الاحترافية.
    """
    is_scalar = np.isscalar(t)
    t_arr = np.asarray(t, dtype=np.float64)
    t_clamped = np.clip(t_arr, 0.0, 1.0)

    k = max(1.0, float(stiffness))
    c = max(0.1, float(damping))
    m = max(0.05, float(mass))

    omega_n = math.sqrt(k / m)
    zeta = c / (2.0 * math.sqrt(k * m))

    # معايرة الزمن الفيزيائي بحيث يرتد النابض بحيوية ثم يستقر عند نهاية الفترة [0, 1]
    t_phys = t_clamped * (6.4 / max(3.8, zeta * omega_n))

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


def hormozi_spring_pop(
    word_elapsed_sec: float,
    word_duration_sec: float = 0.25,
    peak_scale: float = 1.15,
    base_scale: float = 1.00,
    stiffness: float = 340.0,
    damping: float = 14.0
) -> float:
    """
    دالة فيزياء الزنبرك المخصصة للكلمة المنطوقة حالياً بأسلوب (Alex Hormozi Kinetic Typography):
    - تقفز بالكلمة فوراً من `1.00x` إلى `1.15x` (+15%) مع نبضة ارتداد سريعة (`Spring Bounce` يصل لحظياً إلى ~1.18x ثم يستقر عند `1.15x`)
      طوال فترة نطق الكلمة، وبمجرد انتهاء الكلمة تعود فوراً إلى `1.00x`.
    """
    if word_elapsed_sec < 0.0 or word_elapsed_sec > max(0.05, word_duration_sec):
        return float(base_scale)

    attack_window = min(0.14, max(0.06, word_duration_sec * 0.55))
    u = min(1.0, max(0.0, word_elapsed_sec / attack_window))
    sp = float(spring_damper(u, stiffness=stiffness, damping=damping, mass=0.75, initial_velocity=3.2))
    scale_now = float(base_scale) + (float(peak_scale) - float(base_scale)) * sp
    return round(max(0.5, min(1.32, scale_now)), 4)


def spring_overshoot_scale(
    t: float,
    start_scale: float = 0.25,
    target_scale: float = 1.00,
    stiffness: float = 285.0,
    damping: float = 12.5,
    mass: float = 0.80
) -> float:
    """
    خوارزمية ظهور الأيقونات والرسومات البصرية بتأثير الارتداد الحيوي السريع (Spring Physics Pop-In)
    بدلاً من الحركة الخطية المملة.
    """
    u = max(0.0, min(1.0, float(t)))
    sp = float(spring_damper(u, stiffness=stiffness, damping=damping, mass=mass, initial_velocity=2.8))
    return round(float(start_scale) + (float(target_scale) - float(start_scale)) * sp, 4)


def spring_velocity(
    t: Union[float, np.ndarray],
    stiffness: float = 240.0,
    damping: float = 13.5,
    mass: float = 0.85
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


def ease_out_back(t: Union[float, np.ndarray], overshoot: float = 1.85) -> Union[float, np.ndarray]:
    """منحنى دخول بارتداد خلفي حيوي (`Ease-Out Back`) للأيقونات والشارات."""
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
    amplitude: float = 1.08,
    period: float = 0.28
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
    p1x: float = 0.16,
    p1y: float = 1.0,
    p2x: float = 0.30,
    p2y: float = 1.0
) -> Union[float, np.ndarray]:
    """محلل منحنيات بيزيير التكعيبية (`Cubic Bezier Solver` بطريقة نيوتن-رافسون - غير خطي بالكامل)."""
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
# 2. محرك التحريك المتتابع بفيزياء الزنبرك (Staggered Spring Keyframe Sequencer)
# ==============================================================================
class StaggeredKeyframeSequencer:
    """
    يدير التحريك المتتابع لعناصر المشهد الواحد (الإطار الزجاجي -> الأيقونة -> العنوان -> العناصر الفرعية -> الكلمات)
    بفيزياء الزنبرك السريعة (`stiffness=250, damping=13`) بتأخير زمني قياسي `stagger_delay = 0.035s`.
    """

    def __init__(
        self,
        stagger_delay: float = 0.035,
        entry_duration: float = 0.36,
        exit_duration: float = 0.22,
        stiffness: float = 250.0,
        damping: float = 13.0,
        mass: float = 0.82
    ):
        self.stagger_delay = max(0.01, float(stagger_delay))
        self.entry_duration = max(0.10, float(entry_duration))
        self.exit_duration = max(0.08, float(exit_duration))
        self.stiffness = float(stiffness)
        self.damping = float(damping)
        self.mass = float(mass)

    def evaluate_element(
        self,
        scene_elapsed_sec: float,
        scene_total_sec: float,
        element_index: int = 0,
        entry_offset_xy: Tuple[float, float] = (0.0, 42.0),
        start_scale: float = 0.68,
        start_rotation_deg: float = -5.5,
        easing_mode: str = "spring",
        enable_exit_animation: bool = False
    ) -> Dict[str, float]:
        delay_sec = element_index * self.stagger_delay
        local_entry_t = (scene_elapsed_sec - delay_sec) / self.entry_duration
        clamped_t = max(0.0, min(1.0, local_entry_t))

        if easing_mode == "back":
            prog = float(ease_out_back(clamped_t, overshoot=1.85))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))
        elif easing_mode == "elastic":
            prog = float(ease_out_elastic(clamped_t))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))
        elif easing_mode == "expo":
            prog = float(ease_in_out_expo(clamped_t))
            vel_norm = float(math.sin(clamped_t * math.pi) * 2.4) if 0.0 < clamped_t < 1.0 else 0.0
        else:
            prog = float(spring_damper(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))
            vel_norm = float(spring_velocity(clamped_t, stiffness=self.stiffness, damping=self.damping, mass=self.mass))

        exit_mult = 1.0
        if enable_exit_animation and scene_total_sec > (self.entry_duration + self.exit_duration + 0.35):
            rem_sec = scene_total_sec - scene_elapsed_sec - (element_index * self.stagger_delay * 0.5)
            if rem_sec < self.exit_duration:
                exit_t = max(0.0, min(1.0, rem_sec / self.exit_duration))
                exit_mult = float(ease_in_out_expo(exit_t))

        inv_p = 1.0 - prog
        dx = float(entry_offset_xy[0]) * inv_p + (1.0 - exit_mult) * (-float(entry_offset_xy[0]) * 0.6)
        dy = float(entry_offset_xy[1]) * inv_p + (1.0 - exit_mult) * (-24.0)

        scale = (float(start_scale) + (1.0 - float(start_scale)) * prog) * (0.88 + 0.12 * exit_mult)
        rotation = float(start_rotation_deg) * inv_p
        # دخول غير خطي فوري للشفافية عبر منحنى الزنبرك
        opacity_in = float(ease_in_out_expo(min(1.0, clamped_t * 2.8)))
        opacity = max(0.0, min(1.0, opacity_in * exit_mult))

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
        entry_offset_xy: Tuple[float, float] = (0.0, 38.0),
        start_scale: float = 0.70,
        easing_mode: str = "spring"
    ) -> List[Dict[str, float]]:
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

    num_samples = min(7, max(3, (blur_px // 2) + 2))
    dx_total = (vx / max(1e-5, speed)) * blur_px
    dy_total = (vy / max(1e-5, speed)) * blur_px

    acc = np.zeros_like(arr, dtype=np.float32)
    weights_sum = 0.0

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