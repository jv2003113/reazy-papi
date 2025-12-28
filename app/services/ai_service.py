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

        # Prepare Prompt (Shared)
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
        1. Suggest NEW recommendations that are NOT covered by existing goals, actions, or current recommendations.
        2. Focus on high impact recommendations first. 
        3. Include details of what you see in the plan that is prompting you to give the recommendation.  
        4. If the recommendation is for certain thresholds, like expense is greater than certain percent of income, set that up as a goal and provide both percent numbers as current and target.
        5. Return a JSON array of objects. Each object must strictly follow this schema:
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
                "actionCategory": "general" | "legal" | "investment" | "budget" (only if actionType=ACTION),
                "currentValue": <number> (optional, for tracking progress),
                "targetValue": <number> (optional, for tracking progress)
                "valueType": "money" | "percent" | "number" (REQUIRED. Default "money". Use "number" for age/years/counts, "percent" for rates, "money" for currency) 
             }}
           }}
        6. Do not output markdown code blocks. Output RAW JSON only.
        """

        try:
            recommendations = []
            
            # Check if AI is explicitly disabled or unconfigured
            if not settings.AI_PROVIDER:
                 logger.info("AI_PROVIDER not set. Skipping AI recommendations.")
                 return []
                 
            provider = settings.AI_PROVIDER.lower()
            
            if provider == "ollama":
                logger.info(f"Using AI Provider: Ollama ({settings.OLLAMA_MODEL})")
                recommendations = AIService._generate_ollama(prompt)
            elif provider == "google":
                # Default to Google
                api_key = settings.GEMINI_API_KEY
                if not api_key:
                    logger.info("GEMINI_API_KEY not found. Skipping Google AI recommendations.")
                    return []
                recommendations = AIService._generate_google(api_key, prompt)
            else:
                logger.warning(f"Unknown AI_PROVIDER '{provider}'. Skipping AI.")
                return []
            
            # Enforce required fields (status, category) just in case AI missed them
            for r in recommendations:
                if "status" not in r:
                    r["status"] = "active"

                if "description" not in r or not r["description"]:
                    r["description"] = f"AI Recommendation: {r.get('title', 'Financial Advice')}"
                
                if "category" not in r:
                    # Attempt to derive from data
                    data = r.get("data", {})
                    if "goalCategory" in data:
                        gc = data["goalCategory"].lower()
                        if "retirement" in gc: r["category"] = "investing"
                        elif "debt" in gc: r["category"] = "debt"
                        else: r["category"] = "saving"
                    elif "actionCategory" in data:
                        ac = data["actionCategory"].lower()
                        if "investment" in ac: r["category"] = "investing"
                        elif "legal" in ac: r["category"] = "estate"
                        elif "budget" in ac: r["category"] = "saving"
                        else: r["category"] = "saving"
                    else:
                        r["category"] = "saving" # Safe default
            
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

    @staticmethod
    def extract_portfolio_from_file(
        file_content: bytes,
        mime_type: str,
        user_id: str = "default"
    ) -> dict:
        """
        Extracts portfolio data from a file (PDF/Image) using Google Gemini.
        """
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not found. Skipping extraction.")
            return {"error": "AI service not configured"}
            
        prompt = """
        You are an intelligent financial data extraction assistant. 
        Analyze the attached document (which may be a brokerage statement or screenshot) and extract all investment account and holding information.
        
        Return a JSON object with this structure:
        {
          "accounts": [
            {
              "accountName": "string (e.g. 'Individual Brokerage', 'Roth IRA')",
              "accountType": "string (one of: '401k', 'roth_ira', 'traditional_ira', 'brokerage', 'hsa')",
              "balance": number,
              "holdings": [
                {
                   "ticker": "string (e.g. AAPL, VTI)",
                   "name": "string (optional security name)",
                   "percentage": "string (percentage of account, e.g. '25.5')",
                   "amount": number (optional, dollar amount if percentage not available)
                }
              ]
            }
          ]
        }
        
        Rules:
        1. If multiple accounts are detected, list them all.
        2. Infer account type from context (e.g. "IRA" -> "traditional_ira", "Roth" -> "roth_ira"). Default to "brokerage".
        3. Extract holdings for each account. If holdings are mixed/unclear, do your best to assign them.
        4. If a holding has no ticker (e.g. "Cash"), use symbol "CASH" or similar.
        5. Return RAW JSON only. No markdown formatting.
        """
        
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=api_key)
            
            # Construct content with file part
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=file_content, mime_type=mime_type),
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ]
            )
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
            
        except Exception as e:
            logger.error(f"Gemini Extraction Error: {e}")
            return {"error": str(e)}

    @staticmethod
    def _generate_google(api_key: str, prompt: str) -> list[dict]:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Google AI Error: {e}")
            raise e

    @staticmethod
    def _generate_ollama(prompt: str) -> list[dict]:
        import urllib.request
        import urllib.error
        import re
        
        url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode('utf-8')
                res_json = json.loads(res_body)
                
                text = res_json.get("response", "").strip()
                
                # Strip <think>...</think> (DeepSeek reasoning)
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                
                # Clean markdown code blocks
                text = text.replace('```json', '').replace('```', '').strip()
                
                # Check for empty response
                if not text:
                    logger.warning("Ollama returned empty text after stripping.")
                    return []

                parsed = json.loads(text)
                
                # Check if it was a string that needs DOUBLE parsing (unlikely but possible)
                if isinstance(parsed, str):
                    try:
                        parsed = json.loads(parsed)
                    except:
                        pass
                
                if isinstance(parsed, dict):
                    # AI might have returned wrapped object like {"recommendations": [...]}
                    if "recommendations" in parsed and isinstance(parsed["recommendations"], list):
                        return parsed["recommendations"]
                    # Or just a single object? The prompt asks for array.
                    # If single object, wrap in list
                    return [parsed]
                
                if isinstance(parsed, list):
                    return parsed
                    
                logger.warning(f"Ollama returned unexpected type: {type(parsed)}")
                return []
                
        except Exception as e:
            logger.error(f"Ollama AI Error: {e}")
            # If 404, hint about model
            if "HTTP Error 404" in str(e):
                logger.error(f"Make sure model '{settings.OLLAMA_MODEL}' is pulled: `ollama pull {settings.OLLAMA_MODEL}`")
            raise e
