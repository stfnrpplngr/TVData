# TVData MCP safety contract

The TVData MCP is a read-only application interface over repository data. CSV files and versioned profile data remain authoritative; MCP tools do not mutate them.

## Tool annotations

Every tool registered on the server inherits the same MCP safety metadata through `ReadOnlyMCPServer` in `mcp_safety.py`:

- `readOnlyHint = true`
- `openWorldHint = false`
- `destructiveHint` is omitted
- `idempotentHint` is omitted for read-only tools

The Python SDK exposes the corresponding snake-case fields (`read_only_hint`, `open_world_hint`, ...); the MCP wire representation remains protocol-defined.

The server-level default is deliberate. TVData registers tools in several modules (`mcp_server.py`, `mcp_tools.py`, compensation tools and special-payment tools). A central server default prevents a newly added tool family from silently losing the same safety contract.

## Meaning of closed world

`openWorldHint = false` describes the current tool behavior: tools read the checked-out/versioned TVData repository and perform local deterministic resolution/calculation. They do not browse arbitrary web resources or mutate external systems.

Source URLs returned as provenance are data, not network actions performed by the tool.

## Validation

`tests/test_mcp_safety.py` connects to the real in-process `MCPServer`, lists the complete runtime tool catalog and asserts the safety annotations on every tool.

The targeted `TVData MCP smoke` workflow runs only when MCP implementation/tests/profile files change and executes the full `tests/test_mcp*.py` regression suite. This keeps validation scoped to the MCP surface instead of adding a broad repository workflow.

## Boundary

Safety annotations are advisory protocol metadata and do not replace transport security. A remotely exposed Streamable HTTP deployment still requires an explicit trusted authentication/TLS boundary and must not be made public merely because its tools are read-only.
