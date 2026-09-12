import numpy as np
from pipecat_effects import AGC, Biquad, Limiter, Meter, Saturation

RATE = 16000
CHUNK = 320


def test_the_lowpass_drops_the_nyquist_tone_and_holds_the_voice_band():
    cut = Biquad(kind="lowpass", hz=6000.0)

    high = _peak_db(_run(cut, _tone(8000.0, RATE)))
    low = _peak_db(_run(cut, _tone(1000.0, RATE)))

    assert high <= -20.0
    assert abs(low) <= 1.0


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


def _run(effect, x: np.ndarray) -> np.ndarray:
    """Runs one effect over the signal."""
    apply = effect.start(RATE)
    return np.concatenate([apply(chunk) for chunk in np.split(x, len(x) // CHUNK)])


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


def _peak_db(x: np.ndarray) -> float:
    """Gives the settled peak in dBFS."""
    return float(20.0 * np.log10(np.abs(x[len(x) // 2 :]).max() + 1e-12))
