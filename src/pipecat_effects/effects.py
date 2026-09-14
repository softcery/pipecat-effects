"""Eight effects. Each one validates values and builds one apply call."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from pipecat_effects.primitives import KINDS, Envelope, Kind, Line, Loudness, Samples, Section, row

type Apply = Callable[[Samples], Samples]

FLOOR = 1e-9  # linear level that reads as silence
HOLD_LUFS = -50.0  # under this loudness, gain holds
WINDOW_MS = 400.0  # loudness window, automatic gain
COMBS = (1116, 1188, 1277, 1356)  # Schroeder delays in samples at 44100 Hz
ALLPASS = (556, 441)
ALLPASS_FEEDBACK = 0.5
SCHROEDER_RATE = 44100


class Effect(Protocol):
    """One stage. start gives one apply call."""

    def start(self, rate: int) -> Apply:
        """Builds primitives of this stage."""
        ...


type Effects = Sequence[Effect]


@dataclass(frozen=True, slots=True, kw_only=True)
class Gain:
    """One multiply."""

    db: float = 0.0

    def __post_init__(self) -> None:
        _within("db", self.db, -60.0, 24.0)

    def start(self, rate: int) -> Apply:
        """Gives one multiply."""
        factor = np.float32(_linear(self.db))
        return lambda x: x * factor


@dataclass(frozen=True, slots=True, kw_only=True)
class Biquad:
    """One second-order section from the Audio EQ Cookbook."""

    kind: Kind
    hz: float
    q: float = 0.7071
    gain_db: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind: expected one of {KINDS}, got a name outside them")
        _within("hz", self.hz, 10.0, 20000.0)
        _within("q", self.q, 0.1, 20.0)
        _within("gain_db", self.gain_db, -24.0, 24.0)

    def start(self, rate: int) -> Apply:
        """Gives one section run call."""
        return Section(self.row(rate)).run

    def row(self, rate: int) -> tuple[float, ...]:
        """Gives the 6 coefficients of this section at this rate."""
        return row(self.kind, rate=rate, hz=self.hz, q=self.q, gain_db=self.gain_db)


@dataclass(frozen=True, slots=True, kw_only=True)
class Saturation:
    """Memoryless tanh waveshaper with a dry/wet mix."""

    drive: float = 2.0
    mix: float = 1.0

    def __post_init__(self) -> None:
        _within("drive", self.drive, 0.1, 20.0)
        _within("mix", self.mix, 0.0, 1.0)

    def start(self, rate: int) -> Apply:
        """Gives one waveshaper call, unity at full scale."""
        drive = np.float32(self.drive)
        wet = np.float32(self.mix / math.tanh(self.drive))
        dry = np.float32(1.0 - self.mix)
        return lambda x: dry * x + wet * np.tanh(drive * x)


@dataclass(frozen=True, slots=True, kw_only=True)
class Compressor:
    """One envelope, gain over threshold by ratio, then makeup."""

    threshold_db: float = -18.0
    ratio: float = 3.0
    attack_ms: float = 5.0
    release_ms: float = 80.0
    makeup_db: float = 0.0

    def __post_init__(self) -> None:
        _within("threshold_db", self.threshold_db, -60.0, 0.0)
        _within("ratio", self.ratio, 1.0, 20.0)
        _within("attack_ms", self.attack_ms, 0.0, 200.0)
        _within("release_ms", self.release_ms, 1.0, 2000.0)
        _within("makeup_db", self.makeup_db, -24.0, 24.0)

    def start(self, rate: int) -> Apply:
        """Follows level, applies gain."""
        level = Envelope(rate=rate, attack_ms=self.attack_ms, release_ms=self.release_ms)
        slope = 1.0 - 1.0 / self.ratio
        threshold, makeup = self.threshold_db, self.makeup_db

        def apply(x: Samples) -> Samples:
            over = np.maximum(_decibels(level.run(np.abs(x))) - threshold, 0.0)
            return x * _gain(makeup - slope * over)

        return apply


@dataclass(frozen=True, slots=True, kw_only=True)
class AGC:
    """Momentary K-weighted loudness to target, at bounded rate."""

    target_lufs: float = -20.0
    max_db_per_second: float = 6.0

    def __post_init__(self) -> None:
        _within("target_lufs", self.target_lufs, -40.0, -10.0)
        _within("max_db_per_second", self.max_db_per_second, 0.1, 20.0)

    def start(self, rate: int) -> Apply:
        """Measures loudness, ramps gain."""
        loudness = Loudness(rate=rate, window_ms=WINDOW_MS)
        gain = Envelope(
            rate=rate, attack_ms=0.0, release_ms=0.0, max_per_second=self.max_db_per_second
        )
        target = self.target_lufs

        def apply(x: Samples) -> Samples:
            level = loudness.run(x)
            wanted = gain.value if level < HOLD_LUFS else target - level
            return x * _gain(gain.run(np.full(x.size, wanted, dtype=np.float32)))

        return apply


@dataclass(frozen=True, slots=True, kw_only=True)
class Limiter:
    """Memoryless soft clipper. Soft knee under the ceiling, hard ceiling at it."""

    ceiling_db: float = -1.0
    knee_db: float = 3.0

    def __post_init__(self) -> None:
        _within("ceiling_db", self.ceiling_db, -24.0, 0.0)
        _within("knee_db", self.knee_db, 0.0, 12.0)

    def start(self, rate: int) -> Apply:
        """Memoryless curve, 0 samples over the ceiling."""
        ceiling = np.float32(_linear(self.ceiling_db))
        knee = np.float32(_linear(self.ceiling_db - self.knee_db))
        width = np.float32(2.0 * (ceiling - knee))
        span = np.float32(4.0 * (ceiling - knee)) if self.knee_db > 0.0 else np.float32(1.0)

        def apply(x: Samples) -> Samples:
            magnitude = np.abs(x)
            over = np.clip(magnitude - knee, 0.0, width)
            return np.copysign(np.minimum(magnitude, knee + over - over * over / span), x)

        return apply


@dataclass(frozen=True, slots=True, kw_only=True)
class Reverb:
    """Schroeder reverberator. Four comb filters, 2 allpass filters."""

    decay_ms: float = 200.0
    mix: float = 0.15

    def __post_init__(self) -> None:
        _within("decay_ms", self.decay_ms, 10.0, 500.0)
        _within("mix", self.mix, 0.0, 1.0)

    def start(self, rate: int) -> Apply:
        """Sums combs, runs the allpass pair."""
        combs = [
            Line(samples=n, feedback=self._feedback(n, rate)) for n in self._delays(COMBS, rate)
        ]
        allpass = [
            Line(samples=n, feedback=ALLPASS_FEEDBACK, allpass=True)
            for n in self._delays(ALLPASS, rate)
        ]
        wet, dry = np.float32(self.mix / len(combs)), np.float32(1.0 - self.mix)

        def apply(x: Samples) -> Samples:
            tail = np.stack([comb.run(x) for comb in combs]).sum(axis=0) * wet
            for section in allpass:
                tail = section.run(tail)
            return dry * x + tail

        return apply

    def _delays(self, delays: tuple[int, ...], rate: int) -> list[int]:
        """Scales Schroeder delays to this rate."""
        return [max(round(delay * rate / SCHROEDER_RATE), 1) for delay in delays]

    def _feedback(self, samples: int, rate: int) -> float:
        """Gives feedback that falls 60 dB in decay_ms."""
        return 10.0 ** (-3000.0 * samples / (rate * self.decay_ms))


@dataclass(frozen=True, slots=True, kw_only=True)
class DeEsser:
    """Split-band de-esser. The envelope of one band-pass band sets the cut of that band."""

    hz: float = 6500.0
    q: float = 1.5
    threshold_db: float = -30.0
    ratio: float = 4.0
    attack_ms: float = 1.0
    release_ms: float = 40.0

    def __post_init__(self) -> None:
        _within("hz", self.hz, 1000.0, 20000.0)
        _within("q", self.q, 0.1, 20.0)
        _within("threshold_db", self.threshold_db, -60.0, 0.0)
        _within("ratio", self.ratio, 1.0, 20.0)
        _within("attack_ms", self.attack_ms, 0.0, 200.0)
        _within("release_ms", self.release_ms, 1.0, 2000.0)

    def start(self, rate: int) -> Apply:
        """Takes the band down over threshold."""
        band = Section.at("bandpass", rate=rate, hz=self.hz, q=self.q)
        level = Envelope(rate=rate, attack_ms=self.attack_ms, release_ms=self.release_ms)
        slope = 1.0 - 1.0 / self.ratio
        threshold = self.threshold_db

        def apply(x: Samples) -> Samples:
            found = band.run(x)
            over = np.maximum(_decibels(level.run(np.abs(found))) - threshold, 0.0)
            return x - (1.0 - _gain(-slope * over)) * found

        return apply


def _within(field: str, value: float, low: float, high: float) -> None:
    """Refuses one value outside its range."""
    if not low <= value <= high:
        side = "under" if value < low else "over"
        raise ValueError(f"{field}: expected {low} to {high}, got a value {side} the range")


def _linear(db: float) -> float:
    """Gives one amplitude from dB."""
    return 10.0 ** (db / 20.0)


def _gain(db: Samples | float) -> Samples:
    """Gives one amplitude per dB level."""
    return 10.0 ** (np.asarray(db, dtype=np.float32) / 20.0)


def _decibels(level: Samples) -> Samples:
    """Gives one dB level per amplitude."""
    return 20.0 * np.log10(np.maximum(level, FLOOR))
