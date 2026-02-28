# Health Companion

AI-powered personalized fitness and meal planning for students—tailored to goals, diet, budget, and equipment. Generates 7-day meal plans and workout plans using Gemini and your recipe/workout data.

---

## Clone & run in a few minutes

Follow these steps **in order** from your computer. All commands are run from the **Health_Companion** project folder (the one that contains `app/`, `scripts/`, and `pyproject.toml`).

### Step 0: Clone the project

If you don’t have the code yet:

```bash
git clone <YOUR_REPO_URL> Health_Companion
cd Health_Companion
```

Replace `<YOUR_REPO_URL>` with the actual repo URL (e.g. `https://github.com/yourusername/Health_Companion.git`). If you already have the folder, just open a terminal and `cd` into it.

---

### Step 1: Install prerequisites

You need these installed **before** the app will run:

| What | Why | How |
|------|-----|-----|
| **Python 3.12+** | Runtime | [python.org](https://www.python.org/downloads/) – check with `python --version` |
| **PostgreSQL** | Database | Install and start the server (e.g. port 5432). [PostgreSQL downloads](https://www.postgresql.org/download/) |
| **uv** | Package manager | `pip install uv` |
| **Gemini API key** | AI plans | Free at [Google AI Studio](https://aistudio.google.com/) → “Get API key” |

---

### Step 2: Configure environment

Create your `.env` file from the example:

- **Windows (Command Prompt):** `copy .env.example .env`
- **Windows (PowerShell) / macOS / Linux:** `cp .env.example .env`

Edit `.env` and set **both**:

```env
DATABASE_URL=postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
GEMINI_API_KEY=your_gemini_api_key_here
```

Example (local PostgreSQL, database name `health_companion`):

```env
DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/health_companion
GEMINI_API_KEY=AIzaSy...
```

- Get a Gemini key: [Google AI Studio](https://aistudio.google.com/) → Create API key.
- If your DB password has `@`, `#`, etc., percent-encode them (e.g. `@` → `%40`).

---

### Step 3: Install dependencies

From the **Health_Companion** folder:

```bash
uv sync
```

---

### Step 4: Set up the database

Run these **once** (first-time setup):

**4a. Create the database** (only if the DB in `DATABASE_URL` doesn’t exist yet):

```bash
uv run python -m scripts.create_db
```

**4b. Create all tables:**

```bash
uv run python -m scripts.init_db
```

**4c. Load recipes and workouts from CSV:**

```bash
uv run python -m scripts.load_recipes
uv run python -m scripts.load_workouts
```

You should see messages like “Loaded 151 recipes…” and “Loaded 100 workouts.”

**Optional:** If you had an old `recipes` table from before (not a fresh install) and get errors about missing columns, run once:

```bash
uv run python -m scripts.migrate_add_meal_type
```

Then run `load_recipes` again.

---

### Step 5: Run the app

From the **Health_Companion** folder:

```bash
uv run streamlit run app/app.py
```

Open the URL shown in the terminal (usually **http://localhost:8501**).

**You’re running successfully when:** The app opens with the title **Health Companion** and four tabs—**Dashboard**, **Nutrition & Meals**, **Workout**, **Progress**. Create a profile on the Dashboard, then generate a meal plan and a workout plan.

**Usage:** Dashboard → create or load profile (profile code or email) → **Nutrition & Meals** → generate meal plan → **Workout** → generate workout plan → **Progress** → log weight and view trend.

---

## Quick reference (already set up)

If the database, tables, and `.env` are already configured and you only need to start the app:

```bash
cd path/to/Health_Companion
uv sync
uv run streamlit run app/app.py
```

Then open **http://localhost:8501** in your browser.

---

## Project layout

| Path | Purpose |
|------|--------|
| `app/app.py` | Streamlit UI (tabs: Dashboard, Nutrition & Meals, Workout, Progress) |
| `app/config.py` | Loads `DATABASE_URL` and `GEMINI_API_KEY` from `.env` |
| `app/database.py` | SQLAlchemy engine and session |
| `app/models/` | User, Recipe, Workout, MealPlan, WorkoutPlan, ProgressLog |
| `app/services/` | user, recipe, workout, meal_plan, workout_plan, progress |
| `app/ai_engine/` | calorie_engine, gemini_client, meal_plan_generator, workout_plan_generator |
| `scripts/create_db.py` | Create PostgreSQL database |
| `scripts/init_db.py` | Create all tables |
| `scripts/migrate_add_meal_type.py` | Add meal_type, ingredients, instructions to `recipes` if missing |
| `scripts/load_recipes.py` | Load `data/recipes.csv` into DB |
| `scripts/load_workouts.py` | Load `data/workouts.csv` into DB |
| `data/recipes.csv` | Recipe data |
| `data/workouts.csv` | Workout/exercise data |

---

## Tech stack

- **Python 3.12+**
- **Streamlit** – web UI
- **SQLAlchemy** + **PostgreSQL** – database
- **google-generativeai** – Gemini API (meal and workout plan generation)
- **pandas**, **numpy** – data handling
- **python-dotenv** – environment variables

---

## Troubleshooting

| Problem | What to try |
|--------|-------------|
| App won’t start or “Database not configured” / “Gemini API key not found” | Ensure `.env` exists in the project root with `DATABASE_URL=postgresql://...` and `GEMINI_API_KEY=...`. Verify with: `uv run python -c "from app.config import DATABASE_URL, GEMINI_API_KEY; print('DB:', 'OK' if DATABASE_URL else 'Missing'); print('Gemini:', 'OK' if GEMINI_API_KEY else 'Missing')"` |
| “No module named 'app.database'” or “'app' is not a package” | Run all commands from the **Health_Companion** folder and start with `uv run streamlit run app/app.py` (not from inside `app/`). |
| “column ingredients does not exist” when loading recipes | Run `uv run python -m scripts.migrate_add_meal_type`, then `load_recipes` again. |
| “GEMINI_API_KEY not found” or “API key missing” | Add `GEMINI_API_KEY=your_key` to `.env`. Get a key from [Google AI Studio](https://aistudio.google.com/). |
| 429 quota exceeded | Wait about a minute and retry. Optionally change `MODEL_NAME` in `app/ai_engine/gemini_client.py` to `gemini-2.5-flash-lite`. |
| 404 model not found | The app uses `gemini-2.5-flash`. See [Gemini API models](https://ai.google.dev/gemini-api/docs/models). |

More detail: [POST_IMPLEMENTATION_ISSUES_AND_FIXES.md](POST_IMPLEMENTATION_ISSUES_AND_FIXES.md).

## Deployment

The Health Companion application is fully deployed using modern cloud technologies to ensure accessibility, scalability, and secure configuration management.

### Deployment Platform

- **Frontend Hosting:** Streamlit Cloud  
- **Database:** Neon PostgreSQL (Cloud-hosted)  
- **AI Model:** Google Gemini API  
- **Environment Management:** Streamlit Secrets (Production)

### Deployment Architecture

User (Browser)
      ↓

Streamlit Cloud App
      ↓

Gemini API (Generative AI)
      ↓
      
Neon PostgreSQL Cloud Database


### Environment Configuration

In production, sensitive credentials are securely managed using **Streamlit Secrets**, including:

- `DATABASE_URL`
- `GEMINI_API_KEY`

This ensures:
- No hardcoded credentials  
- Secure API key handling  
- Separation between local and production environments  

The application supports both:
- Local development using `.env`
- Cloud deployment using `st.secrets`


### Production Features Implemented

- Automatic database table creation  
- Auto-seeding of workout dataset in production  
- Cloud-based PostgreSQL integration  
- Error handling for API rate limits (429)  
- Environment fallback logic (local vs cloud)

---

### Live Application

🔗 https://health-companion-app.streamlit.app/


### What This Deployment Demonstrates

- Full-stack cloud integration  
- Secure API management  
- Real-world production debugging  
- AI model integration in a deployed environment