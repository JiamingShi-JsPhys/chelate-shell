/**
 * Chelate Shell — DSH (DeepSeek Harness) host adapter.
 *
 * The orchestrator itself is Python (`cli.py` + `core/` + `skills/`). This file
 * does one job: expose that CLI to DSH as model-callable tools, so an agent
 * running inside the harness can list the registered skills, run one of them,
 * drive the gated pipeline, and audit `results/` without leaving the session.
 *
 * Nothing is reimplemented here. Every tool shells out to `cli.py` with an
 * explicit argument vector (never a shell string), forwards the abort signal,
 * and returns the process's own exit code and output unchanged.
 *
 * Interpreter: set CHELATE_PYTHON to pin one; otherwise `python` on Windows and
 * `python3` elsewhere, which is what the rest of the project's docs assume.
 */
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineTool } from '@deepseek-ai/dsh-tools'

/** Repo root — `cli.py` resolves its own sys.path from here. */
const REPO_ROOT = dirname(fileURLToPath(import.meta.url))
const CLI = join(REPO_ROOT, 'cli.py')

const DEFAULT_TIMEOUT_MS = 600_000

function interpreter() {
  const pinned = process.env.CHELATE_PYTHON
  if (pinned && pinned.trim() !== '') return pinned
  return process.platform === 'win32' ? 'python' : 'python3'
}

/**
 * Run the CLI once and collect its output.
 * @param {string[]} argv - arguments after `cli.py`.
 * @param {{cwd?: string, timeoutMs?: number, signal?: AbortSignal}} opts
 */
function runCli(argv, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(interpreter(), [CLI, ...argv], {
        cwd: opts.cwd ?? REPO_ROOT,
        signal: opts.signal,
        windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      })
    } catch (error) {
      resolve({
        exitCode: -1,
        stdout: '',
        stderr: `${error?.message ?? error}`,
        timedOut: false,
        spawnError: true,
      })
      return
    }

    let stdout = ''
    let stderr = ''
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      child.kill()
    }, timeoutMs)

    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk
    })

    const finish = (code) => {
      clearTimeout(timer)
      resolve({ exitCode: code ?? -1, stdout, stderr, timedOut, spawnError: false })
    }

    child.on('error', (error) => {
      finish(null)
      stderr += `\n${error?.message ?? error}`
    })
    child.on('close', finish)
  })
}

/** Model-facing text for one finished CLI run. */
function renderRun(label, result) {
  const status = result.spawnError
    ? 'could not start the interpreter'
    : result.timedOut
      ? 'timed out'
      : result.exitCode === 0
        ? 'ok'
        : `exit ${result.exitCode}`
  const parts = [`${label}: ${status}`]
  if (result.stdout.trim() !== '') parts.push(result.stdout.trimEnd())
  if (result.stderr.trim() !== '') parts.push(`--- stderr ---\n${result.stderr.trimEnd()}`)
  return [{ type: 'text', text: parts.join('\n') }]
}

const runResultSchema = {
  type: 'object',
  properties: {
    exitCode: { type: 'integer' },
    timedOut: { type: 'boolean', required: true },
    stdout: { type: 'string', required: true },
    stderr: { type: 'string', required: true },
  },
  additionalProperties: false,
}

const runJson = (result) =>
  JSON.stringify({
    exitCode: result.exitCode,
    timedOut: result.timedOut,
    stdout: result.stdout,
    stderr: result.stderr,
  })

const skills = defineTool({
  name: 'chelate_skills',
  description:
    'List the skills registered in Chelate Shell, with each one\'s pipeline stage and the third-party packages it needs. Read this before calling chelate_run, so the skill name comes from the registry rather than a guess.',
  parameters: {},
  output: {
    schema: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          name: { type: 'string', required: true },
          stage: { type: 'string', required: true },
          dependencies: { type: 'string', required: true },
        },
      },
    },
    render: (_args, value) => {
      const lines = value.map(
        (s) => `${s.name} — stage=${s.stage} deps=${s.dependencies || '-'}`,
      )
      return [{ type: 'text', text: `${value.length} skills registered\n${lines.join('\n')}` }]
    },
  },
  async execute(_args, exec) {
    const result = await runCli(['list'], { timeoutMs: 120_000, signal: exec.signal })
    if (result.exitCode !== 0 || result.timedOut) {
      throw new Error(
        `cli.py list failed (${result.timedOut ? 'timeout' : `exit ${result.exitCode}`}): ${result.stderr.trim()}`,
      )
    }
    const parsed = []
    for (const line of result.stdout.split(/\r?\n/)) {
      const m = /^\s{2}(\S+)\s+stage=(\S+)\s+deps=\[(.*)\]$/.exec(line)
      if (m) parsed.push({ name: m[1], stage: m[2], dependencies: m[3] === '-' ? '' : m[3] })
    }
    return parsed
  },
  presentCall: (args) => ({ card: 'generic', title: 'chelate_skills', rawInput: args }),
})

