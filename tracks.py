import csv
import io
import logging
import re
import urllib.request
import urllib.error
from config import TRACKS_CSV_PATH

logger = logging.getLogger("radio.tracks")

# Track registry: KEY TITLE -> File Name
_tracks: dict[str, str] = {}

# Regex to detect Google Sheets URL and extract sheet ID and gid
_GSHEET_PATTERN = re.compile(
    r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)(?:/edit)?(?:\?.*gid=(\d+))?"
)


def _get_csv_export_url(sheets_url: str) -> str | None:
    """Convert a Google Sheets URL to its CSV export URL."""
    match = _GSHEET_PATTERN.match(sheets_url)
    if not match:
        return None
    sheet_id = match.group(1)
    gid = match.group(2) or "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _fetch_csv_from_url(url: str) -> str:
    """Fetch CSV content from a URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def _load_tracks():
    """Load tracks from CSV file or Google Sheets URL."""
    global _tracks
    new_tracks: dict[str, str] = {}

    try:
        # Check if it's a Google Sheets URL
        export_url = _get_csv_export_url(TRACKS_CSV_PATH)

        if export_url:
            logger.info(f"Fetching tracks from Google Sheets...")
            csv_content = _fetch_csv_from_url(export_url)
            reader = csv.DictReader(io.StringIO(csv_content))
        else:
            # Local file
            f = open(TRACKS_CSV_PATH, "r", encoding="utf-8")
            reader = csv.DictReader(f)

        for row in reader:
            key = row.get("KEY TITLE", "").strip()
            filename = row.get("File Name", "").strip()
            if key and filename:
                new_tracks[key] = filename

        if not export_url:
            f.close()

        _tracks = new_tracks
        logger.info(f"Loaded {len(_tracks)} tracks from {TRACKS_CSV_PATH}")

    except FileNotFoundError:
        logger.error(f"Tracks CSV not found: {TRACKS_CSV_PATH}")
    except urllib.error.URLError as e:
        logger.error(f"Failed to fetch tracks from URL: {e}")
    except Exception as e:
        logger.error(f"Failed to load tracks CSV: {e}")


def get_track_filename(key: str) -> str | None:
    """Get filename for a track key."""
    if not _tracks:
        _load_tracks()
    return _tracks.get(key)


def get_all_track_keys() -> list[str]:
    """Get all available track keys."""
    if not _tracks:
        _load_tracks()
    return list(_tracks.keys())


def reload_tracks():
    """Force reload tracks from CSV."""
    global _tracks
    _tracks = {}
    _load_tracks()
