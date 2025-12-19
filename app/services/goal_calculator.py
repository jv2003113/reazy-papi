from app.models.user import User

class GoalCalculator:
    @staticmethod
    def calculate_initial_values(user: User, ref_goal_title: str) -> dict:
        """
        Calculates the initial currentAmount and targetAmount for a given goal type.
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
            print(f"DEBUG: Calculating Debt Goal. CC: {user.creditCardDebt}, Student: {user.studentLoanDebt}, Other: {user.otherDebt}")
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            mortgage = float(user.mortgageBalance or 0)
            
            # Track ALL debt (Consumer + Mortgage)
            total_debt = credit_cards + student_loans + other_debt + mortgage
            
            result["targetAmount"] = total_debt if total_debt > 0 else 1000.0
            result["currentAmount"] = 0.0
            
        # 4. Buy a Home
        elif "home" in title:
             result["targetAmount"] = 50000.0 # Placeholder down payment
             result["currentAmount"] = 0.0
             
        # 5. Passive Income
        elif "passive" in title:
             result["targetAmount"] = 2000.0 # Monthly target
             result["currentAmount"] = float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)
             
        return result

    @staticmethod
    def calculate_current_progress(user: User, user_goal_target: float, ref_goal_title: str) -> float:
        """
        Calculates the *current amount* based on live user data.
        Returns the value to be used for 'currentAmount'.
        """
        if not ref_goal_title:
            return 0.0

        title = ref_goal_title.lower()

        if "emergency" in title:
            return float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
        
        elif "401" in title:
            return float(user.retirementAccount401kContribution or 0)
            
        elif "debt" in title:
            # Paid Off = Initial Target (Debt) - Current Debt
            credit_cards = float(user.creditCardDebt or 0)
            student_loans = float(user.studentLoanDebt or 0)
            other_debt = float(user.otherDebt or 0)
            mortgage = float(user.mortgageBalance or 0)
            current_total_debt = credit_cards + student_loans + other_debt + mortgage
            
            paid_off = user_goal_target - current_total_debt
            return max(0.0, paid_off) # Ensure not negative if debt increases
            
        elif "passive" in title:
             return float(user.otherIncomeAmount1 or 0) + float(user.otherIncomeAmount2 or 0)

        return 0.0
