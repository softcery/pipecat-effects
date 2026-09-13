"""Five stateful blocks. Each effect composes them and adds no state."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import sosfilt

Samples = np.ndarray

KINDS = ("lowpass", "highpass", "bandpass", "peak", "lowshelf", "highshelf")
NYQUIST_RATIO = 0.45  # highest centre, as part of the rate
BLOCK_MS = 1.0  # envelope step
K_SHELF = (1681.974, 0.7071752, 3.999843)  # BS.1770 stage 1, hz, q and gain_db
K_HIGHPASS = (38.13547, 0.5003270)  # BS.1770 stage 2, hz and q
OFFSET_LUFS = -0.691  # calibration, K-weighted mean square, BS.1770
SILENCE = -120.0  # floor of one level reading


class Section:
    """One second-order section on sosfilt, or a cascade of them, with cookbook coefficients."""

    def __init__(self, sos: Sequence[float] | Sequence[Sequence[float]]) -> None:
        self._sos = np.asarray(sos, dtype=np.float64).reshape(-1, 6)
        self._state = np.zeros((self._sos.shape[0], 2), dtype=np.float64)

    @classmethod
    def at(
        cls, kind: str, *, rate: int, hz: float, q: float = 0.7071, gain_db: float = 0.0
    ) -> Section:
        """Gives one section at this rate. A centre over the bound raises."""
        return cls(row(kind, rate=rate, hz=hz, q=q, gain_db=gain_db))

    def run(self, x: Samples) -> Samples:
        """Filters one chunk and holds its state."""
        out, self._state = sosfilt(self._sos, x.astype(np.float64), zi=self._state)
        return out.astype(np.float32)


class Envelope:
    """One-pole follower on 1 ms blocks. Attack on rise, release on fall, bounded rate."""

    def __init__(
        self,
        *,
        rate: int,
        attack_ms: float,
        release_ms: float,
        max_per_second: float = math.inf,
    ) -> None:
        self._block = max(round(BLOCK_MS * rate / 1000.0), 1)
        blocks = rate / self._block
        self._attack = _pole(attack_ms, blocks)
        self._release = _pole(release_ms, blocks)
        self._step = max_per_second / blocks
        self._value = 0.0

    @property
    def value(self) -> float:
        """Gives one level this follower holds."""
        return self._value

    def run(self, x: Samples) -> Samples:
        """Gives one followed level per sample. It steps once per block."""
        attack, release, step, value = self._attack, self._release, self._step, self._value
        levels = []
        for peak in _peaks(x, self._block):
            pole = attack if peak > value else release
            moved = value + (1.0 - pole) * (peak - value)
            value = min(max(moved, value - step), value + step)
            levels.append(value)
        self._value = value
        return np.repeat(np.array(levels, dtype=np.float32), self._block)[: x.size]


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


class Loudness:
    """K-weighted loudness on 2 sections, BS.1770. One window gives the momentary value."""

    def __init__(self, *, rate: int, window_ms: float = 0.0) -> None:
        hz, q, gain_db = K_SHELF
        cut_hz, cut_q = K_HIGHPASS
        self._weight = Section(
            (
                row("highshelf", rate=rate, hz=hz, q=q, gain_db=gain_db),
                row("highpass", rate=rate, hz=cut_hz, q=cut_q),
            )
        )
        self._window = np.zeros(round(window_ms * rate / 1000.0), dtype=np.float64)
        self._at = 0
        self._held = 0.0
        self._square = 0.0
        self._samples = 0

    @property
    def value(self) -> float:
        """Gives loudness since one take, in LUFS."""
        return lufs(self._square / self._samples if self._samples else 0.0)

    def run(self, x: Samples) -> float:
        """Takes one chunk. Gives window loudness, or interval loudness with no window."""
        squares = np.square(self._weight.run(x).astype(np.float64))
        self._square += float(squares.sum())
        self._samples += x.size
        if not self._window.size:
            return self.value
        return lufs(self._slide(squares) / self._window.size)

    def _slide(self, squares: Samples) -> float:
        """Writes one chunk into its ring, oldest first, and gives that window sum."""
        size = self._window.size
        if squares.size >= size:
            self._window[:] = squares[-size:]
            self._at, self._held = 0, float(self._window.sum())
            return self._held
        end = self._at + squares.size
        if end <= size:
            self._held += float(squares.sum() - self._window[self._at : end].sum())
            self._window[self._at : end] = squares
        else:
            head = size - self._at
            self._held += float(
                squares.sum() - self._window[self._at :].sum() - self._window[: end - size].sum()
            )
            self._window[self._at :] = squares[:head]
            self._window[: end - size] = squares[head:]
        self._at = end % size
        return self._held

    def take(self) -> float:
        """Gives loudness since one take, then clears it."""
        taken = self.value
        self._square, self._samples = 0.0, 0
        return taken


def lufs(mean_square: float) -> float:
    """Gives loudness of one K-weighted mean square. Silence gives its floor."""
    return _floor(OFFSET_LUFS + 10.0 * math.log10(mean_square)) if mean_square > 0.0 else SILENCE


def dbfs(level: float) -> float:
    """Gives one amplitude in dB. Silence gives the floor."""
    return _floor(20.0 * math.log10(level)) if level > 0.0 else SILENCE


def _floor(db: float) -> float:
    """Holds one reading at the floor."""
    return max(db, SILENCE)


def row(
    kind: str, *, rate: int, hz: float, q: float = 0.7071, gain_db: float = 0.0
) -> tuple[float, ...]:
    """Gives 6 coefficients of one section at this rate. A centre over its bound raises."""
    bound = NYQUIST_RATIO * rate
    if hz > bound:
        raise ValueError(
            f"hz: expected at most {bound} Hz at the rate {rate} Hz, got a centre over it"
        )
    w0 = 2.0 * math.pi * hz / rate
    b, a = _cookbook(kind, w0=w0, alpha=math.sin(w0) / (2.0 * q), gain_db=gain_db)
    return (*(value / a[0] for value in b), 1.0, a[1] / a[0], a[2] / a[0])


def _peaks(x: Samples, size: int) -> Samples:
    """Gives highest value of each block. Its last block repeats one edge."""
    blocks = -(-x.size // size)
    padded = np.pad(x, (0, blocks * size - x.size), mode="edge")
    return padded.reshape(blocks, size).max(axis=1)


def _pole(ms: float, per_second: float) -> float:
    """Gives one pole of this time constant, at this step rate."""
    return math.exp(-1000.0 / (ms * per_second)) if ms > 0.0 else 0.0


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
