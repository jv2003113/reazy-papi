from fastapi import APIRouter
from . import auth, users, retirement, milestones, dashboard, goals, actions, investments

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Note: existing "users" router might use "/users" or similar.
# Existing user routes in JS were likely /api/users.
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(retirement.router, prefix="/retirement-plans", tags=["retirement-plans"])
api_router.include_router(milestones.router, prefix="/milestones", tags=["milestones"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(actions.router, prefix="/actions", tags=["actions"])
# Investments router uses paths like /funds and /users/{id}/investment-accounts, so we mount at root of API
# Investments router uses paths like /funds and /users/{id}/investment-accounts, so we mount at root of API
api_router.include_router(investments.router, tags=["investments"])


