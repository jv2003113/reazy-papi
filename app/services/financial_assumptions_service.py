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

    # 2024 Tax Brackets & Rules
    # Source: IRS Rev. Proc. 2023-34
    
    STANDARD_DEDUCTION_2024 = {
        "single": 14600,
        "married_jointly": 29200,
        "head_household": 21900
    }

    # Brackets: (Threshold, Rate) - Cumulative
    # "If income > Threshold, apply Rate to (Income - Threshold) + BaseTax" logic usually?
    # Or simpler: List of tuples (Upper Limit, Rate).
    # Easier for calculation: List of (Lower Limit, Rate).
    
    TAX_BRACKETS_2024 = {
        "single": [
            (0, 0.10),
            (11600, 0.12),
            (47150, 0.22),
            (100525, 0.24),
            (191950, 0.32),
            (243725, 0.35),
            (609350, 0.37)
        ],
        "married_jointly": [
            (0, 0.10),
            (23200, 0.12),
            (94300, 0.22),
            (201050, 0.24),
            (383900, 0.32),
            (487450, 0.35),
            (731200, 0.37)
        ]
    }

    # Long Term Capital Gains Brackets (Based on Taxable Income including Cap Gains)
    # 2024 Thresholds
    CAP_GAINS_BRACKETS_2024 = {
        "single": [
            (0, 0.0),
            (47025, 0.15),
            (518900, 0.20)
        ],
        "married_jointly": [
            (0, 0.0),
            (94050, 0.15),
            (583750, 0.20)
        ]
    }

    def get_tax_rates(self, year: int) -> TaxRates:
        """
        Returns tax rate assumptions for a given year.
        Currently returns static defaults regardless of year.
        """
        # In a real system, we might project tax reform or changes.
        return self.DEFAULT_TAX_RATES

    def calculate_federal_income_tax(self, gross_ordinary_income: float, filing_status: str) -> float:
        """
        Calculates 2024 Federal Income Tax using progressive brackets.
        Subtracts Standard Deduction automatically.
        """
        status = filing_status.lower()
        if status not in self.STANDARD_DEDUCTION_2024:
            status = "single" # Default

        std_deduction = self.STANDARD_DEDUCTION_2024[status]
        taxable_income = max(0, gross_ordinary_income - std_deduction)
        
        brackets = self.TAX_BRACKETS_2024.get(status, self.TAX_BRACKETS_2024["single"])
        
        tax = 0.0
        # Brackets are (Lower, Rate)
        # We need to calculate checks between brackets.
        
        for i, (current_min, rate) in enumerate(brackets):
            # Determine range of this bracket
            # Next bracket start is the ceiling of this bracket
            if i < len(brackets) - 1:
                next_min = brackets[i+1][0]
                bracket_cap = next_min
            else:
                bracket_cap = float('inf')
                
            # How much income falls in this bracket?
            if taxable_income > current_min:
                # Amount in this bracket is min(taxable, cap) - current_min
                subject_to_tax = min(taxable_income, bracket_cap) - current_min
                tax += subject_to_tax * rate
            else:
                break
                
        return tax

    def calculate_capital_gains_tax(self, gross_ordinary_income: float, long_term_gains: float, filing_status: str) -> float:
        """
        Calculates Capital Gains Tax.
        Cap Gains sit ON TOP of Ordinary Income for bracket determination.
        """
        status = filing_status.lower()
        if status not in self.STANDARD_DEDUCTION_2024:
            status = "single"

        std_deduction = self.STANDARD_DEDUCTION_2024[status]
        
        # Taxable Ordinary Income (floor for cap gains stacking)
        taxable_ordinary = max(0, gross_ordinary_income - std_deduction)
        
        # Total Taxable Income (for determining cap gains bracket)
        total_taxable = taxable_ordinary + long_term_gains
        
        brackets = self.CAP_GAINS_BRACKETS_2024.get(status, self.CAP_GAINS_BRACKETS_2024["single"])
        
        tax = 0.0
        
        for i, (current_min, rate) in enumerate(brackets):
            if i < len(brackets) - 1:
                next_min = brackets[i+1][0]
                bracket_cap = next_min
            else:
                bracket_cap = float('inf')
                
            # We are looking for the portion of the "Stack" that represents the Cap Gains.
            # The stack is from `taxable_ordinary` to `total_taxable`.
            
            # Intersection of [taxable_ordinary, total_taxable] AND [current_min, bracket_cap]
            
            # Start of segment
            seg_start = max(taxable_ordinary, current_min)
            # End of segment
            seg_end = min(total_taxable, bracket_cap)
            
            if seg_end > seg_start:
                tax += (seg_end - seg_start) * rate
                
        return tax

    def get_marginal_rate(self, gross_ordinary_income: float, filing_status: str) -> float:
        """Helper to get marginal ordinary rate"""
        status = filing_status.lower()
        if status not in self.STANDARD_DEDUCTION_2024:
            status = "single"
            
        std_deduction = self.STANDARD_DEDUCTION_2024[status]
        taxable_income = max(0, gross_ordinary_income - std_deduction)
        
        brackets = self.TAX_BRACKETS_2024.get(status, self.TAX_BRACKETS_2024["single"])
        # Find the highest bracket we are in
        current_rate = 0.0
        for thresh, rate in brackets:
            if taxable_income > thresh:
                current_rate = rate
            else:
                break
        return current_rate

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
