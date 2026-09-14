"""Output audio filter. One chain per session, run as given."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterControlFrame, FilterEnableFrame, FilterUpdateSettingsFrame

from pipecat_effects.effects import Apply, Biquad, Effect, Effects
from pipecat_effects.primitives import Samples, Section

SCALE = 32768.0  # int16 full scale
TOP = 32767  # highest int16 sample
SETTING = "effects"  # update frame key of a new chain


class EffectsFilter(BaseAudioFilter):
    """Processes spoken audio. It adds 0 samples of latency and runs on mono."""

    def __init__(self, effects: Effects) -> None:
        self._effects: Effects = tuple(effects)
        self._rate = 0
        self._chain: list[Apply] = []
        self._heard: list[Apply] | None = None  # the chain of the last chunk, None for the input
        self._enabled = True

    async def start(self, sample_rate: int) -> None:
        """Builds the chain at this rate."""
        self._rate = sample_rate
        self._chain = _started(self._effects, sample_rate)
        self._heard = self._chain if self._enabled else None

    async def stop(self) -> None:
        """Drops the chain."""
        self._chain, self._heard, self._rate = [], None, 0

    async def process_frame(self, frame: FilterControlFrame) -> None:
        """Enable frame switches the bypass. Settings frame rebuilds the chain."""
        if isinstance(frame, FilterEnableFrame):
            self._enabled = frame.enable
        elif isinstance(frame, FilterUpdateSettingsFrame):
            self._update(frame.settings)

    async def filter(self, audio: bytes) -> bytes:
        """Runs one mono int16 chunk, silence included. Gives int16 bytes."""
        taken = decoded(audio)
        if not taken.size:
            return audio
        given = self._chunk(taken)
        return np.clip(np.rint(given * SCALE), -SCALE, TOP).astype(np.int16).tobytes()

    def _chunk(self, x: Samples) -> Samples:
        """Runs the chain, in bypass too. A change fades from the output last heard."""
        wet = _through(self._chain, x)
        before, after = self._before(x, wet), (wet if self._enabled else x)
        self._heard = self._chain if self._enabled else None
        return after if before is after else _faded(before, after)

    def _before(self, x: Samples, wet: Samples) -> Samples:
        """Gives this chunk through the chain last heard. A bypass heard the input."""
        if self._heard is None:
            return x
        return wet if self._heard is self._chain else _through(self._heard, x)

    def _update(self, settings: Mapping[str, Any]) -> None:
        """Builds the new chain, then swaps it in. A failed build keeps the old chain."""
        if (payload := settings.get(SETTING)) is None:
            return
        effects = _sequence(payload)
        if self._rate:
            try:
                self._chain = _started(effects, self._rate)
            except (TypeError, ValueError) as error:
                raise type(error)(f"{SETTING}: {error}") from error
        self._effects = effects


def decoded(audio: bytes) -> Samples:
    """Gives one int16 chunk as float32 samples, full scale at 1.0. An odd byte count raises."""
    if len(audio) % 2:
        raise ValueError(f"audio: expected int16 bytes, an even count, got {len(audio)} bytes")
    return np.frombuffer(audio, dtype=np.int16).astype(np.float32) / SCALE


def _started(effects: Effects, rate: int) -> list[Apply]:
    """Starts each effect. Adjacent biquads run as one cascade in one sosfilt call."""
    chain: list[Apply] = []
    rows: list[tuple[float, ...]] = []
    for index, effect in enumerate((*effects, None)):
        if isinstance(effect, Biquad):
            rows.append(effect.row(rate))
            continue
        if rows:
            chain.append(Section(rows).run)
            rows = []
        if effect is None:
            continue
        stage = effect.start(rate)
        if not callable(stage):
            raise TypeError(
                f"index {index}: expected start to give a callable, got {type(stage).__name__}"
            )
        chain.append(stage)
    return chain


def _through(chain: Sequence[Apply], x: Samples) -> Samples:
    """Runs one chunk through each stage."""
    for stage in chain:
        x = stage(x)
    return x


def _faded(before: Samples, after: Samples) -> Samples:
    """Fades linearly from one output to the other over 1 chunk."""
    ramp = np.linspace(0.0, 1.0, before.size + 1, dtype=np.float32)[1:]
    return before * (1.0 - ramp) + after * ramp


def _sequence(effects: Any) -> Effects:
    """Refuses one update payload outside a sequence of effects."""
    if isinstance(effects, str | bytes) or not isinstance(effects, Sequence):
        raise TypeError(
            f"{SETTING}: expected a sequence of effects, got one {type(effects).__name__}"
        )
    outside = sum(1 for effect in effects if not isinstance(effect, Effect))
    if outside:
        raise TypeError(f"{SETTING}: expected each item to give start, got {outside} without it")
    return tuple(effects)
