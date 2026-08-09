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
        
        db.commit()
        logger.info("Seeded %s missing role permission mapping(s).", seeded_count)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed role permissions: {e}")
        # We don't raise here to prevent startup crash, but log error
