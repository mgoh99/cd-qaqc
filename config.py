import os
from dotenv import load_dotenv

load_dotenv()

WRIKE_TOKEN                = os.getenv("WRIKE_TOKEN", "")
SUPABASE_URL               = os.getenv("SUPABASE_URL", "")
SUPABASE_API_KEY           = os.getenv("SUPABASE_API_KEY", "")
FLASK_SECRET_KEY           = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
SESSION_LIFETIME_SECONDS   = int(os.getenv("SESSION_LIFETIME_SECONDS", "86400"))
