
"""Add meal_type, ingredients, instructions columns to recipes table if missing. Run once: uv run python -m scripts.migrate_add_meal_type"""
from sqlalchemy import text
from app.database import engine

def main():
    with engine.connect() as conn:
        # PostgreSQL: add columns if not exists
        for col, col_type in [
            ("meal_type", "VARCHAR"),
            ("ingredients", "TEXT"),
            ("instructions", "TEXT"),
        ]:
            conn.execute(text(f"""
                ALTER TABLE recipes
                ADD COLUMN IF NOT EXISTS {col} {col_type}
            """))
        conn.commit()
    print("Migration done: recipes.meal_type, ingredients, instructions added if missing.")

if __name__ == "__main__":
    main()