const run = defineTool({
  name: 'chelate_run',
  description:
    'Run one Chelate Shell skill directly against a workspace, bypassing the pipeline. Use it for a single step; use chelate_pipeline when the stage order and the gates matter. Extra `args` are passed through to the skill\'s own run.py verbatim.',
  parameters: {
    skill: {
      type: 'string',
      required: true,
      description: 'Skill name exactly as chelate_skills reports it, e.g. "data-profiler".',
    },
    root: {
      type: 'string',
      required: true,
      description: 'Workspace directory the skill reads from and writes into.',
    },
    args: {
      type: 'array',
      items: { type: 'string' },
      description: 'Additional flags for the skill, e.g. ["--input", "draft.md"].',
    },
  },
  output: {
    schema: runResultSchema,
    render: (args, value) => renderRun(`chelate_run ${args.skill}`, value),
  },
  async execute(args, exec) {
    const argv = ['run', args.skill, '--root', args.root]
    if (Array.isArray(args.args)) argv.push(...args.args)
    return runCli(argv, { cwd: args.root, signal: exec.signal })
  },
  presentCall: (args) => ({ card: 'generic', title: `chelate_run ${args.skill}`, rawInput: args }),
})

const pipeline = defineTool({
  name: 'chelate_pipeline',
  description:
    'Run the gated Chelate Shell pipeline over a workspace: skills execute in the declared stage order, and a failing gate stops the run instead of passing its output downstream. Mode "a" runs the default chain, "b" adapts to one input kind, "c" runs only the skills named in `selected`. Use `dryRun` to print the planned order without executing anything.',
  parameters: {
    root: {
      type: 'string',
      required: true,
      description: 'Workspace directory (the four-zone layout lives here).',
    },
    mode: {
      type: 'string',
      enum: ['a', 'b', 'c'],
      description: 'Pipeline mode. Defaults to "a".',
    },
    inputs: {
      type: 'array',
      items: { type: 'string' },
      description: 'Input files, workspace-relative or absolute, forwarded as --input to the skills that declare that type.',
    },
    selected: {
      type: 'string',
      description: 'Comma-separated skill names for mode "c".',
    },
    dryRun: {
      type: 'boolean',
      description: 'Print the planned execution order and run nothing.',
    },
    skillArgs: {
      type: 'array',
      items: { type: 'string' },
      description: 'Per-skill arguments as "skill:--flag value", one entry per skill.',
    },
  },
  output: {
    schema: runResultSchema,
    render: (args, value) => renderRun(`chelate_pipeline mode=${args.mode ?? 'a'}`, value),
  },
  async execute(args, exec) {
    const argv = ['pipeline', '--root', args.root]
    if (args.mode) argv.push('--mode', args.mode)
    if (args.selected) argv.push('--selected', args.selected)
    if (Array.isArray(args.inputs) && args.inputs.length > 0) argv.push('--inputs', ...args.inputs)
    for (const spec of args.skillArgs ?? []) argv.push('--skill-arg', spec)
    if (args.dryRun === true) argv.push('--dry-run')
    return runCli(argv, { cwd: args.root, signal: exec.signal })
  },
  presentCall: (args) => ({ card: 'generic', title: 'chelate_pipeline', rawInput: args }),
})

const audit = defineTool({
  name: 'chelate_audit',
  description:
    'Report files sitting in `results/` that no promotion accounts for. The approval gate guards promote(), not the directory, so this is how a stray copy shows up. Exits non-zero when anything is unaccounted for.',
  parameters: {
    root: {
      type: 'string',
      required: true,
      description: 'Workspace directory to audit.',
    },
  },
  output: {
    schema: runResultSchema,
    render: (_args, value) => renderRun('chelate_audit', value),
  },
  async execute(args, exec) {
    return runCli(['audit', '--root', args.root], { cwd: args.root, signal: exec.signal })
  },
  presentCall: (args) => ({ card: 'generic', title: 'chelate_audit', rawInput: args }),
})

/** Cordis plugin name. */
const name = 'chelate-shell'

/** Services required before apply() runs. */
const inject = ['tools']

/**
 * Register the four tools.
 * @param ctx - the tool registry.
 */
function apply(ctx) {
  for (const tool of [skills, run, pipeline, audit]) ctx.tools.register(tool)
}

export { apply, inject, name }
