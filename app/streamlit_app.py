"""Health Companion – AI-powered meal and workout plans for students."""
import sys
from pathlib import Path

# Ensure project root is on path so "app" is the package (avoids "app is not a package" when run from app/)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import re
from io import BytesIO
from html import escape as html_escape
import streamlit as st
from datetime import date
import pandas as pd
import altair as alt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.database import SessionLocal
from app.config import GEMINI_API_KEY, DATABASE_URL
from app.services.user_service import (
    get_user_by_id,
    get_user_by_profile_code,
    get_user_by_email,
    create_user,
    update_user_preferences,
)
from app.services.meal_plan_service import get_latest_meal_plan
from app.services.workout_plan_service import get_latest_workout_plan
from app.services.progress_service import log_weight, get_weight_logs, get_latest_weight_log
from app.ai_engine.calorie_engine import (
    get_all_metrics,
    ideal_weight_kg,
    healthy_bmi_range_kg,
    estimate_weeks_to_weight,
)
from app.ai_engine.meal_plan_generator import generate_and_save_meal_plan, SLOT_ORDER
from app.ai_engine.workout_plan_generator import generate_and_save_workout_plan

# Must be first Streamlit command
st.set_page_config(
    page_title="Health Companion",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS for a cleaner, more professional UI
st.markdown("""
<style>
    /* Hide sidebar completely – full-width app with tabs */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebar"] + div { margin-left: 0 !important; max-width: 100% !important; }
    /* Main content area – more top space so tabs aren't chopped */
    .block-container { padding-top: 3rem !important; padding-bottom: 3rem; max-width: 1100px; }
    /* Headers */
    h1 { font-weight: 700; color: #1a1a2e; letter-spacing: -0.02em; margin-bottom: 0.25rem !important; }
    h2 { font-weight: 600; color: #16213e; font-size: 1.25rem !important; margin-top: 1.5rem !important; }
    /* Subtle caption */
    .stCaptionContainer p { color: #64748b; font-size: 0.95rem; }
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border-right: 1px solid #e2e8f0;
    }
    [data-testid="stSidebar"] .stRadio label { font-weight: 500; }
    /* Card-like expanders */
    .streamlit-expanderHeader { background: #f8fafc; border-radius: 8px; }
    /* Metric cards */
    [data-testid="stMetricValue"] { font-weight: 700; color: #0f172a; }
    /* Consistent button sizing and alignment */
    .stButton > button {
        min-height: 2.75rem !important;
        padding: 0.5rem 1.25rem !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: box-shadow 0.2s ease;
        white-space: nowrap !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%) !important;
        box-shadow: 0 4px 12px rgba(2, 132, 199, 0.35);
    }
    .stButton > button:not([kind="primary"]) {
        border: 1px solid #e2e8f0 !important;
        background: #fff !important;
        color: #475569 !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        background: #f8fafc !important;
        border-color: #cbd5e1 !important;
    }
    /* Button row: same height and alignment (Generate / Regenerate) */
    [data-testid="stHorizontalBlock"]:has(.stButton):not(:has([data-testid="stMetric"])) {
        display: flex !important;
        align-items: stretch !important;
        gap: 0.75rem !important;
    }
    [data-testid="stHorizontalBlock"]:has(.stButton):not(:has([data-testid="stMetric"])) [data-testid="column"] {
        display: flex !important;
        align-items: stretch !important;
    }
    [data-testid="stHorizontalBlock"]:has(.stButton):not(:has([data-testid="stMetric"])) [data-testid="column"]:first-child .stButton {
        width: 100%;
    }
    [data-testid="stHorizontalBlock"]:has(.stButton):not(:has([data-testid="stMetric"])) [data-testid="column"]:first-child .stButton > button {
        width: 100%;
    }
    /* Right column button (Regenerate) keeps natural width so text stays on one line */
    [data-testid="stHorizontalBlock"]:has(.stButton):not(:has([data-testid="stMetric"])) [data-testid="column"]:last-child .stButton > button {
        width: auto !important;
        min-width: max-content !important;
    }
    /* Info box */
    [data-testid="stAlert"] { border-radius: 8px; }
    /* Form spacing */
    .stForm { border: 1px solid #e2e8f0; border-radius: 10px; padding: 1.25rem; background: #fafbfc; }
    /* Dashboard profile card */
    .dashboard-profile-card {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
    }
    .dashboard-profile-card h3 { margin: 0 0 0.5rem 0 !important; font-size: 1rem !important; color: #64748b !important; font-weight: 600 !important; }
    .dashboard-metric-card {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-explainer { color: #64748b; font-size: 0.875rem; line-height: 1.5; margin-top: 0.5rem; }
    /* Grocery list cards */
    .grocery-card {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        display: flex;
        flex-direction: column;
        min-height: 100px;
    }
    .grocery-card .grocery-name { font-weight: 600; color: #0f172a; font-size: 1rem; margin-bottom: 0.35rem; }
    .grocery-card .grocery-cost { font-weight: 600; color: #0284c7; font-size: 1rem; margin-top: auto; }
    /* Align metric row and download button to top */
    [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
        align-items: flex-start !important;
    }
    /* Right column in each row (Regenerate, Download meal plan, Download grocery) pushed to far right */
    [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child {
        display: flex !important;
        justify-content: flex-end !important;
    }
    /* Keep button text on one line (e.g. Regenerate meal plan) */
    [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child .stButton > button,
    [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child [data-testid="stDownloadButton"] > button {
        white-space: nowrap !important;
        min-width: max-content !important;
    }
    /* Dashboard metrics grid: 4 equal cards */
    .dashboard-metrics-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin: 1rem 0 1.5rem 0;
    }
    .dashboard-metric-box {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem 1rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .dashboard-metric-box .metric-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.5rem;
        display: block;
    }
    .dashboard-metric-box .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.2;
    }
    .dashboard-metric-box .metric-unit {
        font-size: 0.8rem;
        font-weight: 500;
        color: #475569;
        margin-top: 0.15rem;
    }
    /* Tabs: clean, minimal look (no red) + breathing room at top */
    .stTabs {
        margin-top: 0.5rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        background: #f8fafc;
        padding: 0.35rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        border: 1px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.65rem 1.35rem;
        font-weight: 600;
        font-size: 0.95rem;
        border-radius: 8px;
        color: #64748b !important;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #334155 !important;
        background: #f1f5f9 !important;
    }
    .stTabs [aria-selected="true"] {
        background: #fff !important;
        color: #0f172a !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.06);
        border: none !important;
        border-bottom: none !important;
    }
    .stTabs [aria-selected="true"] span, .stTabs [aria-selected="true"] p {
        color: #0f172a !important;
    }
    /* Remove default red underline / highlight */
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-bottom: none !important;
    }
</style>
""", unsafe_allow_html=True)

# Session state defaults
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "latest_meal_plan" not in st.session_state:
    st.session_state["latest_meal_plan"] = None
if "latest_workout_plan" not in st.session_state:
    st.session_state["latest_workout_plan"] = None


def get_db_session():
    """Get a DB session and ensure it's closed after use."""
    return SessionLocal()


def _sum_quantity_strings(qtys):
    """
    Given a list of quantity strings (e.g. ["200ml", "100ml", "50ml"]), return a single total
    when all use the same unit (e.g. "350ml"). Otherwise return "qty1 + qty2 + ...".
    """
    if not qtys:
        return "—"
    parsed = []
    for q in qtys:
        q = str(q).strip()
        if not q:
            continue
        # Match optional number (int or decimal) at start, rest is unit
        m = re.match(r"^\s*([\d.]+)\s*(.*)$", q)
        if m:
            try:
                num = float(m.group(1))
                unit = (m.group(2) or "").strip()
                parsed.append((num, unit))
            except ValueError:
                parsed.append((1, q))
        else:
            parsed.append((1, q))
    if not parsed:
        return "—"
    units = [p[1].lower() for p in parsed]
    if all(u == units[0] for u in units):
        total_num = sum(p[0] for p in parsed)
        unit = parsed[0][1]
        if unit:
            return f"{total_num:g} {unit}".strip()
        return f"{total_num:g}"
    return " + ".join(qtys)


# Pantry items typically bought in larger packs and reused across weeks (for fallback when LLM doesn't set reusable)
_PANTRY_KEYWORDS = (
    "oil", "bread", "paste", "atta", "flour", "rice", "dal", "lentil", "masala", "powder",
    "spice", "asafoetida", "besan", "chana", "cumin", "turmeric", "coriander", "pepper",
    "cloves", "cardamom", "cinnamon", "mustard", "fenugreek", "biryani", "garam", "chilli",
    "ginger", "garlic", "sugar", "salt", "vinegar", "sauce", "jam", "honey", "ghee",
)


def _infer_reusable(display_name):
    """Treat as reusable if item name suggests pantry/staple (for old plans or when LLM omits flag)."""
    lower = display_name.lower()
    return any(kw in lower for kw in _PANTRY_KEYWORDS)


def _parse_and_merge_grocery_items(grocery_strings):
    """
    Parse grocery strings: "Item name | quantity | approx_cost_rupees | reusable" or 2/3 part variants.
    Merge by item name (case-insensitive): collect quantities, sum costs; item is reusable if any entry says so.
    Returns list of (display_name, total_quantity_str, total_cost, is_reusable).
    """
    merged = {}  # key -> (display_name, [quantities], total_cost, is_reusable)
    for s in grocery_strings:
        s = str(s).strip()
        if not s:
            continue
        if "|" in s:
            parts = [p.strip() for p in s.split("|", 3)]  # up to 4 parts
            name = parts[0] if parts else s
            if len(parts) >= 4:
                qty = parts[1]
                cost_str = parts[2]
                reusable_str = (parts[3] or "").lower()
                is_reusable = reusable_str in ("yes", "true", "1", "y")
            elif len(parts) == 3:
                qty = parts[1]
                cost_str = parts[2]
                is_reusable = False
            elif len(parts) == 2:
                qty = ""
                cost_str = parts[1]
                is_reusable = False
            else:
                qty, cost_str, is_reusable = "", "", False
            try:
                cost = int(re.sub(r"[^\d]", "", cost_str)) if cost_str else 0
            except (ValueError, TypeError):
                cost = 0
        else:
            name, qty, cost, is_reusable = s, "", 0, False
        if not name:
            continue
        key = name.lower().strip()
        if key not in merged:
            merged[key] = (name, [], 0, False)
        disp, qtys, total, any_reusable = merged[key]
        if qty:
            qtys.append(qty)
        merged[key] = (disp, qtys, total + cost, any_reusable or is_reusable)
    out = []
    for (disp, qtys, total, is_reusable) in merged.values():
        total_qty = _sum_quantity_strings(qtys)
        # Fallback: infer reusable from name if LLM didn't set it (e.g. old plans)
        if not is_reusable and _infer_reusable(disp):
            is_reusable = True
        out.append((disp, total_qty, total, is_reusable))
    out.sort(key=lambda x: x[0].lower())
    return out


def _parse_ingredients_to_list(ingredients_text):
    """Split recipe ingredients (comma/newline/and-separated) into a sorted, deduplicated list."""
    if not ingredients_text or not str(ingredients_text).strip():
        return []
    text = str(ingredients_text).strip()
    # Split on newlines, commas, and " and " (keep tokens)
    parts = re.split(r"[\n,]+|\s+and\s+", text, flags=re.IGNORECASE)
    seen = set()
    out = []
    for p in parts:
        p = p.strip()
        if not p or len(p) < 2:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return sorted(out, key=lambda x: x.lower())


def _pdf_escape(s):
    """Escape for ReportLab Paragraph (XML-like)."""
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;")


def _build_meal_plan_pdf(plan_obj):
    """Return PDF bytes for the 7-day meal plan."""
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(name="CustomTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=12)
    style_heading = ParagraphStyle(name="CustomHeading", parent=styles["Heading2"], fontSize=12, spaceAfter=6)
    style_body = ParagraphStyle(name="CustomBody", parent=styles["Normal"], fontSize=9, spaceAfter=4)
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = []
    cost = plan_obj.get("total_weekly_cost", 0)
    story.append(Paragraph(_pdf_escape("7-Day Meal Plan"), style_title))
    story.append(Paragraph(_pdf_escape(f"Weekly cost: Rs. {cost:.0f}"), style_body))
    story.append(Spacer(1, 12))
    for d in plan_obj.get("days", []):
        day_num = d.get("day", 0)
        date_str = d.get("date", "")
        story.append(Paragraph(_pdf_escape(f"Day {day_num} — {date_str}"), style_heading))
        meals_by_slot = {m.get("slot"): m for m in d.get("meals", [])}
        for _slot_key, label in SLOT_ORDER:
            m = meals_by_slot.get(_slot_key)
            if m:
                name = m.get("name") or m.get("recipe_name") or "Meal"
                cal = m.get("calories") or 0
                recipe = (m.get("recipe_detail") or m.get("description") or "").strip()
                story.append(Paragraph(_pdf_escape(f"{label}: {name} — {cal} kcal"), style_body))
                if recipe:
                    for line in recipe.split("\n")[:15]:
                        if line.strip():
                            story.append(Paragraph(_pdf_escape(line.strip()), style_body))
            else:
                story.append(Paragraph(_pdf_escape(f"{label}: —"), style_body))
        story.append(Spacer(1, 8))
    doc.build(story)
    return buffer.getvalue()


def _build_grocery_pdf(grocery_tuples, total_cost):
    """Return PDF bytes for the grocery list."""
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(name="GroceryTitle", parent=styles["Heading1"], fontSize=16, spaceAfter=12)
    style_body = ParagraphStyle(name="GroceryBody", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = []
    story.append(Paragraph(_pdf_escape("Grocery List (Whole Week)"), style_title))
    story.append(Paragraph(_pdf_escape("Items marked with [R] can be reused for future weeks."), style_body))
    story.append(Spacer(1, 8))
    for display_name, total_qty, approx_cost, is_reusable in grocery_tuples:
        prefix = "[R] " if is_reusable else ""
        qty_show = total_qty if (total_qty and total_qty != "—") else "—"
        cost_str = f"Rs. {approx_cost:.0f}" if approx_cost else "—"
        story.append(Paragraph(_pdf_escape(f"• {prefix}{display_name} — {qty_show} — {cost_str}"), style_body))
    if total_cost > 0:
        story.append(Spacer(1, 8))
        story.append(Paragraph(_pdf_escape(f"Total approx grocery cost: Rs. {total_cost:.0f}"), style_body))
    doc.build(story)
    return buffer.getvalue()


def check_env():
    """Return None if OK, else error message."""
    if not DATABASE_URL:
        return "Database not configured. Check your .env file (DATABASE_URL)."
    if not GEMINI_API_KEY:
        return "Gemini API key not found. Add GEMINI_API_KEY to your .env file."
    return None


# ----- Environment check -----
env_error = check_env()
if env_error:
    st.error(env_error)
    st.stop()

# ----- Restore user from URL (profile code) -----
url_code = st.query_params.get("code")
if url_code:
    db = get_db_session()
    try:
        user = get_user_by_profile_code(db, url_code)
        if user:
            st.session_state["user_id"] = user.id
    finally:
        db.close()

# ----- Header (no sidebar – branding in main area) -----
st.markdown("### 🥗 Health Companion")
st.caption("AI-powered meal and workout plans for students.")
st.markdown("")  # small spacer before tabs

# ----- Tabs -----
tab_dashboard, tab_meals, tab_workout, tab_progress = st.tabs(["Dashboard", "Nutrition & Meals", "Workout", "Progress"])

with tab_dashboard:
    user_id = st.session_state.get("user_id")

    # ----- When no user: show returning user / recover and new profile form -----
    if not user_id:
        col_recover_a, col_recover_b = st.columns(2)
        with col_recover_a:
            with st.expander("🔑 Returning user? Enter your profile code"):
                with st.form("enter_code_form"):
                    code_input = st.text_input("Profile code", placeholder="e.g. ABC12XY", key="profile_code_input").strip().upper()
                    if st.form_submit_button("Load my profile"):
                        if not code_input:
                            st.warning("Please enter your profile code.")
                        else:
                            db = get_db_session()
                            try:
                                user = get_user_by_profile_code(db, code_input)
                                if user:
                                    st.session_state["user_id"] = user.id
                                    st.query_params["code"] = user.profile_code
                                    st.rerun()
                                else:
                                    st.error("No profile found for that code. Check the code and try again.")
                            finally:
                                db.close()
        with col_recover_b:
            with st.expander("📧 Forgot your code? Recover by email"):
                with st.form("recover_by_email_form"):
                    email_input = st.text_input("Email", placeholder="Email you used when creating profile", key="recover_email_input").strip()
                    if st.form_submit_button("Recover my profile"):
                        if not email_input:
                            st.warning("Please enter your email.")
                        else:
                            db = get_db_session()
                            try:
                                user = get_user_by_email(db, email_input)
                                if user:
                                    st.session_state["user_id"] = user.id
                                    st.query_params["code"] = user.profile_code
                                    st.rerun()
                                else:
                                    st.error("No profile found for that email. Add an email when creating a profile to use this later.")
                            finally:
                                db.close()

        with st.expander("✨ New here? Create your profile", expanded=False):
            with st.form("profile_form"):
                name = st.text_input("Name", placeholder="Your name")
                age = st.number_input("Age", min_value=1, max_value=120, value=25)
                gender = st.selectbox("Gender", ["Male", "Female", "Other"])
                height_cm = st.number_input("Height (cm)", min_value=50, max_value=250, value=170)
                weight_kg = st.number_input("Weight (kg)", min_value=30.0, max_value=300.0, value=70.0, step=0.5)
                goal = st.selectbox(
                    "Goal",
                    ["Weight Loss", "Maintain Weight", "Muscle Gain"],
                )
                dietary_preference = st.selectbox("Dietary preference", ["Veg", "Non-veg", "Vegan"])
                cuisine_options = ["Any", "Indian", "Chinese", "Italian", "Mexican", "Thai", "Continental", "Mediterranean", "American", "Greek", "French"]
                cuisine = st.selectbox("Cuisine preference", cuisine_options, help="Meal plan will favor recipes from this cuisine when available.")
                budget = st.number_input("Weekly food budget (₹)", min_value=0.0, value=500.0, step=50.0)
                equipment = st.selectbox(
                    "Equipment available",
                    ["None", "Yoga Mat", "Dumbbells", "Treadmill", "Resistance Bands", "Gym Machine", "Full Gym"],
                )
                workout_minutes_per_day = st.number_input("Workout minutes per day", min_value=0, max_value=120, value=30)
                email = st.text_input("Email (optional – for recovering your profile if you forget your code)", placeholder="your@email.com")
                submitted = st.form_submit_button("Save profile", type="primary")

            if submitted:
                if not name or not name.strip():
                    st.warning("Please enter your name.")
                else:
                    db = get_db_session()
                    try:
                        user = create_user(
                            db,
                            name=name.strip(),
                            age=int(age),
                            gender=gender,
                            height_cm=float(height_cm),
                            weight_kg=float(weight_kg),
                            goal=goal,
                            dietary_preference=dietary_preference,
                            budget=float(budget),
                            equipment=equipment,
                            workout_minutes_per_day=int(workout_minutes_per_day),
                            email=email or None,
                            cuisine=cuisine if cuisine and cuisine != "Any" else None,
                        )
                        st.session_state["user_id"] = user.id
                        st.query_params["code"] = user.profile_code
                        st.success(f"Profile saved! Your profile code is **{user.profile_code}**. Bookmark this page or save the code to return later.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save profile: {e}")
                    finally:
                        db.close()

    # ----- When user exists: professional dashboard -----
    if user_id:
        db = get_db_session()
        try:
            user = get_user_by_id(db, user_id)
            if user:
                # Use last logged weight as current weight when available; else profile weight
                latest_log = get_latest_weight_log(db, user_id)
                weight_kg = float(latest_log.weight_kg) if latest_log else (getattr(user, "weight_kg", None) or 0)
                metrics = get_all_metrics(user, weight_kg_override=weight_kg)
                name = getattr(user, "name", None) or "there"
                height_cm = getattr(user, "height_cm", None) or 0
                goal = getattr(user, "goal", None) or "Maintain Weight"

                if user.profile_code:
                    st.caption(f"Profile code: **{user.profile_code}** — bookmark this page or save the code to return later.")

                # Welcome and profile summary card
                st.markdown(f"""
                <div class="dashboard-profile-card">
                    <h3>Welcome back</h3>
                    <p style="font-size: 1.5rem; font-weight: 700; color: #0f172a; margin: 0 0 0.75rem 0;">{name}</p>
                    <p style="color: #475569; margin: 0; font-size: 0.95rem;">
                        <strong>Weight</strong> {weight_kg:.1f} kg &nbsp;·&nbsp; <strong>Height</strong> {height_cm:.0f} cm &nbsp;·&nbsp; <strong>Goal</strong> {goal}
                    </p>
                </div>
                """, unsafe_allow_html=True)

                # Edit preferences form (inline on Dashboard)
                with st.expander("Edit your preferences", expanded=False):
                    with st.form("edit_profile_form"):
                        edit_name = st.text_input("Name", value=getattr(user, "name", "") or "")
                        edit_age = st.number_input(
                            "Age",
                            min_value=1,
                            max_value=120,
                            value=int(getattr(user, "age", 25) or 25),
                        )
                        gender_options = ["Male", "Female", "Other"]
                        current_gender = (getattr(user, "gender", "") or "").strip()
                        gender_index = gender_options.index(current_gender) if current_gender in gender_options else 0
                        edit_gender = st.selectbox("Gender", gender_options, index=gender_index)
                        edit_height_cm = st.number_input(
                            "Height (cm)",
                            min_value=50,
                            max_value=250,
                            value=int(float(getattr(user, "height_cm", 170) or 170)),
                        )
                        edit_weight_kg = st.number_input(
                            "Weight (kg)",
                            min_value=30.0,
                            max_value=300.0,
                            value=float(getattr(user, "weight_kg", 70.0) or 70.0),
                            step=0.5,
                        )
                        goal_options = ["Weight Loss", "Maintain Weight", "Muscle Gain"]
                        current_goal = getattr(user, "goal", goal_options[0]) or goal_options[0]
                        goal_index = goal_options.index(current_goal) if current_goal in goal_options else 0
                        edit_goal = st.selectbox("Goal", goal_options, index=goal_index)
                        diet_options = ["Veg", "Non-veg", "Vegan"]
                        current_diet = getattr(user, "dietary_preference", diet_options[0]) or diet_options[0]
                        diet_index = diet_options.index(current_diet) if current_diet in diet_options else 0
                        edit_diet = st.selectbox("Dietary preference", diet_options, index=diet_index)
                        cuisine_options = ["Any", "Indian", "Chinese", "Italian", "Mexican", "Thai", "Continental", "Mediterranean", "American", "Greek", "French"]
                        current_cuisine = getattr(user, "cuisine", None) or "Any"
                        cuisine_index = cuisine_options.index(current_cuisine) if current_cuisine in cuisine_options else 0
                        edit_cuisine = st.selectbox("Cuisine preference", cuisine_options, index=cuisine_index, help="Meal plan will favor recipes from this cuisine.")
                        edit_budget = st.number_input(
                            "Weekly food budget (₹)",
                            min_value=0.0,
                            value=float(getattr(user, "budget", 500.0) or 500.0),
                            step=50.0,
                        )
                        equipment_options = [
                            "None",
                            "Yoga Mat",
                            "Dumbbells",
                            "Treadmill",
                            "Resistance Bands",
                            "Gym Machine",
                            "Full Gym",
                        ]
                        current_equipment = getattr(user, "equipment", equipment_options[0]) or equipment_options[0]
                        equipment_index = (
                            equipment_options.index(current_equipment) if current_equipment in equipment_options else 0
                        )
                        edit_equipment = st.selectbox("Equipment available", equipment_options, index=equipment_index)
                        edit_workout_minutes = st.number_input(
                            "Workout minutes per day",
                            min_value=0,
                            max_value=120,
                            value=int(getattr(user, "workout_minutes_per_day", 30) or 30),
                        )
                        edit_email = st.text_input(
                            "Email (optional – for recovering your profile if you forget your code)",
                            value=getattr(user, "email", "") or "",
                        )
                        edit_submitted = st.form_submit_button("Save changes", type="primary")

                    if edit_submitted:
                        if not edit_name or not edit_name.strip():
                            st.warning("Please enter your name.")
                        else:
                            try:
                                updated = update_user_preferences(
                                    db,
                                    user_id,
                                    name=edit_name.strip(),
                                    age=int(edit_age),
                                    gender=edit_gender,
                                    height_cm=float(edit_height_cm),
                                    weight_kg=float(edit_weight_kg),
                                    goal=edit_goal,
                                    dietary_preference=edit_diet,
                                    budget=float(edit_budget),
                                    equipment=edit_equipment,
                                    workout_minutes_per_day=int(edit_workout_minutes),
                                    email=edit_email,
                                    cuisine=edit_cuisine if edit_cuisine and edit_cuisine != "Any" else None,
                                )
                                if updated:
                                    st.success("Preferences updated. Your dashboard has been refreshed.")
                                    st.rerun()
                                else:
                                    st.error("Could not update preferences. User not found.")
                            except Exception as e:
                                st.error(f"Could not update preferences: {e}")

                # Key metrics in equal-width cards
                st.subheader("Your health metrics")
                st.caption("Personalized from your profile. Use these to guide your nutrition and meal plans.")
                bmi, bmr, tdee, budget = metrics["bmi"], int(metrics["bmr"]), int(metrics["tdee"]), int(metrics["calorie_target"])
                st.markdown(f"""
                <div class="dashboard-metrics-row">
                    <div class="dashboard-metric-box">
                        <span class="metric-label">BMI</span>
                        <span class="metric-value">{bmi}</span>
                        <div class="metric-unit">Body Mass Index</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">BMR</span>
                        <span class="metric-value">{bmr:,}</span>
                        <div class="metric-unit">kcal/day</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">TDEE</span>
                        <span class="metric-value">{tdee:,}</span>
                        <div class="metric-unit">kcal/day</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">Daily calorie budget</span>
                        <span class="metric-value">{budget:,}</span>
                        <div class="metric-unit">kcal · {goal}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Ideal weight & timeline: professional 4-card row (current, ideal, kg to lose/gain, time)
                ideal_kg = ideal_weight_kg(height_cm)
                min_kg, max_kg = healthy_bmi_range_kg(height_cm)
                weeks_est, msg = estimate_weeks_to_weight(
                    weight_kg, ideal_kg,
                    int(metrics["tdee"]), int(metrics["calorie_target"]),
                    goal,
                )
                # Kg to lose or gain
                goal_lower = (goal or "").strip().lower()
                losing = "loss" in goal_lower or "lose" in goal_lower
                gaining = "gain" in goal_lower or "muscle" in goal_lower
                if losing and weight_kg > ideal_kg:
                    kg_diff = weight_kg - ideal_kg
                    kg_label = "To lose"
                    kg_value = f"{kg_diff:.1f}"
                elif gaining and weight_kg < ideal_kg:
                    kg_diff = ideal_kg - weight_kg
                    kg_label = "To gain"
                    kg_value = f"{kg_diff:.1f}"
                else:
                    kg_label = "To lose / gain"
                    kg_value = "—"
                # Time estimated
                if weeks_est is not None and weeks_est >= 1:
                    if weeks_est <= 4:
                        time_value = f"~{weeks_est:.0f} wk"
                    elif weeks_est <= 52:
                        time_value = f"~{weeks_est:.0f} wk (~{weeks_est/4:.0f} mo)"
                    else:
                        time_value = f"~{weeks_est:.0f} wk"
                elif msg == "maintain":
                    time_value = "Maintain"
                elif msg in ("already_at_or_below", "already_at_or_above"):
                    time_value = "At goal"
                elif msg in ("no_deficit", "no_surplus"):
                    time_value = "Adjust plan"
                else:
                    time_value = "—"
                st.subheader("Weight goal & timeline")
                st.caption("Ideal weight from healthy BMI (18.5–24.9). Time estimate assumes consistent adherence to your calorie plan.")
                current_weight_unit = "kg (from latest log)" if latest_log else "kg (from profile)"
                st.markdown(f"""
                <div class="dashboard-metrics-row">
                    <div class="dashboard-metric-box">
                        <span class="metric-label">Current weight</span>
                        <span class="metric-value">{weight_kg:.1f}</span>
                        <div class="metric-unit">kg</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">Ideal weight</span>
                        <span class="metric-value">{ideal_kg}</span>
                        <div class="metric-unit">kg</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">{kg_label}</span>
                        <span class="metric-value">{kg_value}</span>
                        <div class="metric-unit">kg</div>
                    </div>
                    <div class="dashboard-metric-box">
                        <span class="metric-label">Time estimated</span>
                        <span class="metric-value">{time_value}</span>
                        <div class="metric-unit">to reach ideal</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Detailed explanations
                st.subheader("Understanding your metrics")
                with st.expander("**BMI - Body Mass Index**", expanded=False):
                    st.markdown("""
                    **What it is:** BMI is a simple ratio of your weight to your height squared (kg/m²). It is widely used as a screening tool to categorize body weight relative to height.

                    **How we use it:** Your BMI helps place you in a range (underweight, healthy, overweight, or obese) based on WHO guidelines. It does not measure body fat directly or account for muscle mass, so it is best used alongside other metrics like BMR and TDEE for nutrition planning.

                    **Your value:** A BMI in the range 18.5–24.9 is generally conside
                    red healthy for adults. Values above or below can inform whether your calorie target should support weight loss, maintenance, or gain.
                    """)
                with st.expander("**BMR - Basal Metabolic Rate**", expanded=False):
                    st.markdown("""
                    **What it is:** BMR is the number of calories your body burns at complete rest—just to keep you alive (breathing, circulation, cell repair, temperature). It represents the minimum energy your body needs with no activity.

                    **How we calculate it:** We use the **Mifflin–St Jeor equation**, which is the standard used by dietitians and is based on your weight, height, age, and sex. It is more accurate than older formulas for most adults.

                    **Why it matters:** BMR is the foundation for your total daily energy needs. Your meal plan and calorie budget are built on top of this number, adjusted for your activity level and goal.
                    """)
                with st.expander("**TDEE - Total Daily Energy Expenditure**", expanded=False):
                    st.markdown("""
                    **What it is:** TDEE is the total number of calories you burn in a full day, including BMR plus all activity: walking, exercise, daily tasks, and even digesting food. It is your true "maintenance" intake—eating this many calories typically keeps your weight stable.

                    **How we calculate it:** We multiply your BMR by an **activity factor** (e.g. 1.4 for light-to-moderate activity, typical for students). Higher activity increases the factor; sedentary lifestyles use a lower one.

                    **Why it matters:** Your **daily calorie budget** is derived from TDEE: we subtract calories for weight loss, add for muscle gain, or match TDEE to maintain weight. All meal plans are designed to meet this budget.
                    """)
        finally:
            db.close()

with tab_meals:

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Complete your profile on the **Dashboard** tab first.")
        st.stop()

    def load_meal_plan_into_session(db):
        plan_obj = get_latest_meal_plan(db, user_id)
        if plan_obj and plan_obj.plan_json:
            import json
            st.session_state["latest_meal_plan"] = json.loads(plan_obj.plan_json)
        else:
            st.session_state["latest_meal_plan"] = None

    db = get_db_session()
    try:
        if st.session_state.get("latest_meal_plan") is None:
            load_meal_plan_into_session(db)

        gen_clicked = st.button("Generate my meal plan", type="primary", help="Generate or replace your 7-day meal plan")
        if gen_clicked:
            with st.spinner("Generating your meal plan…"):
                try:
                    plan = generate_and_save_meal_plan(db, user_id)
                    if plan:
                        st.session_state["latest_meal_plan"] = plan
                        st.success("Meal plan generated!")
                    else:
                        st.error("Could not generate plan. Please try again.")
                        st.caption("Possible causes: no recipes in the database, or the AI returned invalid data. Check that recipes are loaded (scripts/load_recipes) and your Gemini API key is set in .env.")
                except Exception as e:
                    err = str(e)
                    if "429" in err or "quota" in err.lower():
                        st.warning("Rate limit reached. Wait about a minute and try again. You can switch to gemini-2.5-flash-lite in app/ai_engine/gemini_client.py if needed.")
                    else:
                        st.error("Could not generate plan. Please try again.")
                    with st.expander("Error details (for debugging)"):
                        st.code(err)
        else:
            pass  # show existing plan below

        plan = st.session_state.get("latest_meal_plan")
        if not plan:
            st.info("Generate your first meal plan using the button above.")
        else:
            days = plan.get("days", [])
            st.subheader("Your 7-day plan")
            cost = plan.get("total_weekly_cost", 0)
            user = get_user_by_id(db, user_id)
            budget = float(getattr(user, "budget", 500) or 500) if user else 500
            within_budget = cost <= budget if cost and budget else True
            # Weekly cost on left, Download meal plan on far right
            cost_col, dl_plan_col = st.columns([4, 1])
            with cost_col:
                st.metric("Weekly cost", f"₹{cost:.0f}", delta=f"Within budget (₹{budget:.0f})" if within_budget else f"Over by ₹{cost - budget:.0f}")
            with dl_plan_col:
                st.download_button(
                    "Download meal plan",
                    data=_build_meal_plan_pdf(plan),
                    file_name="meal_plan.pdf",
                    mime="application/pdf",
                    key="dl_meal_plan",
                )

            # Grocery data (used for download and for display below)
            weekly_raw = plan.get("weekly_grocery_list") or []
            all_raw = weekly_raw if weekly_raw else [g for d in days for g in (d.get("grocery_list") or [])]
            merged_groceries = _parse_and_merge_grocery_items(all_raw)
            total_grocery_cost = sum(g[2] for g in merged_groceries)

            # Build slot key -> label for display
            slot_label = {s[0]: s[1] for s in SLOT_ORDER}

            for d in days:
                day_num = d.get("day", 0)
                date_str = d.get("date", "")
                meals_by_slot = {m.get("slot"): m for m in d.get("meals", [])}

                with st.expander(f"**Day {day_num}** — {date_str}", expanded=(day_num == 1)):
                    for slot_key, label in SLOT_ORDER:
                        m = meals_by_slot.get(slot_key)
                        if m:
                            name = m.get("name") or m.get("recipe_name") or "Meal"
                            recipe_detail = m.get("recipe_detail") or m.get("description") or ""
                            cal = m.get("calories") or 0
                            st.markdown(f"##### {label}")
                            st.markdown(f"**{name}** — {cal} kcal")
                            if recipe_detail:
                                st.markdown(recipe_detail)
                            st.markdown("---")
                        else:
                            st.markdown(f"##### {label}")
                            st.caption("—")
                            st.markdown("---")

            # Grocery list: caption row, download button a bit more to the right
            st.subheader("Grocery list (whole week)")
            grocery_cap_col, grocery_dl_col = st.columns([4, 1])
            with grocery_cap_col:
                st.caption(f"Use this list to shop for the week. Weekly plan cost ₹{cost:.0f} is within your budget of ₹{budget:.0f}." if within_budget else f"Weekly plan cost ₹{cost:.0f} (budget ₹{budget:.0f}).")
                st.caption("Items marked with ♻️ can be reused for future weeks.")
            with grocery_dl_col:
                st.download_button(
                    "Download grocery list",
                    data=_build_grocery_pdf(merged_groceries, total_grocery_cost),
                    file_name="grocery_list.pdf",
                    mime="application/pdf",
                    key="dl_grocery",
                )
            if merged_groceries:
                missing_qty = sum(1 for g in merged_groceries if not g[1] or g[1] == "—")
                if missing_qty == len(merged_groceries):
                    st.info("Regenerate your meal plan to get **quantities** and **reusable** labels for each item (e.g. Apple — 0.5 kg, Oil — 1 litre).")
                n_cols = 3
                reuse_emoji = "♻️ "
                for row_start in range(0, len(merged_groceries), n_cols):
                    row_items = merged_groceries[row_start : row_start + n_cols]
                    cols = st.columns(n_cols)
                    for col, (display_name, total_qty, approx_cost, is_reusable) in zip(cols, row_items):
                        with col:
                            qty_show = total_qty if (total_qty and total_qty != "—") else "—"
                            cost_str = f"₹{approx_cost:.0f}" if approx_cost else "—"
                            name_prefix = reuse_emoji if is_reusable else ""
                            safe_name = html_escape(display_name)
                            safe_qty = html_escape(qty_show)
                            st.markdown(
                                f'<div class="grocery-card">'
                                f'<div class="grocery-name">{name_prefix}{safe_name} — {safe_qty}</div>'
                                f'<div class="grocery-cost">{cost_str}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                if total_grocery_cost > 0:
                    st.markdown("---")
                    st.markdown(f"**Total approx grocery cost:** ₹{total_grocery_cost:.0f}")
            else:
                st.caption("— No items generated. Regenerate the meal plan to get items with quantity and cost.")
    finally:
        db.close()

with tab_workout:
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Complete your profile on the **Dashboard** tab first.")
        st.stop()

    def load_workout_plan_into_session(db):
        plan_obj = get_latest_workout_plan(db, user_id)
        if plan_obj and plan_obj.plan_json:
            import json
            st.session_state["latest_workout_plan"] = json.loads(plan_obj.plan_json)
        else:
            st.session_state["latest_workout_plan"] = None

    db = get_db_session()
    try:
        if st.session_state.get("latest_workout_plan") is None:
            load_workout_plan_into_session(db)

        gen_workout_clicked = st.button("Generate my workout plan", type="primary", help="Generate or replace your 7-day workout plan")
        if gen_workout_clicked:
            with st.spinner("Generating your workout plan…"):
                try:
                    plan = generate_and_save_workout_plan(db, user_id)
                    if plan:
                        st.session_state["latest_workout_plan"] = plan
                        st.success("Workout plan generated!")
                    else:
                        st.error("Could not generate workout plan. Please try again.")
                        st.caption("Check that workouts are loaded (scripts/load_workouts) and your Gemini API key is set in .env.")
                except Exception as e:
                    err = str(e)
                    if "429" in err or "quota" in err.lower():
                        st.warning("Rate limit reached. Wait about a minute and try again. You can switch to gemini-2.5-flash-lite in app/ai_engine/gemini_client.py if needed.")
                    else:
                        st.error("Could not generate workout plan. Please try again.")
                    with st.expander("Error details (for debugging)"):
                        st.code(err)

        plan = st.session_state.get("latest_workout_plan")
        if not plan:
            st.info("Generate your first workout plan using the button above.")
        else:
            st.subheader("Your weekly workout")
            for d in plan.get("days", []):
                day_num = d.get("day", 0)
                exercises = d.get("exercises", [])
                with st.expander(f"Day {day_num}"):
                    for ex in exercises:
                        name = ex.get("name", "")
                        duration = ex.get("duration_min", "")
                        instructions = ex.get("instructions", "") or ex.get("exercise_detail", "")
                        if instructions:
                            with st.expander(f"**{name}** — {duration} min", expanded=False):
                                st.markdown(instructions)
                        else:
                            st.markdown(f"**{name}** — {duration} min")
    finally:
        db.close()

with tab_progress:
    st.subheader("Log your weight to track progress over time.")

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Complete your profile on the **Dashboard** tab first.")
        st.stop()

    db = get_db_session()
    try:
        with st.form("log_weight_form"):
            weight_kg = st.number_input("Weight (kg)", min_value=30.0, max_value=300.0, value=70.0, step=0.5)
            log_date = st.date_input("Date", value=date.today())
            if st.form_submit_button("Log weight"):
                try:
                    log_weight(db, user_id, weight_kg, log_date)
                    st.success("Weight logged!")
                except Exception as e:
                    st.error(f"Could not log weight: {e}")

        logs = get_weight_logs(db, user_id)
        if len(logs) < 2:
            st.info("Log your first weight to see the chart. Add at least 2 entries for a trend line.")
        else:
            st.subheader("Weight trend")
            df = pd.DataFrame([
                {"date": log.logged_at, "weight_kg": float(log.weight_kg)}
                for log in logs
            ])
            # Ensure date is datetime for Altair
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            w_min, w_max = df["weight_kg"].min(), df["weight_kg"].max()
            y_padding = max(2.0, (w_max - w_min) * 0.15) if w_max > w_min else 2.0
            y_domain = [max(30, w_min - y_padding), min(200, w_max + y_padding)]

            chart = (
                alt.Chart(df)
                .mark_line(point={"size": 90, "filled": True}, strokeWidth=2)
                .encode(
                    x=alt.X("date:T", title="Date", axis=alt.Axis(format="%b %d", labelOverlap="parity")),
                    y=alt.Y("weight_kg:Q", title="Weight (kg)", scale=alt.Scale(domain=y_domain)),
                )
                .properties(
                    title=alt.TitleParams(text="Weight over time", subtitle="Log entries in the Progress tab"),
                    height=320,
                )
                .configure_axis(
                    labelFontSize=11,
                    titleFontSize=12,
                    gridOpacity=0.2,
                )
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)
    finally:
        db.close()