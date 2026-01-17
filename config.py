import os
from dotenv import load_dotenv

load_dotenv()


# === Config ===
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
LISTENER_QUEUE_MAXSIZE = int(os.getenv("LISTENER_QUEUE_MAXSIZE", "256"))
IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", "600"))
SILENCE_PATH = os.getenv("SILENCE_PATH", "silence.mp3")
MUSIC_BASE_DIR = os.getenv("MUSIC_BASE_DIR", "music")

# Server configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
LOGIN_URL = os.getenv("LOGIN_URL", "https://farreachco.com/login")

# Session configuration
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "frc_session")
SESSION_SECRET = os.getenv("SESSION_SECRET") or exit("SESSION_SECRET is required")

# Database configuration (all required for security)
PG_DB = os.getenv("PG_DB") or exit("PG_DB environment variable required")
PG_USER = os.getenv("PG_USER") or exit("PG_USER environment variable required")
PG_PW = os.getenv("PG_PW") or exit("PG_PW environment variable required")
PG_HOST = os.getenv("PG_HOST") or exit("PG_HOST environment variable required")
SESSION_DB_DSN = f"dbname={PG_DB} user={PG_USER} password={PG_PW} host={PG_HOST}"

# === Load Silence Buffer ===
try:
    with open(SILENCE_PATH, "rb") as f:
        SILENT_BUFFER = f.read()
except FileNotFoundError:
    import logging
    logging.warning(f"Silence buffer file not found: {SILENCE_PATH}. Using fallback.")
    SILENT_BUFFER = b"\x00" * CHUNK_SIZE
