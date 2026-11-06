[English](README.md) · [中文说明](README_zh.md)

# video-tracker

OpenCV coordinate extraction (CSRT/Template trackers), FFT spectrum analysis, and physics consistency probes (teleport/smoothness, conservation, equation of motion).

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

The test suite covers 124 cases.

## Usage

Legacy CLI (unchanged from the original release):

```bash
python -m scripts.run <probe|track|fft|physics|report|demo> --config <json>
```

Router adapter (thin wrapper — same code underneath):

```bash
python run.py --root <workspace> --action demo -- --output <dir>
```

## Migration note

The skill's internal tree is migrated byte-for-byte from the original
release (verified by SHA-256 on every test run). The only additions are the
root-level `run.py` adapter and `manifest.json`; `run.py` performs argument
mapping and gate emission only — all logic stays in the original modules,
wired through [`lib/chelate_core/adapter.py`](../../lib/chelate_core/adapter.py).

## Limitations

- The tracker extracts pixel coordinates; it does not measure physical
  quantities directly — mass, scale and frame-rate conversions are declared
  in the config and checked, not inferred.
- Occluded targets can be lost; re-acquisition is template-based and can
  latch onto a similar object.
- FFT spectra assume a steady, band-limited motion signal; noisy or
  accelerating motion blurs the peak and the bandwidth estimate.

## License

MIT — see [LICENSE](LICENSE).
