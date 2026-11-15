/**
 * Legacy DeepSeek Harness entry (`.dsh-plugin/plugin.json` -> `main`).
 *
 * The real adapter lives at the package root so that `cordis.patch.yml` and
 * this descriptor resolve to one implementation instead of two stubs.
 */
export { apply, inject, name } from '../index.js'
