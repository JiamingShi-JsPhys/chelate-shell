---
name: task-organizer
description: The mandatory entry point for complex tasks. Initializes the standard three-tier workspace, enforces verification loops with automatic rollback, and maintains a broadcast index for context compression.
metadata:
  author: Jiaming Shi
  license: MIT
  version: 1.0.1
  entry_point: python -m scripts.run
  python_requires: '>=3.9'
---



# task-organizer







Task organizer for task folders: builds the standard three-tier structure



(`material/initial` + `material/downloaded` + `process/` + `results/` +



`_broadcast/`), files every deliverable by provenance, verifies each run



(8 checks, auto-rollback on failure), and maintains a read-only broadcast



index (`_broadcast/INDEX.md`) so a later session reads the index first and



opens only the originals it needs.







## MANDATORY WORKFLOW - what you do when this skill triggers


## Dependency bootstrap (run on first use)

Before the first run, probe the runtime deps for this skill:

- **Core**: pure standard library — no install required.
- **Optional**: `openpyxl` (Excel index) and `PyYAML` (YAML rule files).

If an optional dep is missing, the feature degrades (e.g. index falls back
to markdown, YAML rules unavailable) rather than failing. Do **not**
install automatically. Tell the user which optional dep is absent and ask
whether to `pip install openpyxl` / `pip install pyyaml` (or run
`python -m pip install -r requirements.txt`); install only after they say
yes. Never install into the global environment without explicit consent —
prefer a project venv when one exists.







**This skill is an instruction to ACT, not a document to summarize.** When



any trigger under "When to use" is met, you MUST run the tool and report



what it did; answering with a description of this skill - its features,



command list, architecture - is a **failure mode**, not a result.



**Scope:** fires only when the user has chosen a workspace (a task /



project / research folder); with no chosen workspace, do not organize.







1. **Session-start structure check, then the folder-signal gate.**



   **Run the structure check first - it is read-only and always safe.** As



   soon as the workspace folder is known, run `doctor <root>`: one stat



   pass, nothing written or moved, so it runs **before** any confirmation.



   Healthy (structure present) -> carry on, skip the rest of this step.



   **Structure missing -> apply the gate:**



   - Explicit organize / setup request, or the compound "produce an



     artifact AND keep the folder tidy" (see "Content-production



     scenarios") -> already an explicit organize intent: run `init <root>`



     now, no proposal needed.



   - Folder merely **attached, referenced, or named** and a task starts on



     it -> **PROPOSE one init** and stop: *"I see you are working in



     `<folder>`; want me to set up the standard three-tier structure before we start?"*



     Do **not** run any command



     until the user confirms - `init` moves existing content into



     `material/initial/`, a layout change the user must agree to first. If



     the user declines, carry on as asked and do not re-propose:



     at most once per folder.



