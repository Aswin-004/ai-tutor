"""Centralized environment configuration — single source of truth for all env vars.

Previously scattered across auth.py, core.py, mongo.py, and app.py, each
reading os.getenv() independently.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Auth / JWT ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set — refusing to start without it")
if len(SECRET_KEY) < 32:
    raise ValueError("SECRET_KEY must be at least 32 characters (256 bits) for HS256 security")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
if ALGORITHM != "HS256":
    raise ValueError(f"Only HS256 is supported; got {ALGORITHM}")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# --- MongoDB ---
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "ai_tutor")

# --- External API keys ---
JINA_API_KEY = os.getenv("JINA_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not JINA_API_KEY or not GOOGLE_API_KEY:
    raise ValueError("Missing API Keys in .env file")

# --- CORS ---
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _allowed_origins.split(",") if o.strip()]
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

if IS_PRODUCTION and any("localhost" in o for o in ALLOWED_ORIGINS):
    raise ValueError("localhost must not be in ALLOWED_ORIGINS in production. Set ALLOWED_ORIGINS env var.")
