from typing import List, Dict, Any
from app.models.user import User
from app.models.retirement import RetirementPlan, AnnualSnapshot

class RecommendationEngine:
    @staticmethod
    def generate_recommendations(
        user: User, 
        plan: RetirementPlan, 
        current_portfolio_allocation: Dict[str, Any],
        active_goal_titles: List[str] = []
    ) -> List[Dict[str, Any]]:
        recommendations = []
        
        # 1. Savings Rate Analysis
        monthly_income = (float(user.currentIncome or 0) + float(user.spouseCurrentIncome or 0)) / 12
        monthly_savings = (
            float(user.investmentContribution or 0) + 
            float(user.retirementAccount401kContribution or 0) + 
            float(user.retirementAccountIRAContribution or 0) + 
            float(user.retirementAccountRothContribution or 0)
        ) / 12
        
        savings_rate = (monthly_savings / monthly_income * 100) if monthly_income > 0 else 0
        
        if savings_rate < 15:
            recommendations.append({
                "id": "rec_savings_rate_high",
                "title": "Boost Your Savings Rate",
                "description": f"Your current savings rate is {int(savings_rate)}%. Aiming for at least 15% is recommended for long-term security.",
                "category": "saving",
                "impact": "high",
                "status": "active"
            })
        elif savings_rate < 20:
             recommendations.append({
                "id": "rec_savings_rate_med",
                "title": "Increase Savings to 20%",
                "description": "You are doing well, but increasing your savings rate to 20% would significantly accelerate your timeline.",
                "category": "saving",
                "impact": "medium",
                "status": "active"
            })
            
        # 2. Emergency Fund Analysis
        if "Emergency Fund" not in active_goal_titles:
            cash = float(user.savingsBalance or 0) + float(user.checkingBalance or 0)
            monthly_expenses = float(user.totalMonthlyExpenses or 4000) # Default to 4000 if not set
            months_covered = cash / monthly_expenses if monthly_expenses > 0 else 0
            
            if months_covered < 3:
                 recommendations.append({
                    "id": "rec_emergency_fund",
                    "title": "Build Emergency Fund",
                    "description": f"You have {int(months_covered)} months of expenses saved. We recommend keeping 3-6 months liquid for emergencies.",
                    "category": "risk",
                    "impact": "high",
                    "status": "active",
                    "suggestedRefGoalTitle": "Emergency Fund"
                })
            
        # 3. 401k Contribution Analysis
        if "Max 401(k)" not in active_goal_titles:
            # 2024 Limit is 23,000 (standard). We'll use a simplified check.
            annual_401k = float(user.retirementAccount401kContribution or 0)
            if annual_401k < 23000 and annual_401k > 0:
                 recommendations.append({
                    "id": "rec_401k_max",
                    "title": "Maximize 401(k)",
                    "description": f"You are contributing ${int(annual_401k):,} annually. Consider increasing up to the $23,000 IRS limit to lower your taxable income.",
                    "category": "tax",
                    "impact": "medium",
                    "status": "active",
                    "suggestedRefGoalTitle": "Max 401(k)"
                })
            
        # 4. Asset Allocation Check
        # Rule of thumb: 110 - Age = Stock Allocation %
        current_age = user.currentAge or 30
        target_stock_pct = 110 - current_age
        
        # Get current stock % from allocation dict passed in
        # structure: {'total': X, 'categories': {'stocks': {'percentage': Y, ...}}}
        current_stock_pct = current_portfolio_allocation.get("categories", {}).get("stocks", {}).get("percentage", 60)
        
        # If deviation is > 15%
        if current_stock_pct < (target_stock_pct - 15):
             recommendations.append({
                "id": "rec_allocation_conservative",
                "title": "Portfolio Too Conservative?",
                "description": f"Your stock allocation is {current_stock_pct}%, but based on your age, you might consider closer to {target_stock_pct}% for growth.",
                "category": "investing",
                "impact": "medium",
                "status": "active"
            })
        elif current_stock_pct > (target_stock_pct + 15):
             recommendations.append({
                "id": "rec_allocation_aggressive",
                "title": "Portfolio Too Aggressive?",
                "description": f"Your stock allocation is {current_stock_pct}%, which exposes you to high volatility. A target of {target_stock_pct}% is standard for your age.",
                "category": "risk",
                "impact": "high",
                "status": "active"
            })
            
        return recommendations
