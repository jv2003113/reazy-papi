from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.core.config import settings
from sqlmodel import select
import hmac
import hashlib
import json
from datetime import datetime

router = APIRouter()

@router.post("/lemonsqueezy")
async def handle_lemonsqueezy_webhook(
    request: Request,
    x_signature: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle webhooks from Lemon Squeezy.
    """
    if not settings.LEMONSQUEEZY_WEBHOOK_SECRET:
         raise HTTPException(status_code=500, detail="Webhook secret not configured")

    # 1. Verify Signature
    raw_body = await request.body()
    secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET.encode()
    digest = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    
    if not x_signature or not hmac.compare_digest(digest, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    # 2. Parse Event
    try:
        data = json.loads(raw_body)
        event_name = data["meta"]["event_name"]
        payload = data["data"]
        attributes = payload["attributes"]
        custom_data = data["meta"]["custom_data"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")
        
    # 3. Handle Events
    # Events: subscription_created, subscription_updated, subscription_cancelled, subscription_expired
    if event_name in ["subscription_created", "subscription_updated", "subscription_cancelled", "subscription_expired", "subscription_resumed"]:
        
        user_id = custom_data.get("user_id")
        if not user_id:
            return {"status": "ignored", "reason": "no user_id"}
            
        # Find User
        user = await db.get(User, user_id)
        if not user:
            return {"status": "ignored", "reason": "user not found"}
            
        # Update User Subscription Info
        user.subscriptionId = str(payload["id"])
        user.customerId = str(attributes["customer_id"])
        user.variantId = str(attributes["variant_id"])
        user.subscriptionStatus = attributes["status"]  # active, on_trial, past_due, cancelled, expired
        
        # Parse renewal date
        renews_at = attributes.get("renews_at")
        ends_at = attributes.get("ends_at")
        
        # Set current period end preference: check 'ends_at' (if cancelling) or 'renews_at'
        target_date_str = ends_at if ends_at else renews_at
        if target_date_str:
            try:
                # ISO format: "2021-08-11T13:47:34.000000Z"
                # python fromisoformat might need replacing 'Z' with '+00:00'
                if target_date_str.endswith('Z'):
                    target_date_str = target_date_str[:-1] + '+00:00'
                dt = datetime.fromisoformat(target_date_str)
                # Convert to naive UTC to satisfy asyncpg/Postgres TIMESTAMP WITHOUT TIME ZONE
                if dt.tzinfo is not None:
                    from datetime import timezone
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                user.currentPeriodEnd = dt
            except ValueError:
                pass
                
        # If active, basic plan -> Access Control Logic could be:
        # checking user.subscriptionStatus == 'active' in dependencies
        
        db.add(user)
        await db.commit()
        
        return {"status": "processed", "event": event_name}

    return {"status": "ignored", "event": event_name}
