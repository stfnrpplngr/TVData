# TVData MCP P1: context, versioning and provenance

P1 extends the read-only TVData MCP application profile with three capabilities that are required before compensation comparisons can be treated as reproducible analytical outputs: contextual working-time resolution, explicit profile versioning, and source-authority classification.

## 1. Contextual weekly working time

A pay table can be canonical while its regular weekly working time still depends on context. `TV-L` is the primary example: one storage table is used for remuneration, while regular weekly working time differs by Land.

The profile therefore keeps working-time context outside the remuneration matrix in:

`profiles/tvdata-mcp/working-time-context.csv`

Each record contains:

- canonical `table_id`;
- jurisdiction code and label;
- employment context;
- validity interval where known;
- weekly hours as a decimal value;
- evidence quality;
- direct value source and, where applicable, a separate legal-basis source;
- explanatory notes.

The MCP tool `resolve_weekly_working_time` resolves these records. For example:

- `TV-L` without a jurisdiction remains unresolved because a single number would be misleading;
- `TV-L` + `DE-ST` resolves to 40:00 hours for the current general context;
- `TVöD-Bund` falls back to the unambiguous table-level working-time source;
- a historical date earlier than the first documented context record is not backfilled from a later value.

`compare_pay_positions_with_context` uses this resolver before applying the transparent base-pay-per-contract-hour normalization. It does not change pay-table values.

### Evidence distinction

Source authority and value evidence are deliberately separate concepts. A primary legal text may define a rule while a secondary source reports the currently operational state-specific value. Therefore context rows carry their own evidence quality instead of inheriting a blanket quality label from any linked high-authority URL.

For the current TV-L profile:

- the 40-hour general rule in the eastern tariff area is supported directly by the TV-L legal/tariff text and marked `high`;
- state-specific values that are currently taken from the established public-service reference portal are marked `medium` until a direct state/social-partner source is profiled.

This is a profile-level quality statement, not a claim that secondary values are incorrect.

## 2. Versioned application profile

`profiles/tvdata-mcp/manifest.json` is the machine-readable contract for this application profile.

It currently declares:

- profile id `tvdata-tariff-intelligence`;
- profile version `0.2.0`;
- schema version `1.0.0`;
- experimental stability;
- repository CSV as the source of truth;
- MCP SDK compatibility;
- capabilities and non-negotiable guardrails;
- locations of profile-owned data files.

The manifest is exposed through `get_application_profile_manifest` so an MCP client can inspect the profile contract before relying on optional capabilities.

Versioning rules for subsequent changes:

- patch: corrections that do not change tool/schema semantics;
- minor: backward-compatible new fields, tools or profile capabilities;
- major: breaking schema/tool semantics or changed interpretation of an existing canonical field.

The profile remains pre-1.0 while source coverage and annual-compensation semantics are still being hardened.

## 3. Source authority registry

`profiles/tvdata-mcp/source-registry.csv` classifies known source domains by:

- source class;
- authority level;
- role in the evidence chain;
- default quality tier.

The registry intentionally classifies authority, not truth. It never performs a network reachability check and it does not infer that a URL is temporally correct merely because its domain is authoritative.

Examples:

- TdL, responsible ministries and official legal publication services are primary sources for their respective domains;
- dbb and ver.di are social-partner / collective-bargaining-party sources;
- established aggregation/reference portals are secondary sources;
- unknown domains remain `unknown` rather than being guessed.

`assess_pay_system_provenance` returns separate pay-table and working-time source assessments for one system. `audit_source_provenance` surfaces missing, secondary-only and unclassified evidence across current tables.

## 4. 2026 provenance corrections

The P1 work exposed stale links in two otherwise current metadata records. The remuneration values were not changed.

- `tables/TV-L/Meta.csv`: the source now points to the 2026 TV-L general table valid from 1 April 2026.
- `tables/TVöD-Bund/Meta.csv`: the source now points to the current dbb TVöD consolidated text containing the Bund table valid from 1 May 2026.

These changes keep `valid_from`, table values and storage identifiers unchanged; they repair provenance only.

## 5. Guardrails

P1 does not add:

- job-equivalence inference;
- automatic equivalence between civil-service and collective-agreement grades;
- total annual compensation;
- net-pay calculations;
- employer cost;
- inflation adjustment;
- historical working-time extrapolation.

Base-pay-per-contract-hour remains an analytical normalization (`12 * monthly base / (52 * weekly hours)`), not a payroll hourly wage.

## 6. Next extensions

The next useful layer is P2, but it should depend on the P1 audit results. Candidates are:

1. expand primary-source coverage for state-specific working-time records;
2. add temporal source-consistency checks (`valid_from` versus explicitly stated source validity);
3. formalize recurring allowances and annual special payments into a validated annual-compensation profile;
4. add CPI-backed nominal/real-pay comparisons as an external adapter;
5. keep net pay and employer cost in separate calculation engines rather than embedding tax/social-insurance rules in TVData.
