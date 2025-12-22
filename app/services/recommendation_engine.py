from typing import List, Dict, Any
from app.models.user import User
from app.models.retirement import RetirementPlan, AnnualSnapshot
# (No extra imports needed here as we import AIService locally inside the method to avoid circular deps if any)

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

        # Helper for safer retrieval
        def get_d(category, key, default=0):
            d = getattr(user, category, {}) or {}
            return float(d.get(key) or 0)

        # 1. Savings Rate Analysis
        monthly_income = (get_d("income", "currentIncome") + get_d("income", "spouseCurrentIncome")) / 12
        monthly_savings = (
            get_d("assets", "investmentContribution") + 
            get_d("assets", "retirementAccount401kContribution") + 
            get_d("assets", "retirementAccountIRAContribution") + 
            get_d("assets", "retirementAccountRothContribution")
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
            if ef_values["currentValue"] < ef_values["targetValue"]:
                 monthly_exp = get_d("expenses", "totalMonthlyExpenses")
                 if monthly_exp == 0: monthly_exp = 4000
                 months_covered = ef_values["currentValue"] / monthly_exp
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
                        "currentValue": ef_values["currentValue"],
                        "targetValue": ef_values["targetValue"],
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
            annual_401k = get_d("assets", "retirementAccount401kContribution")
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
                        "currentValue": annual_401k,
                        "targetValue": target_401k,
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
            current_age = (user.personal_info or {}).get("currentAge") or 30
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

        # --- AI Integration ---
        try:
            from app.services.ai_service import AIService
            
            # Prepare context
            # Prepare detailed context
            # Helper for strings
            def get_s(cat, key): return (getattr(user, cat, {}) or {}).get(key)

            user_profile = {
                "demographics": {
                    "age": get_d("personal_info", "currentAge"),
                    "retirementAge": get_d("personal_info", "targetRetirementAge"),
                    "location": get_s("personal_info", "currentLocation") or "US",
                    "maritalStatus": get_s("personal_info", "maritalStatus"),
                    "dependents": int(get_d("personal_info", "dependents")),
                    "riskTolerance": get_s("risk", "riskTolerance")
                },
                "income": {
                    "user": get_d("income", "currentIncome"),
                    "spouse": get_d("income", "spouseCurrentIncome"),
                    "other1": {"source": get_s("income", "otherIncomeSource1"), "amount": get_d("income", "otherIncomeAmount1")},
                    "other2": {"source": get_s("income", "otherIncomeSource2"), "amount": get_d("income", "otherIncomeAmount2")},
                    "growthRate": get_d("income", "expectedIncomeGrowth")
                },
                "assets": {
                    "savings": get_d("assets", "savingsBalance"),
                    "checking": get_d("assets", "checkingBalance"),
                    "investments": get_d("assets", "investmentBalance"),
                    "realEstate": get_d("assets", "realEstateValue"),
                    "401k": get_d("assets", "retirementAccount401k"),
                    "ira": get_d("assets", "retirementAccountIRA"),
                    "roth": get_d("assets", "retirementAccountRoth"),
                    "hsa": get_d("assets", "hsaBalance")
                },
                "contributions_monthly": {
                    "savings": get_d("assets", "investmentContribution") / 12, # Assuming this is general investment
                    "401k": get_d("assets", "retirementAccount401kContribution") / 12,
                    "ira": get_d("assets", "retirementAccountIRAContribution") / 12,
                    "roth": get_d("assets", "retirementAccountRothContribution") / 12
                },
                "liabilities": {
                    "mortgage": {
                        "balance": get_d("liabilities", "mortgageBalance"),
                        "rate": get_d("liabilities", "mortgageRate"),
                        "payment": get_d("liabilities", "mortgagePayment"),
                        "yearsLeft": int(get_d("liabilities", "mortgageYearsLeft"))
                    },
                    "creditCards": get_d("liabilities", "creditCardDebt"),
                    "studentLoans": get_d("liabilities", "studentLoanDebt"),
                    "otherDebt": get_d("liabilities", "otherDebt")
                },
                "expenses": {
                    "monthlyTotal": get_d("expenses", "totalMonthlyExpenses"),
                    "breakdown": (user.expenses or {}).get("breakdown", []) 
                }
            }
            
            from app.services.retirement_service import RetirementService
            inputs = RetirementService._resolve_inputs(plan, user)

            current_net_worth = (
                get_d("assets", "savingsBalance") + 
                get_d("assets", "checkingBalance") + 
                get_d("assets", "investmentBalance") + 
                get_d("assets", "realEstateValue") + 
                get_d("assets", "retirementAccount401k") + 
                get_d("assets", "retirementAccountIRA") + 
                get_d("assets", "retirementAccountRoth") + 
                get_d("assets", "hsaBalance")
            ) - (
                get_d("liabilities", "mortgageBalance") + 
                get_d("liabilities", "creditCardDebt") + 
                get_d("liabilities", "studentLoanDebt") + 
                get_d("liabilities", "otherDebt")
            )

            plan_summary = {
                "retirementAge": inputs["retirementAge"],
                "lifeExpectancy": inputs["endAge"], # or user.lifeExpectancy? inputs['endAge'] comes from plan/overrides
                "targetSpending": inputs["desiredAnnualRetirementSpending"],
                "currentNetWorth": current_net_worth,
                "portfolio": current_portfolio_allocation
            }
            
            # We need to pass simple lists of strings for context
            # Ideally we pass full objects but titles are sufficient for "don't duplicate" context
            goals_ctx = [{"title": t} for t in active_goal_titles]
            actions_ctx = [{"title": t} for t in active_action_titles]
            
            ai_recs = AIService.generate_financial_advice(
                user_profile,
                plan_summary,
                goals_ctx,
                actions_ctx,
                recommendations, # Existing rule-based ones
                user_id=str(user.id)
            )
            
            # Filter AI Recs (Double Check)
            for rec in ai_recs:
                # Check uniqueness against Goals, Actions, AND existing Recommendations
                is_duplicate = (
                    is_title_present(rec["title"], active_goal_titles) or
                    is_title_present(rec["title"], active_action_titles) or
                    any(r["title"] == rec["title"] for r in recommendations)
                )
                
                if not is_duplicate:
                    recommendations.append(rec)
                    
        except Exception as e:
            # Fail silently on AI, fallback to rules
            print(f"AI Integration Error: {e}")

        return recommendations

    @staticmethod
    def trigger_ai_refresh(
        user: User, 
        plan: RetirementPlan, 
        active_goal_titles: List[str],
        active_action_titles: List[str],
        current_portfolio_allocation: Dict[str, Any] = {}
    ):
        """
        Background task to force refresh AI recommendations.
        """
        try:
            from app.services.ai_service import AIService
            
             # Helper for safer retrieval (duplicate definition because it's static context)
            def get_d(category, key, default=0):
                d = getattr(user, category, {}) or {}
                return float(d.get(key) or 0)
            def get_s(cat, key): return (getattr(user, cat, {}) or {}).get(key)

            user_profile = {
                "demographics": {
                    "age": get_d("personal_info", "currentAge"),
                    "retirementAge": get_d("personal_info", "targetRetirementAge"),
                    "location": get_s("personal_info", "currentLocation") or "US",
                    "maritalStatus": get_s("personal_info", "maritalStatus"),
                    "dependents": int(get_d("personal_info", "dependents")),
                    "riskTolerance": get_s("risk", "riskTolerance")
                },
                "income": {
                    "user": get_d("income", "currentIncome"),
                    "spouse": get_d("income", "spouseCurrentIncome"),
                    "other1": {"source": get_s("income", "otherIncomeSource1"), "amount": get_d("income", "otherIncomeAmount1")},
                    "other2": {"source": get_s("income", "otherIncomeSource2"), "amount": get_d("income", "otherIncomeAmount2")},
                    "growthRate": get_d("income", "expectedIncomeGrowth")
                },
                "assets": {
                    "savings": get_d("assets", "savingsBalance"),
                    "checking": get_d("assets", "checkingBalance"),
                    "investments": get_d("assets", "investmentBalance"),
                    "realEstate": get_d("assets", "realEstateValue"),
                    "401k": get_d("assets", "retirementAccount401k"),
                    "ira": get_d("assets", "retirementAccountIRA"),
                    "roth": get_d("assets", "retirementAccountRoth"),
                    "hsa": get_d("assets", "hsaBalance")
                },
                "contributions_monthly": {
                    "savings": get_d("assets", "investmentContribution") / 12, # Assuming this is general investment
                    "401k": get_d("assets", "retirementAccount401kContribution") / 12,
                    "ira": get_d("assets", "retirementAccountIRAContribution") / 12,
                    "roth": get_d("assets", "retirementAccountRothContribution") / 12
                },
                "liabilities": {
                    "mortgage": {
                        "balance": get_d("liabilities", "mortgageBalance"),
                        "rate": get_d("liabilities", "mortgageRate"),
                        "payment": get_d("liabilities", "mortgagePayment"),
                        "yearsLeft": int(get_d("liabilities", "mortgageYearsLeft"))
                    },
                    "creditCards": get_d("liabilities", "creditCardDebt"),
                    "studentLoans": get_d("liabilities", "studentLoanDebt"),
                    "otherDebt": get_d("liabilities", "otherDebt")
                },
                "expenses": {
                    "monthlyTotal": get_d("expenses", "totalMonthlyExpenses"),
                    "breakdown": (user.expenses or {}).get("breakdown", []) 
                }
            }
            
            # Resolve inputs
            from app.services.retirement_service import RetirementService
            inputs = RetirementService._resolve_inputs(plan, user)
            
            # Recalculate Net Worth
            current_net_worth = (
                get_d("assets", "savingsBalance") + 
                get_d("assets", "checkingBalance") + 
                get_d("assets", "investmentBalance") + 
                get_d("assets", "realEstateValue") + 
                get_d("assets", "retirementAccount401k") + 
                get_d("assets", "retirementAccountIRA") + 
                get_d("assets", "retirementAccountRoth") + 
                get_d("assets", "hsaBalance")
            ) - (
                get_d("liabilities", "mortgageBalance") + 
                get_d("liabilities", "creditCardDebt") + 
                get_d("liabilities", "studentLoanDebt") + 
                get_d("liabilities", "otherDebt")
            )

            plan_summary = {
                "retirementAge": inputs["retirementAge"],
                "lifeExpectancy": inputs["endAge"],
                "targetSpending": float(inputs["desiredAnnualRetirementSpending"] or 0),
                "currentNetWorth": current_net_worth,
                "portfolio": current_portfolio_allocation
            }
            
            goals_ctx = [{"title": t} for t in active_goal_titles]
            actions_ctx = [{"title": t} for t in active_action_titles]
            
            # For background refresh, we might pass empty existing recommendations or standard ones?
            # AI normally filters out existing reccs. If we pass empty, it might suggest things we already have.
            # Ideally we pass current rule-based ones. 
            # But calculating them requires calling `generate_recommendations` recursively which is fine.
            # Let's perform a lightweight call to self.generate_recommendations? No, that requires inputs.
            # Let's pass empty for now. The deduplication happens at READ time in the engine anyway.
            # The AI cache serves raw AI ideas. The engine filters them. So passing empty here is acceptable 
            # as long as the prompt doesn't fail.
            
            AIService.generate_financial_advice(
                user_profile,
                plan_summary,
                goals_ctx,
                actions_ctx,
                existing_recommendations=[], 
                user_id=str(user.id),
                force_refresh=True
            )
        except Exception as e:
            print(f"Background AI Refresh Failed: {e}")
