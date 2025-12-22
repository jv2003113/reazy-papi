import os
from google import genai
import json
import logging
import time
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path("app/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 3600  # 1 hour in seconds

class AIService:
    @staticmethod
    def generate_financial_advice(
        user_profile: dict,
        plan_summary: dict,
        goals: list[dict],
        actions: list[dict],
        existing_recommendations: list[dict],
        user_id: str = "default",
        force_refresh: bool = False
    ) -> list[dict]:
        """
        Generates financial recommendations using Google Gemini.
        Expected API Key in env: GEMINI_API_KEY
        """
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not found. Skipping AI recommendations.")
            return []

        # --- Caching Logic ---
        cache_file = CACHE_DIR / f"ai_rec_{user_id}.json"
        
        # Skip cache read if force_refresh is True
        cache_exists = cache_file.exists()
        print(f"AI Cache Check: User={user_id}, Force={force_refresh}, Enabled={settings.AI_CACHE_ENABLED}, Exists={cache_exists}, Path={cache_file}")
        
        if not force_refresh and settings.AI_CACHE_ENABLED and cache_exists:
            try:
                logger.info(f"Serving AI recommendations from cache for user {user_id}")
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    # Ensure status is present (fix for existing bad cache)
                    for r in data:
                        if "status" not in r:
                            r["status"] = "active"
                    return data
            except Exception as e:
                logger.warning(f"Failed to read cache: {e}")

        try:
            # New SDK Client Initialization
            client = genai.Client(api_key=api_key)
            
            # Construct Prompt
            prompt = f"""
            You are an expert financial advisor. Analyze the following user data and suggest 2-3 specific, actionable financial recommendations.
            
            USER PROFILE:
            {json.dumps(user_profile, indent=2)}

            RETIREMENT PLAN:
            {json.dumps(plan_summary, indent=2)}

            EXISTING GOALS:
            {json.dumps(goals, indent=2)}

            EXISTING ACTIONS:
            {json.dumps(actions, indent=2)}

            CURRENT RULE-BASED RECOMMENDATIONS:
            {json.dumps(existing_recommendations, indent=2)}

            INSTRUCTIONS:
            1. Suggest 2-3 NEW recommendations that are NOT covered by existing goals, actions, or current recommendations.
            2. Focus on "blind spots" (e.g., ).
            3. Return a JSON array of objects. Each object must strictly follow this schema:
               {{
                 "id": "ai_rec_<unique_suffix>",
                 "title": "Short Title",
                 "description": "One sentence description.",
                 "impact": "high" | "medium" | "info",
                 "status": "active",
                 "actionType": "ACTION" | "GOAL", 
                 "category": "saving" | "investing" | "debt" | "risk" | "estate" | "tax",
                 "data": {{ 
                    "icon": "Lightbulb" | "TrendingUp" | "Shield" | "AlertCircle" | "Info",
                    "goalCategory": "savings" | "retirement" | "debt" | "income" (only if actionType=GOAL),
                    "actionCategory": "general" | "legal" | "investment" | "budget" (only if actionType=ACTION)
                 }}
               }}
            4. Do not output markdown code blocks. Output RAW JSON only.
            """

            # New SDK Generation Call
            print("Calling AI")
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            
            # Clean response (remove markdown if model adds it)
            # Response object has .text property
            text = response.text.replace('```json', '').replace('```', '').strip()
            
            recommendations = json.loads(text)

            # Enforce status="active" just in case AI missed it
            for r in recommendations:
                if "status" not in r:
                    r["status"] = "active"
            
            # Save to Cache
            try:
                with open(cache_file, "w") as f:
                    json.dump(recommendations, f)
            except Exception as e:
                logger.warning(f"Failed to write cache: {e}")

            return recommendations

        except Exception as e:
            logger.error(f"Error generating AI recommendations: {e}")
            return []
