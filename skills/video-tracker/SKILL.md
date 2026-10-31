---
name: video-tracker
description: Experimental tool for extracting motion data from physics videos. Uses OpenCV to output standardized trajectories, JSON summaries, and FFT frequency spectra.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.2.0
  entry_point: python run.py
  python_requires: '>=3.10'
version: 1.2.0
---




# video-tracker







> **Status: experimental / unstable.** The tracker works well on clean,



> single-object footage but degrades on heavily occluded, deformable, or



> fast targets. Error is target-specific — treat every run as



> preliminary and verify against a known reference before trusting the



> numbers.







A self-contained skill that turns an experiment video into reproducible



physics data:







- **Video tracking** — pluggable backend per declared object (`auto` CSRT



  with automatic `cv2.matchTemplate` fallback on OpenCV 5.x, or `template`),



  with an optional template-matching re-acquire when the tracker loses the



  target, plus sub-pixel refinement and an optical-flow fallback



  (brief occlusion, reflective shells, flipped covers).



- **FFT analysis** — amplitude spectrum of the tracked coordinate series;



  dominant peak, period, and top-N resonances; PNG figure.



- **Standardized output** — `frame, time_s, x_px, y_px, confidence` CSV plus



  a JSON summary (FPS, total frames, lost-frame lists, success rate, and cm



  units when a scale is declared).



- **Batch mode** — process several videos sequentially and roll up into one



  batch JSON.







> The skill is deterministic: same video + same config → same outputs. It



> never modifies the raw video file.







## MANDATORY WORKFLOW


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Required (video steps)**: `numpy`, `opencv-contrib-python-headless`.
- **Optional**: `matplotlib` (PNG spectrum / trajectory figures),
  `PyYAML` (YAML configs; JSON works with the standard library alone).

If a required dep is missing, the video steps will not run. **Do not
install automatically.** Tell the user which package is missing and ask
whether to `python -m pip install numpy opencv-contrib-python-headless`
(or `pip install -r requirements.txt`); install only after they confirm.
Prefer a project-local venv. OpenCV-dependent tests skip cleanly when the
full stack is absent; the FFT / CSV / JSON / report paths are pure numpy.







When the user asks to extract motion data from an experiment video, follow



these steps in order.







1. **Confirm inputs.** Verify a video path, the FPS, and the ROI(s) for the



   target object(s) are known. If the user has not declared ROIs, ask —



   the tracker cannot guess where the target is in the first frame.



2. **Load the config.** `config.yaml` (or a JSON equivalent) declares



   `videos`, `objects` (one ROI per object), `fps`, optional



   `scale_cm_per_px`, the CSRT `params` block, and the `tracker_type` /



   `subpixel` / `use_optical_flow_fallback` / `max_dim` / `frame_step`



   knobs. YAML requires PyYAML;



   JSON works with the standard library alone.



3. **Probe before tracking.** Run `python scripts/run.py probe --config cfg`



   to print container metadata (FPS, frame count, resolution). Confirm the



   video is readable and the resolution is workable (trackers are not GPU-



   accelerated; 720p and below are recommended, or set `max_dim`).



4. **Narrow to the event window (when applicable).** For long or



   multi-event videos, the whole file is rarely the part that matters — a



   slow-motion falling page, a pendulum swing, or a projectile pass usually



   occupies a few-seconds sub-window. Track that window, not the whole file:



   - The config supports a `frame_range: [start, end]` list that limits



     tracking to `[start, end]` (inclusive). When set, the CSV time axis



     is shifted so `time_s` starts at `start/fps` instead of 0.



   - For experiments with a physical marker (e.g., a known cm ruler in



     the frame), also declare `scale_cm_per_px` here so the output



     positions carry a cm column.



   - If no event window is declared, the full video is tracked (the



     default) and you should expect a runtime proportional to



     `n_frames × resolution` — at 1080p × 60 fps × 4000+ frames this



     takes 10+ minutes and is usually the wrong granularity anyway.



5. **Track.** Run `python scripts/run.py track --config cfg`. For every



   frame in scope, each object's tracker is updated; on a loss the



   optional template-matching re-acquire fires, and if that fails an



   optical-flow estimate advances the last known centre. Outputs:



   `<video>_tracking.csv`, `<video>_summary.json` under the `output/`



   directory. The raw video is never modified.



