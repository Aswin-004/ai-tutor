"""
Set required env vars at module level — must happen before any project imports
so that auth.py, core.py, etc. don't raise ValueError on missing keys.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("JINA_API_KEY", "test-jina-key")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "ai_tutor_test")
