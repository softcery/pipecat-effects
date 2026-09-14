import numpy as np
import pytest

from pipecat_effects import AGC, Biquad, Compressor, Limiter, Meter, Saturation

RATE = 24000
CHUNK = 480
TAIL = 120  # samples of one settled reading, 5 ms


def test_the_lowpass_follows_the_analytic_magnitude():
    cut = Biquad(kind="lowpass", hz=6000.0)

    high = _peak_db(_run(cut, _tone(8000.0, RATE)))
    low = _peak_db(_run(cut, _tone(1000.0, RATE)))

    assert abs(high - _magnitude(8000.0, hz=6000.0)) <= 0.5
    assert abs(low - _magnitude(1000.0, hz=6000.0)) <= 0.5
    assert abs(high + 10.0) <= 1.0
    assert abs(low) <= 0.1


def test_a_centre_over_the_nyquist_bound_raises_with_the_bound_and_the_rate():
    narrow = 8000

    with pytest.raises(ValueError, match="hz") as raised:
        Biquad(kind="lowpass", hz=6000.0).start(narrow)

    assert "3600.0 Hz" in str(raised.value)
    assert f"rate {narrow} Hz" in str(raised.value)


def test_the_limiter_leaves_no_sample_over_the_ceiling():
    ceiling = 10.0 ** (-1.0 / 20.0)
    saturation = Saturation(drive=5.0).start(RATE)
    limiter = Limiter(ceiling_db=-1.0).start(RATE)
    square = np.tile(np.repeat([1.0, -1.0], 20), CHUNK // 40).astype(np.float32)

    over = sum(int(np.sum(np.abs(limiter(saturation(square))) > ceiling)) for _ in range(1000))

    assert over == 0


def test_the_automatic_gain_lands_on_the_target_from_2_levels():
    target = -20.0
    speech = _speech(5 * RATE)

    landed = [
        _loudness(_run(AGC(target_lufs=target), _at(speech, level))[3 * RATE :])
        for level in (-30.0, -14.0)
    ]

    assert max(abs(loudness - target) for loudness in landed) <= 1.0


def test_the_compressor_settles_again_on_the_first_chunk_after_a_pause():
    apply = Compressor(ratio=8.0).start(RATE)
    chunks = np.split(_tone(200.0, RATE), RATE // CHUNK)
    silence = np.zeros(CHUNK, dtype=np.float32)

    settled = _gain_db([apply(chunk) for chunk in chunks][-1], chunks[-1])
    for _ in range(100):
        apply(silence)
    again = _gain_db(apply(chunks[0]), chunks[0])

    assert abs(again - settled) <= 1.0


def _run(effect, x: np.ndarray) -> np.ndarray:
    """Runs one effect over the signal."""
    apply = effect.start(RATE)
    return np.concatenate([apply(chunk) for chunk in np.split(x, len(x) // CHUNK)])


def _magnitude(tone: float, *, hz: float, q: float = 0.7071) -> float:
    """Gives the cookbook lowpass magnitude at this tone, in dB."""
    w0 = 2.0 * np.pi * hz / RATE
    alpha, cos = np.sin(w0) / (2.0 * q), np.cos(w0)
    powers = np.exp(-1j * 2.0 * np.pi * tone * np.arange(3) / RATE)
    top = np.array([(1.0 - cos) / 2.0, 1.0 - cos, (1.0 - cos) / 2.0]) @ powers
    bottom = np.array([1.0 + alpha, -2.0 * cos, 1.0 - alpha]) @ powers
    return float(20.0 * np.log10(abs(top / bottom)))


def _tone(hz: float, samples: int) -> np.ndarray:
    """Gives one full scale cosine."""
    return np.cos(2.0 * np.pi * hz * np.arange(samples) / RATE).astype(np.float32)


def _speech(samples: int) -> np.ndarray:
    """Gives noise under a syllable envelope."""
    steps = np.arange(samples) / RATE
    envelope = (0.5 + 0.5 * np.sin(2.0 * np.pi * 4.0 * steps)) ** 2
    return (np.random.default_rng(7).normal(size=samples) * envelope).astype(np.float32)


def _at(x: np.ndarray, lufs: float) -> np.ndarray:
    """Scales the signal to this loudness."""
    return (x * 10.0 ** ((lufs - _loudness(x)) / 20.0)).astype(np.float32)


def _loudness(x: np.ndarray) -> float:
    """Reads signal loudness on one meter."""
    meter = Meter()
    meter.start(RATE)
    for chunk in np.split(x[: len(x) // CHUNK * CHUNK], len(x) // CHUNK):
        meter.write(chunk)
    return meter.read().lufs


def _gain_db(given: np.ndarray, taken: np.ndarray) -> float:
    """Gives the settled gain of one chunk, in dB."""
    return float(20.0 * np.log10(np.abs(given[-TAIL:]).max() / np.abs(taken[-TAIL:]).max()))


def _peak_db(x: np.ndarray) -> float:
    """Gives the settled peak in dBFS."""
    return float(20.0 * np.log10(np.abs(x[len(x) // 2 :]).max() + 1e-12))
