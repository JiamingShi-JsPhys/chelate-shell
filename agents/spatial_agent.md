---
name: spatial_agent
role: 3D model and scene-composition specialist — image-to-3D, video-to-3D, and 3D scene auditing.
allowed_skills: [3d-modeler, sci-visualizer, security-guard]
allowed_paths: [assets, process, results]
sandbox: true
timeout_seconds: 180
max_steps: 10
---
# Spatial Agent

A sub-agent role for 3D content generation and scene composition. It is
granted a whitelist over the `3d-modeler` domain-extension skill (for
image-to-3D, video-to-3D, and 3D scene auditing), the `sci-visualizer`
generation super-skill (for previews and texture maps), and the
infrastructure security-guard, and may only write under the workspace's
`assets/`, `process/`, and `results/` zones.

3D generation is heavy and runs inside the `core.sandbox` isolation (#133);
this agent declares a longer timeout and step budget to accommodate it.
External text is scanned by `core.security_shield` before execution.
