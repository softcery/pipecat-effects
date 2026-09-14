"""The 4 chains of the README clips, by name. Each one ends with Limiter."""

from pipecat_effects import AGC, Biquad, Compressor, DeEsser, Effects, Limiter, Reverb, Saturation

EQ_COMPRESSION: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=90.0),
    Biquad(kind="lowshelf", hz=200.0, gain_db=2.5),
    Biquad(kind="peak", hz=3200.0, q=1.2, gain_db=-2.0),
    DeEsser(hz=6500.0, threshold_db=-32.0, ratio=4.0),
    Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=8.0, release_ms=120.0, makeup_db=2.0),
    Saturation(drive=1.2, mix=0.15),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)

TELEPHONE: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=300.0),
    Biquad(kind="lowpass", hz=3400.0),
    Compressor(threshold_db=-20.0, ratio=4.0, attack_ms=3.0, release_ms=60.0, makeup_db=3.0),
    Saturation(drive=3.0, mix=0.3),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)

BROADCAST: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=100.0),
    DeEsser(hz=6500.0, threshold_db=-30.0, ratio=5.0),
    Compressor(threshold_db=-30.0, ratio=4.0, attack_ms=0.5, release_ms=60.0, makeup_db=18.0),
    Biquad(kind="peak", hz=3500.0, q=0.8, gain_db=4.0),
    Limiter(ceiling_db=-1.0, knee_db=2.0),
)

ROOM: Effects = (
    AGC(target_lufs=-20.0),
    Reverb(decay_ms=400.0, mix=0.3),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)

CHAINS: dict[str, Effects] = {
    "eq-compression": EQ_COMPRESSION,
    "telephone": TELEPHONE,
    "broadcast": BROADCAST,
    "room": ROOM,
}
