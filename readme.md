# Music Streaming Server | Far Reach Co.

A simple music streaming server built with FastAPI, FFmpeg, and PostgreSQL-backed sessions. Streams audio files from playlists and allows authenticated users to control playback (play, switch playlists).

---

## Requirements

- Python 3.10+
- FFmpeg installed and available in `$PATH`

---

## Installation

```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Config

Set the following values in `config.py` or via environment variables:

```python
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "your-signing-secret"
SESSION_COOKIE_NAME = "frcsession"
SESSION_DB_DSN = "postgresql://user:pass@localhost:5432/your_db"

MUSIC_BASE_DIR = "./music"

CHUNK_SIZE = 4096
LISTENER_QUEUE_MAXSIZE = 5
SILENT_BUFFER = b"\0" * CHUNK_SIZE
```

---

## Run

```bash
python3 radio.py
```

Or with `uvicorn` manually:

```bash
uvicorn radio:service.app --reload --host 0.0.0.0 --port 5000
```

---

## Authentication

This server reads Express-compatible signed cookies (e.g., `s:<value>.<sig>`) and validates them using HMAC SHA256.

Session data is loaded from a `session` table in PostgreSQL. Example schema:

```sql
CREATE TABLE session (
  sid VARCHAR PRIMARY KEY,
  sess JSONB NOT NULL,
  expire TIMESTAMP NOT NULL
);
```

Expected JSON structure:

```json
{
  "user": "user_id_value"
}
```

---

## API Endpoints

### `GET /`
Returns the main landing page (`index.html`).

### `GET /listen?channel=some_channel`
Returns the listener interface.

### `GET /host`
Requires login. Shows host controls.

### `POST /command`
JSON body:
```json
{
  "channel": "my_channel",
  "command": "next" // or "stop"
}
```
Or:
```json
{
  "channel": "my_channel",
  "playlist": "folder_name"
}
```

### `GET /stream?channel=some_channel`
Streams MP3 audio for that channel.

---

## Notes

- The server only streams `.mp3`, `.wav`, `.ogg`, `.flac` files.
- You must have `ffmpeg` installed and accessible from the command line.
- Long-lived background threads will terminate if no listeners connect for `IDLE_TIMEOUT` seconds (default 600).