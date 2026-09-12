"""Mixer adapter. It carries one filter on the output."""

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


class FilterMixer(BaseAudioMixer):
    """Runs one filter on the output, until audio_out_filter merges."""

    def __init__(self, audio_filter: BaseAudioFilter) -> None:
        self._filter = audio_filter

    async def start(self, sample_rate: int) -> None:
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
