"""Output audio filter. One chain per session, limiter last."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterControlFrame, FilterEnableFrame, FilterUpdateSettingsFrame

from pipecat_effects.effects import Apply, Biquad, Effect, Limiter
from pipecat_effects.meter import Meter
from pipecat_effects.primitives import Samples, Section

SCALE = 32768.0  # int16 full scale
TOP = 32767  # highest int16 sample
SETTING = "effects"  # update frame key of a new chain


class EffectsFilter(BaseAudioFilter):
    """Processes spoken audio. It adds 0 samples of latency and runs on mono."""

    def __init__(self, effects: Sequence[Effect]) -> None:
        self.meter = Meter()
        self._effects = _limited(effects)
        self._rate = 0
        self._chain: list[Apply] = []
        self._fading: list[Apply] = []
        self._enabled = True

    async def start(self, sample_rate: int) -> None:
        """Builds the chain at this rate."""
        self._rate = sample_rate
        self._chain = _started(self._effects, sample_rate)
        self.meter.start(sample_rate)

    async def stop(self) -> None:
        """Drops the chain."""
        self._chain, self._fading, self._rate = [], [], 0

    async def process_frame(self, frame: FilterControlFrame) -> None:
        """Enable frame bypasses. Settings frame rebuilds."""
        if isinstance(frame, FilterEnableFrame):
            self._enabled = frame.enable
        elif isinstance(frame, FilterUpdateSettingsFrame):
            self._update(frame.settings)

    async def filter(self, audio: bytes) -> bytes:
        """Runs one mono int16 chunk, silence included. Gives int16 bytes."""
        taken = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / SCALE
        if not taken.size:
            return audio
        given = self._chunk(taken)
        self.meter.write(given)
        return np.clip(np.rint(given * SCALE), -SCALE, TOP).astype(np.int16).tobytes()

    def _chunk(self, x: Samples) -> Samples:
        """Runs the chain. Update fades over 1 chunk."""
        if not self._enabled:
            return x
        given = _through(self._chain, x)
        if not self._fading:
            return given
        ramp = np.linspace(0.0, 1.0, x.size, dtype=np.float32)
        faded = _through(self._fading, x)
        self._fading = []
        return faded * (1.0 - ramp) + given * ramp

    def _update(self, settings: Mapping[str, Any]) -> None:
        """Builds one chain, keeps its old one to fade."""
        effects = settings.get(SETTING)
        if effects is None:
            return
        self._effects = _limited(_sequence(effects))
        if not self._rate:
            return
        self._fading = self._chain
        self._chain = _started(self._effects, self._rate)


def _started(effects: Sequence[Effect], rate: int) -> list[Apply]:
    """Starts each effect. Adjacent biquads run as one cascade in one sosfilt call."""
    chain: list[Apply] = []
    rows: list[tuple[float, ...]] = []
    for effect in (*effects, None):
        if isinstance(effect, Biquad):
            rows.append(effect.row(rate))
            continue
        if rows:
            chain.append(Section(rows).run)
            rows = []
        if effect is not None:
            chain.append(effect.start(rate))
    return chain


def _through(chain: Sequence[Apply], x: Samples) -> Samples:
    """Runs one chunk through each stage."""
    for stage in chain:
        x = stage(x)
    return x


def _limited(effects: Sequence[Effect]) -> tuple[Effect, ...]:
    """Gives these effects with one limiter last."""
    if effects and isinstance(effects[-1], Limiter):
        return tuple(effects)
    return (*effects, Limiter())


def _sequence(effects: Any) -> Sequence[Effect]:
    """Refuses one update payload outside a sequence of effects."""
    if isinstance(effects, str | bytes) or not isinstance(effects, Sequence):
        raise ValueError(
            f"{SETTING}: expected a sequence of effects, got one {type(effects).__name__}"
        )
    outside = sum(1 for effect in effects if not hasattr(effect, "start"))
    if outside:
        raise ValueError(f"{SETTING}: expected each item to give start, got {outside} without it")
    return effects