6. **Spectrum.** Run `python scripts/run.py fft --config cfg` to compute the



   FFT amplitude spectrum of each object's x/y series and write



   `<video>_fft.json` + `<video>_spectra.png` (schematics, not data).



7. **Report.** Run `python scripts/run.py report --config cfg` to produce a



   Markdown report combining the tracking summary and spectral findings.



8. **Physics consistency (optional).** Run



   `python scripts/run.py physics --config cfg --family <fam>` to judge



   whether the track obeys Newtonian laws (teleport / conservation /



   equation-of-motion probes) and write `<video>_physics.json`. Pure numpy,



   re-uses the CSV/JSON from step 5; no reference video is needed.



9. **Recover / re-tune.** If tracking quality is poor, adjust `params`



   (lower `psr_threshold`, raise `patch_ratio`) and re-run. The output



   directory is additive: old files are not deleted unless you ask for



   `--force`.







## Hard constraints







- **Never modify the raw video.** All outputs land under `output/`; the



  source file is opened read-only.



- **No interactive input.** Every parameter (ROI, FPS, scale, params) comes



  from the config. There is no `selectROI`, no `input()`, no `imshow`.



- **Deterministic.** Same video + same config → identical CSV/JSON bytes



  (the PNG spectra layout is stable, but the figure itself is a schematic,



  not a data source).



- **Trackers are CPU-only.** No GPU acceleration is available in the Python



  bindings; keep the resolution modest, or set `max_dim` to auto-downscale



  large frames for speed.







## Plugin contract







The skill exposes a single CLI entry point (`scripts/run.py`) with



subcommands. Exit codes:







- `0` — success.



- `2` — usage / config / tracking error (clear message on stderr).



- `3` — internal error (bug in the skill itself).







## Output products







```



output/



  <video>_tracking.csv      # frame, time_s, x_px, y_px, confidence, reinit



                           # (+ x_cm, y_cm when scale_cm_per_px is set)



  <video>_summary.json      # video, fps, n_frames, objects (success_rate,



                           # lost_frames, reinit_frames), scale



  <video>_fft.json          # per-signal spectrum: dominant freq, period, top-N



  <video>_spectra.png       # amplitude-spectrum + trajectory figure (matplotlib)



  <video>_report.md         # Markdown combining summary + FFT findings



  <video>_physics.json      # per-object physics-consistency probes (optional)



  batch_summary.json        # roll-up when processing multiple videos



```







## Limitations







- **Unstable / experimental.** This skill is shipped as a preliminary



  tool, not a tuned production tracker. End-to-end tracking error is



  target-specific and can be several pixels (observed ~2–5 px RMSE on a



  clean synthetic benchmark, much larger on cluttered footage); the



  template re-acquire and the FFT stage both have their own failure



  modes. Verify every result against a known reference before relying on



  it, and do not cite numbers without that check.



- **CSRT accuracy is target-specific.** It excels on a single, roughly



  constant-sized object per camera. Heavily occluded or deformable targets



  may still drop out even with the template re-acquire fallback.



- **Sub-pixel and optical-flow support.** Optional sub-pixel centroid



  refinement (`subpixel`) produces fractional-pixel centres; on a tracker



  loss the optical-flow fallback (`use_optical_flow_fallback`) advances the



  last known centre instead of freezing. The position only freezes



  (`confidence = 0`) when both re-acquire and flow fail. FFT resolution is



  bounded by the video length.



- **CPU-bound.** A 1080p 60 fps video with 2 objects may take several



  minutes to process.



- **YAML configs need PyYAML.** JSON configs work with the standard library



  alone; OpenCV is required for the video steps but not for the FFT math.







## Failure handling







- A missing / unreadable video raises a clear `VideoError` (exit 2).



- An ROI that lies outside the first frame is detected at init and fails



  fast (`TrackingError`).



- A per-object tracker loss during the run is **recorded, not fatal**: the



  position freezes and the frame is flagged in `lost_frames`. The sweep



  continues to the next object / next video.



- A failed template-match re-acquire is recorded as `reinit = False` and



  the confidence drops to 0; the next frame retries.






