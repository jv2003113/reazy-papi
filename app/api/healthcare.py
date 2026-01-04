from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal

router = APIRouter()

class HealthcareEstimateRequest(BaseModel):
    current_age: int
    retirement_age: int
    health_status: Literal['excellent', 'good', 'fair', 'poor']
    has_medical_conditions: bool
    has_longevity_history: bool
    anticipated_healthcare_needs: Literal['low', 'moderate', 'high']
    desired_coverage_level: int # 1-10
    annual_income: Optional[float] = 0  # For IRMAA calculation

class ExpenseItem(BaseModel):
    name: str
    value: float
    color: str

class HealthcareEstimateResponse(BaseModel):
    monthly_total: int
    annual_total: int
    lifetime_total: int
    inflation_adjusted_lifetime_total: int
    breakdown: List[ExpenseItem]

@router.post("/estimate", response_model=HealthcareEstimateResponse)
def estimate_healthcare_costs(data: HealthcareEstimateRequest):
    # Base monthly costs (approximate 2024/2025 figures)
    BASE_MEDICARE_PREMIUM = 170.0
    BASE_SUPPLEMENTAL = 200.0
    BASE_OUT_OF_POCKET = 150.0
    BASE_DENTAL_VISION = 80.0
    BASE_PRESCRIPTION = 120.0

    # 1. Health Status Multiplier
    health_multiplier = 1.0
    if data.health_status == 'excellent':
        health_multiplier = 0.8
    elif data.health_status == 'good':
        health_multiplier = 1.0
    elif data.health_status == 'fair':
        health_multiplier = 1.3
    elif data.health_status == 'poor':
        health_multiplier = 1.6

    # 2. Medical Conditions & Longevity Adjustments
    if data.has_medical_conditions:
        health_multiplier += 0.2
    
    # Longevity impacts lifetime cost calculation more than monthly, 
    # but might slightly increase premiums if underwriting was involved (less relevant for Medicare, but good proxy for general health spend)
    if data.has_longevity_history:
        health_multiplier += 0.1

    # 3. Needs Multiplier
    needs_multiplier = 1.0
    if data.anticipated_healthcare_needs == 'low':
        needs_multiplier = 0.8
    elif data.anticipated_healthcare_needs == 'moderate':
        needs_multiplier = 1.0
    elif data.anticipated_healthcare_needs == 'high':
        needs_multiplier = 1.4

    # 4. Coverage Level Multiplier (1-10)
    # Higher coverage = Higher premiums, Lower out-of-pocket
    # But for total cost estimation, we can assume higher coverage implies higher willingness to spend on premium services.
    # The frontend logic was: coverageMultiplier = 0.7 + level * 0.05
    coverage_multiplier = 0.7 + (data.desired_coverage_level * 0.05)

    # IRMAA Brackets (2025) - Single Filer for simplicity (or simplified joint assumption)
    # Ideally should ask filing status, but using Single thresholds conservatively
    irmaa_part_b = 0.0
    irmaa_part_d = 0.0
    
    income = data.annual_income or 0
    if income > 106000:
        if income <= 133000:
            irmaa_part_b = 74.00
            irmaa_part_d = 13.70
        elif income <= 167000:
            irmaa_part_b = 185.00
            irmaa_part_d = 34.20
        elif income <= 201000:
            irmaa_part_b = 296.00
            irmaa_part_d = 54.70
        elif income <= 500000:
            irmaa_part_b = 406.90
            irmaa_part_d = 78.60
        else:
            irmaa_part_b = 443.90
            irmaa_part_d = 85.80

    # Calculate Components
    
    # Medicare Part B
    adjusted_medicare = (BASE_MEDICARE_PREMIUM * health_multiplier) + irmaa_part_b
    
    # Supplemental
    adjusted_supplemental = BASE_SUPPLEMENTAL * health_multiplier * coverage_multiplier

    # Out of pocket
    adjusted_out_of_pocket = BASE_OUT_OF_POCKET * health_multiplier * needs_multiplier
    
    adjusted_dental_vision = BASE_DENTAL_VISION * coverage_multiplier
    
    # Prescription Drugs (Part D + Out of Pocket)
    adjusted_prescription = (BASE_PRESCRIPTION * health_multiplier * needs_multiplier) + irmaa_part_d

    # Totals
    monthly_total = (
        adjusted_medicare + 
        adjusted_supplemental + 
        adjusted_out_of_pocket + 
        adjusted_dental_vision + 
        adjusted_prescription
    )
    
    annual_total = monthly_total * 12
    
    # Lifetime calculation with Inflation
    # Assumes life expectancy of 95
    years_to_retirement = max(0, data.retirement_age - data.current_age)
    years_in_retirement = max(0, 95 - data.retirement_age)
    
    # Simple lifetime (today's dollars)
    lifetime_total = annual_total * years_in_retirement

    # Inflated lifetime
    HEALTHCARE_INFLATION = 0.055 # 5.5%
    
    inflated_lifetime_total = 0.0
    current_projected_annual = annual_total
    
    # First, inflate to retirement start
    current_projected_annual = current_projected_annual * ((1 + HEALTHCARE_INFLATION) ** years_to_retirement)
    
    # Then sum for each year in retirement
    for _ in range(years_in_retirement):
        inflated_lifetime_total += current_projected_annual
        current_projected_annual *= (1 + HEALTHCARE_INFLATION)

    # Construct Breakdown for Chart
    breakdown = [
        ExpenseItem(name='Medicare Premiums (incl. IRMAA)', value=round(adjusted_medicare * 12), color='#1E88E5'),
        ExpenseItem(name='Supplemental Insurance', value=round(adjusted_supplemental * 12), color='#43A047'),
        ExpenseItem(name='Out-of-Pocket Costs', value=round(adjusted_out_of_pocket * 12), color='#FFA000'),
        ExpenseItem(name='Dental & Vision', value=round(adjusted_dental_vision * 12), color='#9C27B0'),
        ExpenseItem(name='Prescription Drugs', value=round(adjusted_prescription * 12), color='#F44336'),
    ]

    return HealthcareEstimateResponse(
        monthly_total=round(monthly_total),
        annual_total=round(annual_total),
        lifetime_total=round(lifetime_total),
        inflation_adjusted_lifetime_total=round(inflated_lifetime_total),
        breakdown=breakdown
    )
