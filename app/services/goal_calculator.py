from app.models.user import User

class GoalCalculator:
    """
    Utility service for dynamically calculating goal progress and targets.
    
    This class maps real-time User data (e.g. savings balance, debt amounts) 
    to specific Goal types (e.g. Emergency Fund, Pay Off Debt).
    """
    @staticmethod
    def calculate_initial_values(user: User, ref_goal_title: str) -> dict:
        """
        Calculates the initial 'currentAmount' and default 'targetAmount' for a new goal.
        
        Logic varies by goal type:
        - Emergency Fund: Target = 6 * Monthly Expenses. Current = Cash + Savings.
        - Debt: Target = Sum of high-interest debt. Current = 0 (Goal is to pay off).
        - Retirement: Target = IRS Limits. Current = Contributions.
        - Health Savings: Target = Arbitrary/Limit. Current = HSA Balance.
        
        Returns:
            dict: {"currentAmount": float, "targetAmount": float}
        """
        result = {"currentAmount": 0.0, "targetAmount": 100.0}
        
        if not ref_goal_title:
            return result
            
        title = ref_goal_title.lower()
        
        # 1. Emergency Fund
        if "emergency" in title:
            # ... (keep existing debug)
            monthly_expenses = float(user.totalMonthlyExpenses or 4000)
            target = monthly_expenses * 6 # Aim for 6 months
            current = float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
            
            result["targetAmount"] = target
            result["currentAmount"] = current
            
        # 2. Max 401(k)
        elif "401" in title:
            result["targetAmount"] = 23000.0 # 2024 Limit
            result["currentAmount"] = float(user.retirementAccount401kContribution or 0)
            
            # 3. Pay Off Debt
        elif "debt" in title:
            # High Interest Debt Only (Exclude Mortgage)
            print(f"DEBUG: Calculating High Interest Debt Goal. CC: {user.creditCardDebt}, Student: {user.studentLoanDebt}, Other: {user.otherDebt}")
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            
            # Track ONLY High Interest Debt
            total_debt = credit_cards + student_loans + other_debt
            
            result["targetAmount"] = total_debt if total_debt > 0 else 1000.0
            result["currentAmount"] = 0.0
            
        # 4. Pay off Mortgage (Replacing Buy a Home)
        elif "home" in title or "mortgage" in title:
             mortgage_balance = float(user.mortgageBalance or 0)
             result["targetAmount"] = mortgage_balance if mortgage_balance > 0 else 250000.0
             result["currentAmount"] = 0.0
             
        # 5. Additional Income (Renamed from Passive)
        elif "additional" in title or "income" in title:
             # Default target if not set, user can override in UI now
             result["targetAmount"] = 2000.0 
             result["currentAmount"] = float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)

        # 6. HSA Goal
        elif "health" in title or "hsa" in title:
             # Default to annual max contribution limit for family (approx 8300 in 2024)? 
             # Or just a round number like 10k?
             result["targetAmount"] = 10000.0
             result["currentAmount"] = float(user.hsaBalance or 0) + float(user.spouseHsaBalance or 0)
             
        return result

    @staticmethod
    def calculate_current_progress(user: User, user_goal_target: float, ref_goal_title: str) -> float:
        """
        Calculates the *current amount* (progress) based on live user data.
        
        This allows goals to auto-update as the user modifies their profile (e.g. updates savings balance).
        
        For Debt/Mortgage goals:
        Progress is calculated as (Initial Target - Current Balance). 
        This represents the "Amount Paid Off".
        
        Returns:
            float: The calculated current amount.
        """
        if not ref_goal_title:
            return 0.0

        title = ref_goal_title.lower()

        if "emergency" in title:
            return float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
        
        elif "401" in title:
            return float(user.retirementAccount401kContribution or 0)
            
        elif "debt" in title:
            # Paid Off = Initial Target (High Interest Debt) - Current High Interest Debt
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            
            print(f"DEBUG: Calc Current Debt. CC: {credit_cards}, Student: {student_loans}, Other: {other_debt}")

            current_total_debt = credit_cards + student_loans + other_debt
            
            paid_off = user_goal_target - current_total_debt
            return max(0.0, paid_off) # Ensure not negative if debt increases

        elif "home" in title or "mortgage" in title:
            # Paid Off = Initial Target (Mortgage) - Current Mortgage
            current_mortgage = float(user.mortgageBalance or 0)
            paid_off = user_goal_target - current_mortgage
            return max(0.0, paid_off)
            
        elif "additional" in title or "income" in title:
             return float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)

        elif "health" in title or "hsa" in title:
             return float(user.hsaBalance or 0) + float(user.spouseHsaBalance or 0)

        return 0.0
