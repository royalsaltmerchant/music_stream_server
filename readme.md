# Music Streaming Server | Far Reach Co.

A simple music streaming server built with FastAPI, FFmpeg, and PostgreSQL-backed sessions. Streams audio files from categorized playlists and allows authenticated users to control playback (play, switch playlists). Music is organized into categories (e.g., "strahd", "ambient") with playlists nested within each category.

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
SESSION_COOKIE_NAME = "frc_session"
SESSION_DB_DSN = "postgresql://user:pass@localhost:5432/your_db"

MUSIC_BASE_DIR = "music"  # Base directory containing category folders

CHUNK_SIZE = 4096
LISTENER_QUEUE_MAXSIZE = 5
SILENT_BUFFER = b"\0" * CHUNK_SIZE
```

---

## Directory Structure

Music files should be organized into a two-level hierarchy: categories and playlists.

```
music/
├── strahd/              # Category 1
│   ├── combat/          # Playlist 1
│   │   ├── track1.mp3
│   │   └── track2.mp3
│   ├── Church/          # Playlist 2
│   │   └── hymn.mp3
│   └── Town/            # Playlist 3
│       └── ambient.mp3
└── ambient/             # Category 2
    ├── nature/          # Playlist 4
    │   └── forest.mp3
    └── tavern/          # Playlist 5
        └── chatter.mp3
```

**Supported audio formats:** `.mp3`, `.wav`, `.ogg`, `.flac`

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

### `GET /host?channel=some_channel`
Requires login. Shows host controls for managing the specified channel.

### `GET /playlists`
Requires login. Returns available categories and their playlists.

Response format:
```json
{
  "categories": {
    "strahd": ["Argynvostholt", "Church", "combat", "Town"],
    "ambient": ["nature", "tavern"]
  }
}
```

### `POST /command`
Requires login. Controls playback or switches playlists.

Send a command (next/stop):
```json
{
  "channel": "my_channel",
  "command": "next"
}
```

Or switch to a playlist (format: `category/playlist`):
```json
{
  "channel": "my_channel",
  "playlist": "strahd/combat"
}
```

### `GET /stream?channel=some_channel`
Streams MP3 audio for that channel.

---

## Notes

- Music must be organized in a two-level directory structure: `category/playlist/`
- The server only streams `.mp3`, `.wav`, `.ogg`, `.flac` files
- You must have `ffmpeg` installed and accessible from the command line
- Empty categories (categories with no playlists) are automatically filtered from the API
- Long-lived background threads will terminate if no listeners connect for `IDLE_TIMEOUT` seconds (default 600)