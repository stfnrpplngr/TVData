# TVData MCP server

TVData exposes its public-sector remuneration data through a small, read-only Model Context Protocol (MCP) server. The CSV files in this repository remain the source of truth; the MCP layer adds discovery, comparison and analytical semantics without copying the data into a second datastore.

## Design goal

The server is not just a CSV reader. Its primary use case is **tariff and remuneration intelligence**: an MCP client should be able to find pay systems, compare exact positions, rank comparable cells, inspect progression and working time, follow historical changes and see the provenance and limits of every comparison.

A key design rule is that **pay proximity is not employment equivalence**. Comparisons between collective agreements and civil-service salary scales are allowed, but the server explicitly marks the limits of nominal base-pay comparisons. It does not infer equivalent duties, qualification requirements, pension rights, social-insurance treatment or net income.

## Scope

The server supports three layers:

1. **Data access** — tables, metadata, base pay, allowances, pension metadata.
2. **Deterministic comparison** — exact positions, rankings, contractual working-time normalization, progression and history.
3. **Interpretation guardrails** — provenance, validity dates, comparability warnings and data-quality diagnostics.

It does **not** modify repository data, calculate a complete net salary, or execute the legacy `scripts/prv/*` calculation functions. It also does not currently construct total annual compensation by automatically adding allowances: the allowance schemas contain different semantics (`func_type`, `adding_type`, options), so aggregation should only be introduced once those rules have a validated standalone contract.

## Requirements

- Python 3.10+
- `pip install -r requirements-mcp.txt`

For tests, also install `pytest>=8`.

## Run locally (stdio)

```bash
python mcp_server.py
```

`stdio` is the default transport and is appropriate when a local MCP host launches the server as a child process.

## Run over Streamable HTTP

```bash
TVDATA_MCP_TRANSPORT=streamable-http \
TVDATA_MCP_HOST=127.0.0.1 \
TVDATA_MCP_PORT=8000 \
python mcp_server.py
```

The MCP endpoint is then available at `http://127.0.0.1:8000/mcp`.

For container/PaaS deployment, set `TVDATA_MCP_HOST=0.0.0.0` and terminate TLS at the reverse proxy or platform edge. Because the underlying repository is public and this server is read-only, application-level authentication is not required for the initial public-data use case. If write tools or non-public datasets are added later, authentication and authorization become mandatory design concerns.

## Tools

### Discovery and raw data

| Tool | Purpose |
| --- | --- |
| `list_pay_tables` | Find current pay-table identifiers and core metadata. |
| `get_pay_table_structure` | Discover valid grades, steps and linked components before querying. |
| `get_pay_table_metadata` | Return all metadata for one table. |
| `get_base_pay` | Return monthly gross base pay for table + grade + step. |
| `get_progression` | Return documented years to the next step. |
| `list_allowances` | List all allowances or those linked to one table. |
| `get_allowance_value` | Return one allowance value plus its semantics metadata. |
| `get_allowance_metadata` | Return all metadata for an allowance. |
| `list_pension_plans` | List all supplementary pension plans or those linked to one table. |
| `get_pension_metadata` | Return all metadata for a pension plan. |

### Comparison and analytics

| Tool | Purpose |
| --- | --- |
| `compare_pay_positions` | Compare 2–20 exact table/grade/step positions and show deltas and comparability warnings. |
| `rank_pay_positions` | Rank the same grade/step across selected or filtered current tables. |
| `compare_weekly_working_time` | Compare regular weekly hours with dedicated provenance. |
| `compare_step_progressions` | Compare waiting times and cumulative years-to-step. |
| `get_pay_history_series` | Combine the current table with matching `archive/<table>-YYYY` snapshots. |
| `find_nearest_pay_positions` | Find nearest nominal base-pay cells without claiming job/status equivalence. |
| `get_pay_provenance` | Return validity, pay source, working-time source and linked compensation components. |
| `audit_pay_data_quality` | Check metadata compatibility, missing provenance and numeric matrix integrity. |

## Example analytical workflows

### TV-L vs. TVöD Bund

