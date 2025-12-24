from pydantic import BaseModel
from typing import Dict, Optional

class TaxRates(BaseModel):
    ordinary_income: float
    capital_gains: float
    social_security: float

class ContributionLimits(BaseModel):
    limit_401k: float
    limit_ira: float
    limit_hsa_family: float
    limit_hsa_single: float
    catch_up_401k: float
    catch_up_ira: float
    catch_up_hsa: float

class FinancialAssumptionsService:
    """
    Service to provide financial assumptions such as tax rates, contribution limits,
    and RMD rules. These are currently static but can be connected to a live data source.
    """
    
    # 2024-ish Defaults
    DEFAULT_TAX_RATES = TaxRates(
        ordinary_income=0.22,  # Effective blended rate assumption
        capital_gains=0.15,    # Long term cap gains
        social_security=0.187  # 0.85 * 0.22 (Taxable portion of SS usually 85% for high earners)
    )

    # 2024 Limits
    DEFAULT_CONTRIBUTION_LIMITS = ContributionLimits(
        limit_401k=23000.0,
        limit_ira=7000.0,
        limit_hsa_family=8300.0,
        limit_hsa_single=4150.0,
        catch_up_401k=7500.0,
        catch_up_ira=1000.0,
        catch_up_hsa=1000.0
    )

    RMD_UNIFORM_LIFETIME_TABLE = {
        72: 27.4, 73: 26.5, 74: 25.5,
        75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0, 79: 21.1,
        80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8,
        85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9,
        90: 12.2, 91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5,
        95: 8.9,  96: 8.4,  97: 7.8,  98: 7.3,  99: 6.8,
        100: 6.4, 101: 6.0, 102: 5.6, 103: 5.2, 104: 4.9,
        105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9, 109: 3.7,
        110: 3.5, 111: 3.4, 112: 3.3, 113: 3.1, 114: 3.0,
        115: 2.9 # And older
    }

    def get_tax_rates(self, year: int) -> TaxRates:
        """
        Returns tax rate assumptions for a given year.
        Currently returns static defaults regardless of year.
        """
        # In a real system, we might project tax reform or changes.
        return self.DEFAULT_TAX_RATES

    def get_contribution_limits(self, year: int) -> ContributionLimits:
        """
        Returns contribution limits for a given year.
        Currently returns static 2024 defaults.
        """
        # In reality, these index with inflation.
        return self.DEFAULT_CONTRIBUTION_LIMITS

    def get_rmd_divisor(self, age: int) -> float:
        """
        Returns the RMD divisor for a given age based on the IRS Uniform Lifetime Table.
        """
        # SECURE 2.0 Act raised RMD age to 73 (and eventually 75).
        # We'll use 73 as the starting point for now, returning 0 if under.
        if age < 73:
            return 0.0
            
        # If age is in table, use it. If strictly older than table, use last value (simplified)
        # or extrapolated. The table usually goes up to 120+. 115 is 2.9.
        if age >= 115:
            return 2.9
            
        return self.RMD_UNIFORM_LIFETIME_TABLE.get(age, 27.4)
