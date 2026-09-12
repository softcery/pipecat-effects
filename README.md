# pipecat-effects

Output audio effects for [pipecat](https://github.com/pipecat-ai/pipecat). One filter, 8 effects,
3 presets and one loudness meter. The chain is causal and adds 0 samples of latency.
The package ships a `py.typed` marker.

Tested with pipecat-ai 1.10.0, numpy 2.5.3, scipy 1.18.1 on Python 3.14.

## Install

```
pip install pipecat-effects
```

## Use

Pipecat has no output filter field yet, so `FilterMixer` carries the filter as the output mixer.

```python
from pipecat.transports.base_transport import TransportParams
from pipecat_effects import WARM, EffectsFilter, FilterMixer


def transport_params() -> TransportParams:
    return TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_out_mixer=FilterMixer(EffectsFilter(WARM), channels=1),
    )
```

`FilterMixer` takes the channel count of the transport params. `start` raises on more than 1
channel.

Build one filter per session. Each effect holds its state across chunks.

`examples/bot.py` runs one voice bot with the warm chain.

## Effects

| effect | values | method |
| --- | --- | --- |
| `Gain` | `db` | one multiply |
| `Biquad` | `kind`, `hz`, `q`, `gain_db` | one second-order section, RBJ cookbook |
| `Saturation` | `drive`, `mix` | `tanh(drive * x) / tanh(drive)`, dry and wet sum |
| `Compressor` | `threshold_db`, `ratio`, `attack_ms`, `release_ms`, `makeup_db` | one envelope follower |
| `AGC` | `target_lufs`, `max_db_per_second` | K-weighted loudness over 400 ms, ramped gain |
| `Limiter` | `ceiling_db`, `knee_db` | soft knee, hard bound on sample peaks |
| `Reverb` | `decay_ms`, `mix` | 4 comb lines and 2 allpass lines, Schroeder |
| `DeEsser` | `hz`, `q`, `threshold_db`, `ratio` | one band, taken out by its envelope |

`kind` takes lowpass, highpass, bandpass, peak, lowshelf or highshelf.

The presets are `TELEPHONE`, `RADIO` and `WARM`. Each one starts with `AGC` and ends with
`Limiter` at -1 dB. The filter appends `Limiter()` to any chain that ends elsewhere, so the int16
cast clips 0 samples.

## Control

`FilterEnableFrame` bypasses the chain. `FilterUpdateSettingsFrame` with `{"effects": (...)}`
builds a new chain and crossfades over one chunk. Through `FilterMixer` the transport carries
both as `MixerEnableFrame` and `MixerUpdateSettingsFrame`.

## Meter

`EffectsFilter.meter.read()` gives the K-weighted loudness in LUFS and the true peak in dBTP of
the output since the last read, then clears both. The true peak runs on 4 times oversampling with
48 taps. `FilterMixer.read()` gives the same pair as a mapping, and gives no field on silence.

## Cost

One 20 ms chunk at 24 kHz, warm preset, mean of 1000 chunks on one x86-64 workstation, Python
3.14.7.

| path | mean | 95th |
| --- | --- | --- |
| filter, 20 ms chunk | 0.260 ms | 0.323 ms |
| mixer on silence, 10 ms chunk | 0.235 ms | 0.295 ms |
| true peak, 10 ms chunk | 0.0099 ms | 0.0120 ms |
| loudness and true peak, 10 ms chunk | 0.034 ms | 0.042 ms |

`bench.py --out rows.jsonl --sha <commit>` writes one row.

## Limits

- The filter runs on mono. `FilterMixer.start` raises on more than 1 channel.
- The chain runs on every chunk, silence included, so each follower keeps its time. One idle
  session costs 100 silent chunks a second.
- `AGC` reads momentary loudness without the gate of BS.1770. Under -50 LUFS the gain holds.
- The limiter bounds sample peaks. The -1 dB ceiling leaves the margin for inter-sample peaks at
  a codec resampler. The true peak meter reports, it does not bound.
- A `Biquad` centre over 0.45 of the sample rate raises at `start`, with the bound and the rate.
- One section falls 12 dB per octave. A lowpass at 6000 Hz drops an 8 kHz tone by 10.0 dB at a
  24 kHz rate.
- A chunk of 0 samples passes through. The primitives need 1 sample or more.
- `Reverb` takes `decay_ms` to 500. A hall needs convolution and stays out.
- Pitch, formant, lookahead and convolution stay out.

## License

BSD 2-Clause.
