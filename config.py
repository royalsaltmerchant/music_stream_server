import os

# === Config ===
CHUNK_SIZE = 1024
LISTENER_QUEUE_MAXSIZE = 256
SILENCE_PATH = "silence.mp3"
MUSIC_BASE_DIR = os.path.join("music", "strahd")
AVAILABLE_CHANNELS = ["alpha", "beta", "gamma", "delta", "epsilon"]

# === Load Silence Buffer ===
with open(SILENCE_PATH, "rb") as f:
    SILENT_BUFFER = f.read()
