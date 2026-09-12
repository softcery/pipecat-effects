"""Three chains. Each one runs AGC first and Limiter last."""

from __future__ import annotations

from pipecat_effects.effects import (
    AGC,
    Biquad,
    Compressor,
    DeEsser,
    Effect,
    Limiter,
    Saturation,
)

Effects = tuple[Effect, ...]

TELEPHONE: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=300.0),
    Biquad(kind="lowpass", hz=3400.0),
    Compressor(threshold_db=-20.0, ratio=4.0, attack_ms=3.0, release_ms=60.0, makeup_db=3.0),
    Saturation(drive=3.0, mix=0.3),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)

RADIO: Effects = (
    AGC(target_lufs=-16.0),
    Biquad(kind="highpass", hz=80.0),
    DeEsser(hz=6500.0, threshold_db=-30.0, ratio=5.0),
    Compressor(threshold_db=-24.0, ratio=6.0, attack_ms=2.0, release_ms=120.0, makeup_db=6.0),
    Biquad(kind="peak", hz=3000.0, q=1.0, gain_db=3.0),
    Saturation(drive=2.0, mix=0.25),
    Limiter(ceiling_db=-1.0, knee_db=4.0),
)

WARM: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=90.0),
    Biquad(kind="lowshelf", hz=200.0, gain_db=2.5),
    Biquad(kind="peak", hz=3200.0, q=1.2, gain_db=-2.0),
    DeEsser(hz=6500.0, threshold_db=-32.0, ratio=4.0),
    Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=8.0, release_ms=120.0, makeup_db=2.0),
    Saturation(drive=1.2, mix=0.15),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)
