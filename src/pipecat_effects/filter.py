"""Output audio filter. One chain per session, limiter last."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterControlFrame, FilterEnableFrame, FilterUpdateSettingsFrame

from pipecat_effects.effects import Apply, Effect, Limiter
from pipecat_effects.meter import Meter
from pipecat_effects.primitives import Samples

SCALE = 32768.0  # int16 full scale
TOP = 32767  # highest int16 sample
SETTING = "effects"  # update frame key of a new chain


class EffectsFilter(BaseAudioFilter):
    """Shapes spoken audio. It adds 0 samples of latency."""

    def __init__(self, effects: Sequence[Effect], *, channels: int = 1) -> None:
        self.meter = Meter()
        self._effects = _limited(effects)
        self._channels = channels
        self._rate = 0
        self._chain: list[Apply] = []
        self._fading: list[Apply] = []
        self._enabled = True
        self._quiet = False

    async def start(self, sample_rate: int) -> None:
        """Builds the chain. Over 1 channel raises."""
        if self._channels != 1:
            raise ValueError(f"channels: expected 1, got {self._channels} channels")
        self._rate = sample_rate
        self._chain = [effect.start(sample_rate) for effect in self._effects]
        self._quiet = False
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
        """Runs one mono int16 chunk, gives int16 bytes."""
        taken = np.frombuffer(audio, dtype=np.int16)
        if self._quiet and not taken.any():
            self.meter.quiet(taken.size)
            return audio
        given = self._chunk(taken.astype(np.float32) / SCALE)
        self.meter.write(given)
        sent = np.clip(np.rint(given * SCALE), -SCALE, TOP).astype(np.int16)
        self._quiet = not sent.any()
        return sent.tobytes()

    def _chunk(self, x: Samples) -> Samples:
        """Runs the chain. One chunk fades on update."""
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
        """Builds one chain, keeps the old to fade."""
        effects = settings.get(SETTING)
        if effects is None:
            return
        self._effects = _limited(effects)
        if not self._rate:
            return
        self._fading = self._chain
        self._chain = [effect.start(self._rate) for effect in self._effects]
        self._quiet = False


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
