# pipecat-effects

Output audio effects for [pipecat](https://github.com/pipecat-ai/pipecat). One filter, 8 effects
and one loudness meter. You build the chain. The chain is causal and adds 0 samples of latency.
The package ships a `py.typed` marker.

CI tests the package on `uv.lock` and on the lowest allowed pipecat-ai, numpy and scipy.

## Install

```
pip install pipecat-effects
```

## Use

Pipecat has no output filter field yet, so `FilterMixer` runs the filter as the output mixer.

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


def transport_params() -> TransportParams:
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_mixer=FilterMixer(EffectsFilter(CHAIN), channels=1),
    )
```

`examples/bot.py` runs one voice bot with that chain. It needs 4 pipecat extras and
`OPENAI_API_KEY`.

```
pip install pipecat-effects "pipecat-ai[runner,webrtc,openai,silero]"
python examples/bot.py
```

## Listen

One sentence of Cartesia sonic-3.5 speech, 24 kHz mono, run in 20 ms chunks as a transport
does. `examples/chains.py` holds each chain. `examples/clips.py` renders the clips with ffmpeg.
GitHub mutes each player at load. Unmute it to listen. Loudness is integrated, measured by
ffmpeg `ebur128`.

### Unprocessed

https://github.com/user-attachments/assets/db4aec5b-0c94-4f29-95b0-343d64e6c718

No filter. -18.3 LUFS, -1.3 dBTP.

### EQ and compression

https://github.com/user-attachments/assets/b0503417-de1f-47bd-90e0-1152c1e9d34a

The chain in [Use](#use): 2.5 dB low shelf at 200 Hz, 2 dB cut at 3.2 kHz, de-esser, 3:1
compressor. -23.2 LUFS, -5.5 dBTP.

### Telephone

https://github.com/user-attachments/assets/dcb91965-4ee8-4227-b445-88c6d366de87

300 Hz to 3400 Hz band, 4:1 compressor, drive 3.0 at 0.3 mix. -22.0 LUFS, -5.1 dBTP.

### Broadcast

https://github.com/user-attachments/assets/e0a58689-c594-4ff4-8a63-84776262fd14

100 Hz high-pass, de-esser, 4:1 compressor with 0.5 ms attack and 18 dB makeup, +4 dB at 3.5 kHz.
-16.3 LUFS, -1.4 dBTP. Against the unprocessed clip: +2.0 LU, and +3.7 dB from 2 to 4 kHz.

### Room

https://github.com/user-attachments/assets/fd63f979-ba8f-4652-a544-b967fd25f1a6

Schroeder reverb, 400 ms decay, 0.3 mix. -21.2 LUFS, -3.4 dBTP.

## Build a chain

- A chain is any sequence of effects. The filter runs them in order.
- Build one filter per session. Each effect holds its state across chunks.
- Put `AGC` first. It reads the level before any stage changes it.
- The filter appends `Limiter()` to a chain that ends elsewhere, so the int16 cast clips 0 samples.
- `FilterMixer` takes the channel count of the transport params. `start` raises over 1 channel.
- Each effect validates its values at build time. A value outside the range raises `ValueError`
  that names the field and the range.

The chain in [Use](#use) is one example. [Listen](#listen) compares it with 3 other chains.

## Effects

| effect | field | default | range |
| --- | --- | --- | --- |
| `Gain` | `db` | 0.0 | -60 to 24 |
| `Biquad` | `kind` | none | one of lowpass, highpass, bandpass, peak, lowshelf, highshelf |
| | `hz` | none | 10 to 20000 |
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

await task.queue_frame(MixerEnableFrame(enable=False))
await task.queue_frame(MixerUpdateSettingsFrame(settings={"effects": (Gain(db=-3.0), Limiter())}))
```

- `MixerEnableFrame(enable=False)` bypasses the chain. The audio passes unchanged.
- `MixerUpdateSettingsFrame` with an `effects` key builds a new chain and crossfades over one
  chunk.
