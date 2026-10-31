# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-10-25

### Changed
- Version declaration unified to 1.2.0 across the repository: `__version__`
  in `scripts/__init__.py` now matches `manifest.json` and the `SKILL.md`
  frontmatter (previously 1.0.1). No capability change.

## [1.0.1] - 2026-10-16

Patch release: no functional change to the checker. This revision ships the
documentation and install section rewritten to the repository's standard
template (bilingual README, unified four-method install section, per-skill
security disclosure) so the skill can be re-published consistently.

### Changed

- **README rewritten (EN + ZH).** Fully reworked to the repository's
  standard template: bilingual nav line, a compact design-principles /
  core-features block, a unified "Download and install" section, and a
  per-skill security disclosure example in the "Report issues" block.
- **Installation streamlined to four standard methods.** The install
  section now documents exactly four routes in one consistent style:
  the cross-platform installer binary, the source archive, Agent
  self-fetch, and `git clone`.

## [1.0.0] - 2026-10-14

The first release of the formula-validator skill. It exists to answer one
question deterministically: **is this formula right?** The language model
extracts the formula and reads the report; every verdict below it comes from
SymPy and NumPy, never from the model's own arithmetic.

### Added

- **Five deterministic CAS checks (D1-D5)**: parse, dimensional analysis,
  limit-case enumeration, 10,000-sample numerical comparison, and symbolic
  identity proof. The order is chosen so the cheapest and most decisive
  check runs first and dimension gates the rest.
- **Tri-state verdicts.** `pass`, `fail`, and `unknown` are all first-class
  outputs. Abstention is never softened into a pass, and a check that could
  not run is reported with its reason.
- **Physics-friendly parsing namespace.** `E`, `N`, `S`, `Q`, `O`, `beta`,
  `gamma`, `zeta`, `Lambda`, `Xi` are forced to plain symbols so SymPy does
  not read the `E` in `E = m*c**2` as Euler's number; `gamma(x)` still
  reaches the function. `--symbols I` forces `I` to a symbol.
- **LaTeX input**: `\frac`, `\sqrt`, `\partial`, `\dagger`, `pmatrix`,
  implicit multiplication, and `\sin^2\theta` correctly parsed as
  `(sin theta)**2`.
- **Automatic singularity enumeration.** `solve(denominator, x)` finds the
  poles without the user naming them, and each side's behaviour is compared
  there. Limit checking is *comparative*: both sides diverging with a ratio
  tending to 1 is a property, not an error.
- **Multi-step derivation breakpoint location.** A chain of steps is
  compared pairwise; the first break is named, and the cause is classified
  as `dimension_break`, `constant_factor`, or `structural`.
- **High-precision arbitration.** A float64 disagreement is only a
  suspicion: near a root, cancellation alone can separate two equal sides by
  many ulps. 40-digit arithmetic at the worst point gets the last word, and
  noise is reported as noise rather than as an algebraic error.
- **Definition detection.** When one side is a bare symbol the input reads as
  a definition, not an identity, so sampling it would manufacture a false
  failure. Only the dimensional check runs, and the reason is stated.
- **Conflict verdict.** Dimensions disagree while the numbers agree almost
  always means a wrong *unit declaration*, so it is surfaced as its own
  state rather than folded into `fail`.
- **Matrix property checks**: hermitian, unitary, anti-hermitian, orthogonal,
  symmetric, traceless, unit-modulus determinant, idempotent, real
  eigenvalues - reported through both a symbolic and a numeric channel.
- **Zero-dependency MCP Server** (stdio JSON-RPC 2.0, protocol
  `2024-11-05`, four tools) implemented natively, with no `mcp` package to
  install.
- **Compact output by design.** The compact JSON summary is what enters the
  context window; the full Markdown report goes to disk. `derive` reports
  only the first break plus one summary line, so the verification cost is
  **O(1)** in the length of the derivation, not O(n).
- **A standalone guarantee.** The skill depends on nothing but the local CAS
  libraries. A contributing invariant and a documentation contract test fail
  the suite if any shipped document names another skill or advertises an
  integration with one, so a dependency on work that does not exist cannot
  be reintroduced quietly.
- **Bare-subscript summation is rejected.** `sum_i F_ij` is no longer silently
  mis-read through the LaTeX fallback as `s*u*m_i*F_i*j`. The parser raises
  `ParseError` and points at the SymPy-native `Sum(f(i), (i, 1, N))`.
- **`check --expect-zero` decides "the expression is zero".** The symbolic
  prover runs on `expr == 0`: `sin(x)**2 + cos(x)**2 - 1` returns `pass`, a
  genuine non-identity returns `fail`, and an expression the simplifier cannot
  close abstains (`unknown`) rather than guessing.
- **Each run writes its own report file.** Reports are named
  `<mode>-<hash>-<timestamp>.md`, so a batch keeps every formula's detail;
  `_reports/latest.md` points only at the most recent run.
- **`--json-pretty`** indents the compact JSON summary for a narrow terminal
  instead of wrapping as one line.

### Hardening

Hardening found by adversarial debug and review rounds before the release;
the regression tests that pin each item below ship in 1.0.0:

- **SciPy stays off the common path.** A cold SciPy import costs 200-550 ms,
  so `_compile` tries NumPy first and reaches SciPy only for the functions
  NumPy genuinely lacks (`erf`, `gamma`, `besselj`, `zeta`); behaviour for
  those functions is unchanged, only the import is deferred. Internal time
  for the canonical failing case is 335 ms.
- **Every compiled evaluator is probed before it is trusted.** `lambdify`
  resolves names it cannot translate *at call time*, not at compile time:
  `erf` under `["numpy"]` returns a function built on scalar `math.erf` that
  only raises `TypeError` when handed an array. A candidate module set is
  therefore accepted only after one cheap evaluation succeeds.
- **Report tables carry one status word per cell.** Every stage state has a
  marker, so no cell can render as `skipped skipped`; a regression test
  forbids the bare fallback.
- **The second canonical case's limit ratio is documented correctly.** At
  `x -> 1` both sides of `1/(1-x**2) = 1/(1-x)` diverge with a ratio tending
  to 0.5; the example file states this and notes that checking only
  `x -> 0` and `x -> +-inf` misses both poles.
- **Limit evaluation no longer hangs on periodic expressions.** `sp.limit` is
  now called on a simplified form, which closes the SymPy loop that
  `sin(x)**2 + cos(x)**2 - 1` at `x -> 0` triggered inside `igcd`/series
  expansion.

- **Test suite expanded to 246 cases (84% line coverage).** In-process unit tests for the CLI, the five core engines, the LaTeX fallback, and report rendering now exercise every branch the subprocess CLI tests could not reach: the numeric-probe fallback, the limit comparative / divergent-ratio paths, the symbolic verdict tri-state, and the matrix zero-test path. `mpmath` is now declared explicitly in `requirements.txt` (it was only a transitive SymPy dependency before).

### Not claimed

- Numerical agreement is evidence, not proof. Regions that were never
  sampled may still be wrong.
- Without declared units the dimensional check abstains rather than guesses.
  A wrong guess that produces a false error is worse than admitting
  ignorance.
- Symbolic proof is bounded by expression size; `unresolved` reports the
  simplifier's limit, not a defect in the formula.
- LaTeX `\int`, `\sum`, `\prod` need an unambiguous body; otherwise SymPy
  syntax is the better route.
- Whether the skill loads at all depends on the agent recognising the
  situation from the description line before `SKILL.md` is ever read. That
  decision is outside this repository's control.
