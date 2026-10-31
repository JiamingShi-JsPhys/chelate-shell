---
name: video-tracker
version: 1.2.0
description: >
  Turns an experiment video into reproducible physics data: tracks declared
  objects (CSRT with template fallback), computes the amplitude spectrum of the
  coordinate series, and runs physics-consistency probes. Experimental and
  unstable — every run must be checked against a known reference.
metadata:
  version: 1.2.0
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# video-tracker

Extracts coordinates from a video, derives spectra, and probes physical
consistency. It never modifies the raw video and requires every parameter to
come from the config.

- **Stage:** `ingest` · **Sandbox:** no · **Dependencies:** `numpy`, `opencv` (`matplotlib` optional for figures)

## Quick Execution

Run this exact form — do not read the source tree:

```bash
python run.py --root <WS> --action probe -- --config cfg.json
```

- `probe` verifies the config and the first frame before any tracking starts.
- Then `track` → `fft` → `report`; `physics` adds the consistency probes.
- Outputs land in `<WS>/process/vt_output/` (plus the gate JSON).

## When to use

- A recorded experiment must yield position/angle over time.
- A periodic signal must be recovered from tracked coordinates (FFT).
- Tracked data must be checked for physical plausibility.

## When NOT to use

- Low-contrast, heavily occluded or deformable footage — expect failure.
- The measurement is available directly from the instrument.

## Actions

| `--action` | Does | Extra arguments |
| --- | --- | --- |
| `probe` | Validate config + first frame | `--config <cfg>` |
| `track` | Track the declared objects | `--config <cfg>` |
| `fft` | Amplitude spectrum of the tracked series | `--config <cfg>` |
| `physics` | Physical-consistency probes | `--config <cfg> --family <fam>` |
| `report` | Markdown report from the products | `--config <cfg>` |
| `demo` | Run the bundled demo | `--config <cfg>` |

## Hard constraints

- **Never modify the raw video.** All products go under `process/`.
- **No interactive input.** ROI, FPS, scale and parameters all come from the config.
- **Deterministic.** Same video + same config → identical bytes.

## Outputs

- `<WS>/process/vt_output/<video>_tracking.csv` — `frame, time_s, x_px, y_px, confidence, reinit` (+ `x_cm, y_cm` when a scale is set).
- `<video>_summary.json`, `<video>_fft.json`, `<video>_spectra.png`, `<video>_report.md`, `<video>_physics.json`, `batch_summary.json`.
- `<WS>/process/gates/video-tracker_<ts>.json` — the gate result.

## Failure handling

- A missing or unreadable video raises a clear error and exits `2`.
- An ROI outside the first frame fails at init, before tracking.
- A per-object tracker loss is recorded, not fatal; a failed re-acquire is recorded as `reinit = False`.

## Limitations

- **Experimental / unstable** — treat every run as preliminary.
- CSRT accuracy is target-specific; sub-pixel and optical-flow support are optional.
- CPU-bound: a 1080p 60 fps clip with two objects can take several minutes.
