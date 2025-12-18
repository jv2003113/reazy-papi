from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
# from jose import jwt # Removed
import jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import security
from app.core.config import settings
from app.database import get_db
from app.models.user import User
from sqlmodel import select

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False
)

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2)
) -> User:
    # Try to get token from cookie if not in header
    if not token:
        token = request.cookies.get("access_token")
        # Handle "Bearer " prefix if present in cookie (optional, usually raw token)
        if token and token.startswith("Bearer "):
            token = token.split(" ")[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = payload.get("sub")
    except (jwt.InvalidTokenError, ValidationError): # PyJWT raises InvalidTokenError
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    
    # In 'sub' we stored user ID
    result = await db.execute(select(User).where(User.id == token_data))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
