from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.jobs import router as jobs_router
from app.routers.friends import router as friends_router

__all__ = ["auth_router", "users_router", "jobs_router", "friends_router"]
