from fastapi import APIRouter

from .performance import router as performance_router
from .employee import router as employee_router
from .team import router as team_router
from .settings import router as settings_router
from .upload import router as upload_router
from .users_and_actions import users_router, actions_router
from .config import router as config_router
from .team_management import router as team_management_router
from .auth import router as auth_router
from .bulk_operations import router as bulk_operations_router
from .health import router as health_router
from .search import router as search_router
from .vitals import router as vitals_router
from .reports import router as reports_router
from .insights import router as insights_router
from .planning import router as planning_router

router = APIRouter()

router.include_router(performance_router, tags=["Performance"])
router.include_router(employee_router, prefix="/employee", tags=["Employee"])
router.include_router(team_router, prefix="/team-actions", tags=["Team Actions"])
router.include_router(settings_router, prefix="/settings", tags=["Settings"])
router.include_router(upload_router, prefix="/uploads", tags=["Uploads"])
router.include_router(users_router, prefix="/users", tags=["Users"])
router.include_router(actions_router, prefix="/corrective-actions", tags=["Corrective Actions"])
router.include_router(config_router, tags=["Configuration"])
router.include_router(team_management_router, tags=["Team Management"])
router.include_router(auth_router, tags=["Authentication"])
router.include_router(bulk_operations_router, tags=["Bulk Operations"])
router.include_router(health_router, tags=["Health Check"])
router.include_router(search_router, tags=["Search"])
router.include_router(vitals_router, tags=["Web Vitals"])
router.include_router(reports_router)
router.include_router(insights_router)
router.include_router(planning_router)

