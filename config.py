import os
from dotenv import load_dotenv

load_dotenv()


# === Config ===
CHUNK_SIZE = 1024
LISTENER_QUEUE_MAXSIZE = 256
SILENCE_PATH = "silence.mp3"
MUSIC_BASE_DIR = os.path.join("music", "strahd")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "frcsession")
SESSION_SECRET = os.getenv("SESSION_SECRET") or exit("SESSION_SECRET is required")

PG_DB = os.getenv("PG_DB", "radio_dev")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PW = os.getenv("PG_PW", "")
PG_HOST = os.getenv("PG_HOST", "localhost")
SESSION_DB_DSN = f"dbname={PG_DB} user={PG_USER} password={PG_PW} host={PG_HOST}"

# === Load Silence Buffer ===
with open(SILENCE_PATH, "rb") as f:
    SILENT_BUFFER = f.read()
