from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.database import get_db
from app.models.user import User
from app.core.config import settings
import httpx
from pydantic import BaseModel

router = APIRouter()

class CheckoutResponse(BaseModel):
    url: str

class PortalResponse(BaseModel):
    url: str

class CheckoutRequest(BaseModel):
    planType: str = "monthly" # monthly or yearly

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    checkout_data: CheckoutRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Generate a Lemon Squeezy checkout URL for the Basic Plan.
    """
    variant_id = None
    if checkout_data.planType == "yearly":
        variant_id = settings.LEMONSQUEEZY_VARIANT_ID_YEARLY
    else:
        # Default to monthly
        variant_id = settings.LEMONSQUEEZY_VARIANT_ID_MONTHLY
        
    # Fallback for legacy SINGLE variant setup
    if not variant_id:
        variant_id = settings.LEMONSQUEEZY_VARIANT_ID

    if not settings.LEMONSQUEEZY_STORE_ID or not variant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment configuration missing"
        )
        
    # https://docs.lemonsqueezy.com/api/checkouts#create-a-checkout
    ls_url = "https://api.lemonsqueezy.com/v1/checkouts"
    
    headers = {
        "Authorization": f"Bearer {settings.LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }
    
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "custom": {
                        "user_id": str(current_user.id)
                    },
                    "email": current_user.email,
                    # Optional: prefill name if available
                    "name": f"{current_user.personal_info.get('firstName', '')} {current_user.personal_info.get('lastName', '')}".strip() or None
                }
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": str(settings.LEMONSQUEEZY_STORE_ID)
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": str(variant_id)
                    }
                }
            }
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(ls_url, json=payload, headers=headers)
        
        if response.status_code != 201:
            # Log error
            print(f"Lemon Squeezy Error: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to generate checkout link"
            )
            
        data = response.json()
        checkout_url = data["data"]["attributes"]["url"]
        
        return {"url": checkout_url}

@router.post("/portal", response_model=PortalResponse)
async def get_customer_portal(
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get a link to the Customer Portal for managing subscription using Customer ID.
    If User doesn't have a Customer ID (not subscribed or synced), return error.
    """
    if not current_user.customerId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active customer record found."
        )
        
    # https://docs.lemonsqueezy.com/api/customers#retrieve-a-customer
    # Actually, we rely on the Customer Portal link which is usually tied to the customer object
    # Or we can just redirect them to https://<store>.lemonsqueezy.com/billing
    # But API allows generating a signed link?
    # Lemon Squeezy doesn't have a dedicated "create portal session" endpoint like Stripe.
    # Instead, the customer portal link is found in the Customer object response.
    
    headers = {
        "Authorization": f"Bearer {settings.LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }

    async with httpx.AsyncClient() as client:
        # Fetch customer to get the `urls.customer_portal`
        response = await client.get(
            f"https://api.lemonsqueezy.com/v1/customers/{current_user.customerId}",
            headers=headers
        )
        
        if response.status_code != 200:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve customer portal"
            )

        data = response.json()
        portal_url = data["data"]["attributes"]["urls"]["customer_portal"]
        
        return {"url": portal_url}