- The transport maps both to `FilterEnableFrame` and `FilterUpdateSettingsFrame`. Call
  `EffectsFilter.process_frame` with those 2 frames when you hold the filter directly.
- An `effects` value outside a sequence of effects raises `TypeError` that names the field.

## Meter

```python
reading = mixer.read()  # {"lufs": -19.92, "dbtp": -1.04}, or {} on silence
```

- `EffectsFilter.meter.read()` gives a `Reading` with `lufs` and `dbtp` of the output since the
  last read, then clears both.
- `lufs` is the K-weighted loudness of ITU-R BS.1770. The published 48 kHz filter moves to the
  session rate by the bilinear transform. A 997 Hz sine at 0 dBFS reads -3.01 LUFS.
- `dbtp` is the true peak, on 4 times oversampling with 48 taps.
- `FilterMixer.read()` gives the same pair as a mapping, and gives no field on silence.
- Both readings hold a floor of -120.0 dB.

## Cost

One chunk at 24 kHz, the 8 stage chain above, mean of 1000 chunks. Python 3.13.9, macOS arm64,
commit 859e13c.

| path | mean | 95th |
| --- | --- | --- |
| filter, 20 ms chunk | 0.190 ms | 0.215 ms |
| mixer on silence, 10 ms chunk | 0.158 ms | 0.178 ms |
| true peak, 10 ms chunk | 0.0103 ms | 0.0115 ms |
| loudness and true peak, 10 ms chunk | 0.031 ms | 0.037 ms |

`bench.py --out rows.jsonl --sha <commit>` writes one row.

## Limits

- The filter runs on mono. `FilterMixer.start` raises on more than 1 channel.
- A flush with an output mixer never goes quiet, so `flush_pipeline` waits out its caller. The
  defect is in pipecat, and it holds for every output mixer.
- The chain runs on every chunk, silence included, so attack and release stay continuous through
  silence. One idle session costs 100 silent chunks a second.
- `AGC` reads momentary loudness without the gate of ITU-R BS.1770, the loudness standard. Under
  -50 LUFS the gain holds.
- `AGC` sets the level at its place in the chain. Later stages move the output level. The EQ and
  compression clip holds `AGC(target_lufs=-20.0)` and measures -23.2 LUFS.
- `Limiter` is a memoryless soft clipper. It has no attack or release, so a signal driven far
  over the ceiling distorts.
- The -1 dB ceiling leaves the margin for inter-sample peaks at a codec resampler. The true peak
  meter only reports.
- The true peak meter cuts at the input Nyquist. At a 24 kHz rate it reads a 10 kHz sine 0.5 dB
  under its peak.
- The K-weighting at 8 kHz differs from the standard by 0.12 dB at most from 100 Hz to 3 kHz. At
  24 kHz it differs by 0.023 dB at most.
- The package has no limiter with lookahead. The broadcast clip holds a peak-to-loudness ratio,
  true peak minus loudness, of 14.9 dB. The unprocessed clip holds 17.0 dB.
- A `Biquad` centre over 0.45 of the sample rate raises at `start`, with the highest allowed
  centre and the rate.
- One section falls 12 dB per octave. A lowpass at 6000 Hz drops an 8 kHz tone by 10.0 dB at a
  24 kHz rate.
- A chunk of 0 samples passes through. The primitives need 1 sample or more.
- `Reverb` takes `decay_ms` to 500. A hall reverb needs convolution, which is not included.
- Pitch shift, formant shift, lookahead and convolution are not included.
- `FilterMixer` goes away when pipecat takes an output filter field on `TransportParams`.

## Develop

- `make lint` checks the lock, the format, the lint rules, and the types with pyright.
- `make test` runs the tests. `make test-lowest` runs them on the lowest allowed dependencies.
- `make audit` checks `uv.lock` for known vulnerabilities.

## License

BSD 2-Clause.
