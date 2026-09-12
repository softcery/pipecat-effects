import numpy as np
from pipecat_effects import Meter

RATE = 24000
CHUNK = 480


def test_the_true_peak_of_a_997_hz_sine():
    steps = np.arange(RATE) / RATE
    sine = (10.0 ** (-6.0 / 20.0) * np.sin(2.0 * np.pi * 997.0 * steps)).astype(np.float32)

    reading = _read(sine)

    assert abs(reading.dbtp + 6.0) <= 0.5


def test_the_true_peak_of_a_2_sample_pulse():
    pulse = np.zeros(CHUNK, dtype=np.float32)
    pulse[CHUNK // 2], pulse[CHUNK // 2 + 1] = 1.0, -1.0

    reading = _read(pulse)

    assert reading.dbtp > 0.0


def _read(x: np.ndarray):
    """Writes the signal to one meter, chunk by chunk, and reads it."""
    meter = Meter()
    meter.start(RATE)
    for chunk in np.split(x, len(x) // CHUNK):
        meter.write(chunk)
    return meter.read()
