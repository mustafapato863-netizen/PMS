from fastapi import APIRouter, Depends, Query, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
import io
from typing import List
from datetime import datetime

from api.dependencies import (
    performance_repo,
    planning_service,
    insights_service,
    serialize_performance_record,
    require_role,
    get_current_user_scope,
    filter_records_by_scope,
    user_can_access_team,
    user_can_access_team_level,
    require_authenticated_scope,
)
from utils.report_scope import filter_records_by_team_levels
from config.database import get_db
from sqlalchemy.orm import Session
from models.schemas import StandardResponse
from exports.report_exporter import ReportExporter
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository
from utils.performance_levels import normalize_performance_level
from config.loader import ConfigurationError, load_team_config, resolve_team_config
from services.balanced_scorecard_service import BalancedScorecardService
from services.bsc_template_service import bsc_template_service
from services.management_bsc_service import ManagementBSCService, ManagementBSCSchemaError
from services.dashboard_record_service import DashboardRecordService
from api.middleware.rbac_middleware import require_permission
from services.upload_security import read_validated_excel
from models.report_schemas import MONTHS

router = APIRouter(prefix="/performance", tags=["Performance"])


def _management_base_config(team: str, level: str) -> dict:
    return {
        "team": team,
        "db_name": team,
        "region": "UAE",
        "employee_id_col": "Employee ID",
        "employee_name_col": "Employee Name",
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "kpis": [
            {
                "key": "management_placeholder",
                "label": "Management Placeholder",
                "weight": 1.0,
                "direction": "higher_better",
                "unit": "%",
                "color": "#10B981",
                "actual_col": "Actual Value",
                "target_col": "Target Value",
                "achievement_col": "Score %",
            }
        ],
        "performance_levels": {
            level: {
                "balanced_scorecard": {
                    "enabled": True,
                    "perspectives": [
                        {"key": "Financial", "label": "Financial", "display_order": 1, "icon_key": "wallet"},
                        {"key": "Customer", "label": "Customer", "display_order": 2, "icon_key": "users"},
                        {"key": "Internal Process", "label": "Internal Process", "display_order": 3, "icon_key": "settings"},
                        {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4, "icon_key": "graduation-cap"},
                    ],
                    "strategy_map_links": [
                        {"from": "Learning & Growth", "to": "Internal Process"},
                        {"from": "Internal Process", "to": "Customer"},
                        {"from": "Customer", "to": "Financial"},
                    ],
                },
                "kpis": [],
            }
        },
    }


