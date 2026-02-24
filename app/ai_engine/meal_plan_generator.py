# LLM generates the full meal plan; DB recipes are context only.
# JSON shape:
# {
#   "days": [
#     {
#       "day": 1,
#       "date": "YYYY-MM-DD",
#       "meals": [
#         {
#           "slot": "early_morning",
#           "time": "6:30 AM",
#           "name": "Banana and almonds",
#           "recipe_detail": "Ingredients: ... Method/notes: ...",
#           "calories": 120
#         },
#         ... (7 slots per day)
#       ],
#       "grocery_list": ["item1", "item2", ...]
#     }
#   ],
#   "total_weekly_cost": number
# }

import json
from datetime import datetime, timedelta
from app.ai_engine.gemini_client import generate_text
from app.services.user_service import get_user_by_id
from app.services.recipe_service import get_recipes_filtered, get_all_recipes
from app.services.meal_plan_service import create_meal_plan
from app.ai_engine.calorie_engine import get_all_metrics

SLOT_ORDER = [
    ("early_morning", "Early morning (6:30 AM)"),
    ("breakfast", "Breakfast (8:00 AM)"),
    ("mid_morning_snack", "Mid-morning snack (10:30 AM)"),
    ("lunch", "Lunch (1:00 PM)"),
    ("evening_snack", "Evening snack (4:30 PM)"),
    ("dinner", "Dinner (7:30 PM)"),
    ("before_bed", "Before bed (9:00 PM)"),
]


def recipes_to_context(recipes, max_chars=8000):
    """Turn recipes into one string for LLM context (inspiration only)."""
    lines = []
    for r in recipes:
        block = (
            f"- {r.name}: {getattr(r, 'meal_type', 'Any')} | "
            f"Cal: {r.calories_per_serving} | P: {r.protein_g}g C: {r.carbs_g}g F: {r.fat_g}g | "
            f"Diet: {r.diet_type} | Cuisine: {r.cuisine or 'Any'}"
        )
        if getattr(r, "ingredients", None):
            block += f"\n  Ingredients: {r.ingredients[:300]}"
        if getattr(r, "instructions", None):
            block += f"\n  Method: {r.instructions[:300]}"
        lines.append(block)
    out = "\n".join(lines)
    return out[:max_chars] if len(out) > max_chars else out


def build_meal_plan_prompt(user, recipes, calorie_target, budget, num_days=7):
    """Build prompt: LLM generates full plan with 7 slots per day, detailed recipe per meal, grocery list per day."""
    recipe_context = recipes_to_context(recipes)
    goal = getattr(user, "goal", "Maintain Weight") or "Maintain Weight"
    diet = getattr(user, "dietary_preference", "Veg") or "Veg"
    cuisine_pref = getattr(user, "cuisine", None) or "any"
    budget = float(budget)
    slots_desc = ", ".join(f'"{s[0]}"' for s in SLOT_ORDER)

    prompt = f"""You are a student-friendly nutrition assistant. Generate a {num_days}-day meal plan. You MUST output valid JSON only (no markdown, no code fence).

USER: Goal={goal}, Diet={diet}, Cuisine preference={cuisine_pref}. Daily calorie target≈{calorie_target} kcal. Weekly budget≈₹{budget}.

RULES:
1. Each day has exactly these 7 meal slots in this order: {slots_desc}.
2. For each meal provide: "slot" (one of those keys), "time" (e.g. "6:30 AM"), "name" (dish name), "recipe_detail" (detailed recipe: ingredients with quantities + short method or key steps; 2-5 sentences), "calories" (number).
3. Provide ONE "weekly_grocery_list" at the plan level (NOT per day): a single array of strings for the whole week. Each string MUST have exactly 4 parts separated by pipe: "Item name | total_quantity_for_week | approx_cost_rupees | reusable". List EVERY ingredient separately — do NOT group (e.g. do NOT write "Basic Spices (Salt, Turmeric, ...)". Instead list "Salt | 200g | 20 | yes", "Turmeric | 50g | 30 | yes", "Cumin Seeds | 50g | 25 | yes", "Mustard Seeds | 50g | 25 | yes", "Red Chili Powder | 50g | 40 | yes" as separate entries). total_quantity_for_week: realistic shopper-friendly amount for 7 days (e.g. "6 pieces", "0.5 kg", "1 litre", "200g"). reusable: "yes" for pantry (oil, bread, paste, spices, atta, flour, rice, dal); "no" for perishables. No pipe inside the item name.
4. Total weekly cost must be reasonable for budget ₹{budget}. Match daily calories to about {calorie_target}.
5. Use the RECIPE CONTEXT below only as inspiration. You are free to create meals that fit the user's diet and goal; do not restrict yourself to only listing recipe IDs.

RECIPE CONTEXT (for inspiration only; you generate the actual plan):
{recipe_context}

    Output a single JSON object with this exact shape. Include "weekly_grocery_list" ONCE at plan level (total for whole week, realistic quantities).
{{"days": [{{"day": 1, "date": "YYYY-MM-DD", "meals": [{{"slot": "early_morning", "time": "6:30 AM", "name": "...", "recipe_detail": "...", "calories": 120}}, ... 7 meals per day]}}, ... {num_days} days], "weekly_grocery_list": ["Apple | 0.5 kg | 60 | no", "Banana | 6 pieces | 30 | no", "Cooking oil | 1 litre | 180 | yes", ...], "total_weekly_cost": number}}

Output the JSON now (no other text):"""

    return prompt


def generate_meal_plan(user, recipes, calorie_target, budget, num_days=7):
    """Call Gemini to generate full meal plan JSON; return dict or None."""
    prompt = build_meal_plan_prompt(user, recipes, calorie_target, budget, num_days)
    raw = generate_text(prompt)
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(plan, dict) or "days" not in plan:
        return None
    plan.setdefault("total_weekly_cost", 0)
    plan.setdefault("weekly_grocery_list", [])
    for d in plan.get("days", []):
        d.setdefault("grocery_list", [])
    return plan


def generate_and_save_meal_plan(session, user_id):
    """Load user, get recipes as context, generate full plan with LLM, save and return plan dict."""
    user = get_user_by_id(session, user_id)
    if not user:
        return None
    metrics = get_all_metrics(user)
    calorie_target = metrics["calorie_target"]
    budget = float(getattr(user, "budget", 500) or 500)
    diet = (getattr(user, "dietary_preference", "Veg") or "Veg").strip().lower()
    cuisine_pref = (getattr(user, "cuisine", None) or "").strip() or None
    if cuisine_pref and cuisine_pref.lower() == "any":
        cuisine_pref = None
    recipes = get_recipes_filtered(session, diet_type=diet, cuisine=cuisine_pref)
    if not recipes:
        recipes = get_recipes_filtered(session, diet_type=diet)
    if not recipes:
        recipes = get_all_recipes(session)
    # Pass recipes as context even if empty; LLM can still generate
    plan = generate_meal_plan(user, recipes or [], calorie_target, budget, 7)
    if not plan:
        return None
    weekly_cost = plan.get("total_weekly_cost", 0)
    create_meal_plan(session, user_id, calorie_target, plan, weekly_cost)
    return plan