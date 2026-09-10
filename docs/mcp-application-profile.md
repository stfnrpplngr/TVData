# TVData MCP application profile

TVData stores remuneration values in repository CSV files. The MCP application profile adds a semantic and temporal interpretation layer without replacing those files as the source of truth.

## Design rule

The profile follows a thin-layer principle:

1. **storage identity** remains the existing table directory, e.g. `Beamte-LSA-A`, `TV-L`, `TVöD-Bund`;
2. **semantic identity** describes regime, tariff family, scope, jurisdiction and pay-scale context;
3. **entity resolution** maps human wording to ranked canonical table ids;
4. **temporal resolution** maps an `as_of` date to the latest *known* current/archive snapshot on or before that date;
5. **analysis** consumes only resolved canonical identities and repository snapshots.

No semantic profile field changes a remuneration value.

## Canonical semantic fields

`list_pay_systems` exposes, where deterministically available:

- `table_id`: canonical repository identifier;
- `regime`: `civil_service`, `collective_agreement` or `unknown`;
- `family`: e.g. `Beamtenbesoldung`, `TV-L`, `TVöD`, `TV-N`;
- `scope`: federal, state, municipal, multi-state, employer-specific, sectoral or unknown;
- `jurisdiction_code`: stable application-profile code such as `DE-ST`, `DE`, `DE-LAENDER`;
- `jurisdiction_name_de`;
- `pay_scale`: e.g. `A`, `B`, `W`, `R`, where the storage identifier supports that interpretation;
- `variant`: storage-level subtype where applicable;
- `pay_grade_prefix`: metadata-provided grade prefix;
- aliases for entity resolution.

The profile intentionally does not invent occupational equivalence, legal equivalence or qualification mappings.

## Human entity resolution

`resolve_pay_system_entity` accepts natural terminology and returns ranked candidates plus the evidence used for matching.

Examples:

- `A13 LSA` -> `Beamte-LSA-A` with jurisdiction context `DE-ST`;
- `Bund E13` -> `TVöD-Bund` when the grade prefix and federal context support that candidate;
- `TV-L Sachsen-Anhalt` -> `TV-L`, while Sachsen-Anhalt is retained as jurisdiction context rather than being mistaken for a separate TV-L table.

The resolver reports confidence and an ambiguity warning. A low-confidence or closely tied result must not be silently selected for consequential calculations.

## Temporal resolution

`resolve_pay_table_as_of(table_id, as_of)` searches:

- the current `tables/<table_id>` directory; and
- matching `archive/<table_id>-YYYY` directories.

It selects the latest snapshot whose `valid_from` is on or before the requested date.

Accepted date formats are:

- `YYYY-MM-DD`;
- `YYYY.MM.DD`;
- `YYYY/MM/DD`;
- `DD.MM.YYYY`.

### Historical completeness guardrail

The archive is a repository history, not a statutory temporal database. Therefore:

- an archived snapshot is described as the **latest known snapshot on or before** the date;
- an interval between two snapshots does not prove that no intermediate tariff/besoldung change occurred;
- a date after the latest current `valid_from` is resolved to the latest known current snapshot with an explicit warning;
- a date before the earliest known snapshot fails rather than extrapolating backwards.

This distinction is essential for auditability.

## Date-aware tools

| Tool | Purpose |
| --- | --- |
| `resolve_pay_table_as_of` | Resolve table + date to a known snapshot. |
| `get_base_pay_at_date` | Read one grade/step from the resolved snapshot. |
| `compare_pay_positions_at_dates` | Compare 2-20 explicit positions and dates. |
| `rank_pay_positions_at_date` | Rank nominal base pay across systems using one requested date. |

Historical comparisons preserve `snapshot_id`, `snapshot_valid_from`, requested date, source and resolution status.

## Working-time rule for historical data

Current working-time metadata must not be silently projected backwards. For historical snapshots:

- working-time normalization is omitted by default unless the historical snapshot itself contains an unambiguous value;
- callers may supply an explicit `weekly_hours_override` when they have a justified historical context;
- the response identifies the basis used.

## Non-equivalence rule

A comparison between e.g. A13 and E13 is a comparison of numeric remuneration cells, not a statement that the positions are equivalent. The MCP profile keeps separate:

- employment regime;
- pay scale / tariff family;
- jurisdiction;
- base pay;
- contractual working time;
- allowances;
- pensions;
- taxes and social insurance;
- occupational duties and qualification requirements.

## Next profile extensions

The next useful extensions are deliberately downstream of this P0 layer:

1. contextual weekly-working-time resolution (e.g. TV-L + `DE-ST`);
2. versioned application-profile/schema identifier;
3. source-quality and verification metadata;
4. validated annual-compensation profiles for recurring allowances and special payments;
5. optional CPI/real-wage adapter;
6. separate net-pay and employer-cost engines.
