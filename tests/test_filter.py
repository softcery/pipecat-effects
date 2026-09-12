import numpy as np
import pytest
from pipecat.frames.frames import FilterUpdateSettingsFrame
from pipecat_effects import WARM, EffectsFilter, Gain

RATE = 24000
CHUNK = 480
LEVEL = 16384  # int16 sample at half of full scale


async def test_a_settings_update_crossfades_without_a_step():
    audio = np.full(CHUNK, LEVEL, dtype=np.int16).tobytes()
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    before = await effects.filter(audio)
    await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": [Gain(db=-12.0)]}))
    fading = await effects.filter(audio)
    after = await effects.filter(audio)

    assert _step_db(before + fading + after) <= 6.0


async def test_start_refuses_more_than_1_channel():
    effects = EffectsFilter(WARM, channels=2)

    with pytest.raises(ValueError, match="channels") as raised:
        await effects.start(RATE)

    assert "got 2 channels" in str(raised.value)


def _step_db(audio: bytes) -> float:
    """Gives the largest level step between 2 adjacent samples, in dB."""
    samples = np.abs(np.frombuffer(audio, dtype=np.int16).astype(np.float64)) + 1e-9
    return float(np.abs(20.0 * np.log10(samples[1:] / samples[:-1])).max())
