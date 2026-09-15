<div align="center">
  <a href="https://github.com/pipecat-ai/pipecat">
    <img alt="Pipecat" width="220px" height="auto" src="https://raw.githubusercontent.com/pipecat-ai/pipecat/main/pipecat.png">
  </a>
  <p><em>A <a href="https://docs.pipecat.ai/api-reference/server/services/audio-filters/pipecat-effects">community integration</a> for <a href="https://github.com/pipecat-ai/pipecat">Pipecat</a></em></p>
</div>

# pipecat-effects

[![PyPI version](https://img.shields.io/pypi/v/pipecat-effects?cacheSeconds=3600)](https://pypi.org/project/pipecat-effects)
[![Python versions](https://img.shields.io/pypi/pyversions/pipecat-effects?cacheSeconds=3600)](https://pypi.org/project/pipecat-effects)
[![Check workflow](https://img.shields.io/github/actions/workflow/status/softcery/pipecat-effects/check.yml?branch=main&label=check)](https://github.com/softcery/pipecat-effects/actions/workflows/check.yml)
[![License BSD 2-Clause](https://img.shields.io/github/license/softcery/pipecat-effects)](LICENSE)

pipecat-effects runs an audio effects chain on the output of a
[pipecat](https://github.com/pipecat-ai/pipecat) bot. You build the chain from 8 effects, and it
adds no latency.

## Install

```
pip install pipecat-effects
```

## Use

Pipecat 1.10.0 has no output filter field. `FilterMixer` runs the filter as the output mixer.
Tested with pipecat 1.10.0.

```python
from pipecat.transports.base_transport import TransportParams
from pipecat_effects import (
    AGC,
    Biquad,
    Compressor,
    DeEsser,
    Effects,
    EffectsFilter,
    FilterMixer,
    Limiter,
    Saturation,
)

CHAIN: Effects = (
    AGC(target_lufs=-20.0),
    Biquad(kind="highpass", hz=90.0),
    Biquad(kind="lowshelf", hz=200.0, gain_db=2.5),
    Biquad(kind="peak", hz=3200.0, q=1.2, gain_db=-2.0),
    DeEsser(hz=6500.0, threshold_db=-32.0, ratio=4.0),
    Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=8.0, release_ms=120.0, makeup_db=2.0),
    Saturation(drive=1.2, mix=0.15),
    Limiter(ceiling_db=-1.0, knee_db=3.0),
)
CHANNELS = 1


def transport_params() -> TransportParams:
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_channels=CHANNELS,
        audio_out_mixer=FilterMixer(EffectsFilter(CHAIN), channels=CHANNELS),
    )
```

`examples/bot.py` runs one voice bot with that chain. It needs 4 pipecat extras and
`OPENAI_API_KEY`. The wheel has no `examples/`, so run it from a clone of this repository.

```
uv run --with "pipecat-ai[runner,webrtc,openai,silero]" examples/bot.py --chain telephone
```

`--chain` picks one of the 4 chains in [Listen](#listen). `--bypass` runs the session with the
chain off. The log gives the loudness and the true peak of each bot turn.

## Listen

One sentence of Cartesia sonic-3.5 speech, 24 kHz mono, run in 40 ms chunks, the stock output
chunk of pipecat. `examples/chains.py` holds each chain. `examples/clips.py` renders the clips
with ffmpeg. GitHub mutes each player at load. Unmute it to listen. On PyPI each player is a
link. Loudness is integrated, measured by ffmpeg `ebur128`.

### Unprocessed

https://github.com/user-attachments/assets/9b4a4b80-8168-4380-a12d-b98f9fdcaaa7

No filter. -18.3 LUFS, -1.3 dBTP.

### EQ and compression

https://github.com/user-attachments/assets/33bbbafc-3627-416c-84f0-baf398f4922f

The chain in [Use](#use): 2.5 dB low shelf at 200 Hz, 2 dB cut at 3.2 kHz, de-esser, 3:1
compressor. -23.2 LUFS, -5.5 dBTP.

### Telephone

https://github.com/user-attachments/assets/6fff6b7a-ef53-44a1-b275-5e29ca4ab1bb

300 Hz to 3400 Hz band, 4:1 compressor, drive 3.0 at 0.3 mix. -22.0 LUFS, -5.1 dBTP.

### Broadcast

https://github.com/user-attachments/assets/0e336600-fde6-4ddb-8210-bd74be7fe0b4

100 Hz high-pass, de-esser, 4:1 compressor with 0.5 ms attack and 18 dB makeup, +4 dB at 3.5 kHz.
-16.3 LUFS, -1.4 dBTP. Against the unprocessed clip: +2.0 LU, and +3.7 dB in the share of power
from 2 to 4 kHz.

### Room

https://github.com/user-attachments/assets/6cbc794c-5a33-4cb4-a2be-ccfebffe1f79

Schroeder reverb, 400 ms decay, 0.3 mix. -21.2 LUFS, -3.5 dBTP.

## Build a chain

- A chain is any sequence of effects. The filter runs them in order and adds no stage.
- Build one filter per session. Each effect holds its state across chunks.
- Put `AGC` first. It reads the level before any stage changes it.
- If a chain ends without `Limiter`, the int16 cast hard clips each sample over full scale. End
  each chain with `Limiter`.
- Give `FilterMixer` the `audio_out_channels` value as `channels`. `start` raises over 1 channel.
- Each effect validates its values at build time. A value outside the range raises `ValueError`
  that names the field and the range.

## Effects

| effect | field | default | range |
| --- | --- | --- | --- |
| `Gain` | `db` | 0.0 | -60 to 24 |
| `Biquad` | `kind` | required | one of lowpass, highpass, bandpass, peak, lowshelf, highshelf |
| | `hz` | required | 10 to 20000 |
| | `q` | 0.7071 | 0.1 to 20 |
| | `gain_db` | 0.0 | -24 to 24 |
| `Saturation` | `drive` | 2.0 | 0.1 to 20 |
| | `mix` | 1.0 | 0 to 1 |
| `Compressor` | `threshold_db` | -18.0 | -60 to 0 |
| | `ratio` | 3.0 | 1 to 20 |
| | `attack_ms` | 5.0 | 0 to 200 |
| | `release_ms` | 80.0 | 1 to 2000 |
| | `makeup_db` | 0.0 | -24 to 24 |
| `AGC` | `target_lufs` | -20.0 | -40 to -10 |
| | `max_db_per_second` | 6.0 | 0.1 to 20 |
| `Limiter` | `ceiling_db` | -1.0 | -24 to 0 |
| | `knee_db` | 3.0 | 0 to 12 |
| `Reverb` | `decay_ms` | 200.0 | 10 to 500 |
| | `mix` | 0.15 | 0 to 1 |
| `DeEsser` | `hz` | 6500.0 | 1000 to 20000 |
| | `q` | 1.5 | 0.1 to 20 |
| | `threshold_db` | -30.0 | -60 to 0 |
| | `ratio` | 4.0 | 1 to 20 |
| | `attack_ms` | 1.0 | 0 to 200 |
| | `release_ms` | 40.0 | 1 to 2000 |

`mix` sets the dry/wet ratio. 0 gives only the input, the dry signal. 1 gives only the processed
signal, the wet signal.

Method of each effect:

| effect | method |
| --- | --- |
| `Gain` | one multiply |
| `Biquad` | one second-order section, Audio EQ Cookbook by Robert Bristow-Johnson |
| `Saturation` | tanh waveshaper, `tanh(drive * x) / tanh(drive)`, dry/wet mix |
| `Compressor` | one envelope follower |
| `AGC` | K-weighted loudness over 400 ms, gain ramped at `max_db_per_second` or less |
| `Limiter` | memoryless soft clipper, soft knee, hard ceiling on sample peaks |
| `Reverb` | Schroeder reverberator, 4 comb filters and 2 allpass filters |
| `DeEsser` | split-band, the envelope of one band-pass band sets the cut of that band |

## Control

Change the chain at runtime with 2 stock frames.

```python
from pipecat.frames.frames import MixerEnableFrame, MixerUpdateSettingsFrame
from pipecat_effects import Gain, Limiter

await worker.queue_frame(MixerEnableFrame(enable=False))
await worker.queue_frame(MixerUpdateSettingsFrame(settings={"effects": (Gain(db=-3.0), Limiter())}))
```

- `MixerEnableFrame(enable=False)` bypasses the chain. The filter gives the input, and the chain
  keeps running on it, so envelopes and delay lines stay current.
- `MixerUpdateSettingsFrame` with an `effects` key builds a new chain and swaps it in.
- Each change fades over one chunk, from the output last heard to the new output. If 2 updates
  arrive before one chunk, the chain last heard fades to the last chain. The chain between them
  is not heard.
- `FilterMixer` maps the 2 mixer frames to `FilterEnableFrame` and `FilterUpdateSettingsFrame`.
  Call `EffectsFilter.process_frame` with those 2 frames when you hold the filter directly.
- An `effects` value outside a sequence of effects raises `TypeError` that names the field. An
  item whose `start` gives no callable raises `TypeError` that names the field and the index.
- A chain that fails to build raises `ValueError` that names the `effects` field. The old chain
  keeps running.
- An update before `start` builds at `start`. A failed build then raises at `start` and names the
  field of the effect, not `effects`.

## Meter

```python
reading = mixer.read()  # Reading(lufs=-19.92, dbtp=-1.04), or None on silence
```

- `FilterMixer` meters each chunk it gives to the transport, after the int16 cast.
- `FilterMixer.read()` gives a `Reading` with `lufs` and `dbtp` since the last read, then clears
  both. Silence gives `None`.
- `lufs` is the K-weighted loudness of ITU-R BS.1770, the loudness standard. The published 48 kHz filter moves to the
  session rate by the bilinear transform. A 997 Hz sine at 0 dBFS reads -3.01 LUFS.
- `dbtp` is the true peak, on 4 times oversampling with 48 taps.
- `Meter` reads float chunks for any other caller. Its `read` gives the floor, -120.0 dB, in
  place of `None`.

## Cost

One 40 ms chunk at 24 kHz, the stock output chunk of pipecat. The 8 effect chain above, mean of
1000 chunks, median of 4 runs. Python 3.13.9, macOS arm64.

| path | mean | 95th |
| --- | --- | --- |
| filter | 0.245 ms | 0.265 ms |
| mixer on silence with the meter | 0.315 ms | 0.347 ms |
| true peak | 0.028 ms | 0.030 ms |
| loudness and true peak | 0.063 ms | 0.069 ms |

`python examples/bench.py --out rows.jsonl --sha <commit>` writes one row.

## Limits

### Chain

- The filter runs on mono. `FilterMixer.start` raises on more than 1 channel.
- The chain runs on each chunk, silence included, so attack and release stay continuous through
  silence. At the stock `audio_out_10ms_chunks` of 4, one idle session costs 25 silent chunks of
  40 ms a second, 7.9 ms of compute a second on the [Cost](#cost) machine.
- A bypassed chain keeps running, so it costs the same as an active chain.
- Outside a bypass, the chunk after an update runs the old chain and the new chain.
- A chunk of 0 samples passes through. An odd byte count raises `ValueError` that names `audio`.
- A `Biquad` or `DeEsser` centre over 0.45 of the sample rate raises at `start`, with the highest
  allowed centre and the rate. The error names `hz`, not the effect.
- At 8 kHz the highest centre is 3600 Hz. The chain in [Use](#use) raises there, since its
  `DeEsser` sits at 6500 Hz.
- Not included: lookahead, convolution, pitch shift, formant shift. The broadcast clip holds a
  peak-to-loudness ratio, true peak minus loudness, of 14.9 dB. The unprocessed clip holds
  17.0 dB. A hall reverb needs convolution.

### Effects

- `Compressor` and `DeEsser` set the gain of each 1 ms block from the peak of that block. `AGC`
  sets one target per chunk from the loudness at the chunk end. Each gain reads ahead inside its
  chunk, by up to 1 ms or 1 chunk.
- `AGC` reads momentary loudness without the gate of BS.1770. Under -50 LUFS the gain holds.
- `AGC` sets the level at its place in the chain. Later stages move the output level. The EQ and
  compression clip holds `AGC(target_lufs=-20.0)` and measures -23.2 LUFS.
- `Limiter` is a memoryless soft clipper. It has no attack or release, so a signal driven far
  over the ceiling distorts.
- The -1 dB ceiling leaves the margin for inter-sample peaks at a codec resampler. The true peak
  meter only reports.
- One section falls 12 dB per octave. A lowpass at 6000 Hz drops an 8 kHz tone by 10.0 dB at a
  24 kHz rate.
- `Reverb` takes `decay_ms` to 500.

### Meter

- The true peak meter cuts at the input Nyquist. At a 24 kHz rate it reads a 10 kHz sine 0.5 dB
  under its peak.
- The K-weighting at 8 kHz differs from the standard by 0.43 dB at most from 100 Hz to 3 kHz. At
  24 kHz it differs by 0.040 dB at most.

### Pipecat

- With an output mixer, a flush that fails to drain does not time out. Each mixer chunk reaches
  the pipeline sink and counts as progress. A flush that drains returns. The defect is in
  pipecat 1.10.0 and holds for each output mixer.

## Develop

- The package ships a `py.typed` marker. It exports `Effect`, `Apply` and `Samples` for a caller
  who writes an effect.
- `make lint` checks the lock, the format, the lint rules, and the types with pyright.
- `make test` runs the tests. `make test-lowest` runs them on the lowest allowed pipecat-ai,
  numpy and scipy. CI runs both.
- `make audit` checks `uv.lock` for known vulnerabilities.

## License

BSD 2-Clause. [Softcery](https://softcery.com) builds and maintains the package.
