# Changelog

## 0.1.0

- `EffectsFilter` on `BaseAudioFilter`, with a bypass, a crossfaded settings update and a meter.
- 8 effects on 4 primitives: `Gain`, `Biquad`, `Saturation`, `Compressor`, `AGC`, `Limiter`,
  `Reverb`, `DeEsser`.
- 3 presets: `TELEPHONE`, `RADIO`, `WARM`.
- `Meter` with K-weighted loudness in LUFS and 4 times oversampled true peak in dBTP.
- `FilterMixer` on `BaseAudioMixer`, so an output transport carries a filter today.
