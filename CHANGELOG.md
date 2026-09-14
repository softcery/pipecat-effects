# Changelog

## 0.1.0, 2026-09-15

- `EffectsFilter` on `BaseAudioFilter`. It runs the chain as given, with a bypass and a settings
  update that each fade over one chunk.
- 8 effects on 5 primitives: `Gain`, `Biquad`, `Saturation`, `Compressor`, `AGC`, `Limiter`,
  `Reverb`, `DeEsser`. The caller builds the chain. The package ships no preset.
- `Meter` with K-weighted loudness in LUFS and 4 times oversampled true peak in dBTP.
- `FilterMixer` on `BaseAudioMixer`, so an output transport carries a filter today. It takes the
  channel count, meters each chunk and gives a `Reading` or `None` per call of `read`.
- A `py.typed` marker.
