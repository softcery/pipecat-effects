"""Mixer adapter. It runs one filter on the output and meters the result."""

from __future__ import annotations

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.audio.mixers.base_audio_mixer import BaseAudioMixer
from pipecat.frames.frames import (
    FilterEnableFrame,
    FilterUpdateSettingsFrame,
    MixerControlFrame,
    MixerEnableFrame,
    MixerUpdateSettingsFrame,
)

from pipecat_effects.filter import decoded
from pipecat_effects.meter import Meter, Reading
from pipecat_effects.primitives import SILENCE


class FilterMixer(BaseAudioMixer):
    """Runs one filter on the output, until audio_out_filter merges. It meters each chunk."""

    def __init__(self, audio_filter: BaseAudioFilter, *, channels: int) -> None:
        self._filter = audio_filter
        self._channels = channels
        self._meter = Meter()

    async def start(self, sample_rate: int) -> None:
        """Starts the filter and the meter. Over 1 channel raises."""
        if self._channels != 1:
            raise ValueError(f"channels: expected 1, got {self._channels}")
        await self._filter.start(sample_rate)
        self._meter.start(sample_rate)

    async def stop(self) -> None:
        await self._filter.stop()

    async def process_frame(self, frame: MixerControlFrame) -> None:
        """Maps one mixer frame to one filter frame."""
        if isinstance(frame, MixerEnableFrame):
            await self._filter.process_frame(FilterEnableFrame(enable=frame.enable))
        elif isinstance(frame, MixerUpdateSettingsFrame):
            await self._filter.process_frame(FilterUpdateSettingsFrame(settings=frame.settings))

    async def mix(self, audio: bytes) -> bytes:
        """Filters one chunk and meters the int16 result."""
        mixed = await self._filter.filter(audio)
        self._meter.write(decoded(mixed))
        return mixed

    def read(self) -> Reading | None:
        """Gives loudness and true peak since the last read, then clears. Silence gives None."""
        reading = self._meter.read()
        return None if reading.lufs <= SILENCE else reading
