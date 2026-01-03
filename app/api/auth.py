from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api import deps
from app.core import security
from app.core.config import settings
from app.database import get_db
from app.models.user import User, UserRead

router = APIRouter()

# --- Google Auth Imports ---
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

class GoogleLoginRequest(BaseModel):
    token: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    message: str
    user: UserRead

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
        secure=False,
        domain=None # Ensure it defaults to host only
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
    personal_info = {}
    if signup_data.firstName: personal_info["firstName"] = signup_data.firstName
    if signup_data.lastName: personal_info["lastName"] = signup_data.lastName

    user = User(
        email=signup_data.email,
        password=security.get_password_hash(signup_data.password),
        personal_info=personal_info
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

@router.post("/google", response_model=UserResponse)
async def google_login(
    response: Response,
    google_data: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    # 1. Verify Google Token
    try:
        # We don't check audience here because we want to allow any valid token for this demo/setup. 
        # In prod, pass CLIENT_ID as second arg.
        id_info = id_token.verify_oauth2_token(google_data.token, google_requests.Request())
        
        # Extract info
        email = id_info.get("email")
        google_id = id_info.get("sub")
        first_name = id_info.get("given_name")
        last_name = id_info.get("family_name")
        picture = id_info.get("picture")
        
        if not email:
            raise ValueError("Email not found in token")
            
    except Exception as e:
        print(f"Google Token Verification Error: {e}")
        raise HTTPException(status_code=400, detail="Invalid Google Token")

    # 2. Find or Create User
    # Strategy: Match by google_id first. If not found, match by email.
    # If matching by email, link google_id.
    
    # Check by Google ID
    query = select(User).where(User.googleId == google_id)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user:
        # Check by Email
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        user = result.scalars().first()
        
        if user:
            # Existing email, link account
            user.googleId = google_id
            if not user.profilePicture and picture:
                user.profilePicture = picture
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            # Store names in personal_info JSONB bucket
            personal_info = {}
            if first_name: personal_info["firstName"] = first_name
            if last_name: personal_info["lastName"] = last_name
            
            user = User(
                email=email,
                password=None, # No password for OAuth
                googleId=google_id,
                profilePicture=picture,
                personal_info=personal_info
            )
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
    # 3. Create Session (JWT)
    access_token = security.create_access_token(subject=user.id)
    
    response.set_cookie(
        key="access_token",
        value=f"{access_token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False
    )
    
    return {
        "message": "Login successful",
        "user": user
    }
