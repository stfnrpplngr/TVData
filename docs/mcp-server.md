# TVData MCP server

TVData exposes public-sector remuneration data through a read-only Model Context Protocol (MCP) server. Repository CSV files remain the canonical source of truth. The MCP layer adds discovery, semantic resolution, deterministic comparison, context resolution, provenance and compensation semantics without creating a second datastore.

## Architectural boundary

The MCP is an analytical interface, not a payroll engine and not a second data model. It follows `Require -> Adopt -> Profile -> Extend -> Invent`.

It may discover pay systems, resolve current/historical snapshots, compare nominal base pay, normalize by documented working time, inspect provenance and compensation components, and perform narrowly scoped arithmetic where all legally relevant inputs are explicitly supplied.

It must not mutate repository data; infer occupational/legal equivalence from similar pay; infer individual entitlement, a tariff assessment base or proration exceptions; treat archive snapshots as a legally complete temporal database; calculate net pay/employer cost without separate models; or silently construct total annual compensation from incomplete components.

## Application profile

`profiles/tvdata-mcp/manifest.json` defines the versioned application profile.

Current profile:

- profile id: `tvdata-tariff-intelligence`
- profile version: `0.4.0`
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

The endpoint is then available at `http://127.0.0.1:8000/mcp`. Authentication becomes mandatory if write tools or non-public data are introduced.

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

### Compensation semantics

- `inspect_compensation_components`
- `audit_compensation_component_semantics`
- `get_annual_special_payment_rule`
- `calculate_annual_special_payment`

## P1 working-time and provenance context

Working time is not always a property of the pay table alone. `profiles/tvdata-mcp/working-time-context.csv` stores contextual records where jurisdiction or employment context is required.

For example, `TV-L` without a Land is intentionally unresolved. `resolve_weekly_working_time(table_id="TV-L", jurisdiction_code="DE-ST")` resolves Sachsen-Anhalt using profiled provenance. `TVöD-Bund` can use its unambiguous table-level default.

The working-time normalization

```text
(monthly base × 12) / (weekly contractual hours × 52)
```

is an analytical comparison metric, not a payroll hourly wage.

`profiles/tvdata-mcp/source-registry.csv` classifies known source domains by authority role and evidence quality. Authority and factual/temporal correctness remain separate concepts.

## P2 compensation-component semantics

Allowance tables use repository-specific combinations such as `func_type=fabsolute|frelative` and `adding_type=monthly|yearly`. P2 makes these semantics explicit instead of assuming every linked component can be safely added to annual base pay.

The inspection layer classifies components as `absolute_monthly`, `absolute_yearly`, `relative_monthly`, `relative_yearly` or `unknown`.

Annual special payments stored as relative yearly factors use:

```text
value_semantics=annual_percentage_divided_by_12
```

A stored value of `6.25` can therefore be reconstructed as an encoded annual rate of `75 %`. That reconstruction is not yet a euro payment calculation because the tariff-specific assessment base and entitlement/proration rules remain separate.

P2 also updates the encoded 2026 annual-special-payment rates for TVöD Bund (95/90/75 %), general VKA (85 %) and the generic VKA S-table profile (85 % with explicit exclusion of BT-B/BT-K contexts). `default_option` remains repository/UI configuration and is not treated as proof of individual entitlement.

## P3 annual-special-payment rules

P3 moves rule facts into the canonical allowance metadata rather than an MCP-only side table. Annual special-payment components now describe, where applicable:

- entitlement reference date;
- regular assessment months;
- assessment-base rule and excluded payment components;
- pay-grade reference date;
- late-start threshold and replacement assessment rule;
- partial-period normalization;
- one-twelfth proration semantics including the fact that tariff exceptions exist;
- payment month;
- a dedicated rule source.

The profile captures a material TV-L/TVöD distinction: TV-L switches to the first full employment month for employment beginning after 31 August, whereas TVöD Bund/VKA use the corresponding late-start rule after 30 September. The MCP exposes the distinction instead of normalizing it away.

### Step-dependent TV-L E13Ü rule

TV-L E13Ü cannot be represented by one annual-special-payment rate. Under the formalized rule, steps 2 and 3 use the E13 rate of 46.47 %, while the other available E13Ü steps use the E14 rate of 32.53 %. The legacy component table contains only one `13Ü` row and is therefore insufficient by itself.

For `pay_grade="13Ü"`, `get_annual_special_payment_rule` consequently requires `step`. It validates the step against the current pay table before applying the conditional rule. Calls without a step, or with unavailable steps such as step 1, fail rather than silently returning the raw row value. `inspect_compensation_components` also warns that the raw component view is context-incomplete for this grade.

### VKA employment context

The repository has no separate BT-B/BT-K pay-table entities. Therefore the generic VKA and generic SuE annual-special-payment rules explicitly exclude these special employment contexts. Conditional calculation requires `employment_context` for those generic components and rejects `TVöD-BT-B` or `TVöD-BT-K` rather than applying the general 85 % rate. This keeps absence of modeling distinct from a false generic answer.

### Conditional arithmetic

`get_annual_special_payment_rule(table_id, pay_grade, step=None)` returns the formalized rule and resolved annual rate.

`calculate_annual_special_payment(...)` performs only the final arithmetic:

```text
confirmed_assessment_base_monthly_eur
× annual_rate_pct / 100
× payable_twelfths / 12
```

The caller must explicitly provide:

1. a tariff-compliant, confirmed monthly assessment base;
2. `payable_twelfths` after resolving reductions and exceptions;
3. `entitlement_confirmed=true` only after the individual entitlement test has been resolved;
4. `step` where the rate is step-dependent;
5. `employment_context` where the generic component excludes special contexts.

The tool refuses to infer any of these inputs. It also rejects non-finite assessment bases and unavailable steps.

The result is one gross special-payment component. It is not total annual compensation, net pay or employer cost.

## Historical semantics

Historical resolution chooses the latest known repository snapshot on or before the requested date. It does not extrapolate backwards before the earliest known snapshot and does not silently project current working-time values into older periods. Archive history is therefore repository history, not a legally complete validity-time database.

## Testing

Relevant pure tests after installing dependencies:

```bash
pytest -q tests/test_mcp_analytics.py tests/test_mcp_context.py tests/test_mcp_compensation.py tests/test_mcp_special_payments.py
```

MCP contract tests:

```bash
pytest -q tests/test_mcp_server.py tests/test_mcp_context_contract.py tests/test_mcp_compensation_contract.py tests/test_mcp_special_payment_contract.py
```

No GitHub Actions workflow is introduced solely for this MCP feature.

## Validation status

Regression tests cover profile versioning, contextual working time, provenance, annual-rate reconstruction, conditional E13Ü rates, rule semantics, conditional special-payment arithmetic and MCP tool contracts. In the current authoring environment, outbound DNS blocks cloning the repository and the MCP SDK is not installed, so the complete runtime `pytest` suite cannot be executed here. That limitation must remain explicit until validation runs in an environment with `requirements-mcp.txt` installed.

## Next boundary

A later profile may assemble a validated annual-compensation view, but only from components whose entitlement, assessment base, temporal validity, proration and interaction/double-counting semantics are formalized. Net pay, employer cost and CPI-backed real-pay analysis remain separate adapters/engines and should not contaminate TVData's canonical pay-data boundary.
