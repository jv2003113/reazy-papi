from fastapi import APIRouter
from app.api import auth, users, retirement, milestones

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Note: existing "users" router might use "/users" or similar.
# Existing user routes in JS were likely /api/users.
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(retirement.router, prefix="/retirement-plans", tags=["retirement-plans"])
api_router.include_router(milestones.router, prefix="/milestones", tags=["milestones"])
