# Token budget

What an installed Chelate Shell costs in context, measured rather than
estimated, and what this release changed about it.

A skill is paid for twice. Its `description` is read by the router in every
session, whether the skill is used or not; its `SKILL.md` body enters the
context when the skill is invoked. The documents are a third cost, paid when
an agent reads them. None of that is visible in a test run, which is why the
numbers below are printed from the tree rather than guessed.

## Measured on 2026-11-18

Token figures are `characters / 4` (English-heavy text, no tokenizer in the
standard library). The method is one pass over `skills/*/SKILL.md`: fold the
frontmatter `description`, count it, count the file.

| Surface | Before | After |
|---|---|---|
| Skill descriptions, every session | 24 skills, 5,966 chars ≈ 1,480 tok | 25 skills, 2,554 chars ≈ 638 tok |
| One `SKILL.md` body (16 tiered skills) | 41,517 chars ≈ 10,380 tok | 21,756 chars ≈ 5,440 tok (−48%; avg 340 tok each) |
| One `SKILL.md` body (8 legacy skills) | — | unchanged, byte-frozen by `test_capability_guard` |
| `pipeline --mode a` decision record | ≈ 700 tok of JSON | ≈ 40 tok with `--summary` |
| `README.md` / `ORCHESTRATOR.md` / `docs/REFERENCE.md` | 7,100 / 4,240 / 2,560 tok | unchanged |

The body and document figures are not small — they are just not paid on every
turn. A session that installs the plugin and never calls a skill now costs
about 640 tokens for the routing layer, plus whatever the host adds for its
own tools.

## What changed

- **Descriptions are capped.** Every SKILL.md description is one sentence
  plus its trigger, ≤ 120 characters, and `python cli.py skill lint` fails
  above that. The cap exists because the cost of a long description is paid
  by every user on every turn, and a number nobody enforces drifts.
  `task-organizer` is the one documented exception (420), because its own
  suite pins the phrases that make the folder trigger fire; the exception is
  listed in `core/skillkit.py` rather than hidden in the test.
- **Bodies are tiered.** Sixteen skills keep the executable instruction, the
  verdict table and the use / do-not-use boundary in `SKILL.md`; actions,
  outputs, failure handling, limits and the shared delivery rules moved to
  `skills/<name>/references/<name>-reference.md`, which is read only when
  asked. Content was moved, not deleted — the reference file is one link away
  and `skill lint` fails on a broken or orphaned reference.
- **`pipeline --summary`.** The router already prints one line per skill; this
  flag drops the full JSON decision record from stdout and prints a tally
  instead. The record still exists — it is the same dict written to
  `process/reports/` and `_broadcast/` — it is simply not read back into an
  agent's context to be paraphrased.
- **Nothing was removed.** Every skill, gate, flag and recorded field is still
  there. Compression applied to layout and wording, never to capability.

## What was not changed, and why

The eight legacy skills (the `LEGACY_SKILLS` list: task-organizer,
document-evolution-tracker, video-tracker, formula-validator,
conflict-detector, fulltext-extractor, literature-retriever,
bibtex-normalizer) keep their bodies byte-identical to the v1.0.0 source;
`tests/test_capability_guard.py` exists to prove exactly that, so the tiering
was applied to the other sixteen. Their descriptions — the part paid every
session — were compressed like the rest, apart from `task-organizer`, whose
routing phrases are pinned by its own suite and which is the one documented
exception in `core/skillkit.py`.

The three long documents stay as they are: they are read on purpose, not on
every turn.

## Guidance for adding a skill

- The description answers "when does this fire" in one sentence. Details
  belong in the body.
- Put the executable instruction first (`## Quick Execution`), reference
  material after it. An agent that stops reading early should still have been
  told what to run.
- `skill lint` is the check; it runs in CI.

## Prior art

The form of this work was informed by two public sources, neither of which
contributed text, code or fixtures to this repository:

- SkillReducer (Gao et al., arXiv:2603.29919) — an empirical study of skill
  bloat and a two-stage method for compressing routing descriptions and
  restructuring bodies behind progressive disclosure. Its measurements are
  its own; the figures in the table above were taken from this tree.
- Anthropic, *Effective context engineering for AI agents* — the framing of a
  finite attention budget and the case for loading context just in time.

The cap, the summary flag and this page were written here; if they disagree
with either source, this tree is the one that is wrong about itself.
