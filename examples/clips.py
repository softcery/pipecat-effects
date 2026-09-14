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

from chains import BROADCAST, EQ_COMPRESSION, ROOM, TELEPHONE
from pipecat_effects import Effects, EffectsFilter

CHUNK_MS = 20
PICTURE = "showwavespic=s=1280x320:colors=0x2f6feb"

CHAINS: dict[str, Effects] = {
    "eq-compression": EQ_COMPRESSION,
    "telephone": TELEPHONE,
    "broadcast": BROADCAST,
    "room": ROOM,
}


def main() -> None:
    """Writes the unprocessed clip and one clip per chain."""
    parsed = _arguments()
    rate, audio = _read(parsed.speech)
    parsed.out.mkdir(parents=True, exist_ok=True)
    _clip(parsed.out / "unprocessed", rate, audio)
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
                f"speech: expected mono int16, got {taken.getnchannels()} channels "
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
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, arguments)], check=True)  # noqa: S603, S607


def _arguments() -> argparse.Namespace:
    """Reads the speech wav and the output folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", type=Path, required=True, help="mono int16 wav of speech")
    parser.add_argument("--out", type=Path, required=True, help="folder of the clips")
    return parser.parse_args()


if __name__ == "__main__":
    main()
