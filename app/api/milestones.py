from typing import List, Any
from app.api import deps
from fastapi import APIRouter, Depends
from app.models.user import User

router = APIRouter()

@router.get("/standard", response_model=List[dict])
async def get_standard_milestones(
    current_user: User = Depends(deps.get_current_user)
) -> Any:
    return [
        {"id": "std_1", "name": "Retirement Starts", "title": "Retirement Starts", "description": "You retire", "type": "standard", "category": "retirement", "targetAge": 65},
        {"id": "std_2", "name": "Social Security Starts", "title": "Social Security Starts", "description": "Social Security payments begin", "type": "standard", "category": "income", "targetAge": 67},
        {"id": "std_3", "name": "Mortgage Paid Off", "title": "Mortgage Paid Off", "description": "Mortgage is fully paid", "type": "standard", "category": "liability", "targetAge": None},
        {"id": "std_4", "name": "Medicare Eligibility", "title": "Medicare Eligibility", "description": "Eligible for Medicare", "type": "standard", "category": "health", "targetAge": 65},
        {"id": "std_5", "name": "RMDs Begin", "title": "RMDs Begin", "description": "Required Minimum Distributions start", "type": "standard", "category": "tax", "targetAge": 73},
    ]
