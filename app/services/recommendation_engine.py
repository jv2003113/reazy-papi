from typing import List, Dict, Any
from app.models.user import User
from app.models.retirement import RetirementPlan, AnnualSnapshot

class RecommendationEngine:
    @staticmethod
    def generate_recommendations(
        user: User, 
        plan: RetirementPlan, 
        current_portfolio_allocation: Dict[str, Any],
        active_goal_titles: List[str] = [],
        active_action_titles: List[str] = []
    ) -> List[Dict[str, Any]]:
        """
        Analyzes the user's financial profile to generate actionable recommendations.

        Returns:
            List[Dict]: A list of recommendation objects containing title, description, impact, actionType, and data.
        """
        recommendations = []
        
        # Helper for case-insensitive exact & loose match
        def is_title_present(target_title: str, title_list: List[str]) -> bool:
            if not title_list:
                return False
            target = target_title.lower()
            # Check for exact match first (case-insensitive)
            # User asked for "full title, case insensitive" logic. 
            # But earlier "Emergency Fund" checking was loose. 
            # Let's support both: if the goal title IS the target, OR if it's very likely the same thing.
            # Actually user said: "modify this logic to match the full tiltle, still case insenstive."
            # So stricter is better.
            return any(t.lower() == target for t in title_list)

        # 1. Savings Rate Analysis
        monthly_income = (float(user.currentIncome or 0) + float(user.spouseCurrentIncome or 0)) / 12
        monthly_savings = (
            float(user.investmentContribution or 0) + 
            float(user.retirementAccount401kContribution or 0) + 
            float(user.retirementAccountIRAContribution or 0) + 
            float(user.retirementAccountRothContribution or 0)
        ) / 12
        
        savings_rate = (monthly_savings / monthly_income * 100) if monthly_income > 0 else 0
        
        # Check against actions too
        rec_savings_title = "Boost Your Savings Rate"
        if not is_title_present(rec_savings_title, active_action_titles):
            if savings_rate < 15:
                recommendations.append({
                    "id": "rec_savings_rate_high",
                    "title": rec_savings_title,
                    "description": f"Your current savings rate is {int(savings_rate)}%. Aiming for at least 15% is recommended for long-term security.",
                    "category": "saving",
                    "impact": "high",
                    "status": "active",
                    "actionType": "ACTION",
                    "data": {"actionCategory": "budget"}
                })
            elif savings_rate < 20:
                 # Check alternate title
                 rec_savings_med = "Increase Savings to 20%"
                 if not is_title_present(rec_savings_med, active_action_titles):
                    recommendations.append({
                        "id": "rec_savings_rate_med",
                        "title": rec_savings_med,
                        "description": "You are doing well, but increasing your savings rate to 20% would significantly accelerate your timeline.",
                        "category": "saving",
                        "impact": "medium",
                        "status": "active",
                        "actionType": "ACTION",
                        "data": {"actionCategory": "budget"}
                    })
            
        # 2. Emergency Fund Analysis
        # Check if user already has an Emergency Fund goal OR action
        # If they added it as a goal -> invisible. If they added it as an action -> invisible.
        ef_title = "Emergency Fund"
        # The recommendation title is "Build Emergency Fund", so the created goal uses that title.
        has_ef_goal = is_title_present("Emergency Fund", active_goal_titles) or \
                      is_title_present("Build Emergency Fund", active_goal_titles) or \
                      is_title_present("Build Emergency Fund", active_action_titles)
        
        if not has_ef_goal:
            # Calculate what the goal SHOULD be
            from app.services.goal_calculator import GoalCalculator
            ef_values = GoalCalculator.calculate_initial_values(user, "EMERGENCY_FUND")
            
            # Logic: If current < target, recommend it
            if ef_values["currentAmount"] < ef_values["targetAmount"]:
                 months_covered = ef_values["currentAmount"] / (float(user.totalMonthlyExpenses or 4000))
                 recommendations.append({
                    "id": "rec_emergency_fund",
                    "title": "Build Emergency Fund",
                    "description": f"You have {int(months_covered)} months of expenses saved. We recommend keeping 6 months liquid.",
                    "category": "risk",
                    "impact": "high",
                    "status": "active",
                    "actionType": "GOAL",
                    "data": {
                        "goalType": "EMERGENCY_FUND",
                        "currentAmount": ef_values["currentAmount"],
                        "targetAmount": ef_values["targetAmount"],
                        "icon": "Shield",
                        "goalCategory": "savings"
                    }
                })
            
        # 3. 401k Contribution Analysis
        # Recommended Title: "Maximize 401(k)"
        # Note: Titles are matched loosely in filtering, so "Maximize 401(k)" is fine.
        has_401k_goal = is_title_present("Max 401(k)", active_goal_titles) or \
                        is_title_present("Maximize 401(k)", active_goal_titles)
        
        if not has_401k_goal:
            annual_401k = float(user.retirementAccount401kContribution or 0)
            target_401k = 23000.0
            if annual_401k < target_401k and annual_401k > 0:
                 recommendations.append({
                    "id": "rec_401k_max",
                    "title": "Maximize 401(k)",
                    "description": f"You are contributing ${int(annual_401k):,} annually. Consider increasing up to the $23,000 IRS limit.",
                    "category": "tax",
                    "impact": "medium",
                    "status": "active",
                    "actionType": "GOAL",
                    "data": {
                        "goalType": "RETIREMENT_401K",
                        "currentAmount": annual_401k,
                        "targetAmount": target_401k,
                        "icon": "TrendingUp",
                        "goalCategory": "retirement"
                    }
                })
            
        # 4. Asset Allocation Check
        rec_conservative_title = "Portfolio Too Conservative?"
        rec_aggressive_title = "Portfolio Too Aggressive?"
        
        # Check against ACTIONS
        has_alloc_action = is_title_present(rec_conservative_title, active_action_titles) or \
                           is_title_present(rec_aggressive_title, active_action_titles)

        if not has_alloc_action:
            current_age = user.currentAge or 30
            target_stock_pct = 110 - current_age
            current_stocks = current_portfolio_allocation.get("categories", {}).get("stocks", {}).get("percentage", 60)
            
            if current_stocks < (target_stock_pct - 15):
                 recommendations.append({
                    "id": "rec_allocation_conservative",
                    "title": rec_conservative_title,
                    "description": f"Your stock allocation is {current_stocks}%, but based on your age, you might consider closer to {target_stock_pct}% for growth.",
                    "category": "investing",
                    "impact": "medium",
                    "status": "active",
                    "actionType": "ACTION", 
                    "data": {"actionCategory": "investment"}
                })
            elif current_stocks > (target_stock_pct + 15):
                 recommendations.append({
                    "id": "rec_allocation_aggressive",
                    "title": rec_aggressive_title,
                    "description": f"Your stock allocation is {current_stocks}%, which exposes you to high volatility. A target of {target_stock_pct}% is standard for your age.",
                    "category": "risk",
                    "impact": "high",
                    "status": "active",
                    "actionType": "ACTION",
                    "data": {"actionCategory": "investment"}
                })

        # 5. Review Beneficiaries (Static Action Recommendation)
        rec_ben_title = "Review Beneficiaries"
        if not is_title_present(rec_ben_title, active_action_titles):
            recommendations.append({
                 "id": "rec_beneficiaries",
                 "title": rec_ben_title,
                 "description": "Ensure your retirement accounts and insurance policies have up-to-date beneficiary designations.",
                 "category": "estate",
                 "impact": "info",
                 "status": "active",
                 "actionType": "ACTION",
                 "data": {"actionCategory": "legal"}
            })

        return recommendations
