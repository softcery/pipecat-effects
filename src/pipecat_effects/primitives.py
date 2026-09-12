"""Four stateful blocks. Each effect composes them and adds no state."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import sosfilt

Samples = np.ndarray

KINDS = ("lowpass", "highpass", "bandpass", "peak", "lowshelf", "highshelf")
NYQUIST_RATIO = 0.45  # highest centre, as part of the rate


class Section:
    """One second-order section on sosfilt, with cookbook coefficients."""

    def __init__(self, sos: Sequence[float]) -> None:
        self._sos = np.asarray(sos, dtype=np.float64).reshape(1, 6)
        self._state = np.zeros((1, 2), dtype=np.float64)

    @classmethod
    def at(
        cls, kind: str, *, rate: int, hz: float, q: float = 0.7071, gain_db: float = 0.0
    ) -> Section:
        """Gives one section at this rate. A high centre clamps."""
        w0 = 2.0 * math.pi * min(hz, NYQUIST_RATIO * rate) / rate
        b, a = _cookbook(kind, w0=w0, alpha=math.sin(w0) / (2.0 * q), gain_db=gain_db)
        return cls((*(value / a[0] for value in b), 1.0, a[1] / a[0], a[2] / a[0]))

    def run(self, x: Samples) -> Samples:
        """Filters one chunk and holds its state."""
        out, self._state = sosfilt(self._sos, x.astype(np.float64), zi=self._state)
        return out.astype(np.float32)


class Envelope:
    """One-pole follower. Attack on rise, release on fall."""

    def __init__(self, *, rate: int, attack_ms: float, release_ms: float) -> None:
        self._attack = _pole(attack_ms, rate)
        self._release = _pole(release_ms, rate)
        self._value = 0.0

    def run(self, x: Samples) -> Samples:
        """Gives one followed level per sample."""
        attack, release, value = self._attack, self._release, self._value
        out = []
        for sample in x.tolist():
            pole = attack if sample > value else release
            value += (1.0 - pole) * (sample - value)
            out.append(value)
        self._value = value
        return np.array(out, dtype=np.float32)


class Line:
    """Delay line with feedback. One comb, or one allpass."""

    def __init__(self, *, samples: int, feedback: float, allpass: bool = False) -> None:
        self._buffer = np.zeros(max(samples, 1), dtype=np.float32)
        self._feedback = np.float32(feedback)
        self._allpass = allpass
        self._at = 0

    def run(self, x: Samples) -> Samples:
        """Reads, writes with feedback, moves on."""
        out = np.empty_like(x)
        done = 0
        while done < x.size:
            step = min(self._buffer.size - self._at, x.size - done)
            delayed = self._buffer[self._at : self._at + step]
            stored = x[done : done + step] + self._feedback * delayed
            out[done : done + step] = (
                delayed - self._feedback * stored if self._allpass else delayed
            )
            self._buffer[self._at : self._at + step] = stored
            self._at = (self._at + step) % self._buffer.size
            done += step
        return out


class Fir:
    """Polyphase interpolator. It holds one chunk tail."""

    def __init__(self, taps: Samples, *, factor: int) -> None:
        phases = np.stack([taps[phase::factor] * factor for phase in range(factor)])
        self._phases = np.ascontiguousarray(phases[:, ::-1].T)  # one column per phase, back in time
        self._tail = np.zeros(phases.shape[1] - 1, dtype=np.float32)

    def run(self, x: Samples) -> Samples:
        """Gives factor samples per input sample."""
        block = np.concatenate((self._tail, x))
        self._tail = block[block.size - self._tail.size :]
        return (sliding_window_view(block, self._phases.shape[0]) @ self._phases).reshape(-1)


def _pole(ms: float, rate: int) -> float:
    """Gives one pole of this time constant."""
    return math.exp(-1000.0 / (ms * rate)) if ms > 0.0 else 0.0


def _cookbook(
    kind: str, *, w0: float, alpha: float, gain_db: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Gives numerator and denominator of one kind."""
    cos = math.cos(w0)
    amp = 10.0 ** (gain_db / 40.0)
    shelf = 2.0 * math.sqrt(amp) * alpha
    match kind:
        case "lowpass":
            return ((1.0 - cos) / 2.0, 1.0 - cos, (1.0 - cos) / 2.0), _poles(cos, alpha)
        case "highpass":
            return ((1.0 + cos) / 2.0, -(1.0 + cos), (1.0 + cos) / 2.0), _poles(cos, alpha)
        case "bandpass":
            return (alpha, 0.0, -alpha), _poles(cos, alpha)
        case "peak":
            return (
                (1.0 + alpha * amp, -2.0 * cos, 1.0 - alpha * amp),
                (1.0 + alpha / amp, -2.0 * cos, 1.0 - alpha / amp),
            )
        case "lowshelf":
            plus, minus = amp + 1.0, amp - 1.0
            return (
                (
                    amp * (plus - minus * cos + shelf),
                    2.0 * amp * (minus - plus * cos),
                    amp * (plus - minus * cos - shelf),
                ),
                (
                    plus + minus * cos + shelf,
                    -2.0 * (minus + plus * cos),
                    plus + minus * cos - shelf,
                ),
            )
        case "highshelf":
            plus, minus = amp + 1.0, amp - 1.0
            return (
                (
                    amp * (plus + minus * cos + shelf),
                    -2.0 * amp * (minus + plus * cos),
                    amp * (plus + minus * cos - shelf),
                ),
                (
                    plus - minus * cos + shelf,
                    2.0 * (minus - plus * cos),
                    plus - minus * cos - shelf,
                ),
            )
        case _:
            raise ValueError(f"kind: expected one of {KINDS}, got a name outside them")


def _poles(cos: float, alpha: float) -> tuple[float, float, float]:
    """Gives one denominator each resonant kind shares."""
    return (1.0 + alpha, -2.0 * cos, 1.0 - alpha)
