"""Mixer adapter. It runs one filter on the output."""

from __future__ import annotations

from collections.abc import Mapping

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.audio.mixers.base_audio_mixer import BaseAudioMixer
from pipecat.frames.frames import (
    FilterEnableFrame,
    FilterUpdateSettingsFrame,
    MixerControlFrame,
    MixerEnableFrame,
    MixerUpdateSettingsFrame,
)

from pipecat_effects.filter import EffectsFilter
from pipecat_effects.primitives import SILENCE

DIGITS = 2  # digits of one reading


class FilterMixer(BaseAudioMixer):
    """Runs one filter on the output, until audio_out_filter merges."""

    def __init__(self, audio_filter: BaseAudioFilter, *, channels: int = 1) -> None:
        self._filter = audio_filter
        self._channels = channels
        self._meter = audio_filter.meter if isinstance(audio_filter, EffectsFilter) else None

    async def start(self, sample_rate: int) -> None:
        """Starts one filter. Over 1 channel raises."""
        if self._channels != 1:
            raise ValueError(f"audio_out_channels: expected 1, got {self._channels} channels")
        await self._filter.start(sample_rate)

    async def stop(self) -> None:
        await self._filter.stop()

    async def process_frame(self, frame: MixerControlFrame) -> None:
        """Maps one mixer frame to one filter frame."""
        if isinstance(frame, MixerEnableFrame):
            await self._filter.process_frame(FilterEnableFrame(enable=frame.enable))
        elif isinstance(frame, MixerUpdateSettingsFrame):
            await self._filter.process_frame(FilterUpdateSettingsFrame(settings=frame.settings))

    async def mix(self, audio: bytes) -> bytes:
        return await self._filter.filter(audio)

    def read(self) -> Mapping[str, float]:
        """Gives loudness and true peak since one read. Silence gives no field."""
        if self._meter is None:
            return {}
        reading = self._meter.read()
        if reading.lufs <= SILENCE:
            return {}
        return {"lufs": round(reading.lufs, DIGITS), "dbtp": round(reading.dbtp, DIGITS)}
