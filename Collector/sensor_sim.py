# sensor_sim.py
# -*- coding: utf-8 -*-
"""
Predwise – Interview Sensor Simulator
- read_xyz(): returns (x, y, z) floats each call
- Simulates:
  * Multiple operating modes (unknown externally)
  * Noise + drift
  * Anomalies: spikes, dropouts, bursts, bias jumps
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class _ModeSpec:
    name: str
    # Base vibration characteristics
    amp: float           # overall amplitude scale
    f1: float            # dominant frequency (Hz)
    f2: float            # secondary frequency (Hz)
    noise_sigma: float   # gaussian noise sigma
    drift_per_sec: float # slow drift amount per second


class SensorSim:
    """
    Stateful simulator. Call read_xyz() at your desired sampling rate.

    Notes:
    - The simulator does NOT enforce 3200 Hz. Collector controls timing.
    - Modes change internally over time; mode label is not exposed.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        # mode switching
        min_mode_sec: float = 20.0,
        max_mode_sec: float = 120.0,
        # anomalies
        spike_prob_per_sec: float = 0.06,   # ~ once every ~16 sec on avg
        dropout_prob_per_sec: float = 0.02, # occasional dropouts
        burst_prob_per_sec: float = 0.03,
        bias_jump_prob_per_sec: float = 0.01,
    ):
        if seed is not None:
            random.seed(seed)

        self._modes = [
            _ModeSpec("IDLE",    amp=0.12, f1=18.0,  f2=60.0,  noise_sigma=0.03, drift_per_sec=0.0004),
            _ModeSpec("LIGHT",   amp=0.35, f1=32.0,  f2=92.0,  noise_sigma=0.05, drift_per_sec=0.0008),
            _ModeSpec("NORMAL",  amp=0.65, f1=48.0,  f2=120.0, noise_sigma=0.07, drift_per_sec=0.0012),
            _ModeSpec("HEAVY",   amp=1.00, f1=55.0,  f2=155.0, noise_sigma=0.09, drift_per_sec=0.0018),
            _ModeSpec("IMPACT",  amp=1.25, f1=42.0,  f2=210.0, noise_sigma=0.10, drift_per_sec=0.0015),
        ]

        self._min_mode_sec = float(min_mode_sec)
        self._max_mode_sec = float(max_mode_sec)

        self._spike_p = float(spike_prob_per_sec)
        self._dropout_p = float(dropout_prob_per_sec)
        self._burst_p = float(burst_prob_per_sec)
        self._bias_jump_p = float(bias_jump_prob_per_sec)

        self._t0 = time.monotonic()
        self._last_t = self._t0

        self._mode = random.choice(self._modes)
        self._mode_end_t = self._t0 + random.uniform(self._min_mode_sec, self._max_mode_sec)

        # stateful components
        self._phase1 = random.uniform(0, 2 * math.pi)
        self._phase2 = random.uniform(0, 2 * math.pi)
        self._bias_x = 0.0
        self._bias_y = 0.0
        self._bias_z = 0.0

        self._drift_x = 0.0
        self._drift_y = 0.0
        self._drift_z = 0.0

        # anomaly state
        self._burst_left = 0.0     # seconds remaining of burst
        self._dropout_left = 0.0   # seconds remaining of dropout
        self._spike_left = 0.0     # seconds remaining of spike window
        self._spike_scale = 0.0

    def _maybe_switch_mode(self, now: float) -> None:
        if now >= self._mode_end_t:
            # biased random walk between modes: more time in NORMAL/HEAVY
            weights = [0.20, 0.22, 0.28, 0.22, 0.08]
            self._mode = random.choices(self._modes, weights=weights, k=1)[0]
            self._mode_end_t = now + random.uniform(self._min_mode_sec, self._max_mode_sec)

    def _maybe_start_anomaly(self, dt: float) -> None:
        # Convert per-second probability to per-step probability: p_step ≈ 1 - (1 - p_sec)^dt
        def happens(p_per_sec: float) -> bool:
            if p_per_sec <= 0:
                return False
            p_step = 1.0 - pow(1.0 - p_per_sec, dt)
            return random.random() < p_step

        # Dropout: outputs near-zero + extra noise for a short duration
        if self._dropout_left <= 0 and happens(self._dropout_p):
            self._dropout_left = random.uniform(0.08, 0.40)

        # Burst: higher amplitude + higher noise briefly
        if self._burst_left <= 0 and happens(self._burst_p):
            self._burst_left = random.uniform(0.10, 0.80)

        # Spike: very large instantaneous impulses (few samples)
        if self._spike_left <= 0 and happens(self._spike_p):
            self._spike_left = random.uniform(0.01, 0.06)
            self._spike_scale = random.uniform(2.5, 8.0)

        # Bias jump: step change in bias (e.g., sensor mount shift)
        if happens(self._bias_jump_p):
            self._bias_x += random.uniform(-0.25, 0.25)
            self._bias_y += random.uniform(-0.25, 0.25)
            self._bias_z += random.uniform(-0.25, 0.25)

    def read_xyz(self) -> Tuple[float, float, float]:
        """
        Returns:
            x, y, z (float) each call.
        """
        now = time.monotonic()
        dt = max(0.0, now - self._last_t)
        self._last_t = now

        # switch mode occasionally
        self._maybe_switch_mode(now)

        # anomalies may start
        self._maybe_start_anomaly(dt)

        m = self._mode

        # advance phases (dominant frequencies)
        self._phase1 += 2.0 * math.pi * m.f1 * dt
        self._phase2 += 2.0 * math.pi * m.f2 * dt

        # slow drift (random walk-ish)
        self._drift_x += random.uniform(-1, 1) * m.drift_per_sec * dt
        self._drift_y += random.uniform(-1, 1) * m.drift_per_sec * dt
        self._drift_z += random.uniform(-1, 1) * m.drift_per_sec * dt

        # base vibration signal: mix of sinusoids with axis coupling
        s1 = math.sin(self._phase1)
        s2 = math.sin(self._phase2)
        s3 = math.sin(0.7 * self._phase2 + 0.3 * self._phase1)

        x = m.amp * (0.95 * s1 + 0.20 * s2) + 0.04 * s3
        y = m.amp * (0.55 * s1 + 0.55 * s2) - 0.02 * s3
        z = m.amp * (0.20 * s1 + 0.85 * s2) + 0.06 * s3

        # add bias + drift
        x += self._bias_x + self._drift_x
        y += self._bias_y + self._drift_y
        z += self._bias_z + self._drift_z

        # apply burst / dropout / spike effects
        if self._burst_left > 0:
            burst_gain = 1.0 + random.uniform(0.6, 1.6)
            x *= burst_gain
            y *= burst_gain
            z *= burst_gain
            self._burst_left -= dt

        if self._dropout_left > 0:
            # near zero with some noise
            x *= random.uniform(0.00, 0.08)
            y *= random.uniform(0.00, 0.08)
            z *= random.uniform(0.00, 0.08)
            self._dropout_left -= dt

        if self._spike_left > 0:
            # impulse-like addition, different axis scaling
            imp = self._spike_scale * random.uniform(-1.0, 1.0)
            x += imp * random.uniform(0.7, 1.2)
            y += imp * random.uniform(0.2, 0.9)
            z += imp * random.uniform(0.4, 1.4)
            self._spike_left -= dt

        # gaussian noise
        x += random.gauss(0.0, m.noise_sigma)
        y += random.gauss(0.0, m.noise_sigma)
        z += random.gauss(0.0, m.noise_sigma)

        return float(x), float(y), float(z)


# --- Simple module-level interface expected by the interview prompt ---

_default_sim = SensorSim(seed=42)

def read_xyz() -> Tuple[float, float, float]:
    """
    Interview contract: each call returns (x, y, z) floats.
    """
    return _default_sim.read_xyz()