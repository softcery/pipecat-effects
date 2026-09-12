"""Output meter. Loudness in LUFS, true peak in dBTP."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import firwin

from pipecat_effects.effects import FLOOR, OFFSET_LUFS, k_weighting
from pipecat_effects.primitives import Fir, Samples, Section

OVERSAMPLE = 4
TAPS = 48  # interpolation taps, BS.1770 Annex 2
BAND = 0.3  # cutoff, part of the oversampled Nyquist rate
SILENCE = -120.0
TRUE_PEAK_TAPS = firwin(TAPS, BAND, window="blackman").astype(np.float32)


@dataclass(frozen=True, slots=True)
class Reading:
    """Loudness and true peak since the last read."""

    lufs: float
    dbtp: float


class Meter:
    """Reads loudness and true peak."""

    def __init__(self) -> None:
        self._weight: tuple[Section, Section] | None = None
        self._peak: Fir | None = None
        self._square = 0.0
        self._samples = 0
        self._top = 0.0

    def start(self, rate: int) -> None:
        self._weight = k_weighting(rate)
        self._peak = Fir(TRUE_PEAK_TAPS, factor=OVERSAMPLE)
        self._square, self._samples, self._top = 0.0, 0, 0.0

    def write(self, x: Samples) -> None:
        if self._weight is None or self._peak is None:
            return
        shelf, cut = self._weight
        weighted = cut.run(shelf.run(x)).astype(np.float64)
        self._square += float(np.square(weighted).sum())
        self._samples += x.size
        self._top = max(self._top, float(np.abs(self._peak.run(x)).max(initial=0.0)))

    def quiet(self, samples: int) -> None:
        """Takes one silent chunk."""
        self._samples += samples

    def read(self) -> Reading:
        """Gives both readings, then clears them."""
        mean = self._square / self._samples if self._samples else 0.0
        lufs = OFFSET_LUFS + 10.0 * math.log10(mean + FLOOR)
        reading = Reading(
            lufs=max(lufs, SILENCE), dbtp=max(20.0 * math.log10(self._top + FLOOR), SILENCE)
        )
        self._square, self._samples, self._top = 0.0, 0, 0.0
        return reading