def _level_filter(value: str | None) -> str | None:
    try:
        normalized = normalize_performance_level(value, allow_all=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return None if normalized == "All" else normalized


def _get_dashboard_records(
    db: Session,
    team: str | None = None,
    month: str | None = None,
    employee_id: str | None = None,
    grade: str | None = None,
    status: str | None = None,
    performance_level: str | None = None,
    year: int | None = None,
    position: str | None = None,
    region: str | None = None,
):
    return DashboardRecordService(
        db,
        sql_repository_cls=SQLPerformanceRepository,
    ).list_records(
        team=team,
        month=month,
        employee_id=employee_id,
        grade=grade,
        status=status,
        performance_level=performance_level,
        year=year,
        position=position,
        region=region,
    )


@router.get("/balanced-scorecard", response_model=StandardResponse)
def get_balanced_scorecard(
    request: Request,
    db: Session = Depends(get_db),
    team: str = Query(...),
    performance_level: str = Query(...),
    month: str = Query("All"),
    year: int | None = Query(None, ge=2000, le=2100),
    branch: str | None = Query(None),
    employee_ids: List[str] = Query(default=[]),
    history_months: int = Query(6, ge=1, le=24),
    selected_kpi: str | None = Query(None),
):
    level = _level_filter(performance_level)
    if level not in {"Managerial", "Corporate"}:
        raise HTTPException(status_code=422, detail="Balanced Scorecard supports Managerial and Corporate only")
    if branch and branch.lower() != "all":
        raise HTTPException(status_code=422, detail="Branch filtering is not configured for this team")

    scope = require_authenticated_scope(db, request)
    if not user_can_access_team_level(scope, team, level):
        raise HTTPException(status_code=403, detail="Access denied for this team and performance level")

    try:
        config = resolve_team_config(load_team_config(team), level)
    except ConfigurationError:
        config = resolve_team_config(_management_base_config(team, level), level)
    if not config.get("balanced_scorecard", {}).get("enabled"):
        raise HTTPException(status_code=404, detail="Balanced Scorecard is not configured for this context")

    records = _get_dashboard_records(db, team=team, performance_level=level)
    records = filter_records_by_scope(records, scope)
    available_ids = {str(getattr(record, "employee_id", None) or record.get("employee_id")) for record in records}
    requested_ids = set(employee_ids)
    is_self_scoped = scope.get("role") in {"Agent", "Executive"}
    if is_self_scoped:
        self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
        authorized_ids = available_ids | ({self_id} if self_id else set())
        if requested_ids - authorized_ids:
            raise HTTPException(status_code=403, detail="One or more selected people are outside the authorized context")
        employee_ids = employee_ids or sorted(authorized_ids)

    management_service = ManagementBSCService(db)
    try:
        data = management_service.build_scorecard_dataset(
            team_name=team,
            performance_level=level,
            month=month,
            year=year,
            employee_ids=employee_ids,
            history_months=history_months,
            selected_kpi=selected_kpi,
            base_config=config,
        )
    except ManagementBSCSchemaError as exc:
        raise HTTPException(status_code=500, detail="Failed to load performance records.") from exc
    dataset_ids = {item["employee_id"] for item in data.get("available_people", [])}
    if not is_self_scoped and requested_ids - (available_ids | dataset_ids):
        raise HTTPException(status_code=403, detail="One or more selected people are outside the authorized context")
    return StandardResponse(success=True, message="Balanced Scorecard retrieved successfully", data=data)


@router.get("/balanced-scorecard/template/download")
def download_balanced_scorecard_template(
    _user=Depends(require_permission("view_reports")),
):
    template_path = bsc_template_service.template_path()
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Management Overview template is not available")
    return FileResponse(
        path=template_path,
        filename=template_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/balanced-scorecard/template/upload", response_model=StandardResponse)
async def upload_balanced_scorecard_template(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    _user=Depends(require_permission("upload_data")),
):
    contents = await read_validated_excel(file, allowed_extensions=(".xlsx",))
    uploaded_by = _user.get("username", "Admin") if isinstance(_user, dict) else "Admin"
    try:
        rows = bsc_template_service.parse_upload(contents)
        result = ManagementBSCService(db).import_template_rows(
            rows=rows,
            updated_by=uploaded_by,
            source_filename=file.filename,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ManagementBSCSchemaError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process the scorecard template.") from exc
    return StandardResponse(
        success=True,
        message="Management Overview template uploaded successfully",
        data={
            "filename": file.filename,
            "sheet_name": bsc_template_service.sheet_name,
            **bsc_template_service.summarize_rows(rows),
            **result,
        },
    )

@router.get("", response_model=StandardResponse)
def get_all_records(
    request: Request,
    db: Session = Depends(get_db),
    team: str = Query(None, alias="team"),
    month: str = Query(None),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        if team and not user_can_access_team(scope, team):
            raise HTTPException(status_code=403, detail="Access denied for this team")

        records = _get_dashboard_records(
            db,
            team=team,
            month=month,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        records = filter_records_by_scope(records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records",
            data=[serialize_performance_record(r) for r in records]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        import logging
        logging.getLogger(__name__).error("Failed to fetch performance records: %s\n%s", e, traceback.format_exc())
        return StandardResponse(
            success=False,
            message=f"Failed to fetch performance records: {e}"
        )


@router.get("/catalog", response_model=StandardResponse)
def get_performance_catalog(
    request: Request,
    db: Session = Depends(get_db),
):
    """Lightweight authorized dimensions for the global application shell."""
    scope = get_current_user_scope(db, request)
    rows = DashboardRecordService(
        db,
        sql_repository_cls=SQLPerformanceRepository,
    ).list_option_rows()
    rows = filter_records_by_scope(rows, scope)
    rows = filter_records_by_team_levels(rows, scope)

    periods = sorted(
        {
            (int(row["year"]), MONTHS[str(row["month"])], str(row["month"]))
            for row in rows
            if row.get("year") and str(row.get("month")) in MONTHS
        },
        reverse=True,
    )
    scopes = sorted(
        {
            (
                str(row.get("team") or ""),
                str(row.get("region") or ""),
                str(row.get("performance_level") or "Employee"),
                str(row.get("position") or ""),
            )
            for row in rows
            if row.get("team")
        }
    )
    return StandardResponse(
        success=True,
        message="Authorized performance catalog retrieved",
        data={
            "periods": [
                {"year": year, "month": month, "key": f"{year}-{month_number:02d}"}
                for year, month_number, month in periods
            ],
            "months": [
                month
                for month in MONTHS
                if any(period_month == month for _, _, period_month in periods)
            ],
            "scopes": [
                {
                    "team": team,
                    "region": region or None,
                    "performance_level": performance_level,
                    "position": position or None,
                }
                for team, region, performance_level, position in scopes
            ],
        },
    )


@router.get("/records", response_model=StandardResponse)
def get_monthly_records(
    request: Request,
    db: Session = Depends(get_db),
    team: str = Query(None, alias="team"),
    month: str = Query(None),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        if team and not user_can_access_team(scope, team):
            raise HTTPException(status_code=403, detail="Access denied for this team")

        records = _get_dashboard_records(
            db,
            team=team,
            month=month,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        records = filter_records_by_scope(records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(records)} performance records",
            data=[serialize_performance_record(r) for r in records]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message="Failed to fetch performance records."
        )


@router.get("/employee/{emp_id}", response_model=StandardResponse)
def get_employee_history(
    emp_id: str,
    request: Request,
    db: Session = Depends(get_db),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        records = _get_dashboard_records(
            db,
            employee_id=emp_id,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        records = filter_records_by_scope(records, scope)
        emp_records = records
        from services.planning_service import MONTH_ORDER
        emp_records.sort(key=lambda x: (x.year or 0, MONTH_ORDER.get(x.month, 0)))

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(emp_records)} performance records for employee",
            data=[serialize_performance_record(r) for r in emp_records]
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message="Failed to fetch employee performance history."
        )


@router.get("/team/{team_name}", response_model=StandardResponse)
def get_team_yearly_records(
    team_name: str,
    request: Request,
    db: Session = Depends(get_db),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        team_records = _get_dashboard_records(
            db,
            team=team_name,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        team_records = filter_records_by_scope(team_records, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(team_records)} performance records for team",
            data=[serialize_performance_record(r) for r in team_records]
        )
    except Exception as e:
        return StandardResponse(
            success=False,
            message="Failed to fetch team performance records."
        )


@router.get("/grade/{team_name}", response_model=StandardResponse)
def get_by_grade(
    team_name: str,
    request: Request,
    db: Session = Depends(get_db),
    grade: str = Query(...),
    month: str = Query(...),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        filtered = _get_dashboard_records(
            db,
            team=team_name,
            month=month,
            grade=grade,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        filtered = filter_records_by_scope(filtered, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(filtered)} records with grade {grade}",
            data=[serialize_performance_record(r) for r in filtered]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message="Failed to fetch records by grade."
        )


@router.get("/status/{team_name}", response_model=StandardResponse)
def get_by_status(
    team_name: str,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Query(...),
    month: str = Query(...),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
):
    try:
        if not month:
            raise HTTPException(status_code=400, detail="month is required")

        scope = get_current_user_scope(db, request)
        if not user_can_access_team(scope, team_name):
            raise HTTPException(status_code=403, detail="Access denied for this team")
        filtered = _get_dashboard_records(
            db,
            team=team_name,
            month=month,
            status=status,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        filtered = filter_records_by_scope(filtered, scope)

        return StandardResponse(
            success=True,
            message=f"Retrieved {len(filtered)} records with status {status}",
            data=[serialize_performance_record(r) for r in filtered]
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(
            success=False,
            message="Failed to fetch records by status."
        )


@router.get("/planning", response_model=StandardResponse)
def get_planning_categories(
    month: str = Query(...),
    performance_level: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        categories = planning_service.classify_all(month, _level_filter(performance_level))
        flat_categories = {}
        for cat, recs in categories.items():
            flat_categories[cat] = [serialize_performance_record(r) for r in recs]

        return StandardResponse(
            success=True,
            message=f"Classified planning categories for {month}",
            data=flat_categories
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to compile planning lists.")


@router.get("/insights", response_model=StandardResponse)
def get_insights(
    month: str = Query(...),
    performance_level: str = Query(None),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        insights = insights_service.generate_insights(month, _level_filter(performance_level))
        return StandardResponse(
            success=True,
            message="Insights compiled successfully",
            data=insights
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to compile executive insights.")


@router.get("/export", response_class=StreamingResponse)
def export_report(
    request: Request,
    db: Session = Depends(get_db),
    month: str = Query("All"),
    team: str = Query("All"),
    format: str = Query("excel"),
    performance_level: str = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    position: str | None = Query(None),
    region: str | None = Query(None),
    workflow: str | None = Query(None),
    channel: str | None = Query(None),
    domain: str | None = Query(None),
    group: str | None = Query(None),
    role: str = Depends(require_role(["Admin", "Manager"]))
):
    try:
        scope = get_current_user_scope(db, request)
        effective_team = team
        if team.casefold() == "pre-approvals" and workflow:
            effective_team = {
                "op_final": "Pre-Approvals OP Final",
                "ip_final": "Pre-Approvals IP Final",
                "ip_elective": "Pre-Approvals IP Elective Dubai",
            }.get(workflow.casefold(), team)
        if team.casefold() == "call center" and channel:
            effective_team = {
                "inbound": "Inbound",
                "outbound": "Outbound",
            }.get(channel.casefold(), team)
        rcm_domain_teams = {
            "pre_approvals": {
                "Pre-Approvals",
                "Pre-Approvals IP Offshore",
                "Pre-Approvals OP Dubai",
                "Pre-Approvals OP Final SHJAJM",
                "Pre-Approvals IP Final Dubai",
                "Pre-Approvals IP Final SHJAJM",
                "Pre-Approvals IP Elective",
                "Pre-Approvals IP Elective Dubai",
            },
            "submission": {"Submission"},
            "re_submission": {"Re-Submission"},
            "coding": {"Coding"},
        }
        rcm_group_teams = {
            "offshore_egy": {"Pre-Approvals IP Offshore"},
            "uae": set().union(*rcm_domain_teams.values()) - {"Pre-Approvals IP Offshore"},
        }
        rcm_filter_teams = None
        if team.casefold() == "rcm":
            if domain and domain.casefold() != "all":
                rcm_filter_teams = rcm_domain_teams.get(domain.casefold())
                if rcm_filter_teams is None:
                    raise HTTPException(status_code=422, detail="Unknown RCM domain")
                if not any(user_can_access_team(scope, source_team) for source_team in rcm_filter_teams):
                    raise HTTPException(status_code=403, detail="Access denied for this RCM domain")
            else:
                rcm_filter_teams = set().union(*rcm_domain_teams.values())
            if group and group.casefold() != "all":
                group_teams = rcm_group_teams.get(group.casefold())
                if group_teams is None:
                    raise HTTPException(status_code=422, detail="Unknown RCM group")
                if not any(user_can_access_team(scope, source_team) for source_team in group_teams):
                    raise HTTPException(status_code=403, detail="Access denied for this RCM group")
                rcm_filter_teams &= group_teams
        if effective_team != "All":
            if effective_team.casefold() == "rcm":
                has_rcm_access = user_can_access_team(scope, "RCM")
            else:
                has_rcm_access = user_can_access_team(scope, effective_team)
            if not has_rcm_access:
                raise HTTPException(status_code=403, detail="Access denied for this team")
        records = _get_dashboard_records(
            db,
            team=None if effective_team == "All" or effective_team.casefold() == "rcm" else effective_team,
            month=None if month == "All" else month,
            performance_level=_level_filter(performance_level),
            year=year,
            position=position,
            region=region,
        )
        records = filter_records_by_scope(records, scope)
        if rcm_filter_teams is not None:
            allowed_rcm_names = {name.casefold() for name in rcm_filter_teams}
            records = [record for record in records if str(getattr(record, "team", "")).casefold() in allowed_rcm_names]

        if team.casefold() == "marketing":
            safe_position = position.replace(" ", "_") if position else None
            period = "_".join(
                part for part in (str(year) if year else None, month if month != "All" else None) if part
            )
            filename_parts = ["Marketing"]
            if safe_position:
                filename_parts.append(safe_position)
            if period:
                filename_parts.append(period)
            report_stem = "_".join(filename_parts)
        elif team.casefold() == "rcm":
            report_stem = f"PMS_Report_{domain or 'All'}_RCM"
        else:
            report_stem = f"PMS_Report_{month}_{team}"

        if format.lower() == "csv":
            file_data = ReportExporter.export_to_csv(records)
            media_type = "text/csv"
            filename = f"{report_stem}.csv"
        else:
            file_data = ReportExporter.export_to_excel(records)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"{report_stem}.xlsx"

        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Export failed.") from exc
