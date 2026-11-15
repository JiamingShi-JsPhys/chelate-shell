# Security Policy

Chelate Shell runs local skills and executes their entry points, so a defect
here can be more than a wrong answer: it can run a command. Reports about the
orchestrator — command execution, the sandbox, path handling, the approval
token, or the pre-dispatch screening — are treated as security issues.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.3.x   | Yes |
| 1.2.x and older | No — upgrade to the latest 1.3.x release |

Only the newest 1.3.x release on the default branch receives fixes. Older
tags stay available for reproduction, not for patching.

## Reporting a vulnerability

Use GitHub's private reporting form rather than a public issue:

1. Open the **Security** tab of this repository.
2. Choose **Report a vulnerability**.
3. Describe the issue there.

The report stays private between you and the maintainer until a fix is
published. Please do not open a public issue, discussion, or pull request for
a suspected vulnerability before that.

Do not put secrets, tokens, credentials, or personal data in the report. A
reproduction built from placeholder values is enough to show the problem.

## What to include

- The release tag or commit you tested, and the output of `git describe`.
- The operating system and Python version.
- The smallest reproduction you can manage: the command, the config, the input
  file, and what you observed.
- The impact you believe it has — what an attacker could do, and what they
  would need to control first.

## Scope

In scope:

- Command execution: the plugin runner in `multi-dim-manager`, the sandbox in
  `core/sandbox.py`, and the executable whitelist.
- Path handling: writes that escape the declared workspace, traversal through
  adapter paths or output flags.
- The approval token, the promotion lock, and the rollback path.
- The pre-dispatch screen in `security-guard`, when a realistic payload gets
  past it.

Out of scope:

- Vulnerabilities in third-party packages or in the host platform — report
  those to the upstream project.
- A skill returning a scientifically wrong verdict. That is a correctness
  bug; open a normal issue.
- Anything that requires the attacker to already control the machine or the
  account running the tool.

## Response

This is a single-maintainer project and no formal SLA is offered. Reports are
read as they arrive; expect an initial reply within about a week, then either
a fix or a written explanation of why the behaviour is intended. Please allow
a reasonable window for a fix to be published before any public disclosure.

## Safe harbour

Research that stays within the scope above, runs against your own installation,
and avoids other people's data and systems will not be pursued. Do not test
against services you do not own or lack permission to test.
