"""Central configuration for Binance Square Content Engine."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

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
HAS_OPENAI = bool(OPENAI_API_KEY)
