from typing import List, Any
from fastapi import APIRouter

router = APIRouter()

@router.get("/standard", response_model=List[dict])
async def get_standard_milestones() -> Any:
    return [
        {"id": "std_1", "name": "Retirement Starts", "title": "Retirement Starts", "description": "You retire", "type": "standard", "category": "retirement", "defaultAge": 65},
        {"id": "std_2", "name": "Social Security Starts", "title": "Social Security Starts", "description": "Social Security payments begin", "type": "standard", "category": "income", "defaultAge": 67},
        {"id": "std_3", "name": "Mortgage Paid Off", "title": "Mortgage Paid Off", "description": "Mortgage is fully paid", "type": "standard", "category": "liability", "defaultAge": None},
        {"id": "std_4", "name": "Medicare Eligibility", "title": "Medicare Eligibility", "description": "Eligible for Medicare", "type": "standard", "category": "health", "defaultAge": 65},
        {"id": "std_5", "name": "RMDs Begin", "title": "RMDs Begin", "description": "Required Minimum Distributions start", "type": "standard", "category": "tax", "defaultAge": 73},
    ]
