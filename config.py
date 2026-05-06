"""Central configuration for Binance Square Content Engine."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
# Google Gemini powers the Content Generator + Engagement Assistant.
# Get a key at https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# --- Web server ---
PORT = int(os.getenv("PORT", "5000"))

# --- Timezone (Binance Square targets a global EN audience, always plan in UTC) ---
TIMEZONE = os.getenv("TIMEZONE", "UTC")

# --- Paths ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
PROMPTS_DIR = os.path.join(ROOT_DIR, "prompts")
STATIC_DIR = os.path.join(ROOT_DIR, "static")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Posting windows (UTC) where Binance Square EN traffic peaks ---
# Tuned for overlap between US morning (13-16 UTC) and ME evening (19-20 UTC).
PRIME_POSTING_HOURS_UTC = [13, 14, 15, 16, 19, 20]

# --- Feature flags ---
HAS_LLM = bool(GEMINI_API_KEY)