A client can compare `TV-L / 13 / step 4` with `TVöD-Bund / 13 / step 4`. TV-L has working time that depends on the federal state, so the caller can provide an explicit `weekly_hours_override` (for example 40 hours) when a working-time-normalized comparison is required. Without an unambiguous value, the server deliberately leaves the normalized figure unresolved instead of guessing.

### A13 across jurisdictions

`rank_pay_positions(pay_grade="13", step="4", regime="civil_service")` ranks current civil-service A-scale cells that contain that grade and step. Tables without the requested position are counted as skipped rather than silently treated as zero.

### Historical development

`get_pay_history_series(table_id="TV-L", pay_grade="13", step="4")` combines matching archive snapshots such as `archive/TV-L-2022` with the current `tables/TV-L` value and returns nominal changes between consecutive available snapshots.

### Pay-nearest search

`find_nearest_pay_positions` is intentionally heuristic. It answers questions such as “which current pay cells are numerically closest to this salary?” It does **not** answer “which jobs are equivalent?”. The result always carries this warning because similar base salaries can arise from very different legal and occupational structures.

## Comparison semantics

### Monthly and annual base pay

`monthly_base_eur` is the table's nominal monthly gross base pay. `annual_base_eur` is simply `monthly_base_eur * 12`; it is **not total annual compensation** and excludes annual bonuses, allowances and other components.

### Working-time normalization

`base_per_contract_hour_eur` is an analytical normalization:

```text
(monthly base × 12) / (weekly contractual hours × 52)
```

It is not a payroll hourly wage. Vacation, public holidays, overtime, bonuses and allowances are not adjusted. If the source specifies a contextual range (for example TV-L working time by federal state), the server does not choose a value automatically; callers can provide an explicit override.

### Different employment regimes

Civil-service salary scales and collective agreements can be compared at the nominal-base-pay layer. Total compensation and net income are not directly comparable because pension, social-insurance, tax and employment-status rules differ. The MCP response makes this boundary explicit.

### Validity

Every comparison exposes `valid_from` where available. A comparison can therefore reveal that inputs come from different effective dates. Historical data are sourced from the repository's `archive` directories rather than reconstructed from external sources at request time.

## Metadata compatibility

The repository currently contains both `name,value` and `key,value` variants of `Meta.csv`. The MCP reader accepts both and the data-quality audit reports the alternate form. This preserves coverage while making schema convergence visible instead of silently dropping affected tables.

## Test

Pure comparison logic can be tested without starting a server:

```bash
pytest -q tests/test_mcp_analytics.py
```

MCP transport/schema contracts use the SDK's in-memory client:

```bash
pytest -q tests/test_mcp_server.py
```

The repository contains both test layers. They should be run after installing `requirements-mcp.txt`; no GitHub Actions workflow is added solely for the MCP server.

## Recommended next extensions

The next useful extensions should preserve the separation between canonical data and derived analytics:

1. **As-of-date resolution** — resolve the dataset valid on a requested date from current/archive snapshots, with explicit handling where `valid_to` is not recorded.
2. **Canonical taxonomy and aliases** — encode jurisdiction, employment regime, tariff family and aliases in metadata instead of relying on table-name heuristics.
3. **Validated annual-compensation profiles** — aggregate recurring allowances and annual bonuses only after their calculation semantics are formalized and tested.
4. **Context resolver for working time** — resolve TV-L or other conditional hours from jurisdiction/context rather than requiring a manual override.
5. **Source-quality metadata** — distinguish primary legal/tariff sources from secondary references and expose verification/access dates systematically.
6. **Schema/version contract** — publish a stable MCP output/application-profile version for downstream clients.
7. **Real-wage analysis as an optional external-data profile** — inflation adjustment requires CPI data outside the current TVData source of truth and should therefore be a separate, provenance-aware adapter rather than silently embedded constants.
8. **Employer-cost/net-pay integration only as a separate engine** — these require tax, social-insurance and scenario assumptions that should not contaminate TVData's canonical pay-data boundary.

## ChatGPT

For ChatGPT usage, expose the Streamable HTTP endpoint through a supported remote deployment or a secure MCP tunnel. Keep the server read-only unless there is a concrete, separately authorized write use case.
