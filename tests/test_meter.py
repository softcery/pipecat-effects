import numpy as np
import pytest

from pipecat_effects import Meter

RATE = 24000
CHUNK = 480


@pytest.mark.parametrize("rate", [24000, 48000])
def test_the_loudness_of_a_997_hz_sine_at_full_scale(rate: int):
    reading = _read(_sine(997.0, 0.0, rate), rate)

    assert abs(reading.lufs + 3.01) <= 0.1


def test_the_true_peak_of_a_997_hz_sine():
    reading = _read(_sine(997.0, -6.0))

    assert abs(reading.dbtp + 6.0) <= 0.5


def test_the_true_peak_of_a_10_khz_sine():
    reading = _read(_sine(10000.0, -6.0))

    assert abs(reading.dbtp + 6.0) <= 1.0


def test_the_true_peak_of_a_2_sample_pulse():
    pulse = np.zeros(CHUNK, dtype=np.float32)
    pulse[CHUNK // 2], pulse[CHUNK // 2 + 1] = 1.0, -1.0

    reading = _read(pulse)

    assert reading.dbtp > 0.0


def _sine(hz: float, dbfs: float, rate: int = RATE) -> np.ndarray:
    """Gives 1 s of one sine at this peak level."""
    steps = np.arange(rate) / rate
    return (10.0 ** (dbfs / 20.0) * np.sin(2.0 * np.pi * hz * steps)).astype(np.float32)


def _read(x: np.ndarray, rate: int = RATE):
    """Writes the signal to one meter, chunk by chunk, and reads it."""
    meter = Meter()
    meter.start(rate)
    for chunk in np.split(x, len(x) // CHUNK):
        meter.write(chunk)
    return meter.read()
