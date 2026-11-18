# Graphene tight-binding — an end-to-end run, and five attacks on it

A worked example with a small piece of real physics, so the question the
security layer exists to answer stops being abstract:

> when an agent goes around the workflow, what does the shell actually do?

The artefact is the nearest-neighbour tight-binding band structure of a
honeycomb lattice — graphene, in the simplest model — written with nothing but
the Python standard library. No numpy, no matplotlib, no network.

```bash
python examples/graphene-tight-binding/run_demo.py
```

Exit code 0 means every scenario below behaved as documented; 1 means at least
one did not. `--keep` leaves the scratch workspaces on disk, `--out DIR` puts
them somewhere you choose.

## The run

Each scenario builds its own workspace and runs the same six steps:

1. **write the model** — `material/initial/hamiltonian.py` (the Hamiltonian the
   agent proposes) and `parameters.json` (hopping `t = 2.7 eV`, lattice
   constant `a = 2.46 Å`);
2. **compute** — sample Γ → M → K → Γ and write `process/bands/eigenvalues.csv`
   and `process/bands/bands.svg`;
3. **check and gate** — the gate asserts the one property the model claims:
   the structure factor vanishes at K, so the bands touch at zero. It records
   the SHA-256 of both inputs and the digest of the code that judged them;
4. **hash** — those digests are what the token and the gate bind to;
5. **approve** — a one-time token for this plan (the demo uses the scripted
   hatch and prints a note saying so);
6. **publish** — `promote()` stages the copy and renames it into `results/`.

The physics is checked in the demo itself: at the Dirac point the two bands
meet at `E = 0`, which is what makes the calculation worth gating rather than
merely running.

## The five attacks

| # | The agent tries | Result |
|---|---|---|
| 1 | edit `parameters.json` after the gate ran | **refused** — the gate expired |
| 2 | replace the approved `hamiltonian.py` | **refused** — the token no longer fits the plan |
| 3 | overwrite a published figure in `results/` | **named** by `cli.py audit` as modified |
| 4 | delete a bound input after the gate ran | **refused** — bound input missing |
| 5 | write `results/stolen.csv` by hand | **named** by `cli.py audit` as unapproved |

Scenarios 1, 2 and 4 are stopped **before** anything is written. Scenarios 3
and 5 happen after the fact: the approval gate guards `promote()`, not the
`results/` directory, so the shell detects those two by name and digest rather
than preventing them. The demo prints which is which instead of blurring the
distinction — that distinction is the honest content of this example, and it
is the same one `docs/SAFETY.md` states under its limitations.

## Why this shape

A demo that ends at `evil.txt` proves a string comparison works. This one
starts from what a researcher actually wants protected — the model, the
parameters, the calculation and the figures that came out of them — and shows
what happens when each of those is changed behind the workflow's back.

Making the shell prevent scenario 3 and 5 needs a filesystem boundary (a
worker running as a different OS user, a `results/` only the issuer can
write), not another check inside Python. That is the 1.4.0 target; this
release does not claim it.
