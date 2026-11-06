import os, re, io

BASE = os.path.dirname(os.path.abspath(__file__))
SKILLS_SRC = os.path.join(BASE, '..', '..', 'chelate-shell-main', 'skills')
OUT = os.path.join(BASE, 'FILE_FUNCTION_MAP.md')

skills = ['task-organizer', 'multi-dim-manager', 'document-evolution-tracker',
          'capstone-labmate', 'video-tracker', 'longitudinal-analysis',
          'formula-validator', 'ai-trace-remover', 'conflict-detector']

def defs_of(path):
    items = []
    try:
        with open(path, encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                m = re.match(r'^(def|class)\s+([A-Za-z_]\w*)', line)
                if m:
                    items.append((i, 'def' if m.group(1) == 'def' else 'class', m.group(2)))
    except Exception:
        pass
    return items

def count_loc(path):
    try:
        with open(path, encoding='utf-8') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

buf = io.StringIO()
grand_files = 0
grand_loc = 0
for s in skills:
    files = []
    for root, dirs, fs in os.walk(os.path.join(SKILLS_SRC, s)):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.pytest_cache')]
        for f in fs:
            if f.endswith('.py'):
                files.append(os.path.relpath(os.path.join(root, f), SKILLS_SRC))
    files.sort()
    loc = sum(count_loc(os.path.join(SKILLS_SRC, p)) for p in files)
    grand_files += len(files)
    grand_loc += loc
    buf.write('\n## {} — {} py files / {} LOC\n\n'.format(s, len(files), loc))
    buf.write('| # | File | LOC | Top-level definitions (line:kind name) |\n')
    buf.write('|---|------|-----|----------------------------------------|\n')
    for idx, rel in enumerate(files, 1):
        p = os.path.join(SKILLS_SRC, rel)
        n = count_loc(p)
        ds = defs_of(p)
        if not ds:
            txt = '(module / no top-level defs)'
        elif len(ds) > 14:
            txt = '; '.join('{}:{} {}'.format(l, k, nm) for l, k, nm in ds[:14])
            txt += '; ... (+{} more)'.format(len(ds) - 14)
        else:
            txt = '; '.join('{}:{} {}'.format(l, k, nm) for l, k, nm in ds)
        buf.write('| {} | `{}` | {} | {} |\n'.format(idx, rel, n, txt))

header = []
header.append('# Chelate v1.1.0 — Legacy File & Function Map (Adapter Wiring Reference)')
header.append('')
header.append('Source of truth: `chelate-shell-main/skills/` (clean tree, verified UTF-8).')
header.append('Every legacy Python file, its line count, and its top-level definitions.')
header.append('The new root-level `run.py` adapters import these modules in-process;')
header.append('no legacy code is rewritten (red line: 100% capability migration).')
header.append('')
header.append('Grand total: **{} Python files, {} LOC**.'.format(grand_files, grand_loc))
header.append('')
header.append('Adapter wiring summary (how each new root `run.py` reaches the legacy code):')
header.append('')
header.append('| Skill | Legacy entry | Adapter import | Dispatch |')
header.append('|-------|--------------|----------------|----------|')
header.append('| task-organizer | `python -m scripts.run` | `from scripts import run as legacy` | `legacy.run_from_cli(argv)` |')
header.append('| multi-dim-manager | `python -m scripts.run` | `from scripts import run as legacy` | `legacy.main(argv)` |')
header.append('| document-evolution-tracker | `python -m src.cli` | `from src import cli as legacy` | `legacy.main(argv)` |')
header.append('| capstone-labmate | `python scripts/<stage>.py` | `import preconfigure_cap / process_cap / draft_report` (scripts dir on sys.path) | `mod.main(argv)` |')
header.append('| video-tracker | `python -m scripts.run` | `from scripts import run as legacy` | `legacy.main(argv)` |')
header.append('| longitudinal-analysis | `python -m src.cli` | `from src import cli as legacy` | `legacy.main(argv)` |')
header.append('| formula-validator | `python scripts/cli.py` | `from scripts import cli as legacy` | `legacy.main(argv)` |')
header.append('| ai-trace-remover | `python -m src.cli` | `from src import cli as legacy` | `legacy.main(argv)` |')
header.append('| conflict-detector | `python -m src.cli` | `from src import cli as legacy` | `legacy.main(argv)` |')
header.append('')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(header))
    f.write(buf.getvalue())

print('written {} files / {} LOC -> {}'.format(grand_files, grand_loc, OUT))
