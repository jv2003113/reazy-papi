from app.models.user import User

class GoalCalculator:
    """
    Utility service for dynamically calculating goal progress and targets.
    
    This class maps real-time User data (e.g. savings balance, debt amounts) 
    to specific Goal types (e.g. "EMERGENCY_FUND", "DEBT_PAYOFF").
    """
    @staticmethod
    def _get_val(user: User, category: str, key: str) -> float:
        d = getattr(user, category, {}) or {}
        return float(d.get(key) or 0)

    @staticmethod
    def calculate_initial_values(user: User, goal_type: str) -> dict:
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
        result = {"currentValue": 0.0, "targetValue": 100.0}
        
        if not goal_type:
            return result
            
        # 1. Emergency Fund
        if goal_type == "EMERGENCY_FUND":
            monthly_expenses = GoalCalculator._get_val(user, "expenses", "totalMonthlyExpenses")
            if monthly_expenses == 0: monthly_expenses = 4000.0
            target = monthly_expenses * 6 # Aim for 6 months
            current = GoalCalculator._get_val(user, "assets", "savingsBalance") + GoalCalculator._get_val(user, "assets", "checkingBalance")
            
            result["targetValue"] = target
            result["currentValue"] = current
            
        # 2. Max 401(k)
        elif goal_type == "RETIREMENT_401K":
            result["targetValue"] = 23000.0 # 2024 Limit
            result["currentValue"] = GoalCalculator._get_val(user, "assets", "retirementAccount401kContribution")
            
            # 3. Pay Off Debt
        elif goal_type == "DEBT_PAYOFF":
            # High Interest Debt Only (Exclude Mortgage)
            credit_cards = GoalCalculator._get_val(user, "liabilities", "creditCardDebt")
            student_loans = GoalCalculator._get_val(user, "liabilities", "studentLoanDebt")
            other_debt = GoalCalculator._get_val(user, "liabilities", "otherDebt")
            
            # Track ONLY High Interest Debt
            total_debt = credit_cards + student_loans + other_debt
            
            result["targetValue"] = total_debt if total_debt > 0 else 1000.0
            result["currentValue"] = 0.0
            
        # 4. Pay off Mortgage
        elif goal_type == "MORTGAGE_PAYOFF":
             mortgage_balance = GoalCalculator._get_val(user, "liabilities", "mortgageBalance")
             result["targetValue"] = mortgage_balance if mortgage_balance > 0 else 250000.0
             result["currentValue"] = 0.0
             
        # 5. Additional Income
        elif goal_type == "ADDITIONAL_INCOME":
             result["targetValue"] = 2000.0 
             result["currentValue"] = GoalCalculator._get_val(user, "income", "otherIncomeAmount1") + GoalCalculator._get_val(user, "income", "otherIncomeAmount2")

        # 6. HSA Goal
        elif goal_type == "HEALTH_SAVINGS":
             result["targetValue"] = 10000.0
             result["currentValue"] = GoalCalculator._get_val(user, "assets", "hsaBalance") + GoalCalculator._get_val(user, "assets", "spouseHsaBalance")
             
        return result

    @staticmethod
    def calculate_current_progress(user: User, user_goal_target: float, goal_type: str) -> float:
        """
        Calculates the *current amount* (progress) based on live user data.
        
        This allows goals to auto-update as the user modifies their profile (e.g. updates savings balance).
        
        For Debt/Mortgage goals:
        Progress is calculated as (Initial Target - Current Balance). 
        This represents the "Amount Paid Off".
        
        Returns:
            float: The calculated current amount.
        """
        if not goal_type:
            return 0.0

        if goal_type == "EMERGENCY_FUND":
            return GoalCalculator._get_val(user, "assets", "savingsBalance") + GoalCalculator._get_val(user, "assets", "checkingBalance")
        
        elif goal_type == "RETIREMENT_401K":
            return GoalCalculator._get_val(user, "assets", "retirementAccount401kContribution")
            
        elif goal_type == "DEBT_PAYOFF":
            credit_cards = GoalCalculator._get_val(user, "liabilities", "creditCardDebt")
            student_loans = GoalCalculator._get_val(user, "liabilities", "studentLoanDebt")
            other_debt = GoalCalculator._get_val(user, "liabilities", "otherDebt")
            
            current_total_debt = credit_cards + student_loans + other_debt
            
            paid_off = user_goal_target - current_total_debt
            return max(0.0, paid_off) # Ensure not negative if debt increases

        elif goal_type == "MORTGAGE_PAYOFF":
            current_mortgage = GoalCalculator._get_val(user, "liabilities", "mortgageBalance")
            paid_off = user_goal_target - current_mortgage
            return max(0.0, paid_off)
            
        elif goal_type == "ADDITIONAL_INCOME":
             return GoalCalculator._get_val(user, "income", "otherIncomeAmount1") + GoalCalculator._get_val(user, "income", "otherIncomeAmount2")

        elif goal_type == "HEALTH_SAVINGS":
             return GoalCalculator._get_val(user, "assets", "hsaBalance") + GoalCalculator._get_val(user, "assets", "spouseHsaBalance")

        return 0.0
