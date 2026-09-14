"""Renders the README clips. One mono int16 wav in, one wav and one mp4 per chain out.

It runs each chain in 20 ms chunks, as a transport does. ffmpeg draws the waveform and
muxes the mp4.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import wave
from pathlib import Path

from pipecat_effects import (
    AGC,
    Biquad,
    Compressor,
    DeEsser,
    Effects,
    EffectsFilter,
    Limiter,
    Reverb,
    Saturation,
)

CHUNK_MS = 20
PICTURE = "showwavespic=s=1280x320:colors=0x2f6feb"

CHAINS: dict[str, Effects] = {
    "voice": (
        AGC(target_lufs=-20.0),
        Biquad(kind="highpass", hz=90.0),
        Biquad(kind="lowshelf", hz=200.0, gain_db=2.5),
        Biquad(kind="peak", hz=3200.0, q=1.2, gain_db=-2.0),
        DeEsser(hz=6500.0, threshold_db=-32.0, ratio=4.0),
        Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=8.0, release_ms=120.0, makeup_db=2.0),
        Saturation(drive=1.2, mix=0.15),
        Limiter(ceiling_db=-1.0, knee_db=3.0),
    ),
    "telephone": (
        AGC(target_lufs=-20.0),
        Biquad(kind="highpass", hz=300.0),
        Biquad(kind="lowpass", hz=3400.0),
        Compressor(threshold_db=-20.0, ratio=4.0, attack_ms=3.0, release_ms=60.0, makeup_db=3.0),
        Saturation(drive=3.0, mix=0.3),
        Limiter(ceiling_db=-1.0, knee_db=3.0),
    ),
    "broadcast": (
        AGC(target_lufs=-16.0),
        Biquad(kind="highpass", hz=80.0),
        DeEsser(hz=6500.0, threshold_db=-30.0, ratio=5.0),
        Compressor(threshold_db=-24.0, ratio=6.0, attack_ms=2.0, release_ms=120.0, makeup_db=6.0),
        Biquad(kind="peak", hz=3000.0, q=1.0, gain_db=3.0),
        Saturation(drive=2.0, mix=0.25),
        Limiter(ceiling_db=-1.0, knee_db=4.0),
    ),
    "room": (
        AGC(target_lufs=-20.0),
        Reverb(decay_ms=400.0, mix=0.3),
        Limiter(ceiling_db=-1.0, knee_db=3.0),
    ),
}


def main() -> None:
    """Writes the dry clip and one clip per chain."""
    parsed = _arguments()
    rate, audio = _read(parsed.dry)
    parsed.out.mkdir(parents=True, exist_ok=True)
    _clip(parsed.out / "dry", rate, audio)
    for name, chain in CHAINS.items():
        _clip(parsed.out / name, rate, asyncio.run(_shaped(chain, rate, audio)))


async def _shaped(chain: Effects, rate: int, audio: bytes) -> bytes:
    """Runs one chain over the audio in transport chunks."""
    effects = EffectsFilter(chain)
    await effects.start(rate)
    step = 2 * rate * CHUNK_MS // 1000
    chunks = [audio[at : at + step] for at in range(0, len(audio), step)]
    return b"".join([await effects.filter(chunk) for chunk in chunks])


def _read(path: Path) -> tuple[int, bytes]:
    """Gives the rate and the samples of one mono int16 wav."""
    with wave.open(str(path), "rb") as taken:
        if taken.getnchannels() != 1 or taken.getsampwidth() != 2:
            raise ValueError(
                f"dry: expected mono int16, got {taken.getnchannels()} channels "
                f"of {8 * taken.getsampwidth()} bits"
            )
        return taken.getframerate(), taken.readframes(taken.getnframes())


def _clip(stem: Path, rate: int, audio: bytes) -> None:
    """Writes one wav, its waveform and one mp4 that plays it."""
    sound, picture = stem.with_suffix(".wav"), stem.with_suffix(".png")
    with wave.open(str(sound), "wb") as given:
        given.setnchannels(1)
        given.setsampwidth(2)
        given.setframerate(rate)
        given.writeframes(audio)
    _ffmpeg("-i", sound, "-filter_complex", PICTURE, "-frames:v", "1", picture)
    _ffmpeg(
        *("-loop", "1", "-i", picture, "-i", sound),
        *("-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p"),
        *("-c:a", "aac", "-b:a", "160k", "-shortest"),
        stem.with_suffix(".mp4"),
    )


def _ffmpeg(*arguments: str | Path) -> None:
    """Runs ffmpeg quietly. A failure raises."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, arguments)], check=True)


def _arguments() -> argparse.Namespace:
    """Reads the dry wav and the output folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", type=Path, required=True, help="mono int16 wav of speech")
    parser.add_argument("--out", type=Path, required=True, help="folder of the clips")
    return parser.parse_args()


if __name__ == "__main__":
    main()
