"""The filter on `audio_out_filter` of the stock output transport, pipecat 1.13 and later."""

import numpy as np
from pipecat.frames.frames import (
    FilterEnableFrame,
    FilterUpdateSettingsFrame,
    Frame,
    OutputAudioRawFrame,
    StartFrame,
)
from pipecat.pipeline.worker import PipelineParams
from pipecat.tests.utils import run_test
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams

from pipecat_effects import EffectsFilter, Gain

RATE = 24000
CHUNK = 960  # 40 ms, the stock output chunk
LEVEL = 8000


class Sink(BaseOutputTransport):
    """Output transport that keeps each chunk it writes."""

    def __init__(self, params: TransportParams) -> None:
        super().__init__(params)
        self.peaks: list[int] = []

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self.set_transport_ready(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        self.peaks.append(int(np.abs(np.frombuffer(frame.audio, dtype=np.int16)).max()))
        return True


def tone(destination: str | None = None) -> OutputAudioRawFrame:
    t = np.arange(CHUNK) / RATE
    audio = (LEVEL * np.sin(2 * np.pi * 440.0 * t)).astype(np.int16).tobytes()
    frame = OutputAudioRawFrame(audio=audio, sample_rate=RATE, num_channels=1)
    frame.transport_destination = destination
    return frame


async def written(
    effects: EffectsFilter, frames: list[Frame], destinations: list[str] | None = None
) -> list[int]:
    """Gives the peak of each audio chunk the transport writes, end silence excluded."""
    sink = Sink(
        TransportParams(
            audio_out_enabled=True,
            audio_out_sample_rate=RATE,
            audio_out_filter=effects,
            audio_out_destinations=destinations or [],
        )
    )
    await run_test(
        sink, frames_to_send=frames, pipeline_params=PipelineParams(audio_out_sample_rate=RATE)
    )
    return [peak for peak in sink.peaks if peak]


async def test_the_transport_runs_the_chain_on_each_chunk():
    peaks = await written(EffectsFilter([Gain(db=-6.0)]), [tone(), tone()])

    assert peaks == [4009, 4009]


async def test_a_filter_enable_frame_bypasses_the_chain():
    frames = [tone(), FilterEnableFrame(enable=False), tone(), tone()]

    peaks = await written(EffectsFilter([Gain(db=-6.0)]), frames)

    assert peaks[0] == 4009
    assert 4009 < peaks[1] < LEVEL
    assert peaks[2] == LEVEL


async def test_a_filter_update_settings_frame_swaps_the_chain():
    update = FilterUpdateSettingsFrame(settings={"effects": (Gain(db=-12.0),)})

    peaks = await written(EffectsFilter([Gain(db=-6.0)]), [tone(), update, tone(), tone()])

    assert peaks[0] == 4009
    assert peaks[2] == 2010


async def test_audio_for_another_destination_skips_the_filter():
    peaks = await written(EffectsFilter([Gain(db=-6.0)]), [tone("side")], destinations=["side"])

    assert peaks == [LEVEL]
