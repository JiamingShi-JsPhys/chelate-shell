---
name: formula-validator
description: Deterministic formula checker for physics and math. Runs five CAS layers (parse, dimension, limit, numeric, symbolic) to return a strict pass/fail/unknown verdict.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.1.3
  entry_point: python run.py
  python_requires: '>=3.10'
---




# formula-validator







Deterministic formula checker for physics and mathematics. You extract and



interpret; the tool computes. Five CAS checks run per request and return a



compact verdict with the failing point highlighted.







## When to use







- A formula, identity, or derived result appears and its correctness matters -



  whether the user asks for a check, states it confidently, or says it "looks



  wrong".



- A multi-step derivation must be checked line by line, or a wrong result



  needs the specific broken step located.



- A matrix from group theory or quantum mechanics must be confirmed Hermitian,



  unitary, traceless, and so on.



- A formula is about to feed a later step, so an error now propagates.



- The user asks for a dimensional check, a limiting-case check, or a numerical



  spot-check by name.







## When NOT to use







- Purely numeric evaluation with no symbolic claim (`compute 3.7**2`) - that is



  arithmetic, not verification.



- Prose, references, or literature search with no formula to check.



- Curve fitting or statistics on measured data - this tool checks algebra, not



  empirical models.



- Numerical simulation or ODE integration - use a solver, not a verifier.



- A formula the user merely wants typeset or rewritten, with no correctness



  question attached.







## Hard constraints







- **Never compute the algebra yourself.** Extraction and interpretation are



  yours; every computation runs through `scripts/cli.py` or the MCP tool. If a



  check did not run, say it did not run.



- **Never report a verdict the tool did not produce.** `unknown` is a valid



  result and must be passed through as `unknown`, not softened into a pass.



- **Never guess a unit silently.** Leave the symbol undeclared so the



  dimensional check abstains, or pass `--infer` and repeat the guessed units



  back to the user.



- **SymPy syntax is the preferred input.** LaTeX works, but SymPy syntax parses



  more reliably and avoids `\int`, `\sum`, and unmatched-brace failures.







## Execution steps


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Required**: `sympy`, `numpy`, `scipy`, `mpmath`.

If any are missing, the tool will not run. **Do not install automatically.**
Tell the user exactly which packages are missing and ask whether to
`python -m pip install sympy numpy scipy mpmath` (or `pip install -r
requirements.txt`); install only after they confirm. Prefer a project-local
venv over the global environment when one is available.







### 1. Extract the formula (your only computational job)







Turn the user's formula into an equation `lhs = rhs` in SymPy syntax. Map the



notation: `**` for powers, `sqrt()`, `exp()`, `log()`, `I` for the imaginary



unit, `Derivative(f(x), x)`, `Integral(f(x), (x, 0, oo))`,



`Matrix([[a, b], [c, d]])`, `Sum(f, (i, a, b))` for a bounded sum (write a



conditional sum such as `i != j` as "full sum minus the diagonal terms"), and



`D(f, x, n)` for an n-th derivative. Parse-error traps: bare `sum_i`



subscripts, `sum_(j!=i)` conditional notation, and mismatched-arity sums are



rejected, not guessed. Keep the original notation for the reply - step 5 needs



it.







### 2. Collect units







If the physical meanings are clear, declare them with repeatable



`--units NAME=UNIT`. Units are products with `*` and powers with `**`



(`kg*m/s**2`, `J`, `eV`, `T`); names resolve against SI



(`kg m s A K mol cd`, `N J W Pa C V F ohm Wb T H Hz eV`). If the meanings are



unclear, **leave them undeclared** - the dimensional check then abstains



instead of guessing. Only use `--infer` when asked, and repeat every inferred



unit back to the user. For a pure-mathematics identity, declare nothing.







### 3. Run the check







```bash



python scripts/cli.py validate --expr "sqrt(k/m) = omega" \



    --units k=kg/(s**2) --units m=kg



```







Add what the situation needs:







| Need | Flag |



|---|---|



| A suspected pole at `x = 1` | `--critical x=1` |



| A symbol that must stay positive | `--positive m,k` |



| `I` meaning current, not `sqrt(-1)` | `--symbols I` |



| Fewer or more samples | `--samples 20000` |



| A looser tolerance | `--tol 1e-6` |



| Skip the symbolic prover on huge input | `--no-symbolic` |







For a single expression with nothing to compare it to, use `check` instead of



`validate`. For a derivation chain, use `derive --steps-file <file>` (one step



per line). For matrices, use `matrix --matrix "Matrix([[...]])"`.







**Windows / PowerShell**: any argument containing `*`, `/`, `(`, or `,` must be



quoted as a whole, otherwise the shell mangles it. Correct:



`--units "m=kg" --units "a=m/s**2"`. Incorrect (bash-style, breaks on



Windows): `--units m=kg/s**2`.







### 4. Read the compact summary







The command prints one line of JSON; that summary is what belongs in your



context. The full Markdown report is written to `_reports/` - each run gets



its own file (`validate-<hash>-<timestamp>.md`) so batch checks do not



overwrite one another, and `_reports/latest.md` points at the most recent.



Open the report only when the verdict is not a clean pass. Pass



`--json-pretty` to indent the summary, or `--report PATH` to choose the file.







Exit codes: `0` pass, `1` fail/conflict, `2` unknown, `3` parse error,



`4` internal error. `unknown` means the decidable check was *abstained*, not



that no check ran - name in your report which check abstained. Never report



`unknown` as "no check ran".



### 5. Report back in the user's notation







State the verdict, then the single most actionable finding, translated back



into the user's own symbols. Lead with the error, not with the list of checks



that passed.







## Verification







Five deterministic checks run in order, cheapest and most decisive first:







| | Check | What a failure means |



|---|---|---|



| D1 | Parse | The input could not be read; we abstain rather than guess. |



| D2 | Dimension | The two sides carry different dimensions, or a sum adds unlike quantities. |



| D3 | Limit | The two sides behave differently as some variable runs to 0 or infinity. |



| D4 | Numeric | They disagree at random points; the worst point is reported. |



| D5 | Symbolic | `lhs - rhs` will not reduce to zero. |







Two safety behaviours you must not override:







- **D2 disagrees but D4 agrees** -> verdict `conflict`. Almost always the unit



  *declaration* is wrong, not the formula. Fix the units before touching the



  algebra.



- **D4 disagrees but 40-digit arithmetic agrees** -> reported as a pass with a



  floating-point note. Near a root, two correct forms can differ by many ulps;



  this is not an algebraic error.







## Failure handling







- **Exit 3 (parse error)** - retry in SymPy syntax. If it still fails, quote



  the parser's hint to the user; do not "fix" the formula by guessing what



  they meant.



- **Exit 2 (unknown)** - report it as unknown and name what was not checked.



  Add units, or restate the claim as an identity between two full expressions,



  to turn it into a decidable check.



- **Exit 4** - report the message verbatim and stop. Do not fall back to



  checking by hand.



- **Definition, not identity** - `E = m*c**2` has a bare symbol on one side,



  so numerical sampling would reject a correct formula. The tool detects this,



  checks dimensions only, and says so. To get the full check, compare two



  independent derivations of the same quantity, or state it as an identity



  between two full expressions (no bare symbol).



- **Residual expected to be zero** - when a single expression should reduce to



  zero (an equation-of-motion residual, a cycloid identity), run



  `check --expr "<residual>" --expect-zero`; the symbolic prover then tests



  `expr == 0` directly. A genuine identity returns `pass`; an expression zero



  only *conditional* on a solution is reported honestly as



  not-identically-zero.







## Requirements







`sympy`, `numpy`, `scipy` (see `requirements.txt`); the MCP server needs no



additional packages. On Windows, install into a project-local venv (do not



pollute the global environment):



`python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt`.






