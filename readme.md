# Music Streaming Server | Far Reach Co.

A music streaming server built with FastAPI, FFmpeg, and PostgreSQL-backed sessions. Streams audio files from S3/CloudFront using signed URLs and allows authenticated users to control playback. Tracks are registered via CSV and organized into named playlists.

---

## Requirements

- Python 3.10+
- FFmpeg installed and available in `$PATH`
- AWS S3 bucket with CloudFront distribution
- CloudFront key pair for signed URLs

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

Set the following environment variables (or in `.env` file):

### Required

```bash
# Session/Auth
SESSION_SECRET=your-signing-secret
PG_DB=your_database
PG_USER=your_user
PG_PW=your_password
PG_HOST=localhost

# CloudFront
CLOUDFRONT_DOMAIN=d1234567890.cloudfront.net
CLOUDFRONT_KEY_ID=KXXXXXXXXXXXXXXX
CLOUDFRONT_PRIVATE_KEY_PATH=./private_frc_cloudfront_key.pem
```

### Optional

```bash
TRACKS_CSV_PATH=tracks.csv          # Default: tracks.csv
SESSION_COOKIE_NAME=frc_session     # Default: frc_session
HOST=0.0.0.0                        # Default: 0.0.0.0
PORT=5000                           # Default: 5000
CHUNK_SIZE=1024                     # Default: 1024
LISTENER_QUEUE_MAXSIZE=256          # Default: 256
IDLE_TIMEOUT=600                    # Default: 600 (seconds)
LOGIN_URL=https://example.com/login # Redirect URL for unauthenticated users
```

---

## Track Registry (CSV)

Tracks are registered in a CSV file with the following headers:

```
Track Name,File Name,KEY TITLE,Track Number,Album,Psudo-Tags,Previous Titles
```

Example row:
```
Haunting Tavern,haunting_tavern_remst_fullmix.mp3,HAUNTING_TAVERN_REMST_FULLMIX,1,Secrets of Strahd Original Soundtrack,"peaceful, town, village, horror, sos",
```

- **KEY TITLE**: Unique identifier used in playlist definitions
- **File Name**: Filename in S3 (stored at `s3://bucket/audio/{filename}`)

---

## Playlist Definitions

Playlists are defined in `playlists.py`:

```python
PLAYLISTS = {
    "tavern_ambience": ["HAUNTING_TAVERN_REMST_FULLMIX", "TAVERN_BUSTLE"],
    "combat_epic": ["BATTLE_EPIC1", "BATTLE_EPIC2"],
}
```

Each playlist maps to a list of track keys from the CSV.

---

## S3/CloudFront Setup

Audio files should be stored in S3 with the path prefix `/audio/`:

```
s3://your-bucket/
└── audio/
    ├── haunting_tavern_remst_fullmix.mp3
    ├── battle_epic_01.mp3
    └── ...
```

CloudFront should be configured with:
- Origin pointing to your S3 bucket
- Signed URL requirement (restricted viewer access)
- Key pair for signing (private key stored locally)

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
Requires login. Returns available playlist names.

Response format:
```json
{
  "playlists": ["tavern_ambience", "combat_epic", "exploration"]
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

Or switch to a playlist by name:
```json
{
  "channel": "my_channel",
  "playlist": "tavern_ambience"
}
```

### `GET /stream?channel=some_channel`
Streams MP3 audio for that channel.

---

## Notes

- Audio files are streamed from CloudFront via signed URLs (3-day expiry)
- FFmpeg reads directly from the signed URL and transcodes to MP3
- The server streams `.mp3`, `.wav`, `.ogg`, `.flac` files (any format FFmpeg supports)
- You must have `ffmpeg` installed and accessible from the command line
- Background streamer threads terminate if no listeners connect for `IDLE_TIMEOUT` seconds (default 600)
