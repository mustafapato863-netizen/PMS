from __future__ import annotations

from models.report_definitions import BlockConfig, ReportBlock, ReportSlide, ReportStoryMetadata, ReportTemplateDefinition


def _block(template: str, slide: int, order: int, block_type: str, slot: str, **config) -> ReportBlock:
    return ReportBlock(id=f"{template}-s{slide}-b{order}", type=block_type, slot=slot, config=BlockConfig(**config))


def _slide(template: str, order: int, title: str, layout: str, blocks: list[tuple[str, str]]) -> ReportSlide:
    return ReportSlide(id=f"{template}-s{order + 1}", title=title, layout=layout, order=order, blocks=[_block(template, order + 1, index + 1, block_type, slot) for index, (block_type, slot) in enumerate(blocks)])


def _definition(
    key: str,
    slides: list[tuple[str, str, list[tuple[str, str]]]],
    *,
    story_metadata: dict | None = None,
) -> dict:
    return ReportTemplateDefinition(
        slides=[_slide(key, index, title, layout, blocks) for index, (title, layout, blocks) in enumerate(slides)],
        story_metadata=ReportStoryMetadata.model_validate(story_metadata or {}),
    ).model_dump(mode="json")


SYSTEM_TEMPLATES = [
    {
        "template_key": "offshore_monthly_performance_review", "version": 3, "name": "Full Monthly Performance Review", "report_type": "executive",
        "description": "Recommended management story using canonical score movement, weighted KPI loss, repeated people risk and evidence confidence.",
        "definition": _definition("offshore-v3", [
            ("Cover & Reporting Scope", "cover", [("cover_title", "cover")]),
            ("Executive Summary", "kpi_chart_narrative", [("offshore_summary", "summary"), ("overall_score_comparison", "chart"), ("executive_summary", "narrative")]),
            ("Overall Score Movement", "full_width", [("overall_score_movement_bridge", "full")]),
            ("Risk Concentration", "two_blocks", [("team_risk_matrix", "left"), ("insights_summary", "right")]),
            ("Lowest KPIs by Weighted Impact", "full_width", [("lowest_kpis_weighted_impact", "full")]),
            ("Team / Position Deep Dive", "team_review", [("team_performance_overview", "overview"), ("score_trend", "trend"), ("team_performance_analysis", "analysis")]),
            ("Lowest Employees — Current Period", "full_width", [("lowest_employees_current_period", "full")]),
            ("Three-Month Repeated Risk", "full_width", [("three_month_consecutive_low_performers", "full")]),
            ("Evidence-Based Root Cause Analysis", "full_width", [("root_cause_evidence_matrix", "full")]),
            ("Existing Actions and Planning", "actions_planning", [("corrective_actions", "actions"), ("planning_progress", "planning")]),
            ("Data / Configuration Warnings", "full_width", [("applied_configuration_audit", "full")]),
            ("Decisions and Next Steps", "decisions_next_steps", [("management_commentary", "narrative"), ("decisions_required", "decisions")]),
        ], story_metadata={
            "mode": "full", "fixed_page_count": 11, "pages_per_team": 1, "recommended": True,
            "outline": ["Executive context", "Overall score movement", "Risk concentration", "Weighted KPI loss", "Team deep dives", "Current and repeated people risk", "Evidence-based causes", "Actions and planning", "Configuration warnings", "Decisions"],
        }),
    },
    {
        "template_key": "offshore_monthly_performance_review", "version": 2, "name": "Full Monthly Performance Review", "report_type": "executive",
        "description": "Recommended evidence-to-decision monthly story with one focused review page per authorized team.",
        "definition": _definition("offshore", [
            ("Cover & Reporting Scope", "cover", [("cover_title", "cover")]),
            ("Executive Summary", "kpi_chart_narrative", [("offshore_summary", "summary"), ("overall_score_comparison", "chart"), ("executive_summary", "narrative")]),
            ("Report Agenda", "full_width", [("agenda", "full")]),
            ("Overall Performance Movement", "chart_narrative", [("overall_score_comparison", "chart"), ("overall_score_movement", "narrative")]),
            ("Cross-Team Comparison", "two_blocks", [("department_ranking", "left"), ("team_risk_matrix", "right")]),
            ("Team Performance Review", "team_review", [("team_performance_overview", "overview"), ("score_trend", "trend"), ("team_performance_analysis", "analysis")]),
            ("Priority KPIs & Lost Contribution", "chart_table", [("performance_gap_drivers", "chart"), ("lost_points_analysis", "table")]),
            ("Current-Month People Risk", "two_blocks", [("bottom_performers", "left"), ("actions_summary", "right")]),
            ("Repeated Performance Risk", "full_width", [("consecutive_low_performers", "full")]),
            ("Root Cause Analysis", "two_blocks", [("root_cause_analysis", "left"), ("insights_summary", "right")]),
            ("Process Actions", "actions_planning", [("process_action_plan", "actions"), ("milestone_overview", "planning")]),
            ("Staff Actions", "process_staff_actions", [("staff_action_plan", "table_left"), ("corrective_actions", "table_right")]),
            ("Execution & Plan Status", "feedback_status", [("performance_status", "summary"), ("feedback_sessions_status", "table")]),
            ("Decisions and Next Steps", "decisions_next_steps", [("management_commentary", "narrative"), ("decisions_required", "decisions")]),
            ("Final Conclusion", "closing_page", [("final_conclusion", "full")]),
        ], story_metadata={
            "mode": "full", "fixed_page_count": 14, "pages_per_team": 1, "recommended": True,
            "outline": ["Executive context", "Overall movement", "Cross-team comparison", "Team reviews", "People and KPI risk", "Root causes", "Actions and execution", "Decisions"],
        }),
    },
    {
        "template_key": "offshore_monthly_executive_brief", "version": 1, "name": "Executive Performance Brief", "report_type": "executive",
        "description": "Compact leadership brief covering performance movement, team risk, actions, insights and decisions.",
        "definition": _definition("brief", [
            ("Cover & Reporting Scope", "cover", [("cover_title", "cover")]),
            ("Executive Overview", "kpi_chart_narrative", [("offshore_summary", "summary"), ("overall_score_comparison", "chart"), ("executive_summary", "narrative")]),
            ("Overall Movement & Team Risk", "two_blocks", [("overall_score_movement", "left"), ("team_risk_matrix", "right")]),
            ("Team Snapshot", "team_review", [("team_performance_overview", "overview"), ("score_trend", "trend"), ("team_performance_analysis", "analysis")]),
            ("Actions, Insights & Decisions", "kpi_chart_narrative", [("actions_summary", "summary"), ("insights_summary", "chart"), ("decisions_required", "narrative")]),
        ], story_metadata={
            "mode": "compact", "fixed_page_count": 4, "pages_per_team": 1, "recommended": True,
            "outline": ["Executive overview", "Overall movement and risk", "Team snapshots", "Actions, insights and decisions"],
        }),
    },
    {
        "template_key": "executive_monthly_review", "version": 1, "name": "Executive Monthly Review", "report_type": "executive",
        "description": "Organization performance, drivers, people risk, plans and decisions.",
        "definition": _definition("executive", [
            ("Cover", "cover", [("cover_title", "cover")]),
            ("Executive Summary", "kpi_chart_narrative", [("executive_kpi_summary", "summary"), ("score_trend", "chart"), ("system_analysis", "narrative")]),
            ("Performance Overview", "two_charts", [("grade_distribution", "chart_left"), ("team_ranking", "chart_right")]),
            ("Performance Drivers", "chart_narrative", [("performance_gap_drivers", "chart"), ("recommendations", "narrative")]),
            ("Team or Position Deep Dive", "chart_table", [("position_ranking", "chart"), ("kpi_performance", "table")]),
            ("People Performance", "two_tables", [("top_performers", "table_left"), ("employees_below_target", "table_right")]),
            ("Actions and Planning", "actions_planning", [("corrective_actions", "actions"), ("planning_progress", "planning")]),
            ("Decisions and Next Steps", "closing_decisions", [("management_commentary", "narrative"), ("decisions_required", "decisions")]),
        ]),
    },
    {
        "template_key": "team_performance_review", "version": 1, "name": "Team Performance Review", "report_type": "team",
        "description": "A complete monthly team performance and intervention review.",
        "definition": _definition("team", [
            ("Cover", "cover", [("cover_title", "cover")]),
            ("Team Summary", "kpi_chart_narrative", [("team_summary", "summary"), ("score_trend", "chart"), ("system_analysis", "narrative")]),
            ("KPI Performance", "full_width", [("kpi_performance", "full")]),
            ("Score Trend", "chart_narrative", [("score_trend", "chart"), ("recommendations", "narrative")]),
            ("Grade Distribution", "full_width", [("grade_distribution", "full")]),
            ("Employee Performance", "full_width", [("employee_performance", "full")]),
            ("Corrective Actions", "table_narrative", [("corrective_actions", "table"), ("management_commentary", "narrative")]),
            ("Decisions", "closing_decisions", [("next_steps", "narrative"), ("decisions_required", "decisions")]),
        ]),
    },
    {
        "template_key": "marketing_performance_review", "version": 1, "name": "Marketing Performance Review", "report_type": "position",
        "description": "Position-led marketing performance, drivers and actions.",
        "definition": _definition("marketing", [
            ("Cover", "cover", [("cover_title", "cover")]),
            ("Marketing Summary", "kpi_chart_narrative", [("team_summary", "summary"), ("score_trend", "chart"), ("system_analysis", "narrative")]),
            ("Performance by Position", "full_width", [("position_ranking", "full")]),
            ("Grade Distribution", "full_width", [("grade_distribution", "full")]),
            ("Critical Positions", "table_narrative", [("employees_below_target", "table"), ("recommendations", "narrative")]),
            ("Position Deep Dive", "chart_table", [("performance_gap_drivers", "chart"), ("kpi_performance", "table")]),
            ("Performance Drivers", "chart_narrative", [("contribution_waterfall", "chart"), ("critical_insights", "narrative")]),
            ("Actions and Next Steps", "actions_planning", [("corrective_actions", "actions"), ("planning_progress", "planning")]),
        ]),
    },
    {
        "template_key": "corrective_actions_review", "version": 1, "name": "Corrective Actions Review", "report_type": "corrective_actions",
        "description": "Corrective-action status, ownership, overdue risk and plan linkage.",
        "definition": _definition("actions", [
            ("Cover", "cover", [("cover_title", "cover")]),
            ("Action Summary", "four_kpis", [("performance_status", "summary")]),
            ("Actions by Status", "full_width", [("corrective_actions", "full")]),
            ("Overdue Actions", "table_narrative", [("corrective_actions", "table"), ("system_analysis", "narrative")]),
            ("Actions by Team", "chart_table", [("actions_by_owner", "chart"), ("corrective_actions", "table")]),
            ("Employee Actions", "full_width", [("corrective_actions", "full")]),
            ("Plan Progress", "actions_planning", [("at_risk_plans", "actions"), ("planning_progress", "planning")]),
            ("Decisions", "closing_decisions", [("management_commentary", "narrative"), ("decisions_required", "decisions")]),
        ]),
    },
    {
        "template_key": "data_quality_review", "version": 1, "name": "Data Quality Review", "report_type": "data_quality",
        "description": "Upload coverage, errors, missing configuration and required corrections.",
        "definition": _definition("quality", [
            ("Cover", "cover", [("cover_title", "cover")]),
            ("Upload Summary", "four_kpis", [("data_quality_summary", "summary")]),
            ("Valid and Rejected Rows", "full_width", [("data_quality_summary", "full")]),
            ("Error Distribution", "full_width", [("upload_error_table", "full")]),
            ("Missing Employees", "table_narrative", [("upload_error_table", "table"), ("system_analysis", "narrative")]),
            ("Missing Configuration", "full_width", [("upload_error_table", "full")]),
            ("Data Quality Details", "full_width", [("upload_error_table", "full")]),
            ("Required Corrections", "closing_decisions", [("recommendations", "narrative"), ("decisions_required", "decisions")]),
        ]),
    },
]
