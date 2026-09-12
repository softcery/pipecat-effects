"""Chunk time of filter, idle adapter and true peak meter. One row per run."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from pipecat_effects import WARM, EffectsFilter, FilterMixer, Fir, Meter
from pipecat_effects.meter import OVERSAMPLE, TRUE_PEAK_TAPS

RUNS = 1000
RATE = 24000
CHUNK_MS = 20.0
IDLE_MS = 10.0


def main() -> None:
    """Measures each cost, appends one row."""
    parsed = _arguments()
    row = {
        "run": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "rate": parsed.rate,
        "runs": RUNS,
        "filter_ms": asyncio.run(_filter(parsed.rate)),
        "idle_ms": asyncio.run(_idle(parsed.rate)),
        "peak_ms": _peak(parsed.rate),
        "meter_ms": _meter(parsed.rate),
    }
    with parsed.out.open("a", encoding="utf-8") as rows:
        rows.write(json.dumps(row) + "\n")


async def _filter(rate: int) -> dict[str, float]:
    """Gives cost of one warm speech chunk."""
    effects = EffectsFilter(WARM)
    await effects.start(rate)
    audio = _speech(rate, CHUNK_MS)
    return await _timed(lambda: effects.filter(audio))


async def _idle(rate: int) -> dict[str, float]:
    """Gives cost of one silent chunk, chain at rest."""
    mixer = FilterMixer(EffectsFilter(WARM))
    await mixer.start(rate)
    silence = bytes(2 * int(rate * IDLE_MS / 1000.0))
    await mixer.mix(silence)
    return await _timed(lambda: mixer.mix(silence))


def _peak(rate: int) -> dict[str, float]:
    """Gives cost of one true peak reading."""
    peak = Fir(TRUE_PEAK_TAPS, factor=OVERSAMPLE)
    chunk = _samples(rate, IDLE_MS)
    return _spread([_once(lambda: np.abs(peak.run(chunk)).max()) for _ in range(RUNS)])


def _meter(rate: int) -> dict[str, float]:
    """Gives cost of both readings."""
    meter = Meter()
    meter.start(rate)
    chunk = _samples(rate, IDLE_MS)
    return _spread([_once(lambda: meter.write(chunk)) for _ in range(RUNS)])


async def _timed(call: Callable[[], Coroutine[Any, Any, Any]]) -> dict[str, float]:
    """Runs the call, gives one spread."""
    taken = []
    for _ in range(RUNS):
        started = time.perf_counter()
        await call()
        taken.append((time.perf_counter() - started) * 1000.0)
    return _spread(taken)


def _once(call: Callable[[], Any]) -> float:
    """Gives one call time in milliseconds."""
    started = time.perf_counter()
    call()
    return (time.perf_counter() - started) * 1000.0


def _spread(taken: list[float]) -> dict[str, float]:
    """Gives mean, 95th percentile and max."""
    ordered = sorted(taken)
    return {
        "mean": round(mean(taken), 4),
        "p95": round(ordered[int(0.95 * len(ordered))], 4),
        "max": round(ordered[-1], 4),
    }


def _samples(rate: int, ms: float) -> np.ndarray:
    """Gives one speech chunk as float32."""
    return np.frombuffer(_speech(rate, ms), dtype=np.int16).astype(np.float32) / 32768.0


def _speech(rate: int, ms: float) -> bytes:
    """Gives one noise chunk as int16 bytes."""
    samples = int(rate * ms / 1000.0)
    noise = np.random.default_rng(7).normal(scale=0.1, size=samples)
    return (noise * 32767).astype(np.int16).tobytes()


def _arguments() -> argparse.Namespace:
    """Reads the output path and rate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="path of the jsonl rows")
    parser.add_argument("--rate", type=int, default=RATE, help="transport sample rate in Hz")
    return parser.parse_args()


if __name__ == "__main__":
    main()
