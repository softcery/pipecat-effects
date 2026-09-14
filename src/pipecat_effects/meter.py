"""Output meter. LUFS loudness, dBTP true peak."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import firwin

from pipecat_effects.primitives import SILENCE, Fir, Loudness, Samples, dbfs

# 48 taps at 4 times, BS.1770 Annex 2
OVERSAMPLE = 4
TAPS = 48
BAND = 1.0 / OVERSAMPLE  # cutoff at the input Nyquist, as part of the oversampled Nyquist
TRUE_PEAK_TAPS = np.asarray(firwin(TAPS, BAND, window="blackman"), dtype=np.float32)


@dataclass(frozen=True, slots=True)
class Reading:
    """One read of the output."""

    lufs: float
    dbtp: float


class Meter:
    """Reads loudness and true peak per interval."""

    def __init__(self) -> None:
        self._loudness: Loudness | None = None
        self._peak: Fir | None = None
        self._top = 0.0

    def start(self, rate: int) -> None:
        """Builds both readers."""
        self._loudness = Loudness(rate=rate)
        self._peak = Fir(TRUE_PEAK_TAPS, factor=OVERSAMPLE)
        self._top = 0.0

    def write(self, x: Samples) -> None:
        """Takes one chunk, none before start."""
        if self._loudness is None or self._peak is None:
            return
        self._loudness.run(x)
        self._top = max(self._top, float(np.abs(self._peak.run(x)).max(initial=0.0)))

    def read(self) -> Reading:
        """Gives both readings, then clears."""
        reading = Reading(
            lufs=SILENCE if self._loudness is None else self._loudness.take(),
            dbtp=dbfs(self._top),
        )
        self._top = 0.0
        return reading