2. **Resolve the target root path first.** Path named / referenced /



   obvious -> use it. **The user gave no path** ("set up a task



   workspace") -> **ask for it**, and propose a concrete default so the



   user only has to say yes (e.g. `~/Desktop/<task-name>`). Never guess a



   location silently; never abandon the task over a missing path.



3. **Pick the entry point.** New / empty folder, "set up a workspace", or



   the compound "produce + keep tidy" -> `init` first: **`init` is the



   task-start command - it builds EVERY structural folder immediately**



   (`material/initial/`, `material/downloaded/`, `process/`, `results/`



   **and `_broadcast/`**) and lifts pre-existing content into



   `material/initial/` as user material (cheap: no snapshot, no verify).



   Existing folder with content -> `organize` (default `--mode full`).



   Ambiguous -> ask one short question; if the folder exists, default to



   `organize`.



4. **RUN the tool via Bash**, from this skill's own directory:



   ```bash



   cd <directory containing this SKILL.md>



   python -m scripts.run init     <root>



   python -m scripts.run organize <root>



   ```



   Python 3.10+, standard library only (`openpyxl` merely adds the xlsx



   index).



5. **Verify, then report.** Success looks like `organize: done` +



   `verification: passed`. `verification: failed` means the tool already



   rolled itself back to the before-state - report that, do not blindly



   re-run. Report the three-tier tree, the user's material in



   `material/initial/` untouched, the verdict, and that the run reverses



   with `undo` (`process/history/`).



6. **Declare provenance as you go.** After every file you fetch into the



   task folder, run immediately:



   ```bash



   python -m scripts.run mark-downloaded <root> <file> --url <source-url>



   ```



   That keeps `material/downloaded/` meaning "files the assistant



   fetched", not a guess from the filename.



7. **Final delivery - organize, then build the broadcast index



   (mandatory).** Before handing the final answer back in a workspace



   task, run the pipeline once more so the deliverable files correctly (a



   name containing `final` / `deliverable` / `report` / `review` /



   `summary` lands in `results/`), then rebuild the index:



   ```bash



   python -m scripts.run organize <root>



   python -m scripts.run broadcast <root>



   ```



   The broadcast index is **mandatory for a workspace task**, not



   optional: it lets the next session - and a long conversation - jump to



   the right file instead of re-reading every original.







## When to use







**Always-on (no separate trigger).** Part of the normal task rhythm, not



an optional feature, so they cannot be missed by the match:







- **At session start (the structure check).** Run `doctor <root>` first:



  a **read-only, zero-cost** scan (nothing read, moved or written).



  `incomplete` -> run `init` before any content work; `healthy` ->



  continue untouched. The check is idempotent - on an already-tidy folder



  it costs one stat pass and changes nothing.



- **At task start**, `init` builds every structural folder up front



  (`material/initial`, `material/downloaded`, `process/`, `results/`,



  `_broadcast/`) - no folder is missing when the work begins.



- **At final delivery**, `organize` files the finished work into



  `results/` and `broadcast` rebuilds the read-only digest - mandatory



  for any task with a workspace folder.







**Matched triggers (these fire on their own signals).**







- **Content production.** The user reads files in a task folder and



  writes something from them - a report, a feasibility study, a review, a



  summary, notes, an article, an abstract - and the artifact lands in that



  folder. The trigger does not depend on the task being multi-step or on



  the deliverable's name: producing any deliverable inside a task folder



  fires it even for a single, one-shot write, even if the word "organize"



  is never spoken and the request looks like a pure writing task (see



  "Content-production scenarios"). **It is a hard constraint:** writing



  the artifact and maintaining the folder structure are one combined



  action - whenever you produce a deliverable in the folder you MUST also



  run the bookend loop (`init` at start, `organize` + `broadcast` before



  the final answer). Leaving the folder loose after a write is a



  failure, not a shortcut.



- **Folder signal.** A folder is attached, referenced, or named and the



  user starts a task on it without asking to organize: PROPOSES one



  `init` first, runs only after confirmation (the gate above).







Just chatting with no workspace folder -> the skill does not apply.



"List folder contents" / "rename a single file" -> out of scope.







## Content-production scenarios (writing an article / review / report in a task folder)







"Write a review of X" / "draft a report" / "summarise these transcripts"



**inside a task folder** is this skill's territory: the trigger is the



*combination* of producing an artifact **and** a task folder to keep tidy.







**This is a hard constraint, not a suggestion.** If you produce ANY



deliverable (report, review, article, abstract, proposal, table, or any



other finished document) **inside a task folder**, you MUST also run the



full bookend loop on that same folder - `init` at task start,



`organize` + `broadcast` before the final answer. **Not skippable, not



deferrable, not optional:** writing the file and keeping the folder in



the standard layout happen together, every time, with no separate



"please organize" request. Answering the write while leaving the folder



loose - or filing the deliverable by hand - is a **failure mode**, not a



shortcut. A one-shot write still requires the bookend loop: the trigger



is a workspace folder plus a deliverable, not the number of steps.







Run in this order, no step skipped:







1. **Set up first.** New folder or no three-tier structure yet -> run



   `init <root>` **before writing anything**: the compound request already



   carries the "keep tidy" intent, so this runs directly with



   no folder-signal proposal. `init` registers everything already present



   as user material, protecting the user's inputs from the start.



2. **Produce the artifact.** Write it into the task folder (any location;



   `organize` will file it).



3. **Declare provenance as you go.** Files **you** fetched ->



   `mark-downloaded` (with the source URL); files the **user** placed ->



   already registered by `init`, or `mark-user`.



4. **Name the deliverable so it is recognisable.** Names containing



   `final` / `deliverable` / `report` / `review` / `summary` file under



   `results/` automatically; when in doubt rename to `final_<name>`.



5. **Run `organize <root>`** and report the verified result.



6. **Build the broadcast index.** Run `broadcast <root>` so



   `_broadcast/INDEX.md` + `index.json` summarise every file; a later



   session reads the index first and opens only what it needs.







**Re-filing rule.** If a blind first `organize` dumped files into



`process/` before anything was declared, declaring them afterwards



(`mark-user` / `mark-downloaded`) **and re-running `organize`** moves them



home. Undeclared files stay in `process/` - that keeps re-runs idempotent.







## Broadcast center (`_broadcast/`) - the context-compression index







A folder can hold more documents than a session can afford to read. The



broadcast center is a **read-only digest** of every supported file, small



enough to always read first, rich enough to know what to open next; it is



a standalone command that works on **any** folder:







```bash



cd <directory containing this SKILL.md>



python -m scripts.run broadcast <root> [--ai] [--max-files N] [--keywords K]



```







It writes - and only writes - `<root>/_broadcast/INDEX.md` (one line per



file: path, type, size, date, one-sentence summary, keywords) and



`index.json` (same data, machine-readable). Supported: `txt` / `md` /



`csv` / `json` / `docx` / `pdf` / `pptx` / `xlsx`; everything else is



listed "Skipped", never touched. Summaries: `--ai` (or `TASK_ORG_AI=1`



plus a key) lets the model write them; the default local mode is the



first 200 characters plus statistical keywords - offline, deterministic,



free. Guarantees: **read-only** - originals are opened for reading only;



nothing is moved, renamed or modified.



The only writes are the two files in `_broadcast/`.



**Idempotent** - re-running regenerates both index files in place.



**Bounded** - per-file caps, `--max-files`, an over-sized index warns but



never fails. **Protected** - `_broadcast` is tool-owned, so `init` /



`organize` never relocate it.







### READ-ORDER protocol (mandatory for any later session)







A session opening a folder with a `_broadcast/` index follows this exact



read order. The point is to save tokens: the index is the cheap layer,



the originals the expensive layer, and you open the expensive layer only



when a specific entry earns it.







1. **Read the directory first.** Open `_broadcast/INDEX.md`, read its



   **Directory** section (the keyword -> file map); do NOT read the



   per-file detail blocks yet. One read tells you what exists and where,



   without touching a single original.



2. **Resolve the task to keywords.** Pick the 1-3 topics that matter,



   look them up in the directory, note the file entries under them.



3. **Open only the matching originals.** Everything else stays unread;



   where the index already summarizes a file well, rely on the digest



   instead of opening the original at all.



4. **Skim the digest for the rest.** For files you did not open, the



   per-file summary + keywords in `INDEX.md` is your whole view - that



   is the intended token saving.



5. **If the index is missing or stale, build it first.** Run



   `doctor <root>`; if it reports the index absent or stale, run



   `broadcast <root>` before reading. Never re-read every original just



   because the index lags.







No `_broadcast/` at all -> skip straight to step 5. Starting a



**long-context task**, or any folder too large to read in one session?



Build the broadcast center first and read `INDEX.md` before opening any



original. For a workspace task the broadcast center is mandatory (step 7



of the workflow) - never skip it; on a non-workspace folder, propose it



once and wait for confirmation.







## Usage examples







```bash



cd <directory containing this SKILL.md>







python -m scripts.run init <root>                    # create the skeleton (cheap)



python -m scripts.run organize <root>                # full pipeline + verify + rollback



python -m scripts.run organize <root> --mode quick   # move only, no verify



python -m scripts.run organize <root> --mode incremental  # reuse unchanged digests



python -m scripts.run mark-downloaded <root> <file> --url <source-url>  # provenance



python -m scripts.run broadcast <root>               # rebuild the read-only index



python -m scripts.run undo <history_file> [--root <root>]  # reverse a verified run



```







Placement is by provenance, not filename: `downloaded` ->



`material/downloaded/`; user material -> `material/initial/`



(**verbatim** - never renamed, modified or deleted); names containing



final / deliverable / report / review / summary -> `results/`;



everything else (assistant output) -> `process/`. Custom keyword rules:



`.task-organizer.yml`, optionally with named `profiles.<name>` via



`--profile`. Authoritative specs: `BUILTIN_PLACEMENT` in



`scripts/rules.py`, the 8 checks in `scripts/verify.py`.







## Failure handling







- **`verification: failed`** - the tool already rolled back to the



  before-state (moves reversed, created dirs / indexes removed, log



  renamed `..._Cancelled.md`). Report that fact; fix the cause and



  re-run - rollback is idempotent, re-running is safe.



- **C8 warning (deliverable at the root, no standard structure)** - the



  missed-init signal: run `init <root>` first, then `organize <root>`.



- **User-material name clash** - the file is left in place and reported,



  never renamed; only files the tool itself owns may be suffixed.



- **Skipped entries** - hidden files, empty folders, symlinks and



  read-only files are never moved; they are logged and marked in the



  index. Per-entry errors are caught and logged, so one bad file cannot



  fail the batch.



- Every command prints its own error message (exit `0` success, `2`



  usage / config error).







Requirements: Python 3.10+, standard library only; `openpyxl` merely



adds the xlsx index and degrades to md-only when missing.






