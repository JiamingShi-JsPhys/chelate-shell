[chelate-shell](../README.md) · [简体中文](TESTING_zh.md)

# Testing

The root suite, the seven per-skill suites, and the two environments CI runs.

## Tests

```bash
python -m pytest tests/ -q
```

That is 394 tests. With the optional dependencies installed, **383 pass and 11 skip**: one needs a v1.0.0 source tree that is not shipped, one asserts POSIX file modes (Windows does not enforce them — it runs and passes on Linux), and nine are `no_stubs` exemptions for engine skills and restored legacy trees. On a machine with nothing but pytest, the dependency-gated cases skip instead: the tests that assert a real verdict carry a `requires()` marker, so the suite still passes — and what gets exercised there is the `UNVERIFIED` path a fresh user actually meets. CI runs both environments, on Python 3.10 and 3.12.

Each skill also keeps its own upstream suite under `skills/<skill>/tests/` — 918 tests across the seven skills that have one. They cannot share a pytest process (several define a top-level `tests` module, which is what `ImportPathMismatchError` was about), so CI runs one directory per process in a third job. The root suite covers the gate contract, manifest schema validation, flat-layout enforcement (a manifest must sit exactly one level under `skills/`), pipeline planning and FAIL termination, the migration guard, the legacy D1–D5 and FFT/physics probes, the five skills added in v1.1.x, workspace input-path resolution, `--inputs` auto-wiring, the unified debug layer, the manifest-contract suite (plugin manifests for all four host platforms, plus SKILL.md frontmatter agreement), the rule-file adapters for the plugin-less hosts, the security shield, the four heavy engine skills' real logic and `UNVERIFIED` degradation, and the repo-consistency guard: every skill's docs, manifest, entrypoint, `LICENSE` and declared dependencies stay in agreement.
