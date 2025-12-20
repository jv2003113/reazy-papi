from app.models.user import User
from app.models.goal import GoalType

class GoalCalculator:
    """
    Utility service for dynamically calculating goal progress and targets.
    
    This class maps real-time User data (e.g. savings balance, debt amounts) 
    to specific Goal types (e.g. Emergency Fund, Pay Off Debt).
    """
    @staticmethod
    def calculate_initial_values(user: User, goal_type: GoalType) -> dict:
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
        
    @staticmethod
    def calculate_initial_values(user: User, goal_type: GoalType) -> dict:
        """
        Calculates the initial 'currentAmount' and default 'targetAmount' for a new goal.
        """
        result = {"currentAmount": 0.0, "targetAmount": 100.0}
        
        if not goal_type:
            return result
            
        # 1. Emergency Fund
        if goal_type == GoalType.EMERGENCY_FUND:
            monthly_expenses = float(user.totalMonthlyExpenses or 4000)
            target = monthly_expenses * 6 # Aim for 6 months
            current = float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
            
            result["targetAmount"] = target
            result["currentAmount"] = current
            
        # 2. Max 401(k)
        elif goal_type == GoalType.RETIREMENT_401K:
            result["targetAmount"] = 23000.0 # 2024 Limit
            result["currentAmount"] = float(user.retirementAccount401kContribution or 0)
            
            # 3. Pay Off Debt
        elif goal_type == GoalType.DEBT_PAYOFF:
            # High Interest Debt Only (Exclude Mortgage)
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            
            # Track ONLY High Interest Debt
            total_debt = credit_cards + student_loans + other_debt
            
            result["targetAmount"] = total_debt if total_debt > 0 else 1000.0
            result["currentAmount"] = 0.0
            
        # 4. Pay off Mortgage
        elif goal_type == GoalType.MORTGAGE_PAYOFF:
             mortgage_balance = float(user.mortgageBalance or 0)
             result["targetAmount"] = mortgage_balance if mortgage_balance > 0 else 250000.0
             result["currentAmount"] = 0.0
             
        # 5. Additional Income
        elif goal_type == GoalType.ADDITIONAL_INCOME:
             result["targetAmount"] = 2000.0 
             result["currentAmount"] = float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)

        # 6. HSA Goal
        elif goal_type == GoalType.HEALTH_SAVINGS:
             result["targetAmount"] = 10000.0
             result["currentAmount"] = float(user.hsaBalance or 0) + float(user.spouseHsaBalance or 0)
             
        return result

    @staticmethod
    def calculate_current_progress(user: User, user_goal_target: float, goal_type: GoalType) -> float:
        """
        Calculates the *current amount* (progress) based on live user data.
        
        This allows goals to auto-update as the user modifies their profile (e.g. updates savings balance).
        
        For Debt/Mortgage goals:
        Progress is calculated as (Initial Target - Current Balance). 
        This represents the "Amount Paid Off".
        
        Returns:
            float: The calculated current amount.
        """
    @staticmethod
    def calculate_current_progress(user: User, user_goal_target: float, goal_type: GoalType) -> float:
        """
        Calculates the *current amount* (progress) based on live user data.
        """
        if not goal_type:
            return 0.0

        if goal_type == GoalType.EMERGENCY_FUND:
            return float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
        
        elif goal_type == GoalType.RETIREMENT_401K:
            return float(user.retirementAccount401kContribution or 0)
            
        elif goal_type == GoalType.DEBT_PAYOFF:
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            
            current_total_debt = credit_cards + student_loans + other_debt
            
            paid_off = user_goal_target - current_total_debt
            return max(0.0, paid_off) # Ensure not negative if debt increases

        elif goal_type == GoalType.MORTGAGE_PAYOFF:
            current_mortgage = float(user.mortgageBalance or 0)
            paid_off = user_goal_target - current_mortgage
            return max(0.0, paid_off)
            
        elif goal_type == GoalType.ADDITIONAL_INCOME:
             return float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)

        elif goal_type == GoalType.HEALTH_SAVINGS:
             return float(user.hsaBalance or 0) + float(user.spouseHsaBalance or 0)

        return 0.0
