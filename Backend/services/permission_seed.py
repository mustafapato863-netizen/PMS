"""Role-Based Access Control Permission Seeder
Seeds the role_permissions table with the enterprise permission matrix.
"""

import logging
import uuid
from sqlalchemy.orm import Session
from models.models import RolePermission

logger = logging.getLogger(__name__)

# Permission definitions mapped to enterprise roles
PERMISSION_MATRIX = {
    "Admin": [
        "create_team", "delete_team", "edit_team_config",
        "upload_data", "edit_performance", "delete_performance",
        "view_reports", "export_data", "manage_users",
        "manage_permissions", "view_audit_logs", "restore_data",
        "manage_batch_operations", "configure_kpi",
        "manage_alerts", "view_system_metrics", "view_plans", "manage_plans"
    ],
    # General Manager: Admin operational set minus Settings-admin powers
    # (manage_users, manage_permissions, restore_data, view_system_metrics).
    # Includes team-management perms for /team-management.
    # Settings-locked: no upload_data / delete_performance (Admin retains both).
    "General Manager": [
        "create_team", "delete_team", "edit_team_config",
        "edit_performance",
        "view_reports", "export_data",
        "view_audit_logs",
        "manage_batch_operations", "configure_kpi",
        "manage_alerts", "view_plans", "manage_plans",
        "manage_team_members", "view_actions", "create_actions", "manage_team_kpi",
        "view_aggregated_analytics",
    ],
    "Manager": [
        "upload_data", "edit_performance", "view_reports",
        "export_data", "manage_team_members", "view_actions",
        "create_actions", "manage_team_kpi", "view_plans", "manage_plans"
    ],
    "Executive": [
        "view_reports", "export_data", "view_aggregated_analytics",
        "view_audit_logs", "view_plans"
    ],
    "Viewer": [
        "view_reports"
    ]
}


def seed_role_permissions(db: Session) -> None:
    """
    Adds missing mappings without replacing existing rows.

    This is safe to run at every application start, including after new
    permissions are introduced.
    """
    try:
        existing = {
            (row.role, row.permission)
            for row in db.query(RolePermission.role, RolePermission.permission).all()
        }
        seeded_count = 0
        for role, permissions in PERMISSION_MATRIX.items():
            for perm in permissions:
                if (role, perm) in existing:
                    continue
                role_perm = RolePermission(
                    id=uuid.uuid4(),
                    role=role,
                    permission=perm
                )
                db.add(role_perm)
                seeded_count += 1
        
        # Retract Settings-locked GM perms if previously seeded (F4).
        obsolete_gm = (
            db.query(RolePermission)
            .filter(
                RolePermission.role == "General Manager",
                RolePermission.permission.in_(("upload_data", "delete_performance")),
            )
            .all()
        )
        for row in obsolete_gm:
            db.delete(row)
        if obsolete_gm:
            logger.info("Removed %s obsolete General Manager permission(s).", len(obsolete_gm))

        db.commit()
        logger.info("Seeded %s missing role permission mapping(s).", seeded_count)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed role permissions: {e}")
        # We don't raise here to prevent startup crash, but log error
