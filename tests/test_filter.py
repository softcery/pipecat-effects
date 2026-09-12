import numpy as np
import pytest
from pipecat.frames.frames import FilterUpdateSettingsFrame
from pipecat_effects import WARM, EffectsFilter, Gain, Reverb

RATE = 24000
CHUNK = 480
LEVEL = 16384  # int16 sample at half of full scale


async def test_a_settings_update_crossfades_without_a_step():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    steps = await _updated(effects, [Gain(db=-12.0)])

    assert steps <= 6.0


async def test_a_reverb_chain_crossfades_without_a_step():
    effects = EffectsFilter([Reverb(decay_ms=300.0, mix=0.5)])
    await effects.start(RATE)

    steps = await _updated(effects, [Gain(db=0.0)])

    assert steps <= 6.0


async def test_an_update_payload_outside_a_sequence_names_the_effects_field():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    with pytest.raises(ValueError, match="effects") as raised:
        await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": 3}))
    with pytest.raises(ValueError, match="effects") as listed:
        await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": [{"db": 0}]}))

    assert "got one int" in str(raised.value)
    assert "got 1 without it" in str(listed.value)


async def test_a_chunk_of_0_samples_passes_through():
    effects = EffectsFilter(WARM)
    await effects.start(RATE)

    assert await effects.filter(b"") == b""


async def _updated(effects: EffectsFilter, chain: list) -> float:
    """Updates one chain mid-stream, gives its largest step over 1 fade."""
    audio = np.full(CHUNK, LEVEL, dtype=np.int16).tobytes()
    before = await effects.filter(audio)
    await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": chain}))
    fading = await effects.filter(audio)
    after = await effects.filter(audio)
    return _step_db(before + fading + after)


def _step_db(audio: bytes) -> float:
    """Gives the largest level step between 2 adjacent samples, in dB."""
    samples = np.abs(np.frombuffer(audio, dtype=np.int16).astype(np.float64)) + 1e-9
    return float(np.abs(20.0 * np.log10(samples[1:] / samples[:-1])).max())
