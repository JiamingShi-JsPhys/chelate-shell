# MCP Server

Exposes the validator as four MCP tools over stdio JSON-RPC.

## Why no `mcp` package

The server speaks the wire protocol directly, so mounting it needs nothing
beyond the skill's own requirements (`sympy`, `numpy`, `scipy`). A machine that
is already set up for scientific work can mount this without another
dependency, and without a second Python environment to keep in sync.

## Tools

| Tool | Purpose |
|---|---|
| `formula_validate` | Verify an equation with all five deterministic checks. |
| `formula_inspect` | Dimension, poles and limit behaviour of a single expression. |
| `formula_derive` | Verify a derivation chain and localise the first break. |
| `matrix_check` | Hermitian / unitary / ... for group theory and QM. |

Four tools on purpose. Tool schemas are injected into every conversation that
mounts the server, so a large surface charges rent on every turn; a verification
summary costs a few hundred tokens.

## Mounting

Add an entry to `~/# local configmcp.json` (the file used for custom connectors,
**not** `.mcp.json`):

```json
{
  "mcpServers": {
    "formula-validator": {
      "command": "<python>",
      "args": ["<path>/formula-validator/mcp_server/server.py"]
    }
  }
}
```

Replace `<python>` with an interpreter that has the requirements installed — on
Windows use the absolute path, e.g.
`C:/Users/you/# local configbinaries/python/envs/default/Scripts/python.exe`.

After saving the config, the server does not activate on its own: open the
custom connectors entry at the top right of the connector management page and
click **Trust** on the new server.

A ready-to-edit copy is in `mcp_config.example.json`.

## Behaviour notes

- stdout carries JSON-RPC only; diagnostics go to stderr, so a stray warning
  never corrupts a frame.
- Every tool call is wrapped: an exception becomes `isError: true` with the
  message, never a dropped connection.
- Tools return the compact summary. Complete Markdown reports are written to
  `_reports/latest.md`; pass `full_report: true` only when you actually need the
  detail in context.
- `formula_validate` accepts LaTeX as well as SymPy syntax. SymPy syntax is more
  reliable; LaTeX needs an unambiguous body for `\int`, `\sum` and `\prod`.

## Smoke test

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"formula_validate","arguments":{"expr":"1/(x*(1+x)) = 1/x - 1/(1+x)"}}}' \
  | python mcp_server/server.py
```

## Not claimed

- The server implements the `2024-11-05` protocol revision for the methods it
  needs (`initialize`, `tools/list`, `tools/call`, `ping`). It does not
  implement resources, prompts, sampling or roots.
- Tool availability still depends on the client loading the server; a
  misconfigured path shows up as a connection failure, not as a tool error.
