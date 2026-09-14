import numpy as np
import pytest
from pipecat.frames.frames import FilterEnableFrame, FilterUpdateSettingsFrame

from pipecat_effects import Biquad, Compressor, Effects, EffectsFilter, Gain, Reverb

RATE = 24000
CHUNK = 480
LEVEL = 16384  # int16 sample at half of full scale
AUDIO = np.full(CHUNK, LEVEL, dtype=np.int16).tobytes()


async def test_the_filter_appends_no_limiter():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)
    top = np.full(CHUNK, 32767, dtype=np.int16).tobytes()

    assert await effects.filter(top) == top


async def test_a_settings_update_crossfades_without_a_step():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    steps = await _updated(effects, [Gain(db=-12.0)])

    assert steps <= 6.0


async def test_2_updates_inside_one_chunk_fade_from_the_chain_last_heard():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    steps = await _updated(effects, [Gain(db=-12.0)], [Gain(db=-6.0)])

    assert steps <= 6.0


async def test_a_reverb_chain_crossfades_without_a_step():
    effects = EffectsFilter([Reverb(decay_ms=300.0, mix=0.5)])
    await effects.start(RATE)

    steps = await _updated(effects, [Gain(db=0.0)])

    assert steps <= 6.0


async def test_a_bypass_passes_the_input_and_each_switch_fades_without_a_step():
    effects = EffectsFilter([Compressor()])
    await effects.start(RATE)

    chunks = [await effects.filter(AUDIO)]
    await effects.process_frame(FilterEnableFrame(enable=False))
    chunks += [await effects.filter(AUDIO) for _ in range(100)]
    await effects.process_frame(FilterEnableFrame(enable=True))
    chunks += [await effects.filter(AUDIO) for _ in range(2)]

    assert chunks[-3] == AUDIO
    assert chunks[-1] != AUDIO
    assert _step_db(b"".join(chunks)) <= 6.0


async def test_an_update_that_fails_to_build_keeps_the_old_chain():
    effects = EffectsFilter([Gain(db=-6.0)])
    await effects.start(RATE)
    before = await effects.filter(AUDIO)
    wide = FilterUpdateSettingsFrame(settings={"effects": [Biquad(kind="lowpass", hz=12000.0)]})

    with pytest.raises(ValueError, match="effects: hz"):
        await effects.process_frame(wide)

    assert await effects.filter(AUDIO) == before


async def test_an_update_payload_outside_a_sequence_names_the_effects_field():
    effects = EffectsFilter([Gain(db=0.0)])
    await effects.start(RATE)

    with pytest.raises(TypeError, match="effects") as raised:
        await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": 3}))
    with pytest.raises(TypeError, match="effects") as listed:
        await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": [{"db": 0}]}))

    assert "got one int" in str(raised.value)
    assert "got 1 without it" in str(listed.value)


async def test_a_chunk_of_0_samples_passes_through():
    effects = EffectsFilter([Compressor(), Gain(db=1.0)])
    await effects.start(RATE)

    assert await effects.filter(b"") == b""


async def _updated(effects: EffectsFilter, *chains: Effects) -> float:
    """Updates the chain once per given chain before one chunk, gives the largest step."""
    before = await effects.filter(AUDIO)
    for chain in chains:
        await effects.process_frame(FilterUpdateSettingsFrame(settings={"effects": chain}))
    fading = await effects.filter(AUDIO)
    after = await effects.filter(AUDIO)
    return _step_db(before + fading + after)


def _step_db(audio: bytes) -> float:
    """Gives the largest level step between 2 adjacent samples, in dB."""
    samples = np.abs(np.frombuffer(audio, dtype=np.int16).astype(np.float64)) + 1e-9
    return float(np.abs(20.0 * np.log10(samples[1:] / samples[:-1])).max())
