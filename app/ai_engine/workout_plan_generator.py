# Workout plan JSON shape (use in prompt):
# { "days": [ { "day": 1, "exercises": [ { "exercise_id": 1, "name": "...", "instructions": "detailed 2-4 sentences...", "duration_min": 10 } ] } ] }

import json
from app.ai_engine.gemini_client import generate_text
from app.services.user_service import get_user_by_id
from app.services.workout_service import get_workouts_filtered, get_all_workouts
from app.services.workout_plan_service import create_workout_plan


def workouts_to_context(workouts):
    """Turn a list of Workout objects into one string for the prompt."""
    lines = []
    for w in workouts:
        block = (
            f"ID: {w.id} | Name: {w.exercise_name} | Category: {w.category} | "
            f"Difficulty: {w.difficulty} | Goal: {w.goal} | Equipment: {w.equipment_required}"
        )
        if getattr(w, "suggested_instructions", None):
            block += f"\n  Instructions: {w.suggested_instructions}"
        lines.append(block)
    return "\n\n".join(lines)


def build_workout_plan_prompt(user, workouts, minutes_per_day, num_days=7):
    """Build the prompt for Gemini: user constraints + workout list + JSON instructions."""
    workout_context = workouts_to_context(workouts)
    goal = getattr(user, "goal", "Maintain Weight") or "Maintain Weight"
    equipment = getattr(user, "equipment", "None") or "None"
    minutes = int(minutes_per_day or 30)

    prompt = f"""You are a fitness assistant for students. Create a {num_days}-day workout plan with DETAILED instructions for each exercise.

USER: Goal={goal}, Equipment available={equipment}, Minutes per day={minutes}.

RULES:
- Use ONLY the exercises listed below. Pick by ID.
- Only use exercises where equipment_required matches "{equipment}" (or "None" if user has no equipment).
- Total time per day should be about {minutes} minutes.
- For EACH exercise you MUST provide a detailed "instructions" field: 2–4 full sentences that include (1) how to perform the exercise step-by-step, (2) key form or technique tips, (3) sets/reps or duration guidance if applicable, (4) one short safety or intensity note. Use the suggested_instructions from the EXERCISES context as a base but expand into clear, user-friendly detail. Do not output one-line instructions.
- Output valid JSON only, no markdown. Shape:
{{"days": [{{"day": 1, "exercises": [{{"exercise_id": 1, "name": "...", "instructions": "Warm up for 2 min. Do 3 sets of 12 reps with 60 sec rest. Keep core tight and back straight. Stop if you feel joint pain.", "duration_min": 10}}]}}]}}

EXERCISES (use only these; expand their suggested_instructions into full detail in your output):
{workout_context}

Output the JSON workout plan now:"""

    return prompt


def generate_workout_plan(user, workouts, minutes_per_day, num_days=7):
    """Call Gemini to generate a workout plan JSON; return dict or None on failure."""
    prompt = build_workout_plan_prompt(user, workouts, minutes_per_day, num_days)
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
    return plan


def generate_and_save_workout_plan(session, user_id):
    """Load user, get workouts, generate plan with Gemini, save and return plan dict."""
    user = get_user_by_id(session, user_id)
    if not user:
        return None
    goal = getattr(user, "goal", "Maintain Weight") or "Maintain Weight"
    equipment = getattr(user, "equipment", "None") or "None"
    minutes = int(getattr(user, "workout_minutes_per_day", 30) or 30)
    workouts = get_workouts_filtered(session, goal=goal, equipment=equipment)
    if not workouts:
        workouts = get_workouts_filtered(session, equipment=equipment)
    if not workouts:
        workouts = get_all_workouts(session)
    if not workouts:
        return None
    plan = generate_workout_plan(user, workouts, minutes, 7)
    if not plan:
        return None
    create_workout_plan(session, user_id, plan)
    return plan