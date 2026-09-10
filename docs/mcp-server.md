# TVData MCP server

TVData exposes public-sector remuneration data through a read-only Model Context Protocol (MCP) server. Repository CSV files remain the canonical source of truth. The MCP layer adds discovery, semantic resolution, deterministic comparison, context resolution, provenance and compensation-component inspection without creating a second datastore.

## Architectural boundary

The MCP is an analytical interface, not a payroll engine and not a second data model. It follows the project rule `Require -> Adopt -> Profile -> Extend -> Invent`.

The server may:

- discover pay systems, grades, steps, allowances and supplementary pension metadata;
- resolve human pay-system terms to canonical table identifiers;
- resolve current and latest-known historical snapshots;
- compare and rank nominal base pay;
- normalize base pay by documented contractual working time;
- inspect progression, provenance and data quality;
- inspect compensation-component encodings and calculation readiness.

The server must not:

- mutate repository data;
- infer occupational, legal or status equivalence from similar pay;
- calculate net income or employer cost without separate tax/social-insurance models;
- treat archived yearly snapshots as a legally complete temporal database;
- calculate a payment amount from an annual percentage without the tariff-specific assessment base;
- automatically construct total annual compensation until all included components have validated entitlement, temporal and assessment-base semantics.

## Application profile

`profiles/tvdata-mcp/manifest.json` defines the versioned application profile.

Current profile:

- profile id: `tvdata-tariff-intelligence`
- profile version: `0.3.0`
- schema version: `1.0.0`
- stability: `experimental`
- source of truth: `repository-csv`

The profile is exposed through `get_application_profile_manifest`.

## Requirements and execution

- Python 3.10+
- `pip install -r requirements-mcp.txt`
- install `pytest>=8` for tests

Local stdio transport:

```bash
python mcp_server.py
```

Streamable HTTP:

```bash
TVDATA_MCP_TRANSPORT=streamable-http \
TVDATA_MCP_HOST=127.0.0.1 \
TVDATA_MCP_PORT=8000 \
python mcp_server.py
```

The endpoint is then available at `http://127.0.0.1:8000/mcp`. For remote deployment, terminate TLS at the platform/reverse proxy. Authentication becomes mandatory if write tools or non-public data are ever introduced.

## Tool layers

### Raw discovery

- `list_pay_tables`
- `get_pay_table_structure`
- `get_pay_table_metadata`
- `get_base_pay`
- `get_progression`
- `list_allowances`
- `get_allowance_value`
- `get_allowance_metadata`
- `list_pension_plans`
- `get_pension_metadata`

### Tariff intelligence

- `list_pay_systems`
- `resolve_pay_system_entity`
- `resolve_pay_table_as_of`
- `get_base_pay_at_date`
- `compare_pay_positions`
- `compare_pay_positions_at_dates`
- `rank_pay_positions`
- `rank_pay_positions_at_date`
- `compare_step_progressions`
- `get_pay_history_series`
- `find_nearest_pay_positions`

### Context and provenance

- `resolve_weekly_working_time`
- `compare_pay_positions_with_context`
- `compare_weekly_working_time`
- `get_pay_provenance`
- `assess_pay_system_provenance`
- `audit_pay_data_quality`
- `audit_source_provenance`

### P2 compensation semantics

- `inspect_compensation_components`
- `audit_compensation_component_semantics`

These P2 tools inspect component encodings, options, validity, scope, provenance and annualization readiness. They deliberately stop before total-compensation calculation.

## Working-time context

Working time is not always a property of the pay table alone. `profiles/tvdata-mcp/working-time-context.csv` stores contextual records where jurisdiction or employment context is required.

Example: `TV-L` without a Land is intentionally unresolved. `resolve_weekly_working_time(table_id="TV-L", jurisdiction_code="DE-ST")` resolves Sachsen-Anhalt to the documented value and returns its provenance and evidence quality. `TVöD-Bund` can use an unambiguous table-level default.

`compare_pay_positions_with_context` uses this resolver so callers do not need to inject arbitrary working-time overrides when a profiled context exists.

The normalization

```text
(monthly base × 12) / (weekly contractual hours × 52)
```

is an analytical comparison metric, not a payroll hourly wage.

## Provenance

`profiles/tvdata-mcp/source-registry.csv` classifies known source domains by authority role and evidence quality. Source authority and factual/temporal correctness are kept separate: an authoritative domain does not prove that a particular document is the correct version for a dataset.

The provenance tools expose source URLs, validity metadata, registry classification and gaps. P1 also corrected stale pay-table source links for current TV-L and TVöD-Bund data without changing the corresponding pay values.

## P2 compensation semantics

Allowance tables use repository-specific combinations such as `func_type=fabsolute|frelative` and `adding_type=monthly|yearly`. P2 makes these semantics explicit instead of assuming that every linked component can be safely added to annual base pay.

The inspection layer classifies components as:

- `absolute_monthly`
- `absolute_yearly`
- `relative_monthly`
- `relative_yearly`
- `unknown`

For annual special payments stored as a relative yearly factor, P2 introduces:

```text
value_semantics=annual_percentage_divided_by_12
```

This means a stored value such as `6.25` can be reconstructed as an encoded annual rate of `75 %` (`6.25 × 12`). It does **not** mean the payment equals 75 % of one table month. The tariff-specific assessment base, entitlement conditions, reductions and special contexts remain separate requirements.

Accordingly, `represented_annual_rate_pct` is informational/provenance output, while `safe_for_total_annual_compensation` remains `false` for these components.

### 2026 annual-special-payment data

P2 updates the encoded 2026 annual-special-payment rates for the current TVöD profiles:

- Bund: 95 % for E1-E8, 90 % for E9a-E12, 75 % for E13-E15;
- general VKA: 85 %;
- generic VKA S-table profile: 85 %, explicitly excluding `TVöD-BT-B` and `TVöD-BT-K` special contexts.

The special BT-B/BT-K rules are intentionally not projected into the generic S-table component.

`default_option` remains repository configuration metadata and is not interpreted by the MCP as proof of individual entitlement.

## Historical semantics

Historical resolution chooses the latest known repository snapshot on or before the requested date. It does not extrapolate backwards before the earliest known snapshot and does not silently project current working-time values into older periods. The archive therefore provides repository history, not a legally complete validity-time database.

## Testing

Pure domain/profile tests live under `tests/` and MCP contract tests use the SDK in-memory client. Relevant commands after installing the MCP dependencies include:

```bash
pytest -q tests/test_mcp_analytics.py tests/test_mcp_context.py tests/test_mcp_compensation.py
pytest -q tests/test_mcp_server.py tests/test_mcp_context_contract.py tests/test_mcp_compensation_contract.py
```

No GitHub Actions workflow is introduced solely for this MCP feature.

## Validation status

The repository changes include regression tests for profile versioning, contextual working time, provenance, annual-rate reconstruction and MCP tool contracts. In the current authoring environment, direct GitHub cloning is unavailable because outbound DNS is blocked and the MCP SDK is not installed, so the full runtime `pytest` suite cannot be executed here. This limitation must remain explicit in the pull request until the suite is run in an environment with `requirements-mcp.txt` installed.

## Next boundary

A future P3 may add validated annual-compensation calculations, but only after formalizing at least:

1. entitlement conditions and default semantics;
2. tariff-specific assessment bases;
3. time-dependent component validity;
4. reductions/proration and special employment contexts;
5. component interaction/double-counting rules.

Net pay, employer cost and CPI-backed real-pay analysis should remain separate adapters/engines rather than being folded into the TVData canonical pay-data boundary.
