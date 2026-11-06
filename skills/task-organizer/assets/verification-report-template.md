# Verification Report

- generated at: {timestamp}
- root: `{root}`
- verdict: **{PASS | FAIL (rollback needed)}**

## Checks

| Code | Check | Severity | Result | Detail |
|------|-------|----------|--------|--------|
| C1 | File count conservation | error | {PASS/FAIL} | {detail} |
| C2 | Content integrity (unmoved files SHA stable) | error | {PASS/FAIL} | {detail} |
| C3 | Move traceability | error | {PASS/FAIL} | {detail} |
| C4 | No unauthorized deletion | error | {PASS/FAIL} | {detail} |
| C5 | No unauthorized modification (size stable) | error | {PASS/FAIL} | {detail} |
| C6 | No unauthorized addition (index/log only) | warning | {PASS/FAIL} | {detail} |
| C7 | Directory structure compliance | error | {PASS/FAIL} | {detail} |

## Details

### C1 File count conservation - {passed/failed}
- {detail lines}

### C2 Content integrity - {passed/failed}
- {detail lines}

### C3 Move traceability - {passed/failed}
- {detail lines}

### C4 No unauthorized deletion - {passed/failed}
- {detail lines}

### C5 No unauthorized modification - {passed/failed}
- {detail lines}

### C6 No unauthorized addition - {passed/failed}
- {detail lines}

### C7 Directory structure compliance - {passed/failed}
- {detail lines}
