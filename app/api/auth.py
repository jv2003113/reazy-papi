from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api import deps
from app.core import security
from app.core.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    message: str
    user: User

class SignupRequest(BaseModel):
    email: str
    password: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None

@router.post("/login", response_model=UserResponse)
async def login(
    response: Response,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Verify User
    query = select(User).where(User.email == login_data.email)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user or not security.verify_password(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # 2. Create JWT
    access_token = security.create_access_token(subject=user.id)
    
    # 3. Set Cookie
    response.set_cookie(
        key="access_token",
        value=f"{access_token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False # Set to True in production
    )
    
    return {
        "message": "Login successful",
        "user": user
    }

@router.post("/signup", response_model=UserResponse)
async def signup(
    response: Response,
    signup_data: SignupRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Check existing
    query = select(User).where(User.email == signup_data.email)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # 2. Create User
    user = User(
        email=signup_data.email,
        password=security.get_password_hash(signup_data.password),
        firstName=signup_data.firstName,
        lastName=signup_data.lastName
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # 3. Login immediately
    access_token = security.create_access_token(subject=user.id)
    response.set_cookie(
        key="access_token",
        value=f"{access_token}",
        httponly=True,
        samesite="lax",
        secure=False
    )
    
    return {
        "message": "User created successfully",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    return {
        "message": "User retrieved successfully",
        "user": current_user
    }

@router.post("/logout")
async def logout(response: Response) -> Any:
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}

class PasswordUpdateRequest(BaseModel):
    currentPassword: str
    newPassword: str

@router.post("/update-password")
async def update_password(
    password_data: PasswordUpdateRequest,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Verify current password
    if not security.verify_password(password_data.currentPassword, current_user.password):
        raise HTTPException(
            status_code=400,
            detail="Incorrect current password"
        )
        
    # 2. Update password
    current_user.password = security.get_password_hash(password_data.newPassword)
    db.add(current_user)
    await db.commit()
    
    return {"message": "Password updated successfully"}
