# pipecat-effects

Output audio effects for [pipecat](https://github.com/pipecat-ai/pipecat). One filter, 8 effects
and one loudness meter. You build the chain. The chain is causal and adds 0 samples of latency.
The package ships a `py.typed` marker.

Tested with pipecat-ai 1.10.0, numpy 2.5.3, scipy 1.18.1 on Python 3.13.9.

## Install

```
pip install pipecat-effects
```

## Use

Pipecat has no output filter field yet, so `FilterMixer` carries the filter as the output mixer.

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

`examples/bot.py` runs one voice bot with that chain.

## Listen

One sentence of Cartesia sonic-3.5 speech, 24 kHz mono, run in 20 ms chunks as a transport
does. `examples/clips.py` holds each chain and renders the clips with ffmpeg. GitHub mutes each
player at load. Unmute it to listen. Loudness is integrated, measured by ffmpeg `ebur128`.

### Dry

https://github.com/user-attachments/assets/db4aec5b-0c94-4f29-95b0-343d64e6c718

No filter. -18.3 LUFS, -1.3 dBTP.

### Voice

https://github.com/user-attachments/assets/b0503417-de1f-47bd-90e0-1152c1e9d34a

The chain in [Use](#use): low boost, high cut, de-esser, 3:1 compressor. -23.2 LUFS, -5.4 dBTP.

### Telephone

https://github.com/user-attachments/assets/dcb91965-4ee8-4227-b445-88c6d366de87

300 Hz to 3400 Hz band, 4:1 compressor, drive 3.0 at 0.3 mix. -22.0 LUFS, -5.0 dBTP.

### Broadcast

https://github.com/user-attachments/assets/153a9e6e-f418-403f-ab53-7dc24da19081

AGC at -16 LUFS, de-esser, 6:1 compressor, +3 dB at 3000 Hz. -22.9 LUFS, -6.9 dBTP.

### Room

https://github.com/user-attachments/assets/fd63f979-ba8f-4652-a544-b967fd25f1a6

Reverb with 400 ms decay at 0.3 mix. -21.1 LUFS, -3.4 dBTP.

## Build a chain

- A chain is any sequence of effects. The filter runs them in order.
- Build one filter per session. Each effect holds its state across chunks.
- Put `AGC` first. It reads the level before any stage changes it.
- The filter appends `Limiter()` to a chain that ends elsewhere, so the int16 cast clips 0 samples.
- `FilterMixer` takes the channel count of the transport params. `start` raises over 1 channel.
- Each effect validates its values at build time. A value outside the range raises `ValueError`
  that names the field and the range.

The chain in [Use](#use) is one voicing. [Listen](#listen) compares it with 3 other chains.

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

Method of each effect:

| effect | method |
| --- | --- |
| `Gain` | one multiply |
| `Biquad` | one second-order section, RBJ cookbook |
| `Saturation` | `tanh(drive * x) / tanh(drive)`, dry and wet sum |
| `Compressor` | one envelope follower |
| `AGC` | K-weighted loudness over 400 ms, ramped gain |
| `Limiter` | soft knee, hard bound on sample peaks |
| `Reverb` | 4 comb lines and 2 allpass lines, Schroeder |
| `DeEsser` | one band, taken out by its envelope |

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
- An `effects` value outside a sequence raises `ValueError` that names the field and the type.

## Meter

```python
reading = mixer.read()  # {"lufs": -19.92, "dbtp": -1.04}, or {} on silence
```

- `EffectsFilter.meter.read()` gives a `Reading` with `lufs` and `dbtp` of the output since the
  last read, then clears both.
- `lufs` is the K-weighted loudness. `dbtp` is the true peak, on 4 times oversampling with 48
  taps.
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
- The chain runs on every chunk, silence included, so each follower keeps its time. One idle
  session costs 100 silent chunks a second.
- `AGC` reads momentary loudness without the gate of BS.1770. Under -50 LUFS the gain holds.
- `AGC` sets the level at its place in the chain. Later stages move the output level. The
  broadcast clip holds `AGC(target_lufs=-16.0)` and measures -22.9 LUFS.
- The limiter bounds sample peaks. The -1 dB ceiling leaves the margin for inter-sample peaks at
  a codec resampler. The true peak meter reports, it does not bound.
- A `Biquad` centre over 0.45 of the sample rate raises at `start`, with the bound and the rate.
- One section falls 12 dB per octave. A lowpass at 6000 Hz drops an 8 kHz tone by 10.0 dB at a
  24 kHz rate.
- A chunk of 0 samples passes through. The primitives need 1 sample or more.
- `Reverb` takes `decay_ms` to 500. A hall needs convolution and stays out.
- Pitch, formant, lookahead and convolution stay out.
- `FilterMixer` goes away when pipecat takes an output filter field on `TransportParams`.

## License

BSD 2-Clause.
