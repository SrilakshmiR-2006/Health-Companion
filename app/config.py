import os
import streamlit as st

# First try Streamlit secrets (Cloud)
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    # Fallback to local .env
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")