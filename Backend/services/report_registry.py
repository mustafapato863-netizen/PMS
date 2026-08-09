from __future__ import annotations

from copy import deepcopy
from typing import Any


BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    "cover_title": {"name": "Cover", "category": "Narrative", "description": "Report title, scope and reporting period.", "icon": "presentation", "provider": "cover", "slots": ["cover"], "permissions": ["view_reports"]},
    "executive_kpi_summary": {"name": "Executive KPI Summary", "category": "Summary", "description": "Authorized score, workforce, below-target and risk metrics.", "icon": "layout-dashboard", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"], "default": {"metrics": ["average_score", "total_employees", "employees_below_target", "critical_risks"]}},
    "team_summary": {"name": "Team Summary", "category": "Summary", "description": "Performance summary for the selected team scope.", "icon": "users", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"]},
    "team_performance_overview": {"name": "Team Performance Overview", "category": "Summary", "display_category": "Teams & People", "source_page": "Team Dashboard", "description": "Team score, population, grade mix and weighted KPI status from the selected period.", "icon": "layout-dashboard", "provider": "team_overview", "slots": ["overview", "summary", "full"], "permissions": ["view_reports"]},
    "team_performance_analysis": {"name": "Team Performance Analysis", "category": "Analysis", "display_category": "Insights & Drivers", "source_page": "Team Dashboard", "description": "Canonical KPI drivers, target gaps and recommended focus for the selected team.", "icon": "lightbulb", "provider": "team_analysis", "slots": ["analysis", "insights", "narrative", "full"], "permissions": ["view_reports"]},
    "actions_summary": {"name": "Actions Summary", "category": "Summary", "display_category": "Actions & Planning", "source_page": "Executive Summary", "description": "Corrective-action volume, employee coverage, status and root-cause mix.", "icon": "clipboard-check", "provider": "actions_summary", "slots": ["summary", "actions", "left", "right", "full"], "permissions": ["view_actions"]},
    "insights_summary": {"name": "Insights Summary", "category": "Drivers and Insights", "display_category": "Insights & Drivers", "source_page": "Insights", "description": "Highest-impact insight, analysis coverage and decision-ready focus from the canonical workspace.", "icon": "scan-search", "provider": "insights_summary", "slots": ["chart", "insights", "narrative", "left", "right", "full"], "permissions": ["view_reports"]},
    "team_risk_matrix": {"name": "Team Risk Matrix", "category": "Drivers and Insights", "display_category": "Insights & Drivers", "source_page": "Insights", "description": "Authorized team score, trend, critical risk and main-cause comparison.", "icon": "table-properties", "provider": "team_risk_matrix", "slots": ["chart", "table", "left", "right", "full"], "permissions": ["view_reports"]},
    "position_summary": {"name": "Position Summary", "category": "Summary", "description": "Performance summary grouped by position.", "icon": "briefcase", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"]},
    "employee_summary": {"name": "Employee Summary", "category": "Summary", "description": "Individual performance overview.", "icon": "user", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"]},
    "performance_status": {"name": "Performance Status", "category": "Summary", "description": "Grade and status overview.", "icon": "gauge", "provider": "summary", "slots": ["summary", "chart", "full"], "permissions": ["view_reports"]},
    "score_trend": {"name": "Score Trend", "category": "Performance", "description": "Real average score trend across available periods.", "icon": "trending-up", "provider": "trend", "slots": ["chart", "chart_left", "chart_right", "full"], "permissions": ["view_reports"]},
    "grade_distribution": {"name": "Grade Distribution", "category": "Performance", "description": "Distribution of measured performance grades.", "icon": "chart-bar", "provider": "grade_distribution", "slots": ["chart", "chart_left", "chart_right", "table", "full"], "permissions": ["view_reports"]},
    "team_ranking": {"name": "Team Ranking", "category": "Performance", "description": "Authorized team ranking by average score.", "icon": "ranking", "provider": "team_ranking", "slots": ["table", "chart", "full"], "permissions": ["view_reports"]},
    "position_ranking": {"name": "Position Ranking", "category": "Performance", "description": "Position ranking by average score.", "icon": "ranking", "provider": "position_ranking", "slots": ["table", "chart", "full"], "permissions": ["view_reports"]},
    "kpi_performance": {"name": "KPI Performance", "category": "Performance", "description": "Actual, target and contribution by KPI.", "icon": "table", "provider": "kpi", "slots": ["table", "chart", "full"], "permissions": ["view_reports"]},
    "performance_gap_drivers": {"name": "Performance Gap Drivers", "category": "Drivers and Insights", "description": "Weighted KPIs widening or closing the performance gap.", "icon": "git-compare", "provider": "drivers", "slots": ["chart", "chart_left", "chart_right", "full"], "permissions": ["view_reports"]},
    "contribution_waterfall": {"name": "Contribution Waterfall", "category": "Drivers and Insights", "description": "KPI contribution movement by impact.", "icon": "chart-column", "provider": "drivers", "slots": ["chart", "full"], "permissions": ["view_reports"]},
    "top_performers": {"name": "Top Performers", "category": "People", "description": "Highest measured employees in the scope.", "icon": "award", "provider": "top_people", "slots": ["table", "table_left", "table_right", "full"], "permissions": ["view_reports"]},
    "bottom_performers": {"name": "Bottom Performers", "category": "People", "description": "Lowest measured employees in the scope.", "icon": "users", "provider": "bottom_people", "slots": ["table", "table_left", "table_right", "full"], "permissions": ["view_reports"]},
    "employees_below_target": {"name": "Employees Below Target", "category": "People", "description": "Employees whose score is below the configured threshold.", "icon": "user-round-x", "provider": "below_target", "slots": ["table", "table_left", "table_right", "full"], "permissions": ["view_reports"]},
    "employee_performance": {"name": "Employee Performance", "category": "People", "description": "Detailed employee score, grade and status table.", "icon": "table", "provider": "employee_table", "slots": ["table", "full"], "permissions": ["view_reports"]},
    "corrective_actions": {"name": "Corrective Actions", "category": "Actions and Planning", "description": "Open and completed corrective actions in scope.", "icon": "clipboard-check", "provider": "actions", "slots": ["table", "actions", "full"], "permissions": ["view_actions"]},
    "planning_progress": {"name": "Planning Progress", "category": "Actions and Planning", "description": "Performance-plan progress and status.", "icon": "list-checks", "provider": "plans", "slots": ["chart", "planning", "full"], "permissions": ["view_plans"]},
    "milestone_overview": {"name": "Milestone Overview", "category": "Actions and Planning", "description": "Plan milestone status summary.", "icon": "flag", "provider": "milestones", "slots": ["table", "planning", "full"], "permissions": ["view_plans"]},
    "at_risk_plans": {"name": "At-Risk Plans", "category": "Actions and Planning", "description": "Plans requiring intervention.", "icon": "triangle-alert", "provider": "at_risk_plans", "slots": ["table", "actions", "full"], "permissions": ["view_plans"]},
    "actions_by_owner": {"name": "Actions by Owner", "category": "Actions and Planning", "description": "Corrective actions grouped by accountable owner.", "icon": "user-check", "provider": "actions_by_owner", "slots": ["chart", "actions", "full"], "permissions": ["view_actions"]},
    "critical_insights": {"name": "Critical Insights", "category": "Drivers and Insights", "description": "Highest-impact evidence from authorized KPI data.", "icon": "lightbulb", "provider": "drivers", "slots": ["insights", "narrative", "full"], "permissions": ["view_reports"]},
    "recommendations": {"name": "Recommendations", "category": "Narrative", "description": "Evidence-based recommended focus areas.", "icon": "sparkles", "provider": "recommendations", "slots": ["narrative", "decisions", "full"], "permissions": ["view_reports"]},
    "decisions_required": {"name": "Decisions Required", "category": "Narrative", "description": "Decision prompts derived from material gaps.", "icon": "circle-help", "provider": "decisions", "slots": ["decisions", "narrative", "full"], "permissions": ["view_reports"]},
    "system_analysis": {"name": "System Analysis", "category": "Narrative", "description": "Deterministic evidence-based PMS analysis.", "icon": "bot", "provider": "narrative", "slots": ["narrative", "full"], "permissions": ["view_reports"]},
    "management_commentary": {"name": "Management Commentary", "category": "Narrative", "description": "Manager-authored context stored separately from system analysis.", "icon": "message-square", "provider": "commentary", "slots": ["narrative", "commentary", "full"], "permissions": ["view_reports"]},
    "next_steps": {"name": "Next Steps", "category": "Narrative", "description": "Prioritized follow-up actions.", "icon": "list-todo", "provider": "recommendations", "slots": ["decisions", "narrative", "full"], "permissions": ["view_reports"]},
    "data_quality_summary": {"name": "Data Quality Summary", "category": "Data Quality", "description": "Upload volume, success and error status.", "icon": "shield-check", "provider": "data_quality", "slots": ["summary", "chart", "full"], "permissions": ["view_reports"]},
    "upload_error_table": {"name": "Upload Error Table", "category": "Data Quality", "description": "Available source upload errors and affected teams.", "icon": "table-properties", "provider": "upload_errors", "slots": ["table", "full"], "permissions": ["view_reports"]},
}

BLOCK_REGISTRY.update({
    "overall_score_movement_bridge": {"name": "Overall PMS Score Movement Bridge", "category": "Drivers and Insights", "description": "Reconciles adjacent-month score movement across KPI, population, scope, configuration and residual effects.", "icon": "waypoints", "provider": "overall_score_movement_bridge", "slots": ["chart", "chart_left", "chart_right", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "lowest_kpis_weighted_impact": {"name": "Lowest KPIs by Weighted Lost Points", "category": "Drivers and Insights", "description": "Ranks valid scored KPIs by normalized weighted lost points and separates configuration exclusions.", "icon": "chart-no-axes-column-decreasing", "provider": "lowest_kpis_weighted_impact", "slots": ["table", "chart", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "lowest_employees_current_period": {"name": "Lowest Employees — Current Period", "category": "People", "description": "Lowest current-period employees with canonical classification, KPI loss and intervention evidence.", "icon": "user-round-search", "provider": "lowest_employees_current_period", "slots": ["table", "table_left", "table_right", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "three_month_consecutive_low_performers": {"name": "Three-Consecutive-Month Low Performers", "category": "People", "description": "Employees below the accepted threshold for three exact valid calendar months.", "icon": "calendar-clock", "provider": "three_month_consecutive_low_performers", "slots": ["table", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "applied_configuration_audit": {"name": "Applied Configuration Audit", "category": "Data Quality", "description": "Diagnostic comparison of persisted evidence and the effective period-applied KPI configuration.", "icon": "list-checks", "provider": "applied_configuration_audit", "slots": ["table", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "root_cause_evidence_matrix": {"name": "Evidence-Based Root Cause Matrix", "category": "Drivers and Insights", "description": "Separates process, staff, combined, data/configuration and unclassified causes by evidence confidence.", "icon": "scan-search", "provider": "root_cause_evidence_matrix", "slots": ["insights", "narrative", "table", "full"], "permissions": ["view_reports"], "default": {"row_limit": 10}},
    "agenda": {"name": "Agenda", "category": "Narrative", "description": "Generated report-page agenda.", "icon": "list", "provider": "agenda", "slots": ["full", "narrative"], "permissions": ["view_reports"]},
    "offshore_summary": {"name": "Offshore Summary", "category": "Summary", "description": "Authorized offshore performance and population summary.", "icon": "building-2", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"]},
    "department_summary": {"name": "Department Summary", "category": "Summary", "description": "Selected department score and movement summary.", "icon": "users", "provider": "summary", "slots": ["summary", "full"], "permissions": ["view_reports"]},
    "overall_score_comparison": {"name": "Overall Score Comparison", "category": "Performance", "description": "Primary versus explicitly selected comparison period.", "icon": "git-compare", "provider": "score_comparison", "slots": ["chart", "chart_left", "chart_right", "full"], "permissions": ["view_reports"]},
    "actual_vs_target": {"name": "Actual vs Target", "category": "Performance", "description": "Normalized KPI actual, target, achievement and gap.", "icon": "target", "provider": "kpi", "slots": ["chart", "table", "full"], "permissions": ["view_reports"]},
    "department_ranking": {"name": "Department Ranking", "category": "Performance", "description": "Authorized department ranking by final PMS score.", "icon": "ranking", "provider": "team_ranking", "slots": ["chart", "table", "full"], "permissions": ["view_reports"]},
    "weighted_performance_gap": {"name": "Weighted Performance Gap", "category": "Performance", "description": "Weighted gap using existing KPI contribution values.", "icon": "chart-no-axes-combined", "provider": "drivers", "slots": ["chart", "full"], "permissions": ["view_reports"]},
    "lost_points_analysis": {"name": "Lost-Points Analysis", "category": "Performance", "description": "Lowest KPIs ranked by weighted lost points, not raw units.", "icon": "trending-down", "provider": "lowest_kpis", "slots": ["table", "chart", "full"], "permissions": ["view_reports"]},
    "lowest_employees": {"name": "Lowest Employees", "category": "People", "description": "Lowest final PMS scores with KPI, action and feedback context.", "icon": "users-round", "provider": "lowest_people", "slots": ["table", "full"], "permissions": ["view_reports"]},
    "consecutive_low_performers": {"name": "Three-Month Consecutive Low Performers", "category": "People", "description": "Employees below threshold in three consecutive valid months.", "icon": "calendar-range", "provider": "consecutive_low", "slots": ["table", "full"], "permissions": ["view_reports"]},
    "overall_score_movement": {"name": "Overall Score Movement Explanation", "category": "Analysis", "description": "Contribution-based reconciliation of primary versus comparison score.", "icon": "route", "provider": "movement", "slots": ["narrative", "chart", "full"], "permissions": ["view_reports"]},
    "lowest_indicators": {"name": "Lowest Indicators", "category": "Analysis", "description": "High-weight indicators producing the largest normalized loss.", "icon": "list-ordered", "provider": "lowest_kpis", "slots": ["table", "insights", "full"], "permissions": ["view_reports"]},
    "root_cause_analysis": {"name": "Root Cause Analysis", "category": "Analysis", "description": "Confirmed causes, likely factors and data issues with evidence labels.", "icon": "search-check", "provider": "root_causes", "slots": ["insights", "narrative", "full"], "permissions": ["view_reports"]},
    "process_issues": {"name": "Process Issues", "category": "Analysis", "description": "Provisional evidence associated with workflow, system or process constraints.", "icon": "workflow", "provider": "process_issues", "slots": ["insights", "narrative", "full"], "permissions": ["view_reports"]},
    "staff_issues": {"name": "Staff Issues", "category": "Analysis", "description": "Provisional evidence associated with coaching, attendance or individual performance.", "icon": "user-cog", "provider": "staff_issues", "slots": ["insights", "narrative", "full"], "permissions": ["view_reports"]},
    "opportunities": {"name": "Opportunities", "category": "Analysis", "description": "Measured improvements that can offset score gaps.", "icon": "lightbulb", "provider": "drivers", "slots": ["insights", "narrative", "full"], "permissions": ["view_reports"]},
    "process_action_plan": {"name": "Process Action Plan", "category": "Actions", "description": "Quantified process actions from existing Planning and Actions.", "icon": "workflow", "provider": "process_actions", "slots": ["actions", "table_left", "full"], "permissions": ["view_actions"]},
    "staff_action_plan": {"name": "Staff Action Plan", "category": "Actions", "description": "Quantified staff coaching, training and PIP actions.", "icon": "user-check", "provider": "staff_actions", "slots": ["actions", "table_right", "full"], "permissions": ["view_actions"]},
    "feedback_sessions_status": {"name": "Feedback Sessions Status", "category": "Actions", "description": "Status derived from existing feedback/coaching corrective actions.", "icon": "messages-square", "provider": "feedback", "slots": ["actions", "table", "full"], "permissions": ["view_actions"]},
    "executive_summary": {"name": "Executive Summary", "category": "Narrative", "description": "Evidence-to-decision monthly summary.", "icon": "file-text", "provider": "narrative", "slots": ["narrative", "full"], "permissions": ["view_reports"]},
    "final_conclusion": {"name": "Final Conclusion", "category": "Narrative", "description": "Cross-department conclusion and material decision summary.", "icon": "flag", "provider": "narrative", "slots": ["narrative", "full"], "permissions": ["view_reports"]},
    "missing_period_data": {"name": "Missing Period Data", "category": "Data Quality", "description": "Missing primary, comparison or history periods.", "icon": "calendar-x", "provider": "data_quality", "slots": ["table", "full"], "permissions": ["view_reports"]},
    "invalid_targets": {"name": "Invalid Targets", "category": "Data Quality", "description": "Missing or zero KPI targets in the selected scope.", "icon": "target", "provider": "data_quality", "slots": ["table", "full"], "permissions": ["view_reports"]},
    "missing_configuration": {"name": "Missing Configuration", "category": "Data Quality", "description": "Incomplete KPI weights, targets or employee assignments.", "icon": "settings", "provider": "data_quality", "slots": ["table", "full"], "permissions": ["view_reports"]},
})


ALL_BLOCK_CATEGORIES = sorted({item["category"] for item in BLOCK_REGISTRY.values()})

DISPLAY_CATEGORY_MAP = {
    "Summary": "Executive Summary",
    "Performance": "Performance",
    "People": "Teams & People",
    "Tables": "Teams & People",
    "Analysis": "Insights & Drivers",
    "Drivers and Insights": "Insights & Drivers",
    "Actions": "Actions & Planning",
    "Actions and Planning": "Actions & Planning",
    "Narrative": "Narrative",
    "Data Quality": "Data Quality",
}


LAYOUT_REGISTRY: dict[str, dict[str, Any]] = {
    "cover": {"slots": {"cover": ["Narrative"]}, "max_blocks": 1},
    "full_width": {"slots": {"full": ["Summary", "Performance", "People", "Drivers and Insights", "Actions and Planning", "Narrative", "Tables", "Data Quality"]}, "max_blocks": 1},
    "two_blocks": {"slots": {"left": ALL_BLOCK_CATEGORIES, "right": ALL_BLOCK_CATEGORIES}, "max_blocks": 2},
    "four_kpis": {"slots": {"summary": ["Summary", "Data Quality"]}, "max_blocks": 1},
    "kpi_chart": {"slots": {"summary": ["Summary"], "chart": ["Performance", "Drivers and Insights", "Data Quality"]}, "max_blocks": 2},
    "kpi_chart_narrative": {"slots": {"summary": ["Summary"], "chart": ["Performance", "Drivers and Insights"], "narrative": ["Narrative"]}, "max_blocks": 3},
    "two_charts": {"slots": {"chart_left": ["Performance", "Drivers and Insights"], "chart_right": ["Performance", "Drivers and Insights"]}, "max_blocks": 2},
    "chart_table": {"slots": {"chart": ["Performance", "Drivers and Insights", "Actions and Planning", "Data Quality"], "table": ["People", "Tables", "Performance", "Actions and Planning", "Data Quality"]}, "max_blocks": 2},
    "chart_narrative": {"slots": {"chart": ["Performance", "Drivers and Insights"], "narrative": ["Narrative", "Analysis", "Drivers and Insights"]}, "max_blocks": 2},
    "table_narrative": {"slots": {"table": ["People", "Tables", "Performance", "Actions and Planning", "Data Quality"], "narrative": ["Narrative"]}, "max_blocks": 2},
    "two_tables": {"slots": {"table_left": ["People", "Tables", "Actions and Planning"], "table_right": ["People", "Tables", "Actions and Planning"]}, "max_blocks": 2},
    "comparison": {"slots": {"chart_left": ["Summary", "Performance"], "chart_right": ["Summary", "Performance"]}, "max_blocks": 2},
    "risk_actions": {"slots": {"insights": ["Drivers and Insights"], "actions": ["Actions and Planning"]}, "max_blocks": 2},
    "insights_decisions": {"slots": {"insights": ["Drivers and Insights"], "decisions": ["Narrative"]}, "max_blocks": 2},
    "actions_planning": {"slots": {"actions": ["Actions", "Actions and Planning"], "planning": ["Actions", "Actions and Planning"]}, "max_blocks": 2},
    "closing_decisions": {"slots": {"narrative": ["Narrative"], "decisions": ["Narrative"]}, "max_blocks": 2},
    "department_divider": {"slots": {"full": ["Narrative", "Summary"]}, "max_blocks": 1},
    "root_cause_actions": {"slots": {"insights": ["Analysis", "Drivers and Insights"], "actions": ["Actions", "Actions and Planning"]}, "max_blocks": 2},
    "process_staff_actions": {"slots": {"table_left": ["Actions", "Actions and Planning"], "table_right": ["Actions", "Actions and Planning"]}, "max_blocks": 2},
    "feedback_status": {"slots": {"summary": ["Summary", "Actions"], "table": ["Actions", "Actions and Planning"]}, "max_blocks": 2},
    "decisions_next_steps": {"slots": {"narrative": ["Narrative"], "decisions": ["Narrative", "Actions"]}, "max_blocks": 2},
    "closing_page": {"slots": {"full": ["Narrative"]}, "max_blocks": 1},
    "team_review": {"slots": {"overview": ["Summary"], "trend": ["Performance"], "analysis": ["Analysis", "Drivers and Insights"]}, "max_blocks": 3},
}


def public_block_registry() -> list[dict[str, Any]]:
    blocks = []
    for key, value in BLOCK_REGISTRY.items():
        item = deepcopy(value)
        item.setdefault("display_category", DISPLAY_CATEGORY_MAP.get(item["category"], item["category"]))
        item.setdefault("source_page", "Report Builder")
        blocks.append({"type": key, **item})
    return blocks


def public_layout_registry() -> list[dict[str, Any]]:
    return [{"key": key, **deepcopy(value)} for key, value in LAYOUT_REGISTRY.items()]


def validate_definition(definition) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    slide_ids: set[str] = set()
    block_ids: set[str] = set()
    for slide in definition.slides:
        if slide.id in slide_ids:
            issues.append({"severity": "error", "code": "duplicate_slide", "message": "Slide IDs must be unique", "slide_id": slide.id})
        slide_ids.add(slide.id)
        layout = LAYOUT_REGISTRY.get(slide.layout)
        if not layout:
            issues.append({"severity": "error", "code": "unknown_layout", "message": f"Unknown layout: {slide.layout}", "slide_id": slide.id})
            continue
        if len(slide.blocks) > layout["max_blocks"]:
            issues.append({"severity": "error", "code": "layout_overflow", "message": "The slide contains more blocks than its layout supports", "slide_id": slide.id})
        used_slots: set[str] = set()
        for block in slide.blocks:
            registry = BLOCK_REGISTRY.get(block.type)
            if block.id in block_ids:
                issues.append({"severity": "error", "code": "duplicate_block", "message": "Block IDs must be unique", "slide_id": slide.id, "block_id": block.id})
            block_ids.add(block.id)
            if not registry:
                issues.append({"severity": "error", "code": "unknown_block", "message": f"Unknown block type: {block.type}", "slide_id": slide.id, "block_id": block.id})
                continue
            if block.slot not in layout["slots"] or registry["category"] not in layout["slots"].get(block.slot, []):
                issues.append({"severity": "error", "code": "incompatible_block", "message": f"{registry['name']} is not compatible with slot {block.slot}", "slide_id": slide.id, "block_id": block.id})
            if block.slot in used_slots:
                issues.append({"severity": "error", "code": "duplicate_slot", "message": f"Slot {block.slot} already contains a block", "slide_id": slide.id, "block_id": block.id})
            used_slots.add(block.slot)
    return issues
