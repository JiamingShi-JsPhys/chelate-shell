# Changelog

All notable changes to this skill are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-10-25

### Changed
- Version declaration unified to 1.2.0 across the repository: `__version__`
  in `scripts/__init__.py` now matches `manifest.json` and the `SKILL.md`
  frontmatter (previously 0.0.0). No capability change.

## [0.0.0] - 2026-10-18

**Experimental packaging release.** This first public build ships the
video-tracker as a *preliminary / unstable* tool, intentionally versioned
`0.0.0` to signal that the interface and outputs are not yet stable. It
contains the same pipeline as the 1.0.0 feature baseline (probe ->
track -> fft -> report, plus the `physics` consistency probes); nothing
about the tracking behavior changes between 1.0.0 and 0.0.0 — the
version is reset to 0.0.0 solely to mark the skill as experimental.
Verify every output against a known reference before relying on it.

### Changed

- Version set to `0.0.0` (experimental / unstable). The feature set is
  carried over from the 1.0.0 baseline unchanged; this is a status
  marker, not a feature or regression.

## [1.0.0] - 2026-10-15

First public release of the skill. It ships the baseline pipeline for a
physics-experiment video (probe -> track -> fft -> report), plus the
robustness pass landed in this round. This release is marked
**experimental / unstable**: the tracker is target-specific and the
end-to-end error is not yet bounded, so every result should be verified
against a known reference.

### Added

- `frame_range` config key: `track` now accepts an optional
  `[start, end]` event window. The reader seeks to `start` and tracks
  through `end` (inclusive), so a 1080p multi-minute video can be reduced
  to a few-seconds sub-window in a handful of seconds. Frame numbers stay
  source-absolute; the time axis is shifted so `time_s = 0` at the window
  start. Omit the key to track the whole file (unchanged default).
- Real-video validation: a slow-motion falling-page experiment
  (`test.mp4`) drives the full probe / track / fft / report pipeline to
  confirm deterministic outputs on a genuine file.
- `physics` subcommand + `scripts/physics.py`: an optional, numpy-only
  physics-consistency check that judges whether a tracked trajectory obeys
  Newtonian laws (no OpenCV / matplotlib / torch). Three probes:
  * **Teleport / smoothness** — a robust MAD 2nd-difference test that flags
    single-frame speed jumps from silent object swaps or recording gaps.
  * **Conservation** — the motion's invariant is measured on the
    model-fitted trajectory (so pixel noise does not fake a violation):
    kinetic energy for constant-speed, simple-harmonic energy for
    oscillators, radial linearity for a spiral, decay linearity for a
    damped oscillator.
  * **Equation-of-motion fit** — the design model (sinusoid / damped
    sinusoid / polynomial / spiral) is fitted and reported as a
    *dynamical score* in [0, 1].
  The step re-uses the CSV/JSON that `track` already writes (no reference
  video required) and emits `<video>_physics.json`; an optional
  `--reference-csv` adds per-object deltas against a ground-truth track.
  A `--per-object` JSON flag lets multi-object videos give each body its
  own `{"family", "fx", "fy", "center"}`, overriding the global
  `--family` / `--fx` / `--fy` / `--cx` / `--cy` when bodies follow
  different laws.

### Changed

- Positioning is "experimental / unstable": the shipped skill is a
  preliminary tool. Documentation (SKILL.md, README, README_zh) now
  carries an explicit unstable status banner, and the Limitations sections
  lead with target-specific, several-pixel tracking error. The
  `references/` directory (upstream provenance scripts and tuning notes)
  was removed from the shipped tree; the skill is self-contained.

### Fixed

- `report.py` Objects / FFT sections: flattened the per-object table rows
  so Markdown tables render correctly instead of collapsing to a
  character-by-character layout when a data row outlived the header.
- OpenCV 5.0 `init()` compatibility: an out-of-bounds ROI now raises
  `TrackingError` reliably; a `w` / `h` larger than the frame at the
  origin is tolerated by the C++ layer and no longer mis-reported.
- `test_run_cli.py`: removed a duplicated `test_no_args_prints_help`
  definition so the documented test count matches the executed suite.
