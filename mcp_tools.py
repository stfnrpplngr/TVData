"""MCP tool registration for TVData analytics.

Tool functions intentionally keep explicit Python signatures so the MCP SDK can
derive stable input schemas. Domain calculations live in ``mcp_analytics``,
semantic/temporal resolution in ``mcp_intelligence`` and P1 context/provenance
logic in ``mcp_context``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from mcp_analytics import (
    AnalyticsError,
    ComparisonResult,
    DataQualityReport,
    HistoryResult,
    NearestPayResult,
    PayGradeRequest,
    PayPositionRequest,
    ProgressionComparisonResult,
    ProvenanceResult,
    RankingResult,
    TableStructure,
    WorkingTimeInfo,
    audit_pay_data,
    compare_positions,
    compare_progressions,
    compare_working_time,
    find_nearest_base_pay,
    get_pay_history,
    get_provenance,
    get_table_structure,
    rank_base_pay,
)
from mcp_compensation_tools import register_compensation_tools
from mcp_context import (
    ContextualComparisonResult,
    ContextualPayPositionRequest,
    PaySystemSourceAssessment,
    ProfileManifest,
    SourceAuditReport,
    WorkingTimeResolution,
    assess_pay_system_sources,
    audit_source_quality,
    compare_pay_positions_contextual,
    get_profile_manifest,
    resolve_working_time,
)
from mcp_intelligence import (
    BasePayAsOf,
    DatedComparisonResult,
    DatedPayPositionRequest,
    DatedRankingResult,
    PaySystemResolution,
    SnapshotResolution,
    compare_pay_positions_as_of,
    get_base_pay_as_of,
    list_pay_system_catalog,
    rank_pay_positions_as_of,
    resolve_pay_snapshot,
    resolve_pay_system,
)
from mcp_profile import PaySystemIdentity


def _tool_error(exc: AnalyticsError) -> ToolError:
    return ToolError(str(exc))


def register_analytics_tools(mcp, root: Path) -> None:
    """Register higher-level, read-only tariff-analysis tools."""

    @mcp.tool()
    def get_application_profile_manifest() -> ProfileManifest:
        """Return the versioned TVData MCP application-profile manifest and guardrails."""
        try:
            return get_profile_manifest(root)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def resolve_weekly_working_time(
        table_id: str,
        jurisdiction_code: str | None = None,
        as_of: str | None = None,
        employment_context: str = "general",
    ) -> WorkingTimeResolution:
        """Resolve regular weekly working time using profile context and documented provenance."""
        try:
            return resolve_working_time(root, table_id, jurisdiction_code, as_of, employment_context)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def compare_pay_positions_with_context(
        positions: list[ContextualPayPositionRequest],
    ) -> ContextualComparisonResult:
        """Compare current pay positions while resolving jurisdiction-specific working time automatically."""
        try:
            return compare_pay_positions_contextual(root, positions)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def assess_pay_system_provenance(table_id: str) -> PaySystemSourceAssessment:
        """Classify documented pay and working-time sources by authority role and evidence quality."""
        try:
            return assess_pay_system_sources(root, table_id)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def audit_source_provenance(query: str | None = None, limit: int = 300) -> SourceAuditReport:
        """Audit source completeness and source-authority classification across current pay systems."""
        try:
            return audit_source_quality(root, query, limit)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def list_pay_systems(
        query: str | None = None,
        regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        jurisdiction_code: str | None = None,
        family: str | None = None,
        limit: int = 100,
    ) -> list[PaySystemIdentity]:
        """List canonical pay-system identities with regime, family, jurisdiction, scope and aliases."""
        try:
            return list_pay_system_catalog(root, query, regime, jurisdiction_code, family, limit)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def resolve_pay_system_entity(query: str, limit: int = 5) -> PaySystemResolution:
        """Resolve human terms such as 'A13 LSA', 'Bund E13' or 'TV-L Sachsen-Anhalt' to canonical table ids."""
        try:
            return resolve_pay_system(root, query, limit)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def resolve_pay_table_as_of(table_id: str, as_of: str) -> SnapshotResolution:
        """Resolve a canonical table and date to the latest known current/archive snapshot on or before that date."""
        try:
            return resolve_pay_snapshot(root, table_id, as_of)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def get_base_pay_at_date(table_id: str, pay_grade: str, step: str, as_of: str) -> BasePayAsOf:
        """Return base pay from the latest known repository snapshot on or before an explicit date."""
        try:
            return get_base_pay_as_of(root, table_id, pay_grade, step, as_of)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def compare_pay_positions_at_dates(positions: list[DatedPayPositionRequest]) -> DatedComparisonResult:
        """Compare 2-20 exact pay positions at explicit dates with historical-coverage guardrails."""
        try:
            return compare_pay_positions_as_of(root, positions)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def rank_pay_positions_at_date(
        pay_grade: str,
        step: str,
        as_of: str,
        table_ids: list[str] | None = None,
        query: str | None = None,
        regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        family: str | None = None,
        jurisdiction_code: str | None = None,
        limit: int = 20,
    ) -> DatedRankingResult:
        """Rank nominal base pay across latest-known snapshots on/before one date."""
        try:
            return rank_pay_positions_as_of(
                root,
                pay_grade,
                step,
                as_of,
                table_ids,
                query,
                regime,
                family,
                jurisdiction_code,
                limit,
            )
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def get_pay_table_structure(table_id: str) -> TableStructure:
        """Discover valid pay grades, steps and linked components before querying a table."""
        try:
            return get_table_structure(root, table_id)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def compare_pay_positions(positions: list[PayPositionRequest]) -> ComparisonResult:
        """Compare 2-20 exact current pay positions with comparability caveats and optional working-time overrides."""
        try:
            return compare_positions(root, positions)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def rank_pay_positions(
        pay_grade: str,
        step: str,
        table_ids: list[str] | None = None,
        query: str | None = None,
        regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        metric: Literal["monthly_base", "annual_base", "base_per_contract_hour"] = "monthly_base",
        weekly_hours_overrides: dict[str, float] | None = None,
        limit: int = 20,
    ) -> RankingResult:
        """Rank the same grade/step across current tables by base pay or working-time normalization."""
        try:
            return rank_base_pay(
                root,
                pay_grade,
                step,
                table_ids,
                query,
                regime,
                metric,
                weekly_hours_overrides,
                limit,
            )
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def compare_step_progressions(positions: list[PayGradeRequest]) -> ProgressionComparisonResult:
        """Compare step waiting times and cumulative years-to-step for 2-20 table/grade pairs."""
        try:
            return compare_progressions(root, positions)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def get_pay_history_series(table_id: str, pay_grade: str, step: str) -> HistoryResult:
        """Return current plus matching archived yearly snapshots for an exact table/grade/step."""
        try:
            return get_pay_history(root, table_id, pay_grade, step)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def get_pay_provenance(table_id: str) -> ProvenanceResult:
        """Return pay-table and working-time provenance, validity and linked compensation components."""
        try:
            return get_provenance(root, table_id)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def compare_weekly_working_time(table_ids: list[str]) -> list[WorkingTimeInfo]:
        """Compare documented regular weekly working time and provenance across pay systems."""
        try:
            return compare_working_time(root, table_ids)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def find_nearest_pay_positions(
        reference: PayPositionRequest,
        candidate_table_ids: list[str] | None = None,
        candidate_query: str | None = None,
        candidate_regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        candidate_grade_prefix: str | None = None,
        limit: int = 10,
    ) -> NearestPayResult:
        """Find nearest nominal base-pay cells without claiming job, grade or status equivalence."""
        try:
            return find_nearest_base_pay(
                root,
                reference,
                candidate_table_ids,
                candidate_query,
                candidate_regime,
                candidate_grade_prefix,
                limit,
            )
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    @mcp.tool()
    def audit_pay_data_quality(query: str | None = None, limit: int = 200) -> DataQualityReport:
        """Audit current pay-table metadata, provenance and numeric matrix integrity for comparison readiness."""
        try:
            return audit_pay_data(root, query, limit)
        except AnalyticsError as exc:
            raise _tool_error(exc) from exc

    register_compensation_tools(mcp, root)
