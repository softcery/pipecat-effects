import numpy as np
import pytest

from pipecat_effects import EffectsFilter, FilterMixer, Gain, Reverb

RATE = 24000
CHUNK = 480
LEVEL = 16384  # int16 sample at half of full scale


async def test_start_refuses_more_than_1_channel():
    mixer = FilterMixer(EffectsFilter([Gain(db=1.0)]), channels=2)

    with pytest.raises(ValueError, match="channels") as raised:
        await mixer.start(RATE)

    assert "got 2" in str(raised.value)


async def test_the_mixer_runs_the_chain_on_a_silent_chunk():
    mixer = FilterMixer(EffectsFilter([Reverb(decay_ms=400.0, mix=0.5)]), channels=1)
    await mixer.start(RATE)

    await mixer.mix(np.full(CHUNK, LEVEL, dtype=np.int16).tobytes())
    tail = await mixer.mix(bytes(2 * CHUNK))

    assert np.abs(np.frombuffer(tail, dtype=np.int16)).max() > 0


async def test_the_reading_gives_the_loudness_and_the_true_peak():
    mixer = FilterMixer(EffectsFilter([Gain(db=1.0)]), channels=1)
    await mixer.start(RATE)

    await mixer.mix(np.full(CHUNK, LEVEL, dtype=np.int16).tobytes())
    reading = mixer.read()

    assert reading is not None
    assert -60.0 < reading.lufs < 0.0
    assert -60.0 < reading.dbtp < 0.0


async def test_the_reading_of_silence_is_none():
    mixer = FilterMixer(EffectsFilter([Gain(db=1.0)]), channels=1)
    await mixer.start(RATE)

    await mixer.mix(bytes(2 * CHUNK))

    assert mixer.read() is None
